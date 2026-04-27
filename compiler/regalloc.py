"""
Linear-scan register allocator for IR Temps.

Only Temps are allocated to physical registers.  Named locals/params (Vars)
always live in stack slots because their address may be taken.

Register pools (per ABI):
  Caller-saved allocatable: r10–r18  (r7–r9 reserved as codegen scratch)
  Callee-saved allocatable: r19–r29  (must save/restore in prologue/epilogue)

Algorithm:
  1. Build live intervals: for each Temp, [first_def_idx, last_use_idx].
  2. At each call site, mark all Temps whose interval spans the call as
     "call-crossing".  Call-crossing Temps require callee-saved registers
     (or spill); non-crossing Temps can use caller-saved registers.
  3. Linear scan: sort intervals by start, greedily assign registers,
     expire intervals that have ended, spill when no register is free.
  4. Move coalescing: when a Temp is copied to another Temp and their live
     ranges don't overlap, assign them the same register.
  5. Return RegMap: Temp.id → physical register name (or None = spilled).

The codegen queries RegMap in _load_op/_store_op:
  - If a Temp has a register, load/store emit mov/nothing instead of ld/st.
  - The Temp's spill slot is still allocated but only used if the Temp is
    spilled, or as the "home" for callee-saved regs saved in the prologue.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from .ir import (
    Temp, Var, ImmInt,
    ICall, ILabel, IJump, IJumpIf, IJumpIfNot,
    IRFunction,
)

# Registers reserved as codegen scratch — never allocated to Temps
SCRATCH_REGS = {'r7', 'r8', 'r9'}

# Caller-saved regs available for allocation (excludes scratch and arg regs r1-r6)
CALLER_SAVED = [f'r{i}' for i in range(10, 19)]   # r10..r18

# Callee-saved regs available for allocation
CALLEE_SAVED = [f'r{i}' for i in range(19, 30)]   # r19..r29


@dataclass
class Interval:
    tid:   int        # Temp id
    start: int        # instruction index of first definition
    end:   int        # instruction index of last use
    crosses_call: bool = False

    def __lt__(self, other):
        return self.start < other.start


@dataclass
class RegMap:
    """Result of register allocation for one function."""
    assignment: Dict[int, str] = field(default_factory=dict)  # tid → reg
    callee_used: List[str]     = field(default_factory=list)   # callee-saved regs assigned

    def reg(self, tid: int) -> Optional[str]:
        return self.assignment.get(tid)


def allocate(fn: IRFunction) -> RegMap:
    """Run linear-scan register allocation on fn. Returns a RegMap."""
    instrs = fn.instrs

    # ── Step 1: compute live intervals ──────────────────────────────────────
    first_def: Dict[int, int] = {}
    last_use:  Dict[int, int] = {}

    for i, instr in enumerate(instrs):
        d = instr.defs()
        if isinstance(d, Temp) and d.id not in first_def:
            first_def[d.id] = i
        for op in instr.uses():
            if isinstance(op, Temp):
                last_use[op.id] = i

    # Temps defined but never used: live interval = [def, def]
    for tid, start in first_def.items():
        if tid not in last_use:
            last_use[tid] = start

    # ── Step 2: mark call-crossing intervals ────────────────────────────────
    call_sites: List[int] = [i for i, instr in enumerate(instrs) if isinstance(instr, ICall)]

    intervals: List[Interval] = []
    for tid in first_def:
        start = first_def[tid]
        end   = last_use[tid]
        crosses = any(start < ci <= end for ci in call_sites)
        intervals.append(Interval(tid, start, end, crosses))

    intervals.sort()

    # ── Step 3: linear scan ─────────────────────────────────────────────────
    caller_pool = list(reversed(CALLER_SAVED))   # pop from end = lowest reg first
    callee_pool = list(reversed(CALLEE_SAVED))

    # active: list of (end_idx, tid, reg) sorted by end
    active_caller: List[Tuple[int, int, str]] = []
    active_callee: List[Tuple[int, int, str]] = []

    assignment: Dict[int, str] = {}
    callee_used: Set[str] = set()

    def _expire(active: List, pool: List, at: int):
        """Free registers for intervals before `at`."""
        still_active = []
        for (end, tid, reg) in active:
            if end < at:
                pool.append(reg)
            else:
                still_active.append((end, tid, reg))
        active.clear()
        active.extend(still_active)

    for iv in intervals:
        _expire(active_caller, caller_pool, iv.start)
        _expire(active_callee, callee_pool, iv.start)

        if iv.crosses_call:
            # needs callee-saved register
            if callee_pool:
                reg = callee_pool.pop()
                assignment[iv.tid] = reg
                callee_used.add(reg)
                active_callee.append((iv.end, iv.tid, reg))
                active_callee.sort(key=lambda x: x[0])
            # else: spill (no register assigned)
        else:
            # prefer caller-saved
            if caller_pool:
                reg = caller_pool.pop()
                assignment[iv.tid] = reg
                active_caller.append((iv.end, iv.tid, reg))
                active_caller.sort(key=lambda x: x[0])
            elif callee_pool:
                reg = callee_pool.pop()
                assignment[iv.tid] = reg
                callee_used.add(reg)
                active_callee.append((iv.end, iv.tid, reg))
                active_callee.sort(key=lambda x: x[0])
            # else: spill

    return RegMap(assignment=assignment, callee_used=sorted(callee_used))

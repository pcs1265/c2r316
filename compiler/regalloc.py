"""
Linear-scan register allocator for IR Temps.

Only Temps are allocated to physical registers.  Named locals/params (Vars)
always live in stack slots because their address may be taken.

Register pools (per ABI):
  r7–r9   : codegen scratch — never allocated to Temps
  r10–r18 : caller-saved — allocatable, but r10–r16 are also the inline-asm
             operand pool (%0–%9 → r7–r16); see clobber handling below
  r19–r29 : callee-saved — used for Temps that must survive a call

Crossing markers (both use strict inequality: start < site < end, so a Temp
whose last use IS the event does not need to survive it):

  crosses_call: a call site falls within the live range.
                The Temp must reside in a callee-saved register.

  forbidden:    union of IInlineAsm.clobbers for every asm site within the
                live range.  The Temp must not be assigned any register in
                this set.  For a k-operand asm, clobbers = {r7..r7+k-1};
                since r7–r9 are not allocatable, only r10–r16 matter in
                practice.

Algorithm:
  1. Build live intervals [first_def, last_use] for each Temp.
  2. Mark crosses_call and compute forbidden per interval.
  3. Linear scan: sort by start, greedily assign from caller_free / callee_free
     filtered by forbidden, expire ended intervals, evict if no register fits.
  4. Return RegMap: Temp.id → physical register (or None = spilled).
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Optional, Set, Tuple

from .ir import (
    Temp, Var, ImmInt,
    ICall, IInlineAsm,
    IRFunction,
)

# Registers reserved as codegen scratch — never allocated to Temps.
SCRATCH_REGS = {'r7', 'r8', 'r9'}

# Caller-saved registers available for allocation (scratch excluded).
CALLER_SAVED = [f'r{i}' for i in range(10, 19)]  # r10..r18

# Callee-saved registers available for allocation.
CALLEE_SAVED = [f'r{i}' for i in range(19, 30)]  # r19..r29

CALLEE_SET = frozenset(CALLEE_SAVED)


@dataclass
class Interval:
    tid:          int
    start:        int
    end:          int
    crosses_call: bool          = False
    forbidden:    FrozenSet[str] = field(default_factory=frozenset)

    def __lt__(self, other):
        return self.start < other.start


@dataclass
class RegMap:
    """Result of register allocation for one function."""
    assignment:  Dict[int, str] = field(default_factory=dict)
    callee_used: List[str]      = field(default_factory=list)

    def reg(self, tid: int) -> Optional[str]:
        return self.assignment.get(tid)


def allocate(fn: IRFunction) -> RegMap:
    """Run linear-scan register allocation on fn.  Returns a RegMap."""
    instrs = fn.instrs

    # ── Step 1: live intervals ───────────────────────────────────────────────
    first_def: Dict[int, int] = {}
    last_use:  Dict[int, int] = {}

    for i, instr in enumerate(instrs):
        d = instr.defs()
        if isinstance(d, Temp) and d.id not in first_def:
            first_def[d.id] = i
        for op in instr.uses():
            if isinstance(op, Temp):
                last_use[op.id] = i

    for tid, start in first_def.items():
        if tid not in last_use:
            last_use[tid] = start

    # ── Step 2: crossing markers ─────────────────────────────────────────────
    # Strictly < end: a Temp whose last use IS the event only needs to be
    # readable before it — it does not need to survive through it.
    call_sites: List[Tuple[int, None]] = [
        i for i, instr in enumerate(instrs) if isinstance(instr, ICall)
    ]
    asm_instrs: List[Tuple[int, IInlineAsm]] = [
        (i, instr) for i, instr in enumerate(instrs) if isinstance(instr, IInlineAsm)
    ]

    use_count: Dict[int, int] = {}
    for instr in instrs:
        for op in instr.uses():
            if isinstance(op, Temp):
                use_count[op.id] = use_count.get(op.id, 0) + 1

    def _spill_cost(tid: int, start: int, end: int) -> float:
        return use_count.get(tid, 0) / max(1, end - start)

    intervals: List[Interval] = []
    for tid in first_def:
        start = first_def[tid]
        end   = last_use[tid]
        crosses_call = any(start < ci < end for ci in call_sites)
        # Union the clobbers of every asm instruction whose site is strictly
        # within the live range.  Callee-saved regs (r19+) are never in any
        # clobber set, so forbidden only ever restricts caller-saved choices.
        forbidden: FrozenSet[str] = frozenset().union(*(
            instr.clobbers
            for ai, instr in asm_instrs
            if start < ai < end
        ))
        intervals.append(Interval(tid, start, end, crosses_call, forbidden))

    intervals.sort()

    # ── Step 3: linear scan ─────────────────────────────────────────────────
    caller_free: Set[str] = set(CALLER_SAVED)
    callee_free: Set[str] = set(CALLEE_SAVED)

    # active: (end, tid, reg) — one list; reg class inferred from CALLEE_SET
    active: List[Tuple[int, int, str]] = []

    assignment:  Dict[int, str] = {}
    callee_used: Set[str]       = set()

    def _expire(at: int):
        still = []
        for (end, tid, reg) in active:
            if end < at:
                (callee_free if reg in CALLEE_SET else caller_free).add(reg)
            else:
                still.append((end, tid, reg))
        active.clear()
        active.extend(still)

    def _assign(iv: Interval, reg: str):
        assignment[iv.tid] = reg
        if reg in CALLEE_SET:
            callee_used.add(reg)
        active.append((iv.end, iv.tid, reg))
        active.sort(key=lambda x: x[0])

    def _pick(pool: Set[str], forbidden: FrozenSet[str],
              prefer_order: List[str]) -> Optional[str]:
        """Choose the first register from prefer_order that is in pool and not forbidden."""
        for r in prefer_order:
            if r in pool and r not in forbidden:
                return r
        return None

    def _evict(iv: Interval, forbidden: FrozenSet[str],
               require_callee: bool) -> bool:
        """Evict the cheapest active entry whose reg is usable for iv."""
        best_idx, best_cost, best_reg = None, float('inf'), None
        for k, (end, tid, reg) in enumerate(active):
            if require_callee and reg not in CALLEE_SET:
                continue
            if reg in forbidden:
                continue
            cost = _spill_cost(tid, first_def[tid], end)
            if cost < best_cost:
                best_cost, best_idx, best_reg = cost, k, reg
        if best_idx is None:
            return False
        cur_cost = _spill_cost(iv.tid, iv.start, iv.end)
        if best_cost >= cur_cost:
            return False  # current interval is cheaper to spill
        end_, evict_tid, reg = active.pop(best_idx)
        del assignment[evict_tid]
        _assign(iv, reg)
        return True

    for iv in intervals:
        _expire(iv.start)

        if iv.crosses_call:
            # Must be in callee-saved to survive the call.
            reg = _pick(callee_free, iv.forbidden, CALLEE_SAVED)
            if reg is not None:
                callee_free.discard(reg)
                _assign(iv, reg)
            else:
                _evict(iv, iv.forbidden, require_callee=True)
        else:
            # Prefer caller-saved (cheaper: no save/restore), then callee-saved.
            reg = _pick(caller_free, iv.forbidden, CALLER_SAVED)
            if reg is not None:
                caller_free.discard(reg)
                _assign(iv, reg)
            else:
                reg = _pick(callee_free, iv.forbidden, CALLEE_SAVED)
                if reg is not None:
                    callee_free.discard(reg)
                    _assign(iv, reg)
                else:
                    if not _evict(iv, iv.forbidden, require_callee=False):
                        pass  # spilled — no assignment

    return RegMap(assignment=assignment, callee_used=sorted(callee_used))

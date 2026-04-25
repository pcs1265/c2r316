"""
C to R316 Compiler - Code Generator
IR → TPTASM R316 Assembly

ABI (see docs/ABI.md for full specification):
  r0       : zero (read-only)
  r1..r6   : arguments / return values (a0-a5)
  r7..r18  : caller-saved temporaries (t0-t11)
  r19..r29 : callee-saved (s0-s10)
  r30 (sp) : stack pointer (grows downward)
  r31 (lr) : link register

Stack frame layout (per function):
  [sp+0 .. sp+F-1]          : spill slots for Temps and local Vars
  [sp+F .. sp+F+CS-1]       : saved callee-saved registers (only those used)
  [sp+F+CS]                 : saved lr (non-leaf functions only)
  [sp+F+CS+1 .. ]           : stack arguments (7th+, caller's responsibility)

Register allocation:
  Each Temp/Var gets a fixed spill slot allocated linearly.
  Small number of physical regs used as scratch; values always
  loaded into scratch before use and stored back after def.

  scratch regs: r7 (primary/left/dst), r8 (secondary/right), r9 (address)
"""

from __future__ import annotations
import os
from typing import Dict, List, Optional, Set

from .ir import (
    Temp, Var, Global, ImmInt, StrLabel, Operand,
    IConst, ICopy, IAddrOf, IBinOp, IUnaryOp, ILoad, IStore,
    ICall, IRet, ILabel, IJump, IJumpIf, IJumpIfNot,
    IInlineAsm, IVaStart, IVaArg, IRFunction, IRProgram, Instr,
)
from .regalloc import allocate, RegMap


class CodegenError(Exception):
    pass


# ── Physical register names (per docs/ABI.md) ─────────────────────────────────

SP         = 'r30'
LR         = 'r31'
SCRATCH_A  = 'r7'   # primary scratch / result
SCRATCH_B  = 'r8'   # secondary scratch
SCRATCH_C  = 'r9'   # address scratch

ARG_REGS   = ['r1', 'r2', 'r3', 'r4', 'r5', 'r6']
RET_REG    = 'r1'

# Callee-saved registers that the compiler may allocate
CALLEE_SAVED_REGS = [f'r{i}' for i in range(19, 30)]  # r19..r29


class FuncContext:
    """
    Spill-slot allocator with temp recycling.
    Vars (locals/params) get permanent slots.
    Temps get slots recycled after their last use.

    outgoing_slots: number of words at [sp+0..sp+outgoing_slots-1] reserved
    for outgoing stack arguments; all other slots start above this area.
    """

    def __init__(self, instrs: list, params: list[str], local_sizes: Dict[str, int] = None,
                 outgoing_slots: int = 0):
        self._slots:    Dict[str, int] = {}
        self._free:     list[int]      = []   # recycled slots available
        self._next      = outgoing_slots       # start above the outgoing-arg area
        self._peak      = outgoing_slots

        # params first — permanent slots starting at outgoing_slots
        for name in params:
            self._alloc_permanent(f'v_{name}')

        # pre-reserve contiguous slots for locals larger than 1 word (arrays)
        for name, size in (local_sizes or {}).items():
            if size > 1:
                self._alloc_permanent_block(f'v_{name}', size)

        # compute last-use index for every Temp
        last_use: Dict[int, int] = {}
        for i, instr in enumerate(instrs):
            for op in instr.uses():
                if isinstance(op, Temp):
                    last_use[op.id] = i
            # a Temp that is defined but never used still gets a slot;
            # mark its last use as the def site so it's freed immediately
            d = instr.defs()
            if isinstance(d, Temp) and d.id not in last_use:
                last_use[d.id] = i

        self._last_use = last_use
        self._instrs   = instrs

    def _alloc_permanent(self, key: str) -> int:
        slot = self._next
        self._next += 1
        self._peak  = max(self._peak, self._next)
        self._slots[key] = slot
        return slot

    def _alloc_permanent_block(self, key: str, size: int) -> int:
        """Reserve `size` contiguous slots; key maps to the first slot."""
        slot = self._next
        self._next += size
        self._peak  = max(self._peak, self._next)
        self._slots[key] = slot
        return slot

    def _alloc_temp(self, key: str) -> int:
        if self._free:
            slot = self._free.pop()
        else:
            slot = self._next
            self._next += 1
            self._peak  = max(self._peak, self._next)
        self._slots[key] = slot
        return slot

    def slot(self, op: Operand) -> int:
        if isinstance(op, Temp):
            key = f't{op.id}'
            if key not in self._slots:
                self._alloc_temp(key)
            return self._slots[key]
        if isinstance(op, Var):
            key = f'v_{op.name}'
            if key not in self._slots:
                self._alloc_permanent(key)
            return self._slots[key]
        raise CodegenError(f"No slot for {op}")

    def free_dead_temps(self, instr_idx: int):
        """Release slots for Temps whose last use is at instr_idx."""
        instr = self._instrs[instr_idx]
        for op in instr.uses():
            if isinstance(op, Temp) and self._last_use.get(op.id) == instr_idx:
                key = f't{op.id}'
                if key in self._slots:
                    self._free.append(self._slots.pop(key))
        # also free a def-only temp (never used) right after its def
        d = instr.defs()
        if isinstance(d, Temp) and self._last_use.get(d.id) == instr_idx:
            key = f't{d.id}'
            if key in self._slots:
                self._free.append(self._slots.pop(key))

    @property
    def frame_size(self) -> int:
        return self._peak


class Codegen:
    def __init__(self):
        self._out:  list[str] = []
        self._ctx:  Optional[FuncContext] = None
        self._is_leaf = False
        self._callee_saves: List[str] = []  # callee-saved regs used by current function
        self._frame_size = 0
        self._callee_save_n = 0
        # source annotation (-g flag)
        self._annotate = False
        self._src_lines: list[str] = []
        self._src_name: str = ''
        self._last_src_line: int = 0
        # scratch-register forwarding: tracks which Temp is live in SCRATCH_A/SCRATCH_C
        self._scratch_a_temp: Optional[Temp] = None
        self._scratch_c_temp: Optional[Temp] = None
        # register allocation map for current function
        self._regmap: Optional[RegMap] = None
        # fused compare-branch indices for current function
        self._fused_cmp: dict = {}
        self._fused_branch_idxs: set = set()
        # variadic support
        self._va_spill_base: int = 0   # frame offset where arg-reg spill starts
        self._va_spill_n:    int = 0   # number of arg-reg spill slots (0 or 6)
        # ASM peephole stats
        self._peephole_eliminated: int = 0

    # ── Source annotation (-g) ────────────────────────────────────────────────

    def set_source(self, src: str, src_name: str):
        """Enable source annotation for -g flag."""
        self._annotate = True
        self._src_name = src_name
        self._file_lines: dict = {}   # filename -> list[str]
        self._last_loc = None

    def _get_file_lines(self, filename: str):
        if filename not in self._file_lines:
            try:
                import os
                with open(filename, encoding='utf-8') as f:
                    self._file_lines[filename] = f.read().split('\n')
            except OSError:
                self._file_lines[filename] = []
        return self._file_lines[filename]

    def _emit_src_comment(self, instr: Instr):
        """Emit a source line comment if annotation is enabled and line changed."""
        if not self._annotate or not instr.loc:
            return
        fname, line = instr.loc
        if (fname, line) == self._last_loc:
            return
        lines = self._get_file_lines(fname)
        if 1 <= line <= len(lines):
            src_text = lines[line - 1].strip()
            if src_text:
                self._emit(f'    ; {fname}:{line}: {src_text}')
        self._last_loc = (fname, line)

    # ── Output ────────────────────────────────────────────────────────────────

    def _emit(self, line: str):
        self._out.append(line)

    def _lbl(self, name: str):
        self._emit(f'{name}:')

    def _ins(self, s: str):
        self._emit(f'    {s}')

    # ── Spill helpers ─────────────────────────────────────────────────────────

    def _spill_slot(self, op: Operand) -> int:
        return self._ctx.slot(op)

    def _invalidate_scratch(self):
        """Call before any instruction that clobbers scratch regs without tracking."""
        self._scratch_a_temp = None
        self._scratch_c_temp = None

    def _load_op(self, op: Operand, reg: str):
        """Load operand value into physical register."""
        if isinstance(op, ImmInt):
            if reg == SCRATCH_A and self._scratch_a_temp is not None:
                self._scratch_a_temp = None
            elif reg == SCRATCH_C and self._scratch_c_temp is not None:
                self._scratch_c_temp = None
            self._ins(f'mov {reg}, {op.value & 0xFFFF}')
        elif isinstance(op, StrLabel):
            self._ins(f'mov {reg}, {op.name}')
        elif isinstance(op, Global):
            self._ins(f'ld {reg}, {self._mangle_global(op.name)}')
        elif isinstance(op, (Temp, Var)):
            # if this temp is already in the target register, skip the load
            if isinstance(op, Temp):
                # check register allocator assignment
                preg = self._regmap.reg(op.id) if self._regmap else None
                if preg is not None:
                    if preg != reg:
                        self._ins(f'mov {reg}, {preg}')
                    # invalidate scratch tracking if we wrote to a scratch reg
                    if reg == SCRATCH_A:
                        self._scratch_a_temp = None
                    elif reg == SCRATCH_C:
                        self._scratch_c_temp = None
                    return
                if self._scratch_a_temp == op:
                    if reg != SCRATCH_A:
                        self._ins(f'mov {reg}, {SCRATCH_A}')
                        if reg == SCRATCH_C:
                            self._scratch_c_temp = op
                    return
                if self._scratch_c_temp == op:
                    if reg != SCRATCH_C:
                        self._ins(f'mov {reg}, {SCRATCH_C}')
                        if reg == SCRATCH_A:
                            self._scratch_a_temp = op
                    return
            slot = self._spill_slot(op)
            self._ins(f'ld {reg}, {SP}, {slot}')
            if reg == SCRATCH_A:
                self._scratch_a_temp = op if isinstance(op, Temp) else None
            elif reg == SCRATCH_C:
                self._scratch_c_temp = op if isinstance(op, Temp) else None
        else:
            raise CodegenError(f"Cannot load {op}")

    def _store_op(self, reg: str, op: Operand, skip_if_last: bool = False):
        """Store physical register into operand's spill slot.

        If skip_if_last is True and op is a Temp whose last use is the very
        next instruction, skip the store — the value will be forwarded from
        the scratch register instead.
        """
        if isinstance(op, (Temp, Var)):
            if isinstance(op, Temp):
                preg = self._regmap.reg(op.id) if self._regmap else None
                if preg is not None:
                    # Temp lives in a physical register — emit mov if needed
                    if reg != preg:
                        self._ins(f'mov {preg}, {reg}')
                    # invalidate scratch tracking for the destination
                    if reg == SCRATCH_A:
                        self._scratch_a_temp = None
                    elif reg == SCRATCH_C:
                        self._scratch_c_temp = None
                    return
            if skip_if_last and isinstance(op, Temp):
                last = self._ctx._last_use.get(op.id, -1)
                if last == self._cur_instr_idx + 1:
                    # don't spill; track as live in scratch
                    if reg == SCRATCH_A:
                        self._scratch_a_temp = op
                    elif reg == SCRATCH_C:
                        self._scratch_c_temp = op
                    return
            slot = self._spill_slot(op)
            self._ins(f'st {reg}, {SP}, {slot}')
            # track what's in scratch registers after store
            if reg == SCRATCH_A:
                self._scratch_a_temp = op if isinstance(op, Temp) else None
            elif reg == SCRATCH_C:
                self._scratch_c_temp = op if isinstance(op, Temp) else None
        else:
            raise CodegenError(f"Cannot store into {op}")

    def _dst_reg(self, op: Operand) -> str:
        """Return the physical register to compute a result into.

        If op is a Temp with an allocated register, return that register so
        the computation lands there directly (no mov needed after).
        Otherwise return SCRATCH_A.
        """
        if isinstance(op, Temp) and self._regmap:
            preg = self._regmap.reg(op.id)
            if preg is not None:
                return preg
        return SCRATCH_A

    def _src_reg(self, op: Operand, scratch: str) -> str:
        """Return the register that holds op's value, loading into scratch if needed.

        If op is a Temp with an allocated register, return that register directly
        (no load emitted).  Otherwise load into scratch and return scratch.
        Avoids a mov when the value is already in a physical register.
        """
        if isinstance(op, Temp) and self._regmap:
            preg = self._regmap.reg(op.id)
            if preg is not None:
                return preg
        self._load_op(op, scratch)
        return scratch

    def _mangle_global(self, name: str) -> str:
        """User-defined names get _C_ prefix; __ runtime helpers are emitted as-is."""
        if name.startswith('__'):
            return name
        return f'_C_{name}'

    def _load_addr(self, op: Operand, reg: str):
        """Load the *address* of an operand into a register."""
        if isinstance(op, Global):
            self._ins(f'mov {reg}, {self._mangle_global(op.name)}')
        elif isinstance(op, (Temp, Var)):
            slot = self._spill_slot(op)
            if slot == 0:
                self._ins(f'mov {reg}, {SP}')
            else:
                self._ins(f'add {reg}, {SP}, {slot}')
        else:
            raise CodegenError(f"Cannot take address of {op}")

    # ── Top-Level ─────────────────────────────────────────────────────────────

    def generate(self, prog: IRProgram) -> str:
        self._emit('; Generated by C->R316 compiler')
        self._emit('%include "common"')
        self._emit('%include "runtime/runtime.asm"')
        self._emit('')

        for fn in prog.functions:
            self._gen_func(fn)

        if prog.globals:
            self._emit('; -- global variables --')
            for name, words, init_vals in prog.globals:
                if init_vals:
                    vals = [str(v) for v in init_vals] + ['0'] * (words - len(init_vals))
                else:
                    vals = ['0'] * words
                self._emit(f'{self._mangle_global(name)}: dw {", ".join(vals)}')

        if prog.strings:
            self._emit('')
            self._emit('; -- string literals --')
            for lbl, chars in prog.strings:
                data = (', '.join(str(c) for c in chars) + ', 0') if chars else '0'
                self._emit(f'{lbl}: dw {data}')

        return '\n'.join(self._out)

    # ── Function ──────────────────────────────────────────────────────────────

    def _peephole(self, instrs: list) -> list:
        """
        Collapse ICopy(t, Var) immediately followed by ILoad(t2, t) — where t
        is not used anywhere else — into ILoad(t2, Var).  This eliminates the
        store-then-reload round-trip that otherwise occurs for every pointer
        dereference of a local/param variable.
        """
        # count uses of each Temp across the whole instruction list
        use_count: Dict[int, int] = {}
        for instr in instrs:
            for op in instr.uses():
                if isinstance(op, Temp):
                    use_count[op.id] = use_count.get(op.id, 0) + 1

        result = []
        skip = set()
        for i, instr in enumerate(instrs):
            if i in skip:
                continue
            # look for ICopy(t, Var/ImmInt/StrLabel) followed by ILoad(t2, t)
            if (isinstance(instr, ICopy)
                    and isinstance(instr.dst, Temp)
                    and isinstance(instr.src, (Var, ImmInt, StrLabel, Global))
                    and use_count.get(instr.dst.id, 0) == 1
                    and i + 1 < len(instrs)):
                nxt = instrs[i + 1]
                if isinstance(nxt, ILoad) and nxt.addr == instr.dst:
                    result.append(ILoad(nxt.dst, instr.src, nxt.loc))
                    skip.add(i + 1)
                    continue
            result.append(instr)
        return result

    def _gen_func(self, fn: IRFunction):
        fn = IRFunction(fn.name, fn.params, self._peephole(fn.instrs), fn.local_sizes,
                        is_variadic=fn.is_variadic)
        self._scratch_a_temp = None
        self._scratch_c_temp = None
        self._cur_instr_idx = 0
        self._regmap = allocate(fn)

        # Pre-scan: how many outgoing stack-argument words does this function need?
        # Reserve that many slots at [sp+0..sp+OA-1] so calls can write args there.
        outgoing_slots = self._max_outgoing_stack_slots(fn)

        # dry run to compute true peak frame size with recycling
        dry = FuncContext(fn.instrs, fn.params, fn.local_sizes, outgoing_slots)
        for i, instr in enumerate(fn.instrs):
            for op in instr.uses():
                if isinstance(op, Var):
                    dry.slot(op)
            d = instr.defs()
            if d is not None:
                dry.slot(d)
            dry.free_dead_temps(i)
        peak = dry.frame_size

        self._ctx = FuncContext(fn.instrs, fn.params, fn.local_sizes, outgoing_slots)

        # pre-scan: ensure all Var operands get permanent slots
        for instr in fn.instrs:
            for op in instr.uses():
                if isinstance(op, Var):
                    self._ctx.slot(op)

        self._is_leaf = not any(isinstance(i, ICall) for i in fn.instrs)

        # Determine which callee-saved registers this function uses.
        # For now, with the spill-only allocator, we don't allocate callee-saved
        # registers to temporaries.  When a register allocator is added, this
        # scan will detect which callee-saved regs are assigned.
        self._callee_saves = self._detect_callee_saves(fn)
        self._callee_save_n = len(self._callee_saves)

        # Stack frame layout (per docs/ABI.md §4 + §2.3):
        #   [sp+0 .. sp+OA-1]          : outgoing stack-arg area (OA words, caller view)
        #   [sp+OA .. sp+F-1]          : local variables / spill slots
        #   [sp+F .. sp+F+VS-1]        : arg-reg spill area (variadic only, 6 words)
        #   [sp+F+VS .. sp+F+VS+CS-1]  : saved callee-saved registers
        #   [sp+F+VS+CS]               : saved LR (non-leaf only)
        # peak already includes OA (FuncContext starts allocating at outgoing_slots).
        VA_SPILL_N = 6
        VS = VA_SPILL_N if fn.is_variadic else 0
        self._va_spill_n = VS
        F = peak
        CS = self._callee_save_n
        total = F + VS + CS + (1 if not self._is_leaf else 0)
        self._frame_size = total
        self._va_spill_base = F   # arg-reg spill area starts right after local slots
        lr_slot = F + VS + CS    # LR is saved after callee-saved area

        # Record va_spill_base on the IRFunction so IVaStart can use it
        fn.va_spill_base = self._va_spill_base

        func_start = len(self._out)
        self._emit(f'; function {fn.name}')
        self._lbl(self._mangle_global(fn.name))

        # Prologue: allocate stack frame
        if total > 0:
            self._ins(f'sub {SP}, {total}')

        # Save link register (non-leaf only) — §5.2 step 2
        if not self._is_leaf:
            self._ins(f'st {LR}, {SP}, {lr_slot}')

        # Save callee-saved registers — §5.2 step 3
        for i, reg in enumerate(self._callee_saves):
            self._ins(f'st {reg}, {SP}, {F + VS + i}')

        # Variadic: spill all 6 argument registers to the dedicated spill area — §10
        if fn.is_variadic:
            for i, reg in enumerate(ARG_REGS):
                self._ins(f'st {reg}, {SP}, {F + i}')

        # Copy arguments to their named spill slots — §5.2 step 4
        # Params 0..5: from argument registers a0-a5.
        # Params 6+:   from stack arg area above the callee's frame (§4.3).
        stack_arg_base = F + VS + CS + (0 if self._is_leaf else 1)
        for i, pname in enumerate(fn.params):
            slot = self._ctx.slot(Var(pname))
            if i < len(ARG_REGS):
                self._ins(f'st {ARG_REGS[i]}, {SP}, {slot}')
            else:
                overflow_idx = i - len(ARG_REGS)
                self._ins(f'ld {SCRATCH_A}, {SP}, {stack_arg_base + overflow_idx}')
                self._ins(f'st {SCRATCH_A}, {SP}, {slot}')

        # Pre-scan: find compare instructions whose result is used only in
        # the immediately following JumpIf/JumpIfNot — these can be fused
        # into a single conditional branch without materializing 0/1.
        self._fused_cmp = self._find_fused_cmps(fn.instrs)
        # Set of branch instruction indices suppressed because their compare was fused
        self._fused_branch_idxs = {v[0] for v in self._fused_cmp.values()}

        # Generate instructions
        for idx, instr in enumerate(fn.instrs):
            self._cur_instr_idx = idx
            self._gen_instr(instr, lr_slot, total)
            self._ctx.free_dead_temps(idx)

        self._asm_peephole(func_start)
        self._emit('')

    def _asm_peephole(self, func_start: int):
        """Post-process emitted assembly lines for a function.

        Pass 1 — st→ld forwarding:
          Eliminates st Rx, r30, N followed by ld Ry, r30, N (possibly with
          transparent intervening instructions), replacing the ld with mov Ry, Rx.

        Pass 2 — ld→ld forwarding (redundant reload):
          If a slot is loaded into Rx and the same slot is loaded again before
          Rx or the slot is clobbered, replace the second ld with mov Ry, Rx.

        Pass 3 — mov chain collapsing:
          mov rA, rX; mov rB, rA  →  mov rB, rX  (drop first if rA unused after)
          Only when rA is a pure scratch register (r7–r18): those are caller-saved
          temporaries with no ABI significance between instructions.
          Also drops mov rX, rX (self-move) unconditionally.

        Transparent instructions for passes 1 & 2: source comments, stores to
        other offsets, and instructions that don't write the tracked register.
        Stops at: labels, branches, store/write to the tracked register or slot.
        """
        import re
        lines = self._out
        n = len(lines)
        drop = set()
        patch: dict = {}  # index → replacement string

        st_pat  = re.compile(r'^(\s*)st (\w+), (r30), (\d+)$')
        ld_pat  = re.compile(r'^(\s*)ld (\w+), (r30), (\d+)$')
        mov_pat = re.compile(r'^(\s*)mov (r\d+), (r\d+)$')
        # Patterns that write a destination register (all ALU/memory ops with a dst)
        dst_pat = re.compile(r'^\s*(?:ld|mov|add|sub|mul|mulh|and|or|xor|adc|sbb|shl|shr|not)\s+(\w+)')
        label   = re.compile(r'^\s*\.\w+:')
        branch  = re.compile(r'^\s*j')

        # Pure scratch registers: caller-saved, not arg/return, not special.
        # Safe to use as collapsible intermediates in mov chains.
        SCRATCH_REGS = {f'r{i}' for i in range(7, 19)}

        # Pass 1: st Rx, r30, N  →  forward to subsequent ld _, r30, N
        for i in range(func_start, n):
            if i in drop or i in patch:
                continue
            ms = st_pat.match(lines[i])
            if not ms:
                continue
            indent, st_src, offset = ms.group(1), ms.group(2), ms.group(4)

            j = i + 1
            while j < n:
                ln = lines[j]
                stripped = ln.lstrip()
                if stripped.startswith('; '):
                    j += 1
                    continue
                if label.match(ln) or branch.match(ln):
                    break
                ms2 = st_pat.match(ln)
                if ms2 and ms2.group(4) == offset:
                    break
                dm = dst_pat.match(ln)
                if dm and dm.group(1) == st_src:
                    break
                ml = ld_pat.match(ln)
                if ml and ml.group(4) == offset:
                    ld_dst = ml.group(2)
                    if ld_dst == st_src:
                        drop.add(j)
                    else:
                        patch[j] = f'{indent}mov {ld_dst}, {st_src}'
                    break
                j += 1

        # Pass 2: ld Rx, r30, N  →  forward to subsequent ld _, r30, N
        for i in range(func_start, n):
            if i in drop or i in patch:
                continue
            ml = ld_pat.match(lines[i])
            if not ml:
                continue
            indent, ld_src, offset = ml.group(1), ml.group(2), ml.group(4)

            j = i + 1
            while j < n:
                ln = lines[j]
                stripped = ln.lstrip()
                if stripped.startswith('; '):
                    j += 1
                    continue
                if label.match(ln) or branch.match(ln):
                    break
                # Store to the same slot clobbers it
                ms2 = st_pat.match(ln)
                if ms2 and ms2.group(4) == offset:
                    break
                # Any write to ld_src invalidates the cached value
                dm = dst_pat.match(ln)
                if dm and dm.group(1) == ld_src:
                    break
                ml2 = ld_pat.match(ln)
                if ml2 and ml2.group(4) == offset:
                    ld_dst = ml2.group(2)
                    if ld_dst == ld_src:
                        drop.add(j)
                    else:
                        patch[j] = f'{indent}mov {ld_dst}, {ld_src}'
                    break
                j += 1

        # Apply passes 1 & 2 before pass 3 so mov chains are visible
        _before = len(lines)
        for i in sorted(drop | set(patch.keys()), reverse=True):
            if i in drop:
                lines.pop(i)
            elif i in patch:
                lines[i] = patch[i]
        self._peephole_eliminated += _before - len(lines)
        drop.clear()
        patch.clear()
        n = len(lines)

        # Pass 3: mov chain collapsing (only scratch intermediates, r7–r18)
        # Also eliminates mov rX, rX.
        # Repeat until stable (handles 3+ hop chains).
        changed = True
        while changed:
            changed = False
            n = len(lines)
            for i in range(func_start, n - 1):
                if i in drop:
                    continue
                # Drop self-moves unconditionally
                ms = mov_pat.match(lines[i])
                if ms and ms.group(2) == ms.group(3):
                    drop.add(i)
                    changed = True
                    continue
                # Collapse: mov rA, rX; mov rB, rA  →  mov rB, rX  (drop first)
                # Only when rA is a pure scratch register
                ms1 = mov_pat.match(lines[i])
                if not ms1:
                    continue
                rA, rX = ms1.group(2), ms1.group(3)
                if rA not in SCRATCH_REGS:
                    continue
                j = i + 1
                # Skip source annotation comments
                while j < n and lines[j].lstrip().startswith('; '):
                    j += 1
                if j >= n:
                    continue
                ms2 = mov_pat.match(lines[j])
                if not ms2 or ms2.group(3) != rA:
                    continue
                rB = ms2.group(2)
                # Verify rA is not used again after line j within this function
                # (scan forward until end, label, branch, or write to rA)
                rA_used_after = False
                for k in range(j + 1, n):
                    lk = lines[k].strip()
                    if not lk or lk.startswith('; '):
                        continue
                    if label.match(lines[k]) or branch.match(lines[k]):
                        break
                    # Write to rA ends its live range (check before use check)
                    dm = dst_pat.match(lines[k])
                    if dm and dm.group(1) == rA:
                        break
                    # Any use of rA as a source operand
                    if re.search(rf'\b{rA}\b', lk):
                        rA_used_after = True
                        break
                if rA_used_after:
                    continue
                indent = ms1.group(1)
                patch[j] = f'{indent}mov {rB}, {rX}'
                drop.add(i)
                changed = True

            _before = len(lines)
            for idx in sorted(drop | set(patch.keys()), reverse=True):
                if idx in drop:
                    lines.pop(idx)
                elif idx in patch:
                    lines[idx] = patch[idx]
            self._peephole_eliminated += _before - len(lines)
            drop.clear()
            patch.clear()

    def _max_outgoing_stack_slots(self, fn: IRFunction) -> int:
        """Count the max overflow stack arg words needed across all calls."""
        max_slots = 0
        for instr in fn.instrs:
            if isinstance(instr, ICall):
                overflow = max(0, len(instr.args) - len(ARG_REGS))
                max_slots = max(max_slots, overflow)
        return max_slots

    def _detect_callee_saves(self, fn: IRFunction) -> List[str]:
        """Return the callee-saved registers assigned by the register allocator."""
        return list(self._regmap.callee_used) if self._regmap else []

    # ── Compare-branch fusion ─────────────────────────────────────────────────

    def _find_fused_cmps(self, instrs: list) -> dict:
        """Return mapping: cmp_instr_idx → (branch_instr_idx, jump_op, target).

        A compare IBinOp at index i can be fused with the branch at i+1 when:
          - The cmp result Temp is used only in that one branch (use_count == 1)
          - The next instruction is IJumpIf or IJumpIfNot
          - The branch condition is exactly the cmp result Temp
        """
        from .ir import IBinOp, IJumpIf, IJumpIfNot, Temp as IRTemp

        # count uses of each temp
        use_count: Dict[int, int] = {}
        for instr in instrs:
            for op in instr.uses():
                if isinstance(op, IRTemp):
                    use_count[op.id] = use_count.get(op.id, 0) + 1

        fused = {}
        for i, instr in enumerate(instrs):
            if not isinstance(instr, IBinOp) or instr.op not in self._CMP_JMP:
                continue
            if not isinstance(instr.dst, IRTemp):
                continue
            if use_count.get(instr.dst.id, 0) != 1:
                continue
            if i + 1 >= len(instrs):
                continue
            nxt = instrs[i + 1]
            if isinstance(nxt, IJumpIf) and nxt.cond == instr.dst:
                fused[i] = (i + 1, self._CMP_JMP[instr.op], nxt.target)
            elif isinstance(nxt, IJumpIfNot) and nxt.cond == instr.dst:
                # invert the jump condition
                inv = {'jz': 'jnz', 'jnz': 'jz', 'jl': 'jge', 'jge': 'jl',
                       'jg': 'jle', 'jle': 'jg'}
                fused[i] = (i + 1, inv[self._CMP_JMP[instr.op]], nxt.target)
        return fused

    # ── Instructions ──────────────────────────────────────────────────────────

    def _cond_reg(self, cond: Operand) -> str:
        """Return a register holding the condition value, loading if necessary."""
        if isinstance(cond, Temp) and self._regmap:
            preg = self._regmap.reg(cond.id)
            if preg is not None:
                return preg
        self._load_op(cond, SCRATCH_A)
        return SCRATCH_A

    def _gen_instr(self, instr: Instr, lr_slot: int, frame_size: int):
        self._emit_src_comment(instr)

        if isinstance(instr, ILabel):
            self._invalidate_scratch()
            self._lbl(instr.name)

        elif isinstance(instr, IConst):
            dst = self._dst_reg(instr.dst)
            self._scratch_a_temp = None
            self._ins(f'mov {dst}, {instr.value & 0xFFFF}')
            if dst == SCRATCH_A:
                self._store_op(SCRATCH_A, instr.dst)

        elif isinstance(instr, ICopy):
            dst = self._dst_reg(instr.dst)
            self._load_op(instr.src, dst)
            if dst == SCRATCH_A:
                self._store_op(SCRATCH_A, instr.dst)

        elif isinstance(instr, IAddrOf):
            dst = self._dst_reg(instr.dst)
            self._scratch_a_temp = None
            self._load_addr(instr.var, dst)
            if dst == SCRATCH_A:
                self._store_op(SCRATCH_A, instr.dst)

        elif isinstance(instr, ILoad):
            dst  = self._dst_reg(instr.dst)
            areg = self._src_reg(instr.addr, SCRATCH_C)
            self._scratch_a_temp = None
            self._ins(f'ld {dst}, {areg}')
            if dst == SCRATCH_A:
                self._store_op(SCRATCH_A, instr.dst)

        elif isinstance(instr, IStore):
            if isinstance(instr.addr, Var):
                # scalar local/param: direct spill-slot store
                slot = self._spill_slot(instr.addr)
                self._load_op(instr.src, SCRATCH_A)
                self._ins(f'st {SCRATCH_A}, {SP}, {slot}')
                # update scratch_a tracking: value is the src temp
                if isinstance(instr.src, Temp):
                    self._scratch_a_temp = instr.src
            else:
                areg = self._src_reg(instr.addr, SCRATCH_C)
                sreg = self._src_reg(instr.src,  SCRATCH_A)
                self._ins(f'st {sreg}, {areg}')

        elif isinstance(instr, IBinOp):
            fused = self._fused_cmp.get(self._cur_instr_idx)
            if fused:
                # Emit compare + direct branch; skip materializing 0/1
                _, jmp_op, target = fused
                lreg = self._src_reg(instr.left,  SCRATCH_A)
                rreg = self._src_reg(instr.right, SCRATCH_B)
                self._ins(f'sub r0, {lreg}, {rreg}')
                self._invalidate_scratch()
                self._ins(f'{jmp_op} {target}')
            else:
                self._gen_binop(instr)

        elif isinstance(instr, IUnaryOp):
            self._gen_unaryop(instr)

        elif isinstance(instr, ICall):
            self._gen_call(instr)
            self._invalidate_scratch()

        elif isinstance(instr, IRet):
            if instr.src is not None:
                lreg = self._src_reg(instr.src, RET_REG)
                if lreg != RET_REG:
                    self._ins(f'mov {RET_REG}, {lreg}')
            self._gen_epilogue(lr_slot, frame_size)

        elif isinstance(instr, IJump):
            self._invalidate_scratch()
            self._ins(f'jmp {instr.target}')

        elif isinstance(instr, IJumpIf):
            if self._cur_instr_idx in self._fused_branch_idxs:
                pass  # emitted by the preceding fused IBinOp
            else:
                cr = self._cond_reg(instr.cond)
                self._ins(f'test {cr}, {cr}')
                self._invalidate_scratch()
                self._ins(f'jnz {instr.target}')

        elif isinstance(instr, IJumpIfNot):
            if self._cur_instr_idx in self._fused_branch_idxs:
                pass  # emitted by the preceding fused IBinOp
            else:
                cr = self._cond_reg(instr.cond)
                self._ins(f'test {cr}, {cr}')
                self._invalidate_scratch()
                self._ins(f'jz {instr.target}')

        elif isinstance(instr, IInlineAsm):
            self._invalidate_scratch()
            self._gen_inline_asm(instr)

        elif isinstance(instr, IVaStart):
            # Compute: dst = sp + va_spill_base + num_fixed
            offset = self._va_spill_base + instr.num_fixed
            dst = self._dst_reg(instr.dst)
            self._scratch_a_temp = None
            if offset == 0:
                self._ins(f'mov {dst}, {SP}')
            else:
                self._ins(f'add {dst}, {SP}, {offset}')
            if dst == SCRATCH_A:
                self._store_op(SCRATCH_A, instr.dst, skip_if_last=True)

        elif isinstance(instr, IVaArg):
            # Load ap pointer, dereference to get value
            dst = self._dst_reg(instr.dst)
            self._load_op(instr.ap, SCRATCH_C)
            self._scratch_a_temp = None
            self._ins(f'ld {dst}, {SCRATCH_C}')
            if dst == SCRATCH_A:
                self._store_op(SCRATCH_A, instr.dst)

        else:
            raise CodegenError(f"Unhandled IR instruction: {type(instr)}")

    # Caller-saved regs available as operand slots for inline asm (%0..%9)
    _ASM_REGS = ['r7', 'r8', 'r9', 'r10', 'r11', 'r12', 'r13', 'r14', 'r15', 'r16']

    def _gen_inline_asm(self, instr: IInlineAsm):
        if len(instr.srcs) > len(self._ASM_REGS):
            raise CodegenError(
                f"asm: too many input operands ({len(instr.srcs)}, max {len(self._ASM_REGS)})"
            )
        regs = []
        for i, src in enumerate(instr.srcs):
            reg = self._ASM_REGS[i]
            self._load_op(src, reg)
            regs.append(reg)
        # substitute %0..%N in each line of the template
        for line in instr.text.split('\n'):
            text = line.strip()
            if not text:
                continue
            for i, reg in enumerate(regs):
                text = text.replace(f'%{i}', reg)
            self._ins(text)

    def _gen_epilogue(self, lr_slot: int, frame_size: int):
        # Restore callee-saved registers
        F = self._frame_size - self._va_spill_n - self._callee_save_n - (1 if not self._is_leaf else 0)
        VS = self._va_spill_n
        for i, reg in enumerate(self._callee_saves):
            self._ins(f'ld {reg}, {SP}, {F + VS + i}')

        # Restore link register (non-leaf only)
        if not self._is_leaf:
            self._ins(f'ld {LR}, {SP}, {lr_slot}')

        # Deallocate stack frame
        if frame_size > 0:
            self._ins(f'add {SP}, {frame_size}')

        # Return
        self._ins(f'jmp {LR}')

    # ── BinOp instruction selection ───────────────────────────────────────────

    _CMP_JMP = {
        '==': 'jz',  '!=': 'jnz',
        '<':  'jl',  '>':  'jg',
        '<=': 'jle', '>=': 'jge',
    }

    def _gen_binop(self, instr: IBinOp):
        op  = instr.op
        dst = self._dst_reg(instr.dst)

        if op in self._CMP_JMP:
            self._gen_compare(instr, dst)
            return

        # Get source registers without unnecessary loads.
        # _src_reg returns the allocated reg if available, else loads into scratch.
        # We must pick scratches carefully to avoid src/dst aliasing.
        lreg = self._src_reg(instr.left,  SCRATCH_A)
        # For right, avoid using same scratch as left if left used SCRATCH_A
        rreg = self._src_reg(instr.right, SCRATCH_B)

        # Three-operand instructions: add/sub/mul dst, lreg, rreg
        # Safe as long as dst != rreg (would clobber right before reading it)
        # or dst == lreg (in-place update is fine).
        THREE_OP = {'+': 'add', '-': 'sub', '*': 'mul'}
        if op in THREE_OP and dst != rreg:
            if op == '*':
                self._ins(f'mul {dst}, {lreg}, {rreg}')
            else:
                self._ins(f'{THREE_OP[op]} {dst}, {lreg}, {rreg}')
        else:
            # Fall back: load left into SCRATCH_A if not already there, operate 2-op
            acc = lreg if lreg != rreg else SCRATCH_A
            if acc != lreg:
                self._ins(f'mov {acc}, {lreg}')
            if op == '+':
                self._ins(f'add {acc}, {rreg}')
            elif op == '-':
                self._ins(f'sub {acc}, {rreg}')
            elif op == '*':
                self._ins(f'mul {acc}, {acc}, {rreg}')
            elif op == '&':
                self._ins(f'and {acc}, {rreg}')
            elif op == '|':
                self._ins(f'or  {acc}, {rreg}')
            elif op == '^':
                self._ins(f'xor {acc}, {rreg}')
            elif op == '<<':
                self._ins(f'shl {acc}, {rreg}')
            elif op == '>>':
                self._ins(f'shr {acc}, {rreg}')
            else:
                raise CodegenError(f"Unknown binop: {op!r}")
            if dst != acc:
                self._ins(f'mov {dst}, {acc}')

        self._scratch_a_temp = None
        if dst == SCRATCH_A:
            self._store_op(SCRATCH_A, instr.dst)

    def _gen_compare(self, instr: IBinOp, dst: str):
        """Materialise comparison result as 0 or 1."""
        # Use the allocated register of the left operand directly if possible,
        # otherwise load into SCRATCH_A.
        left_reg = SCRATCH_A
        if isinstance(instr.left, Temp) and self._regmap:
            preg = self._regmap.reg(instr.left.id)
            if preg is not None and preg != SCRATCH_B and preg != dst:
                left_reg = preg
        if left_reg == SCRATCH_A:
            self._load_op(instr.left, SCRATCH_A)
        self._load_op(instr.right, SCRATCH_B)
        self._ins(f'sub r0, {left_reg}, {SCRATCH_B}')

        j        = self._CMP_JMP[instr.op]
        true_lbl = f'._cmp_t_{id(instr)}'
        end_lbl  = f'._cmp_e_{id(instr)}'

        self._ins(f'{j} {true_lbl}')
        self._ins(f'mov {dst}, 0')
        self._ins(f'jmp {end_lbl}')
        self._lbl(true_lbl)
        self._ins(f'mov {dst}, 1')
        self._lbl(end_lbl)
        self._scratch_a_temp = None
        if dst == SCRATCH_A:
            self._store_op(SCRATCH_A, instr.dst)

    # ── UnaryOp instruction selection ─────────────────────────────────────────

    def _gen_unaryop(self, instr: IUnaryOp):
        dst = self._dst_reg(instr.dst)
        self._load_op(instr.src, SCRATCH_A)
        op = instr.op

        if op == '-':
            # Avoid D=S aliasing in sub: copy to SCRATCH_B first so the
            # hardware reads the old value before the write.
            self._ins(f'mov {SCRATCH_B}, {SCRATCH_A}')
            self._ins(f'sub {SCRATCH_A}, r0, {SCRATCH_B}')
        elif op == '~':
            self._ins(f'xor {SCRATCH_A}, 0xFFFF')
        else:
            raise CodegenError(f"Unknown unary op: {op!r}")

        self._scratch_a_temp = None
        if dst != SCRATCH_A:
            self._ins(f'mov {dst}, {SCRATCH_A}')
        else:
            self._store_op(SCRATCH_A, instr.dst)

    # ── Call ──────────────────────────────────────────────────────────────────

    def _gen_call(self, instr: ICall):
        # Load first 6 arguments into a0-a5 (r1-r6)
        for i, arg in enumerate(instr.args):
            if i < len(ARG_REGS):
                self._load_op(arg, ARG_REGS[i])

        # Stack arguments for 7th+ params (§2.3 / §4.4):
        # The caller reserves [sp+0..sp+OA-1] for outgoing stack args (OA words
        # pre-allocated in its frame). Store overflow args there so they are at
        # [caller_sp + overflow_idx]; after the callee's `sub sp, callee_total`
        # they land at [callee_sp + callee_total + overflow_idx] as §4.3 requires.
        for i, arg in enumerate(instr.args):
            if i >= len(ARG_REGS):
                overflow_idx = i - len(ARG_REGS)
                self._load_op(arg, SCRATCH_A)
                self._ins(f'st {SCRATCH_A}, {SP}, {overflow_idx}')

        if isinstance(instr.func, Global):
            self._ins(f'jmp {LR}, {self._mangle_global(instr.func.name)}')
        else:
            # function pointer in a temp
            self._load_op(instr.func, SCRATCH_A)
            self._ins(f'jmp {LR}, {SCRATCH_A}')

        if instr.dst is not None:
            preg = self._regmap.reg(instr.dst.id) if self._regmap else None
            if preg is not None and preg != RET_REG:
                self._ins(f'mov {preg}, {RET_REG}')
            elif preg is None:
                self._store_op(RET_REG, instr.dst)
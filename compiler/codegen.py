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
    """

    def __init__(self, instrs: list, params: list[str], local_sizes: Dict[str, int] = None):
        self._slots:    Dict[str, int] = {}
        self._free:     list[int]      = []   # recycled slots available
        self._next      = 0
        self._peak      = 0

        # params first — permanent slots 0..len(params)-1
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
        # variadic support
        self._va_spill_base: int = 0   # frame offset where arg-reg spill starts
        self._va_spill_n:    int = 0   # number of arg-reg spill slots (0 or 6)

    # ── Source annotation (-g) ────────────────────────────────────────────────

    def set_source(self, src: str, src_name: str):
        """Enable source annotation for -g flag."""
        self._annotate = True
        self._src_lines = src.split('\n')
        self._src_name = src_name
        self._last_src_line = 0

    def _emit_src_comment(self, instr: Instr):
        """Emit a source line comment if annotation is enabled and line changed."""
        if not self._annotate or not instr.loc:
            return
        _, line = instr.loc
        if line != self._last_src_line and 1 <= line <= len(self._src_lines):
            src_text = self._src_lines[line - 1].strip()
            if src_text:
                self._emit(f'    ; {self._src_name}:{line}: {src_text}')
            self._last_src_line = line

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
            self._ins(f'ld {reg}, {op.name}')
        elif isinstance(op, (Temp, Var)):
            # if this temp is already in the target register, skip the load
            if isinstance(op, Temp):
                if self._scratch_a_temp == op:
                    if reg != SCRATCH_A:
                        self._ins(f'mov {reg}, {SCRATCH_A}')
                    return
                if self._scratch_c_temp == op:
                    if reg != SCRATCH_C:
                        self._ins(f'mov {reg}, {SCRATCH_C}')
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

    def _load_addr(self, op: Operand, reg: str):
        """Load the *address* of an operand into a register."""
        if isinstance(op, Global):
            self._ins(f'mov {reg}, {op.name}')
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
                self._emit(f'{name}: dw {", ".join(vals)}')

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
        # dry run to compute true peak frame size with recycling
        dry = FuncContext(fn.instrs, fn.params, fn.local_sizes)
        for i, instr in enumerate(fn.instrs):
            for op in instr.uses():
                if isinstance(op, Var):
                    dry.slot(op)
            d = instr.defs()
            if d is not None:
                dry.slot(d)
            dry.free_dead_temps(i)
        peak = dry.frame_size

        self._ctx = FuncContext(fn.instrs, fn.params, fn.local_sizes)

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

        # Stack frame layout (per docs/ABI.md §4):
        #   [sp+0 .. sp+F-1]           : local/spill slots (F = peak)
        #   [sp+F .. sp+F+5]           : arg-reg spill area (variadic only, 6 words)
        #   [sp+F+VS .. sp+F+VS+CS-1]  : saved callee-saved registers
        #   [sp+F+VS+CS]               : saved LR (non-leaf only)
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

        self._emit(f'; function {fn.name}')
        self._lbl(fn.name)

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

        # Copy register arguments to their named spill slots — §5.2 step 4
        # (for variadic functions the arg-reg spill above already captured them;
        # this loop still copies fixed params into named slots for normal use)
        for i, pname in enumerate(fn.params):
            if i < len(ARG_REGS):
                slot = self._ctx.slot(Var(pname))
                self._ins(f'st {ARG_REGS[i]}, {SP}, {slot}')

        # Generate instructions
        for idx, instr in enumerate(fn.instrs):
            self._cur_instr_idx = idx
            self._gen_instr(instr, lr_slot, total)
            self._ctx.free_dead_temps(idx)

        self._emit('')

    def _detect_callee_saves(self, fn: IRFunction) -> List[str]:
        """
        Detect which callee-saved registers are used by the function.
        
        With the current spill-only allocator, no callee-saved registers
        are allocated to temporaries, so this returns an empty list.
        When a register allocator is added, this should scan the function's
        register assignments and return the set of callee-saved regs used.
        """
        # TODO: implement when register allocator is added
        # For now, all values are spilled to stack slots, so no callee-saved
        # registers are used beyond their spill-slot storage.
        return []

    # ── Instructions ──────────────────────────────────────────────────────────

    def _gen_instr(self, instr: Instr, lr_slot: int, frame_size: int):
        self._emit_src_comment(instr)

        if isinstance(instr, ILabel):
            self._invalidate_scratch()
            self._lbl(instr.name)

        elif isinstance(instr, IConst):
            self._scratch_a_temp = None
            self._ins(f'mov {SCRATCH_A}, {instr.value & 0xFFFF}')
            self._store_op(SCRATCH_A, instr.dst)

        elif isinstance(instr, ICopy):
            self._load_op(instr.src, SCRATCH_A)
            self._store_op(SCRATCH_A, instr.dst)

        elif isinstance(instr, IAddrOf):
            self._scratch_a_temp = None
            self._load_addr(instr.var, SCRATCH_A)
            self._store_op(SCRATCH_A, instr.dst)

        elif isinstance(instr, ILoad):
            self._load_op(instr.addr, SCRATCH_C)
            self._scratch_a_temp = None
            self._ins(f'ld {SCRATCH_A}, {SCRATCH_C}')
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
                self._load_op(instr.addr, SCRATCH_C)
                self._load_op(instr.src,  SCRATCH_A)
                self._ins(f'st {SCRATCH_A}, {SCRATCH_C}')

        elif isinstance(instr, IBinOp):
            self._gen_binop(instr)

        elif isinstance(instr, IUnaryOp):
            self._gen_unaryop(instr)

        elif isinstance(instr, ICall):
            self._gen_call(instr)
            self._invalidate_scratch()

        elif isinstance(instr, IRet):
            if instr.src is not None:
                self._load_op(instr.src, RET_REG)
            self._gen_epilogue(lr_slot, frame_size)

        elif isinstance(instr, IJump):
            self._invalidate_scratch()
            self._ins(f'jmp {instr.target}')

        elif isinstance(instr, IJumpIf):
            self._load_op(instr.cond, SCRATCH_A)
            self._ins(f'test {SCRATCH_A}, {SCRATCH_A}')
            self._invalidate_scratch()
            self._ins(f'jnz {instr.target}')

        elif isinstance(instr, IJumpIfNot):
            self._load_op(instr.cond, SCRATCH_A)
            self._ins(f'test {SCRATCH_A}, {SCRATCH_A}')
            self._invalidate_scratch()
            self._ins(f'jz {instr.target}')

        elif isinstance(instr, IInlineAsm):
            self._invalidate_scratch()
            self._gen_inline_asm(instr)

        elif isinstance(instr, IVaStart):
            # Compute: dst = sp + va_spill_base + num_fixed
            offset = self._va_spill_base + instr.num_fixed
            self._scratch_a_temp = None
            if offset == 0:
                self._ins(f'mov {SCRATCH_A}, {SP}')
            else:
                self._ins(f'add {SCRATCH_A}, {SP}, {offset}')
            self._store_op(SCRATCH_A, instr.dst, skip_if_last=True)

        elif isinstance(instr, IVaArg):
            # Load ap pointer, dereference to get value
            self._load_op(instr.ap, SCRATCH_C)
            self._scratch_a_temp = None
            self._ins(f'ld {SCRATCH_A}, {SCRATCH_C}')
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
        op = instr.op

        if op in self._CMP_JMP:
            self._gen_compare(instr)
            return

        self._load_op(instr.left,  SCRATCH_A)
        self._load_op(instr.right, SCRATCH_B)

        if op == '+':
            self._ins(f'add {SCRATCH_A}, {SCRATCH_B}')
        elif op == '-':
            self._ins(f'sub {SCRATCH_A}, {SCRATCH_B}')
        elif op == '*':
            self._ins(f'mul {SCRATCH_A}, {SCRATCH_A}, {SCRATCH_B}')
        elif op == '&':
            self._ins(f'and {SCRATCH_A}, {SCRATCH_B}')
        elif op == '|':
            self._ins(f'or  {SCRATCH_A}, {SCRATCH_B}')
        elif op == '^':
            self._ins(f'xor {SCRATCH_A}, {SCRATCH_B}')
        elif op == '<<':
            self._ins(f'shl {SCRATCH_A}, {SCRATCH_B}')
        elif op == '>>':
            self._ins(f'shr {SCRATCH_A}, {SCRATCH_B}')
        else:
            raise CodegenError(f"Unknown binop: {op!r}")

        self._scratch_a_temp = None
        self._store_op(SCRATCH_A, instr.dst)

    def _gen_compare(self, instr: IBinOp):
        """Materialise comparison result as 0 or 1."""
        self._load_op(instr.left,  SCRATCH_A)
        self._load_op(instr.right, SCRATCH_B)
        self._ins(f'sub r0, {SCRATCH_A}, {SCRATCH_B}')

        j       = self._CMP_JMP[instr.op]
        true_lbl = f'._cmp_t_{id(instr)}'
        end_lbl  = f'._cmp_e_{id(instr)}'

        self._ins(f'{j} {true_lbl}')
        self._ins(f'mov {SCRATCH_A}, 0')
        self._ins(f'jmp {end_lbl}')
        self._lbl(true_lbl)
        self._ins(f'mov {SCRATCH_A}, 1')
        self._lbl(end_lbl)
        self._store_op(SCRATCH_A, instr.dst)

    # ── UnaryOp instruction selection ─────────────────────────────────────────

    def _gen_unaryop(self, instr: IUnaryOp):
        self._load_op(instr.src, SCRATCH_A)
        op = instr.op

        if op == '-':
            self._ins(f'sub {SCRATCH_A}, r0, {SCRATCH_A}')
        elif op == '~':
            self._ins(f'xor {SCRATCH_A}, 0xFFFF')
        else:
            raise CodegenError(f"Unknown unary op: {op!r}")

        self._scratch_a_temp = None
        self._store_op(SCRATCH_A, instr.dst)

    # ── Call ──────────────────────────────────────────────────────────────────

    def _gen_call(self, instr: ICall):
        # Load arguments into a0-a5 (r1-r6)
        for i, arg in enumerate(instr.args):
            if i < len(ARG_REGS):
                self._load_op(arg, ARG_REGS[i])

        # TODO: stack arguments for 7th+ params (see docs/ABI.md §2.3)
        # When a function has more than 6 arguments, the remaining ones
        # must be stored on the stack by the caller before the call.

        if isinstance(instr.func, Global):
            self._ins(f'jmp {LR}, {instr.func.name}')
        else:
            # function pointer in a temp
            self._load_op(instr.func, SCRATCH_A)
            self._ins(f'jmp {LR}, {SCRATCH_A}')

        if instr.dst is not None:
            self._store_op(RET_REG, instr.dst)
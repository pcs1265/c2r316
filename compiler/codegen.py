"""
C to R316 Compiler - Code Generator
IR → TPTASM R316 Assembly

ABI:
  r1..r4  : arguments / return values (r1=lo, r2=hi for long)
  r5..r13 : caller-saved temporaries
  r14..r29: callee-saved
  r30 (sp): stack pointer (grows downward)
  r31 (lr): link register

Stack frame layout (per function):
  [sp+0 .. sp+N-1] : spill slots for Temps and local Vars
  [sp+N]           : saved lr  (non-leaf functions only)

Register allocation:
  Each Temp/Var gets a fixed spill slot allocated linearly.
  Small number of physical regs used as scratch; values always
  loaded into scratch before use and stored back after def.

  scratch regs: r5 (left/dst), r6 (right), r7 (addr)
"""

from __future__ import annotations
import os
from typing import Dict, Optional

from .ir import (
    Temp, Var, Global, ImmInt, StrLabel, Operand,
    IConst, ICopy, IAddrOf, IBinOp, IUnaryOp, ILoad, IStore,
    ICall, IRet, ILabel, IJump, IJumpIf, IJumpIfNot,
    IInlineAsm, IRFunction, IRProgram, Instr,
)


class CodegenError(Exception):
    pass


# Physical register names
SP   = 'r30'
LR   = 'r31'
SCRATCH_A = 'r5'   # primary scratch / result
SCRATCH_B = 'r6'   # secondary scratch
SCRATCH_C = 'r7'   # address scratch
ARG_REGS  = ['r1', 'r2', 'r3', 'r4']
RET_REG   = 'r1'


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

    def _load_op(self, op: Operand, reg: str):
        """Load operand value into physical register."""
        if isinstance(op, ImmInt):
            self._ins(f'mov {reg}, {op.value & 0xFFFF}')
        elif isinstance(op, StrLabel):
            self._ins(f'mov {reg}, {op.name}')
        elif isinstance(op, Global):
            self._ins(f'ld {reg}, {op.name}')
        elif isinstance(op, (Temp, Var)):
            slot = self._spill_slot(op)
            self._ins(f'ld {reg}, {SP}, {slot}')
        else:
            raise CodegenError(f"Cannot load {op}")

    def _store_op(self, reg: str, op: Operand):
        """Store physical register into operand's spill slot."""
        if isinstance(op, (Temp, Var)):
            slot = self._spill_slot(op)
            self._ins(f'st {reg}, {SP}, {slot}')
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
        self._emit('')

        # entry point
        self._emit('; -- entry point --')
        self._lbl('start')
        self._ins(f'jmp {LR}, __stack_init')
        self._ins(f'jmp {LR}, __term_init')
        self._ins(f'jmp {LR}, main')
        self._ins('hlt')
        self._emit('')

        for fn in prog.functions:
            self._gen_func(fn)

        if prog.globals:
            self._emit('; -- global variables --')
            for name in prog.globals:
                self._emit(f'{name}: dw 0')

        if prog.strings:
            self._emit('')
            self._emit('; -- string literals --')
            for lbl, chars in prog.strings:
                data = (', '.join(str(c) for c in chars) + ', 0') if chars else '0'
                self._emit(f'{lbl}: dw {data}')

        return '\n'.join(self._out)

    # ── Function ──────────────────────────────────────────────────────────────

    def _gen_func(self, fn: IRFunction):
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
        frame_size    = peak + (0 if self._is_leaf else 1)
        lr_slot       = peak

        self._emit(f'; function {fn.name}')
        self._lbl(fn.name)

        if frame_size > 0:
            self._ins(f'sub {SP}, {frame_size}')

        if not self._is_leaf:
            self._ins(f'st {LR}, {SP}, {lr_slot}')

        for i, pname in enumerate(fn.params):
            if i < len(ARG_REGS):
                slot = self._ctx.slot(Var(pname))
                self._ins(f'st {ARG_REGS[i]}, {SP}, {slot}')

        for idx, instr in enumerate(fn.instrs):
            self._gen_instr(instr, lr_slot, frame_size)
            self._ctx.free_dead_temps(idx)

        self._emit('')

    # ── Instructions ──────────────────────────────────────────────────────────

    def _gen_instr(self, instr: Instr, lr_slot: int, frame_size: int):

        if isinstance(instr, ILabel):
            self._lbl(instr.name)

        elif isinstance(instr, IConst):
            self._ins(f'mov {SCRATCH_A}, {instr.value & 0xFFFF}')
            self._store_op(SCRATCH_A, instr.dst)

        elif isinstance(instr, ICopy):
            self._load_op(instr.src, SCRATCH_A)
            self._store_op(SCRATCH_A, instr.dst)

        elif isinstance(instr, IAddrOf):
            self._load_addr(instr.var, SCRATCH_A)
            self._store_op(SCRATCH_A, instr.dst)

        elif isinstance(instr, ILoad):
            self._load_op(instr.addr, SCRATCH_C)
            self._ins(f'ld {SCRATCH_A}, {SCRATCH_C}')
            self._store_op(SCRATCH_A, instr.dst)

        elif isinstance(instr, IStore):
            self._load_op(instr.addr, SCRATCH_C)
            self._load_op(instr.src,  SCRATCH_A)
            self._ins(f'st {SCRATCH_A}, {SCRATCH_C}')

        elif isinstance(instr, IBinOp):
            self._gen_binop(instr)

        elif isinstance(instr, IUnaryOp):
            self._gen_unaryop(instr)

        elif isinstance(instr, ICall):
            self._gen_call(instr)

        elif isinstance(instr, IRet):
            if instr.src is not None:
                self._load_op(instr.src, RET_REG)
            self._gen_epilogue(lr_slot, frame_size)

        elif isinstance(instr, IJump):
            self._ins(f'jmp {instr.target}')

        elif isinstance(instr, IJumpIf):
            self._load_op(instr.cond, SCRATCH_A)
            self._ins(f'test {SCRATCH_A}, {SCRATCH_A}')
            self._ins(f'jnz {instr.target}')

        elif isinstance(instr, IJumpIfNot):
            self._load_op(instr.cond, SCRATCH_A)
            self._ins(f'test {SCRATCH_A}, {SCRATCH_A}')
            self._ins(f'jz {instr.target}')

        elif isinstance(instr, IInlineAsm):
            self._gen_inline_asm(instr)

        else:
            raise CodegenError(f"Unhandled IR instruction: {type(instr)}")

    # Caller-saved regs available as operand slots for inline asm (%0..%8)
    _ASM_REGS = ['r5', 'r6', 'r7', 'r8', 'r9', 'r10', 'r11', 'r12', 'r13']

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
        if not self._is_leaf:
            self._ins(f'ld {LR}, {SP}, {lr_slot}')
        if frame_size > 0:
            self._ins(f'add {SP}, {frame_size}')
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
        elif op == '/':
            self._ins(f'mov r1, {SCRATCH_A}')
            self._ins(f'mov r2, {SCRATCH_B}')
            self._ins(f'jmp {LR}, __udiv')
            self._ins(f'mov {SCRATCH_A}, r1')
        elif op == '%':
            self._ins(f'mov r1, {SCRATCH_A}')
            self._ins(f'mov r2, {SCRATCH_B}')
            self._ins(f'jmp {LR}, __umod')
            self._ins(f'mov {SCRATCH_A}, r1')
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

        self._store_op(SCRATCH_A, instr.dst)

    # ── Call ──────────────────────────────────────────────────────────────────

    def _gen_call(self, instr: ICall):
        # move args into r1..r4
        for i, arg in enumerate(instr.args):
            if i < len(ARG_REGS):
                self._load_op(arg, ARG_REGS[i])

        if isinstance(instr.func, Global):
            self._ins(f'jmp {LR}, {instr.func.name}')
        else:
            # function pointer in a temp
            self._load_op(instr.func, SCRATCH_A)
            self._ins(f'jmp {LR}, {SCRATCH_A}')

        if instr.dst is not None:
            self._store_op(RET_REG, instr.dst)

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
    IInlineAsm, IRFunction, IRProgram, Instr,
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
        self._emit('%include "runtime/runtime.asm"')
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

        self._is_leaf = not any(
            isinstance(i, ICall) or
            (isinstance(i, IBinOp) and i.op in ('/', '%'))
            for i in fn.instrs
        )

        # Determine which callee-saved registers this function uses.
        # For now, with the spill-only allocator, we don't allocate callee-saved
        # registers to temporaries.  When a register allocator is added, this
        # scan will detect which callee-saved regs are assigned.
        self._callee_saves = self._detect_callee_saves(fn)
        self._callee_save_n = len(self._callee_saves)

        # Stack frame layout (per docs/ABI.md §4):
        #   [sp+0 .. sp+F-1]           : local/spill slots (F = peak)
        #   [sp+F .. sp+F+CS-1]        : saved callee-saved registers
        #   [sp+F+CS]                  : saved LR (non-leaf only)
        F = peak
        CS = self._callee_save_n
        total = F + CS + (1 if not self._is_leaf else 0)
        self._frame_size = total
        lr_slot = F + CS  # LR is saved right after callee-saved area

        self._emit(f'; function {fn.name}')
        self._lbl(fn.name)

        # Prologue: allocate stack frame
        if total > 0:
            self._ins(f'sub {SP}, {total}')

        # Save callee-saved registers
        for i, reg in enumerate(self._callee_saves):
            self._ins(f'st {reg}, {SP}, {F + i}')

        # Save link register (non-leaf only)
        if not self._is_leaf:
            self._ins(f'st {LR}, {SP}, {lr_slot}')

        # Copy register arguments to their spill slots
        for i, pname in enumerate(fn.params):
            if i < len(ARG_REGS):
                slot = self._ctx.slot(Var(pname))
                self._ins(f'st {ARG_REGS[i]}, {SP}, {slot}')

        # Generate instructions
        for idx, instr in enumerate(fn.instrs):
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
        F = self._frame_size - self._callee_save_n - (1 if not self._is_leaf else 0)
        for i, reg in enumerate(self._callee_saves):
            self._ins(f'ld {reg}, {SP}, {F + i}')

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
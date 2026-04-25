"""Minimal R316 emulator for compiler test harness.

Goal: parse the compiler's output.asm and execute it well enough to verify
program behavior — catches codegen bugs (like the left-operand-clobber)
that pure pattern-matching tests miss.

Scope:
  - Instructions actually emitted by the c2r316 compiler:
      mov add adc sub sbb mul and or xor shl shr ld st jmp <jcc> hlt
  - Macros: cmp / test / nop (hardcoded; we skip %include "common")
  - Skipped: %include, %define, %eval, %ifndef, %endif, %macro definitions,
    {RPN expressions}, and most of runtime/runtime.asm. Execution starts at
    `_C_main:` directly, with SP and LR initialized by the harness.
  - Terminal: writes to 0x9FB5 are captured into stdout. Nothing else MMIO.

This is a small-cycle reference, not the full TPT R316 ISA.
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Optional


# ── flags / register helpers ───────────────────────────────────────────────

_MASK16 = 0xFFFF
_BIT15  = 0x8000

def _u16(x: int) -> int: return x & _MASK16
def _s16(x: int) -> int:
    x &= _MASK16
    return x - 0x10000 if x & _BIT15 else x


@dataclass
class Flags:
    Z: int = 0   # zero
    S: int = 0   # sign
    C: int = 0   # carry / borrow inverted (per R316: see manual.md)
    O: int = 0   # signed overflow

    def from_logic(self, result: int) -> None:
        """Update Z/S only; C/O unspecified."""
        r = _u16(result)
        self.Z = int(r == 0)
        self.S = int(bool(r & _BIT15))

    def from_add(self, a: int, b: int, cin: int = 0) -> int:
        """Add a + b + cin, set all four flags, return 16-bit result."""
        a &= _MASK16; b &= _MASK16
        full = a + b + cin
        result = full & _MASK16
        self.Z = int(result == 0)
        self.S = int(bool(result & _BIT15))
        self.C = int(full > _MASK16)
        # Signed overflow: same-sign inputs, different-sign result
        sa = a & _BIT15; sb = b & _BIT15; sr = result & _BIT15
        self.O = int((sa == sb) and (sa != sr))
        return result

    def from_sub(self, p: int, s: int, bin_: int = 0) -> int:
        """Compute p - s - bin_. R316 sub semantics: sub D, P, S → D = P - S,
        and the borrow flag is the inverse of carry-out from `add P, ~S, 1`.
        We model it as "carry = there was a borrow"."""
        p &= _MASK16; s &= _MASK16
        full = p - s - bin_
        result = full & _MASK16
        self.Z = int(result == 0)
        self.S = int(bool(result & _BIT15))
        self.C = int(full < 0)   # borrow occurred
        # Signed overflow on subtract: P and S differ in sign, and result sign != P sign
        sp = p & _BIT15; ss = s & _BIT15; sr = result & _BIT15
        self.O = int((sp != ss) and (sp != sr))
        return result


# ── parser ─────────────────────────────────────────────────────────────────

# Strip line comments (after `;`) but preserve string contents in directives.
_COMMENT_RE = re.compile(r';.*$')

# Parse an integer literal: 0xNN, decimal, or character literal 'x'
def _parse_imm(tok: str, sym: dict) -> int:
    tok = tok.strip()
    if not tok:
        raise ValueError("empty immediate")
    if tok.startswith("'") and tok.endswith("'") and len(tok) >= 3:
        # char literal — handle simple escapes
        s = tok[1:-1]
        if s.startswith('\\'):
            esc = {'n': 10, 't': 9, 'r': 13, '0': 0, '\\': 92, "'": 39, '"': 34}
            return esc.get(s[1], ord(s[1]))
        return ord(s)
    if tok.lower().startswith('0x'):
        return int(tok, 16) & 0xFFFFFFFF
    if tok.lstrip('-').isdigit():
        return int(tok) & 0xFFFFFFFF
    if tok in sym:
        return sym[tok] & 0xFFFFFFFF
    raise ValueError(f"unknown immediate: {tok!r}")


def _is_reg(tok: str) -> bool:
    return bool(re.match(r'^r(?:[0-9]|[12][0-9]|3[01])$', tok))


def _reg_idx(tok: str) -> int:
    return int(tok[1:])


def _strip_comment(line: str) -> str:
    out = []
    in_str = False
    for ch in line:
        if ch == '"':
            in_str = not in_str
            out.append(ch)
        elif ch == ';' and not in_str:
            break
        else:
            out.append(ch)
    return ''.join(out).rstrip()


@dataclass
class Insn:
    op: str
    args: list[str]
    src_line: int = 0
    scope: str = ''   # name of containing global label (for local-label resolution)

    def __repr__(self): return f'{self.op} {", ".join(self.args)}'


@dataclass
class Program:
    insns: list[Insn]
    labels: dict[str, int]   # label name → instruction index
    data: dict[int, int]     # word address → value (for `dw` data)
    data_origin: int = 0


# Macros we hardcode: TPTASM common.asm defines these.
_MACROS = {
    'cmp':  ('sub', ['r0']),
    'test': ('and', ['r0']),
    'nop':  ('mov', ['r0', 'r0']),
}

# Jump aliases from common.asm
_JMP_ALIASES = {
    'ja': 'jnbe', 'jna': 'jbe',
    'jae': 'jnc', 'jnae': 'jc',
    'je': 'jz', 'jne': 'jnz',
    'jg': 'jnle', 'jng': 'jle',
    'jge': 'jnl', 'jnge': 'jl',
    'jb': 'jc', 'jnb': 'jnc',
}


def parse_asm(text: str) -> Program:
    """Parse compiler output. Skips %include, %define, etc.

    The parser splits on commas/whitespace and keeps the asm structure flat:
    one Insn per source line. Labels (anything ending with ':') are recorded.
    `dw` directives are placed at the END as data words, with addresses
    assigned starting from a fixed origin so global symbols can be loaded.
    """
    insns: list[Insn] = []
    labels: dict[str, int] = {}
    data: dict[int, int] = {}
    pending_label_for_data: list[str] = []
    cur_global = ''
    in_macro_def = False
    if_stack: list[bool] = []   # %ifndef block — emit only if top-of-stack True

    # We assign data labels addresses starting from 0xC000 (arbitrary, safe
    # high address that doesn't collide with code or MMIO at 0x9F80).
    # Code labels resolve to instruction indices; data labels to addresses.
    next_data_addr = 0xC000

    for lineno, raw in enumerate(text.splitlines(), 1):
        line = _strip_comment(raw).strip()
        if not line:
            continue

        # %macro definition block — skip until %endmacro
        if in_macro_def:
            if line.startswith('%endmacro'):
                in_macro_def = False
            continue
        if line.startswith('%macro'):
            in_macro_def = True
            continue

        # Conditional blocks (very limited %ifndef / %endif / %else)
        if line.startswith('%ifndef'):
            if_stack.append(True)   # always assume "not defined" — emit content
            continue
        if line.startswith('%ifdef'):
            if_stack.append(False)  # never emit (we don't track defs)
            continue
        if line.startswith('%endif'):
            if if_stack: if_stack.pop()
            continue
        if line.startswith('%else'):
            if if_stack: if_stack[-1] = not if_stack[-1]
            continue
        if if_stack and not if_stack[-1]:
            continue

        # Directives we ignore but don't fail on
        if line.startswith('%'):
            continue

        # Label?  `name:` or `name: instr ...`
        # Handle this FIRST so a label on the same line as `dw ...` is parsed.
        m = re.match(r'^(\.?[A-Za-z_][A-Za-z0-9_]*)\s*:(.*)$', line)
        if m:
            lbl = m.group(1)
            rest = m.group(2).strip()
            if not lbl.startswith('.'):
                cur_global = lbl
            full = lbl if not lbl.startswith('.') else cur_global + lbl
            pending_label_for_data.append(full)
            if not rest:
                continue
            line = rest

        # `dw value, value, value` → emit data words at next_data_addr
        m = re.match(r'^dw\s+(.*)$', line)
        if m:
            values = [v.strip() for v in m.group(1).split(',')]
            for lbl in pending_label_for_data:
                labels[lbl] = next_data_addr   # data address (>= 0xC000)
            pending_label_for_data = []
            for v in values:
                data[next_data_addr] = v   # store raw token; resolved later
                next_data_addr += 1
            continue

        # Now parse as instruction. Args separated by commas, mnemonic by ws.
        # Allow leading dot for instructions that have a leading-dot label
        # already stripped (we already handle labels above, so this regex only
        # matches actual instruction mnemonics — which never start with '.').
        m = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)(?:\s+(.*))?$', line)
        if not m:
            continue   # skip unrecognized lines
        op = m.group(1)
        args_str = m.group(2) or ''
        args = [a.strip() for a in args_str.split(',')] if args_str else []
        # filter empty
        args = [a for a in args if a]

        # Apply macros and aliases
        if op in _MACROS:
            new_op, prefix = _MACROS[op]
            op = new_op
            args = list(prefix) + args
        if op in _JMP_ALIASES:
            op = _JMP_ALIASES[op]

        # Resolve any labels we registered as pointing here
        for lbl in pending_label_for_data:
            labels[lbl] = len(insns)
        pending_label_for_data = []

        insns.append(Insn(op=op, args=args, src_line=lineno, scope=cur_global))

    # Resolve data values that referenced symbols (e.g. `dw _cstr_0`)
    resolved_data: dict[int, int] = {}
    for addr, v in data.items():
        if isinstance(v, int):
            resolved_data[addr] = v
        else:
            resolved_data[addr] = _resolve_symbol(v, labels)
    return Program(insns=insns, labels=labels, data=resolved_data, data_origin=0xC000)


def _resolve_symbol(tok: str, labels: dict) -> int:
    tok = tok.strip()
    try:
        if tok.startswith("'"):
            return _parse_imm(tok, labels) & _MASK16
        if tok.lower().startswith('0x'):
            return int(tok, 16) & _MASK16
        return int(tok) & _MASK16
    except ValueError:
        pass
    if tok in labels:
        return labels[tok] & 0xFFFF
    raise ValueError(f"can't resolve symbol: {tok!r}")


# ── machine ────────────────────────────────────────────────────────────────

class Machine:
    """A small R316 CPU.  Registers are 32-bit but ALU only sees 16 LSBs."""

    SENTINEL_LR = 0xDEAD   # invalid PC: when jmp r31 lands here, we halt

    def __init__(self, prog: Program, sp_init: int = 0x8000, max_cycles: int = 1_000_000):
        self.prog = prog
        self.regs = [0] * 32
        self.regs[30] = sp_init        # sp
        self.regs[31] = self.SENTINEL_LR
        self.flags = Flags()
        self.mem: dict[int, int] = dict(prog.data)
        self.pc: int = 0
        self.stdout: list[int] = []
        self.cycles = 0
        self.max_cycles = max_cycles
        self.halted = False

    # ── register R/W ────────────────────────────────────────────────────────
    def rd(self, name: str) -> int:
        if name == 'r0':
            return 0   # ALU sees r0 as zero
        idx = _reg_idx(name)
        return self.regs[idx] & _MASK16

    def wr(self, name: str, value: int) -> None:
        if name == 'r0':
            return   # writes to r0 are discarded
        idx = _reg_idx(name)
        self.regs[idx] = value & _MASK16

    # ── operand resolution ─────────────────────────────────────────────────
    def operand_value(self, tok: str) -> int:
        if _is_reg(tok):
            return self.rd(tok)
        return _resolve_symbol(tok, self.prog.labels)

    # ── memory ─────────────────────────────────────────────────────────────
    def mem_read(self, addr: int) -> int:
        addr &= _MASK16
        return self.mem.get(addr, 0) & _MASK16

    def mem_write(self, addr: int, value: int) -> None:
        addr &= _MASK16
        if addr == 0x9FB5:   # terminal output (term_term)
            self.stdout.append(value & 0xFF)
            return
        if 0x9F80 <= addr <= 0x9FC6:
            return   # other terminal MMIO: ignore in emulator
        self.mem[addr] = value & _MASK16

    # ── jump conditions ────────────────────────────────────────────────────
    def cond(self, name: str) -> bool:
        f = self.flags
        if name == 'jmp': return True
        c = name[1:]   # strip leading 'j'
        # Map per manual.md condition table
        if c == 'be':  return bool(f.C or f.Z)
        if c == 'l':   return bool(f.S ^ f.O)
        if c == 'le':  return bool(f.Z or (f.S ^ f.O))
        if c == 's':   return bool(f.S)
        if c == 'z':   return bool(f.Z)
        if c == 'o':   return bool(f.O)
        if c == 'c':   return bool(f.C)
        if c == 'nbe': return not (f.C or f.Z)
        if c == 'nl':  return not (f.S ^ f.O)
        if c == 'nle': return not (f.Z or (f.S ^ f.O))
        if c == 'ns':  return not f.S
        if c == 'nz':  return not f.Z
        if c == 'no':  return not f.O
        if c == 'nc':  return not f.C
        raise RuntimeError(f"unknown condition: {name}")

    # ── main step ──────────────────────────────────────────────────────────
    def step(self) -> None:
        if self.pc < 0 or self.pc >= len(self.prog.insns):
            self.halted = True
            return
        ins = self.prog.insns[self.pc]
        op, args = ins.op, ins.args
        self.pc += 1
        # ── data movement ──
        if op == 'mov':
            d = args[0]; s = args[1]
            self.wr(d, self.operand_value(s))
            return
        # ── arithmetic ──
        if op == 'add':
            d, p, s = self._three(args)
            r = self.flags.from_add(self.operand_value(p), self.operand_value(s))
            self.wr(d, r); return
        if op == 'adc':
            d, p, s = self._three(args)
            r = self.flags.from_add(self.operand_value(p), self.operand_value(s), self.flags.C)
            self.wr(d, r); return
        if op == 'sub':
            # sub D, P, S → D = P - S. 2-op `sub D, S` → D = D - S (same).
            # sub D, imm form expands to `add D, D, -imm` per manual; our test
            # programs always use sub D, P_reg, S — so we treat all uniformly.
            d, p, s = self._three(args)
            pv = self.operand_value(p); sv = self.operand_value(s)
            # If S is a literal, R316 actually expands to `add D, P, -S` with
            # carry inverted. We approximate by computing borrow based on full
            # subtraction (correctness, not bit-exact carry semantics).
            r = self.flags.from_sub(pv, sv)
            self.wr(d, r); return
        if op == 'sbb':
            d, p, s = self._three(args)
            r = self.flags.from_sub(self.operand_value(p), self.operand_value(s), self.flags.C)
            self.wr(d, r); return
        if op == 'mul':
            d, p, s = self._three(args)
            r = (self.operand_value(p) * self.operand_value(s)) & _MASK16
            self.wr(d, r); return
        # ── logic ──
        if op in ('and', 'or', 'xor'):
            d, p, s = self._three(args)
            pv = self.operand_value(p); sv = self.operand_value(s)
            r = {'and': pv & sv, 'or': pv | sv, 'xor': pv ^ sv}[op]
            r &= _MASK16
            self.flags.from_logic(r)
            self.wr(d, r); return
        # ── shift ──
        if op == 'shl':
            d, p, s = self._three(args)
            sv = self.operand_value(s) & 0xF
            r = (self.operand_value(p) << sv) & _MASK16
            self.flags.from_logic(r)
            self.wr(d, r); return
        if op == 'shr':
            d, p, s = self._three(args)
            sv = self.operand_value(s) & 0xF
            r = (self.operand_value(p) & _MASK16) >> sv
            self.flags.from_logic(r)
            self.wr(d, r); return
        # ── memory ──
        if op == 'ld':
            # `ld D, addr` (2-op) or `ld D, base, offset` (3-op)
            d = args[0]
            if len(args) == 2:
                addr = self.operand_value(args[1])
            else:
                addr = (self.operand_value(args[1]) + self.operand_value(args[2])) & _MASK16
            self.wr(d, self.mem_read(addr))
            return
        if op == 'st':
            # `st value, addr` or `st value, base, offset`
            val = self.operand_value(args[0])
            if len(args) == 2:
                addr = self.operand_value(args[1])
            else:
                addr = (self.operand_value(args[1]) + self.operand_value(args[2])) & _MASK16
            self.mem_write(addr, val)
            return
        # ── jumps ──
        if op == 'jmp' or (op.startswith('j') and len(op) <= 4):
            self._do_jump(op, args); return
        if op == 'hlt':
            self.halted = True; return
        raise RuntimeError(f"unknown op at pc={self.pc-1}: {op} {args}")

    def _three(self, args: list[str]) -> tuple[str, str, str]:
        """Normalize arg lists to (D, P, S). Two-arg forms expand D-side."""
        if len(args) == 3:
            return args[0], args[1], args[2]
        if len(args) == 2:
            # `op D, S` → D = D op S (treating D as also P)
            return args[0], args[0], args[1]
        raise RuntimeError(f"unexpected arity: {args}")

    def _resolve_label(self, tok: str, scope: str) -> int:
        """Resolve a label reference to an instruction index.  Local labels
        (those starting with '.') are scoped to the containing global label."""
        if tok.startswith('.'):
            full = scope + tok
            if full in self.prog.labels:
                return self.prog.labels[full]
        if tok in self.prog.labels:
            return self.prog.labels[tok]
        return -1

    def _do_jump(self, op: str, args: list[str]) -> None:
        """`jmp target` (unconditional), `jmp r31, target` (call: lr = next pc).
        `j<cc> target` is conditional on flags."""
        scope = self.prog.insns[self.pc - 1].scope   # we already incremented pc
        # Check call form: `jmp r31, target` (also `jmp DSTREG, target`)
        if len(args) == 2 and _is_reg(args[0]):
            link = args[0]
            tgt = args[1]
            if _is_reg(tgt):
                target_pc = self.rd(tgt)
            else:
                target_pc = self._resolve_label(tgt, scope)
            if target_pc < 0:
                raise RuntimeError(f"jump to undefined label {tgt!r}")
            self.wr(link, self.pc)
            self.pc = target_pc
            return
        if len(args) != 1:
            raise RuntimeError(f"unexpected jump form: {op} {args}")
        tgt = args[0]
        if _is_reg(tgt):
            target_pc = self.rd(tgt)
            if target_pc == self.SENTINEL_LR:
                self.halted = True
                return
        else:
            target_pc = self._resolve_label(tgt, scope)
            if target_pc < 0:
                raise RuntimeError(f"jump to undefined label {tgt!r}")
        if op == 'jmp':
            self.pc = target_pc
            return
        if self.cond(op):
            self.pc = target_pc

    def run(self) -> None:
        while not self.halted and self.cycles < self.max_cycles:
            self.step()
            self.cycles += 1
        if not self.halted:
            raise RuntimeError(f"emulator timeout after {self.max_cycles} cycles "
                               f"(likely infinite loop). pc={self.pc}, "
                               f"cur={self.prog.insns[self.pc] if self.pc < len(self.prog.insns) else None}")

    def stdout_str(self) -> str:
        return ''.join(chr(c) for c in self.stdout)


# ── public helper ──────────────────────────────────────────────────────────

def run_main(asm: str, max_cycles: int = 1_000_000) -> tuple[int, str]:
    """Compile output → (return_value_of_main, stdout). Starts at `_C_main:`."""
    prog = parse_asm(asm)
    if '_C_main' not in prog.labels:
        raise RuntimeError("no _C_main in asm")
    m = Machine(prog, max_cycles=max_cycles)
    m.pc = prog.labels['_C_main']
    m.run()
    return m.regs[1] & _MASK16, m.stdout_str()


# ── standalone entry point ─────────────────────────────────────────────────

if __name__ == '__main__':
    import argparse
    import os
    import sys

    ap = argparse.ArgumentParser(
        description='Run a .asm or .c file through the R316 emulator.')
    ap.add_argument('file', help='.asm file (or .c file, compiled first)')
    ap.add_argument('--cycles', type=int, default=1_000_000,
                    metavar='N', help='max emulated cycles (default: 1 000 000)')
    ap.add_argument('--show-retval', action='store_true',
                    help='print main() return value after program output')
    args = ap.parse_args()

    path = args.file
    if path.endswith('.c'):
        # Import compiler from repo root (works whether run as
        # `python tests/r316_emu.py` or from the repo root).
        _this_dir = os.path.dirname(os.path.abspath(__file__))
        _root = os.path.dirname(_this_dir)
        if _root not in sys.path:
            sys.path.insert(0, _root)
        import importlib.util as _ilu
        _spec = _ilu.spec_from_file_location('_compiler_main',
                    os.path.join(_root, 'compiler.py'))
        _mod = _ilu.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        compile_c = _mod.compile_c
        with open(path, encoding='utf-8') as fh:
            src = fh.read()
        asm = compile_c(src, src_name=os.path.basename(path),
                        src_path=os.path.dirname(os.path.abspath(path)))
    else:
        with open(path, encoding='utf-8') as fh:
            asm = fh.read()

    retval, out = run_main(asm, max_cycles=args.cycles)
    sys.stdout.write(out)
    if args.show_retval:
        print(f'\n[exit {retval}]')
    sys.exit(retval)

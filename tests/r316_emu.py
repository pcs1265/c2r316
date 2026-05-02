"""Minimal R316 emulator for compiler test harness.

Goal: parse the compiler's output.asm and execute it well enough to verify
program behavior — catches codegen bugs (like the left-operand-clobber)
that pure pattern-matching tests miss.

Scope:
  - Instructions actually emitted by the c2r316 compiler:
      mov add adc sub sbb mul and or xor shl shr ld st jmp <jcc> hlt
    Plus manual spellings useful for inline asm/debug tests:
      movf adds/adcs/subs/sbbs ands/ors/xors shls/shrs exh/exhs mulh/muls/mulx
  - Macros: cmp / test / nop / call / ret (hardcoded; we skip %include "common")
  - Skipped: %include, %define, %eval, %ifndef, %endif, %macro definitions,
    {RPN expressions}, and most of runtime/runtime.asm. Execution starts at
    `_C_main:` directly, with SP and LR initialized by the harness.
  - Terminal: writes to 0x9FB5 are captured into stdout. Nothing else MMIO.

This is a small-cycle reference, not a frame-accurate TPT R316 simulation.
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Optional


# ── flags / register helpers ───────────────────────────────────────────────

_MASK16 = 0xFFFF
_BIT15  = 0x8000
R316_RAM_WORDS = 0x2000   # 8192 words — the writable-RAM ceiling on real R316
                          # hardware (binary-search probe in __stack_init caps here)

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
        """Compute p - s - bin_. Sets C=1 if a borrow occurred (i.e. result < 0
        before masking), which matches the R316 borrow flag convention."""
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
    update_flags: Optional[bool] = None

    def __repr__(self): return f'{self.op} {", ".join(self.args)}'


def _encode_cell(cell) -> object:
    """JSON-encode one RAM cell. Ints stay ints; Insns become a tagged dict."""
    if isinstance(cell, Insn):
        return {'op': cell.op, 'args': list(cell.args),
                'src_line': cell.src_line, 'scope': cell.scope,
                'update_flags': cell.update_flags}
    return int(cell) & _MASK16


def _decode_cell(cell) -> object:
    """Inverse of `_encode_cell`."""
    if isinstance(cell, dict):
        return Insn(op=cell['op'], args=list(cell['args']),
                    src_line=cell.get('src_line', 0), scope=cell.get('scope', ''),
                    update_flags=cell.get('update_flags'))
    return int(cell) & _MASK16


@dataclass
class Program:
    """Assembled program with a unified address space.

    `mem` is a list of length _MASK16+1 where each cell is either an `Insn`
    object (instruction word — we don't have real R316 opcode encodings, so we
    keep the parsed Insn at its address) or an `int` (data word, from `dw`).
    Cells outside the program's image are zero. `labels` maps each label to
    its address in this space; both code and data labels live in one map.
    """
    mem: list
    labels: dict[str, int]
    code_end: int = 0   # one past the last assembled cell — used for diagnostics


# Macros we hardcode: TPTASM common.asm defines these.
_MACROS = {
    'cmp':  ('sub', ['r0']),
    'test': ('and', ['r0']),
    'nop':  ('mov', ['r0', 'r0']),
    'call': ('jmp', ['r31']),
    'ret':  ('jmp', ['r31']),
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

_NOFLAG_ALIASES = {
    'adds': 'add', 'adcs': 'adc', 'subs': 'sub', 'sbbs': 'sbb',
    'ands': 'and', 'ors': 'or', 'xors': 'xor',
    'shls': 'shl', 'shrs': 'shr', 'exhs': 'exh',
}

_FLAG_ALIASES = {
    'movf': 'mov',
}


def _canonical_jump_op(op: str) -> str:
    if op in _JMP_ALIASES:
        return _JMP_ALIASES[op]
    # Synchronizing aliases insert `y` after the leading `j`: `jya` -> `jynbe`.
    if op.startswith('jy') and len(op) > 2:
        plain = 'j' + op[2:]
        if plain in _JMP_ALIASES:
            return 'jy' + _JMP_ALIASES[plain][1:]
    return op


def parse_asm(text: str) -> Program:
    """Parse compiler output into a unified address-space image.

    All instructions and `dw` words are placed at sequential addresses starting
    at 0, in source order — the same model real R316 sees (code IS RAM). Labels
    point at the cursor at the line they appear on; `__prog_end:` after a `dw`
    therefore correctly points one past the data, and `_C_main:` followed by
    code points at the first instruction of main, regardless of how many bare
    labels intervene.

    Symbol references inside `dw` cells are resolved in a second pass once all
    labels are known.
    """
    mem: list = [0] * (_MASK16 + 1)
    labels: dict[str, int] = {}
    pending_labels: list[str] = []      # labels waiting for the next placed cell
    deferred_dw: list[tuple[int, str]] = []  # (addr, raw_token) — resolve later
    cur_global = ''
    in_macro_def = False
    if_stack: list[bool] = []
    cursor = 0

    def flush_labels_to(addr: int) -> None:
        nonlocal pending_labels
        for lbl in pending_labels:
            labels[lbl] = addr & _MASK16
        pending_labels = []

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
            if_stack.append(True)
            continue
        if line.startswith('%ifdef'):
            if_stack.append(False)
            continue
        if line.startswith('%endif'):
            if if_stack: if_stack.pop()
            continue
        if line.startswith('%else'):
            if if_stack: if_stack[-1] = not if_stack[-1]
            continue
        if if_stack and not if_stack[-1]:
            continue

        # %eval name rpn... — evaluate RPN expression and store as label
        if line.startswith('%eval '):
            parts = line.split()
            if len(parts) >= 3:
                sym = parts[1]
                stack: list[int] = []
                for tok in parts[2:]:
                    if tok == '+':   stack.append(stack.pop(-2) + stack.pop())
                    elif tok == '-': v = stack.pop(); stack.append(stack.pop() - v)
                    elif tok == '*': stack.append(stack.pop(-2) * stack.pop())
                    elif tok == '/': v = stack.pop(); stack.append(stack.pop() // v)
                    elif tok in labels: stack.append(labels[tok])
                    else:
                        try: stack.append(int(tok, 0))
                        except ValueError: stack.append(0)
                if stack:
                    labels[sym] = stack[-1] & _MASK16
            continue

        # %define name value — only handle simple numeric defines
        if line.startswith('%define '):
            parts = line.split()
            if len(parts) == 3:
                try:
                    labels[parts[1]] = int(parts[2], 0) & _MASK16
                except ValueError:
                    pass
            continue

        # Directives we ignore but don't fail on
        if line.startswith('%'):
            continue

        # Label?  `name:` or `name: instr ...`
        m = re.match(r'^(\.?[A-Za-z_][A-Za-z0-9_]*)\s*:(.*)$', line)
        if m:
            lbl = m.group(1)
            rest = m.group(2).strip()
            if not lbl.startswith('.'):
                cur_global = lbl
            full = lbl if not lbl.startswith('.') else cur_global + lbl
            pending_labels.append(full)
            if not rest:
                continue
            line = rest

        # `dw value, value, value` → place each at the cursor
        m = re.match(r'^dw\s+(.*)$', line)
        if m:
            values = [v.strip() for v in m.group(1).split(',')]
            flush_labels_to(cursor)
            for v in values:
                deferred_dw.append((cursor, v))
                mem[cursor] = 0   # placeholder, overwritten in resolve pass
                cursor = (cursor + 1) & _MASK16
            continue

        # Instruction
        m = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)(?:\s+(.*))?$', line)
        if not m:
            continue
        op = m.group(1)
        args_str = m.group(2) or ''
        args = [a.strip() for a in args_str.split(',')] if args_str else []
        args = [a for a in args if a]
        update_flags: Optional[bool] = None

        if op in _MACROS:
            new_op, prefix = _MACROS[op]
            op = new_op
            args = list(prefix) + args
        op = _canonical_jump_op(op)
        if op in _NOFLAG_ALIASES:
            op = _NOFLAG_ALIASES[op]
            update_flags = False
        if op in _FLAG_ALIASES:
            op = _FLAG_ALIASES[op]
            update_flags = True

        flush_labels_to(cursor)
        mem[cursor] = Insn(op=op, args=args, src_line=lineno, scope=cur_global,
                           update_flags=update_flags)
        cursor = (cursor + 1) & _MASK16

    # Any labels still pending at EOF point one past the last placed cell
    flush_labels_to(cursor)

    # Resolve dw references to symbols
    for addr, tok in deferred_dw:
        try:
            mem[addr] = _resolve_symbol(tok, labels) & _MASK16
        except ValueError:
            mem[addr] = 0

    return Program(mem=mem, labels=labels, code_end=cursor)


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

    def __init__(self, prog: Program, sp_init: int = 0x8000, max_cycles: int | None = 1_000_000,
                 stdin: str = '', freq: float | None = None, interactive: bool = False,
                 ram_words: int | None = None):
        self.prog = prog
        self.regs = [0] * 32
        self.regs[30] = sp_init        # sp
        self.regs[31] = self.SENTINEL_LR
        self.flags = Flags()
        # Copy the parsed program image into our own RAM. Cells are either
        # Insn objects (instruction words) or ints (data / poison). A stray
        # `st` into a code address replaces the Insn with an int, and the next
        # fetch there will fail as "non-instruction" — roughly what real R316
        # would do when decoding the garbage left behind.
        self.mem: list = list(prog.mem)
        self.pc: int = 0
        self.stdout: list[int] = []
        self.stdin: list[int] = [ord(c) for c in stdin]
        self.stdin_pos: int = 0
        self.cycles = 0
        self.max_cycles = max_cycles  # None = unlimited
        self.freq = freq              # Hz throttle, or None for full speed
        # None = full 64K; set to e.g. 2048 to simulate a smaller RAM machine
        self.ram_words = ram_words
        self.halted = False
        self.interactive = interactive
        self._term_settings = None
        # Terminal state for cursor tracking
        self._cursor_col = 0
        self._cursor_row = 0
        self._term_cols = 24   # updated from hrange writes
        self._term_rows = 16   # updated from vrange writes
        # Debugging support
        self._breakpoints: dict[int, dict] = {}  # pc -> breakpoint info
        self._breakpoint_counter: int = 0
        self._trace: list[dict] = []  # Execution trace history
        self._trace_enabled: bool = False
        self._interrupted: bool = False  # Set by SIGINT handler
        if interactive:
            self._setup_raw_terminal()

    # ── debugging API ────────────────────────────────────────────────────────
    def get_registers(self) -> dict[str, int]:
        """Return all registers as a dict (r0-r31)."""
        return {f'r{i}': self.regs[i] & _MASK16 for i in range(32)}

    def get_flags(self) -> dict[str, int]:
        """Return flags as a dict (Z, S, C, O)."""
        return {'Z': self.flags.Z, 'S': self.flags.S, 'C': self.flags.C, 'O': self.flags.O}

    def get_pc(self) -> int:
        """Return current PC (instruction index)."""
        return self.pc

    def get_memory(self, addr: int, count: int = 1) -> list[int]:
        """Read 'count' words starting at addr."""
        addr &= _MASK16
        return [self.mem_read((addr + i) & _MASK16) for i in range(count)]

    def get_current_instruction(self) -> dict | None:
        """Return current instruction info, or None if halted/end/non-instruction."""
        if self.pc < 0 or self.pc > _MASK16:
            return None
        ins = self._fetch_cell(self.pc)
        if not isinstance(ins, Insn):
            return None
        return {'op': ins.op, 'args': list(ins.args), 'src_line': ins.src_line, 'scope': ins.scope}

    def get_stdout(self) -> str:
        """Return captured stdout as string."""
        return ''.join(chr(c) for c in self.stdout)

    def is_halted(self) -> bool:
        """Return True if machine is halted."""
        return self.halted

    def get_trace(self) -> list[dict]:
        """Return execution trace history."""
        return list(self._trace)

    def clear_trace(self) -> None:
        """Clear execution trace history."""
        self._trace = []

    def enable_trace(self) -> None:
        """Enable execution tracing."""
        self._trace_enabled = True

    def disable_trace(self) -> None:
        """Disable execution tracing."""
        self._trace_enabled = False

    def snapshot(self) -> dict:
        """Return complete machine state for debugging."""
        return {
            'pc': self.pc,
            'cycles': self.cycles,
            'halted': self.halted,
            'regs': self.get_registers(),
            'flags': self.get_flags(),
            'stdout': self.get_stdout(),
            'stdin': list(self.stdin),
            'stdin_pos': self.stdin_pos,
            'current_instruction': self.get_current_instruction(),
            'breakpoints': self.list_breakpoints(),
            'trace_count': len(self._trace),
        }

    def save_state(self) -> dict:
        """Save complete state to a dict for later restoration."""
        return {
            'version': 1,
            'pc': self.pc,
            'cycles': self.cycles,
            'halted': self.halted,
            'regs': list(self.regs),
            'flags': {'Z': self.flags.Z, 'S': self.flags.S, 'C': self.flags.C, 'O': self.flags.O},
            'mem': list(self.mem),
            'stdout': list(self.stdout),
            'stdin': list(self.stdin),
            'stdin_pos': self.stdin_pos,
            'cursor_col': self._cursor_col,
            'cursor_row': self._cursor_row,
            'term_cols': self._term_cols,
            'term_rows': self._term_rows,
            'trace': list(self._trace),
            'breakpoints': {pc: bp.copy() for pc, bp in self._breakpoints.items()},
        }

    def restore_state(self, state: dict) -> None:
        """Restore state from a dict saved by save_state()."""
        if state.get('version', 0) != 1:
            raise ValueError("Unsupported state version")
        self.pc = state['pc']
        self.cycles = state['cycles']
        self.halted = state['halted']
        self.regs = list(state['regs'])
        self.flags.Z = state['flags']['Z']
        self.flags.S = state['flags']['S']
        self.flags.C = state['flags']['C']
        self.flags.O = state['flags']['O']
        self.mem = list(state['mem'])
        self.stdout = list(state['stdout'])
        self.stdin = list(state['stdin'])
        self.stdin_pos = state['stdin_pos']
        self._cursor_col = state.get('cursor_col', 0)
        self._cursor_row = state.get('cursor_row', 0)
        self._term_cols = state.get('term_cols', 24)
        self._term_rows = state.get('term_rows', 16)
        self._trace = list(state.get('trace', []))
        self._breakpoints = {int(pc): bp.copy() for pc, bp in state.get('breakpoints', {}).items()}

    def save_state_file(self, filepath: str) -> None:
        """Save complete state to a JSON file.

        Memory is dumped as a flat list covering the writable RAM region
        (`0..R316_RAM_WORDS`, i.e. the 8192-word ceiling real R316 hardware
        exposes). Each cell is either an `int` (data) or a small dict
        `{"op": ..., "args": [...], "scope": ..., "src_line": ...}` for `Insn`
        cells. The dump is self-contained: restoring does not require the
        original `Program`, so source-code changes between save and load can't
        silently corrupt restored memory.
        """
        import json
        state = self.save_state()
        state['mem'] = [_encode_cell(c) for c in self.mem[:R316_RAM_WORDS]]
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=2)

    @classmethod
    def load_state_file(cls, filepath: str, prog: Program) -> 'Machine':
        """Load state from a JSON file and return a new Machine instance.

        Memory comes entirely from the dump — `prog` is still required for the
        `Machine` constructor (label resolution at runtime), but mismatches
        between the saved program and `prog` no longer silently corrupt the
        restored memory image, since cells are decoded directly from the file.
        """
        import json
        with open(filepath, 'r', encoding='utf-8') as f:
            state = json.load(f)
        mem = [0] * (_MASK16 + 1)
        for i, cell in enumerate(state['mem']):
            mem[i] = _decode_cell(cell)
        state['mem'] = mem
        state['breakpoints'] = {int(pc): bp for pc, bp in state.get('breakpoints', {}).items()}
        m = cls(prog)
        m.restore_state(state)
        return m

    def set_breakpoint(self, label_or_pc) -> int:
        """Set a breakpoint at a label or PC. Returns breakpoint ID."""
        if isinstance(label_or_pc, str):
            pc = self.prog.labels.get(label_or_pc)
            if pc is None:
                raise ValueError(f"Unknown label: {label_or_pc}")
        else:
            pc = int(label_or_pc)
        self._breakpoint_counter += 1
        bp_id = self._breakpoint_counter
        self._breakpoints[pc] = {'id': bp_id, 'pc': pc, 'label': label_or_pc if isinstance(label_or_pc, str) else None}
        return bp_id

    def clear_breakpoint(self, bp_id: int) -> bool:
        """Clear a breakpoint by ID. Returns True if found."""
        for pc, bp in list(self._breakpoints.items()):
            if bp['id'] == bp_id:
                del self._breakpoints[pc]
                return True
        return False

    def clear_all_breakpoints(self) -> None:
        """Clear all breakpoints."""
        self._breakpoints = {}

    def list_breakpoints(self) -> list[dict]:
        """List all breakpoints."""
        return [bp.copy() for bp in self._breakpoints.values()]

    def run_until_breakpoint(self) -> bool:
        """Run until a breakpoint is hit or machine halts. Returns True if breakpoint hit."""
        while not self.halted:
            if self.pc in self._breakpoints:
                return True
            if not self._step_internal():
                return False
        return False

    def run_until_pc(self, target_pc: int) -> bool:
        """Run until PC reaches target_pc or machine halts. Returns True if target reached."""
        while not self.halted and self.pc != target_pc:
            if not self._step_internal():
                return False
        return self.pc == target_pc

    def step(self, count: int = 1) -> bool:
        """Execute one or more instructions. Returns True if still running, False if halted.
        
        Args:
            count: Number of instructions to execute (default: 1)
        """
        for _ in range(count):
            if not self._step_internal():
                return False
        return not self.halted

    def _step_internal(self) -> bool:
        """Internal step with trace recording."""
        if self.halted:
            return False
        # Record state before for trace
        if self._trace_enabled:
            state_before = {
                'pc': self.pc,
                'regs': self.get_registers(),
                'flags': self.get_flags(),
            }
        # Execute instruction
        self._execute_step()
        self.cycles += 1
        # Record state after for trace
        if self._trace_enabled:
            insn_info = None
            ins = self._fetch_cell(state_before['pc']) if 0 <= state_before['pc'] <= _MASK16 else None
            if isinstance(ins, Insn):
                insn_info = {'op': ins.op, 'args': list(ins.args)}
            self._trace.append({
                'pc': state_before['pc'],
                'op': insn_info['op'] if insn_info else None,
                'args': insn_info['args'] if insn_info else None,
                'regs_before': state_before['regs'],
                'regs_after': self.get_registers(),
                'flags_before': state_before['flags'],
                'flags_after': self.get_flags(),
            })
        return not self.halted

    def _execute_step(self) -> None:
        """Execute one instruction (internal implementation)."""
        if self.pc < 0 or self.pc > _MASK16:
            self.halted = True
            return
        ins = self._fetch_cell(self.pc)
        if not isinstance(ins, Insn):
            raise RuntimeError(
                f"executing non-instruction at pc={self.pc:#06x}: {ins!r} "
                f"(code memory was overwritten or PC ran into data)"
            )
        op, args = ins.op, ins.args
        self.pc = (self.pc + 1) & _MASK16
        # ── data movement ──
        if op == 'mov':
            if len(args) == 3:
                d, p, s = args
            elif len(args) == 2:
                d, s = args
                p = s if _is_reg(s) else 'r0'
            else:
                raise RuntimeError(f"unexpected mov arity: {args}")
            value = self._source_high(p) | (self.operand_value(s) & _MASK16)
            self._maybe_logic_flags(value, ins.update_flags, default=False)
            self.wr(d, value)
            return
        # ── arithmetic ──
        if op == 'add':
            d, p, s = self._three(args)
            r = self._add_result(self.operand_value(p), self.operand_value(s), 0,
                                 ins.update_flags, default=True)
            self.wr(d, self._source_high(p) | r); return
        if op == 'adc':
            d, p, s = self._three(args)
            r = self._add_result(self.operand_value(p), self.operand_value(s), self.flags.C,
                                 ins.update_flags, default=True)
            self.wr(d, self._source_high(p) | r); return
        if op == 'sub':
            d, p, s = self._three(args)
            pv = self.operand_value(p); sv = self.operand_value(s)
            r = self._sub_result(pv, sv, 0, ins.update_flags, default=True)
            self.wr(d, self._source_high(p) | r); return
        if op == 'sbb':
            d, p, s = self._three(args)
            r = self._sub_result(self.operand_value(p), self.operand_value(s), self.flags.C,
                                 ins.update_flags, default=True)
            self.wr(d, self._source_high(p) | r); return
        if op == 'mul':
            d, p, s = self._three(args)
            r = (self.operand_value(p) * self.operand_value(s)) & _MASK16
            self.wr(d, r); return
        if op == 'mulh':
            d, p, s = self._three(args)
            r = ((self.operand_value(p) * self.operand_value(s)) >> 16) & _MASK16
            self.wr(d, r); return
        if op == 'muls':
            d, p, s = self._three(args)
            r = ((_s16(self.operand_value(p)) * _s16(self.operand_value(s))) >> 16) & _MASK16
            self.wr(d, r); return
        if op == 'mulx':
            d, p, s = self._three(args)
            r = (((self.operand_value(p) & _MASK16) * _s16(self.operand_value(s))) >> 16) & _MASK16
            self.wr(d, r); return
        # ── logic ──
        if op in ('and', 'or', 'xor'):
            d, p, s = self._three(args)
            pv = self.operand_value(p); sv = self.operand_value(s)
            r = {'and': pv & sv, 'or': pv | sv, 'xor': pv ^ sv}[op]
            r &= _MASK16
            self._maybe_logic_flags(r, ins.update_flags, default=True)
            self.wr(d, self._source_high(p) | r); return
        # ── shift ──
        if op == 'shl':
            d, p, s = self._three(args)
            sv = self.operand_value(s) & 0xF
            r = (self.operand_value(p) << sv) & _MASK16
            self._maybe_logic_flags(r, ins.update_flags, default=True)
            self.wr(d, self._source_high(p) | r); return
        if op == 'shr':
            d, p, s = self._three(args)
            sv = self.operand_value(s) & 0xF
            r = (self.operand_value(p) & _MASK16) >> sv
            self._maybe_logic_flags(r, ins.update_flags, default=True)
            self.wr(d, self._source_high(p) | r); return
        if op == 'exh':
            d, p, s = self._three(args)
            r = ((self.operand_value(s) & _MASK16) << 16) | ((self.rd32(p) >> 16) & _MASK16)
            self._maybe_logic_flags(r, ins.update_flags, default=True)
            self.wr(d, r); return
        # ── memory ──
        if op == 'ld':
            d = args[0]
            if len(args) == 2:
                addr = self.operand_value(args[1])
            else:
                addr = (self.operand_value(args[1]) + self.operand_value(args[2])) & _MASK16
            self.wr(d, self.mem_read(addr))
            return
        if op == 'st':
            val = self.operand_value(args[0])
            if len(args) == 2:
                addr = self.operand_value(args[1])
            else:
                addr = (self.operand_value(args[1]) + self.operand_value(args[2])) & _MASK16
            self.mem_write(addr, val)
            return
        # ── jumps ──
        if op == 'jmp' or op.startswith('j'):
            self._do_jump(op, args); return
        if op == 'hlt':
            self.halted = True; return
        raise RuntimeError(f"unknown op at pc={self.pc-1}: {op} {args}")

    def _setup_raw_terminal(self) -> None:
        """Set up terminal for raw, non-echoing input."""
        import sys
        import os
        self._is_windows = os.name == 'nt'
        if self._is_windows:
            # Windows: use msvcrt for raw input (non-blocking)
            try:
                import msvcrt
                self._msvcrt = msvcrt
                # Clear screen and move cursor to row 2
                sys.stdout.write('\x1b[2J\x1b[2;1H')
                sys.stdout.flush()
            except ImportError:
                self._term_settings = None
        else:
            # Unix/Linux: use termios
            try:
                import termios
                import tty
                self._term_settings = termios.tcgetattr(sys.stdin.fileno())
                # Use cbreak mode instead of raw mode to allow SIGINT (Ctrl+C) to work
                tty.setcbreak(sys.stdin.fileno())
                # Make stdin non-blocking so we can check for Ctrl+C frequently
                import fcntl
                flags = fcntl.fcntl(sys.stdin.fileno(), fcntl.F_GETFL)
                fcntl.fcntl(sys.stdin.fileno(), fcntl.F_SETFL, flags | os.O_NONBLOCK)
                # Clear screen and move cursor to row 2 (skip top line for status bar)
                sys.stdout.write('\x1b[2J\x1b[2;1H')
                sys.stdout.flush()
            except (ImportError, termios.error, OSError):
                # Non-terminal input: fall back to normal input
                self._term_settings = None

    def _restore_terminal(self) -> None:
        """Restore terminal to original settings."""
        import sys
        if hasattr(self, '_is_windows') and self._is_windows:
            # Reset colors and any scroll region configured for interactive terminal mode.
            sys.stdout.write('\x1b[0m\x1b[r')
            sys.stdout.flush()
        elif self._term_settings is not None:
            import termios
            try:
                # Reset colors and any scroll region configured for interactive terminal mode.
                sys.stdout.write('\x1b[0m\x1b[r')
                sys.stdout.flush()
                termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, self._term_settings)
            except Exception:
                pass

    # ── register R/W ────────────────────────────────────────────────────────
    def rd(self, name: str) -> int:
        if name == 'r0':
            return 0   # ALU sees r0 as zero
        idx = _reg_idx(name)
        return self.regs[idx] & _MASK16

    def rd32(self, name: str) -> int:
        if name == 'r0':
            return 0x20000000
        idx = _reg_idx(name)
        return self.regs[idx] & 0xFFFFFFFF

    def wr(self, name: str, value: int) -> None:
        if name == 'r0':
            return   # writes to r0 are discarded
        idx = _reg_idx(name)
        self.regs[idx] = value & 0xFFFFFFFF

    def _source_high(self, tok: str) -> int:
        return self.rd32(tok) & 0xFFFF0000 if _is_reg(tok) else 0

    def _flags_enabled(self, override: Optional[bool], default: bool) -> bool:
        return default if override is None else override

    def _maybe_logic_flags(self, result: int, override: Optional[bool], default: bool) -> None:
        if self._flags_enabled(override, default):
            self.flags.from_logic(result)

    def _add_result(self, a: int, b: int, cin: int,
                    override: Optional[bool], default: bool) -> int:
        if self._flags_enabled(override, default):
            return self.flags.from_add(a, b, cin)
        return (a + b + cin) & _MASK16

    def _sub_result(self, p: int, s: int, bin_: int,
                    override: Optional[bool], default: bool) -> int:
        if self._flags_enabled(override, default):
            return self.flags.from_sub(p, s, bin_)
        return (p - s - bin_) & _MASK16

    # ── operand resolution ─────────────────────────────────────────────────
    def operand_value(self, tok: str) -> int:
        if _is_reg(tok):
            return self.rd(tok)
        # inline RPN: { token token ... }
        if tok.startswith('{') and tok.endswith('}'):
            inner = tok[1:-1].split()
            stk: list[int] = []
            for t in inner:
                if t == '+':   stk.append(stk.pop(-2) + stk.pop())
                elif t == '-': v = stk.pop(); stk.append(stk.pop() - v)
                elif t == '*': stk.append(stk.pop(-2) * stk.pop())
                elif t == '/': v = stk.pop(); stk.append(stk.pop() // v)
                else: stk.append(_resolve_symbol(t, self.prog.labels))
            return (stk[-1] if stk else 0) & _MASK16
        return _resolve_symbol(tok, self.prog.labels)

    # ── memory ─────────────────────────────────────────────────────────────
    def _map_internal_addr(self, addr: int) -> int:
        """Map a 16-bit address through the manual's 128-cell block mirror model.

        `ram_words=None` preserves the historical harness mode: a flat 64K
        writable address space.  When `ram_words` is configured, reads mirror
        the power-of-two row window and writes are accepted only by the true
        read/write rows.
        """
        addr &= _MASK16
        if self.ram_words is None:
            return addr
        rows = max(1, (self.ram_words + 0x7F) // 0x80)
        p2rows = 1 << (rows - 1).bit_length()
        block = addr >> 7
        offset = addr & 0x7F
        mapped_block = block % p2rows
        row = mapped_block if mapped_block < rows else rows - 1
        mapped = (row << 7) + offset
        return min(mapped, self.ram_words - 1)

    def _is_writable_internal_addr(self, addr: int) -> bool:
        addr &= _MASK16
        if self.ram_words is None:
            return True
        return addr < self.ram_words

    def _fetch_cell(self, addr: int):
        return self.mem[self._map_internal_addr(addr)]

    def mem_read(self, addr: int) -> int:
        addr &= _MASK16
        if addr == 0x9F80:  # terminal input
            if self.stdin_pos < len(self.stdin):
                ch = self.stdin[self.stdin_pos]
                self.stdin_pos += 1
                return ch
            if self.interactive:
                # Read from real terminal (raw mode, no echo, non-blocking)
                import sys
                try:
                    if hasattr(self, '_is_windows') and self._is_windows:
                        # Windows: use msvcrt.kbhit() to check for input (non-blocking)
                        if self._msvcrt.kbhit():
                            ch = self._msvcrt.getch()
                            if not ch:
                                return 0
                            ch = ord(ch) if isinstance(ch, bytes) else ch
                            # Filter out arrow keys and function keys on Windows
                            # Arrow keys: 0xE0 followed by A/B/C/D
                            if ch == 0xE0:
                                # Read the next byte and discard
                                if self._msvcrt.kbhit():
                                    self._msvcrt.getch()
                                return 0  # Ignore arrow keys
                            return ch
                    else:
                        # Unix/Linux: use sys.stdin.read(1) in non-blocking mode
                        try:
                            ch = sys.stdin.read(1)
                            if not ch:  # EOF
                                return 0
                            ch = ord(ch)
                            # Filter out escape sequences (arrow keys, function keys, etc.)
                            # Arrow keys send: ESC [ A/B/C/D
                            if ch == 27:  # ESC
                                # Try to read the next two characters
                                try:
                                    next1 = sys.stdin.read(1)
                                    if next1 == '[':
                                        next2 = sys.stdin.read(1)
                                        # Arrow keys: A=up, B=down, C=right, D=left
                                        if next2 in 'ABCD':
                                            return 0  # Ignore arrow keys
                                        # Other escape sequences - just return 0
                                        return 0
                                except:
                                    pass
                                # Single ESC - return 0
                                return 0
                            return ch
                        except (IOError, OSError):
                            # Non-blocking read with no data available
                            return 0
                except Exception:
                    return 0
            return 0  # no more input (keeps polling loop spinning → timeout)
        cell = self._fetch_cell(addr)
        if isinstance(cell, Insn):
            return 0   # code memory has no real opcode encoding
        return cell & _MASK16

    def mem_write(self, addr: int, value: int) -> None:
        addr &= _MASK16
        if addr == 0x9FB5:   # terminal output (term_term)
            ch = value & 0xFF
            self.stdout.append(ch)
            if ch == 10:  # newline
                self._cursor_col = 0
                self._cursor_row += 1
                if self._cursor_row >= self._term_rows:
                    self._cursor_row = self._term_rows - 1
                if self.interactive:
                    import sys
                    sys.stdout.write('\r\n')
                    sys.stdout.flush()
            else:
                self._cursor_col += 1
                wrap = self._cursor_col >= self._term_cols
                if wrap:
                    self._cursor_col = 0
                    self._cursor_row += 1
                    if self._cursor_row >= self._term_rows:
                        self._cursor_row = self._term_rows - 1
                if self.interactive:
                    import sys
                    sys.stdout.write(chr(ch))
                    if wrap:
                        sys.stdout.write('\r\n')
                    sys.stdout.flush()
            return
        if addr == 0x9FB7:   # TERM_TERM_COL: terminal output with colour
            # data = (bg<<12)|(fg<<8)|char
            ch = value & 0xFF
            self.stdout.append(ch)
            if ch == 10:  # newline
                self._cursor_col = 0
                self._cursor_row += 1
                if self._cursor_row >= self._term_rows:
                    self._cursor_row = self._term_rows - 1
                if self.interactive:
                    import sys
                    sys.stdout.write('\r\n')
                    sys.stdout.flush()
            else:
                self._cursor_col += 1
                wrap = self._cursor_col >= self._term_cols
                if wrap:
                    self._cursor_col = 0
                    self._cursor_row += 1
                    if self._cursor_row >= self._term_rows:
                        self._cursor_row = self._term_rows - 1
                if self.interactive:
                    import sys
                    fg = (value >> 8) & 0xF
                    bg = (value >> 12) & 0xF
                    fg_ansi = self._r316_to_ansi(fg)
                    bg_ansi = self._r316_to_ansi(bg)
                    sys.stdout.write(f'\x1b[38;5;{fg_ansi}m\x1b[48;5;{bg_ansi}m')
                    sys.stdout.write(chr(ch))
                    if wrap:
                        sys.stdout.write('\r\n')
                    sys.stdout.flush()
            return
        if addr == 0x9FC4:   # TERM_CURSOR: cursor position
            # bits[9:5]=row, bits[4:0]=col
            col = value & 0x1F
            row = (value >> 5) & 0x1F
            self._cursor_col = col
            self._cursor_row = row
            if self.interactive:
                import sys
                # Use ANSI escape code to move cursor
                # Add +1 to row to skip top line (for status bar)
                sys.stdout.write(f'\x1b[{row + 2};{col + 1}H')
                sys.stdout.flush()
            return
        if addr == 0x9FC6:   # TERM_COLOUR: fg/bg colour
            # bits[7:4]=bg, bits[3:0]=fg
            if self.interactive:
                import sys
                fg = value & 0xF
                bg = (value >> 4) & 0xF
                # Map R316 colors to ANSI 256-color palette
                fg_ansi = self._r316_to_ansi(fg)
                bg_ansi = self._r316_to_ansi(bg)
                sys.stdout.write(f'\x1b[38;5;{fg_ansi}m\x1b[48;5;{bg_ansi}m')
                sys.stdout.flush()
            return
        if addr == 0x9FC2:   # TERM_HRANGE: bits[9:5]=high_col, bits[4:0]=low_col
            self._term_cols = ((value >> 5) & 0x1F) + 1
            return
        if addr == 0x9FC3:   # TERM_VRANGE: bits[9:5]=high_row, bits[4:0]=low_row
            self._term_rows = ((value >> 5) & 0x1F) + 1
            if self.interactive:
                import sys
                # Confine ANSI scrolling to the R316 terminal rows (row 1 is status bar)
                sys.stdout.write(f'\x1b[2;{self._term_rows + 1}r')
                sys.stdout.flush()
            return
        if 0x9F80 <= addr <= 0x9FC6:
            return   # other terminal MMIO: ignore in emulator
        if not self._is_writable_internal_addr(addr):
            return   # read-only mirror / external mirror — write ignored
        self.mem[self._map_internal_addr(addr)] = value & _MASK16

    def _r316_to_ansi(self, color: int) -> int:
        """Map R316 color index to ANSI 256-color palette."""
        # R316 colors map to standard 16-color ANSI palette
        ansi_colors = [
            0,   # TERM_BLACK   -> 0 (black)
            4,   # TERM_DBLUE   -> 4 (blue)
            2,   # TERM_DGREEN  -> 2 (green)
            6,   # TERM_DCYAN   -> 6 (cyan)
            1,   # TERM_DRED    -> 1 (red)
            5,   # TERM_DMAGENTA -> 5 (magenta)
            3,   # TERM_DYELLOW -> 3 (yellow)
            7,   # TERM_LGREY   -> 7 (white/light gray)
            8,   # TERM_DGREY   -> 8 (bright black / dark gray)
            12,  # TERM_LBLUE   -> 12 (bright blue)
            10,  # TERM_LGREEN  -> 10 (bright green)
            14,  # TERM_LCYAN   -> 14 (bright cyan)
            9,   # TERM_LRED    -> 9 (bright red)
            13,  # TERM_LMAGENTA -> 13 (bright magenta)
            11,  # TERM_LYELLOW -> 11 (bright yellow)
            15,  # TERM_WHITE   -> 15 (bright white)
        ]
        return ansi_colors[color & 0xF]

    # ── jump conditions ────────────────────────────────────────────────────
    def cond(self, name: str) -> bool:
        f = self.flags
        if name == 'jmp': return True
        c = name[1:]   # strip leading 'j'
        if c.startswith('y'):
            c = c[1:]
        elif len(c) > 1 and c[1] == 'y':
            c = c[0] + c[2:]
        if c == '':
            return True
        # Map per manual.md condition table
        if c == 'be':  return bool(f.C or f.Z)
        if c == 'l':   return bool(f.S ^ f.O)
        if c == 'le':  return bool(f.Z or (f.S ^ f.O))
        if c == 's':   return bool(f.S)
        if c == 'z':   return bool(f.Z)
        if c == 'o':   return bool(f.O)
        if c == 'c':   return bool(f.C)
        if c == 'n':   return False
        if c == 'nbe': return not (f.C or f.Z)
        if c == 'nl':  return not (f.S ^ f.O)
        if c == 'nle': return not (f.Z or (f.S ^ f.O))
        if c == 'ns':  return not f.S
        if c == 'nz':  return not f.Z
        if c == 'no':  return not f.O
        if c == 'nc':  return not f.C
        raise RuntimeError(f"unknown condition: {name}")

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
        prev = self._fetch_cell((self.pc - 1) & _MASK16)   # we already incremented pc
        scope = prev.scope if isinstance(prev, Insn) else ''
        if len(args) == 2 and _is_reg(args[0]):
            link, tgt = args
        elif len(args) == 1:
            link, tgt = 'r0', args[0]
        else:
            raise RuntimeError(f"unexpected jump form: {op} {args}")

        if _is_reg(tgt):
            target_pc = self.rd(tgt)
        else:
            target_pc = self._resolve_label(tgt, scope)
            if target_pc < 0:
                raise RuntimeError(f"jump to undefined label {tgt!r}")

        # All jump forms write the post-fetch PC to D. Conditional variants only
        # gate the PC replacement; `jn D, S` is therefore useful for reading PC.
        self.wr(link, self.pc)
        sync = op.startswith('jy') or (len(op) > 2 and op[0] == 'j' and op[2] == 'y')
        if sync:
            return   # single execution unit: synchronizing jumps are bottommost
        should_jump = op == 'jmp' or self.cond(op)
        if should_jump and target_pc == self.SENTINEL_LR:
            self.halted = True
            return
        if op == 'jmp':
            self.pc = target_pc
            return
        if should_jump:
            self.pc = target_pc

    def run(self) -> None:
        import signal
        import time

        # Set up SIGINT handler to allow Ctrl+C to interrupt the emulator
        self._interrupted = False
        _orig_handler = signal.getsignal(signal.SIGINT)

        def _sigint_handler(signum, frame):
            self._interrupted = True

        signal.signal(signal.SIGINT, _sigint_handler)

        try:
            freq = self.freq
            if freq is not None:
                # Throttle to target frequency using a simple sleep-based approach.
                # We accumulate a "credit" of cycles owed and sleep when ahead.
                _BATCH = max(1, int(freq / 100))  # check time every ~10 ms of sim
                _batch_period = _BATCH / freq      # wall seconds per batch
                _deadline = time.monotonic() + _batch_period
                _batch = 0

            while not self.halted:
                # Check for Ctrl+C interrupt
                if self._interrupted:
                    self._restore_terminal()
                    print("\n[Interrupted]")
                    import sys
                    sys.exit(130)  # 128 + SIGINT(2)

                if self.max_cycles is not None and self.cycles >= self.max_cycles:
                    cur = self.mem[self.pc] if 0 <= self.pc <= _MASK16 else None
                    raise RuntimeError(
                        f"emulator timeout after {self.max_cycles} cycles "
                        f"(likely infinite loop). pc={self.pc}, cur={cur}"
                    )
                self._step_internal()
                if freq is not None:
                    _batch += 1
                    if _batch >= _BATCH:
                        _batch = 0
                        _now = time.monotonic()
                        _sleep = _deadline - _now
                        if _sleep > 0:
                            time.sleep(_sleep)
                        _deadline += _batch_period
        finally:
            # Restore original signal handler
            signal.signal(signal.SIGINT, _orig_handler)

    def stdout_str(self) -> str:
        return ''.join(chr(c) for c in self.stdout)


# ── public helper ──────────────────────────────────────────────────────────

def run_main(asm: str, max_cycles: int | None = 1_000_000, stdin: str = '',
             freq: float | None = None) -> tuple[int, str, int]:
    """Compile output → (return_value_of_main, stdout, cycles). Starts at address 0."""
    prog = parse_asm(asm)
    m = Machine(prog, sp_init=0, max_cycles=max_cycles, stdin=stdin, freq=freq)
    m.run()
    return m.regs[1] & _MASK16, m.stdout_str(), m.cycles


# ── standalone entry point ─────────────────────────────────────────────────

if __name__ == '__main__':
    import argparse
    import os
    import sys

    ap = argparse.ArgumentParser(
        description='Run a .asm or .c file through the R316 emulator.')
    ap.add_argument('file', help='.asm file (or .c file, compiled first)')
    ap.add_argument('--cycles', '-c', type=int, default=1_000_000,
                    metavar='N', help='max emulated cycles (default: 1 000 000)')
    ap.add_argument('--unlimited-cycles', '-u', action='store_true',
                    help='run without a cycle limit (no timeout guard)')
    ap.add_argument('--freq', '-f', type=float, default=None,
                    metavar='HZ', help='throttle emulation to HZ cycles/s (e.g. 1000000 for 1 MHz)')
    ap.add_argument('--show-retval', '-r', action='store_true',
                    help='print main() return value after program output')
    ap.add_argument('--stdin', '-s', type=str, default=None,
                    metavar='STR', help='provide stdin input as a string')
    ap.add_argument('--stdin-file', type=str, default=None,
                    metavar='FILE', help='read stdin input from a file')
    ap.add_argument('--interactive', '-i', action='store_true',
                    help='enable interactive terminal input (no echo, char-by-char)')
    ap.add_argument('--ram-words', type=int, default=None,
                    help='simulate a machine with this many words of RAM (e.g. 2048)')
    args = ap.parse_args()
    if args.unlimited_cycles:
        args.cycles = None

    # Determine stdin input
    stdin_input = ''
    if args.stdin is not None:
        stdin_input = args.stdin
    elif args.stdin_file is not None:
        with open(args.stdin_file, 'r', encoding='utf-8') as f:
            stdin_input = f.read()

    # Interactive mode is opt-in. Auto-enabling it for any TTY makes scripted
    # runs and compiler tests unexpectedly switch the user's terminal to raw
    # mode when a program polls terminal input.
    interactive = args.interactive

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
                        src_path=os.path.abspath(path))
    else:
        with open(path, encoding='utf-8') as fh:
            asm = fh.read()

    # Create machine with interactive mode if needed
    prog = parse_asm(asm)
    m = Machine(prog, sp_init=0, max_cycles=args.cycles, stdin=stdin_input, freq=args.freq, interactive=interactive, ram_words=args.ram_words)

    try:
        m.run()
    except RuntimeError as e:
        m._restore_terminal()
        print(f"\nerror: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        m._restore_terminal()

    out = m.stdout_str()
    retval = m.regs[1] & _MASK16
    cycles = m.cycles

    # In interactive mode, output was already printed in real-time
    if not interactive:
        sys.stdout.write(out)
    print(f'[{cycles} cycles]')
    if args.show_retval:
        print(f'[exit {retval}]')
    sys.exit(retval)

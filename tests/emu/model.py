"""Core data structures for parsed R316 programs and CPU state."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .constants import _BIT15, _MASK16, _u16

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



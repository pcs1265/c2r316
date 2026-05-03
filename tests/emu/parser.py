"""Assembler parser for the R316 emulator's test-oriented assembly subset."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from .constants import _MASK16
from .model import Insn, Program

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

# Common aliases we hardcode: TPTASM common.asm defines these.
# `nop` per manual line 516 is `mov r0, r0, r1`, NOT `mov r0, r0, r0` —
# the latter encodes as 0x00000000 (physically zero), which the assembler/HW
# silently rewrites to set bit 0x20000000, redirecting the destination from
# r0 to r16 and clobbering it.
_MACROS = {
    'cmp':  ('sub', ['r0']),
    'test': ('and', ['r0']),
    'nop':  ('mov', ['r0', 'r0', 'r1']),
}


@dataclass
class AsmMacro:
    params: list[str]
    body: list[str]

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
    asm_macros: dict[str, AsmMacro] = {}
    defines: dict[str, str] = {}
    cur_global = ''
    macro_def: tuple[str, list[str], list[str]] | None = None
    if_stack: list[bool] = []
    cursor = 0

    def flush_labels_to(addr: int) -> None:
        nonlocal pending_labels
        for lbl in pending_labels:
            labels[lbl] = addr & _MASK16
        pending_labels = []

    def expand_macro_line(macro: AsmMacro, args: list[str], unique: int) -> list[str]:
        subst = {name: (args[i] if i < len(args) else '') for i, name in enumerate(macro.params)}
        out: list[str] = []
        for body_line in macro.body:
            expanded = body_line
            for name, value in subst.items():
                expanded = re.sub(rf'\b{re.escape(name)}\b', value, expanded)
            # TPTASM peer labels are macro-local. Normalize the subset used by
            # runtime.asm into ordinary local labels with a per-expansion suffix.
            expanded = expanded.replace('_Macrounique', f'__macro_{unique}')
            expanded = re.sub(r'\.\s+_Peerlabel\s+(\w+)\s+(__macro_\d+)',
                              r'.__\1_\2', expanded)
            out.append(expanded)
        return out

    def apply_defines(tok: str) -> str:
        return defines.get(tok, tok)

    def scope_local(tok: str) -> str:
        return cur_global + tok if tok.startswith('.') else tok

    def process_line(line: str, lineno: int, expansion_depth: int = 0) -> None:
        nonlocal cur_global, cursor
        if not line:
            return
        if expansion_depth > 20:
            raise RuntimeError(f"macro expansion too deep at source line {lineno}")

        # Conditional blocks (very limited %ifndef / %endif / %else)
        if line.startswith('%ifndef'):
            if_stack.append(True)
            return
        if line.startswith('%ifdef'):
            if_stack.append(False)
            return
        if line.startswith('%endif'):
            if if_stack: if_stack.pop()
            return
        if line.startswith('%else'):
            if if_stack: if_stack[-1] = not if_stack[-1]
            return
        if if_stack and not if_stack[-1]:
            return

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
                    elif tok == '<<': v = stack.pop(); stack.append(stack.pop() << v)
                    elif tok == '>>': v = stack.pop(); stack.append(stack.pop() >> v)
                    elif tok in labels: stack.append(labels[tok])
                    else:
                        try: stack.append(int(tok, 0))
                        except ValueError: stack.append(0)
                if stack:
                    labels[sym] = stack[-1] & _MASK16
            return

        # %define name value — handle numeric constants and simple textual aliases
        # such as `sp -> r30`.
        if line.startswith('%define '):
            parts = line.split()
            if len(parts) == 3:
                defines[parts[1]] = parts[2]
                try:
                    labels[parts[1]] = int(parts[2], 0) & _MASK16
                except ValueError:
                    pass
            return

        # Directives we ignore but don't fail on
        if line.startswith('%'):
            return

        # Label?  `name:` or `name: instr ...`
        m = re.match(r'^(\.*[A-Za-z_][A-Za-z0-9_]*)\s*:(.*)$', line)
        if m:
            lbl = m.group(1)
            rest = m.group(2).strip()
            if not lbl.startswith('.'):
                cur_global = lbl
            full = lbl if not lbl.startswith('.') else cur_global + lbl
            pending_labels.append(full)
            if not rest:
                return
            line = rest

        # `dw value, value, value` → place each at the cursor
        m = re.match(r'^dw\s+(.*)$', line)
        if m:
            values = [scope_local(v.strip()) for v in m.group(1).split(',')]
            flush_labels_to(cursor)
            for v in values:
                deferred_dw.append((cursor, v))
                mem[cursor] = 0   # placeholder, overwritten in resolve pass
                cursor = (cursor + 1) & _MASK16
            return

        # Instruction
        m = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)(?:\s+(.*))?$', line)
        if not m:
            return
        op = m.group(1)
        args_str = m.group(2) or ''
        args = [a.strip() for a in args_str.split(',')] if args_str else []
        args = [scope_local(apply_defines(a)) for a in args if a]
        update_flags: Optional[bool] = None

        if op in asm_macros:
            unique = lineno * 100 + expansion_depth
            for expanded in expand_macro_line(asm_macros[op], args, unique):
                process_line(_strip_comment(expanded).strip(), lineno, expansion_depth + 1)
            return

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

    for lineno, raw in enumerate(text.splitlines(), 1):
        line = _strip_comment(raw).strip()
        if not line:
            continue

        if macro_def is not None:
            if line.startswith('%endmacro'):
                name, params, body = macro_def
                asm_macros[name] = AsmMacro(params, body)
                macro_def = None
            else:
                macro_def[2].append(line)
            continue
        if line.startswith('%macro'):
            parts = line.split()
            if len(parts) >= 2:
                params = [p.strip().rstrip(',') for p in parts[2:] if p.strip().rstrip(',')]
                macro_def = (parts[1], params, [])
            continue

        process_line(line, lineno)

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


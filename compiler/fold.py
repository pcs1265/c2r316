"""
Constant folding and copy propagation pass (IR level).

Runs before DCE so that DCE can clean up the resulting dead temps.

Constant folding:
  IBinOp(dst, op, ImmInt(a), ImmInt(b))  →  ICopy(dst, ImmInt(fold(a,b)))
  IBinOp(dst, '+', x, ImmInt(0))         →  ICopy(dst, x)
  IBinOp(dst, '+', ImmInt(0), x)         →  ICopy(dst, x)
  IBinOp(dst, '*', x, ImmInt(1))         →  ICopy(dst, x)
  IBinOp(dst, '*', ImmInt(1), x)         →  ICopy(dst, x)
  IBinOp(dst, '*', _, ImmInt(0))         →  ICopy(dst, ImmInt(0))
  IBinOp(dst, '*', ImmInt(0), _)         →  ICopy(dst, ImmInt(0))
  IBinOp(dst, '-', x, ImmInt(0))         →  ICopy(dst, x)
  IUnaryOp(dst, '-', ImmInt(a))          →  ICopy(dst, ImmInt(-a & 0xFFFF))

Copy propagation:
  When ICopy(tA, src) is the sole def of tA and tA is used exactly once,
  substitute src directly at the use site and drop the ICopy.
  Only propagates ImmInt, StrLabel, Global, and Var (not Temp→Temp to avoid
  increasing register pressure; DCE handles that separately).
"""

from __future__ import annotations
from typing import Dict, List, Optional

from .ir import (
    Temp, Var, Global, ImmInt, StrLabel, Operand,
    IConst, ICopy, IBinOp, IUnaryOp, ILoad, IStore,
    ICall, IRet, ILabel, IJump, IJumpIf, IJumpIfNot,
    IInlineAsm, IVaStart, IVaArg, IRFunction, IRProgram, Instr,
)

_MASK = 0xFFFF


def _fold_binop(op: str, a: int, b: int) -> Optional[int]:
    a &= _MASK
    b &= _MASK
    if op == '+':  return (a + b) & _MASK
    if op == '-':  return (a - b) & _MASK
    if op == '*':  return (a * b) & _MASK
    if op == '&':  return a & b
    if op == '|':  return a | b
    if op == '^':  return a ^ b
    if op == '<<': return (a << (b & 15)) & _MASK
    if op == '>>': return (a >> (b & 15)) & _MASK
    if op == '==': return int(a == b)
    if op == '!=': return int(a != b)
    # Comparisons are signed: reinterpret as two's-complement 16-bit values
    sa = a if a < 0x8000 else a - 0x10000
    sb = b if b < 0x8000 else b - 0x10000
    if op == '<':  return int(sa < sb)
    if op == '>':  return int(sa > sb)
    if op == '<=': return int(sa <= sb)
    if op == '>=': return int(sa >= sb)
    return None


def _simplify_binop(instr: IBinOp) -> Instr:
    """Try to simplify a BinOp; return the simplified instruction or the original."""
    dst, op, left, right = instr.dst, instr.op, instr.left, instr.right
    loc = instr.loc

    # Both sides constant → fold completely
    if isinstance(left, ImmInt) and isinstance(right, ImmInt):
        v = _fold_binop(op, left.value, right.value)
        if v is not None:
            return ICopy(dst, ImmInt(v), loc)

    # Identity / absorbing rules
    if isinstance(right, ImmInt):
        if op == '+' and right.value == 0:
            return ICopy(dst, left, loc)
        if op == '-' and right.value == 0:
            return ICopy(dst, left, loc)
        if op == '*' and right.value == 1:
            return ICopy(dst, left, loc)
        if op == '*' and right.value == 0:
            return ICopy(dst, ImmInt(0), loc)
        if op == '<<' and right.value == 0:
            return ICopy(dst, left, loc)
        if op == '>>' and right.value == 0:
            return ICopy(dst, left, loc)

    if isinstance(left, ImmInt):
        if op == '+' and left.value == 0:
            return ICopy(dst, right, loc)
        if op == '*' and left.value == 1:
            return ICopy(dst, right, loc)
        if op == '*' and left.value == 0:
            return ICopy(dst, ImmInt(0), loc)

    return instr


def _fold_function(fn: IRFunction) -> None:
    """Apply copy propagation then constant folding, repeated until stable."""
    instrs = fn.instrs

    # --- Pass 1: copy propagation for ICopy(t, simple_operand) used once ---
    # Must run before folding so that e.g. t2=0; t3=t1+t2 becomes t3=t1+0 → t3=t1.
    # Count uses of each temp
    use_count: Dict[int, int] = {}
    for instr in instrs:
        for op in instr.uses():
            if isinstance(op, Temp):
                use_count[op.id] = use_count.get(op.id, 0) + 1

    # Count definitions of each temp (to reject temps defined in multiple branches)
    def_count: Dict[int, int] = {}
    for instr in instrs:
        d = instr.defs()
        if isinstance(d, Temp):
            def_count[d.id] = def_count.get(d.id, 0) + 1

    # Map: temp id → (instr_index, propagatable operand)
    # Only propagate if defined exactly once and used exactly once.
    # Scalar sources (ImmInt, StrLabel, Global): safe everywhere.
    # Temp sources: safe everywhere EXCEPT the addr field of IStore/ILoad,
    #   where substituting a Temp would change "store through pointer" into
    #   "store to slot".  _subst_instr handles this via addr_sub vs val_sub.
    copy_src: Dict[int, tuple] = {}
    for i, instr in enumerate(instrs):
        if isinstance(instr, ICopy) and isinstance(instr.dst, Temp):
            tid = instr.dst.id
            if use_count.get(tid, 0) == 1 and def_count.get(tid, 0) == 1:
                src = instr.src
                if isinstance(src, (ImmInt, StrLabel, Global, Temp)):
                    copy_src[tid] = (i, src)

    def _subst_scalar(op: Operand) -> Operand:
        """Substitute scalars (ImmInt/StrLabel/Global) only — safe in addr position."""
        if isinstance(op, Temp) and op.id in copy_src:
            s = copy_src[op.id][1]
            if isinstance(s, (ImmInt, StrLabel, Global)):
                return s
        return op

    def _subst_all(op: Operand) -> Operand:
        """Substitute any copy source — NOT safe in addr position."""
        if isinstance(op, Temp) and op.id in copy_src:
            return copy_src[op.id][1]
        return op

    to_drop = set()
    for i, instr in enumerate(instrs):
        uses = instr.uses()
        if not any(isinstance(op, Temp) and op.id in copy_src for op in uses):
            continue
        new_instr = _subst_instr(instr, _subst_scalar, _subst_all)
        instrs[i] = new_instr
        for op in uses:
            if isinstance(op, Temp) and op.id in copy_src:
                # Only drop the source ICopy if this instruction consumed the temp
                new_uses = new_instr.uses()
                if not any(isinstance(u, Temp) and u.id == op.id for u in new_uses):
                    to_drop.add(copy_src[op.id][0])

    if to_drop:
        fn.instrs = [instr for i, instr in enumerate(instrs) if i not in to_drop]

    # --- Pass 2: constant fold any remaining BinOps/UnaryOps ---
    instrs = fn.instrs
    for i, instr in enumerate(instrs):
        if isinstance(instr, IBinOp):
            instrs[i] = _simplify_binop(instr)
        elif isinstance(instr, IUnaryOp) and instr.op == '-' and isinstance(instr.src, ImmInt):
            instrs[i] = ICopy(instr.dst, ImmInt((-instr.src.value) & _MASK), instr.loc)


def _subst_instr(instr: Instr, addr_sub, val_sub) -> Instr:
    """Return a copy of instr with operands substituted.

    addr_sub: applied to address-position operands (ILoad.addr, IStore.addr)
    val_sub:  applied to all value-position operands

    The distinction matters because a Temp in addr position means "dereference
    this pointer value", while a Var in addr position means "direct slot access".
    Propagating a Temp source into an addr position is safe; propagating a Var
    (or any non-Temp that came from a value-load) is not.
    """
    if isinstance(instr, ICopy):
        return ICopy(instr.dst, val_sub(instr.src), instr.loc)
    if isinstance(instr, IBinOp):
        new = IBinOp(instr.dst, instr.op, val_sub(instr.left), val_sub(instr.right), instr.loc)
        return _simplify_binop(new)
    if isinstance(instr, IUnaryOp):
        return IUnaryOp(instr.dst, instr.op, val_sub(instr.src), instr.loc)
    if isinstance(instr, ILoad):
        return ILoad(instr.dst, addr_sub(instr.addr), instr.loc)
    if isinstance(instr, IStore):
        return IStore(addr_sub(instr.addr), val_sub(instr.src), instr.loc)
    if isinstance(instr, ICall):
        return ICall(instr.dst, val_sub(instr.func), [val_sub(a) for a in instr.args], instr.loc)
    if isinstance(instr, IRet):
        return IRet(val_sub(instr.src) if instr.src else None, instr.loc)
    if isinstance(instr, IJumpIf):
        return IJumpIf(val_sub(instr.cond), instr.target, instr.loc)
    if isinstance(instr, IJumpIfNot):
        return IJumpIfNot(val_sub(instr.cond), instr.target, instr.loc)
    if isinstance(instr, IInlineAsm):
        return IInlineAsm(instr.text, [val_sub(s) for s in instr.srcs], instr.loc)
    if isinstance(instr, IVaArg):
        return IVaArg(instr.dst, val_sub(instr.ap), instr.step, instr.loc)
    return instr


def fold(program: IRProgram) -> IRProgram:
    """Run constant folding + copy propagation on every function until stable."""
    for fn in program.functions:
        prev_len = -1
        while len(fn.instrs) != prev_len:
            prev_len = len(fn.instrs)
            _fold_function(fn)
    return program

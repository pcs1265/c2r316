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
from typing import Dict, List, Optional, Set

from .ir import (
    Temp, Var, Global, ImmInt, StrLabel, Operand,
    IConst, ICopy, IAddrOf, IBinOp, IUnaryOp, ILoad, IStore,
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
    # Unsigned ordering compares: use the masked values directly.
    if op == '<u':  return int(a < b)
    if op == '>=u': return int(a >= b)
    # Signed ordering compares: reinterpret as two's-complement 16-bit values.
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

    # Identity / absorbing rules — right-hand constant
    if isinstance(right, ImmInt):
        rv = right.value & _MASK
        if op == '+' and rv == 0:                 return ICopy(dst, left, loc)
        if op == '-' and rv == 0:                 return ICopy(dst, left, loc)
        if op == '*' and rv == 1:                 return ICopy(dst, left, loc)
        if op == '*' and rv == 0:                 return ICopy(dst, ImmInt(0), loc)
        if op == '<<' and rv == 0:                return ICopy(dst, left, loc)
        if op == '>>' and rv == 0:                return ICopy(dst, left, loc)
        if op == '&' and rv == 0:                 return ICopy(dst, ImmInt(0), loc)
        if op == '&' and rv == _MASK:             return ICopy(dst, left, loc)
        if op == '|' and rv == 0:                 return ICopy(dst, left, loc)
        if op == '|' and rv == _MASK:             return ICopy(dst, ImmInt(_MASK), loc)
        if op == '^' and rv == 0:                 return ICopy(dst, left, loc)
        # Strength reduction: x * 2^n → x << n  (works for both signed and unsigned)
        if op == '*' and rv > 0 and (rv & (rv - 1)) == 0:
            n = rv.bit_length() - 1
            return IBinOp(dst, '<<', left, ImmInt(n), loc)
        # Strength reduction for unsigned modulo: x % 2^n → x & (2^n - 1)
        # Note: This is only valid for unsigned modulo. Signed modulo needs
        # special handling for negative numbers. We conservatively apply this
        # only when the right operand is a power of 2.
        # The '%' operator in our IR represents unsigned modulo ('%u').
        if op == '%' and rv > 0 and (rv & (rv - 1)) == 0:
            mask = rv - 1
            return IBinOp(dst, '&', left, ImmInt(mask), loc)

    # Identity / absorbing rules — left-hand constant
    if isinstance(left, ImmInt):
        lv = left.value & _MASK
        if op == '+' and lv == 0:                 return ICopy(dst, right, loc)
        if op == '*' and lv == 1:                 return ICopy(dst, right, loc)
        if op == '*' and lv == 0:                 return ICopy(dst, ImmInt(0), loc)
        if op == '&' and lv == 0:                 return ICopy(dst, ImmInt(0), loc)
        if op == '&' and lv == _MASK:             return ICopy(dst, right, loc)
        if op == '|' and lv == 0:                 return ICopy(dst, right, loc)
        if op == '|' and lv == _MASK:             return ICopy(dst, ImmInt(_MASK), loc)
        if op == '^' and lv == 0:                 return ICopy(dst, right, loc)
        # 0 - x  →  -x  (express as 0 ^ ... is not equivalent; leave as-is unless negation IR exists)
        if op == '*' and lv > 0 and (lv & (lv - 1)) == 0:
            n = lv.bit_length() - 1
            return IBinOp(dst, '<<', right, ImmInt(n), loc)

    # Self-operations on identical Temps (post copy-propagation: same SSA temp).
    # Note: only safe if neither operand has observable side effects — Temps satisfy
    # this by construction (pure SSA values).  Vars/Globals could change between
    # reads if there's a call in between, so restrict to Temps.
    if isinstance(left, Temp) and isinstance(right, Temp) and left.id == right.id:
        if op == '-':                             return ICopy(dst, ImmInt(0), loc)
        if op == '^':                             return ICopy(dst, ImmInt(0), loc)
        if op == '&':                             return ICopy(dst, left, loc)
        if op == '|':                             return ICopy(dst, left, loc)
        if op in ('==', '<=', '>=', '>=u'):       return ICopy(dst, ImmInt(1), loc)
        if op in ('!=', '<',  '>',  '<u'):        return ICopy(dst, ImmInt(0), loc)

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
    # Var sources: safe in value position only (addr_sub excludes them), AND only
    #   when no clobbering instruction (store to same var, call, or label) lies
    #   between the ICopy definition and its single use site.
    copy_src: Dict[int, tuple] = {}
    for i, instr in enumerate(instrs):
        if isinstance(instr, ICopy) and isinstance(instr.dst, Temp):
            tid = instr.dst.id
            if use_count.get(tid, 0) == 1 and def_count.get(tid, 0) == 1:
                src = instr.src
                if isinstance(src, (ImmInt, StrLabel, Global, Temp, Var)):
                    copy_src[tid] = (i, src)

    # Validate Var-source entries: remove any where the variable is clobbered
    # between the definition and the single use (by a store, call, or label).
    var_entries = [(tid, def_idx, src) for tid, (def_idx, src) in copy_src.items()
                   if isinstance(src, Var)]
    if var_entries:
        use_loc: Dict[int, int] = {}
        for i, instr in enumerate(instrs):
            for op in instr.uses():
                if isinstance(op, Temp) and op.id in copy_src:
                    if isinstance(copy_src[op.id][1], Var):
                        use_loc.setdefault(op.id, i)
        for tid, def_idx, var_src in var_entries:
            use_idx = use_loc.get(tid, -1)
            if use_idx < 0:
                del copy_src[tid]
                continue
            clobbered = False
            for j in range(def_idx + 1, use_idx):
                chk = instrs[j]
                if isinstance(chk, (ILabel, ICall)):
                    clobbered = True; break
                if isinstance(chk, IStore) and isinstance(chk.addr, Var) \
                        and chk.addr.name == var_src.name:
                    clobbered = True; break
            if clobbered:
                del copy_src[tid]

    # Remove Temp-source entries whose source Temp is itself a key in copy_src.
    # If t0→Var/Temp(x) and t4→Temp(t0) are both candidates, processing t4's
    # substitution drops t0's ICopy and then any later instruction that still
    # references t4 (resolved to stale t0) will find t0 undefined.
    # Resolution: remove the chained entry (t4→t0) from copy_src; the next
    # _fold_function iteration will propagate it cleanly.
    # This also subsumes the old Var-source-only guard.
    all_copy_keys = set(copy_src.keys())
    for tid in [tid for tid, (_, src) in copy_src.items()
                if isinstance(src, Temp) and src.id in all_copy_keys]:
        del copy_src[tid]

    def _subst_addr(op: Operand) -> Operand:
        """Substitute in address position: safe for ImmInt/StrLabel/Global/Temp.
        Var is NOT safe in addr position (would change pointer-deref to slot access)."""
        if isinstance(op, Temp) and op.id in copy_src:
            s = copy_src[op.id][1]
            if isinstance(s, (ImmInt, StrLabel, Global, Temp)):
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
        new_instr = _subst_instr(instr, _subst_addr, _subst_all)
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
        elif isinstance(instr, IUnaryOp) and isinstance(instr.src, ImmInt):
            v = instr.src.value & _MASK
            if instr.op == '-':
                instrs[i] = ICopy(instr.dst, ImmInt((-v) & _MASK), instr.loc)
            elif instr.op == '~':
                instrs[i] = ICopy(instr.dst, ImmInt((~v) & _MASK), instr.loc)


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


def _addrof_cse(fn: IRFunction) -> None:
    """Deduplicate IAddrOf within a basic block.

    If IAddrOf(tA, x) is followed by IAddrOf(tB, x) with no intervening label,
    replace the second with ICopy(tB, tA).  The existing copy-propagation pass
    then folds the chain away, eliminating the redundant address computation.
    """
    available: Dict[object, Temp] = {}  # var-key → Temp holding &var
    for i, instr in enumerate(fn.instrs):
        if isinstance(instr, ILabel):
            available.clear()
            continue
        if isinstance(instr, IAddrOf):
            key = instr.var  # Var or Global — both frozen dataclasses, hashable
            if key in available:
                fn.instrs[i] = ICopy(instr.dst, available[key], instr.loc)
            else:
                available[key] = instr.dst


def _dead_store_elim(fn: IRFunction) -> None:
    """Remove IStore(Var('x'), _) that is overwritten before x is read again.

    Conservative: only eliminates stores to locals whose address is never taken
    (escaped vars bypass DSE because pointer writes are untracked).  Invalidates
    on ICall and ILabel (control-flow merge).
    """
    escaped: set = set()
    for instr in fn.instrs:
        if isinstance(instr, IAddrOf) and isinstance(instr.var, Var):
            escaped.add(instr.var.name)

    last_store: Dict[str, int] = {}  # var_name → index of pending dead store
    to_remove: set = set()

    for i, instr in enumerate(fn.instrs):
        if isinstance(instr, (ILabel, IJump, IJumpIf, IJumpIfNot)):
            last_store.clear()
            continue
        if isinstance(instr, ICall):
            last_store.clear()
            continue
        if isinstance(instr, IStore) and isinstance(instr.addr, Var):
            name = instr.addr.name
            # The value being stored might itself read a var — flush those first.
            if isinstance(instr.src, Var):
                last_store.pop(instr.src.name, None)
            if name not in escaped:
                if name in last_store:
                    to_remove.add(last_store[name])
                last_store[name] = i
            continue
        # Any instruction that reads a Var keeps its pending store alive.
        for op in instr.uses():
            if isinstance(op, Var):
                last_store.pop(op.name, None)

    if to_remove:
        fn.instrs = [instr for i, instr in enumerate(fn.instrs) if i not in to_remove]


def _remove_trivial_jumps(fn: IRFunction) -> None:
    """Remove IJump(L) where the next non-label instruction is ILabel(L)."""
    instrs = fn.instrs
    changed = True
    while changed:
        changed = False
        new = []
        i = 0
        while i < len(instrs):
            instr = instrs[i]
            if isinstance(instr, IJump):
                # find the next label, skipping no instructions in between
                j = i + 1
                while j < len(instrs) and isinstance(instrs[j], ILabel):
                    if instrs[j].name == instr.target:
                        break
                    j += 1
                else:
                    j = len(instrs)   # didn't find it immediately
                # only remove if target label is the very next instruction
                if i + 1 < len(instrs) and isinstance(instrs[i + 1], ILabel) and instrs[i + 1].name == instr.target:
                    changed = True
                    i += 1
                    continue
            new.append(instr)
            i += 1
        fn.instrs = new
        instrs = fn.instrs


def _branch_threading(fn: IRFunction) -> None:
    """Thread branches: if a jump target is itself a jump, retarget to the final destination.

    Transforms:
        jmp L1      →  jmp L2
        ...
    L1: jmp L2
    L2: ...

    Also handles conditional branches:
        jz L1       →  jz L2
        ...
    L1: jmp L2

    This reduces the depth of jump chains.
    """
    instrs = fn.instrs

    # Build a map: label → (instruction_index, instruction)
    label_map: Dict[str, int] = {}
    for i, instr in enumerate(instrs):
        if isinstance(instr, ILabel):
            label_map[instr.name] = i

    # Build jump chain map: label → final_target
    # A label maps to another label if the first non-label instruction after it is a jump
    jump_chain: Dict[str, str] = {}
    for lbl, idx in label_map.items():
        j = idx + 1
        # Skip additional labels
        while j < len(instrs) and isinstance(instrs[j], ILabel):
            j += 1
        if j < len(instrs) and isinstance(instrs[j], IJump):
            # This label leads directly to another jump
            target = instrs[j].target
            jump_chain[lbl] = target

    # Resolve jump chains to their final targets (follow the chain)
    def resolve_target(target: str, visited: set = None) -> str:
        if visited is None:
            visited = set()
        if target in visited:
            return target  # cycle detected
        visited.add(target)
        if target in jump_chain:
            return resolve_target(jump_chain[target], visited)
        return target

    # Apply threading to all jumps
    changed = False
    for i, instr in enumerate(instrs):
        if isinstance(instr, IJump):
            final = resolve_target(instr.target)
            if final != instr.target:
                instrs[i] = IJump(final, instr.loc)
                changed = True
        elif isinstance(instr, IJumpIf):
            final = resolve_target(instr.target)
            if final != instr.target:
                instrs[i] = IJumpIf(instr.cond, final, instr.loc)
                changed = True
        elif isinstance(instr, IJumpIfNot):
            final = resolve_target(instr.target)
            if final != instr.target:
                instrs[i] = IJumpIfNot(instr.cond, final, instr.loc)
                changed = True

    # If we changed anything, remove unreachable labels
    if changed:
        # Find all labels that are still referenced
        used_labels: Set[str] = set()
        for instr in instrs:
            if isinstance(instr, IJump):
                used_labels.add(instr.target)
            elif isinstance(instr, IJumpIf):
                used_labels.add(instr.target)
            elif isinstance(instr, IJumpIfNot):
                used_labels.add(instr.target)

        # Remove labels that are no longer referenced
        fn.instrs = [instr for instr in instrs
                     if not isinstance(instr, ILabel) or instr.name in used_labels]


def _var_load_cse(fn: IRFunction) -> None:
    """Replace redundant Var loads within a basic block.

    When ICopy(tA, Var('x')) is followed by ICopy(tB, Var('x')) with no
    intervening store to x, call, or label (control-flow boundary), replace
    the second copy with ICopy(tB, tA).  The existing copy-propagation pass
    then folds the tA→tB chain away, eliminating the redundant load entirely.

    Invalidation rules (conservative):
      - IStore(Var('x'), _)  — direct write to the variable
      - ICall                — may modify globals / any var
      - ILabel               — control-flow merge; prior value may not dominate
    """
    # var_name → Temp that currently holds its value
    available: Dict[str, Temp] = {}
    instrs = fn.instrs
    for i, instr in enumerate(instrs):
        if isinstance(instr, ILabel):
            available.clear()
            continue
        if isinstance(instr, ICall):
            available.clear()
            continue
        if isinstance(instr, IStore) and isinstance(instr.addr, Var):
            available.pop(instr.addr.name, None)
            continue
        if isinstance(instr, ICopy) and isinstance(instr.dst, Temp):
            src = instr.src
            if isinstance(src, Var):
                name = src.name
                if name in available:
                    # Replace with copy from the already-loaded temp
                    instrs[i] = ICopy(instr.dst, available[name], instr.loc)
                else:
                    available[name] = instr.dst
            elif isinstance(src, Temp):
                # Track that dst now holds the same value as any var src held
                for vname, t in list(available.items()):
                    if t == src:
                        available[vname] = instr.dst


def _tail_call_opt(fn: IRFunction) -> None:
    """Convert tail calls (call followed by return) into jumps.
    
    DISABLED for now - requires careful handling of:
    - Argument register preservation across callee-saved restore
    - Stack argument area management
    - Proper frame deallocation ordering
    
    TODO: Re-enable after fixing these issues.
    """
    pass


def fold(program: IRProgram) -> IRProgram:
    """Run constant folding + copy propagation on every function until stable."""
    for fn in program.functions:
        _var_load_cse(fn)
        _addrof_cse(fn)
        _dead_store_elim(fn)
        prev_len = -1
        while len(fn.instrs) != prev_len:
            prev_len = len(fn.instrs)
            _fold_function(fn)
        _remove_trivial_jumps(fn)
        _branch_threading(fn)
        _tail_call_opt(fn)
    return program

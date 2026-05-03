"""
Dead Code Elimination pass (IR level).

Algorithm: mark–sweep on Temps within each function.
  1. Seed the live set with every Temp that appears in a "root" instruction
     (one with observable side effects or control flow).
  2. Walk backwards through the instruction list; whenever a def'd Temp is
     live, mark all Temps it uses as live too.
  3. Remove any instruction whose only effect is defining a dead Temp.

Instructions always kept regardless of liveness:
  ILabel, IJump, IJumpIf, IJumpIfNot — control flow
  IStore, ICall (void dst), IInlineAsm  — side effects
  IRet                                   — function exit
  IVaArg                                 — advances the va_list pointer (side effect)
  IVaStart                               — only produces a Temp; safe to DCE if unused
"""

from __future__ import annotations
from collections import deque
from typing import Dict, List, Set

from .ir import (
    Temp, Var, Global,
    IConst, ICopy, IAddrOf, IBinOp, IUnaryOp,
    ILoad, IStore, ICall, IRet,
    ILabel, IJump, IJumpIf, IJumpIfNot,
    IInlineAsm, IVaStart, IVaArg,
    ILongStore, ILongRet, ILongCall,
    IRFunction, IRProgram, iter_defs,
)


def _always_keep(instr) -> bool:
    """Return True for instructions that must be preserved regardless of liveness."""
    if isinstance(instr, (ILabel, IJump, IJumpIf, IJumpIfNot, IStore, IRet,
                          ILongStore, ILongRet, IInlineAsm)):
        return True
    if isinstance(instr, ICall) and instr.dst is None:
        return True
    if isinstance(instr, ILongCall) and instr.dst_lo is None:
        return True
    if isinstance(instr, IVaArg):
        return True
    return False


def dce_function(fn: IRFunction) -> None:
    """Run DCE in-place on a single IRFunction."""
    instrs = fn.instrs

    # Build def→instruction indices map.  After inlining a function with
    # multiple return paths the same temp (result_dst) may have several
    # defining instructions, so we collect ALL of them.
    def_instrs: Dict[int, List[int]] = {}
    for i, instr in enumerate(instrs):
        for d in iter_defs(instr):
            def_instrs.setdefault(d.id, []).append(i)

    # --- pass 1: seed worklist from roots ---
    live: Set[int] = set()   # set of Temp ids
    worklist: deque = deque()

    def _mark(op):
        if isinstance(op, Temp) and op.id not in live:
            live.add(op.id)
            worklist.append(op.id)

    for instr in instrs:
        if _always_keep(instr) or isinstance(instr, (ICall, ILongCall)):
            for op in instr.uses():
                _mark(op)

    # --- pass 2: backward propagation via worklist (O(N)) ---
    while worklist:
        tid = worklist.popleft()
        for idx in def_instrs.get(tid, ()):
            for op in instrs[idx].uses():
                _mark(op)

    # --- pass 3: remove dead definitions ---
    kept = []
    for instr in instrs:
        if _always_keep(instr):
            kept.append(instr)
            continue
        if isinstance(instr, ICall):
            if instr.dst is not None and instr.dst.id not in live:
                instr.dst = None
            kept.append(instr)
            continue
        if isinstance(instr, ILongCall):
            if instr.dst_lo is not None and instr.dst_lo.id not in live and instr.dst_hi.id not in live:
                instr.dst_lo = None
                instr.dst_hi = None
            kept.append(instr)
            continue
        defs = iter_defs(instr)
        if defs and all(d.id not in live for d in defs):
            continue  # dead — drop
        kept.append(instr)

    fn.instrs = kept


def _reachable_functions(program: IRProgram, roots: set) -> set:
    """Return the set of function names reachable from roots via call graph."""
    func_instrs = {fn.name: fn.instrs for fn in program.functions}
    reachable = set()
    worklist = list(roots)
    while worklist:
        name = worklist.pop()
        if name in reachable:
            continue
        reachable.add(name)
        for instr in func_instrs.get(name, []):
            if isinstance(instr, (ICall, ILongCall)) and isinstance(instr.func, Global):
                callee = instr.func.name
                if callee not in reachable:
                    worklist.append(callee)
            # IAddrOf(t, Global('fn')) keeps function pointer targets alive
            if isinstance(instr, IAddrOf) and isinstance(instr.var, Global):
                callee = instr.var.name
                if callee in func_instrs and callee not in reachable:
                    worklist.append(callee)
    return reachable


def eliminate_dead_functions(program: IRProgram, entry: str = 'main') -> IRProgram:
    """Remove functions never reachable from entry. Mutates and returns the program."""
    func_names = {fn.name for fn in program.functions}
    roots = {entry}
    reachable = _reachable_functions(program, roots)
    program.functions = [fn for fn in program.functions if fn.name in reachable]
    return program


def verify_temps(program: IRProgram) -> None:
    """Assert every Temp used in each function is also defined in that function.
    Raises AssertionError on violation — meant to catch compiler bugs early."""
    for fn in program.functions:
        defs: Set[int] = set()
        for instr in fn.instrs:
            for d in iter_defs(instr):
                defs.add(d.id)
        for instr in fn.instrs:
            for op in instr.uses():
                if isinstance(op, Temp) and op.id not in defs:
                    raise AssertionError(
                        f"[verify] {fn.name}: t{op.id} used but never defined\n"
                        f"  in: {instr}"
                    )


def _eliminate_dead_args(program: IRProgram) -> None:
    """Remove parameters that are never read inside their function.

    Only safe for functions not reachable via a function pointer (address-taken
    functions have unknown call sites, so we cannot rewrite their signatures).

    For each eligible function, we:
      1. Find params that are never accessed (no Var(name) in any instruction's
         uses(), and no IAddrOf(t, Var(name)) in the body).
      2. Remove those params from fn.params.
      3. Remove the corresponding argument from every ICall that names the function.
    """
    func_names = {fn.name for fn in program.functions}

    # Collect address-taken functions (ineligible for signature changes)
    address_taken: Set[str] = set()
    for fn in program.functions:
        for instr in fn.instrs:
            if isinstance(instr, IAddrOf) and isinstance(instr.var, Global):
                if instr.var.name in func_names:
                    address_taken.add(instr.var.name)

    changed = True
    while changed:
        changed = False
        for fn in program.functions:
            if fn.name in address_taken:
                continue
            if not fn.params:
                continue
            if fn.is_variadic:
                continue

            # Find which params are actually accessed (read or address-taken)
            accessed: Set[str] = set()
            param_set = set(fn.params)
            for instr in fn.instrs:
                for op in instr.uses():
                    if isinstance(op, Var) and op.name in param_set:
                        accessed.add(op.name)
                # ICall.func is Var when calling via a local function-pointer param;
                # uses() excludes non-Temp func operands, so check it explicitly.
                if isinstance(instr, ICall) and isinstance(instr.func, Var):
                    if instr.func.name in param_set:
                        accessed.add(instr.func.name)
                if isinstance(instr, IAddrOf) and isinstance(instr.var, Var):
                    if instr.var.name in param_set:
                        accessed.add(instr.var.name)

            dead_params = [p for p in fn.params if p not in accessed]
            if not dead_params:
                continue

            # Compute index map: old_index → keep?
            dead_set = set(dead_params)
            keep_mask = [p not in dead_set for p in fn.params]

            # Update function signature
            fn.params = [p for p, keep in zip(fn.params, keep_mask) if keep]

            # Update all call sites in the whole program
            for caller in program.functions:
                for i, instr in enumerate(caller.instrs):
                    if isinstance(instr, ICall) and isinstance(instr.func, Global):
                        if instr.func.name == fn.name:
                            new_args = [a for a, keep in zip(instr.args, keep_mask) if keep]
                            caller.instrs[i] = ICall(instr.dst, instr.func, new_args, instr.loc)

            changed = True


def dce(program: IRProgram, entry: str = 'main') -> IRProgram:
    """Run dead function elimination then per-function DCE."""
    eliminate_dead_functions(program, entry)
    _eliminate_dead_args(program)
    for fn in program.functions:
        dce_function(fn)
    verify_temps(program)
    return program

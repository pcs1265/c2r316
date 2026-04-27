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
    Temp, Global,
    IConst, ICopy, IAddrOf, IBinOp, IUnaryOp,
    ILoad, IStore, ICall, IRet,
    ILabel, IJump, IJumpIf, IJumpIfNot,
    IInlineAsm, IVaStart, IVaArg,
    IRFunction, IRProgram,
)


def _always_keep(instr) -> bool:
    """Return True for instructions that must be preserved regardless of liveness."""
    if isinstance(instr, (ILabel, IJump, IJumpIf, IJumpIfNot, IStore, IRet, IInlineAsm)):
        return True
    if isinstance(instr, ICall) and instr.dst is None:
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
        d = instr.defs()
        if isinstance(d, Temp):
            def_instrs.setdefault(d.id, []).append(i)

    # --- pass 1: seed worklist from roots ---
    live: Set[int] = set()   # set of Temp ids
    worklist: deque = deque()

    def _mark(op):
        if isinstance(op, Temp) and op.id not in live:
            live.add(op.id)
            worklist.append(op.id)

    for instr in instrs:
        if _always_keep(instr) or isinstance(instr, ICall):
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
        d = instr.defs()
        if isinstance(d, Temp) and d.id not in live:
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
            if isinstance(instr, ICall) and isinstance(instr.func, Global):
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
            d = instr.defs()
            if isinstance(d, Temp):
                defs.add(d.id)
        for instr in fn.instrs:
            for op in instr.uses():
                if isinstance(op, Temp) and op.id not in defs:
                    raise AssertionError(
                        f"[verify] {fn.name}: t{op.id} used but never defined\n"
                        f"  in: {instr}"
                    )


def dce(program: IRProgram, entry: str = 'main') -> IRProgram:
    """Run dead function elimination then per-function DCE."""
    eliminate_dead_functions(program, entry)
    for fn in program.functions:
        dce_function(fn)
    verify_temps(program)
    return program

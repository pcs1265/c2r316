"""
IR Inliner pass.

Inlines calls to eligible static functions at their call sites.

Eligibility:
  - Function is static (is_static=True) or always_inline (is_always_inline=True)
  - Not variadic
  - Not recursive (direct or mutual)
  - Instruction count <= INLINE_THRESHOLD, OR is_always_inline=True

Algorithm:
  For each ICall to an eligible callee, replace the call instruction with:
    1. ICopy of each argument into a fresh Temp (acting as the param).
    2. A renamed copy of the callee's instructions, with:
       - All Temp IDs offset by the caller's current max temp ID.
       - All Var(param_name) references replaced by the corresponding arg temp.
       - All ILabel names suffixed with a unique call-site counter.
       - All IJump/IJumpIf/IJumpIfNot targets updated to match.
       - Each IRet replaced by: ICopy(dst, ret_val) if dst != None, then IJump to exit label.
    3. An ILabel for the exit point.

Inline order: process callees before callers (topological), so that already-inlined
callees don't appear in the call graph check.
"""

from __future__ import annotations
import copy
from typing import Dict, List, Optional, Set

from .ir import (
    Temp, Var, Global, ImmInt, StrLabel, Operand,
    IConst, ICopy, IAddrOf, IBinOp, IUnaryOp, ILoad, IStore,
    ICall, IRet, ILabel, IJump, IJumpIf, IJumpIfNot,
    IInlineAsm, IVaStart, IVaArg, IRFunction, IRProgram, Instr,
)

INLINE_THRESHOLD = 5     # max IR instructions to inline automatically (only trivial getters/setters)


def _max_temp_id(instrs: List[Instr]) -> int:
    """Return the highest Temp ID used in instrs, or -1 if none."""
    hi = -1
    for instr in instrs:
        d = instr.defs()
        if isinstance(d, Temp) and d.id > hi:
            hi = d.id
        for op in instr.uses():
            if isinstance(op, Temp) and op.id > hi:
                hi = op.id
    return hi


def _rename_operand(op: Operand, temp_offset: int, param_map: Dict[str, Operand]) -> Operand:
    if isinstance(op, Temp):
        return Temp(op.id + temp_offset)
    if isinstance(op, Var) and op.name in param_map:
        return param_map[op.name]
    return op


def _rename_label(name: str, suffix: str) -> str:
    return name + suffix


def _clone_instrs(
    instrs: List[Instr],
    temp_offset: int,
    param_map: Dict[str, Operand],
    label_suffix: str,
    result_dst: Optional[Temp],
    exit_label: str,
    loc,
) -> List[Instr]:
    """
    Return a renamed copy of callee instrs with IRet replaced by
    copy-to-result + jump-to-exit.
    """
    # resolved: temp_id → simple operand (ImmInt/StrLabel/Global), for
    # eliminating trivial copy chains inside the cloned body.
    resolved: Dict[int, Operand] = {}

    def _ro(op: Operand) -> Operand:
        op = _rename_operand(op, temp_offset, param_map)
        if isinstance(op, Temp) and op.id in resolved:
            return resolved[op.id]
        return op

    def _rl(name):
        return _rename_label(name, label_suffix)

    out = []
    for instr in instrs:
        if isinstance(instr, IRet):
            if result_dst is not None and instr.src is not None:
                out.append(ICopy(result_dst, _ro(instr.src), instr.loc or loc))
            out.append(IJump(exit_label, instr.loc or loc))

        elif isinstance(instr, ILabel):
            out.append(ILabel(_rl(instr.name), instr.loc))

        elif isinstance(instr, IJump):
            out.append(IJump(_rl(instr.target), instr.loc))

        elif isinstance(instr, IJumpIf):
            out.append(IJumpIf(_ro(instr.cond), _rl(instr.target), instr.loc))

        elif isinstance(instr, IJumpIfNot):
            out.append(IJumpIfNot(_ro(instr.cond), _rl(instr.target), instr.loc))

        elif isinstance(instr, ICopy):
            new_dst = Temp(instr.dst.id + temp_offset)
            new_src = _ro(instr.src)
            # Always record the resolved value so subsequent _ro() calls in
            # this clone see the final source directly (no multi-level chains).
            # For non-Temp sources, skip emitting the copy (it would be dead).
            # For Temp sources, still emit the copy so there is a concrete
            # definition in the IR — fold/DCE will remove it if unused.
            resolved[new_dst.id] = new_src
            if not isinstance(new_src, (ImmInt, StrLabel, Global)):
                out.append(ICopy(new_dst, new_src, instr.loc))

        elif isinstance(instr, IConst):
            out.append(IConst(Temp(instr.dst.id + temp_offset), instr.value, instr.loc))

        elif isinstance(instr, IAddrOf):
            new_var = instr.var
            if isinstance(new_var, Var) and new_var.name in param_map:
                # address of a param — can't really happen safely; skip rename
                new_var = new_var
            out.append(IAddrOf(Temp(instr.dst.id + temp_offset), new_var, instr.loc))

        elif isinstance(instr, IBinOp):
            out.append(IBinOp(
                Temp(instr.dst.id + temp_offset),
                instr.op, _ro(instr.left), _ro(instr.right), instr.loc,
            ))

        elif isinstance(instr, IUnaryOp):
            out.append(IUnaryOp(
                Temp(instr.dst.id + temp_offset),
                instr.op, _ro(instr.src), instr.loc,
            ))

        elif isinstance(instr, ILoad):
            out.append(ILoad(Temp(instr.dst.id + temp_offset), _ro(instr.addr), instr.loc))

        elif isinstance(instr, IStore):
            out.append(IStore(_ro(instr.addr), _ro(instr.src), instr.loc))

        elif isinstance(instr, ICall):
            new_args = [_ro(a) for a in instr.args]
            new_dst = Temp(instr.dst.id + temp_offset) if instr.dst is not None else None
            out.append(ICall(new_dst, instr.func, new_args, instr.loc))

        elif isinstance(instr, IInlineAsm):
            # Rename any local labels (words starting with '.') in the asm
            # template so they get a unique suffix at each inline site.
            import re
            renamed_text = re.sub(
                r'(?<!\w)(\.[A-Za-z_][A-Za-z0-9_]*)',
                lambda m: _rl(m.group(1)),
                instr.text,
            )
            out.append(IInlineAsm(renamed_text, [_ro(s) for s in instr.srcs], instr.loc))

        elif isinstance(instr, IVaStart):
            out.append(IVaStart(Temp(instr.dst.id + temp_offset), instr.num_fixed, instr.loc))

        elif isinstance(instr, IVaArg):
            out.append(IVaArg(Temp(instr.dst.id + temp_offset), _ro(instr.ap), instr.step, instr.loc))

        else:
            out.append(copy.copy(instr))

    return out


def _build_call_graph(program: IRProgram) -> Dict[str, Set[str]]:
    """Return {caller_name: {callee_names}} for direct calls only."""
    graph: Dict[str, Set[str]] = {}
    for fn in program.functions:
        callees: Set[str] = set()
        for instr in fn.instrs:
            if isinstance(instr, ICall) and isinstance(instr.func, Global):
                callees.add(instr.func.name)
        graph[fn.name] = callees
    return graph


def _recursive_set(call_graph: Dict[str, Set[str]]) -> Set[str]:
    """Return names of functions involved in any cycle (direct or mutual recursion)."""
    recursive: Set[str] = set()
    all_names = set(call_graph.keys())

    def _reachable(start: str, visited: Set[str]) -> Set[str]:
        out: Set[str] = set()
        stack = [start]
        while stack:
            n = stack.pop()
            if n in out:
                continue
            out.add(n)
            for callee in call_graph.get(n, ()):
                if callee not in out:
                    stack.append(callee)
        return out

    for name in all_names:
        if name in _reachable(name, set()) - {name}:
            recursive.add(name)
        # also mark if it reaches itself
        if name in call_graph.get(name, ()):
            recursive.add(name)

    # simpler: any function that can reach itself
    for name in all_names:
        reachable = _reachable(name, set())
        if name in call_graph.get(name, ()):
            recursive.add(name)
        # mutual: if any callee can reach back to name
        for callee in call_graph.get(name, ()):
            if name in _reachable(callee, set()):
                recursive.add(name)
                recursive.add(callee)

    return recursive


def _inline_calls_in_function(
    caller: IRFunction,
    inlineable: Dict[str, IRFunction],
    call_counter: list,   # mutable counter [int]
) -> bool:
    """Inline one round of calls in caller. Returns True if anything was inlined."""
    changed = False
    new_instrs: List[Instr] = []
    # Pre-compute the max temp ID across the entire caller so that each inline
    # site gets a fresh offset above all existing temps, not just those seen so far.
    global_max = _max_temp_id(caller.instrs)

    for instr in caller.instrs:
        if not (isinstance(instr, ICall) and isinstance(instr.func, Global)):
            new_instrs.append(instr)
            continue

        callee_name = instr.func.name
        callee = inlineable.get(callee_name)
        if callee is None:
            new_instrs.append(instr)
            continue

        # Inline it
        changed = True
        call_counter[0] += 1
        suffix = f'__i{call_counter[0]}'
        exit_label = f'._inline_exit{call_counter[0]}'

        # Allocate fresh temps above all existing IDs (original + prior inlines).
        temp_offset = global_max + 1

        # Map param names → operand holding each arg value.
        # Simple args (ImmInt, StrLabel, Global) map directly — no copy needed.
        # Temp/Var args get a fresh temp copy to avoid aliasing issues if the
        # callee modifies the param slot.
        param_map: Dict[str, Operand] = {}
        arg_temp_count = 0
        for i, param_name in enumerate(callee.params):
            arg_val = instr.args[i] if i < len(instr.args) else ImmInt(0)
            if isinstance(arg_val, (ImmInt, StrLabel, Global)):
                param_map[param_name] = arg_val   # use directly, no copy
            else:
                t = Temp(temp_offset + arg_temp_count)
                new_instrs.append(ICopy(t, arg_val, instr.loc))
                param_map[param_name] = t
                arg_temp_count += 1

        body_temp_offset = temp_offset + arg_temp_count
        # Advance global_max past all temps this inline will use.
        global_max = body_temp_offset + _max_temp_id(callee.instrs) + 1

        # result dst: use instr.dst if caller expects a value
        result_dst = instr.dst  # already a Temp in caller's namespace

        cloned = _clone_instrs(
            callee.instrs,
            temp_offset=body_temp_offset,
            param_map=param_map,
            label_suffix=suffix,
            result_dst=result_dst,
            exit_label=exit_label,
            loc=instr.loc,
        )
        new_instrs.extend(cloned)
        new_instrs.append(ILabel(exit_label, instr.loc))

        # Merge callee local_sizes into caller (with suffix to avoid collision)
        for local_name, size in callee.local_sizes.items():
            caller.local_sizes[local_name + suffix] = size

    caller.instrs = new_instrs
    return changed


def inline(program: IRProgram) -> IRProgram:
    """Run inlining pass on the program. Mutates and returns the program."""
    func_map: Dict[str, IRFunction] = {fn.name: fn for fn in program.functions}

    call_graph = _build_call_graph(program)
    recursive = _recursive_set(call_graph)

    # Build the inlineable set
    inlineable: Dict[str, IRFunction] = {}
    for fn in program.functions:
        if fn.name in recursive:
            continue
        if fn.is_variadic:
            continue
        if fn.is_always_inline:
            inlineable[fn.name] = fn
            continue
        if fn.is_static and not fn.name.startswith('__') and len(fn.instrs) <= INLINE_THRESHOLD:
            inlineable[fn.name] = fn

    if not inlineable:
        return program

    # Two-phase approach:
    # Phase 1: repeatedly inline always_inline callees within the inlineable set
    #          until stable, fully collapsing chains of arbitrary depth.
    # Phase 2: inline into non-inlineable callers exactly once, using the
    #          post-phase-1 bodies. Re-check threshold after phase 1 to avoid
    #          inlining functions that grew beyond INLINE_THRESHOLD due to phase 1.
    call_counter = [0]

    # Phase 1: resolve always_inline chains inside the inlineable set until stable.
    # Runs repeatedly so arbitrarily deep always_inline chains fully collapse.
    always_inline_only = {n: fn for n, fn in inlineable.items() if fn.is_always_inline}
    while True:
        changed = any(
            _inline_calls_in_function(fn, always_inline_only, call_counter)
            for fn in list(inlineable.values())
        )
        if not changed:
            break

    # Phase 2: rebuild threshold check with post-phase-1 sizes, then inline once.
    final_inlineable: Dict[str, IRFunction] = {}
    for name, fn in inlineable.items():
        if fn.is_always_inline or len(fn.instrs) <= INLINE_THRESHOLD:
            final_inlineable[name] = fn

    for fn in program.functions:
        if fn.name not in final_inlineable:
            _inline_calls_in_function(fn, final_inlineable, call_counter)

    return program

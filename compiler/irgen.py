"""
C to R316 Compiler - IR Generator
AST → Three-Address IR

Assumes semantic analysis has already run (ctype / _sym attached to nodes).
"""

from __future__ import annotations
from typing import Optional, List

from .ast_nodes import *
from .ir import (
    Temp, Var, Global, ImmInt, StrLabel, Operand,
    IConst, ICopy, IAddrOf, IBinOp, IUnaryOp, ILoad, IStore,
    ICall, IRet, ILabel, IJump, IJumpIf, IJumpIfNot,
    IInlineAsm, IVaStart, IVaArg, IRFunction, IRProgram,
)


class IRGenError(Exception):
    pass


class IRGen:
    def __init__(self, filename: str = '<unknown>'):
        self._filename   = filename
        self._tmp_cnt    = 0
        self._label_cnt  = 0
        self._fn: Optional[IRFunction] = None
        self._break_stack: List[str]   = []
        self._cont_stack:  List[str]   = []
        # set of local variable names in current function
        self._locals: set[str] = set()
        # set of param names in current function
        self._params: set[str] = set()
        self._strings: List = []

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _tmp(self) -> Temp:
        t = Temp(self._tmp_cnt)
        self._tmp_cnt += 1
        return t

    def _new_label(self, prefix: str) -> str:
        self._label_cnt += 1
        return f'._ir_{prefix}_{self._label_cnt}'

    def _loc(self, node: Node):
        line = getattr(node, 'line', None)
        if not line:
            return self._stmt_loc
        fname = getattr(node, 'filename', None) or self._filename
        return (fname, line)

    def _emit(self, instr):
        self._fn.instrs.append(instr)

    def _operand(self, node: Expr) -> Optional[Operand]:
        """
        Try to turn a simple expression into an operand directly (no instruction).
        Returns None if the expression needs code generation.
        """
        if isinstance(node, IntLit):
            return ImmInt(node.value & 0xFFFF)
        if isinstance(node, CharLit):
            return ImmInt(node.value & 0xFF)
        if isinstance(node, Ident):
            name = node.name
            if name in self._params or name in self._locals:
                return Var(name)
            return Global(name)
        return None

    def _as_temp(self, op: Operand, loc) -> Temp:
        """Ensure operand is in a Temp (emit ICopy if needed)."""
        if isinstance(op, Temp):
            return op
        t = self._tmp()
        self._emit(ICopy(t, op, loc))
        return t

    # ── Top-Level ─────────────────────────────────────────────────────────────

    def generate(self, prog: Program) -> IRProgram:
        ir = IRProgram()

        for decl in prog.decls:
            if isinstance(decl, VarDecl):
                words = max(1, decl.ctype.size())
                init_vals = None
                if isinstance(decl.init, InitList):
                    init_vals = []
                    for e in decl.init.elems:
                        if isinstance(e, (IntLit, CharLit)):
                            init_vals.append(e.value)
                        elif isinstance(e, StringLit):
                            lbl = f'_cstr_{len(self._strings) + 1}'
                            self._strings.append((lbl, e.chars))
                            init_vals.append(lbl)
                        else:
                            init_vals.append(0)
                elif isinstance(decl.init, IntLit):
                    init_vals = [decl.init.value]
                elif isinstance(decl.init, StringLit):
                    lbl = f'_cstr_{len(self._strings) + 1}'
                    self._strings.append((lbl, decl.init.chars))
                    init_vals = [lbl]
                ir.globals.append((decl.name, words, init_vals))
            elif isinstance(decl, FuncDecl) and decl.body is not None:
                ir.functions.append(self._gen_func(decl))

        # string literals are collected during generation
        ir.strings = self._strings
        return ir

    # ── Functions ─────────────────────────────────────────────────────────────

    def _gen_func(self, func: FuncDecl) -> IRFunction:
        self._tmp_cnt = 0
        self._label_cnt = 0
        self._params = {p.name for p in func.params}
        self._locals = set()
        self._break_stack = []
        self._cont_stack  = []
        self._num_fixed_params = len(func.params)
        self._stmt_loc = None

        self._fn = IRFunction(
            name=func.name,
            params=[p.name for p in func.params],
            is_variadic=func.is_variadic,
            is_static=func.is_static,
            is_always_inline=func.is_always_inline,
        )

        self._collect_locals(func.body)
        self._gen_block(func.body)

        # ensure every path ends with a ret
        instrs = self._fn.instrs
        if not instrs or not isinstance(instrs[-1], IRet):
            self._emit(IRet(None, self._loc(func)))

        return self._fn

    def _collect_locals(self, node):
        """Walk body and register all declared local names and their sizes."""
        if isinstance(node, DeclStmt):
            d = node.decl
            self._locals.add(d.name)
            size = d.ctype.size() if isinstance(d.ctype, (CArray, CStruct, CUnion)) else 1
            self._fn.local_sizes[d.name] = size
        elif isinstance(node, Block):
            for s in node.stmts:
                self._collect_locals(s)
        elif isinstance(node, IfStmt):
            self._collect_locals(node.then)
            if node.else_:
                self._collect_locals(node.else_)
        elif isinstance(node, (WhileStmt, DoWhileStmt)):
            self._collect_locals(node.body)
        elif isinstance(node, ForStmt):
            if node.init:
                self._collect_locals(node.init)
            self._collect_locals(node.body)

    # ── Statements ────────────────────────────────────────────────────────────

    def _gen_block(self, block: Block):
        for stmt in block.stmts:
            self._gen_stmt(stmt)

    def _gen_stmt(self, stmt: Stmt):
        loc = self._loc(stmt)
        if loc:
            self._stmt_loc = loc
        if isinstance(stmt, Block):
            self._gen_block(stmt)

        elif isinstance(stmt, DeclStmt):
            d = stmt.decl
            if d.init is not None:
                loc = self._loc(stmt)
                if isinstance(d.init, StringLit) and isinstance(d.ctype, CArray):
                    # char arr[] = "hello" — copy each char + null terminator
                    chars = d.init.chars + [0]
                    base = self._var_addr(d.name, loc)
                    for i, ch in enumerate(chars):
                        if i == 0:
                            self._emit(IStore(base, ImmInt(ch), loc))
                        else:
                            t_off = self._tmp()
                            self._emit(IBinOp(t_off, '+', base, ImmInt(i), loc))
                            self._emit(IStore(t_off, ImmInt(ch), loc))
                elif isinstance(d.init, InitList):
                    elem_sz = d.ctype.base.size() if isinstance(d.ctype, CArray) else 1
                    arr_len = d.ctype.length if isinstance(d.ctype, CArray) else 1
                    base = self._var_addr(d.name, loc)
                    # write explicit initializer elements
                    for i, elem in enumerate(d.init.elems):
                        val = self._gen_expr(elem)
                        if i == 0:
                            self._emit(IStore(base, val, loc))
                        else:
                            t_off = self._tmp()
                            self._emit(IBinOp(t_off, '+', base, ImmInt(i * elem_sz), loc))
                            self._emit(IStore(t_off, val, loc))
                    # zero-fill remaining elements (standard C partial initializer rule)
                    for i in range(len(d.init.elems), arr_len):
                        t_off = self._tmp()
                        self._emit(IBinOp(t_off, '+', base, ImmInt(i * elem_sz), loc))
                        self._emit(IStore(t_off, ImmInt(0), loc))
                else:
                    val = self._gen_expr(d.init)
                    addr = self._var_addr(d.name, loc)
                    self._emit(IStore(addr, val, loc))

        elif isinstance(stmt, ExprStmt):
            self._gen_expr(stmt.expr)

        elif isinstance(stmt, ReturnStmt):
            if stmt.expr is not None:
                val = self._gen_expr(stmt.expr)
                self._emit(IRet(val, self._loc(stmt)))
            else:
                self._emit(IRet(None, self._loc(stmt)))

        elif isinstance(stmt, IfStmt):
            self._gen_if(stmt)

        elif isinstance(stmt, WhileStmt):
            self._gen_while(stmt)

        elif isinstance(stmt, DoWhileStmt):
            self._gen_do_while(stmt)

        elif isinstance(stmt, ForStmt):
            self._gen_for(stmt)

        elif isinstance(stmt, BreakStmt):
            if not self._break_stack:
                raise IRGenError("break outside loop")
            self._emit(IJump(self._break_stack[-1], self._loc(stmt)))

        elif isinstance(stmt, ContinueStmt):
            if not self._cont_stack:
                raise IRGenError("continue outside loop")
            self._emit(IJump(self._cont_stack[-1], self._loc(stmt)))

        elif isinstance(stmt, AsmStmt):
            srcs = [self._gen_expr(e) for e in stmt.inputs]
            self._emit(IInlineAsm(stmt.text, srcs, self._loc(stmt)))

        else:
            raise IRGenError(f"Unhandled statement: {type(stmt)}")

    def _gen_if(self, stmt: IfStmt):
        loc = self._loc(stmt)
        else_lbl = self._new_label('else')
        end_lbl  = self._new_label('endif')

        cond = self._gen_expr(stmt.cond)
        self._emit(IJumpIfNot(cond, else_lbl, loc))

        self._gen_stmt(stmt.then)
        if stmt.else_:
            self._emit(IJump(end_lbl, loc))

        self._emit(ILabel(else_lbl, loc))
        if stmt.else_:
            self._gen_stmt(stmt.else_)
            self._emit(ILabel(end_lbl, loc))

    def _gen_while(self, stmt: WhileStmt):
        loc = self._loc(stmt)
        cond_lbl = self._new_label('wcond')
        end_lbl  = self._new_label('wend')

        self._break_stack.append(end_lbl)
        self._cont_stack.append(cond_lbl)

        self._emit(ILabel(cond_lbl, loc))
        cond = self._gen_expr(stmt.cond)
        self._emit(IJumpIfNot(cond, end_lbl, loc))
        self._gen_stmt(stmt.body)
        self._emit(IJump(cond_lbl, loc))
        self._emit(ILabel(end_lbl, loc))

        self._break_stack.pop()
        self._cont_stack.pop()

    def _gen_do_while(self, stmt: DoWhileStmt):
        loc = self._loc(stmt)
        body_lbl = self._new_label('dobody')
        cond_lbl = self._new_label('docond')
        end_lbl  = self._new_label('doend')

        self._break_stack.append(end_lbl)
        self._cont_stack.append(cond_lbl)

        self._emit(ILabel(body_lbl, loc))
        self._gen_stmt(stmt.body)
        self._emit(ILabel(cond_lbl, loc))
        cond = self._gen_expr(stmt.cond)
        self._emit(IJumpIf(cond, body_lbl, loc))
        self._emit(ILabel(end_lbl, loc))

        self._break_stack.pop()
        self._cont_stack.pop()

    def _gen_for(self, stmt: ForStmt):
        loc = self._loc(stmt)
        cond_lbl = self._new_label('fcond')
        step_lbl = self._new_label('fstep')
        end_lbl  = self._new_label('fend')

        if stmt.init:
            self._gen_stmt(stmt.init)

        self._break_stack.append(end_lbl)
        self._cont_stack.append(step_lbl)

        self._emit(ILabel(cond_lbl, loc))
        if stmt.cond:
            cond = self._gen_expr(stmt.cond)
            self._emit(IJumpIfNot(cond, end_lbl, loc))

        self._gen_stmt(stmt.body)

        self._emit(ILabel(step_lbl, loc))
        if stmt.step:
            self._gen_expr(stmt.step)

        self._emit(IJump(cond_lbl, loc))
        self._emit(ILabel(end_lbl, loc))

        self._break_stack.pop()
        self._cont_stack.pop()

    # ── Expressions → Operand ─────────────────────────────────────────────────

    def _gen_expr(self, expr: Expr) -> Operand:
        """Lower expression, return the operand holding its value."""
        loc = self._loc(expr)

        if isinstance(expr, IntLit):
            return ImmInt(expr.value)

        if isinstance(expr, CharLit):
            return ImmInt(expr.value & 0xFF)

        if isinstance(expr, StringLit):
            lbl = f'_cstr_{len(self._strings) + 1}'
            self._strings.append((lbl, expr.chars))
            expr.label = lbl
            t = self._tmp()
            self._emit(ICopy(t, StrLabel(lbl), loc))
            return t

        if isinstance(expr, Ident):
            return self._gen_load_ident(expr)

        if isinstance(expr, BinOp):
            return self._gen_binop(expr)

        if isinstance(expr, UnaryOp):
            return self._gen_unary(expr)

        if isinstance(expr, Assign):
            return self._gen_assign(expr)

        if isinstance(expr, Call):
            return self._gen_call(expr)

        if isinstance(expr, Index):
            addr = self._gen_addr(expr)
            t = self._tmp()
            self._emit(ILoad(t, addr, loc))
            return t

        if isinstance(expr, Cast):
            val = self._gen_expr(expr.expr)
            if isinstance(expr.to_type, CChar):
                t = self._tmp()
                self._emit(IBinOp(t, '&', val, ImmInt(0xFF), loc))
                return t
            return val

        if isinstance(expr, SizeOf):
            if isinstance(expr.target, CType):
                sz = expr.target.size()
            else:
                sz = expr.target.ctype.size() if expr.target.ctype else 1
            return ImmInt(sz)

        if isinstance(expr, Ternary):
            return self._gen_ternary(expr)

        if isinstance(expr, Member):
            addr = self._gen_member_addr(expr)
            t = self._tmp()
            self._emit(ILoad(t, addr, loc))
            return t

        if isinstance(expr, VaArg):
            return self._gen_vaarg(expr)

        raise IRGenError(f"Unhandled expression: {type(expr)}")

    def _gen_load_ident(self, expr: Ident) -> Operand:
        loc  = self._loc(expr)
        name = expr.name

        # function name → just a label operand (no load)
        if isinstance(expr.ctype, CFunction):
            return Global(name)

        # local array/struct/union decays to its base address
        if isinstance(expr.ctype, (CArray, CStruct, CUnion)) and name not in self._params:
            t = self._tmp()
            self._emit(IAddrOf(t, self._var_operand(name), loc))
            return t

        # scalar local/param: copy directly from spill slot (no address indirection)
        if name in self._params or name in self._locals:
            t = self._tmp()
            self._emit(ICopy(t, Var(name), loc))
            return t

        # global: load via address
        addr = self._var_addr(name, loc)
        t    = self._tmp()
        self._emit(ILoad(t, addr, loc))
        return t

    def _var_operand(self, name: str) -> Union[Var, Global]:
        if name in self._locals or name in self._params:
            return Var(name)
        return Global(name)

    def _var_addr(self, name: str, loc) -> Operand:
        """Return an operand representing the address of a variable."""
        t = self._tmp()
        self._emit(IAddrOf(t, self._var_operand(name), loc))
        return t

    def _gen_addr(self, expr: Expr) -> Operand:
        """Return an operand holding the address of an lvalue."""
        loc = self._loc(expr)

        if isinstance(expr, Ident):
            name = expr.name
            # scalar local/param: use Var directly as the address operand
            if name in self._params or name in self._locals:
                return Var(name)
            return self._var_addr(name, loc)

        if isinstance(expr, Index):
            arr  = self._gen_expr(expr.array)
            idx  = self._gen_expr(expr.index)
            elem_sz = expr.ctype.size() if expr.ctype else 1
            t_idx = self._as_temp(idx, loc)
            if elem_sz > 1:
                t_scaled = self._tmp()
                self._emit(IBinOp(t_scaled, '*', t_idx, ImmInt(elem_sz), loc))
                t_idx = t_scaled
            t_arr = self._as_temp(arr, loc)
            t_addr = self._tmp()
            self._emit(IBinOp(t_addr, '+', t_arr, t_idx, loc))
            return t_addr

        if isinstance(expr, UnaryOp) and expr.op == '*':
            return self._gen_expr(expr.operand)

        if isinstance(expr, Member):
            return self._gen_member_addr(expr)

        raise IRGenError(f"Cannot take address of {type(expr)}")

    def _gen_member_addr(self, expr: Member) -> Operand:
        """Return an operand holding the address of a struct/union member."""
        loc = self._loc(expr)
        sf = expr._field_info   # StructField set by semantic analysis

        if expr.arrow:
            # p->field: p is a pointer; base address is the pointer value
            base = self._gen_expr(expr.obj)
        else:
            # s.field: s is a struct on the stack; get its address.
            # _gen_addr returns Var for a local — must use IAddrOf, not ICopy,
            # to materialise the stack address rather than loading the value.
            raw = self._gen_addr(expr.obj)
            if isinstance(raw, Var):
                t = self._tmp()
                self._emit(IAddrOf(t, raw, loc))
                base = t
            else:
                base = raw

        if sf.offset == 0:
            return self._as_temp(base, loc)

        t = self._tmp()
        self._emit(IBinOp(t, '+', base, ImmInt(sf.offset), loc))
        return t

    def _gen_store_to(self, val: Operand, target: Expr):
        """Store val into an lvalue target."""
        loc = self._loc(target)
        addr = self._gen_addr(target)
        self._emit(IStore(addr, val, loc))

    # ── BinOp ─────────────────────────────────────────────────────────────────

    def _gen_binop(self, expr: BinOp) -> Operand:
        loc = self._loc(expr)

        if expr.op == '&&':
            return self._gen_short_circuit(expr, is_or=False)
        if expr.op == '||':
            return self._gen_short_circuit(expr, is_or=True)

        left  = self._gen_expr(expr.left)
        right = self._gen_expr(expr.right)

        # Division and modulo are lowered to runtime helper calls so that
        # the IR call graph is complete (correct leaf detection, LR save, etc.)
        if expr.op in ('/', '%'):
            helper = '__udiv' if expr.op == '/' else '__umod'
            t = self._tmp()
            self._emit(ICall(t, Global(helper), [left, right], loc))
            return t

        t = self._tmp()
        self._emit(IBinOp(t, expr.op, left, right, loc))
        return t

    def _gen_short_circuit(self, expr: BinOp, is_or: bool) -> Operand:
        loc     = self._loc(expr)
        end_lbl = self._new_label('sc_end')
        result  = self._tmp()

        left = self._gen_expr(expr.left)
        self._emit(ICopy(result, left, loc))

        if is_or:
            self._emit(IJumpIf(result, end_lbl, loc))
        else:
            self._emit(IJumpIfNot(result, end_lbl, loc))

        right = self._gen_expr(expr.right)
        self._emit(ICopy(result, right, loc))

        self._emit(ILabel(end_lbl, loc))
        # normalize to 0/1
        t_norm = self._tmp()
        self._emit(IBinOp(t_norm, '!=', result, ImmInt(0), loc))
        return t_norm

    # ── UnaryOp ───────────────────────────────────────────────────────────────

    def _gen_unary(self, expr: UnaryOp) -> Operand:
        loc = self._loc(expr)
        op  = expr.op

        if op == '-':
            src = self._gen_expr(expr.operand)
            t   = self._tmp()
            self._emit(IUnaryOp(t, '-', src, loc))
            return t

        if op == '~':
            src = self._gen_expr(expr.operand)
            t   = self._tmp()
            self._emit(IUnaryOp(t, '~', src, loc))
            return t

        if op == '!':
            src = self._gen_expr(expr.operand)
            t   = self._tmp()
            self._emit(IBinOp(t, '==', src, ImmInt(0), loc))
            return t

        if op == '&':
            addr = self._gen_addr(expr.operand)
            # If _gen_addr returned a Var directly (scalar local/param), we need
            # the actual stack address as a value — emit IAddrOf to materialise it.
            if isinstance(addr, Var):
                t = self._tmp()
                self._emit(IAddrOf(t, addr, loc))
                return t
            return addr

        if op == '*':
            ptr = self._gen_expr(expr.operand)
            t   = self._tmp()
            self._emit(ILoad(t, ptr, loc))
            return t

        if op in ('++pre', '--pre'):
            addr = self._gen_addr(expr.operand)
            old  = self._tmp()
            if isinstance(addr, Var):
                self._emit(ICopy(old, addr, loc))
            else:
                self._emit(ILoad(old, addr, loc))
            new_ = self._tmp()
            arith_op = '+' if op == '++pre' else '-'
            self._emit(IBinOp(new_, arith_op, old, ImmInt(1), loc))
            self._emit(IStore(addr, new_, loc))
            return new_

        if op in ('++post', '--post'):
            addr = self._gen_addr(expr.operand)
            old  = self._tmp()
            if isinstance(addr, Var):
                self._emit(ICopy(old, addr, loc))
            else:
                self._emit(ILoad(old, addr, loc))
            new_ = self._tmp()
            arith_op = '+' if op == '++post' else '-'
            self._emit(IBinOp(new_, arith_op, old, ImmInt(1), loc))
            self._emit(IStore(addr, new_, loc))
            return old   # post: yield original value

        raise IRGenError(f"Unknown unary op: {op!r}")

    # ── Assign ────────────────────────────────────────────────────────────────

    def _gen_assign(self, expr: Assign) -> Operand:
        loc = self._loc(expr)

        if expr.op == '=':
            val = self._gen_expr(expr.value)
            self._gen_store_to(val, expr.target)
            return val

        # compound: synthesize a BinOp and lower through _gen_binop
        cur  = self._gen_expr(expr.target)
        rhs  = self._gen_expr(expr.value)
        base = expr.op[:-1]   # '+=' → '+'
        t    = self._tmp()
        if base in ('/', '%'):
            helper = '__udiv' if base == '/' else '__umod'
            self._emit(ICall(t, Global(helper), [cur, rhs], loc))
        else:
            self._emit(IBinOp(t, base, cur, rhs, loc))
        self._gen_store_to(t, expr.target)
        return t

    # ── Call ──────────────────────────────────────────────────────────────────

    def _gen_call(self, expr: Call) -> Operand:
        loc  = self._loc(expr)

        # va_start(ap, last): store va_start address into ap
        if isinstance(expr.func, Ident) and expr.func.name == 'va_start':
            ap_addr = self._gen_addr(expr.args[0])
            t = self._tmp()
            self._emit(IVaStart(t, self._num_fixed_params, loc))
            self._emit(IStore(ap_addr, t, loc))
            return ImmInt(0)

        # va_end(ap): no-op at IR level
        if isinstance(expr.func, Ident) and expr.func.name == 'va_end':
            return ImmInt(0)

        args = [self._gen_expr(a) for a in expr.args]

        if isinstance(expr.func, Ident):
            func_op = Global(expr.func.name)
        else:
            func_op = self._gen_expr(expr.func)

        is_void = isinstance(getattr(expr, 'ctype', None), CVoid)
        dst = None if is_void else self._tmp()
        self._emit(ICall(dst, func_op, args, loc))
        return dst if dst is not None else ImmInt(0)

    # ── VaArg ────────────────────────────────────────────────────────────────

    def _gen_vaarg(self, expr: VaArg) -> Operand:
        loc  = self._loc(expr)
        step = expr.arg_type.size() if expr.arg_type.size() > 0 else 1

        # Load current ap value
        ap_val = self._gen_expr(expr.ap)

        # dst = *ap  (load from the address stored in ap)
        dst = self._tmp()
        self._emit(IVaArg(dst, ap_val, step, loc))

        # Advance ap: ap += step; store back
        ap_addr = self._gen_addr(expr.ap)
        new_ap  = self._tmp()
        self._emit(IBinOp(new_ap, '+', ap_val, ImmInt(step), loc))
        self._emit(IStore(ap_addr, new_ap, loc))

        return dst

    # ── Ternary ───────────────────────────────────────────────────────────────

    def _gen_ternary(self, expr: Ternary) -> Operand:
        loc      = self._loc(expr)
        else_lbl = self._new_label('tern_else')
        end_lbl  = self._new_label('tern_end')
        result   = self._tmp()

        cond = self._gen_expr(expr.cond)
        self._emit(IJumpIfNot(cond, else_lbl, loc))

        then_val = self._gen_expr(expr.then)
        self._emit(ICopy(result, then_val, loc))
        self._emit(IJump(end_lbl, loc))

        self._emit(ILabel(else_lbl, loc))
        else_val = self._gen_expr(expr.else_)
        self._emit(ICopy(result, else_val, loc))

        self._emit(ILabel(end_lbl, loc))
        return result

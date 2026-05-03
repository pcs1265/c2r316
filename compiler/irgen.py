"""
C to R316 Compiler - IR Generator
AST → Three-Address IR

Assumes semantic analysis has already run (ctype / _sym attached to nodes).
"""

from __future__ import annotations
from typing import Optional, List

from .ast_nodes import *
from .ir import (
    Temp, Var, Global, ImmInt, StrLabel, Operand, LongValue,
    IConst, ICopy, IAddrOf, IBinOp, IUnaryOp, ILoad, IStore,
    ICall, IRet, ILabel, IJump, IJumpIf, IJumpIfNot,
    IInlineAsm, IVaStart, IVaArg, IRFunction, IRProgram,
    ILongLoad, ILongStore, ILongBinOp, ILongUnaryOp, ILongCompare,
    ILongRet, ILongCall,
    ASM_REGS,
)


class IRGenError(Exception):
    pass


def _const_int_value(e) -> int | None:
    """Return the integer value of a constant integer expression, or None."""
    if isinstance(e, (IntLit, CharLit)):
        return e.value
    if isinstance(e, UnaryOp) and e.op == '-' and isinstance(e.operand, (IntLit, CharLit)):
        return -e.operand.value
    return None


def _flatten_init(init: 'InitList') -> list:
    """Recursively flatten a (possibly nested) InitList into a list of scalar expressions."""
    result = []
    for e in init.elems:
        if isinstance(e, InitList):
            result.extend(_flatten_init(e))
        else:
            result.append(e)
    return result


def _leaf_elem_sz(t: 'CType') -> int:
    """Return the size (in words) of the innermost scalar element of an array type."""
    while isinstance(t, CArray):
        t = t.base
    return t.size()


def _is_long_type(t: 'CType') -> bool:
    return isinstance(t, CLong)


def _pointed_size(t: 'CType') -> int:
    if isinstance(t, CPointer):
        return t.base.size()
    if isinstance(t, CArray):
        return t.base.size()
    return 1


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
        # static locals: original name → mangled global name
        self._static_locals: dict[str, str] = {}
        # pending global entries from static locals (added in generate())
        self._pending_globals: List = []
        self._cur_func_name: str = ''
        # const globals with scalar integer initializers: mangled_name → int value
        self._const_globals: dict[str, int] = {}

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _tmp(self) -> Temp:
        t = Temp(self._tmp_cnt)
        self._tmp_cnt += 1
        return t

    def _new_label(self, prefix: str) -> str:
        self._label_cnt += 1
        return f'._ir_{prefix}_{self._label_cnt}'

    def _user_label(self, name: str) -> str:
        """Mangle a user-written label to avoid clashes with compiler-generated ones.

        User labels are local to a function and are emitted in the output ASM
        as local labels (leading dot)."""
        return f'._user_{name}'

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
            if name in self._static_locals:
                return Global(self._static_locals[name])
            return Global(name)
        return None

    def _as_temp(self, op: Operand, loc) -> Temp:
        """Ensure operand is in a Temp (emit ICopy if needed)."""
        if isinstance(op, Temp):
            return op
        t = self._tmp()
        self._emit(ICopy(t, op, loc))
        return t

    def _long_const(self, value: int) -> LongValue:
        return LongValue(ImmInt(value & 0xFFFF), ImmInt((value >> 16) & 0xFFFF))

    def _as_long(self, val, loc, signed: bool = False) -> LongValue:
        """Convert a scalar operand to a long pair."""
        if isinstance(val, LongValue):
            return val
        lo = val
        hi = self._tmp()
        if signed:
            sign = self._tmp()
            self._emit(IBinOp(sign, '&', lo, ImmInt(0x8000), loc))
            is_neg = self._tmp()
            self._emit(IBinOp(is_neg, '!=', sign, ImmInt(0), loc))
            neg_hi = self._tmp()
            self._emit(IUnaryOp(neg_hi, '-', is_neg, loc))
            self._emit(ICopy(hi, neg_hi, loc))
        else:
            self._emit(ICopy(hi, ImmInt(0), loc))
        return LongValue(lo, hi)

    def _bool_operand(self, val, loc) -> Operand:
        if isinstance(val, LongValue):
            t_lo = self._tmp()
            self._emit(IBinOp(t_lo, '!=', val.lo, ImmInt(0), loc))
            t_hi = self._tmp()
            self._emit(IBinOp(t_hi, '!=', val.hi, ImmInt(0), loc))
            t = self._tmp()
            self._emit(IBinOp(t, '|', t_lo, t_hi, loc))
            return t
        return val

    def _gen_long_expr(self, expr: Expr) -> LongValue:
        """Lower expression as a 32-bit long pair."""
        loc = self._loc(expr)

        if isinstance(expr, IntLit):
            return self._long_const(expr.value)
        if isinstance(expr, CharLit):
            return self._long_const(expr.value & 0xFF)
        if isinstance(expr, UnaryOp) and expr.op == '-':
            src = self._gen_long_expr(expr.operand)
            lo, hi = self._tmp(), self._tmp()
            self._emit(ILongUnaryOp(lo, hi, '-', src.lo, src.hi, loc))
            return LongValue(lo, hi)
        if not isinstance(getattr(expr, 'ctype', None), CLong):
            val = self._gen_expr(expr)
            return self._as_long(val, loc, signed=not getattr(expr.ctype, 'unsigned', False))
        if isinstance(expr, Ident):
            return self._gen_long_load_ident(expr)
        if isinstance(expr, Index):
            addr = self._gen_addr(expr)
            lo, hi = self._tmp(), self._tmp()
            self._emit(ILongLoad(lo, hi, addr, loc))
            return LongValue(lo, hi)
        if isinstance(expr, Member):
            addr = self._gen_member_addr(expr)
            lo, hi = self._tmp(), self._tmp()
            self._emit(ILongLoad(lo, hi, addr, loc))
            return LongValue(lo, hi)
        if isinstance(expr, Cast):
            val = self._gen_expr(expr.expr)
            signed = not getattr(expr.expr.ctype, 'unsigned', False)
            return self._as_long(val, loc, signed=signed)
        if isinstance(expr, Assign):
            val = self._gen_assign(expr)
            if not isinstance(val, LongValue):
                return self._as_long(val, loc, signed=not getattr(expr.ctype, 'unsigned', False))
            return val
        if isinstance(expr, BinOp):
            return self._gen_long_binop(expr)
        if isinstance(expr, UnaryOp):
            if expr.op == '*':
                addr = self._gen_expr(expr.operand)
                lo, hi = self._tmp(), self._tmp()
                self._emit(ILongLoad(lo, hi, addr, loc))
                return LongValue(lo, hi)
            if expr.op == '~':
                src = self._gen_long_expr(expr.operand)
                lo, hi = self._tmp(), self._tmp()
                self._emit(IUnaryOp(lo, '~', src.lo, loc))
                self._emit(IUnaryOp(hi, '~', src.hi, loc))
                return LongValue(lo, hi)
        if isinstance(expr, Call):
            return self._gen_long_call(expr)
        raise IRGenError(f"long expression {type(expr).__name__} not implemented")

    def _gen_long_load_ident(self, expr: Ident) -> LongValue:
        loc, name = self._loc(expr), expr.name
        if name in self._params or name in self._locals:
            lo = self._tmp()
            hi = self._tmp()
            self._emit(ILongLoad(lo, hi, Var(name), loc))
            return LongValue(lo, hi)
        if name in self._const_globals:
            return self._long_const(self._const_globals[name])
        addr = self._var_addr(name, loc)
        lo = self._tmp()
        hi = self._tmp()
        self._emit(ILongLoad(lo, hi, addr, loc))
        return LongValue(lo, hi)

    # ── Top-Level ─────────────────────────────────────────────────────────────

    def generate(self, prog: Program) -> IRProgram:
        ir = IRProgram()

        for decl in prog.decls:
            if isinstance(decl, VarDecl):
                words = max(1, decl.ctype.size())
                init_vals = None
                if isinstance(decl.init, InitList):
                    init_vals = []
                    elem_sz = _leaf_elem_sz(decl.ctype) if isinstance(decl.ctype, CArray) else decl.ctype.size()
                    for e in _flatten_init(decl.init):
                        cv = _const_int_value(e)
                        if cv is not None:
                            if elem_sz == 2:
                                init_vals.extend([cv & 0xFFFF, (cv >> 16) & 0xFFFF])
                            else:
                                init_vals.append(cv)
                        elif isinstance(e, StringLit):
                            lbl = f'_cstr_{len(self._strings) + 1}'
                            self._strings.append((lbl, e.chars))
                            init_vals.append(lbl)
                        else:
                            init_vals.append(0)
                elif _const_int_value(decl.init) is not None:
                    cv = _const_int_value(decl.init)
                    if isinstance(decl.ctype, CLong):
                        init_vals = [cv & 0xFFFF, (cv >> 16) & 0xFFFF]
                    else:
                        init_vals = [cv]
                elif isinstance(decl.init, StringLit):
                    lbl = f'_cstr_{len(self._strings) + 1}'
                    self._strings.append((lbl, decl.init.chars))
                    init_vals = [lbl]
                ir.globals.append((decl.name, words, init_vals))
                # track scalar integer const globals for inline substitution
                if (decl.is_const and isinstance(decl.init, (IntLit, CharLit))
                        and not isinstance(decl.ctype, (CArray, CStruct, CUnion))):
                    self._const_globals[decl.name] = decl.init.value
            elif isinstance(decl, FuncDecl) and decl.body is not None:
                ir.functions.append(self._gen_func(decl))
                # flush static locals registered during function generation
                ir.globals.extend(self._pending_globals)
                self._pending_globals = []

        # string literals are collected during generation
        ir.strings = self._strings
        return ir

    # ── Functions ─────────────────────────────────────────────────────────────

    def _gen_func(self, func: FuncDecl) -> IRFunction:
        self._tmp_cnt = 0
        self._label_cnt = 0
        self._params = {p.name for p in func.params}
        self._locals = set()
        self._static_locals = {}
        self._cur_func_name = func.name
        self._break_stack = []
        self._cont_stack  = []
        self._num_fixed_params = len(func.params)
        self._stmt_loc = None

        # Register static locals as globals before processing the body
        self._collect_static_locals(func.body)

        # Struct return: inject hidden first param '__ret' (pointer to caller's
        # return slot).  The callee writes the struct there and returns the ptr.
        self._struct_ret_type = None
        # Struct params: received as hidden pointers; dereferenced on access.
        self._struct_params: dict[str, CType] = {}
        if isinstance(func.ret_type, (CStruct, CUnion)):
            self._struct_ret_type = func.ret_type
            param_names = ['__ret'] + [p.name for p in func.params]
            self._params.add('__ret')
        else:
            param_names = [p.name for p in func.params]
        for p in func.params:
            if isinstance(p.ctype, (CStruct, CUnion)):
                self._struct_params[p.name] = p.ctype

        self._fn = IRFunction(
            name=func.name,
            params=param_names,
            param_sizes={
                p.name: (2 if isinstance(p.ctype, CLong) else 1)
                for p in func.params
            },
            is_variadic=func.is_variadic,
            is_static=func.is_static,
            is_always_inline=func.is_always_inline,
        )
        if self._struct_ret_type is not None:
            self._fn.param_sizes['__ret'] = 1

        self._collect_locals(func.body)
        self._gen_block(func.body)

        # ensure every path ends with a ret
        instrs = self._fn.instrs
        if not instrs or not isinstance(instrs[-1], IRet):
            self._emit(IRet(None, self._loc(func)))

        return self._fn

    def _collect_static_locals(self, node):
        """Walk body, register static local variables as pending globals."""
        if isinstance(node, DeclStmt):
            d = node.decl
            if not d.is_static:
                return
            mangled = f'_C_{self._cur_func_name}__{d.name}'
            self._static_locals[d.name] = mangled
            words = max(1, d.ctype.size())
            init_vals = self._const_init(d.init, d.ctype)
            self._pending_globals.append((mangled, words, init_vals))
        elif isinstance(node, Block):
            for s in node.stmts:
                self._collect_static_locals(s)
        elif isinstance(node, IfStmt):
            self._collect_static_locals(node.then)
            if node.else_:
                self._collect_static_locals(node.else_)
        elif isinstance(node, (WhileStmt, DoWhileStmt)):
            self._collect_static_locals(node.body)
        elif isinstance(node, ForStmt):
            if node.init:
                self._collect_static_locals(node.init)
            self._collect_static_locals(node.body)

    def _is_const_init(self, init) -> bool:
        """True if the initializer is fully constant (can be baked into global data)."""
        if init is None:
            return True
        if isinstance(init, (IntLit, CharLit, StringLit)):
            return True
        if isinstance(init, InitList):
            return all(isinstance(e, (IntLit, CharLit, StringLit)) for e in init.elems)
        return False

    def _const_init(self, init, ctype):
        """Extract constant initializer values for a global/static, or return None for zero-init."""
        if init is None:
            return None
        cv = _const_int_value(init)
        if cv is not None:
            if isinstance(ctype, CLong):
                return [cv & 0xFFFF, (cv >> 16) & 0xFFFF]
            return [cv]
        if isinstance(init, CharLit):
            return [init.value & 0xFF]
        if isinstance(init, InitList):
            vals = []
            elem_sz = _leaf_elem_sz(ctype) if isinstance(ctype, CArray) else ctype.size()
            for e in init.elems:
                cv = _const_int_value(e)
                if cv is not None:
                    if elem_sz == 2:
                        vals.extend([cv & 0xFFFF, (cv >> 16) & 0xFFFF])
                    else:
                        vals.append(cv)
                elif isinstance(e, StringLit):
                    lbl = f'_cstr_{len(self._strings) + 1}'
                    self._strings.append((lbl, e.chars))
                    vals.append(lbl)
                else:
                    vals.append(0)
            return vals
        if isinstance(init, StringLit):
            lbl = f'_cstr_{len(self._strings) + 1}'
            self._strings.append((lbl, init.chars))
            return [lbl]
        # non-constant initializer: zero-init the storage; init code is emitted at call site
        return None

    def _collect_locals(self, node):
        """Walk body and register all declared local names and their sizes."""
        if isinstance(node, DeclStmt):
            d = node.decl
            if d.is_static:
                return  # handled as a global via _collect_static_locals
            self._locals.add(d.name)
            size = d.ctype.size() if isinstance(d.ctype, (CArray, CStruct, CUnion, CLong)) else 1
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
            if d.is_static:
                # Static local: storage is a global. Constant initializers are
                # already baked into the global data section. For non-constant
                # initializers, emit the assignment guarded by a one-time flag.
                if d.init is not None and not self._is_const_init(d.init):
                    mangled = self._static_locals[d.name]
                    flag_name = mangled + '__init'
                    self._pending_globals.append((flag_name, 1, None))
                    loc = self._loc(stmt)
                    flag_addr = self._tmp()
                    self._emit(IAddrOf(flag_addr, Global(flag_name), loc))
                    flag_val = self._tmp()
                    self._emit(ILoad(flag_val, flag_addr, loc))
                    lbl_done = self._new_label('sl_done')
                    self._emit(IJumpIf(flag_val, lbl_done, loc))
                    # mark initialized
                    self._emit(IStore(flag_addr, ImmInt(1), loc))
                    # emit init code (re-use existing DeclStmt logic via a temp non-static decl)
                    g_addr = self._tmp()
                    self._emit(IAddrOf(g_addr, Global(mangled), loc))
                    if isinstance(d.ctype, CLong):
                        val = self._gen_long_expr(d.init)
                        self._emit(ILongStore(g_addr, val.lo, val.hi, loc))
                    else:
                        val = self._gen_expr(d.init)
                        self._emit(IStore(g_addr, val, loc))
                    self._emit(ILabel(lbl_done, loc))
                return
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
                    elem_sz = _leaf_elem_sz(d.ctype) if isinstance(d.ctype, CArray) else 1
                    total_words = d.ctype.size() if isinstance(d.ctype, CArray) else 1
                    flat = _flatten_init(d.init)
                    base = self._var_addr(d.name, loc)
                    # write explicit initializer elements
                    for i, elem in enumerate(flat):
                        val = self._gen_long_expr(elem) if elem_sz == 2 else self._gen_expr(elem)
                        if i == 0:
                            if isinstance(val, LongValue):
                                self._emit(ILongStore(base, val.lo, val.hi, loc))
                            else:
                                self._emit(IStore(base, val, loc))
                        else:
                            t_off = self._tmp()
                            self._emit(IBinOp(t_off, '+', base, ImmInt(i * elem_sz), loc))
                            if isinstance(val, LongValue):
                                self._emit(ILongStore(t_off, val.lo, val.hi, loc))
                            else:
                                self._emit(IStore(t_off, val, loc))
                    # zero-fill remaining words (standard C partial initializer rule)
                    for i in range(len(flat), total_words // elem_sz):
                        t_off = self._tmp()
                        self._emit(IBinOp(t_off, '+', base, ImmInt(i * elem_sz), loc))
                        if elem_sz == 2:
                            self._emit(ILongStore(t_off, ImmInt(0), ImmInt(0), loc))
                        else:
                            self._emit(IStore(t_off, ImmInt(0), loc))
                elif isinstance(d.ctype, (CStruct, CUnion)):
                    addr = self._var_addr(d.name, loc)
                    self._copy_struct(d.init, addr, d.ctype, loc)
                elif isinstance(d.ctype, CLong):
                    val = self._gen_long_expr(d.init)
                    addr = self._var_addr(d.name, loc)
                    self._emit(ILongStore(addr, val.lo, val.hi, loc))
                else:
                    val = self._gen_expr(d.init)
                    addr = self._var_addr(d.name, loc)
                    self._emit(IStore(addr, val, loc))

        elif isinstance(stmt, ExprStmt):
            self._gen_expr(stmt.expr)

        elif isinstance(stmt, ReturnStmt):
            if self._struct_ret_type is not None and stmt.expr is not None:
                # Struct return: copy struct value word-by-word into *__ret,
                # then return the hidden pointer (already in __ret param slot).
                loc = self._loc(stmt)
                src_addr = self._gen_addr(stmt.expr)
                if isinstance(src_addr, Var):
                    t = self._tmp()
                    self._emit(IAddrOf(t, src_addr, loc))
                    src_addr = t
                ret_ptr = self._tmp()
                self._emit(ICopy(ret_ptr, Var('__ret'), loc))
                size = self._struct_ret_type.size()
                for i in range(size):
                    word = self._tmp()
                    if i == 0:
                        self._emit(ILoad(word, src_addr, loc))
                    else:
                        src_i = self._tmp()
                        self._emit(IBinOp(src_i, '+', src_addr, ImmInt(i), loc))
                        self._emit(ILoad(word, src_i, loc))
                    if i == 0:
                        self._emit(IStore(ret_ptr, word, loc))
                    else:
                        dst_i = self._tmp()
                        self._emit(IBinOp(dst_i, '+', ret_ptr, ImmInt(i), loc))
                        self._emit(IStore(dst_i, word, loc))
                self._emit(IRet(ret_ptr, loc))
            elif stmt.expr is not None:
                if isinstance(getattr(stmt.expr, 'ctype', None), CLong):
                    val = self._gen_long_expr(stmt.expr)
                    self._emit(ILongRet(val.lo, val.hi, self._loc(stmt)))
                else:
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

        elif isinstance(stmt, SwitchStmt):
            self._gen_switch(stmt)

        elif isinstance(stmt, BreakStmt):
            if not self._break_stack:
                raise IRGenError("break outside loop or switch")
            self._emit(IJump(self._break_stack[-1], self._loc(stmt)))

        elif isinstance(stmt, ContinueStmt):
            if not self._cont_stack:
                raise IRGenError("continue outside loop")
            self._emit(IJump(self._cont_stack[-1], self._loc(stmt)))

        elif isinstance(stmt, GotoStmt):
            self._emit(IJump(self._user_label(stmt.label), self._loc(stmt)))

        elif isinstance(stmt, LabelStmt):
            self._emit(ILabel(self._user_label(stmt.label), self._loc(stmt)))
            self._gen_stmt(stmt.body)

        elif isinstance(stmt, AsmStmt):
            srcs = [self._gen_expr(e) for e in stmt.inputs]
            self._emit(IInlineAsm(stmt.text, srcs, self._loc(stmt),
                                  clobbers=frozenset(ASM_REGS[:len(srcs)])))

        else:
            raise IRGenError(f"Unhandled statement: {type(stmt)}")

    def _gen_switch(self, stmt: SwitchStmt):
        loc = self._loc(stmt)
        end_lbl = self._new_label('swend')
        val = self._gen_expr(stmt.expr)

        # assign a label to each clause
        clause_lbls = [self._new_label('swcase') for _ in stmt.clauses]
        default_lbl = end_lbl

        # emit dispatch: compare val against each case constant, jump if equal
        for clause, lbl in zip(stmt.clauses, clause_lbls):
            if clause.value is None:
                default_lbl = lbl
            else:
                cval = self._gen_expr(clause.value)
                eq = self._tmp()
                self._emit(IBinOp(eq, '==', val, cval, loc))
                self._emit(IJumpIf(eq, lbl, loc))

        self._emit(IJump(default_lbl, loc))

        self._break_stack.append(end_lbl)

        for clause, lbl in zip(stmt.clauses, clause_lbls):
            self._emit(ILabel(lbl, loc))
            for s in clause.body:
                self._gen_stmt(s)

        self._break_stack.pop()
        self._emit(ILabel(end_lbl, loc))

    def _gen_if(self, stmt: IfStmt):
        loc = self._loc(stmt)
        else_lbl = self._new_label('else')
        end_lbl  = self._new_label('endif')

        cond = self._bool_operand(self._gen_expr(stmt.cond), loc)
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
        cond = self._bool_operand(self._gen_expr(stmt.cond), loc)
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
        cond = self._bool_operand(self._gen_expr(stmt.cond), loc)
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
            cond = self._bool_operand(self._gen_expr(stmt.cond), loc)
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

        if isinstance(getattr(expr, 'ctype', None), CLong):
            return self._gen_long_expr(expr)

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
            if isinstance(expr.ctype, CArray):
                # sub-array decays to pointer — return address, don't load
                return addr
            t = self._tmp()
            self._emit(ILoad(t, addr, loc))
            return t

        if isinstance(expr, Cast):
            val = self._gen_expr(expr.expr)
            if isinstance(val, LongValue) and not isinstance(expr.to_type, CLong):
                val = val.lo
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
            # Array / struct / union members don't get loaded — their storage
            # lives inline at this address, so the rvalue is the address itself
            # (mirrors the local-ident decay rule in _gen_load_ident).
            if isinstance(expr.ctype, (CArray, CStruct, CUnion)):
                return addr
            t = self._tmp()
            self._emit(ILoad(t, addr, loc))
            return t

        if isinstance(expr, VaArg):
            return self._gen_vaarg(expr)

        raise IRGenError(f"Unhandled expression: {type(expr)}")

    def _gen_load_ident(self, expr: Ident) -> Operand:
        loc  = self._loc(expr)
        name = expr.name

        # function name → its address (label value, not a memory load)
        if isinstance(expr.ctype, CFunction):
            t = self._tmp()
            self._emit(IAddrOf(t, Global(name), loc))
            return t

        # struct param received as hidden pointer — the slot holds the pointer value
        if name in self._struct_params:
            t = self._tmp()
            self._emit(ICopy(t, Var(name), loc))
            return t   # caller treats this as the struct's address

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

        # const global with known integer value: inline as immediate
        if name in self._const_globals:
            t = self._tmp()
            self._emit(ICopy(t, ImmInt(self._const_globals[name]), loc))
            return t

        # global: load via address
        addr = self._var_addr(name, loc)
        t    = self._tmp()
        self._emit(ILoad(t, addr, loc))
        return t

    def _var_operand(self, name: str) -> Union[Var, Global]:
        if name in self._locals or name in self._params:
            return Var(name)
        if name in self._static_locals:
            return Global(self._static_locals[name])
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
            # struct param: slot holds the hidden pointer — load it as the address
            if name in self._struct_params:
                t = self._tmp()
                self._emit(ICopy(t, Var(name), loc))
                return t
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
        if isinstance(getattr(target, 'ctype', None), CLong):
            lv = val if isinstance(val, LongValue) else self._as_long(
                val, loc, signed=not getattr(target.ctype, 'unsigned', False))
            self._emit(ILongStore(addr, lv.lo, lv.hi, loc))
            return
        if isinstance(val, LongValue):
            val = val.lo
        # Truncate to 8 bits when storing to char
        if isinstance(getattr(target, 'ctype', None), CChar):
            t = self._tmp()
            self._emit(IBinOp(t, '&', val, ImmInt(0xFF), loc))
            val = t
        self._emit(IStore(addr, val, loc))

    # ── BinOp ─────────────────────────────────────────────────────────────────

    def _gen_binop(self, expr: BinOp) -> Operand:
        loc = self._loc(expr)

        if expr.op == '&&':
            return self._gen_short_circuit(expr, is_or=False)
        if expr.op == '||':
            return self._gen_short_circuit(expr, is_or=True)

        if expr.op == '-' and is_pointer(expr.left.ctype) and is_pointer(expr.right.ctype):
            left = self._gen_expr(expr.left)
            right = self._gen_expr(expr.right)
            diff = self._tmp()
            self._emit(IBinOp(diff, '-', left, right, loc))
            elem_sz = _pointed_size(expr.left.ctype)
            if elem_sz <= 1:
                return diff
            scaled = self._tmp()
            self._emit(ICall(scaled, Global('__builtin_sdiv'), [diff, ImmInt(elem_sz)], loc))
            return scaled

        if expr.op in ('+', '-') and (
            (is_pointer(expr.left.ctype) and is_integer(expr.right.ctype)) or
            (expr.op == '+' and is_integer(expr.left.ctype) and is_pointer(expr.right.ctype))
        ):
            if is_pointer(expr.left.ctype):
                ptr_expr, idx_expr = expr.left, expr.right
                ptr_first = True
            else:
                ptr_expr, idx_expr = expr.right, expr.left
                ptr_first = False
            ptr = self._gen_expr(ptr_expr)
            idx_val = self._gen_expr(idx_expr)
            idx = idx_val.lo if isinstance(idx_val, LongValue) else idx_val
            elem_sz = _pointed_size(ptr_expr.ctype)
            if elem_sz > 1:
                scaled = self._tmp()
                self._emit(IBinOp(scaled, '*', idx, ImmInt(elem_sz), loc))
                idx = scaled
            t = self._tmp()
            op = '-' if expr.op == '-' and ptr_first else '+'
            self._emit(IBinOp(t, op, ptr, idx, loc))
            return t

        if isinstance(expr.left.ctype, CLong) or isinstance(expr.right.ctype, CLong):
            if expr.op in ('==', '!=', '<', '>', '<=', '>='):
                left = self._gen_long_expr(expr.left)
                right = self._gen_long_expr(expr.right)
                t = self._tmp()
                unsigned = getattr(expr.left.ctype, 'unsigned', False) or getattr(expr.right.ctype, 'unsigned', False)
                self._emit(ILongCompare(t, expr.op, left.lo, left.hi, right.lo, right.hi, unsigned, loc))
                return t
            lv = self._gen_long_binop(expr)
            if isinstance(getattr(expr, 'ctype', None), CLong):
                return lv
            return lv.lo

        left  = self._gen_expr(expr.left)
        right = self._gen_expr(expr.right)

        if expr.op in ('/', '%'):
            def _is_unsigned(t): return getattr(t, 'unsigned', False)
            unsigned = _is_unsigned(expr.left.ctype) or _is_unsigned(expr.right.ctype)
            # Strength reduction: unsigned division/modulo by a power-of-two constant
            #   x / 2^n  →  x >> n
            #   x % 2^n  →  x & (2^n - 1)
            # Only safe for unsigned (signed semantics around negative dividends differ).
            if unsigned and isinstance(right, ImmInt) and right.value > 0:
                v = right.value
                if (v & (v - 1)) == 0:
                    n = v.bit_length() - 1
                    t = self._tmp()
                    if expr.op == '/':
                        self._emit(IBinOp(t, '>>', left, ImmInt(n), loc))
                    else:
                        self._emit(IBinOp(t, '&', left, ImmInt(v - 1), loc))
                    return t
            helper = ('__builtin_udiv' if expr.op == '/' else '__builtin_umod') if unsigned else \
                     ('__builtin_sdiv' if expr.op == '/' else '__builtin_smod')
            t = self._tmp()
            self._emit(ICall(t, Global(helper), [left, right], loc))
            return t

        op = expr.op
        # Unsigned ordering compares: emit `<u` / `>=u` so codegen picks the
        # carry-flag-based branch (jc / jnc) instead of the signed jl / jge.
        # `>u` and `<=u` are normalized away by swapping operands so we only
        # need two new IR opcodes.  `==` / `!=` are signedness-neutral.
        if op in ('<', '<=', '>', '>='):
            def _is_unsigned(t): return getattr(t, 'unsigned', False)
            if _is_unsigned(expr.left.ctype) or _is_unsigned(expr.right.ctype):
                if op == '<':   op = '<u'
                elif op == '>=': op = '>=u'
                elif op == '>':  op, left, right = '<u', right, left
                elif op == '<=': op, left, right = '>=u', right, left

        t = self._tmp()
        self._emit(IBinOp(t, op, left, right, loc))
        return t

    def _gen_long_binop(self, expr: BinOp) -> LongValue:
        loc = self._loc(expr)
        if expr.op in ('*', '/', '%'):
            left = self._gen_long_expr(expr.left)
            right = self._gen_long_expr(expr.right)
            lo, hi = self._tmp(), self._tmp()
            unsigned = getattr(expr.left.ctype, 'unsigned', False) or getattr(expr.right.ctype, 'unsigned', False)
            if expr.op == '*':
                helper = '__builtin_ulmul'
            else:
                helper = ('__builtin_uldiv' if expr.op == '/' else '__builtin_ulmod') if unsigned else \
                         ('__builtin_sldiv' if expr.op == '/' else '__builtin_slmod')
            self._emit(ILongCall(lo, hi, Global(helper), [left.lo, left.hi, right.lo, right.hi], loc))
            return LongValue(lo, hi)
        if expr.op not in ('+', '-'):
            raise IRGenError(f"long operator {expr.op!r} not implemented")
        left = self._gen_long_expr(expr.left)
        right = self._gen_long_expr(expr.right)
        lo, hi = self._tmp(), self._tmp()
        self._emit(ILongBinOp(lo, hi, expr.op, left.lo, left.hi, right.lo, right.hi, loc))
        return LongValue(lo, hi)

    def _gen_short_circuit(self, expr: BinOp, is_or: bool) -> Operand:
        loc     = self._loc(expr)
        end_lbl = self._new_label('sc_end')
        result  = self._tmp()

        # Pre-initialize result to the short-circuit value so that if the LHS
        # causes an early jump (and result is never written by the RHS path),
        # the register already holds the correct answer.  Without this, fused
        # compare+branch codegen skips materializing the LHS as 0/1, leaving
        # result with whatever happened to be in the register slot (often
        # non-zero), making the whole expression appear true when it should be
        # false (or vice versa for ||).
        sc_val = 1 if is_or else 0
        self._emit(IConst(result, sc_val, loc))

        left = self._bool_operand(self._gen_expr(expr.left), loc)

        if is_or:
            self._emit(IJumpIf(left, end_lbl, loc))
        else:
            self._emit(IJumpIfNot(left, end_lbl, loc))

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
            if isinstance(getattr(expr.operand, 'ctype', None), CLong):
                src = self._gen_long_expr(expr.operand)
                t = self._tmp()
                self._emit(ILongCompare(t, '==', src.lo, src.hi, ImmInt(0), ImmInt(0),
                                        getattr(expr.operand.ctype, 'unsigned', False), loc))
                return t
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
            # Struct assignment: copy word-by-word from src address to dst address
            if isinstance(getattr(expr, 'ctype', None), (CStruct, CUnion)):
                ctype = expr.ctype
                dst_addr = self._gen_addr(expr.target)
                if isinstance(dst_addr, Var):
                    t = self._tmp()
                    self._emit(IAddrOf(t, dst_addr, loc))
                    dst_addr = t
                self._copy_struct(expr.value, dst_addr, ctype, loc)
                return dst_addr
            if isinstance(getattr(expr, 'ctype', None), CLong):
                val = self._gen_long_expr(expr.value)
                self._gen_store_to(val, expr.target)
                return val
            val = self._gen_expr(expr.value)
            self._gen_store_to(val, expr.target)
            return val

        # compound: synthesize a BinOp and lower through _gen_binop
        if isinstance(getattr(expr, 'ctype', None), CLong):
            if expr.op not in ('+=', '-=', '*=', '/=', '%='):
                raise IRGenError(f"long compound assignment {expr.op} not implemented")
            synthetic = BinOp(expr.op[:-1], expr.target, expr.value)
            synthetic.ctype = expr.ctype
            val = self._gen_long_binop(synthetic)
            self._gen_store_to(val, expr.target)
            return val

        # compound: synthesize a BinOp and lower through _gen_binop
        cur  = self._gen_expr(expr.target)
        rhs  = self._gen_expr(expr.value)
        base = expr.op[:-1]   # '+=' → '+'
        t    = self._tmp()
        if base in ('/', '%'):
            unsigned = getattr(expr.ctype, 'unsigned', False)
            # Strength reduction (mirrors _gen_binop): unsigned x /= 2^n → x >>= n,
            # unsigned x %= 2^n → x &= 2^n - 1
            if unsigned and isinstance(rhs, ImmInt) and rhs.value > 0 and (rhs.value & (rhs.value - 1)) == 0:
                n = rhs.value.bit_length() - 1
                if base == '/':
                    self._emit(IBinOp(t, '>>', cur, ImmInt(n), loc))
                else:
                    self._emit(IBinOp(t, '&', cur, ImmInt(rhs.value - 1), loc))
            else:
                helper = ('__builtin_udiv' if base == '/' else '__builtin_umod') if unsigned else \
                         ('__builtin_sdiv' if base == '/' else '__builtin_smod')
                self._emit(ICall(t, Global(helper), [cur, rhs], loc))
        else:
            self._emit(IBinOp(t, base, cur, rhs, loc))
        self._gen_store_to(t, expr.target)
        return t

    # ── Call ──────────────────────────────────────────────────────────────────

    def _gen_call(self, expr: Call) -> Operand:
        loc  = self._loc(expr)

        # __builtin_va_start(ap, last): store va_start address into ap
        if isinstance(expr.func, Ident) and expr.func.name == '__builtin_va_start':
            ap_addr = self._gen_addr(expr.args[0])
            t = self._tmp()
            self._emit(IVaStart(t, self._num_fixed_params, loc))
            self._emit(IStore(ap_addr, t, loc))
            return ImmInt(0)

        # __builtin_va_end(ap): no-op at IR level
        if isinstance(expr.func, Ident) and expr.func.name == '__builtin_va_end':
            return ImmInt(0)

        # Determine the called function's type to check for struct args/return
        func_ctype = getattr(expr.func, 'ctype', None)
        if isinstance(func_ctype, CPointer) and isinstance(func_ctype.base, CFunction):
            func_ctype = func_ctype.base

        ir_args = []

        # Struct return: allocate a local slot and prepend its address as hidden arg
        ret_type = getattr(expr, 'ctype', None)
        struct_ret_slot = None
        if isinstance(ret_type, (CStruct, CUnion)):
            struct_ret_slot = self._alloc_struct_slot(ret_type, loc)
            ir_args.append(struct_ret_slot)

        # Evaluate each argument; struct args are copied to a temp slot and
        # their address is passed instead of the value
        param_types = func_ctype.params if isinstance(func_ctype, CFunction) else []
        for i, arg_expr in enumerate(expr.args):
            param_t = param_types[i] if i < len(param_types) else None
            if isinstance(param_t, (CStruct, CUnion)):
                slot_addr = self._alloc_struct_slot(param_t, loc)
                self._copy_struct(arg_expr, slot_addr, param_t, loc)
                ir_args.append(slot_addr)
            elif isinstance(param_t, CLong):
                lv = self._gen_long_expr(arg_expr)
                ir_args.extend([lv.lo, lv.hi])
            elif isinstance(getattr(arg_expr, 'ctype', None), CLong):
                ir_args.append(self._gen_long_expr(arg_expr).lo)
            else:
                ir_args.append(self._gen_expr(arg_expr))

        if isinstance(expr.func, Ident) and isinstance(expr.func.ctype, CFunction):
            func_op = Global(expr.func.name)
        else:
            func_op = self._gen_expr(expr.func)

        is_void = isinstance(ret_type, CVoid)
        if isinstance(ret_type, CLong):
            lo, hi = self._tmp(), self._tmp()
            self._emit(ILongCall(lo, hi, func_op, ir_args, loc))
            return LongValue(lo, hi)
        dst = None if is_void else self._tmp()
        self._emit(ICall(dst, func_op, ir_args, loc))

        # Struct return: dst holds the hidden pointer; load the struct address
        if struct_ret_slot is not None:
            return struct_ret_slot

        return dst if dst is not None else ImmInt(0)

    def _gen_long_call(self, expr: Call) -> LongValue:
        val = self._gen_call(expr)
        if not isinstance(val, LongValue):
            return self._as_long(val, self._loc(expr), signed=not getattr(expr.ctype, 'unsigned', False))
        return val

    def _alloc_struct_slot(self, ctype, loc) -> Temp:
        """Allocate an anonymous local slot for a struct copy; return its address."""
        slot_name = f'__sv_{self._tmp_cnt}'
        self._locals.add(slot_name)
        self._fn.local_sizes[slot_name] = ctype.size()
        addr = self._tmp()
        self._emit(IAddrOf(addr, Var(slot_name), loc))
        return addr

    def _copy_struct(self, src_expr: 'Expr', dst_addr: Operand, ctype, loc):
        """Copy a struct value from src_expr into the memory at dst_addr."""
        # For struct-returning calls, _gen_expr already returns the slot address.
        # For lvalues (Ident, Member, Index), use _gen_addr.
        if isinstance(src_expr, Call) and isinstance(getattr(src_expr, 'ctype', None), (CStruct, CUnion)):
            src_addr = self._gen_expr(src_expr)
        else:
            src_addr = self._gen_addr(src_expr)
        if isinstance(src_addr, Var):
            t = self._tmp()
            self._emit(IAddrOf(t, src_addr, loc))
            src_addr = t
        for i in range(ctype.size()):
            word = self._tmp()
            if i == 0:
                self._emit(ILoad(word, src_addr, loc))
                self._emit(IStore(dst_addr, word, loc))
            else:
                src_i = self._tmp()
                self._emit(IBinOp(src_i, '+', src_addr, ImmInt(i), loc))
                self._emit(ILoad(word, src_i, loc))
                dst_i = self._tmp()
                self._emit(IBinOp(dst_i, '+', dst_addr, ImmInt(i), loc))
                self._emit(IStore(dst_i, word, loc))

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

        cond = self._bool_operand(self._gen_expr(expr.cond), loc)
        self._emit(IJumpIfNot(cond, else_lbl, loc))

        then_val = self._gen_expr(expr.then)
        self._emit(ICopy(result, then_val, loc))
        self._emit(IJump(end_lbl, loc))

        self._emit(ILabel(else_lbl, loc))
        else_val = self._gen_expr(expr.else_)
        self._emit(ICopy(result, else_val, loc))

        self._emit(ILabel(end_lbl, loc))
        return result

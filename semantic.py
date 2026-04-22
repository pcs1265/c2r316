"""
C to R316 Compiler - Semantic Analysis
Symbol table construction + type checking
"""

from ast_nodes import *


class SemanticError(Exception):
    pass


class Symbol:
    def __init__(self, name: str, ctype: CType, is_global: bool = False,
                 is_func: bool = False, offset: int = 0):
        self.name      = name
        self.ctype     = ctype
        self.is_global = is_global
        self.is_func   = is_func
        self.offset    = offset   # local variable: offset from sp


class Scope:
    def __init__(self, parent: Optional['Scope'] = None):
        self.parent  = parent
        self.symbols: dict[str, Symbol] = {}

    def define(self, sym: Symbol):
        self.symbols[sym.name] = sym

    def lookup(self, name: str) -> Optional[Symbol]:
        if name in self.symbols:
            return self.symbols[name]
        if self.parent:
            return self.parent.lookup(name)
        return None


def common_type(a: CType, b: CType) -> CType:
    """Return the common (wider) type of two types"""
    if isinstance(a, CLong) or isinstance(b, CLong):
        return CLong()
    if isinstance(a, (CPointer, CArray)):
        return a
    if isinstance(b, (CPointer, CArray)):
        return b
    return CInt()


class Analyzer:
    def __init__(self):
        self.global_scope = Scope()
        self.scope        = self.global_scope
        self.current_func: Optional[FuncDecl] = None
        self.local_offset = 0      # current function stack size (words)
        self.string_lits: list[StringLit] = []

    # ── Scope Management ───────────────────────────────────────────────────────────

    def _push_scope(self):
        self.scope = Scope(self.scope)

    def _pop_scope(self):
        self.scope = self.scope.parent

    def _define(self, name: str, ctype: CType, is_global=False,
                is_func=False, offset=0):
        sym = Symbol(name, ctype, is_global, is_func, offset)
        self.scope.define(sym)
        return sym

    def _lookup(self, name: str) -> Symbol:
        sym = self.scope.lookup(name)
        if sym is None:
            raise SemanticError(f"Undefined symbol: {name!r}")
        return sym

    # ── Top-Level ───────────────────────────────────────────────────────────────

    def analyze(self, prog: Program):
        # pass 1: register function/global variable declarations
        for decl in prog.decls:
            if isinstance(decl, FuncDecl):
                ftype = CFunction(decl.ret_type,
                                  [p.ctype for p in decl.params])
                self._define(decl.name, ftype, is_global=True, is_func=True)
            elif isinstance(decl, VarDecl):
                self._define(decl.name, decl.ctype, is_global=True)

        # pass 2: analyze function bodies
        for decl in prog.decls:
            if isinstance(decl, FuncDecl) and decl.body is not None:
                self._analyze_func(decl)

    def _analyze_func(self, func: FuncDecl):
        self.current_func = func
        self.local_offset = 0
        self._push_scope()

        # register parameters
        for i, param in enumerate(func.params):
            sym = self._define(param.name, param.ctype)
            # parameters have negative offset (placed by caller)
            # actual layout decided by codegen; just mark here
            sym.is_global = False

        self._analyze_block(func.body)
        func._local_size = self.local_offset   # passed to codegen

        self._pop_scope()
        self.current_func = None

    # ── Statements ─────────────────────────────────────────────────────────────────

    def _analyze_block(self, block: Block):
        self._push_scope()
        for stmt in block.stmts:
            self._analyze_stmt(stmt)
        self._pop_scope()

    def _analyze_stmt(self, stmt: Stmt):
        if isinstance(stmt, Block):
            self._analyze_block(stmt)

        elif isinstance(stmt, DeclStmt):
            d = stmt.decl
            size = d.ctype.size() if not isinstance(d.ctype, CArray) else d.ctype.size()
            size = max(size, 1)
            sym = self._define(d.name, d.ctype, offset=self.local_offset)
            self.local_offset += size
            if d.init is not None:
                self._analyze_expr(d.init)

        elif isinstance(stmt, ExprStmt):
            self._analyze_expr(stmt.expr)

        elif isinstance(stmt, IfStmt):
            self._analyze_expr(stmt.cond)
            self._analyze_stmt(stmt.then)
            if stmt.else_:
                self._analyze_stmt(stmt.else_)

        elif isinstance(stmt, WhileStmt):
            self._analyze_expr(stmt.cond)
            self._analyze_stmt(stmt.body)

        elif isinstance(stmt, ForStmt):
            self._push_scope()
            if stmt.init:
                self._analyze_stmt(stmt.init)
            if stmt.cond:
                self._analyze_expr(stmt.cond)
            if stmt.step:
                self._analyze_expr(stmt.step)
            self._analyze_stmt(stmt.body)
            self._pop_scope()

        elif isinstance(stmt, ReturnStmt):
            if stmt.expr:
                self._analyze_expr(stmt.expr)

        elif isinstance(stmt, (BreakStmt, ContinueStmt)):
            pass

        else:
            raise SemanticError(f"Unknown statement type: {type(stmt)}")

    # ── Expressions ───────────────────────────────────────────────────────────────

    def _analyze_expr(self, expr: Expr) -> CType:
        if isinstance(expr, IntLit):
            expr.ctype = CInt()
            return expr.ctype

        if isinstance(expr, CharLit):
            expr.ctype = CChar()
            return expr.ctype

        if isinstance(expr, StringLit):
            expr.ctype = CPointer(CChar())
            self.string_lits.append(expr)
            return expr.ctype

        if isinstance(expr, Ident):
            sym = self._lookup(expr.name)
            expr.ctype = sym.ctype
            expr._sym  = sym
            return expr.ctype

        if isinstance(expr, BinOp):
            lt = self._analyze_expr(expr.left)
            rt = self._analyze_expr(expr.right)
            if expr.op in ('==', '!=', '<', '>', '<=', '>=', '&&', '||'):
                expr.ctype = CInt()
            else:
                expr.ctype = common_type(lt, rt)
            return expr.ctype

        if isinstance(expr, UnaryOp):
            ot = self._analyze_expr(expr.operand)
            if expr.op == '&':
                expr.ctype = CPointer(ot)
            elif expr.op == '*':
                if isinstance(ot, CPointer):
                    expr.ctype = ot.base
                elif isinstance(ot, CArray):
                    expr.ctype = ot.base
                else:
                    raise SemanticError(f"Dereferencing non-pointer type {ot}")
            elif expr.op == '!':
                expr.ctype = CInt()
            else:
                expr.ctype = ot
            return expr.ctype

        if isinstance(expr, Assign):
            tt = self._analyze_expr(expr.target)
            self._analyze_expr(expr.value)
            expr.ctype = tt
            return expr.ctype

        if isinstance(expr, Call):
            ft = self._analyze_expr(expr.func)
            for arg in expr.args:
                self._analyze_expr(arg)
            if isinstance(ft, CFunction):
                expr.ctype = ft.ret
            else:
                expr.ctype = CInt()   # simplified for function pointers etc.
            return expr.ctype

        if isinstance(expr, Index):
            at = self._analyze_expr(expr.array)
            self._analyze_expr(expr.index)
            if isinstance(at, (CPointer, CArray)):
                expr.ctype = at.base
            else:
                raise SemanticError(f"Indexing non-array/pointer type {at}")
            return expr.ctype

        if isinstance(expr, Cast):
            self._analyze_expr(expr.expr)
            expr.ctype = expr.to_type
            return expr.ctype

        if isinstance(expr, SizeOf):
            expr.ctype = CInt()
            return expr.ctype

        if isinstance(expr, Member):
            self._analyze_expr(expr.obj)
            expr.ctype = CInt()   # simplified when struct unsupported
            return expr.ctype

        if isinstance(expr, Ternary):
            self._analyze_expr(expr.cond)
            t1 = self._analyze_expr(expr.then)
            t2 = self._analyze_expr(expr.else_)
            expr.ctype = common_type(t1, t2)
            return expr.ctype

        raise SemanticError(f"Unknown expression type: {type(expr)}")

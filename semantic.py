"""
C to R316 Compiler - Semantic Analysis
심볼 테이블 구축 + 타입 검사
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
        self.offset    = offset   # 지역 변수: sp 기준 오프셋


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
    """두 타입의 공통(더 넓은) 타입 반환"""
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
        self.local_offset = 0      # 현재 함수 스택 크기 (words)
        self.string_lits: list[StringLit] = []

    # ── 스코프 관리 ───────────────────────────────────────────────────────────

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

    # ── 최상위 ───────────────────────────────────────────────────────────────

    def analyze(self, prog: Program):
        # 1패스: 함수/전역 변수 선언 등록
        for decl in prog.decls:
            if isinstance(decl, FuncDecl):
                ftype = CFunction(decl.ret_type,
                                  [p.ctype for p in decl.params],
                                  decl.variadic)
                self._define(decl.name, ftype, is_global=True, is_func=True)
            elif isinstance(decl, VarDecl):
                self._define(decl.name, decl.ctype, is_global=True)

        # 2패스: 함수 몸체 분석
        for decl in prog.decls:
            if isinstance(decl, FuncDecl) and decl.body is not None:
                self._analyze_func(decl)

    def _analyze_func(self, func: FuncDecl):
        self.current_func = func
        self.local_offset = 0
        self._push_scope()

        # 파라미터 등록
        for i, param in enumerate(func.params):
            sym = self._define(param.name, param.ctype)
            # 파라미터는 음수 오프셋 (caller가 넣어줌)
            # 실제 레이아웃은 codegen이 결정; 여기서는 표시만
            sym.is_global = False

        self._analyze_block(func.body)
        func._local_size = self.local_offset   # codegen에 전달

        self._pop_scope()
        self.current_func = None

    # ── 문장 ─────────────────────────────────────────────────────────────────

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

    # ── 표현식 ───────────────────────────────────────────────────────────────

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
                expr.ctype    = ft.ret
                expr._variadic = ft.variadic
                expr._n_fixed  = len(ft.params)
            else:
                expr.ctype    = CInt()
                expr._variadic = False
                expr._n_fixed  = len(expr.args)
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
            expr.ctype = CInt()   # struct 미지원 시 단순화
            return expr.ctype

        if isinstance(expr, Ternary):
            self._analyze_expr(expr.cond)
            t1 = self._analyze_expr(expr.then)
            t2 = self._analyze_expr(expr.else_)
            expr.ctype = common_type(t1, t2)
            return expr.ctype

        raise SemanticError(f"Unknown expression type: {type(expr)}")

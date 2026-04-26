"""
C to R316 Compiler - Semantic Analysis
Symbol table construction + type checking
"""

from .ast_nodes import *


class SemanticError(Exception):
    def __init__(self, message, line=0, col=0, filename=''):
        super().__init__(message)
        self.line     = line
        self.col      = col
        self.filename = filename


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
        self._cur_line: int = 0
        self._cur_file: str = ''

    def _err(self, msg: str) -> SemanticError:
        return SemanticError(msg, self._cur_line, 0, self._cur_file)

    def _set_loc(self, node):
        """Update current location from a node if it carries one."""
        line = getattr(node, 'line', 0)
        fname = getattr(node, 'filename', '')
        if line:
            self._cur_line = line
        if fname:
            self._cur_file = fname

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

    def _lookup(self, name: str, line: int = 0, filename: str = '') -> Symbol:
        sym = self.scope.lookup(name)
        if sym is None:
            if line:
                self._cur_line = line
            if filename:
                self._cur_file = filename
            raise self._err(f"Undefined symbol: {name!r}")
        return sym

    # ── Top-Level ───────────────────────────────────────────────────────────────

    def analyze(self, prog: Program):
        # pass 1: register function/global variable declarations
        for decl in prog.decls:
            if isinstance(decl, FuncDecl):
                ftype = CFunction(decl.ret_type,
                                  [p.ctype for p in decl.params],
                                  is_variadic=decl.is_variadic)
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

        elif isinstance(stmt, DoWhileStmt):
            self._analyze_stmt(stmt.body)
            self._analyze_expr(stmt.cond)

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

        elif isinstance(stmt, SwitchStmt):
            self._analyze_expr(stmt.expr)
            for clause in stmt.clauses:
                if clause.value is not None:
                    self._analyze_expr(clause.value)
                for s in clause.body:
                    self._analyze_stmt(s)

        elif isinstance(stmt, (BreakStmt, ContinueStmt)):
            pass

        elif isinstance(stmt, GotoStmt):
            pass  # label resolution happens at irgen / asm-emit time

        elif isinstance(stmt, LabelStmt):
            self._analyze_stmt(stmt.body)

        elif isinstance(stmt, AsmStmt):
            for e in stmt.inputs:
                self._analyze_expr(e)

        else:
            raise self._err(f"Unknown statement type: {type(stmt)}")

    # ── Expressions ───────────────────────────────────────────────────────────────

    def _analyze_expr(self, expr: Expr) -> CType:
        self._set_loc(expr)
        if isinstance(expr, IntLit):
            expr.ctype = CInt()
            return expr.ctype

        if isinstance(expr, CharLit):
            expr.ctype = CChar()
            return expr.ctype

        if isinstance(expr, StringLit):
            expr.ctype = CArray(CChar(), len(expr.chars) + 1)
            self.string_lits.append(expr)
            return expr.ctype

        if isinstance(expr, Ident):
            sym = self._lookup(expr.name, expr.line, expr.filename)
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
                    raise self._err(f"Dereferencing non-pointer type {ot}")
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
            # __builtin_va_start(ap, last) and __builtin_va_end(ap) are built-in void operations
            if isinstance(expr.func, Ident) and expr.func.name in ('__builtin_va_start', '__builtin_va_end'):
                for a in expr.args:
                    self._analyze_expr(a)
                expr.func.ctype = CFunction(CVoid(), [])
                expr.ctype = CVoid()
                return expr.ctype

            ft = self._analyze_expr(expr.func)
            # function pointer: unwrap CPointer(CFunction(...))
            if isinstance(ft, CPointer) and isinstance(ft.base, CFunction):
                ft = ft.base
            arg_types = [self._analyze_expr(a) for a in expr.args]
            if isinstance(ft, CFunction):
                name = expr.func.name if isinstance(expr.func, Ident) else '<expr>'
                if ft.is_variadic:
                    # variadic: must supply at least the fixed params
                    if len(expr.args) < len(ft.params):
                        raise self._err(
                            f"Function '{name}' expects at least {len(ft.params)} argument(s), "
                            f"but {len(expr.args)} given"
                        )
                else:
                    # argument count check
                    if len(expr.args) != len(ft.params):
                        raise self._err(
                            f"Function '{name}' expects {len(ft.params)} argument(s), "
                            f"but {len(expr.args)} given"
                        )
                # type check fixed params only
                for i, (arg_t, param_t) in enumerate(zip(arg_types, ft.params)):
                    if not self._is_assignable(arg_t, param_t):
                        raise self._err(
                            f"Function '{name}': argument {i+1} type mismatch — "
                            f"expected {param_t}, got {arg_t}"
                        )
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
                raise self._err(f"Indexing non-array/pointer type {at}")
            return expr.ctype

        if isinstance(expr, Cast):
            self._analyze_expr(expr.expr)
            expr.ctype = expr.to_type
            return expr.ctype

        if isinstance(expr, SizeOf):
            if not isinstance(expr.target, CType):
                self._analyze_expr(expr.target)
            expr.ctype = CInt()
            return expr.ctype

        if isinstance(expr, Member):
            obj_type = self._analyze_expr(expr.obj)
            # for `->`, dereference the pointer first
            if expr.arrow:
                if isinstance(obj_type, CPointer):
                    obj_type = obj_type.base
                else:
                    raise self._err(
                        f"Arrow operator '->' requires a pointer, got {obj_type}"
                    )
            if not isinstance(obj_type, (CStruct, CUnion)):
                raise self._err(
                    f"Member access on non-struct/union type {obj_type}"
                )
            sf = obj_type.get_field(expr.field)
            if sf is None:
                raise self._err(
                    f"'{obj_type}' has no field '{expr.field}'"
                )
            expr._field_info = sf      # offset + ctype for IRGen
            expr.ctype = sf.ctype
            return expr.ctype

        if isinstance(expr, Ternary):
            self._analyze_expr(expr.cond)
            t1 = self._analyze_expr(expr.then)
            t2 = self._analyze_expr(expr.else_)
            expr.ctype = common_type(t1, t2)
            return expr.ctype

        if isinstance(expr, InitList):
            elem_types = [self._analyze_expr(e) for e in expr.elems]
            elem_t = elem_types[0] if elem_types else CInt()
            expr.ctype = CArray(elem_t, len(expr.elems))
            return expr.ctype

        if isinstance(expr, VaArg):
            self._analyze_expr(expr.ap)
            expr.ctype = expr.arg_type
            return expr.ctype

        raise self._err(f"Unknown expression type: {type(expr)}")

    # ── Type Compatibility ───────────────────────────────────────────────────────

    def _is_assignable(self, src: CType, dst: CType) -> bool:
        """Check if src type can be implicitly converted to dst type."""
        # same type → OK
        if type(src) == type(dst):
            # for pointers, check base type compatibility
            if isinstance(src, CPointer) and isinstance(dst, CPointer):
                return self._is_assignable(src.base, dst.base)
            # struct/union: must be the same named type
            if isinstance(src, (CStruct, CUnion)):
                return src.name == dst.name
            return True
        # int/char/long are interchangeable (integer promotions)
        if is_integer(src) and is_integer(dst):
            return True
        # void* ↔ any pointer (C allows implicit conversion)
        if isinstance(src, CPointer) and isinstance(dst, CPointer):
            if isinstance(src.base, CVoid) or isinstance(dst.base, CVoid):
                return True
            return self._is_assignable(src.base, dst.base)
        # array decays to pointer (e.g., char[] → char*)
        if isinstance(src, CArray) and isinstance(dst, CPointer):
            return self._is_assignable(src.base, dst.base)
        # function decays to function pointer (e.g., int(int) → int(*)(int))
        if isinstance(src, CFunction) and isinstance(dst, CPointer) and isinstance(dst.base, CFunction):
            return True
        return False

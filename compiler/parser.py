"""
C to R316 Compiler - Parser
Token stream → AST
"""

from .lexer import TK, Token
from .ast_nodes import *


class ParseError(Exception):
    pass


class Parser:
    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.pos    = 0

    # ── Basic Utilities ──────────────────────────────────────────────────────────────

    def _stamp(self, node, tok: Token):
        """Attach source location from tok onto node."""
        node.line     = tok.line
        node.filename = tok.filename
        return node

    def _cur(self) -> Token:
        return self.tokens[self.pos]

    def _peek(self, offset=1) -> Token:
        p = self.pos + offset
        if p < len(self.tokens):
            return self.tokens[p]
        return self.tokens[-1]

    def _at(self, *kinds) -> bool:
        return self._cur().kind in kinds

    def _eat(self, *kinds) -> Token:
        tok = self._cur()
        if tok.kind not in kinds:
            exp = ', '.join(k.name for k in kinds)
            loc = f'{tok.filename}:{tok.line}' if tok.filename else f'Line {tok.line}'
            raise ParseError(
                f"{loc}:{tok.col}: Expected {exp}, got {tok.kind.name} ({tok.value!r})"
            )
        self.pos += 1
        return tok

    def _try_eat(self, *kinds) -> Optional[Token]:
        if self._at(*kinds):
            return self._eat(*kinds)
        return None

    # ── Type Parsing ─────────────────────────────────────────────────────────────

    TYPE_STARTS = {TK.INT, TK.LONG, TK.CHAR, TK.VOID, TK.UNSIGNED, TK.STRUCT, TK.UNION, TK.ENUM}

    # identifiers that act as type names
    _TYPE_IDENTS = {'__builtin_va_list'}  # __builtin_va_list is int* alias

    def _at_type_start(self) -> bool:
        """True if current token starts a type (keyword, va_list, or typedef name)."""
        if self._cur().kind in self.TYPE_STARTS:
            return True
        if self._cur().kind == TK.IDENT:
            return self._cur().value in self._TYPE_IDENTS or self._cur().value in self._typedefs
        return False

    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.pos    = 0
        # struct/union tag registry: tag → CStruct/CUnion (possibly incomplete)
        self._struct_tags: dict[str, CStruct] = {}
        self._union_tags:  dict[str, CUnion]  = {}
        # typedef alias registry: name → CType
        self._typedefs: dict[str, CType] = {}
        # enum constant registry: name → int value
        self._enum_consts: dict[str, int] = {}

    def _parse_base_type(self) -> CType:
        if self._at(TK.STRUCT):
            return self._parse_struct_or_union(is_union=False)
        if self._at(TK.UNION):
            return self._parse_struct_or_union(is_union=True)
        if self._at(TK.ENUM):
            return self._parse_enum()
        # __builtin_va_list is an alias for int* (pointer to variadic spill area)
        if self._at(TK.IDENT) and self._cur().value == '__builtin_va_list':
            self._eat(TK.IDENT)
            return CPointer(CInt())
        # typedef alias
        if self._at(TK.IDENT) and self._cur().value in self._typedefs:
            return self._typedefs[self._eat(TK.IDENT).value]
        unsigned = bool(self._try_eat(TK.UNSIGNED))
        if self._try_eat(TK.INT):
            return CInt(unsigned)
        if self._try_eat(TK.LONG):
            return CLong(unsigned)
        if self._try_eat(TK.CHAR):
            return CChar(unsigned)
        if self._try_eat(TK.VOID):
            if unsigned:
                raise ParseError("unsigned void is invalid")
            return CVoid()
        # unsigned alone → unsigned int
        if unsigned:
            return CInt(unsigned=True)
        raise ParseError(f"Line {self._cur().line}: Expected type specifier")

    def _parse_struct_or_union(self, is_union: bool) -> CType:
        """Parse `struct [tag] [{ field; ... }]` or `union [tag] [{ ... }]`."""
        if is_union:
            self._eat(TK.UNION)
            registry = self._union_tags
        else:
            self._eat(TK.STRUCT)
            registry = self._struct_tags

        # optional tag
        tag = ''
        if self._at(TK.IDENT):
            tag = self._eat(TK.IDENT).value

        # look up or create the type record
        if tag and tag in registry:
            rec = registry[tag]
        else:
            rec = CUnion(tag) if is_union else CStruct(tag)
            if tag:
                registry[tag] = rec

        # optional body — mutates rec in-place so typedef aliases see the fields
        if self._at(TK.LBRACE):
            self._eat(TK.LBRACE)
            fields: list[StructField] = []
            offset = 0
            while not self._at(TK.RBRACE, TK.EOF):
                ftype, fname = self._parse_type_and_name()
                self._eat(TK.SEMICOLON)
                sf = StructField(fname, ftype, offset)
                fields.append(sf)
                # unions: all fields share offset 0; structs: fields are sequential
                if not is_union:
                    offset += ftype.size()
            self._eat(TK.RBRACE)
            rec.fields = fields
            rec.complete = True

        return rec

    def _parse_enum(self) -> CType:
        """Parse `enum [tag] [{ id [= const-expr], ... }]`. Treated as int."""
        self._eat(TK.ENUM)
        if self._at(TK.IDENT):
            self._eat(TK.IDENT)  # tag — accepted but not stored
        if self._try_eat(TK.LBRACE):
            value = 0
            while not self._at(TK.RBRACE, TK.EOF):
                name = self._eat(TK.IDENT).value
                if self._try_eat(TK.ASSIGN):
                    sign = -1 if self._try_eat(TK.MINUS) else 1
                    if self._at(TK.INT_LIT):
                        value = sign * self._eat(TK.INT_LIT).value
                    elif self._at(TK.IDENT) and self._cur().value in self._enum_consts:
                        value = sign * self._enum_consts[self._eat(TK.IDENT).value]
                    else:
                        raise ParseError(f"Line {self._cur().line}: enum initializer must be an integer constant")
                self._enum_consts[name] = value
                value += 1
                if not self._try_eat(TK.COMMA):
                    break
            self._eat(TK.RBRACE)
        return CInt()

    def _parse_type(self) -> CType:
        base = self._parse_base_type()
        while self._try_eat(TK.STAR):
            base = CPointer(base)
        return base

    def _parse_type_and_name(self) -> tuple[CType, str]:
        """Type + optional identifier. Also handles array brackets and function pointer declarators."""
        base = self._parse_base_type()
        # pointer modifiers
        stars = 0
        while self._try_eat(TK.STAR):
            stars += 1
        # function pointer declarator: ret (*name)(params)
        if self._at(TK.LPAREN) and self._peek().kind == TK.STAR:
            self._eat(TK.LPAREN)
            self._eat(TK.STAR)
            name = ''
            if self._at(TK.IDENT):
                name = self._eat(TK.IDENT).value
            self._eat(TK.RPAREN)
            params, variadic = self._parse_params()
            ret = base
            for _ in range(stars):
                ret = CPointer(ret)
            param_types = [p.ctype for p in params]
            t = CPointer(CFunction(ret, param_types, variadic))
            return t, name
        name = ''
        if self._at(TK.IDENT):
            name = self._eat(TK.IDENT).value
        # Apply pointer stars to base before building array so that
        # `int *arr[10]` correctly yields CArray(CPointer(CInt()), 10).
        elem = base
        for _ in range(stars):
            elem = CPointer(elem)
        # array modifiers
        if self._try_eat(TK.LBRACKET):
            if self._at(TK.INT_LIT):
                length = self._eat(TK.INT_LIT).value
            else:
                length = None
            self._eat(TK.RBRACKET)
            t = CArray(elem, length)
        else:
            t = elem
        return t, name

    # ── Top-Level Parsing ───────────────────────────────────────────────────────────

    def parse(self) -> Program:
        decls = []
        while not self._at(TK.EOF):
            decls.extend(self._parse_top_decl())
        return Program(decls)

    def _parse_typedef(self):
        """typedef <type> <name>; — registers alias in self._typedefs"""
        self._eat(TK.TYPEDEF)
        ret = self._parse_base_type()
        while self._try_eat(TK.STAR):
            ret = CPointer(ret)
        # function pointer typedef: typedef ret (*name)(params);
        if self._at(TK.LPAREN) and self._peek().kind == TK.STAR:
            self._eat(TK.LPAREN)
            self._eat(TK.STAR)
            alias = self._eat(TK.IDENT).value
            self._eat(TK.RPAREN)
            params, variadic = self._parse_params()
            param_types = [p.ctype for p in params]
            self._typedefs[alias] = CPointer(CFunction(ret, param_types, variadic))
        elif self._at(TK.IDENT):
            alias = self._eat(TK.IDENT).value
            self._typedefs[alias] = ret
        self._eat(TK.SEMICOLON)

    def _parse_attribute(self) -> Optional[str]:
        """Consume __attribute__((name)) if present and return the attribute name."""
        if not (self._at(TK.IDENT) and self._cur().value == '__attribute__'):
            return None
        self._eat(TK.IDENT)
        self._eat(TK.LPAREN)
        self._eat(TK.LPAREN)
        name = self._eat(TK.IDENT).value
        self._eat(TK.RPAREN)
        self._eat(TK.RPAREN)
        return name

    def _parse_top_decl(self) -> list:
        if self._at(TK.TYPEDEF):
            self._parse_typedef()
            return []

        # __attribute__((always_inline)) may appear before or after storage class
        attr1 = self._parse_attribute()
        is_static = bool(self._try_eat(TK.STATIC))
        is_extern = bool(self._try_eat(TK.EXTERN))
        attr2 = self._parse_attribute()
        is_always_inline = (attr1 == 'always_inline' or attr2 == 'always_inline')

        start_kind = self._cur().kind
        ret_type = self._parse_base_type()
        # `struct foo { ... };` / `enum E { ... };` with no declarator — type definition only.
        # Detect: the base type started with struct/union/enum AND ended on a `}` (had a body).
        was_aggregate_def = (start_kind in (TK.STRUCT, TK.UNION, TK.ENUM)
                             and self.pos > 0
                             and self.tokens[self.pos - 1].kind == TK.RBRACE)
        if self._at(TK.SEMICOLON) and (isinstance(ret_type, (CStruct, CUnion)) or was_aggregate_def):
            self._eat(TK.SEMICOLON)
            return []

        stars = 0
        while self._try_eat(TK.STAR):
            stars += 1
        for _ in range(stars):
            ret_type = CPointer(ret_type)

        name = self._eat(TK.IDENT).value

        if self._at(TK.LPAREN):
            # function declaration or definition
            params, is_variadic = self._parse_params()
            if self._try_eat(TK.SEMICOLON):
                body = None
            else:
                body = self._parse_block()
            return [FuncDecl(name, ret_type, params, body, is_static, is_variadic, is_always_inline)]
        else:
            # global variable
            results = []
            # handle array
            if self._try_eat(TK.LBRACKET):
                if self._at(TK.INT_LIT):
                    length = self._eat(TK.INT_LIT).value
                else:
                    length = None
                self._eat(TK.RBRACKET)
                vtype = CArray(ret_type, length)
            else:
                vtype = ret_type

            init = None
            if self._try_eat(TK.ASSIGN):
                if self._at(TK.LBRACE):
                    init = self._parse_init_list()
                else:
                    init = self._parse_expr()
            if isinstance(vtype, CArray) and vtype.length is None and isinstance(init, InitList):
                vtype = CArray(vtype.base, len(init.elems))
            results.append(VarDecl(name, vtype, init, is_global=True, is_static=is_static))

            while self._try_eat(TK.COMMA):
                extra_name = self._eat(TK.IDENT).value
                extra_init = None
                if self._try_eat(TK.ASSIGN):
                    if self._at(TK.LBRACE):
                        extra_init = self._parse_init_list()
                    else:
                        extra_init = self._parse_expr()
                results.append(VarDecl(extra_name, vtype, extra_init, is_global=True))

            self._eat(TK.SEMICOLON)
            return results

    def _parse_params(self) -> list[ParamDecl]:
        self._eat(TK.LPAREN)
        params = []
        is_variadic = False
        if self._try_eat(TK.VOID) and self._at(TK.RPAREN):
            self._eat(TK.RPAREN)
            return params, False
        if not self._at(TK.RPAREN):
            while True:
                if self._at(TK.ELLIPSIS):
                    self._eat(TK.ELLIPSIS)
                    is_variadic = True
                    break
                elif self._at_type_start():
                    ptype, pname = self._parse_type_and_name()
                    params.append(ParamDecl(pname or f'_p{len(params)}', ptype))
                    if not self._try_eat(TK.COMMA):
                        break
                else:
                    break
        self._eat(TK.RPAREN)
        return params, is_variadic

    # ── Statement Parsing ─────────────────────────────────────────────────────────────

    def _parse_block(self) -> Block:
        self._eat(TK.LBRACE)
        stmts = []
        while not self._at(TK.RBRACE, TK.EOF):
            result = self._parse_stmt()
            if isinstance(result, list):
                stmts.extend(result)
            else:
                stmts.append(result)
        self._eat(TK.RBRACE)
        return Block(stmts)

    def _parse_stmt(self) -> Stmt:
        tok = self._cur()

        if self._at(TK.LBRACE):
            return self._parse_block()

        if self._at(TK.IF):
            return self._stamp(self._parse_if(), tok)

        if self._at(TK.WHILE):
            return self._stamp(self._parse_while(), tok)

        if self._at(TK.DO):
            return self._stamp(self._parse_do_while(), tok)

        if self._at(TK.FOR):
            return self._stamp(self._parse_for(), tok)

        if self._try_eat(TK.RETURN):
            expr = None
            if not self._at(TK.SEMICOLON):
                expr = self._parse_expr()
            self._eat(TK.SEMICOLON)
            return self._stamp(ReturnStmt(expr), tok)

        if self._try_eat(TK.BREAK):
            self._eat(TK.SEMICOLON)
            return self._stamp(BreakStmt(), tok)

        if self._try_eat(TK.CONTINUE):
            self._eat(TK.SEMICOLON)
            return self._stamp(ContinueStmt(), tok)

        if self._at(TK.ASM):
            return self._stamp(self._parse_asm(), tok)

        # local variable declaration
        if self._at_type_start():
            decls = self._parse_local_decl()
            for d in decls:
                self._stamp(d, tok)
            return decls

        # expression statement
        expr = self._parse_expr()
        self._eat(TK.SEMICOLON)
        return self._stamp(ExprStmt(expr), tok)

    def _parse_if(self) -> IfStmt:
        self._eat(TK.IF)
        self._eat(TK.LPAREN)
        cond = self._parse_expr()
        self._eat(TK.RPAREN)
        then = self._parse_stmt()
        else_ = None
        if self._try_eat(TK.ELSE):
            else_ = self._parse_stmt()
        return IfStmt(cond, then, else_)

    def _parse_asm(self) -> AsmStmt:
        # asm("template")  or  asm("template" : "r"(e), ...)
        self._eat(TK.ASM)
        self._eat(TK.LPAREN)
        template_chars = self._eat(TK.STRING_LIT).value
        template = ''.join(chr(c) for c in template_chars)
        inputs = []
        if self._try_eat(TK.COLON):
            while not self._at(TK.RPAREN):
                # consume constraint string, e.g. "r"
                self._eat(TK.STRING_LIT)
                self._eat(TK.LPAREN)
                inputs.append(self._parse_expr())
                self._eat(TK.RPAREN)
                if not self._try_eat(TK.COMMA):
                    break
        self._eat(TK.RPAREN)
        self._eat(TK.SEMICOLON)
        return AsmStmt(template, inputs)

    def _parse_while(self) -> WhileStmt:
        self._eat(TK.WHILE)
        self._eat(TK.LPAREN)
        cond = self._parse_expr()
        self._eat(TK.RPAREN)
        body = self._parse_stmt()
        return WhileStmt(cond, body)

    def _parse_do_while(self) -> DoWhileStmt:
        self._eat(TK.DO)
        body = self._parse_stmt()
        self._eat(TK.WHILE)
        self._eat(TK.LPAREN)
        cond = self._parse_expr()
        self._eat(TK.RPAREN)
        self._eat(TK.SEMICOLON)
        return DoWhileStmt(body, cond)

    def _parse_for(self) -> ForStmt:
        self._eat(TK.FOR)
        self._eat(TK.LPAREN)
        # init
        if self._at(TK.SEMICOLON):
            self._eat(TK.SEMICOLON)
            init = None
        elif self._at_type_start():
            decls = self._parse_local_decl()
            init = decls[0] if len(decls) == 1 else Block(decls)
        else:
            init = ExprStmt(self._parse_expr())
            self._eat(TK.SEMICOLON)
        # cond
        if self._at(TK.SEMICOLON):
            cond = None
        else:
            cond = self._parse_expr()
        self._eat(TK.SEMICOLON)
        # step
        if self._at(TK.RPAREN):
            step = None
        else:
            step = self._parse_expr()
        self._eat(TK.RPAREN)
        body = self._parse_stmt()
        return ForStmt(init, cond, step, body)

    def _parse_init_list(self) -> InitList:
        self._eat(TK.LBRACE)
        elems = []
        while not self._at(TK.RBRACE, TK.EOF):
            elems.append(self._parse_assign())
            if not self._try_eat(TK.COMMA):
                break
        self._eat(TK.RBRACE)
        return InitList(elems)

    def _parse_local_decl(self) -> list:
        vtype, name = self._parse_type_and_name()
        # struct/union type-only declaration inside a block (`struct foo { ... };`)
        if not name and isinstance(vtype, (CStruct, CUnion)):
            self._eat(TK.SEMICOLON)
            raise ParseError(f"Line {self._cur().line}: type-only declaration inside block has no effect")
        results = []
        init = None
        if self._try_eat(TK.ASSIGN):
            if self._at(TK.LBRACE):
                init = self._parse_init_list()
            else:
                init = self._parse_assign()
        # infer array length from initializer if [] was used
        if isinstance(vtype, CArray) and vtype.length is None:
            if isinstance(init, InitList):
                vtype = CArray(vtype.base, len(init.elems))
            elif isinstance(init, StringLit):
                vtype = CArray(vtype.base, len(init.chars) + 1)  # +1 for null terminator
        results.append(DeclStmt(VarDecl(name, vtype, init, is_global=False)))
        # multi-declaration: int x = 1, y, z = 3;
        while self._try_eat(TK.COMMA):
            extra_name = self._eat(TK.IDENT).value
            extra_init = None
            if self._try_eat(TK.ASSIGN):
                if self._at(TK.LBRACE):
                    extra_init = self._parse_init_list()
                else:
                    extra_init = self._parse_assign()
            results.append(DeclStmt(VarDecl(extra_name, vtype, extra_init, is_global=False)))
        self._eat(TK.SEMICOLON)
        return results

    # ── Expression Parsing (operator precedence) ─────────────────────────────────────────

    def _parse_expr(self) -> Expr:
        return self._parse_assign()

    def _parse_assign(self) -> Expr:
        left = self._parse_ternary()
        op_map = {
            TK.ASSIGN:       '=',
            TK.PLUS_ASSIGN:  '+=',
            TK.MINUS_ASSIGN: '-=',
            TK.STAR_ASSIGN:  '*=',
            TK.SLASH_ASSIGN: '/=',
            TK.PERCENT_ASSIGN: '%=',
            TK.AMP_ASSIGN:   '&=',
            TK.PIPE_ASSIGN:  '|=',
            TK.CARET_ASSIGN: '^=',
            TK.LSHIFT_ASSIGN: '<<=',
            TK.RSHIFT_ASSIGN: '>>=',
        }
        if self._cur().kind in op_map:
            op = op_map[self._eat(self._cur().kind).kind]
            right = self._parse_assign()
            return Assign(op, left, right)
        return left

    def _parse_ternary(self) -> Expr:
        cond = self._parse_or()
        if self._try_eat(TK.QUESTION):
            then_expr = self._parse_expr()
            self._eat(TK.COLON)
            else_expr = self._parse_expr()
            return Ternary(cond, then_expr, else_expr)
        return cond

    def _parse_or(self) -> Expr:
        left = self._parse_and()
        while self._at(TK.OR):
            self._eat(TK.OR)
            right = self._parse_and()
            left = BinOp('||', left, right)
        return left

    def _parse_and(self) -> Expr:
        left = self._parse_bitor()
        while self._at(TK.AND):
            self._eat(TK.AND)
            right = self._parse_bitor()
            left = BinOp('&&', left, right)
        return left

    def _parse_bitor(self) -> Expr:
        left = self._parse_bitxor()
        while self._at(TK.PIPE):
            self._eat(TK.PIPE)
            right = self._parse_bitxor()
            left = BinOp('|', left, right)
        return left

    def _parse_bitxor(self) -> Expr:
        left = self._parse_bitand()
        while self._at(TK.CARET):
            self._eat(TK.CARET)
            right = self._parse_bitand()
            left = BinOp('^', left, right)
        return left

    def _parse_bitand(self) -> Expr:
        left = self._parse_eq()
        while self._at(TK.AMP):
            self._eat(TK.AMP)
            right = self._parse_eq()
            left = BinOp('&', left, right)
        return left

    def _parse_eq(self) -> Expr:
        left = self._parse_rel()
        while self._at(TK.EQ, TK.NEQ):
            tok = self._eat(TK.EQ, TK.NEQ)
            op = '==' if tok.kind == TK.EQ else '!='
            right = self._parse_rel()
            left = BinOp(op, left, right)
        return left

    def _parse_rel(self) -> Expr:
        left = self._parse_shift()
        rel_map = {TK.LT: '<', TK.GT: '>', TK.LTE: '<=', TK.GTE: '>='}
        while self._cur().kind in rel_map:
            op = rel_map[self._eat(self._cur().kind).kind]
            right = self._parse_shift()
            left = BinOp(op, left, right)
        return left

    def _parse_shift(self) -> Expr:
        left = self._parse_add()
        while self._at(TK.LSHIFT, TK.RSHIFT):
            op = '<<' if self._eat(TK.LSHIFT, TK.RSHIFT).kind == TK.LSHIFT else '>>'
            right = self._parse_add()
            left = BinOp(op, left, right)
        return left

    def _parse_add(self) -> Expr:
        left = self._parse_mul()
        while self._at(TK.PLUS, TK.MINUS):
            op = '+' if self._eat(TK.PLUS, TK.MINUS).kind == TK.PLUS else '-'
            right = self._parse_mul()
            left = BinOp(op, left, right)
        return left

    def _parse_mul(self) -> Expr:
        left = self._parse_unary()
        while self._at(TK.STAR, TK.SLASH, TK.PERCENT):
            tok = self._eat(TK.STAR, TK.SLASH, TK.PERCENT)
            op = {TK.STAR: '*', TK.SLASH: '/', TK.PERCENT: '%'}[tok.kind]
            right = self._parse_unary()
            left = BinOp(op, left, right)
        return left

    def _parse_unary(self) -> Expr:
        if self._at(TK.MINUS):
            self._eat(TK.MINUS)
            return UnaryOp('-', self._parse_unary())
        if self._at(TK.TILDE):
            self._eat(TK.TILDE)
            return UnaryOp('~', self._parse_unary())
        if self._at(TK.BANG):
            self._eat(TK.BANG)
            return UnaryOp('!', self._parse_unary())
        if self._at(TK.AMP):
            self._eat(TK.AMP)
            return UnaryOp('&', self._parse_unary())
        if self._at(TK.STAR):
            self._eat(TK.STAR)
            return UnaryOp('*', self._parse_unary())
        if self._at(TK.INC):
            self._eat(TK.INC)
            return UnaryOp('++pre', self._parse_unary())
        if self._at(TK.DEC):
            self._eat(TK.DEC)
            return UnaryOp('--pre', self._parse_unary())
        if self._at(TK.SIZEOF):
            self._eat(TK.SIZEOF)
            # sizeof(type)  vs  sizeof expr
            if self._at(TK.LPAREN) and (self._peek().kind in self.TYPE_STARTS or
                    (self._peek().kind == TK.IDENT and (self._peek().value in self._TYPE_IDENTS
                                                         or self._peek().value in self._typedefs))):
                self._eat(TK.LPAREN)
                t = self._parse_type()
                self._eat(TK.RPAREN)
                return SizeOf(t)
            return SizeOf(self._parse_unary())
        # cast: (type)expr
        if self._at(TK.LPAREN) and (self._peek().kind in self.TYPE_STARTS or
                (self._peek().kind == TK.IDENT and (self._peek().value in self._TYPE_IDENTS
                                                     or self._peek().value in self._typedefs))):
            self._eat(TK.LPAREN)
            t = self._parse_type()
            self._eat(TK.RPAREN)
            return Cast(t, self._parse_unary())
        return self._parse_postfix()

    def _parse_postfix(self) -> Expr:
        node = self._parse_primary()
        while True:
            if self._at(TK.LPAREN):
                # function call
                self._eat(TK.LPAREN)
                args = []
                if not self._at(TK.RPAREN):
                    args.append(self._parse_assign())
                    while self._try_eat(TK.COMMA):
                        args.append(self._parse_assign())
                self._eat(TK.RPAREN)
                node = Call(node, args)
            elif self._at(TK.LBRACKET):
                # array index
                self._eat(TK.LBRACKET)
                idx = self._parse_expr()
                self._eat(TK.RBRACKET)
                node = Index(node, idx)
            elif self._at(TK.DOT):
                self._eat(TK.DOT)
                field = self._eat(TK.IDENT).value
                node = Member(node, field, arrow=False)
            elif self._at(TK.ARROW):
                self._eat(TK.ARROW)
                field = self._eat(TK.IDENT).value
                node = Member(node, field, arrow=True)
            elif self._at(TK.INC):
                self._eat(TK.INC)
                node = UnaryOp('++post', node)
            elif self._at(TK.DEC):
                self._eat(TK.DEC)
                node = UnaryOp('--post', node)
            else:
                break
        return node

    def _parse_primary(self) -> Expr:
        tok = self._cur()

        if tok.kind == TK.INT_LIT:
            self._eat(TK.INT_LIT)
            return IntLit(tok.value)

        if tok.kind == TK.CHAR_LIT:
            self._eat(TK.CHAR_LIT)
            return CharLit(tok.value)

        if tok.kind == TK.STRING_LIT:
            self._eat(TK.STRING_LIT)
            return StringLit(tok.value)

        if tok.kind == TK.IDENT:
            self._eat(TK.IDENT)
            # __builtin_va_arg(ap, type) is a built-in that takes a type argument
            if tok.value == '__builtin_va_arg' and self._at(TK.LPAREN):
                self._eat(TK.LPAREN)
                ap = self._parse_assign()
                self._eat(TK.COMMA)
                arg_type = self._parse_type()
                self._eat(TK.RPAREN)
                return VaArg(ap, arg_type)
            # enum constant: substitute integer literal at parse time
            if tok.value in self._enum_consts:
                return IntLit(self._enum_consts[tok.value])
            return Ident(tok.value, line=tok.line, filename=tok.filename)

        if tok.kind == TK.LPAREN:
            self._eat(TK.LPAREN)
            expr = self._parse_expr()
            self._eat(TK.RPAREN)
            return expr

        loc = f'{tok.filename}:{tok.line}' if tok.filename else f'Line {tok.line}'
        raise ParseError(
            f"{loc}:{tok.col}: Unexpected token {tok.kind.name} ({tok.value!r})"
        )

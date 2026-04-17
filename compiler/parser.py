"""
C to R316 Compiler - Parser
Token stream -> AST
"""

from lexer import TK, Token
from ast_nodes import *

# Enum constants registry: name -> int value (populated during parsing)
_enum_consts: dict[str, int] = {}

# Typedef registry: alias name -> CType
_typedefs: dict[str, 'CType'] = {}


class ParseError(Exception):
    pass


class Parser:
    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.pos    = 0

    # ── Utilities ─────────────────────────────────────────────────────────────

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
            raise ParseError(
                f"Line {tok.line}:{tok.col}: Expected {exp}, got {tok.kind.name} ({tok.value!r})"
            )
        self.pos += 1
        return tok

    def _try_eat(self, *kinds) -> Optional[Token]:
        if self._at(*kinds):
            return self._eat(*kinds)
        return None

    # ── Type parsing ──────────────────────────────────────────────────────────

    TYPE_STARTS = {TK.INT, TK.LONG, TK.CHAR, TK.VOID, TK.UNSIGNED, TK.STRUCT}

    def _at_type_start(self) -> bool:
        """Returns True if the current token can start a type (including typedef aliases)"""
        if self._at(*self.TYPE_STARTS):
            return True
        return self._at(TK.IDENT) and self._cur().value in _typedefs

    def _parse_base_type(self) -> CType:
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
        if self._at(TK.STRUCT):
            self._eat(TK.STRUCT)
            # optional tag name
            if self._at(TK.IDENT):
                self.pos += 1
            # optional body — skip
            if self._at(TK.LBRACE):
                depth = 0
                while not self._at(TK.EOF):
                    if self._at(TK.LBRACE):
                        depth += 1
                    elif self._at(TK.RBRACE):
                        depth -= 1
                        self.pos += 1
                        if depth == 0:
                            break
                        continue
                    self.pos += 1
            return CInt()  # struct -> treated as int (pointer-sized) for now
        # typedef alias
        if not unsigned and self._at(TK.IDENT) and self._cur().value in _typedefs:
            tok = self._eat(TK.IDENT)
            return _typedefs[tok.value]
        # bare 'unsigned' -> unsigned int
        if unsigned:
            return CInt(unsigned=True)
        raise ParseError(f"Line {self._cur().line}: Expected type specifier")

    def _parse_type(self) -> CType:
        base = self._parse_base_type()
        while self._try_eat(TK.STAR):
            base = CPointer(base)
        return base

    def _parse_type_and_name(self) -> tuple[CType, str]:
        """Parse a type followed by an optional name. Handles array brackets."""
        base = self._parse_base_type()
        # pointer modifiers
        stars = 0
        while self._try_eat(TK.STAR):
            stars += 1
        name = ''
        if self._at(TK.IDENT):
            name = self._eat(TK.IDENT).value
        # array modifiers
        if self._try_eat(TK.LBRACKET):
            if self._at(TK.INT_LIT):
                length = self._eat(TK.INT_LIT).value
            else:
                length = None
            self._eat(TK.RBRACKET)
            t = CArray(base, length)
        else:
            t = base
        for _ in range(stars):
            t = CPointer(t) if not isinstance(t, CArray) else t
        if stars and not isinstance(t, (CPointer, CArray)):
            t = CPointer(t)
        # apply stars to type (array takes precedence)
        if stars and isinstance(t, CArray):
            pass  # array wins
        elif stars:
            inner = base
            for _ in range(stars):
                inner = CPointer(inner)
            t = inner
        return t, name

    # ── Top-level parsing ─────────────────────────────────────────────────────

    def parse(self) -> Program:
        decls = []
        while not self._at(TK.EOF):
            decls.extend(self._parse_top_decl())
        return Program(decls)

    def _parse_top_decl(self) -> list:
        # typedef
        if self._at(TK.TYPEDEF):
            self._parse_typedef()
            return []

        # enum definition at top level: enum Name { ... };
        if self._at(TK.ENUM):
            self._parse_enum_def()
            return []

        is_static = bool(self._try_eat(TK.STATIC))
        is_extern = bool(self._try_eat(TK.EXTERN))

        ret_type = self._parse_base_type()
        stars = 0
        while self._try_eat(TK.STAR):
            stars += 1
        for _ in range(stars):
            ret_type = CPointer(ret_type)

        name = self._eat(TK.IDENT).value

        if self._at(TK.LPAREN):
            # function declaration or definition
            params, variadic = self._parse_params()
            if self._try_eat(TK.SEMICOLON):
                body = None
            else:
                body = self._parse_block()
            return [FuncDecl(name, ret_type, params, body, is_static, variadic)]
        else:
            # global variable
            results = []
            # array handling
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
                init = self._parse_init()
            results.append(VarDecl(name, vtype, init, is_global=True, is_static=is_static))

            while self._try_eat(TK.COMMA):
                extra_name = self._eat(TK.IDENT).value
                extra_init = None
                if self._try_eat(TK.ASSIGN):
                    extra_init = self._parse_expr()
                results.append(VarDecl(extra_name, vtype, extra_init, is_global=True))

            self._eat(TK.SEMICOLON)
            return results

    def _parse_typedef(self):
        """typedef <type> <name>; — registers alias in _typedefs"""
        self._eat(TK.TYPEDEF)
        # Parse the underlying type (struct body is skipped for now)
        if self._at(TK.STRUCT):
            # struct typedef: consume until '}' then grab alias name
            depth = 0
            while not self._at(TK.EOF):
                if self._at(TK.LBRACE):
                    depth += 1
                    self.pos += 1
                elif self._at(TK.RBRACE):
                    depth -= 1
                    self.pos += 1
                    if depth == 0:
                        break
                elif self._at(TK.SEMICOLON) and depth == 0:
                    break
                else:
                    self.pos += 1
            # alias name before semicolon
            if self._at(TK.IDENT):
                alias = self._eat(TK.IDENT).value
                _typedefs[alias] = CInt()  # struct -> treated as int for now
        elif self._at(*self.TYPE_STARTS):
            ctype, alias = self._parse_type_and_name()
            if alias:
                _typedefs[alias] = ctype
        else:
            # unknown form — skip to semicolon
            while not self._at(TK.SEMICOLON, TK.EOF):
                self.pos += 1
        self._eat(TK.SEMICOLON)

    def _parse_enum_def(self):
        """enum [Name] { A=0, B, ... }; — registers constants in _enum_consts"""
        self._eat(TK.ENUM)
        # optional tag name
        if self._at(TK.IDENT):
            self.pos += 1
        self._eat(TK.LBRACE)
        val = 0
        while not self._at(TK.RBRACE, TK.EOF):
            name = self._eat(TK.IDENT).value
            if self._try_eat(TK.ASSIGN):
                tok = self._eat(TK.INT_LIT)
                val = tok.value
            _enum_consts[name] = val
            val += 1
            if not self._try_eat(TK.COMMA):
                break
        self._eat(TK.RBRACE)
        self._eat(TK.SEMICOLON)

    def _parse_params(self) -> tuple[list[ParamDecl], bool]:
        """Parse parameter list. Returns (params, is_variadic)."""
        self._eat(TK.LPAREN)
        params = []
        variadic = False
        if self._try_eat(TK.VOID) and self._at(TK.RPAREN):
            self._eat(TK.RPAREN)
            return params, False
        if not self._at(TK.RPAREN):
            while True:
                if self._at(TK.ELLIPSIS):
                    self._eat(TK.ELLIPSIS)
                    variadic = True
                    break
                if self._at_type_start():
                    ptype, pname = self._parse_type_and_name()
                    params.append(ParamDecl(pname or f'_p{len(params)}', ptype))
                    if not self._try_eat(TK.COMMA):
                        break
                else:
                    break
        self._eat(TK.RPAREN)
        return params, variadic

    # ── Statement parsing ─────────────────────────────────────────────────────

    def _parse_block(self) -> Block:
        self._eat(TK.LBRACE)
        stmts = []
        while not self._at(TK.RBRACE, TK.EOF):
            stmts.append(self._parse_stmt())
        self._eat(TK.RBRACE)
        return Block(stmts)

    def _parse_stmt(self) -> Stmt:
        cur = self._cur()

        if self._at(TK.LBRACE):
            return self._parse_block()

        if self._at(TK.IF):
            return self._parse_if()

        if self._at(TK.WHILE):
            return self._parse_while()

        if self._at(TK.FOR):
            return self._parse_for()

        if self._at(TK.DO):
            return self._parse_do_while()

        if self._at(TK.SWITCH):
            return self._parse_switch()

        if self._at(TK.GOTO):
            self._eat(TK.GOTO)
            lbl = self._eat(TK.IDENT).value
            self._eat(TK.SEMICOLON)
            return GotoStmt(lbl)

        # label: IDENT ':'
        if self._at(TK.IDENT) and self._peek().kind == TK.COLON:
            lbl = self._eat(TK.IDENT).value
            self._eat(TK.COLON)
            inner = self._parse_stmt()
            return LabelStmt(lbl, inner)

        if self._try_eat(TK.RETURN):
            expr = None
            if not self._at(TK.SEMICOLON):
                expr = self._parse_expr()
            self._eat(TK.SEMICOLON)
            return ReturnStmt(expr)

        if self._try_eat(TK.BREAK):
            self._eat(TK.SEMICOLON)
            return BreakStmt()

        if self._try_eat(TK.CONTINUE):
            self._eat(TK.SEMICOLON)
            return ContinueStmt()

        # enum definition inside a function
        if self._at(TK.ENUM):
            self._parse_enum_def()
            return Block([])  # no-op

        # local variable declaration
        if self._at_type_start():
            return self._parse_local_decl()

        # expression statement
        expr = self._parse_expr()
        self._eat(TK.SEMICOLON)
        return ExprStmt(expr)

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

    def _parse_while(self) -> WhileStmt:
        self._eat(TK.WHILE)
        self._eat(TK.LPAREN)
        cond = self._parse_expr()
        self._eat(TK.RPAREN)
        body = self._parse_stmt()
        return WhileStmt(cond, body)

    def _parse_for(self) -> ForStmt:
        self._eat(TK.FOR)
        self._eat(TK.LPAREN)
        # init
        if self._at(TK.SEMICOLON):
            self._eat(TK.SEMICOLON)
            init = None
        elif self._at_type_start():
            init = self._parse_local_decl()
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

    def _parse_do_while(self) -> DoWhileStmt:
        self._eat(TK.DO)
        body = self._parse_stmt()
        self._eat(TK.WHILE)
        self._eat(TK.LPAREN)
        cond = self._parse_expr()
        self._eat(TK.RPAREN)
        self._eat(TK.SEMICOLON)
        return DoWhileStmt(body, cond)

    def _parse_switch(self) -> SwitchStmt:
        self._eat(TK.SWITCH)
        self._eat(TK.LPAREN)
        expr = self._parse_expr()
        self._eat(TK.RPAREN)
        self._eat(TK.LBRACE)
        cases = []
        while not self._at(TK.RBRACE, TK.EOF):
            # case N: or default:
            if self._at(TK.CASE):
                self._eat(TK.CASE)
                val = self._eat(TK.INT_LIT).value
                self._eat(TK.COLON)
                cases.append(SwitchCase(val, []))
            elif self._at(TK.DEFAULT):
                self._eat(TK.DEFAULT)
                self._eat(TK.COLON)
                cases.append(SwitchCase(None, []))
            else:
                if not cases:
                    raise ParseError(f"Line {self._cur().line}: Statement before first case in switch")
                cases[-1].stmts.append(self._parse_stmt())
        self._eat(TK.RBRACE)
        return SwitchStmt(expr, cases)

    def _parse_local_decl(self) -> DeclStmt:
        base = self._parse_base_type()
        is_static = False
        stars = 0
        while self._try_eat(TK.STAR):
            stars += 1
        name = self._eat(TK.IDENT).value
        # array
        if self._try_eat(TK.LBRACKET):
            if self._at(TK.INT_LIT):
                length = self._eat(TK.INT_LIT).value
            else:
                length = None
            self._eat(TK.RBRACKET)
            vtype = CArray(base, length)
        else:
            vtype = base
            for _ in range(stars):
                vtype = CPointer(vtype)
        init = None
        if self._try_eat(TK.ASSIGN):
            init = self._parse_init()
        self._eat(TK.SEMICOLON)
        return DeclStmt(VarDecl(name, vtype, init, is_global=False))

    def _parse_init(self) -> Expr:
        """Parse an initializer (after '='). Accepts {1,2,3} brace lists."""
        if self._at(TK.LBRACE):
            self._eat(TK.LBRACE)
            items = []
            while not self._at(TK.RBRACE):
                items.append(self._parse_assign())
                if not self._try_eat(TK.COMMA):
                    break
            self._eat(TK.RBRACE)
            return InitList(items)
        return self._parse_expr()

    # ── Expression parsing (operator precedence) ──────────────────────────────

    def _parse_expr(self) -> Expr:
        return self._parse_assign()

    def _parse_assign(self) -> Expr:
        left = self._parse_ternary()
        op_map = {
            TK.ASSIGN:        '=',
            TK.PLUS_ASSIGN:   '+=',
            TK.MINUS_ASSIGN:  '-=',
            TK.STAR_ASSIGN:   '*=',
            TK.SLASH_ASSIGN:  '/=',
            TK.MOD_ASSIGN:    '%=',
            TK.AMP_ASSIGN:    '&=',
            TK.PIPE_ASSIGN:   '|=',
            TK.CARET_ASSIGN:  '^=',
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
        if not self._try_eat(TK.QUESTION):
            return cond
        then = self._parse_assign()
        self._eat(TK.COLON)
        else_ = self._parse_ternary()   # right-associative
        return Ternary(cond, then, else_)

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
        # cast: (type)expr
        if self._at(TK.LPAREN) and (self._peek().kind in self.TYPE_STARTS or
                (self._peek().kind == TK.IDENT and self._peek().value in _typedefs)):
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
                # va_arg(ap, type) — second argument may be a type expression
                is_va_arg = isinstance(node, Ident) and node.name == 'va_arg'
                if not self._at(TK.RPAREN):
                    args.append(self._parse_assign())
                    while self._try_eat(TK.COMMA):
                        if is_va_arg and self._at(*self.TYPE_STARTS):
                            self._parse_type()  # consume type argument and discard
                        else:
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
            # enum constant?
            if tok.value in _enum_consts:
                return IntLit(_enum_consts[tok.value])
            return Ident(tok.value)

        if tok.kind == TK.LPAREN:
            self._eat(TK.LPAREN)
            expr = self._parse_expr()
            self._eat(TK.RPAREN)
            return expr

        raise ParseError(
            f"Line {tok.line}:{tok.col}: Unexpected token {tok.kind.name} ({tok.value!r})"
        )

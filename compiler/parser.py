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

    # ── Type Parsing ─────────────────────────────────────────────────────────────

    TYPE_STARTS = {TK.INT, TK.LONG, TK.CHAR, TK.VOID, TK.UNSIGNED}

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
        # unsigned alone → unsigned int
        if unsigned:
            return CInt(unsigned=True)
        raise ParseError(f"Line {self._cur().line}: Expected type specifier")

    def _parse_type(self) -> CType:
        base = self._parse_base_type()
        while self._try_eat(TK.STAR):
            base = CPointer(base)
        return base

    def _parse_type_and_name(self) -> tuple[CType, str]:
        """Type + optional identifier. Also handles array brackets."""
        base = self._parse_base_type()
        # pointer modifiers
        stars = 0
        while self._try_eat(TK.STAR):
            stars += 1
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

    def _parse_top_decl(self) -> list:
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
            params = self._parse_params()
            if self._try_eat(TK.SEMICOLON):
                body = None
            else:
                body = self._parse_block()
            return [FuncDecl(name, ret_type, params, body, is_static)]
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
                init = self._parse_expr()
            results.append(VarDecl(name, vtype, init, is_global=True, is_static=is_static))

            while self._try_eat(TK.COMMA):
                extra_name = self._eat(TK.IDENT).value
                extra_init = None
                if self._try_eat(TK.ASSIGN):
                    extra_init = self._parse_expr()
                results.append(VarDecl(extra_name, vtype, extra_init, is_global=True))

            self._eat(TK.SEMICOLON)
            return results

    def _parse_params(self) -> list[ParamDecl]:
        self._eat(TK.LPAREN)
        params = []
        if self._try_eat(TK.VOID) and self._at(TK.RPAREN):
            self._eat(TK.RPAREN)
            return params
        if not self._at(TK.RPAREN):
            while True:
                if self._at(*self.TYPE_STARTS):
                    ptype, pname = self._parse_type_and_name()
                    params.append(ParamDecl(pname or f'_p{len(params)}', ptype))
                    if not self._try_eat(TK.COMMA):
                        break
                else:
                    break
        self._eat(TK.RPAREN)
        return params

    # ── Statement Parsing ─────────────────────────────────────────────────────────────

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

        if self._at(TK.DO):
            return self._parse_do_while()

        if self._at(TK.FOR):
            return self._parse_for()

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

        if self._at(TK.ASM):
            return self._parse_asm()

        # local variable declaration
        if self._at(*self.TYPE_STARTS):
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
        elif self._at(*self.TYPE_STARTS):
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
            init = self._parse_expr()
        self._eat(TK.SEMICOLON)
        return DeclStmt(VarDecl(name, vtype, init, is_global=False))

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
        # cast: (type)expr
        if self._at(TK.LPAREN) and self._peek().kind in self.TYPE_STARTS:
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
            return Ident(tok.value)

        if tok.kind == TK.LPAREN:
            self._eat(TK.LPAREN)
            expr = self._parse_expr()
            self._eat(TK.RPAREN)
            return expr

        raise ParseError(
            f"Line {tok.line}:{tok.col}: Unexpected token {tok.kind.name} ({tok.value!r})"
        )

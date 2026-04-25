"""
C to R316 Compiler - Lexer
Token types and lexer implementation
"""

import re
from enum import Enum, auto


class TK(Enum):
    # literals
    INT_LIT    = auto()
    CHAR_LIT   = auto()
    STRING_LIT = auto()
    IDENT      = auto()

    # keywords
    INT        = auto()
    LONG       = auto()
    CHAR       = auto()
    VOID       = auto()
    IF         = auto()
    ELSE       = auto()
    WHILE      = auto()
    DO         = auto()
    FOR        = auto()
    RETURN     = auto()
    BREAK      = auto()
    CONTINUE   = auto()
    UNSIGNED   = auto()
    STRUCT     = auto()
    UNION      = auto()
    TYPEDEF    = auto()
    EXTERN     = auto()
    STATIC     = auto()
    ASM        = auto()
    SIZEOF     = auto()
    ENUM       = auto()
    GOTO       = auto()

    # operators
    PLUS       = auto()   # +
    MINUS      = auto()   # -
    STAR       = auto()   # *
    SLASH      = auto()   # /
    PERCENT    = auto()   # %
    AMP        = auto()   # &
    PIPE       = auto()   # |
    CARET      = auto()   # ^
    TILDE      = auto()   # ~
    BANG       = auto()   # !
    LSHIFT     = auto()   # <<
    RSHIFT     = auto()   # >>
    LSHIFT_ASSIGN = auto() # <<=
    RSHIFT_ASSIGN = auto() # >>=
    AND        = auto()   # &&
    OR         = auto()   # ||
    EQ         = auto()   # ==
    NEQ        = auto()   # !=
    LT         = auto()   # <
    GT         = auto()   # >
    LTE        = auto()   # <=
    GTE        = auto()   # >=
    ASSIGN     = auto()   # =
    PLUS_ASSIGN  = auto() # +=
    MINUS_ASSIGN = auto() # -=
    STAR_ASSIGN  = auto() # *=
    SLASH_ASSIGN = auto() # /=
    AMP_ASSIGN   = auto() # &=
    PIPE_ASSIGN  = auto() # |=
    CARET_ASSIGN = auto() # ^=
    PERCENT_ASSIGN = auto() # %=
    INC        = auto()   # ++
    DEC        = auto()   # --
    ARROW      = auto()   # ->

    # delimiters
    LPAREN     = auto()   # (
    RPAREN     = auto()   # )
    LBRACE     = auto()   # {
    RBRACE     = auto()   # }
    LBRACKET   = auto()   # [
    RBRACKET   = auto()   # ]
    SEMICOLON  = auto()   # ;
    COLON      = auto()   # :
    QUESTION   = auto()   # ?
    COMMA      = auto()   # ,
    DOT        = auto()   # .
    ELLIPSIS   = auto()   # ...

    EOF        = auto()


KEYWORDS = {
    'int':      TK.INT,
    'long':     TK.LONG,
    'char':     TK.CHAR,
    'void':     TK.VOID,
    'if':       TK.IF,
    'else':     TK.ELSE,
    'while':    TK.WHILE,
    'do':       TK.DO,
    'for':      TK.FOR,
    'return':   TK.RETURN,
    'break':    TK.BREAK,
    'continue': TK.CONTINUE,
    'unsigned': TK.UNSIGNED,
    'struct':   TK.STRUCT,
    'union':    TK.UNION,
    'typedef':  TK.TYPEDEF,
    'extern':   TK.EXTERN,
    'static':   TK.STATIC,
    'asm':      TK.ASM,
    '__asm__':  TK.ASM,
    'sizeof':   TK.SIZEOF,
    'enum':     TK.ENUM,
    'goto':     TK.GOTO,
}


class Token:
    def __init__(self, kind, value, line, col, filename=''):
        self.kind     = kind
        self.value    = value
        self.line     = line
        self.col      = col
        self.filename = filename

    def __repr__(self):
        return f'Token({self.kind}, {self.value!r}, {self.line}:{self.col})'


class LexError(Exception):
    pass


class Lexer:
    def __init__(self, src: str, filename: str = ''):
        self.src      = src
        self.pos      = 0
        self.line     = 1
        self.col      = 1
        self.filename = filename
        self.tokens   = []
        self._tokenize()

    def _cur(self):
        if self.pos < len(self.src):
            return self.src[self.pos]
        return ''

    def _peek(self, offset=1):
        p = self.pos + offset
        if p < len(self.src):
            return self.src[p]
        return ''

    def _advance(self):
        ch = self.src[self.pos]
        self.pos += 1
        if ch == '\n':
            self.line += 1
            self.col = 1
        else:
            self.col += 1
        return ch

    def _skip_whitespace_and_comments(self):
        while self.pos < len(self.src):
            ch = self._cur()
            if ch in ' \t\r\n':
                self._advance()
            elif ch == '#' and self.col == 1:
                # consume the full line
                start = self.pos
                while self.pos < len(self.src) and self._cur() != '\n':
                    self.pos += 1
                directive = self.src[start:self.pos]
                import re as _re
                m = _re.match(r'#line\s+(\d+)\s+"([^"]*)"', directive)
                if m:
                    # set to N-1: the \n we're about to consume will increment to N
                    self.line     = int(m.group(1)) - 1
                    self.filename = m.group(2)
                    self.col      = 1
            elif ch == '/' and self._peek() == '/':
                # single-line comment
                while self.pos < len(self.src) and self._cur() != '\n':
                    self._advance()
            elif ch == '/' and self._peek() == '*':
                # block comment
                self._advance(); self._advance()
                while self.pos < len(self.src):
                    if self._cur() == '*' and self._peek() == '/':
                        self._advance(); self._advance()
                        break
                    self._advance()
            else:
                break

    def _read_int(self):
        start = self.pos
        base = 10
        if self._cur() == '0' and self._peek() in 'xX':
            self._advance(); self._advance()
            base = 16
            while self.pos < len(self.src) and self._cur() in '0123456789abcdefABCDEF':
                self._advance()
        elif self._cur() == '0' and self._peek().isdigit():
            base = 8
            while self.pos < len(self.src) and self._cur() in '01234567':
                self._advance()
        else:
            while self.pos < len(self.src) and self._cur().isdigit():
                self._advance()
        # ignore suffix (u, l, ul, etc.)
        while self.pos < len(self.src) and self._cur() in 'uUlL':
            self._advance()
        return int(self.src[start:self.pos].rstrip('uUlL') or '0', base)

    _SIMPLE_ESC = {
        'n': 10, 't': 9, 'r': 13, '0': 0,
        'a': 7, 'b': 8, 'f': 12, 'v': 11,
        '\\': ord('\\'), "'": ord("'"), '"': ord('"'), '?': ord('?'),
    }

    def _read_escape(self):
        # Called with self.pos pointing at the '\\'.
        self._advance()  # consume backslash
        ch = self._cur()
        if ch == 'x':
            self._advance()
            start = self.pos
            while self.pos < len(self.src) and self._cur() in '0123456789abcdefABCDEF':
                self._advance()
            if self.pos == start:
                raise LexError(f"Line {self.line}: empty hex escape")
            return int(self.src[start:self.pos], 16) & 0xFF
        if ch in '01234567':
            # octal escape, up to 3 digits
            start = self.pos
            while self.pos < len(self.src) and (self.pos - start) < 3 and self._cur() in '01234567':
                self._advance()
            return int(self.src[start:self.pos], 8) & 0xFF
        esc = self._advance()
        return self._SIMPLE_ESC.get(esc, ord(esc))

    def _read_char(self):
        # after '
        self._advance()  # '
        if self._cur() == '\\':
            val = self._read_escape()
        else:
            val = ord(self._advance())
        if self._cur() != "'":
            raise LexError(f"Line {self.line}: Unclosed char literal")
        self._advance()  # '
        return val

    def _read_string(self):
        self._advance()  # "
        chars = []
        while self.pos < len(self.src) and self._cur() != '"':
            if self._cur() == '\\':
                chars.append(self._read_escape())
            else:
                chars.append(ord(self._advance()))
        if self._cur() != '"':
            raise LexError(f"Line {self.line}: Unclosed string literal")
        self._advance()  # "
        return chars

    def _tokenize(self):
        while True:
            self._skip_whitespace_and_comments()
            if self.pos >= len(self.src):
                self.tokens.append(Token(TK.EOF, None, self.line, self.col, self.filename))
                break

            line, col, fname = self.line, self.col, self.filename
            ch = self._cur()

            def _tok(kind, value):
                return Token(kind, value, line, col, fname)

            # number
            if ch.isdigit():
                val = self._read_int()
                self.tokens.append(_tok(TK.INT_LIT, val))
                continue

            # identifier / keyword
            if ch.isalpha() or ch == '_':
                start = self.pos
                while self.pos < len(self.src) and (self._cur().isalnum() or self._cur() == '_'):
                    self._advance()
                word = self.src[start:self.pos]
                kind = KEYWORDS.get(word, TK.IDENT)
                self.tokens.append(_tok(kind, word))
                continue

            # char literal
            if ch == "'":
                val = self._read_char()
                self.tokens.append(_tok(TK.CHAR_LIT, val))
                continue

            # string literal (adjacent strings are concatenated, C standard)
            if ch == '"':
                val = self._read_string()
                self._skip_whitespace_and_comments()
                while self.pos < len(self.src) and self._cur() == '"':
                    val = val + self._read_string()
                    self._skip_whitespace_and_comments()
                self.tokens.append(_tok(TK.STRING_LIT, val))
                continue

            # three-character: ellipsis, shift-assigns
            three = ch + self._peek() + self._peek(2)
            three_map = {
                '...': (TK.ELLIPSIS, '...'),
                '<<=': (TK.LSHIFT_ASSIGN, '<<='),
                '>>=': (TK.RSHIFT_ASSIGN, '>>='),
            }
            if three in three_map:
                kind, value = three_map[three]
                self._advance(); self._advance(); self._advance()
                self.tokens.append(_tok(kind, value))
                continue

            # two-character operators first
            two = ch + self._peek()
            two_map = {
                '<<': TK.LSHIFT, '>>': TK.RSHIFT,
                '&&': TK.AND,    '||': TK.OR,
                '==': TK.EQ,     '!=': TK.NEQ,
                '<=': TK.LTE,    '>=': TK.GTE,
                '+=': TK.PLUS_ASSIGN,  '-=': TK.MINUS_ASSIGN,
                '*=': TK.STAR_ASSIGN,  '/=': TK.SLASH_ASSIGN,
                '%=': TK.PERCENT_ASSIGN,
                '&=': TK.AMP_ASSIGN,   '|=': TK.PIPE_ASSIGN,
                '^=': TK.CARET_ASSIGN, '++': TK.INC,
                '--': TK.DEC,          '->': TK.ARROW,
            }
            if two in two_map:
                self._advance(); self._advance()
                self.tokens.append(_tok(two_map[two], two))
                continue

            # single-character operators
            one_map = {
                '+': TK.PLUS,    '-': TK.MINUS,   '*': TK.STAR,
                '/': TK.SLASH,   '%': TK.PERCENT,  '&': TK.AMP,
                '|': TK.PIPE,    '^': TK.CARET,    '~': TK.TILDE,
                '!': TK.BANG,    '<': TK.LT,       '>': TK.GT,
                '=': TK.ASSIGN,  '(': TK.LPAREN,   ')': TK.RPAREN,
                '{': TK.LBRACE,  '}': TK.RBRACE,   '[': TK.LBRACKET,
                ']': TK.RBRACKET, ';': TK.SEMICOLON, ':': TK.COLON, '?': TK.QUESTION,
                ',': TK.COMMA,   '.': TK.DOT,
            }
            if ch in one_map:
                self._advance()
                self.tokens.append(_tok(one_map[ch], ch))
                continue

            raise LexError(f"Line {line}:{col}: Unexpected character {ch!r}")

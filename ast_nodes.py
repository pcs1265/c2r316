"""
C to R316 Compiler - AST 노드 정의
"""

from dataclasses import dataclass, field
from typing import List, Optional, Any


# ── 타입 시스템 ────────────────────────────────────────────────────────────────

class CType:
    pass

@dataclass
class CInt(CType):
    """16비트 정수 (signed/unsigned)"""
    unsigned: bool = False
    def __repr__(self): return f"{'unsigned ' if self.unsigned else ''}int"
    def size(self): return 1   # 1 word

@dataclass
class CLong(CType):
    """32비트 정수 (two words)"""
    unsigned: bool = False
    def __repr__(self): return f"{'unsigned ' if self.unsigned else ''}long"
    def size(self): return 2   # 2 words

@dataclass
class CChar(CType):
    """8비트 문자 (1 word로 저장)"""
    unsigned: bool = False
    def __repr__(self): return f"{'unsigned ' if self.unsigned else ''}char"
    def size(self): return 1

@dataclass
class CVoid(CType):
    def __repr__(self): return "void"
    def size(self): return 0

@dataclass
class CPointer(CType):
    base: CType
    def __repr__(self): return f"{self.base}*"
    def size(self): return 1   # 16비트 포인터

@dataclass
class CArray(CType):
    base: CType
    length: Optional[int]
    def __repr__(self): return f"{self.base}[{self.length or ''}]"
    def size(self): return (self.length or 0) * self.base.size()

@dataclass
class CFunction(CType):
    ret: CType
    params: List[CType]
    variadic: bool = False
    def __repr__(self): return f"{self.ret}({', '.join(map(str, self.params))}{',...' if self.variadic else ''})"
    def size(self): return 0


def is_integer(t: CType) -> bool:
    return isinstance(t, (CInt, CLong, CChar))

def is_pointer(t: CType) -> bool:
    return isinstance(t, (CPointer, CArray))

def is_scalar(t: CType) -> bool:
    return is_integer(t) or is_pointer(t)

def is_32bit(t: CType) -> bool:
    return isinstance(t, CLong)


# ── AST 노드 기반 클래스 ───────────────────────────────────────────────────────

class Node:
    """모든 AST 노드의 기반"""
    pass


# ── 최상위 선언 ──────────────────────────────────────────────────────────────

@dataclass
class Program(Node):
    decls: List['Decl']

@dataclass
class FuncDecl(Node):
    name: str
    ret_type: CType
    params: List['ParamDecl']
    body: Optional['Block']    # None이면 선언만 (extern)
    is_static: bool = False
    variadic: bool = False

@dataclass
class ParamDecl(Node):
    name: str
    ctype: CType

@dataclass
class VarDecl(Node):
    name: str
    ctype: CType
    init: Optional['Expr']
    is_global: bool = False
    is_static: bool = False


# ── 문장 ─────────────────────────────────────────────────────────────────────

class Stmt(Node):
    pass

@dataclass
class Block(Stmt):
    stmts: List[Stmt]

@dataclass
class ExprStmt(Stmt):
    expr: 'Expr'

@dataclass
class IfStmt(Stmt):
    cond: 'Expr'
    then: Stmt
    else_: Optional[Stmt]

@dataclass
class WhileStmt(Stmt):
    cond: 'Expr'
    body: Stmt

@dataclass
class ForStmt(Stmt):
    init: Optional[Stmt]     # VarDecl 또는 ExprStmt 또는 None
    cond: Optional['Expr']
    step: Optional['Expr']
    body: Stmt

@dataclass
class ReturnStmt(Stmt):
    expr: Optional['Expr']

@dataclass
class BreakStmt(Stmt):
    pass

@dataclass
class ContinueStmt(Stmt):
    pass

@dataclass
class DeclStmt(Stmt):
    decl: VarDecl


# ── 표현식 ───────────────────────────────────────────────────────────────────

class Expr(Node):
    pass

@dataclass
class IntLit(Expr):
    value: int
    ctype: CType = field(default_factory=CInt)

@dataclass
class CharLit(Expr):
    value: int
    ctype: CType = field(default_factory=CChar)

@dataclass
class StringLit(Expr):
    chars: List[int]          # null 포함 아직 아님; codegen이 추가
    label: str = ''           # codegen이 할당
    ctype: CType = field(default_factory=lambda: CPointer(CChar()))

@dataclass
class Ident(Expr):
    name: str
    ctype: CType = None

@dataclass
class BinOp(Expr):
    op: str                   # '+', '-', '*', '/', '%', '&', '|', '^',
                              # '<<', '>>', '&&', '||',
                              # '==', '!=', '<', '>', '<=', '>='
    left: Expr
    right: Expr
    ctype: CType = None

@dataclass
class UnaryOp(Expr):
    op: str                   # '-', '~', '!', '&', '*', '++pre', '--pre',
                              # '++post', '--post'
    operand: Expr
    ctype: CType = None

@dataclass
class Assign(Expr):
    op: str                   # '=', '+=', '-=', '*=', '/=', '&=', '|=', '^='
    target: Expr
    value: Expr
    ctype: CType = None

@dataclass
class Call(Expr):
    func: Expr
    args: List[Expr]
    ctype: CType = None

@dataclass
class Index(Expr):
    array: Expr
    index: Expr
    ctype: CType = None

@dataclass
class Member(Expr):
    obj: Expr
    field: str
    arrow: bool               # True면 ->, False면 .
    ctype: CType = None

@dataclass
class Cast(Expr):
    to_type: CType
    expr: Expr
    ctype: CType = None

@dataclass
class Ternary(Expr):
    cond: Expr
    then: Expr
    else_: Expr
    ctype: CType = None

@dataclass
class SizeOf(Expr):
    target: Any               # CType 또는 Expr
    ctype: CType = field(default_factory=CInt)

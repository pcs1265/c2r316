"""
C to R316 Compiler - AST Node Definitions
"""

from dataclasses import dataclass, field
from typing import List, Optional, Any


# ── Type System ────────────────────────────────────────────────────────────────

class CType:
    pass

@dataclass
class CInt(CType):
    """16-bit integer (signed/unsigned)"""
    unsigned: bool = False
    def __repr__(self): return f"{'unsigned ' if self.unsigned else ''}int"
    def size(self): return 1   # 1 word

@dataclass
class CLong(CType):
    """32-bit integer (two words)"""
    unsigned: bool = False
    def __repr__(self): return f"{'unsigned ' if self.unsigned else ''}long"
    def size(self): return 2   # 2 words

@dataclass
class CChar(CType):
    """8-bit character (stored as 1 word)"""
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
    def size(self): return 1   # 16-bit pointer

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
    def __repr__(self): return f"{self.ret}({', '.join(map(str, self.params))})"
    def size(self): return 0


def is_integer(t: CType) -> bool:
    return isinstance(t, (CInt, CLong, CChar))

def is_pointer(t: CType) -> bool:
    return isinstance(t, (CPointer, CArray))

def is_scalar(t: CType) -> bool:
    return is_integer(t) or is_pointer(t)

def is_32bit(t: CType) -> bool:
    return isinstance(t, CLong)


# ── AST Node Base Class ───────────────────────────────────────────────────────

class Node:
    """Base class for all AST nodes"""
    pass


# ── Top-Level Declarations ──────────────────────────────────────────────────────────────

@dataclass
class Program(Node):
    decls: List['Decl']

@dataclass
class FuncDecl(Node):
    name: str
    ret_type: CType
    params: List['ParamDecl']
    body: Optional['Block']    # None means declaration only (extern)
    is_static: bool = False

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


# ── Statements ─────────────────────────────────────────────────────────────────────

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
    init: Optional[Stmt]     # VarDecl, ExprStmt, or None
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


# ── Expressions ───────────────────────────────────────────────────────────────────

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
    chars: List[int]          # null not yet included; codegen adds it
    label: str = ''           # assigned by codegen
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
    arrow: bool               # True for ->, False for .
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
    target: Any               # CType or Expr
    ctype: CType = field(default_factory=CInt)

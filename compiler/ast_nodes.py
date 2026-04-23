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
class DoWhileStmt(Stmt):
    body: Stmt
    cond: 'Expr'

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

@dataclass
class AsmStmt(Stmt):
    """asm("template" : "r"(e0), "r"(e1), ...)  — inputs only"""
    text:   str        # template string, %0..%N are substituted
    inputs: list       # list[Expr]


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


# ── AST Pretty-Printer ──────────────────────────────────────────────────────────

def dump_ast(node, indent: int = 0) -> str:
    """Return a human-readable dump of the AST."""
    prefix = '  ' * indent
    child_prefix = '  ' * (indent + 1)

    if isinstance(node, Program):
        inner = '\n'.join(dump_ast(d, indent + 1) for d in node.decls)
        return f'{prefix}Program(\n{inner}\n{prefix})'

    if isinstance(node, FuncDecl):
        params = ', '.join(f'{p.ctype} {p.name}' for p in node.params)
        body = dump_ast(node.body, indent + 1) if node.body else f'{child_prefix}<no body>'
        return f'{prefix}FuncDecl({node.ret_type} {node.name}({params})\n{body}\n{prefix})'

    if isinstance(node, ParamDecl):
        return f'{prefix}ParamDecl({node.ctype} {node.name})'

    if isinstance(node, VarDecl):
        init = f' = {dump_ast(node.init, 0)}' if node.init else ''
        return f'{prefix}VarDecl({node.ctype} {node.name}{init})'

    if isinstance(node, Block):
        inner = '\n'.join(dump_ast(s, indent + 1) for s in node.stmts)
        return f'{prefix}Block(\n{inner}\n{prefix})'

    if isinstance(node, ExprStmt):
        return f'{prefix}ExprStmt({dump_ast(node.expr, 0)})'

    if isinstance(node, IfStmt):
        else_part = f'\n{dump_ast(node.else_, indent + 1)}' if node.else_ else ''
        return (f'{prefix}IfStmt(\n'
                f'{child_prefix}cond: {dump_ast(node.cond, 0)}\n'
                f'{child_prefix}then: {dump_ast(node.then, indent + 1)}{else_part}\n'
                f'{prefix})')

    if isinstance(node, WhileStmt):
        return (f'{prefix}WhileStmt(\n'
                f'{child_prefix}cond: {dump_ast(node.cond, 0)}\n'
                f'{child_prefix}body: {dump_ast(node.body, indent + 1)}\n'
                f'{prefix})')

    if isinstance(node, DoWhileStmt):
        return (f'{prefix}DoWhileStmt(\n'
                f'{child_prefix}body: {dump_ast(node.body, indent + 1)}\n'
                f'{child_prefix}cond: {dump_ast(node.cond, 0)}\n'
                f'{prefix})')

    if isinstance(node, ForStmt):
        init = dump_ast(node.init, indent + 1) if node.init else f'{child_prefix}<none>'
        cond = dump_ast(node.cond, 0) if node.cond else '<none>'
        step = dump_ast(node.step, 0) if node.step else '<none>'
        return (f'{prefix}ForStmt(\n'
                f'{child_prefix}init: {init}\n'
                f'{child_prefix}cond: {cond}\n'
                f'{child_prefix}step: {step}\n'
                f'{child_prefix}body: {dump_ast(node.body, indent + 1)}\n'
                f'{prefix})')

    if isinstance(node, ReturnStmt):
        expr = f' {dump_ast(node.expr, 0)}' if node.expr else ''
        return f'{prefix}ReturnStmt({expr})'

    if isinstance(node, BreakStmt):
        return f'{prefix}BreakStmt'

    if isinstance(node, ContinueStmt):
        return f'{prefix}ContinueStmt'

    if isinstance(node, DeclStmt):
        return f'{prefix}DeclStmt({dump_ast(node.decl, 0)})'

    if isinstance(node, AsmStmt):
        inputs = ', '.join(dump_ast(i, 0) for i in node.inputs)
        return f'{prefix}AsmStmt("{node.text}"{", " + inputs if inputs else ""})'

    # ── Expressions ──

    if isinstance(node, IntLit):
        return f'IntLit({node.value})'

    if isinstance(node, CharLit):
        return f'CharLit({chr(node.value)!r})'

    if isinstance(node, StringLit):
        s = ''.join(chr(c) if 32 <= c < 127 else f'\\x{c:02x}' for c in node.chars)
        return f'StringLit("{s}")'

    if isinstance(node, Ident):
        return f'Ident({node.name})'

    if isinstance(node, BinOp):
        return f'({dump_ast(node.left)} {node.op} {dump_ast(node.right)})'

    if isinstance(node, UnaryOp):
        if node.op.endswith('post'):
            return f'({dump_ast(node.operand)}{node.op[0]})'
        return f'({node.op}{dump_ast(node.operand)})'

    if isinstance(node, Assign):
        return f'({dump_ast(node.target)} {node.op} {dump_ast(node.value)})'

    if isinstance(node, Call):
        args = ', '.join(dump_ast(a) for a in node.args)
        return f'{dump_ast(node.func)}({args})'

    if isinstance(node, Index):
        return f'{dump_ast(node.array)}[{dump_ast(node.index)}]'

    if isinstance(node, Member):
        op = '->' if node.arrow else '.'
        return f'{dump_ast(node.obj)}{op}{node.field}'

    if isinstance(node, Cast):
        return f'(({node.to_type}){dump_ast(node.expr)})'

    if isinstance(node, Ternary):
        return f'({dump_ast(node.cond)} ? {dump_ast(node.then)} : {dump_ast(node.else_)})'

    if isinstance(node, SizeOf):
        t = node.target if isinstance(node.target, CType) else dump_ast(node.target)
        return f'sizeof({t})'

    return f'{prefix}Unknown({type(node).__name__})'

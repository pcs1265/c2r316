"""
C to R316 Compiler - IR (Three-Address Code)

Instruction set:
  Const(dst, value)               dst = <int>
  Copy(dst, src)                  dst = src
  AddrOf(dst, var)                dst = &var   (local/global name)
  BinOp(dst, op, left, right)     dst = left op right
  UnaryOp(dst, op, src)           dst = op src
  Load(dst, addr)                 dst = *addr
  Store(addr, src)                *addr = src
  Call(dst, func, args)           dst = func(args...)   dst=None for void
  Ret(src)                        return src            src=None for void
  Label(name)                     name:
  Jump(target)                    goto target
  JumpIf(cond, target)            if cond goto target
  JumpIfNot(cond, target)         if !cond goto target

Operands:
  Temp(id)          anonymous temporary  t0, t1, ...
  Var(name)         named C variable (local or param)
  Global(name)      global variable or function label
  Const(value)      integer constant (as operand, not instruction)
  StrLabel(name)    string literal label

Every instruction records loc=(file, line) for diagnostics.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Union, Tuple


# ── Operands ──────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Temp:
    id: int
    def __str__(self): return f't{self.id}'

@dataclass(frozen=True)
class Var:
    name: str
    def __str__(self): return self.name

@dataclass(frozen=True)
class Global:
    name: str
    def __str__(self): return f'@{self.name}'

@dataclass(frozen=True)
class ImmInt:
    value: int
    def __str__(self): return str(self.value)

@dataclass(frozen=True)
class StrLabel:
    name: str
    def __str__(self): return f'str:{self.name}'


Operand = Union[Temp, Var, Global, ImmInt, StrLabel]
Loc = Optional[Tuple[str, int]]   # (filename, line)  or None


# ── Instructions ──────────────────────────────────────────────────────────────

class Instr:
    loc: Loc = None

    def defs(self) -> Optional[Temp]:
        """Return the Temp this instruction defines, or None."""
        return None

    def uses(self) -> List[Operand]:
        """Return all operands this instruction reads."""
        return []

    def _loc_str(self) -> str:
        if self.loc:
            return f'  ; {self.loc[0]}:{self.loc[1]}'
        return ''


@dataclass
class IConst(Instr):
    """dst = <integer constant>"""
    dst: Temp
    value: int
    loc: Loc = field(default=None, repr=False)

    def defs(self): return self.dst
    def uses(self): return []
    def __str__(self): return f'  {self.dst} = {self.value}{self._loc_str()}'


@dataclass
class ICopy(Instr):
    """dst = src"""
    dst: Temp
    src: Operand
    loc: Loc = field(default=None, repr=False)

    def defs(self): return self.dst
    def uses(self): return [self.src]
    def __str__(self): return f'  {self.dst} = {self.src}{self._loc_str()}'


@dataclass
class IAddrOf(Instr):
    """dst = &var  (address of a local/global)"""
    dst: Temp
    var: Union[Var, Global]
    loc: Loc = field(default=None, repr=False)

    def defs(self): return self.dst
    def uses(self): return [self.var] if isinstance(self.var, Var) else []
    def __str__(self): return f'  {self.dst} = &{self.var}{self._loc_str()}'


@dataclass
class IBinOp(Instr):
    """dst = left op right"""
    dst: Temp
    op: str
    left: Operand
    right: Operand
    loc: Loc = field(default=None, repr=False)

    def defs(self): return self.dst
    def uses(self): return [self.left, self.right]
    def __str__(self): return f'  {self.dst} = {self.left} {self.op} {self.right}{self._loc_str()}'


@dataclass
class IUnaryOp(Instr):
    """dst = op src"""
    dst: Temp
    op: str
    src: Operand
    loc: Loc = field(default=None, repr=False)

    def defs(self): return self.dst
    def uses(self): return [self.src]
    def __str__(self): return f'  {self.dst} = {self.op}{self.src}{self._loc_str()}'


@dataclass
class ILoad(Instr):
    """dst = *addr"""
    dst: Temp
    addr: Operand
    loc: Loc = field(default=None, repr=False)

    def defs(self): return self.dst
    def uses(self): return [self.addr]
    def __str__(self): return f'  {self.dst} = *{self.addr}{self._loc_str()}'


@dataclass
class IStore(Instr):
    """*addr = src"""
    addr: Operand
    src: Operand
    loc: Loc = field(default=None, repr=False)

    def defs(self): return None
    def uses(self): return [self.addr, self.src]
    def __str__(self): return f'  *{self.addr} = {self.src}{self._loc_str()}'


@dataclass
class ICall(Instr):
    """dst = func(args)   dst=None for void calls"""
    dst: Optional[Temp]
    func: Union[Global, Temp]
    args: List[Operand]
    loc: Loc = field(default=None, repr=False)

    def defs(self): return self.dst
    def uses(self): return ([self.func] if isinstance(self.func, Temp) else []) + list(self.args)
    def __str__(self):
        args_str = ', '.join(str(a) for a in self.args)
        lhs = f'{self.dst} = ' if self.dst else ''
        return f'  {lhs}call {self.func}({args_str}){self._loc_str()}'


@dataclass
class IRet(Instr):
    """return src   src=None for void"""
    src: Optional[Operand]
    loc: Loc = field(default=None, repr=False)

    def defs(self): return None
    def uses(self): return [self.src] if self.src else []
    def __str__(self):
        val = f' {self.src}' if self.src else ''
        return f'  ret{val}{self._loc_str()}'


@dataclass
class ILabel(Instr):
    """label definition"""
    name: str
    loc: Loc = field(default=None, repr=False)

    def defs(self): return None
    def uses(self): return []
    def __str__(self): return f'{self.name}:'


@dataclass
class IJump(Instr):
    """unconditional jump"""
    target: str
    loc: Loc = field(default=None, repr=False)

    def defs(self): return None
    def uses(self): return []
    def __str__(self): return f'  jmp {self.target}{self._loc_str()}'


@dataclass
class IJumpIf(Instr):
    """if cond goto target"""
    cond: Operand
    target: str
    loc: Loc = field(default=None, repr=False)

    def defs(self): return None
    def uses(self): return [self.cond]
    def __str__(self): return f'  if {self.cond} goto {self.target}{self._loc_str()}'


@dataclass
class IJumpIfNot(Instr):
    """if !cond goto target"""
    cond: Operand
    target: str
    loc: Loc = field(default=None, repr=False)

    def defs(self): return None
    def uses(self): return [self.cond]
    def __str__(self): return f'  ifnot {self.cond} goto {self.target}{self._loc_str()}'


@dataclass
class IInlineAsm(Instr):
    """asm("template" : srcs...)  — %0..%N substituted at codegen time"""
    text: str
    srcs: List[Operand]
    loc: Loc = field(default=None, repr=False)

    def defs(self): return None
    def uses(self): return list(self.srcs)
    def __str__(self):
        return f'  asm({self.text!r}, {", ".join(str(s) for s in self.srcs)}){self._loc_str()}'


# ── Function IR container ──────────────────────────────────────────────────────

@dataclass
class IRFunction:
    name: str
    params: List[str]           # parameter names in order
    instrs: List[Instr] = field(default_factory=list)
    local_sizes: Dict[str, int] = field(default_factory=dict)  # name → slot count

    def dump(self) -> str:
        lines = [f'function {self.name}({", ".join(self.params)}):']
        for instr in self.instrs:
            lines.append(str(instr))
        return '\n'.join(lines)


@dataclass
class IRProgram:
    functions: List[IRFunction] = field(default_factory=list)
    globals: List[Tuple[str, int]] = field(default_factory=list)  # (name, word_count)
    strings: List[Tuple[str, List[int]]] = field(default_factory=list)  # (label, chars)

    def dump(self) -> str:
        parts = []
        if self.globals:
            parts.append('globals: ' + ', '.join(f'{n}[{w}]' for n, w in self.globals))
        for fn in self.functions:
            parts.append(fn.dump())
        return '\n\n'.join(parts)

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

    def defs(self) -> Optional[Union[Temp, List[Temp]]]:
        """Return Temp(s) this instruction defines, or None."""
        return None

    def uses(self) -> List[Operand]:
        """Return all operands this instruction reads."""
        return []

    def _loc_str(self) -> str:
        if self.loc:
            return f'  ; {self.loc[0]}:{self.loc[1]}'
        return ''


def iter_defs(instr: Instr) -> List[Temp]:
    """Return instruction definitions as a list for scalar and multiword IR."""
    d = instr.defs()
    if d is None:
        return []
    if isinstance(d, list):
        return d
    return [d]


@dataclass(frozen=True)
class LongValue:
    """A 32-bit C long represented as low/high 16-bit operands."""
    lo: Operand
    hi: Operand

    def __str__(self):
        return f'long({self.lo}, {self.hi})'


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
class ILongLoad(Instr):
    """dst_lo,dst_hi = *(long*)addr"""
    dst_lo: Temp
    dst_hi: Temp
    addr: Operand
    loc: Loc = field(default=None, repr=False)

    def defs(self): return [self.dst_lo, self.dst_hi]
    def uses(self): return [self.addr]
    def __str__(self):
        return f'  {self.dst_lo}:{self.dst_hi} = long *{self.addr}{self._loc_str()}'


@dataclass
class ILongStore(Instr):
    """*(long*)addr = src_lo,src_hi"""
    addr: Operand
    src_lo: Operand
    src_hi: Operand
    loc: Loc = field(default=None, repr=False)

    def defs(self): return None
    def uses(self): return [self.addr, self.src_lo, self.src_hi]
    def __str__(self):
        return f'  long *{self.addr} = {self.src_lo}:{self.src_hi}{self._loc_str()}'


@dataclass
class ILongBinOp(Instr):
    """dst_lo,dst_hi = left op right"""
    dst_lo: Temp
    dst_hi: Temp
    op: str
    left_lo: Operand
    left_hi: Operand
    right_lo: Operand
    right_hi: Operand
    loc: Loc = field(default=None, repr=False)

    def defs(self): return [self.dst_lo, self.dst_hi]
    def uses(self): return [self.left_lo, self.left_hi, self.right_lo, self.right_hi]
    def __str__(self):
        return (f'  {self.dst_lo}:{self.dst_hi} = '
                f'{self.left_lo}:{self.left_hi} {self.op} '
                f'{self.right_lo}:{self.right_hi}{self._loc_str()}')


@dataclass
class ILongUnaryOp(Instr):
    """dst_lo,dst_hi = op src_lo,src_hi"""
    dst_lo: Temp
    dst_hi: Temp
    op: str
    src_lo: Operand
    src_hi: Operand
    loc: Loc = field(default=None, repr=False)

    def defs(self): return [self.dst_lo, self.dst_hi]
    def uses(self): return [self.src_lo, self.src_hi]
    def __str__(self):
        return f'  {self.dst_lo}:{self.dst_hi} = {self.op}{self.src_lo}:{self.src_hi}{self._loc_str()}'


@dataclass
class ILongCompare(Instr):
    """dst = left op right, comparing 32-bit low/high pairs."""
    dst: Temp
    op: str
    left_lo: Operand
    left_hi: Operand
    right_lo: Operand
    right_hi: Operand
    unsigned: bool = False
    loc: Loc = field(default=None, repr=False)

    def defs(self): return self.dst
    def uses(self): return [self.left_lo, self.left_hi, self.right_lo, self.right_hi]
    def __str__(self):
        u = 'u' if self.unsigned else ''
        return (f'  {self.dst} = {self.left_lo}:{self.left_hi} '
                f'{self.op}{u} {self.right_lo}:{self.right_hi}{self._loc_str()}')


@dataclass
class ILongRet(Instr):
    """return long lo,hi"""
    lo: Operand
    hi: Operand
    loc: Loc = field(default=None, repr=False)

    def defs(self): return None
    def uses(self): return [self.lo, self.hi]
    def __str__(self):
        return f'  ret long {self.lo}:{self.hi}{self._loc_str()}'


@dataclass
class ILongCall(Instr):
    """dst_lo,dst_hi = func(args...) for long-returning calls.

    args is already ABI-flattened: each long argument contributes lo,hi.
    """
    dst_lo: Optional[Temp]
    dst_hi: Optional[Temp]
    func: Union[Global, Temp]
    args: List[Operand]
    loc: Loc = field(default=None, repr=False)

    def defs(self):
        return [d for d in (self.dst_lo, self.dst_hi) if d is not None]
    def uses(self): return ([self.func] if isinstance(self.func, Temp) else []) + list(self.args)
    def __str__(self):
        args_str = ', '.join(str(a) for a in self.args)
        lhs = f'{self.dst_lo}:{self.dst_hi} = ' if self.dst_lo else ''
        return f'  {lhs}call_long {self.func}({args_str}){self._loc_str()}'


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


# Physical registers used as inline-asm operand slots (%0..%9 → r7..r16).
# Inline asm may clobber exactly the registers corresponding to its operands.
ASM_REGS: List[str] = ['r7', 'r8', 'r9', 'r10', 'r11', 'r12',
                        'r13', 'r14', 'r15', 'r16']


@dataclass
class IInlineAsm(Instr):
    """asm("template" : srcs...)  — %0..%N substituted at codegen time.

    clobbers: frozenset of physical register names that this instruction may
    overwrite.  Set by irgen to ASM_REGS[:len(srcs)]; the register allocator
    uses this to exclude those registers from Temps whose live range crosses
    this instruction.
    """
    text: str
    srcs: List[Operand]
    loc: Loc = field(default=None, repr=False)
    clobbers: frozenset = field(default_factory=frozenset)

    def defs(self): return None
    def uses(self): return list(self.srcs)
    def __str__(self):
        return f'  asm({self.text!r}, {", ".join(str(s) for s in self.srcs)}){self._loc_str()}'


@dataclass
class IVaStart(Instr):
    """dst = va_start address: pointer into variadic spill area past fixed params"""
    dst: Temp
    num_fixed: int   # number of fixed (non-variadic) parameters
    loc: Loc = field(default=None, repr=False)

    def defs(self): return self.dst
    def uses(self): return []
    def __str__(self): return f'  {self.dst} = va_start({self.num_fixed}){self._loc_str()}'


@dataclass
class IVaArg(Instr):
    """dst = *ap; ap += step  — fetch and advance a va_list pointer"""
    dst: Temp
    ap: Operand      # the va_list (pointer) operand
    step: int        # word size of the fetched type (1 or 2)
    loc: Loc = field(default=None, repr=False)

    def defs(self): return self.dst
    def uses(self): return [self.ap]
    def __str__(self): return f'  {self.dst} = va_arg({self.ap}, step={self.step}){self._loc_str()}'


# ── Function IR container ──────────────────────────────────────────────────────

@dataclass
class IRFunction:
    name: str
    params: List[str]           # parameter names in order
    instrs: List[Instr] = field(default_factory=list)
    local_sizes: Dict[str, int] = field(default_factory=dict)  # name → slot count
    param_sizes: Dict[str, int] = field(default_factory=dict)  # name → slot count
    is_variadic: bool = False
    is_static: bool = False
    is_always_inline: bool = False
    # va_spill_base is set by codegen: frame offset where arg-reg spill area begins
    va_spill_base: int = 0

    def dump(self) -> str:
        lines = [f'function {self.name}({", ".join(self.params)}):']
        for instr in self.instrs:
            lines.append(str(instr))
        return '\n'.join(lines)


@dataclass
class IRProgram:
    functions: List[IRFunction] = field(default_factory=list)
    globals: List[Tuple[str, int, Optional[List[Union[int, str]]]]] = field(default_factory=list)  # (name, word_count, init_vals|None); str entries are label names
    strings: List[Tuple[str, List[int]]] = field(default_factory=list)  # (label, chars)

    def dump(self) -> str:
        parts = []
        if self.globals:
            parts.append('globals: ' + ', '.join(f'{n}[{w}]' for n, w, _ in self.globals))
        for fn in self.functions:
            parts.append(fn.dump())
        return '\n\n'.join(parts)

# TODO

## Implemented C Features

### Types
- `int`, `unsigned int`, `char`, `unsigned char`, `void`
- `short`, `unsigned short` — equivalent to `int` on this 16-bit platform
- `signed` — explicit signedness keyword (no-op, int/char are signed by default)
- `long`, `unsigned long` — parsed and type-checked; **no working codegen** (see Known Issues)
- Pointers (single and multi-level)
- 1D arrays (with initializers, inferred size from `{}` or string literal)
- Multi-dimensional arrays (`int a[3][4]`, with initializers and subscripting)
- `struct` and `union` (field access via `.` and `->`, nested, global, arrays of structs)
- `va_list` (as `int*` alias)
- `enum` (with optional tag, optional initializers — auto-incrementing int constants)
- `typedef` (simple aliases, function-pointer typedefs)

### Declarations
- Global and local variable declarations with optional initializers
- Multiple declarators in one statement: `int a, b = 2, c;`
- Function declarations (forward declarations) and definitions
- `static` and `extern` storage class modifiers (including static local persistence)
- `const` and `volatile` type qualifiers (parsed and accepted; semantically ignored)
- `register` storage class (parsed and accepted; semantically ignored)
- Global array `{...}` initializers (literal values only)
- Local array `{...}` initializers with zero-fill for partial init
- Inferred array size: `int arr[] = {1,2,3}` and `char s[] = "hello"`

### Statements
- `if` / `if-else`
- `while`, `do-while`, `for` (with optional init/cond/step; init may declare a variable)
- `return` (with or without expression)
- `break`, `continue`
- `switch` / `case` / `default` (with fallthrough support)
- `goto` and labels (label names are mangled to `._user_<name>` in the asm)
- Inline assembly: `asm("template" : "r"(expr), ...)` — input operands only

### Expressions
- Integer literals (decimal, hex `0x`, octal `0`-prefix; `u`/`l` suffixes accepted and ignored)
- Character literals with escape sequences: `\n \t \r \0 \a \b \f \v \\ \' \" \? \xHH \ooo` (octal up to 3 digits)
- String literals (adjacent concatenation, same escape sequences)
- All arithmetic: `+ - * / %` (div/mod dispatched to `__udiv`/`__umod` runtime helpers)
- All bitwise: `& | ^ ~ << >>`
- All comparison: `== != < > <= >=`
- Logical: `&& ||` (short-circuit evaluation)
- Compound assignments: `+= -= *= /= %= &= |= ^= <<= >>=`
- `sizeof(type)` and `sizeof expr`
- Pre/post `++` and `--`
- Ternary `? :`
- Cast `(type)expr`
- Address-of `&`, dereference `*`
- Array subscript `a[i]` (including multi-dimensional)
- Member access `.` and `->` (with field offset arithmetic)
- Function calls (≤6 args in registers, 7th+ via stack)
- Variadic calls via `va_start` / `va_arg` / `va_end`
- Function pointer calls (typedef, local declarator `int (*fp)(int)`, global, array of function pointers, passing as argument)

### Preprocessor
- `#include "file"` and `#include <file>`
- Object macros: `#define NAME` and `#define NAME value`
- Function-like macros: `#define F(a,b) ...` including variadic `...` / `__VA_ARGS__`
- Stringification (`#arg`) and token pasting (`a##b`)
- `#undef`
- `#ifdef` / `#ifndef` / `#if <expr>` / `#elif <expr>` / `#else` / `#endif`
- `defined(NAME)` and `defined NAME` in `#if`/`#elif`
- `#error`, `#warning`, `#pragma` (ignored)
- Predefined macros: `__FILE__`, `__LINE__`, `__DATE__`, `__TIME__`, `__STDC__`

### Optimizations
- Constant folding + copy propagation (`compiler/fold.py`)
- Strength reduction: `x * 2^n` → `x << n`; unsigned `x / 2^n` → `x >> n`; unsigned `x % 2^n` → `x & (2^n - 1)`
- Algebraic identities: `x & 0`, `x & 0xFFFF`, `x | 0`, `x | 0xFFFF`, `x ^ 0`; self-ops on identical Temps (`t - t`, `t ^ t`, `t == t`, etc.)
- Unary constant folding for `-` and `~`
- Dead code elimination + dead function elimination (`compiler/dce.py`)
- Linear-scan register allocator (`compiler/regalloc.py`): Temps → r10–r18 (caller-saved) and r19–r29 (call-crossing, callee-saved)
- Compare-branch fusion: `t = a < b; if t goto L` → `sub r0,a,b; jl L`
- Peephole: `st Rx,r30,N` + `ld Ry,r30,N` → `mov Ry,Rx`

---

## Code Generation Notes

- **Symbol naming**: all user-defined C symbols (functions and global variables) are emitted with a `_C_` prefix (e.g. `main` → `_C_main`) to avoid collisions with TPTASM reserved mnemonics (`add`, `sub`, `mul`, `or`, etc.). `runtime.asm` calls `_C_main` as the program entry point.

---

## Known Issues

- **`long` (32-bit) arithmetic** — type parses and type-checks, but all arithmetic is 16-bit; multi-word codegen (`add+adc`, `sub+sbb`, `mul+mulh`, even-register alignment per ABI §9) is not implemented
- **Integer literals > 16 bits** — truncated to 16 bits at IR generation; codegen does not emit multi-word constants
- **Struct/union pass-by-value** — hidden-pointer ABI (ABI §4) not generated; use explicit pointers

---

## Not Implemented (C Language Features)

| Feature | Notes |
|---|---|
| ~~`short`, `signed`, `const`, `volatile`, `register`~~ | **Implemented** — `short`/`signed`/`const`/`volatile`/`register` all parsed and accepted; `const`/`volatile`/`register` semantically ignored |
| `float`, `double` | No support at any level |
| Struct/union pass-by-value | Hidden pointer not generated |
| `__func__` / `__FUNCTION__` | C99 implicit per-function string variable; not yet implemented |
| Designated initializers (`{.field = val}`) | Not supported |
| Compound literals (`(Type){...}`) | Not supported |
| Inline asm output operands / clobbers | Input-only `asm()` |
| Bitfield struct members (`: N`) | Not supported |
| Variable-length arrays (VLAs) | Not supported |

---

## Potential Optimizations (Future)
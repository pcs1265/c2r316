# TODO

## Implemented C Features

### Types
- `int`, `unsigned int`, `char`, `unsigned char`, `void`
- `long`, `unsigned long` — parsed and type-checked; **no working codegen** (see Known Issues)
- Pointers (single and multi-level)
- 1D arrays (with initializers, inferred size from `{}` or string literal)
- `struct` and `union` (field access via `.` and `->`, nested, global, arrays of structs)
- `va_list` (as `int*` alias)
- `enum` (with optional tag, optional initializers — auto-incrementing int constants)
- `typedef` (simple aliases, function-pointer typedefs)

### Declarations
- Global and local variable declarations with optional initializers
- Multiple declarators in one statement: `int a, b = 2, c;`
- Function declarations (forward declarations) and definitions
- `static` and `extern` storage class modifiers (parsed; `static` local semantics — persistent across calls — **not implemented**)
- Global array `{...}` initializers (literal values only)
- Local array `{...}` initializers with zero-fill for partial init
- Inferred array size: `int arr[] = {1,2,3}` and `char s[] = "hello"`

### Statements
- `if` / `if-else`
- `while`, `do-while`, `for` (with optional init/cond/step; init may declare a variable)
- `return` (with or without expression)
- `break`, `continue`
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
- Array subscript `a[i]`
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
- **`static` local variables** — `is_static` flag stored on `VarDecl` but irgen treats static locals identically to ordinary locals (no persistent storage across calls)

---

## Not Implemented (C Language Features)

| Feature | Notes |
|---|---|
| `short`, `signed`, `const`, `volatile`, `register` | No lexer tokens |
| `float`, `double` | No support at any level |
| `switch` / `case` / `default` | No keyword tokens, no parse support |
| `goto` / labels | No support |
| Multi-dimensional arrays | `int a[3][4]` is not parsed |
| Struct/union pass-by-value | Hidden pointer not generated |
| Function pointer declarator syntax | Implemented — `int (*fp)(int)` parsed in params, locals, globals |
| `__func__` / `__FUNCTION__` | C99 implicit per-function string variable; not yet implemented |
| Designated initializers (`{.field = val}`) | Not supported |
| Compound literals (`(Type){...}`) | Not supported |
| Inline asm output operands / clobbers | Input-only `asm()` |
| Bitfield struct members (`: N`) | Not supported |
| Variable-length arrays (VLAs) | Not supported |

---

## Potential Optimizations (Future)

- **Copy prop: Var sources** — blocked because `Var` in IStore/ILoad address position means "direct slot access", not "load-and-dereference"; distinguishing address-position vs. value-position uses is required first
- **Common subexpression elimination (CSE)** — `&arr` is recomputed on every array access; CSE would deduplicate `IAddrOf` within a basic block
- **Dead store elimination** — stores to locals never loaded again (requires liveness analysis over Vars, not just Temps)
- **Inlining** — small leaf functions (e.g. `putchar`) called in hot loops; would require repeating the fold→DCE cycle until stable

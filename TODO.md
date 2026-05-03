# TODO

## Implemented C Features

### Types
- `int`, `unsigned int`, `char`, `unsigned char`, `void`
- `short`, `unsigned short` — equivalent to `int` on this 16-bit platform
- `signed` — explicit signedness keyword (no-op, int/char are signed by default)
- `long`, `unsigned long` — represented as two 16-bit halves; basic load/store, constants, `+`, `-`, `*`, comparisons, returns, and fixed-argument calls work
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
- Integer literals (decimal, hex `0x`, octal `0`-prefix; `u`/`l` suffixes accepted; 32-bit values preserved when used as `long`)
- Character literals with escape sequences: `\n \t \r \0 \a \b \f \v \\ \' \" \? \xHH \ooo` (octal up to 3 digits)
- String literals (adjacent concatenation, same escape sequences)
- Arithmetic: `+ - * / %` for 16-bit integers and `long`
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
- Function calls (≤6 scalar argument words in registers, overflow via stack; `long` fixed arguments consume two words)
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
- Dead store elimination (`compiler/fold.py`): removes stores to locals that are overwritten before being read
- Common subexpression elimination (CSE) (`compiler/fold.py`): deduplicates `IAddrOf` and `Var` loads within basic blocks
- Trivial jump removal: eliminates jumps to immediately-following labels
- Function inlining (`compiler/inline.py`): inlines `always_inline` functions
- Linear-scan register allocator (`compiler/regalloc.py`): Temps → r10–r18 (caller-saved) and r19–r29 (call-crossing, callee-saved); `FuncContext` skips spill-slot allocation for register-assigned temps so the frame is correct from the start
- Compare-branch fusion: `t = a < b; if t goto L` → `sub r0,a,b; jl L`
- Peephole: `st Rx,r30,N` + `ld Ry,r30,N` → `mov Ry,Rx`

---

## Code Generation Notes

- **Symbol naming**: all user-defined C symbols (functions and global variables) are emitted with a `_C_` prefix (e.g. `main` → `_C_main`) to avoid collisions with TPTASM reserved mnemonics (`add`, `sub`, `mul`, `or`, etc.). `runtime.asm` calls `_C_main` as the program entry point.

---

## Known Issues

- **`long` shifts** — `<<` and `>>` for `long` are not implemented yet. Add either inline lowering loops or runtime helpers (`__lshl`, `__lshr`, unsigned variants).
- **`long` bitwise operators** — `&`, `|`, and `^` for `long` are not implemented yet. These should lower independently on low/high halves.
- **`long` constant folding** — optimizer folds scalar constants only. Add fold support for `ILongBinOp`, `ILongUnaryOp`, and `ILongCompare`.
- **`long` inliner support** — scalar inliner currently skips functions containing long IR. Teach `compiler/inline.py` to clone/rename `ILong*` instructions before enabling long-function inlining.
- **`long` variadic edge cases** — `va_arg(ap, long)` and `%l` stdio formats work for supported fixed/variadic layouts; broaden tests for mixed long varargs beyond stdio.
- **`long` ABI alignment** — current implementation flattens long args as two consecutive argument words. Revisit even-register alignment/skipped argument registers if strict ABI §2.2.1 compatibility is required.
- **Long literal suffix typing** — `L`/`UL` suffixes are accepted, but semantic typing is still broad/simple. Audit parser/semantic behavior for C-compatible literal type selection.
- **Struct/union pass-by-value** — hidden-pointer ABI (ABI §4) not generated; use explicit pointers

---

## Long Support TODO

Current implemented slice:
- Two-slot storage: `addr+0 = low16`, `addr+1 = high16`.
- Shared long IR: `LongValue`, `ILongLoad`, `ILongStore`, `ILongBinOp`, `ILongUnaryOp`, `ILongCompare`, `ILongRet`, `ILongCall`.
- R316 lowering for constants, load/store, assignment, scalar casts/truncation, truthiness, `+`, `-`, `*`, `/`, `%`, comparisons, fixed-argument calls, and returns.
- Tests cover full-width constants, carry into high half, long return, long argument passing, unsigned/signed long division/modulo, compound long division/modulo assignment, and legacy `test_long_truncation.c`.

Next steps:
- Add `long` bitwise ops: `&`, `|`, `^`, `~` complete high/low behavior and tests.
- Add `long` shifts: constant small shifts first, then variable shifts.
- Extend stdio long formatting/parsing beyond `%ld`, `%lu`, and `%lx` if needed (`%lo`, `%lX`, width/precision edge cases).
- Teach inliner, fold, and DCE optimizations more long-specific simplifications.
- Add focused execution tests for arrays of long, struct fields of long, globals/statics, stack overflow args containing long, and function-pointer calls with long signatures.

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

## Refactoring

- **`compiler/utils/` package** — extract shared helpers into `compiler/utils/`:
  - `callgraph.py`: `_build_call_graph` + `_reachable_functions` + `_recursive_set` are duplicated between `dce.py` and `inline.py`
  - `errors.py`: `_err()` with source-location context is reimplemented in lexer, parser, semantic, and irgen
  - `types.py`: move `is_integer`, `is_pointer`, `is_scalar`, `is_32bit` out of `ast_nodes.py` into a dedicated module

---

## Potential Optimizations (Future)

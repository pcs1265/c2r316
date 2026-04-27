# c2r316: C to R316 Assembly Compiler

c2r316 is a C-to-R316 assembly cross-compiler written in Python. It compiles a subset of C into TPTASM assembly for the **R316 virtual machine** (16-bit ALU, 32-bit registers) used in *The Powder Toy*.

## Compilation Pipeline

```
C Source
  → Preprocessor
  → Lexer
  → Parser
  → Semantic Analyzer
  → IR Generator
  → Optimizer
  → Code Generator
  → R316 ASM
```

1. **Preprocessor**
   - `#include "file"` and `#include <file>`
   - Object macros: `#define NAME` / `#define NAME value`
   - Function-like macros: `#define F(a,b) ...` with variadic `...`/`__VA_ARGS__`
   - Stringification (`#arg`) and token pasting (`a##b`)
   - `#undef`
   - `#ifdef` / `#ifndef` / `#if <expr>` / `#elif <expr>` / `#else` / `#endif`
   - `defined(NAME)` / `defined NAME` in `#if`/`#elif`
   - `#error`, `#warning`, `#pragma` (ignored)
   - Predefined macros: `__FILE__`, `__LINE__`, `__DATE__`, `__TIME__`, `__STDC__`

2. **Lexer**
   - All C operators and punctuation
   - Integer, character, and string literals
   - Adjacent string literal concatenation

3. **Parser**
   - Recursive descent, full C operator precedence
   - All standard control flow and declarations
   - Struct/union, pointer/array declarators, typedef

4. **Semantic Analyzer**
   - Symbol tables and nested block scopes
   - Type annotation and integer promotion
   - Function call type checking (fixed-arity and variadic)

5. **IR Generator**
   - Lowers AST to Three-Address Code IR
   - Short-circuit `&&`/`||`, compound assignments, pre/post increment
   - Struct field offset arithmetic, array index scaling
   - `va_start` / `va_arg` / `va_end`

6. **Optimizer**
   - **Constant folding + copy propagation** — `x + 0 → x`, `t1 = 5; use(t1) → use(5)`
   - **Dead code elimination** — removes unused temporaries and functions unreachable from `main`

7. **Code Generator**
   - **Linear-scan register allocator** — r10–r18 (caller-saved), r19–r29 (callee-saved)
   - **Compare-branch fusion** — `t = a < b; if t goto L` → `sub r0, a, b; jl L`
   - **3-operand arithmetic** — `add dst, src1, src2` when dst ≠ src
   - **Assembly peephole** — `st Rx, r30, N; ld Ry, r30, N` → `mov Ry, Rx`

## R316 Architecture

- **Registers**: 32 general-purpose 32-bit registers (`r0`–`r31`).
  - `r0` — hardwired zero.
  - `r1`–`r6` — argument / return value registers (caller-saved).
  - `r7`–`r9` — compiler scratch (never allocated to user temporaries).
  - `r10`–`r18` — caller-saved temporaries (register allocator).
  - `r19`–`r29` — callee-saved registers (register allocator, for call-crossing values).
  - `r30` (`sp`) — stack pointer.
  - `r31` (`lr`) — link register.
- **Memory**: 16-bit word-addressed space (0x0000–0xFFFF). Memory-mapped terminal I/O at 0x9F80–0x9FC6.
- **ALU**: 16-bit. No hardware division; the compiler emits calls to `__udiv`/`__umod` runtime helpers.

### Runtime (`runtime/runtime.asm`)

At boot, the runtime binary-searches the address space to find the top of writable RAM, initializes `r30` (sp), configures the terminal MMIO (geometry, colors, newline mode), clears the screen, then jumps to `main`.

Provided library functions: `putchar`, `getchar`, `puts`, `print_int`, `print_uint`, `print_hex`, `printf` (supports `%d %u %x %c %s %%`), `strlen`, `strcmp`, `strcpy`, `memset`, `memcpy`.

## Supported C Features

### Types
| Type | Status |
|---|---|
| `int`, `unsigned int` | Full support |
| `char`, `unsigned char` | Full support |
| `void` | Full support |
| `long`, `unsigned long` | Parsed and type-checked; **16-bit arithmetic only** (see Limitations) |
| Pointers (single and multi-level) | Full support |
| 1D arrays (fixed size, inferred size, initializer lists) | Full support |
| Multi-dimensional arrays | Full support |
| `struct`, `union` (nested, global, arrays of) | Full support |
| `enum` (with optional tag, initializers) | Full support |
| `typedef` (aliases, function-pointer typedefs) | Full support |
| `va_list` | Full support (alias for `int*`) |

### Declarations
- Global and local variable declarations with optional initializer
- Multiple declarators: `int a, b = 2, c;`
- Function declarations (forward declarations) and definitions
- `static` and `extern` storage class (global and local static with persistence)
- Array initializer lists `{...}` with zero-fill for partial initializers
- Inferred array size: `int arr[] = {1,2,3}`, `char s[] = "hello"`

### Statements
- `if` / `if-else`
- `while`, `do-while`, `for` (init may declare a variable)
- `return`, `break`, `continue`
- `switch` / `case` / `default` (with fallthrough support)
- `goto` and labels
- Inline assembly: `asm("template" : "r"(expr), ...)` — input operands, `%0`–`%9` substitution

### Expressions
- Integer literals: decimal, hex (`0x`), octal (`0`-prefix); `u`/`l` suffixes accepted
- Character literals: `\n \t \r \0 \\ \' \"`
- String literals (adjacent concatenation)
- Arithmetic: `+ - * / %`
- Bitwise: `& | ^ ~ << >>`
- Comparison: `== != < > <= >=`
- Logical: `&& ||` (short-circuit)
- Compound assignment: `+= -= *= /= %= &= |= ^= <<= >>=`
- Pre/post `++` / `--`
- Ternary `? :`
- `sizeof(type)` and `sizeof expr`
- Cast `(type)expr`
- Address-of `&`, dereference `*`
- Array subscript `a[i]` (including multi-dimensional)
- Member access `.` and `->` (with field offset arithmetic)
- Function calls: ≤6 args in registers (`r1`–`r6`), 7th+ args via stack
- Variadic calls: `va_start` / `va_arg` / `va_end`
- Function pointer calls (typedef, local/global declarators, arrays of function pointers, passing as argument)

### Preprocessor
- `#include "file"` and `#include <file>`
- Object macros: `#define NAME` and `#define NAME value`
- Function-like macros: `#define F(a,b) ...` including variadic `...`/`__VA_ARGS__`
- Stringification (`#arg`) and token pasting (`a##b`) with correct prescan rules
- `#undef`
- `#ifdef` / `#ifndef` / `#if <expr>` / `#elif <expr>` / `#else` / `#endif`
- `defined(NAME)` and `defined NAME` in `#if`/`#elif` expressions
- Full `#if` expression evaluator: arithmetic, bitwise, logical, relational, ternary `?:`, char/hex/octal/binary literals
- `#error`, `#warning`, `#pragma` (ignored)
- Predefined macros: `__FILE__`, `__LINE__`, `__DATE__`, `__TIME__`, `__STDC__`

## Limitations

See [TODO.md](TODO.md) for the full list. Key gaps:

- **`long` arithmetic** — type is tracked but all arithmetic is 16-bit; multi-word codegen not implemented
- **Integer literals > 16 bits** — truncated at IR generation; multi-word constants not emitted
- **Struct/union pass-by-value** — use pointers; hidden-pointer ABI not generated
- **`short`, `signed`, `const`, `volatile`, `register`** — parsed but `const`/`volatile` ignored; `short` not implemented
- **`float`, `double`** — no support at any level
- **`__func__` / `__FUNCTION__`** — C99 implicit per-function string; not yet implemented
- **Designated initializers** — `{.field = val, [3] = x}` not supported
- **Compound literals** — `(Type){...}` not supported
- **Inline asm output operands / clobbers** — input-only `asm()`
- **Bitfield struct members** — `: N` not supported
- **Variable-length arrays (VLAs)** — not supported
- **Signed division** — `__udiv`/`__umod` are unsigned helpers; no signed division

## Usage

```bash
# Compile
python compiler.py examples/hello.c -o output.asm

# With source annotations and verbose stages
python compiler.py examples/hello.c -o output.asm -v -g
```

### CLI Options

| Option | Effect |
|---|---|
| `-o <file>` | Output assembly path |
| `-v`, `--verbose` | Print pipeline stages to stderr |
| `-g`, `--annotate` | Embed C source lines as comments in output |
| `--dump-tokens` | Dump lexer token stream to stderr |
| `--dump-ast` | Dump parsed AST to stderr |
| `--dump-ir` | Dump IR before and after optimization |
| `--dump-ir-pre` | Dump IR before optimization only |
| `--dump-ir-post` | Dump IR after optimization only |
| `--dump-opt-stats` | Print instruction/function count delta per pass |
| `--stop-after {lex,parse,semantic,ir,opt,codegen}` | Stop after the named stage |

## Project Structure

```
compiler.py          — CLI entry point
compiler/
  lexer.py           — Tokenizer
  parser.py          — Recursive descent parser (tokens → AST)
  ast_nodes.py       — AST node definitions
  semantic.py        — Type checking and symbol table
  irgen.py           — AST → Three-Address Code IR
  ir.py              — IR instruction and operand definitions
  fold.py            — Constant folding and copy propagation
  dce.py             — Dead code and dead function elimination
  regalloc.py        — Linear-scan register allocator
  codegen.py         — IR → R316 assembly
runtime/
  stdlib.h           — C standard library declarations
  runtime.asm        — Bootstrap and runtime helpers
docs/
  ABI.md             — Calling convention and register usage specification
TODO.md              — Known issues and planned work
```

## License

Provided "as-is" for educational and hobbyist use in The Powder Toy community.

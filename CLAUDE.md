# CLAUDE.md — Project Guide for c2r316

## Project Overview

c2r316 is a C → R316 assembly cross-compiler written in Python. It compiles C source code into TPTASM assembly for the R316 virtual machine (16-bit ALU, 32-bit registers, 16-bit address space).

## Architecture

```
C Source → Lexer → Parser → Semantic → IRGen → Codegen → R316 ASM
```

- `compiler.py` — CLI entry point
- `compiler/lexer.py` — Tokenizer
- `compiler/parser.py` — Recursive descent parser (tokens → AST)
- `compiler/semantic.py` — Type checking + symbol table
- `compiler/irgen.py` — AST → Three-Address Code IR
- `compiler/codegen.py` — IR → R316 assembly
- `compiler/ast_nodes.py` — AST node definitions
- `compiler/ir.py` — IR instruction/operand definitions
- `runtime/runtime.asm` — Standard library (putchar, getchar, puts, print_int, etc.)

## Key Documents

- **`docs/ABI.md`** — R316 C Compiler ABI specification. **MUST read before modifying codegen, runtime, or any calling-convention-related code.** Covers register classification, argument passing, return values, stack frame layout, long (32-bit) arithmetic, and edge cases.

## R316 Machine Specs

- 32 general-purpose 32-bit registers (r0=zero, r1–r31), 16-bit ALU
- 16-bit word-addressed address space (0x0000–0xFFFF)
- Memory-mapped I/O for terminal (0x9F80–0x9FC6)
- No hardware stack; software-managed via r30 (sp) and r31 (lr)
- Quasi-32-bit: four "physically zero" values cannot be stored in memory

## Working Rules

- **Analyze in small steps**: When analyzing code or assembly output, break the analysis into small, focused steps. Read or examine one section at a time, confirm each step before proceeding to the next. Do NOT attempt to analyze everything in a single pass — this causes errors and omissions.

## Debugging

- `--dump-tokens` — dump lexer tokens to stderr
- `--dump-ast` — dump AST to stderr
- `--dump-ir` — dump IR to stderr
- `--stop-after {lex,parse,semantic,ir,codegen}` — stop after a compilation stage
- `-g` / `--annotate` — annotate ASM with source line comments (requires parser line tracking, see below)
- `-v` / `--verbose` — print compilation stages
- Error messages include source context with caret indicator

## Known Issues

- Parser does not support array initializer syntax `{1, 2, 3}`
- Stack arguments for 7th+ params not implemented (r1–r6 register args work)
- `long` (32-bit) type has no code generation support
- `-g` flag produces no source annotations: parser doesn't set `line` attribute on AST nodes, so `irgen._loc()` always returns `None`
- Integer literals larger than 16 bits are passed through to codegen as-is; codegen does not handle multi-word constants
- `sizeof(struct T)` fails to parse — `sizeof` is not implemented in the parser
- Struct/union pass-by-value (hidden pointer ABI) not implemented; use pointers instead
- `typedef struct { ... } Name;` not supported; use tag names directly

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

## Known Issues

- `compiler/parser.py`: `_parse_ternary` and `_parse_eq` have duplicate method definitions (second one wins)
- `compiler/irgen.py`: `_strings` is a class variable instead of instance variable (shared across compilations)
- Parser does not support ternary operator `? :` or array initializer syntax `{1, 2, 3}`
- Codegen only passes arguments in r1–r4; stack arguments (>4 params) not implemented
- Callee-saved register preservation not implemented in codegen
- `long` (32-bit) type has no code generation support
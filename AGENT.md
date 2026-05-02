# AGENT.md

Project guide for coding agents working on c2r316.

## Agent Rules

- Be explicit about assumptions and ask when a requirement is ambiguous.
- Keep changes small and directly tied to the user request.
- Match existing style instead of doing unrelated cleanup.
- Do not add speculative features, abstractions, or configurability.
- Remove only unused code created by your own changes.
- Verify changes with the narrowest useful test, and broaden tests when touching shared compiler behavior.

## Project Overview

c2r316 is a C to R316 assembly cross-compiler written in Python. It compiles C source into TPTASM assembly for the R316 virtual machine.

Pipeline:

```text
C Source -> Lexer -> Parser -> Semantic -> IRGen -> Codegen -> R316 ASM
```

Key files:

- `compiler.py` - CLI entry point
- `compiler/lexer.py` - tokenizer
- `compiler/parser.py` - recursive descent parser
- `compiler/semantic.py` - type checking and symbol table
- `compiler/irgen.py` - AST to three-address-code IR
- `compiler/codegen.py` - IR to R316 assembly
- `compiler/ast_nodes.py` - AST node definitions
- `compiler/ir.py` - IR instruction and operand definitions
- `compiler/preprocessor.py` - C preprocessor support
- `runtime/runtime.asm` - standard runtime helpers
- `tests/test_compiler.py` - main test harness
- `tests/r316_emu.py` - in-process R316 emulator used by execution tests
- `tests/programs/` - C execution test programs
- `tests/golden/` - expected stdout for execution tests

## Required Reading

- Read `docs/ABI.md` before changing codegen, runtime, stack layout, calling convention, argument passing, return values, or 32-bit arithmetic.
- Read `docs/DEBUG_API.md` before debugging runtime or codegen behavior with the emulator.
- Check `TODO.md` and grep the source before claiming a feature is missing.
- Use `IMPROVEMENTS.md` as the menu for larger improvement work.

## R316 Notes

- 32 general-purpose 32-bit registers: `r0` is zero, `r30` is `sp`, `r31` is `lr`.
- 16-bit ALU with 32-bit register values.
- 16-bit word-addressed memory, `0x0000` to `0xFFFF`.
- Terminal MMIO lives at `0x9F80` to `0x9FC6`.
- There is no hardware stack; stack behavior is managed in software.
- Some physically-zero 32-bit values cannot be stored in memory.

## Symbol Naming

Compiler-emitted user C symbols must be prefixed with `_C_` in assembly, for example `main` becomes `_C_main`. Runtime helper symbols are not prefixed. `runtime/runtime.asm` calls `_C_main`.

## Testing

Run the main suite from the repo root after compiler changes:

```powershell
python tests/test_compiler.py
```

When adding a new execution program:

1. Add `tests/programs/test_*.c`.
2. Run `python tests/gen_goldens.py`.
3. Inspect the generated `tests/golden/*.txt`.
4. Commit both the C file and golden output.

Never regenerate goldens only to hide a failure. Confirm the new output is correct.

## Debugging

Prefer the emulator API over print-and-rerun loops for runtime/codegen issues:

- Use `Machine` from `tests/r316_emu.py`.
- Start with `docs/DEBUG_API.md` for method names and examples.
- Use breakpoints, `step()`, register/memory inspection, traces, and `save_state()` / `restore_state()`.
- Use CLI dumps only when they are the clearest tool for compile-time inspection.

Useful CLI flags:

- `--dump-tokens`
- `--dump-ast`
- `--dump-ir`, `--dump-ir-pre`, `--dump-ir-post`
- `--dump-opt-stats`
- `--stop-after {lex,parse,semantic,ir,opt,codegen}`
- `-g` / `--annotate`
- `-I DIR`
- `-v` / `--verbose`

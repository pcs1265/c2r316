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
- `compiler/preprocessor.py` — C preprocessor (`#include`, `#define`, conditionals)
- `compiler/builtins.h` — auto-prepended built-in helpers (division, etc.)
- `compiler/fold.py`, `compiler/dce.py`, `compiler/inline.py`, `compiler/regalloc.py` — IR optimization passes
- `runtime/runtime.asm` — Standard library (putchar, getchar, puts, print_int, etc.)
- `tests/test_compiler.py` — Test harness (lexer/parser checks + emulator-based execution tests)
- `tests/r316_emu.py` — In-process Python R316 emulator: parses generated asm, executes it, captures stdout via terminal MMIO. Used by execution tests.
- `tests/programs/` — Test C programs (`test_*.c`). Each may have a `.stdin` sidecar for programs that read input.
- `tests/golden/` — Captured stdout for each `tests/programs/test_*.c`. Execution tests compare emulated output byte-for-byte against these.
- `tests/gen_goldens.py` — Regenerates golden files. Run after intentional output-changing changes — never just to make a failing test pass.

## Key Documents

- **`docs/ABI.md`** — R316 C Compiler ABI specification. **MUST read before modifying codegen, runtime, or any calling-convention-related code.** Covers register classification, argument passing, return values, stack frame layout, long (32-bit) arithmetic, and edge cases.
- **`TODO.md`** — current state of the compiler: implemented features, known issues, not-yet-implemented features. Check before adding a feature to confirm it isn't already done or already tracked.
- **`IMPROVEMENTS.md`** — full prioritized survey of potential improvements (correctness, optimization, runtime, tooling, testing). Use this as the menu when picking the next non-trivial task.

## R316 Machine Specs

- 32 general-purpose 32-bit registers (r0=zero, r1–r31), 16-bit ALU
- 16-bit word-addressed address space (0x0000–0xFFFF)
- Memory-mapped I/O for terminal (0x9F80–0x9FC6)
- No hardware stack; software-managed via r30 (sp) and r31 (lr)
- Quasi-32-bit: four "physically zero" values cannot be stored in memory

## Working Rules

- **Analyze in small steps**: When analyzing code or assembly output, break the analysis into small, focused steps. Read or examine one section at a time, confirm each step before proceeding to the next. Do NOT attempt to analyze everything in a single pass — this causes errors and omissions.
- **Run the test suite after compiler changes**: `python tests/test_compiler.py` from the repo root. It smoke-compiles every `tests/programs/test_*.c` plus targeted feature checks. Add a new check there when adding a language feature or fixing a bug.
- **Check `TODO.md` before claiming a feature is missing**: the TODO file occasionally lags reality (e.g. `typedef` was implemented well before its TODO entry was removed). Grep the source first.
- **Don't bypass the `_C_` symbol prefix**: see Symbol Naming Convention. Runtime helpers are the only unprefixed user-callable names.

## Symbol Naming Convention

All user-defined C symbols (functions and global variables) are emitted with a `_C_` prefix in the output assembly (e.g. C `main` → `_C_main`, C `add` → `_C_add`). This avoids collisions with TPTASM reserved mnemonics. `runtime/runtime.asm` calls `_C_main` as the entry point. Runtime helper names (e.g. `__stack_init`, `__term_init`) are defined in `runtime.asm` and are **not** prefixed by the compiler.

## Debugging

- `--dump-tokens` — dump lexer tokens to stderr
- `--dump-ast` — dump AST to stderr
- `--dump-ir` — dump IR before and after optimization (or `--dump-ir-pre` / `--dump-ir-post`)
- `--dump-opt-stats` — print instruction/function count delta per optimization pass
- `--stop-after {lex,parse,semantic,ir,opt,codegen}` — stop after a compilation stage
- `-g` / `--annotate` — annotate ASM with source line comments
- `-I DIR` — add include search path
- `-v` / `--verbose` — print compilation stages
- Error messages include source context with caret indicator

## Testing

- `python tests/test_compiler.py` — runs all checks; exit code is non-zero if any fail.
- Individual feature checks live in that file as `test_*` functions. Add new ones there rather than creating ad-hoc scripts.
- The harness invokes `compile_c` from `compiler.py` directly (not via subprocess), so failures show full Python tracebacks.

### Three layers of tests

1. **Lexer / parser feature tests** — small C snippets compiled to ASM, checked with substring or AST assertions. Catches token-level and parser-level bugs.
2. **Targeted execution tests** (`test_execution_smoke`, `test_print_int_signed`) — small programs run through the in-process R316 emulator (`tests/r316_emu.py`), return value and stdout asserted. Catches codegen and IR-optimization bugs.
3. **Golden execution tests** (`test_examples_run`) — every `tests/programs/test_*.c` is compiled, executed in the emulator, and its **full stdout** is compared byte-for-byte against `tests/golden/<name>.txt`. Catches anything the C-level `check()` could lie about (a miscompiled comparator that prints PASS for wrong values), as well as hangs (output truncates before the golden's final bytes), reordering, dropped lines, and any character-level drift.

### Adding tests

- Adding a new `tests/programs/test_*.c`:
  1. Write it (use the standard `check(name, got, expected)` + `PASS:`/`FAIL:` summary pattern, ending with `puts("=== done ===");`).
  2. Run `python tests/gen_goldens.py` to capture its stdout into `tests/golden/`.
  3. Eyeball the golden — confirm the output is what you expect.
  4. Commit both the `.c` and the `.txt`.
- Updating an existing test's expected output: same flow. **Never** regenerate goldens just to silence a failing check; verify by hand first that the new output is correct.

### Emulator scope and limitations

`tests/r316_emu.py` implements the instructions the c2r316 compiler actually emits (`mov add adc sub sbb mul and or xor shl shr ld st jmp <jcc> hlt`) plus the `cmp/test/nop` macros from `common.asm`. Flag handling follows `manual.md`. Execution starts at `_C_main:` with `sp=0x8000` and `lr=sentinel`; the runtime's `__stack_init` and `__term_init` are skipped. Terminal MMIO writes to `0x9FB5` are captured into stdout. **Not** a full TPT-VM emulator; if a future test needs hardware features beyond this, extend `tests/r316_emu.py`.

### Running the emulator standalone

`tests/r316_emu.py` can be run directly to compile-and-run a `.c` file or execute a pre-built `.asm` file:

```
python tests/r316_emu.py examples/hello.c          # compile then emulate
python tests/r316_emu.py output.asm                # emulate .asm directly
python tests/r316_emu.py file.c --show-retval      # also print [exit N]
python tests/r316_emu.py file.c --cycles 5000000   # override cycle limit
```

Program stdout is written to the terminal; the process exits with `main()`'s return value.



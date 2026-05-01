# CLAUDE.md

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

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
- **`docs/DEBUG_CLI.md`** — CLI debugging flags reference (`--dump-tokens`, `--dump-ast`, `--dump-ir`, `-g`, etc.) with usage examples.
- **`docs/DEBUG_API.md`** — **Read this before debugging any runtime/codegen issue.** Programmatic API for the R316 emulator (`Machine` class) — step execution, breakpoints, inspect registers/memory/flags, instruction tracing, save/restore machine state (time-travel debugging), and `compile_c()` for end-to-end C-source-to-emulator workflows. The doc has a full method reference and copy-pasteable examples for the common patterns; consult it instead of re-deriving call signatures from the source.
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
- **Debug runtime issues with the emulator API, not by re-running with prints**: when a compiled program does the wrong thing, drive `Machine` from a small Python script (step, breakpoint, trace, `get_memory`, `save_state`/`restore_state`). **`docs/DEBUG_API.md` is the reference — read it first**, it has the full method list and ready-to-paste examples. See also the *Debugging* section below. This is almost always faster than edit-recompile-rerun loops, and lets you pinpoint the exact instruction that produced a bad value. A trace agent recently saved >5 cycles of guess-and-check by walking `get_trace()` backwards to find the `st` that clobbered code.

## Symbol Naming Convention

All user-defined C symbols (functions and global variables) are emitted with a `_C_` prefix in the output assembly (e.g. C `main` → `_C_main`, C `add` → `_C_add`). This avoids collisions with TPTASM reserved mnemonics. `runtime/runtime.asm` calls `_C_main` as the entry point. Runtime helper names (e.g. `__stack_init`, `__term_init`) are defined in `runtime.asm` and are **not** prefixed by the compiler.

## Debugging

### Reach for the emulator API first, not print-and-rerun

When a generated program misbehaves (wrong output, hang, "non-instruction" crash, suspicious value), **drive the emulator programmatically via `Machine`** instead of running the binary repeatedly with `print` statements added to the C. The API lives in `tests/r316_emu.py` and is fully documented in **`docs/DEBUG_API.md`** — open that doc first; it has the method reference and copy-pasteable examples for every pattern below. Concretely:

- **Step + inspect** when you need to see what a specific stretch of asm actually does. Set a breakpoint at a label, run to it, then `step()` one instruction at a time, reading `get_registers()` / `get_flags()` / `get_memory()` between steps. Catches wrong register, wrong flag, off-by-one in pointer arithmetic.
- **Trace + replay** for "where did this value come from?". `enable_trace()`, run, then walk `get_trace()` backwards from the bad register/memory state to the instruction that produced it. Much faster than re-deriving by reading asm.
- **`save_state()` checkpoints** before a suspect block, then `restore_state()` to re-run it with different breakpoints / probes — no recompiling, no replaying earlier setup.
- **Catch stray writes** by stepping past every `st` and checking the destination address against the layout you expect. The "non-instruction at pc=…" error tells you *when* code got clobbered; the trace tells you *who* did it.
- **Skip the C round-trip** for codegen-only investigations: build a tiny `Program` from inline asm via `parse_asm()`, no compiler involved.

Reach for `--dump-ir` / re-running the binary only when the API genuinely can't tell you what you need. A single Python script that loads the program and pokes at it is almost always faster than five `print`-edit-recompile cycles.

### CLI flags (for compile-time inspection)

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

`tests/r316_emu.py` implements the instructions the c2r316 compiler actually emits (`mov add adc sub sbb mul and or xor shl shr ld st jmp <jcc> hlt`) plus the `cmp/test/nop` macros from `common.asm`. Flag handling follows `manual.md`. Execution starts at the runtime `start:` label with `sp=0` and `lr=sentinel` — the runtime's `__stack_init` / `__term_init` run normally, set up sp, and call `_C_main`. Terminal MMIO writes to `0x9FB5` are captured into stdout. **Not** a full TPT-VM emulator; if a future test needs hardware features beyond this, extend `tests/r316_emu.py`.

**Memory model:** flat 64K-word RAM in source order. `parse_asm` lays each instruction and each `dw` word at the next address starting from 0, so code and data share one address space (the same model real R316 sees — code IS RAM). Each cell is either an `Insn` object (instruction) or an `int` (data, zero for unwritten cells). A store into a code address replaces the `Insn` with the int, and the next fetch there raises *executing non-instruction at pc=…* — roughly what real R316 would do when decoding the garbage. Reads of un-clobbered code cells return 0 (we have no real opcode encoding to hand back). Labels live in one map (`prog.labels`) regardless of whether they point at code or data.

### Running the emulator standalone

`tests/r316_emu.py` can be run directly to compile-and-run a `.c` file or execute a pre-built `.asm` file:

```
python tests/r316_emu.py examples/hello.c          # compile then emulate
python tests/r316_emu.py output.asm                # emulate .asm directly
python tests/r316_emu.py file.c --show-retval      # also print [exit N]
python tests/r316_emu.py file.c --cycles 5000000   # override cycle limit
```

Program stdout is written to the terminal; the process exits with `main()`'s return value.



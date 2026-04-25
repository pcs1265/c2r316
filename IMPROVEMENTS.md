# c2r316 — Potential Improvements

A complete, prioritized survey. Items are tagged by **size** (S/M/L/XL) and **value** (★/★★/★★★).
Sized for one engineer; XL means "a multi-week project, plan first."

---

## 1. Language Correctness & Coverage

### Critical — known bugs / silent miscompiles
| Item | Size | Value | Notes |
|---|---|---|---|
| 32-bit `long` arithmetic | XL | ★★★ | Type parses but codegen is 16-bit. Need `add+adc`, `sub+sbb`, `mul+mulh` on register pairs, even-register alignment per ABI §9. Touches IR (split `IBinOp` for long, or post-pass that lowers long ops), codegen, regalloc, fold (constant fold of long), and runtime helpers (`__lmul`, `__ldiv`). |
| Integer literals > 16 bits | M | ★★★ | Currently truncated at IR generation. Needs multi-word `ImmInt` (or `ImmLong`) and codegen that emits two `mov` instructions. Blocked by long arithmetic. |
| Static local variables | S | ★★ | `is_static` flag exists but irgen treats them as ordinary locals. Need to lower static locals to globals with mangled names (e.g. `_C_func_var`) and skip frame allocation. |
| Struct/union pass-by-value | M | ★★ | ABI §4 hidden-pointer convention not generated. Caller allocates result slot and passes its address as implicit first arg; callee writes through it. Symmetric for parameters. |
| Pointer arithmetic scaling | S | ★★ | Verify `p + n` scales by `sizeof(*p)`. Spot-check codegen for non-`int*` pointers; if missing, add scaling in irgen. |
| Standard integer promotions | M | ★★ | `char + char` should promote to `int` per C99 §6.3.1.1. Likely partial. Audit semantic + irgen. |

### Missing language features
| Item | Size | Value | Notes |
|---|---|---|---|
| `switch` / `case` / `default` / fallthrough | M | ★★★ | Add tokens, parse statement, lower to either chained `if` (simple) or jump table (when cases are dense). Jump table needs a label-array IR op. |
| `goto` and labels | S | ★★ | Add `Label` and `Goto` IR ops; parser collects labels per function and emits `LabelDef`/`IGoto`. Validate labels resolve at end of function. |
| Multi-dimensional arrays `int a[3][4]` | S | ★★ | Parser already builds `CArray`; just iterate the bracket loop. Subscripting `a[i][j]` and address arithmetic must scale by inner dim. |
| `__func__` / `__FUNCTION__` | S | ★ | Per-function implicit `static const char[]` initialized to function name. Inject at irgen during function prologue if referenced. |
| Designated initializers `{.field = val, [3] = x}` | M | ★★ | Parse `.field` and `[idx]` prefixes inside init lists; resolve to offset, fill remaining slots with zero. |
| Compound literals `(Type){...}` | M | ★ | Lower to a temporary local of `Type` initialized in place. |
| Inline asm output operands + clobbers | M | ★★ | Currently input-only. Output `=r` needs to bind a temp and write it back; clobbers force regalloc to spill. Real value for hand-tuned routines. |
| Bitfield struct members `: N` | M | ★ | Need bit-level load/store and packed layout rules. |
| `enum` constant expressions | S | ★ | Currently only literal `= INT` is allowed; extend to a tiny constant evaluator (handles `+ - * / & | ^ << >> ~ ! && \|\|`). |
| `short`, `signed`, `const`, `volatile`, `register` | S each | ★★ | `const`/`volatile` parsed-and-ignored is fine for now (no harm). `short` should map to a 16-bit type (already the natural width). `signed` is a no-op modifier on `int`/`char`. |
| `_Bool` / `bool` | S | ★ | One-bit type that normalizes to 0/1 on store. Trivial via `& 1`. |
| `float` / `double` | XL | ★ | Would require a soft-float runtime (or fixed-point). Probably not worth it on a 16-bit ALU unless there's a specific use case. |
| Function-pointer declarators in more positions | S | ★ | Already in params/locals/globals; verify in `typedef`, returns. |
| Variable-length arrays (VLAs) | L | ★ | Stack allocation with dynamic size. Low priority. |

### Standard-conformance polish
- Implicit conversions in conditionals (`if (p)` where `p` is a pointer) — verify.
- Empty struct rejection (`struct S {};` is a GCC extension).
- `void` parameter list (`int f(void)`) explicitly distinguishes "zero args" from "unspecified".
- Function declarators with prototypes vs. K&R-style — the former is required; reject K&R.
- Tentative definitions and multiple `extern` decls.

---

## 2. Optimization

### IR-level passes (new)
| Item | Size | Value | Notes |
|---|---|---|---|
| Common subexpression elimination (CSE) | M | ★★★ | Per the existing TODO note: `&arr` recomputed on every array access. Hash `(op, operands)` within a basic block; replace duplicates with the first temp. |
| Dead store elimination | M | ★★ | Requires liveness analysis on `Var`s, not just `Temp`s. Catches "x = 5; x = 6" and writes-then-overwrite patterns. |
| Loop-invariant code motion (LICM) | L | ★★ | Detect natural loops, hoist invariant computations out of the header. Non-trivial without dominator tree. |
| Strength reduction | S | ★★ | `x * 2^n` → `x << n`, `x / 2^n` (unsigned) → `x >> n`, `x % 2^n` (unsigned) → `x & (2^n - 1)`. Pure local rewrite in `fold.py`. |
| Algebraic simplification | S | ★★ | `x + 0`, `x * 1`, `x & 0`, `x \| 0`, `x ^ x`, `x - x`, `x && 1`, etc. Add to `fold.py`. |
| Branch threading | M | ★ | If `if (c) goto L1; else goto L2;` and L1 is `goto L3`, retarget. Cleans up fold/DCE leftovers. |
| Tail-call optimization | M | ★★ | When a function ends with `return f(args)`, jump instead of call+ret. Saves a frame on recursive helpers. Needs ABI compatibility check (same arity, same return type). |
| Better inlining heuristics | M | ★ | Today appears `always_inline`-only. Add small-leaf-function auto-inlining (size < N IR instrs, no recursion, called ≤ K times). Run fold→DCE iteratively until fixed point. |
| Copy propagation through `Var` sources | M | ★ | Blocked per TODO: needs distinguishing address-position vs. value-position uses of a `Var`. Mark IR ops with which operands are addresses (already implicit in op kind — formalize). |
| Constant propagation across basic blocks | M | ★ | Today's `fold.py` is local. Add a tiny worklist-based sparse conditional constant propagation. |
| Switch jump-table lowering | S | ★ | Once `switch` exists, emit `jmp [tbl + r]` for dense cases. R316 has indirect jumps via register; encode the table as 16-bit words. |

### Codegen / ASM peephole
| Item | Size | Value | Notes |
|---|---|---|---|
| More peephole patterns | S | ★★ | `mov rX, rX` → delete. `add rX, 0` → delete. `mov rX, 0` after a jc/jz that already cleared via `r0` → use `r0`. Adjacent `st`/`ld` of same slot beyond current pattern. `sub r0, a, b; jl L` → `cmp+jl`. |
| Use `r0=zero` more aggressively | S | ★ | Anywhere a literal zero is needed, prefer `r0` over `mov rX, 0`. |
| Shorter prologue/epilogue for leaf functions | M | ★★ | If a function calls nothing and uses no callee-saved regs, skip pushing/popping `lr` and frame setup. Halves the prologue cost on small helpers. |
| Coalesce contiguous spill slots | S | ★ | Reorder spills so the frame can use one `sub r30, N` and one `add r30, N` for the whole batch. |

### Register allocator
| Item | Size | Value | Notes |
|---|---|---|---|
| Graph-coloring allocator | XL | ★★ | Replace linear scan. Better spill choices, especially around long-lived call-crossing values. |
| Live-range splitting | L | ★ | Split a temp's range at a call boundary so part lives in caller-saved, part in callee-saved. Reduces spill pressure. |
| Move coalescing | M | ★★ | After regalloc, fold `mov rA, rB` when ranges don't conflict. Often eliminated by peephole today, but coalescing during alloc avoids the spill in the first place. |
| Spill cost heuristic | S | ★ | Today probably FIFO. Spill the temp with the lowest use-density (uses / live-range-length). |

### R316-specific
- Memory-mapped I/O builtins (`__builtin_putchar` → direct `st rX, 0x9F80`) — bypasses runtime call overhead in tight loops.
- `jc` after subtract for unsigned compare — already used; document the pattern in ABI.md.
- Constant pool for repeated 16-bit literals in a function — emit once, `ld` from a local label.

---

## 3. Diagnostics

| Item | Size | Value |
|---|---|---|
| Error recovery (don't bail on first parse error) | M | ★★ |
| `-Wunused-variable`, `-Wunused-function` | S | ★★ |
| `-Wuninitialized` (simple flow-insensitive) | M | ★ |
| `-Wshadow` (local shadows global / outer local) | S | ★ |
| `-Wsign-compare` | S | ★ |
| `-Wimplicit-fallthrough` (once switch lands) | S | ★ |
| Color output (ANSI when stderr is a TTY) | S | ★ |
| Multi-line caret + squiggle range | S | ★★ |
| "Did you mean…?" for typos (Levenshtein on symbol table) | S | ★ |
| Type-mismatch errors include both types in detail | S | ★★ |
| `--Werror` | S | ★ |

---

## 4. Runtime / stdlib

| Item | Size | Value | Notes |
|---|---|---|---|
| `string.h` core: `memcpy`, `memmove`, `memset`, `memcmp`, `strlen`, `strcmp`, `strcpy`, `strncpy`, `strcat` | M | ★★★ | Most C programs need these. Implement in C in `runtime/string.h`/`.c` and let DCE drop unused. |
| `stdlib.h`: `abs`, `atoi`, `min/max` macros | S | ★★ | Trivial. |
| Real `printf` | L | ★★★ | Currently `print_int`, `puts`. Add `%s %d %u %x %o %c %%` plus width/precision/padding. Variadic-aware. |
| `malloc`/`free` (bump or freelist) | M | ★ | If heap is desired. Bump allocator first; freelist later. Document heap region in ABI. |
| `assert(x)` | S | ★★ | Macro that calls `__assert_fail(file, line, msg)` runtime. Critical for finding bugs in test programs. |
| `setjmp`/`longjmp` | M | ★ | Saves callee-saved regs + sp/lr to a `jmp_buf`. Useful but niche. |
| More escape: `\u`, `\U` | S | ★ | Unicode literals — low value on a terminal. |

---

## 5. Tooling / Developer Experience

| Item | Size | Value | Notes |
|---|---|---|---|
| Run tests on the actual R316 VM (`r3.lua`) | M | ★★★ | Lock in semantics, not just compilability. Spawn lua, feed compiled binary, check stdout against expected. The single biggest correctness multiplier. |
| Direct binary output (invoke TPTASM from the compiler) | S | ★★ | `--emit=bin` calls TPTASM and writes a flashable image. Removes a manual step. |
| `--emit-cfg` (Graphviz of basic blocks per function) | S | ★ | Helps debug optimizations. |
| `--time-passes` | S | ★ | Profile the compiler itself. |
| `--annotate` already exists; extend with IR-line cross-references | S | ★ | When dumping IR, also show originating source line and resulting ASM lines. |
| Source-level debug info | L | ★ | A simple `.dbg` sidecar mapping ASM addresses → source lines. Enables a step-debugger if `r3.lua` ever grows one. |
| LSP / editor integration | XL | ★ | Big project. Pylance-of-c-r316. Probably not worth it for a single-target hobby compiler. |
| pyproject.toml + `pip install c2r316` | S | ★ | Makes the compiler installable as a CLI. |
| GitHub Actions CI | S | ★★ | Run `python tests/test_compiler.py` on every push. |

---

## 6. Testing

| Item | Size | Value | Notes |
|---|---|---|---|
| Golden ASM snapshots for every example | S | ★★ | Lock in current codegen so future regressions show up as diffs. Update with `--update-golden`. |
| Execution tests on `r3.lua` | M | ★★★ | Each test C file declares expected stdout; harness compiles, assembles, runs, diffs. |
| Edge-case suite | M | ★★ | Targeted programs: deep recursion, max args, struct with one field, struct with many fields, nested ternary, short-circuit side effects, va_list with 0/1/many varargs, function pointer to varargs, etc. |
| Differential testing vs. GCC | L | ★ | Run the same C program on GCC + R316; compare output. Works only for portable subset. Catches a lot of subtle conformance bugs. |
| Random / fuzz testing | L | ★ | csmith-style generator for the supported subset. Find crashes in the compiler. |
| Performance regression tracking | S | ★ | Record `instrs in` and `instrs out` per example; fail CI if a known-good example regresses by >5%. |
| Coverage measurement | S | ★ | `coverage.py` over the test suite; identify untested compiler branches. |

---

## 7. Architecture / Code Health

| Item | Size | Value | Notes |
|---|---|---|---|
| Standard pass interface | M | ★ | Today `fold(ir)`, `dce(ir)`, `inline(ir)` are ad-hoc. Define `class Pass: name; run(ir) -> stats;` and a pass manager that handles `--time-passes`, `--print-after-X`, etc. |
| Type hints + mypy | M | ★ | Most files have partial hints. Tighten and run mypy in CI. |
| Format with `ruff format` / `black` | S | ★ | Consistent style. |
| Split `codegen.py` (1100 lines) | M | ★ | Roughly: instruction selection, prologue/epilogue, peephole, asm emission. Each is a separable concern. |
| Document each module's contract in a header docstring | S | ★ | One paragraph per file: inputs, outputs, invariants. |
| Architecture doc (`docs/ARCHITECTURE.md`) | S | ★★ | Pass-by-pass walkthrough. Crucial for onboarding (and for future-you). |

---

## 8. Preprocessor

| Item | Size | Value | Notes |
|---|---|---|---|
| `#include_next` | S | ★ | Useful for layering stdlib over runtime. |
| `_Pragma("…")` | S | ★ | Equivalent to `#pragma`. |
| `__COUNTER__` | S | ★ | Useful for unique label generation in macros. |
| Macro hygiene fixes (verify `##` and `#` edge cases) | M | ★★ | If anything in TPTASM-style headers tickles weird tokenization, audit. |
| `#pragma once` | S | ★ | Common alternative to include guards. |
| Better header search ordering | S | ★ | `-isystem` for standard headers (suppresses warnings within). |

---

## 9. Documentation

| Item | Size | Value |
|---|---|---|
| Quickstart in README (install → first program → run) | S | ★★★ |
| Tutorial: a non-trivial C program for R316 (e.g. a small game / dump tool) | M | ★★ |
| Architecture doc (cross-ref of pipeline stages, IR shape, ABI) | M | ★★ |
| ABI examples for every register-class scenario | S | ★★ |
| Per-pass docs (what fold does, what doesn't, why) | S | ★ |
| Contributing guide | S | ★ |

---

## 10. Recommended sequencing

If picking one improvement at a time, this is the order I'd take based on **value × leverage**:

1. **Run-on-VM execution tests** (5 + 6). Without these, every change in §1–§2 is shipping blind. Highest ROI single item.
2. **Golden ASM snapshots** (§6). Cheap, catches regressions immediately.
3. **`switch` / `case`** (§1). Big language feature, unblocks real programs.
4. **Strength reduction + algebraic simplification** (§2). Smallest possible code change for visible improvement in generated ASM.
5. **`string.h` + real `printf`** (§4). Most-asked-for runtime gap.
6. **Static locals + struct pass-by-value** (§1). Removes the two main "gotchas" users hit when porting C code.
7. **32-bit `long` arithmetic** (§1). Big project; do it after the test infrastructure is solid because it touches every layer.
8. **Pass manager refactor** (§7) — only when there's a third or fourth optimization pass and the ad-hoc invocation in `compiler.py` starts to hurt.
9. **Graph-coloring regalloc** (§2) — only if generated code is benchmarked to actually be regalloc-bound. Linear scan is usually fine for hobby compilers.

Skip indefinitely unless a concrete need appears: float/double, VLAs, LSP, fuzz testing, full graph-coloring regalloc.

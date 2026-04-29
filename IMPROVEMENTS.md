# c2r316 — Potential Improvements

A complete, prioritized survey. Items are tagged by **size** (S/M/L/XL) and **value** (★/★★/★★★).
Sized for one engineer; XL means "a multi-week project, plan first."

---

## 0. Completed Improvements

The following items have been implemented since the last survey:

| Item | Size | Value | Notes |
|---|---|---|---|
| `switch` / `case` / `default` / fallthrough | M | ★★★ | Implemented — dispatch + fallthrough + break + default |
| `goto` and labels | S | ★★ | Implemented — `Label` and `Goto` IR ops; labels mangled to `._user_<name>` |
| Multi-dimensional arrays `int a[3][4]` | S | ★★ | Implemented — parser builds nested `CArray`; subscripting and address arithmetic work |
| Static local variables | S | ★★ | Implemented — static locals lowered to globals with mangled names |
| `sizeof(type)` and `sizeof expr` | S | ★★ | Implemented — parser creates `Sizeof` nodes |
| `enum` with optional tag and initializers | S | ★★ | Implemented — auto-incrementing int constants |
| `typedef` (aliases, function-pointer typedefs) | S | ★★ | Implemented — simple aliases and function-pointer typedefs |
| `const` keyword | S | ★ | Implemented — parsed but ignored (no semantic effect) |
| Function pointer declarators | S | ★ | Implemented — `int (*fp)(int)` parsed in params, locals, globals, typedefs, return types |
| Strength reduction | S | ★★ | Implemented — `x * 2^n` → `x << n`, unsigned `x / 2^n` → `x >> n`, unsigned `x % 2^n` → `x & (2^n - 1)` |
| Algebraic identities | S | ★★ | Implemented — `x & 0`, `x & 0xFFFF`, `x | 0`, `x | 0xFFFF`, `x ^ 0`, self-ops |
| `short`, `signed`, `register` keywords | S | ★★ | Implemented — all parsed and accepted; `short` maps to 16-bit type |
| `string.h` core functions | M | ★★★ | Implemented — `memcpy`, `memmove`, `memset`, `memcmp`, `strlen`, `strcpy`, `strncpy`, `strcat`, `strncat`, `strcmp`, `strncmp`, `strchr`, `strstr` in `include/string.h` |
| `printf` | L | ★★★ | Implemented — `%d %u %x %c %s %%` in `include/stdio.h` |
| `scanf` | M | ★★ | Implemented — `%d %u %x %c %s` in `include/stdio.h` |
| Dead store elimination (DSE) | S | ★★ | Implemented in `compiler/fold.py` — removes stores to locals overwritten before read |
| Common subexpression elimination (CSE) | S | ★★ | Implemented in `compiler/fold.py` — `IAddrOf` CSE and Var-load CSE within basic blocks |
| Trivial jump removal | S | ★ | Implemented in `compiler/fold.py` — eliminates `jmp L` where L is the immediately following label |
| Branch / jump threading | S | ★ | Implemented in `compiler/fold.py` — resolves jump chains (`jmp L1; L1: jmp L2` → `jmp L2`); removes labels no longer referenced after threading |
| Copy propagation | S | ★★ | Implemented in `compiler/fold.py` — propagates `ImmInt`/`StrLabel` constants to all use sites; propagates `Var`/`Temp`/`Global` sources at single-use sites; validates Var sources for clobber safety |
| Constant folding | S | ★★ | Implemented in `compiler/fold.py` — folds all arithmetic, bitwise, shift, and comparison binops; folds unary `-`/`~` on constants; runs after copy propagation until stable |
| Dead function elimination | S | ★★ | Implemented in `compiler/dce.py` — removes functions unreachable from `main` via call-graph reachability (handles function-pointer address-taken references) |
| Function inlining | M | ★★ | Implemented in `compiler/inline.py` — inlines `always_inline` functions unconditionally; auto-inlines small static functions (≤ 10 IR instrs) and non-static functions called exactly once; collapses arbitrarily deep `always_inline` chains in phase 1 |
| Linear scan register allocation | M | ★★ | Implemented in `compiler/regalloc.py` — builds live intervals, classifies call-crossing temps (→ callee-saved) vs. non-crossing (→ caller-saved), spills when no register is free, includes move coalescing |

---

## 1. Language Correctness & Coverage

### Critical — known bugs / silent miscompiles
| Item | Size | Value | Notes |
|---|---|---|---|
| 32-bit `long` arithmetic | XL | ★★★ | Type parses but codegen is 16-bit. Need `add+adc`, `sub+sbb`, `mul+mulh` on register pairs, even-register alignment per ABI §9. Touches IR (split `IBinOp` for long, or post-pass that lowers long ops), codegen, regalloc, fold (constant fold of long), and runtime helpers (`__lmul`, `__ldiv`). |
| Integer literals > 16 bits | M | ★★★ | Currently truncated at IR generation. Needs multi-word `ImmInt` (or `ImmLong`) and codegen that emits two `mov` instructions. Blocked by long arithmetic. |
| Struct/union pass-by-value | M | ★★ | ABI §4 hidden-pointer convention not generated. Caller allocates result slot and passes its address as implicit first arg; callee writes through it. Symmetric for parameters. |
| Pointer arithmetic scaling | S | ★★ | Verify `p + n` scales by `sizeof(*p)`. Spot-check codegen for non-`int*` pointers; if missing, add scaling in irgen. |
| Standard integer promotions | M | ★★ | `char + char` should promote to `int` per C99 §6.3.1.1. Likely partial. Audit semantic + irgen. |

### Missing language features
| Item | Size | Value | Notes |
|---|---|---|---|
| `__func__` / `__FUNCTION__` | S | ★ | Per-function implicit `static const char[]` initialized to function name. Inject at irgen during function prologue if referenced. |
| Designated initializers `{.field = val, [3] = x}` | M | ★★ | Parse `.field` and `[idx]` prefixes inside init lists; resolve to offset, fill remaining slots with zero. |
| Compound literals `(Type){...}` | M | ★ | Lower to a temporary local of `Type` initialized in place. |
| Inline asm output operands + clobbers | M | ★★ | Currently input-only. Output `=r` needs to bind a temp and write it back; clobbers force regalloc to spill. Real value for hand-tuned routines. |
| Bitfield struct members `: N` | M | ★ | Need bit-level load/store and packed layout rules. |
| `enum` constant expressions | S | ★ | Currently only literal `= INT` is allowed; extend to a tiny constant evaluator (handles `+ - * / & | ^ << >> ~ ! && \|\|`). |
| `_Bool` / `bool` | S | ★ | One-bit type that normalizes to 0/1 on store. Trivial via `& 1`. |
| `float` / `double` | XL | ★ | Would require a soft-float runtime (or fixed-point). Probably not worth it on a 16-bit ALU unless there's a specific use case. |
| Variable-length arrays (VLAs) | L | ★ | Stack allocation with dynamic size. Low priority. |

### Standard-conformance polish
- Implicit conversions in conditionals (`if (p)` where `p` is a pointer) — verify.
- Empty struct rejection (`struct S {};` is a GCC extension).
- `void` parameter list (`int f(void)`) explicitly distinguishes "zero args" from "unspecified".
- Function declarators with prototypes vs. K&R-style — the former is required; reject K&R.
- Tentative definitions and multiple `extern` decls.

---

## 2. Optimization

### What is already implemented

The compiler runs the following passes in order (see `compiler.py`):

| Pass | Module | Scope | Algorithm |
|---|---|---|---|
| Constant folding | `fold.py` | Per-function, block-local | Fold binop/unary on `ImmInt` operands; arithmetic, bitwise, shift, comparisons |
| Copy propagation | `fold.py` | Per-function, block-local | Forward substitution of constants (multi-use) and single-use `Var`/`Temp`/`Global` sources |
| Algebraic simplification | `fold.py` | Per-instruction | Identities: `x+0`, `x*1`, `x&0`, `x|0xFFFF`, `x^0`, `x-x=0`, `x^x=0`, self-`&`/`|` |
| Strength reduction | `fold.py` | Per-instruction | `x * 2^n → x << n`; `x % 2^n → x & (2^n-1)` (unsigned only) |
| Dead store elimination | `fold.py` | Per-function, block-local | Removes `IStore(Var, _)` overwritten before read; conservative: skips escaped vars, invalidates on call/label |
| Var-load CSE | `fold.py` | Per-function, block-local | Replaces duplicate `ICopy(t, Var('x'))` with `ICopy(t, prior_temp)`; invalidates on store/call/label |
| AddrOf CSE | `fold.py` | Per-function, block-local | Deduplicates `IAddrOf` instructions for the same variable within a basic block |
| Trivial jump removal | `fold.py` | Per-function | Removes `jmp L` where `L` is the immediately following label; iterates until stable |
| Branch / jump threading | `fold.py` | Per-function | Resolves jump chains to their final targets using a chain map; removes labels that become unreferenced |
| Dead code elimination | `dce.py` | Per-function | Mark-sweep on `Temp` liveness; void-result `ICall` always kept; drops dead temp definitions |
| Dead function elimination | `dce.py` | Whole-program | Call-graph reachability from `main`; address-taken functions (`IAddrOf(t, Global)`) kept |
| Function inlining | `inline.py` | Whole-program | `always_inline`: unconditional; static functions ≤ 10 IR instrs: auto-inline; non-static called exactly once, ≤ 10 instrs, address not taken: auto-inline. Phase 1 collapses deep `always_inline` chains; phase 2 inlines into all other callers |
| Linear scan register allocation | `regalloc.py` | Per-function | Live intervals; call-crossing temps → callee-saved registers, non-crossing → caller-saved; spill on exhaustion; move coalescing |
| Peephole | `codegen.py` | Per-function, ASM level | Patterns applied during ASM emission (e.g. redundant moves) |

Fold + DCE are run iteratively until the IR instruction count stabilizes. Inlining runs before fold/DCE so that the optimizer sees the inlined bodies.

---

### Optimization survey relative to this compiler

The table below classifies every optimization from the survey against the R316 target.

#### Already implemented
Constant Folding, Copy Propagation, Algebraic Simplification, Strength Reduction, Dead Store Elimination, Common Subexpression Elimination (local), Dead Code Elimination, Dead Function Elimination (= Interprocedural DCE), Jump Threading / Branch Threading, Unreachable Code Elimination (after branch threading), Function Inlining (with auto-inline heuristics), Tail Recursion Elimination (self-recursive tail calls → loop), Linear Scan Register Allocation, Move Coalescing (within regalloc), Peephole Optimization (including scratch-register source propagation), Dead Argument Elimination (non-address-taken functions), Spill Cost Heuristic (use-density based eviction), Zero Register (`r0`) Promotion.

#### Applicable — not yet implemented

| Optimization | Size | Value | Notes |
|---|---|---|---|
| **Inter-block constant propagation** | M | ★ | Today's `fold.py` is block-local; constants do not flow across labels. A small worklist-based pass (simplified sparse conditional constant propagation) would propagate `ImmInt` definitions across unconditional edges. Handles the common pattern `x = 0; if (...) x = 1; use(x)` only partially without full SCCP. |
| **Loop-invariant code motion (LICM)** | L | ★★ | Detect natural loops (needs dominator tree or back-edge detection), hoist invariant computations out of the loop header. High payoff when loops contain repeated address computations or constant-value loads. Main cost: building and maintaining the CFG. |
| **Switch jump-table lowering** | S | ★ | For dense `switch` cases, emit a jump table (`jmp [base + r]`) instead of chained comparisons. R316 supports register-indirect jumps. Only applicable when cases form a dense integer range. |
| **Leaf function prologue/epilogue elimination** | M | ★★ | If a function makes no calls and uses only caller-saved registers, skip pushing/restoring `lr` and frame pointer setup entirely. Halves the entry/exit cost of small helpers. Requires the regalloc to report which callee-saved regs it actually used. |
| **Constant pool** | S | ★ | Repeated 16-bit literals used multiple times within one function can be emitted once as a local data word and loaded with `ld`. Saves one instruction per extra use. |
| **Live-range splitting** | L | ★ | Split a temp's range at a call boundary so the pre-call portion uses caller-saved registers and the post-call portion uses callee-saved. Reduces unnecessary callee-save/restore pairs. |

#### Not applicable to R316

The following optimizations from the survey do not apply because of hardware or target constraints:

| Category | Optimizations | Reason |
|---|---|---|
| SIMD / vectorization | Loop Vectorization, SLP, Auto-vectorization, SIMD Optimization, Vector Register Allocation | No SIMD hardware |
| Parallelism | Auto-parallelization, OpenMP, Thread-level parallelism, GPU offloading, Kernel Fusion/Fission | Single-core embedded target |
| Profile-guided | PGO, FDO, Hot/Cold Splitting | No runtime profile infrastructure |
| Link-time | LTO, ThinLTO, Whole Program Optimization | Single-TU compiler; `dce.py` already does whole-program DCE |
| Cache / memory topology | Loop Tiling, Loop Interchange, Cache Optimization, Prefetch Insertion, NUMA Optimization, False Sharing Reduction, Memory Coalescing, Bank Conflict Reduction | R316 has no cache hierarchy |
| Floating point | Soft-float passes, NRVO/RVO for float structs | No float support; out of scope |
| Instruction-level parallelism | Software Pipelining, Modulo Scheduling, Superblock / Hyperblock, Trace Scheduling, Speculative Execution | In-order single-issue core |
| C++-specific | Return Value Optimization (RVO), Named RVO, Copy Elision, Temporary Object Elimination, Devirtualization, Virtual Call Elimination, Object Lifetime Optimization | C target only |
| GC / managed memory | GC Optimization, Escape-based Deallocation, Region-based Allocation, Arena Allocation | No heap allocator; not applicable |
| Speculative / guarded | Guarded Devirtualization, Control/Data Speculation, Warp Divergence Optimization | Not applicable to target |
| Graph-coloring regalloc | Graph Coloring Register Allocation | XL effort; linear scan is adequate for the register count and function sizes typical in R316 programs |

#### Deferred / low priority

| Optimization | Reason deferred |
|---|---|
| Sparse Conditional Constant Propagation (SCCP) | Requires full CFG and SSA form; high complexity for marginal gain over inter-block CP |
| Partial Redundancy Elimination / Lazy Code Motion | Subsumes LICM and CSE but requires SSA + dominance; large implementation surface |
| Induction Variable Simplification / Elimination | Useful only after LICM exists and loops are identified |
| Loop Unrolling / Peeling / Rotation / Fusion / Fission | R316 programs are typically small; code-size increase likely outweighs speed gain |
| Escape Analysis | No heap allocator yet; revisit if `malloc` is added |
| Mem2Reg / Stack Allocation Promotion | IR already uses `Temp` for SSA-like values; `Var` slots are the "memory" layer. Full Mem2Reg would require a proper dominator tree and phi-node insertion |
| Function Cloning / Partial Inlining | Useful for specializing hot paths; deferred until profiling infrastructure exists |
| Code Layout Optimization / Basic Block Reordering | Benefits only appear with branch prediction hardware; R316 has none |

---

### Codegen / ASM peephole (existing + planned)
| Item | Size | Value | Notes |
|---|---|---|---|
| More peephole patterns | S | ★★ | `mov rX, rX` → delete. `add rX, 0` → delete. `mov rX, 0` after a jc/jz that already cleared via `r0` → use `r0`. Adjacent `st`/`ld` of same slot beyond current pattern. `sub r0, a, b; jl L` → `cmp+jl`. |
| Use `r0=zero` more aggressively | S | ★ | Anywhere a literal zero is needed, prefer `r0` over `mov rX, 0`. |
| Shorter prologue/epilogue for leaf functions | M | ★★ | If a function calls nothing and uses no callee-saved regs, skip pushing/popping `lr` and frame setup. Halves the prologue cost on small helpers. |
| Coalesce contiguous spill slots | S | ★ | Reorder spills so the frame can use one `sub r30, N` and one `add r30, N` for the whole batch. |

### Register allocator (planned improvements)
| Item | Size | Value | Notes |
|---|---|---|---|
| Graph-coloring allocator | XL | ★★ | Replace linear scan. Better spill choices, especially around long-lived call-crossing values. Deferred: linear scan is adequate at current program sizes. |
| Live-range splitting | L | ★ | Split a temp's range at a call boundary so part lives in caller-saved, part in callee-saved. Reduces spill pressure. |
| Spill cost heuristic | S | ★ | Today probably FIFO. Spill the temp with the lowest use-density (uses / live-range-length). |

### R316-specific
- Memory-mapped I/O builtins (`__builtin_putchar` → direct `st rX, 0x9FB5`) — bypasses runtime call overhead in tight loops.
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
| `stdlib.h`: `abs`, `atoi`, `min/max` macros | S | ★★ | Trivial. |
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
3. **`string.h` + real `printf`** (§4). Most-asked-for runtime gap.
4. **Static locals + struct pass-by-value** (§1). Removes the two main "gotchas" users hit when porting C code.
5. **32-bit `long` arithmetic** (§1). Big project; do it after the test infrastructure is solid because it touches every layer.
6. **Pass manager refactor** (§7) — only when there's a third or fourth optimization pass and the ad-hoc invocation in `compiler.py` starts to hurt.
7. **Graph-coloring regalloc** (§2) — only if generated code is benchmarked to actually be regalloc-bound. Linear scan is usually fine for hobby compilers.

Skip indefinitely unless a concrete need appears: float/double, VLAs, LSP, fuzz testing, full graph-coloring regalloc.
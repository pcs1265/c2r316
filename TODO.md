# C→R316 Compiler TODO

## Bugs (Fixed)

- [x] Ternary operator `?:` parsing incomplete — defined twice, not actually working
- [x] Signed division `int / int` calls `__udiv` → wrong result for negative numbers
- [x] Global array initializer `= {1, 2, 3}` ignored, filled with zeros instead
- [x] `__umod` uses hardcoded address `0xFFFF` for stack storage (wrong pattern)
- [x] `int >> n` uses logical shift (zero-fill) → wrong result for negative numbers
  - R316 `shr` is always a logical shift (confirmed in manual)
  - Fixed to arithmetic right shift (inline mask fill)

---

## Unsupported C Features

### Syntax / Statements
- [x] `do { } while (cond)` loop
- [x] `switch` / `case` / `default`
- [x] `goto` / labels

### Types
- [ ] `struct` / `union` (field type and offset tracking)
- [ ] `long` 32-bit arithmetic (2-word operations, upper 16-bit carry handling)
- [x] `enum` (top-level and local; constants folded to `IntLit` at parse time)
- [ ] `float` / `double` (software floating point)

### Other Language Features
- [x] Preprocessor (`#include "file"`, `#define`, `#ifdef`/`#ifndef`/`#if`/`#else`/`#elif`/`#endif`, `#undef`)
- [x] Compound literal initialization (local array `int a[] = {1, 2, 3}`)
- [ ] Function pointer type checking (currently passes without type info)
- [x] `typedef` support (scalar/pointer aliases registered; struct typedef treated as `int`)

---

## Code Quality / Stability

- [ ] **Register spill** — crashes with exception when temporary registers r5–r13 (9 total) are exhausted
  - Need logic to spill to stack and restore when overflow occurs
- [ ] **`_gen_ternary` register management** — `restore(checkpoint - 1)` approach relies on implicit assumptions
  - No explicit guarantee that then/else branches use the same result register
- [ ] **Missing pointer scaling in compound assignment `+=` etc.**
  - `ptr += 1` increments by 1 instead of element size (currently works by coincidence for int-only)

---

## Performance Optimizations

- [ ] **Constant folding** — avoid computing compile-time constants like `1 + 2` at runtime
- [ ] **Eliminate unnecessary `mov`** — generates `mov r1, r1` when argument is already in r1
- [ ] **Remove unconditional parameter spill** — use register as-is when there is no risk of overwriting
- [ ] **Improve leaf function detection** — currently only checks for function calls; should precisely determine whether LR actually needs to be preserved

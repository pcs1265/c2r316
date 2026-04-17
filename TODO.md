# C→R316 Compiler TODO

## Bugs (Fixed)

- [x] Ternary operator `?:` parsing incomplete — defined twice, not actually working
- [x] Signed division `int / int` calls `__udiv` → wrong result for negative numbers
- [x] Global array initializer `= {1, 2, 3}` ignored, filled with zeros instead
- [x] `__umod` uses hardcoded address `0xFFFF` for stack storage (wrong pattern)
- [x] `int >> n` uses logical shift (zero-fill) → wrong result for negative numbers
  - R316 `shr` is always a logical shift (confirmed in manual)
  - Fixed to arithmetic right shift (inline mask fill)
- [x] Caller-saved registers (r5–r13) not preserved across user function calls
  - `n * factorial(n-1)` type expressions computed wrong results (r5 clobbered by callee)
  - Fixed: `_gen_call` now saves/restores all live outer caller-saved regs around each call
- [x] `int / int` and `int % int` in `_gen_binop` allocated an extra temp register for the result,
  leaking left_r and right_r; subsequent nested divisions/modulos reused the wrong register
  - Fixed: result is written back into left_r (dst); no extra alloc needed
- [x] `x /= n` always used `__udiv` even for signed `int` types
  - Fixed: compound `/=` now selects `__sdiv` vs `__udiv` based on operand type
- [x] `_gen_compare` double-freed `right_r` — both `_gen_compare` and `_gen_binop` called `free()` on it
  - Expressions like `(a < b) + 1` or `(x == 0) * y` corrupted the register allocator state
  - Fixed: removed the redundant `free()` from `_gen_compare`; `_gen_binop` owns the cleanup
- [x] `%=`, `<<=`, `>>=` compound assignments silently no-op'd (operators missing in lexer/parser/codegen)
  - Fixed: added `%=` (two-char) and `<<=`/`>>=` (three-char) token types; wired through parser and codegen
  - Signed `>>=` uses the same inline arithmetic-right-shift pattern as binary `>>`
- [x] Functions using `/` or `%` (but no C-level calls) wrongly classified as leaf functions
  - `jmp r31, __udiv/__sdiv/__umod/__smod` overwrites LR, but leaf functions skip the prologue LR save
  - Fixed: `_has_call` now returns `True` for `BinOp` `/`/`%` and `Assign` `/=`/`%=`
- [x] `va_arg` register allocation inconsistency — result register was at a position above `_used`
  - In complex call contexts this could cause the result to be clobbered by subsequent allocations
  - Fixed: result is now moved into the first free register slot before freeing temporaries

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

- [x] **Register spill** — extended TMP_REGS to 13 (r5–r17); callee-saved regs (r14–r17) saved/restored
  via two-pass function code generation; caller-saved regs (r5–r13) saved/restored around every
  user function call so that live values survive recursive and nested calls.
- [x] **`_gen_ternary` register management** — rewritten with explicit `cp` checkpoint; both branches
  always produce their result in `TMP_REGS[cp]` and the allocator is cleanly restored to `cp+1`.
- [x] **Missing pointer scaling in compound assignment `+=` etc.**
  - `ptr += n` / `ptr -= n` now multiplies `n` by `sizeof(*ptr)` before the add/sub.
  - `++p` / `p++` / `--p` / `p--` use `_ptr_step()` to determine the correct step size.

---

## Performance Optimizations

- [ ] **Constant folding** — avoid computing compile-time constants like `1 + 2` at runtime
- [ ] **Eliminate unnecessary `mov`** — generates `mov r1, r1` when argument is already in r1
- [ ] **Remove unconditional parameter spill** — use register as-is when there is no risk of overwriting
- [x] **Improve leaf function detection** — `_has_call` now also flags `BinOp` `/`/`%` and `Assign` `/=`/`%=` as non-leaf since these emit `jmp r31, __udiv/...`

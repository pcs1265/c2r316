# TODO

## ABI Migration (→ `docs/ABI.md`)

The codegen/runtime has been updated to the new ABI (r1–r6 args, r7–r18 caller-saved, r19–r29 callee-saved).
The following items are still pending:

- **`compiler/codegen.py`**: Implement stack argument passing for 7th+ arguments (§2.3)
- **`compiler/codegen.py`**: Implement long (32-bit) two-register code generation (§9)
  - add+adc, sub+sbb, mul+mulh instruction pairs
  - Even-register alignment rule (§2.2.1)

Completed in commit `89524f0`:
- ~~**`compiler/codegen.py`**: Expand `ARG_REGS` from `['r1'..'r4']` → `['r1'..'r6']`~~
- ~~**`compiler/codegen.py`**: Implement callee-saved register (r19–r29) save/restore in prologue/epilogue (§5.2)~~
- ~~**`compiler/codegen.py`**: Restructure stack frame layout to match new ABI (§4)~~
- ~~**`compiler/codegen.py`**: Change `SCRATCH_A/B/C` from r5/r6/r7 to r7/r8/r9~~
- ~~**`compiler/codegen.py`**: Update `_ASM_REGS` inline asm register pool to r7–r16 (§7)~~
- ~~**`runtime/runtime.asm`**: Update ABI comments (r1–r6 args, r19–r29 callee-saved)~~
- ~~**`runtime/runtime.asm`**: Verify runtime functions are compatible with new ABI~~

## IR Optimization Passes (`compiler/opt.py`)

- **Copy propagation** — eliminate `t1 = t0; use(t1)` → `use(t0)`
- **DCE (Dead Code Elimination)** — remove temps that are defined but never used
- These two together will eliminate most of the `&var → addr → load` chains
  that currently bloat every variable access into 3-4 instructions

## Parser

- **Array initializer syntax** — `int arr[] = {1, 2, 3};` (currently parse error)
- **Ternary operator** `?:` (currently lex error)
- **Remove duplicate `_parse_ternary` definition** — delete lines 351–362 (second definition wins)
- **Remove duplicate `_parse_eq` definition** — delete lines 412–418 (second definition wins)

## Bug Fixes

- **`compiler/irgen.py`**: Change `_strings` from class variable to instance variable
  (delete line 94 class variable, add `self._strings = []` in `__init__`)
  (delete line 94 class variable, add `self._strings = []` in `__init__`)
- **`compiler/irgen.py`**: Remove unnecessary `__init_subclass__` stub (line 96)
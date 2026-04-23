# TODO

## ABI Migration (→ `docs/ABI.md`)

The codegen/runtime has been updated to the new ABI (r1–r6 args, r7–r18 caller-saved, r19–r29 callee-saved).

## IR Optimization Passes (`compiler/opt.py`)

- **Copy propagation** — eliminate `t1 = t0; use(t1)` → `use(t0)`
- **DCE (Dead Code Elimination)** — remove temps that are defined but never used
- These two together will eliminate most of the `&var → addr → load` chains
  that currently bloat every variable access into 3-4 instructions

## Parser

- **Array initializer syntax** — `int arr[] = {1, 2, 3};` (currently parse error)

## Code Generation

- **`compiler/codegen.py`**: Implement stack argument passing for 7th+ arguments (§2.3)
- **`compiler/codegen.py`**: Implement long (32-bit) two-register code generation (§9)
  - add+adc, sub+sbb, mul+mulh instruction pairs
  - Even-register alignment rule (§2.2.1)
- **`compiler/codegen.py`**: Implement callee-saved register tracking in `_used_callee_saved_regs` when register allocator is added.
# TODO

## Optimizations

Current passes: constant folding + copy propagation (`compiler/fold.py`), dead code elimination + dead function elimination (`compiler/dce.py`).

Potential improvements:

- **Copy prop: Var sources** — currently blocked because `Var` in IStore/ILoad address position means "direct slot access" not "load and dereference". Fix requires distinguishing address-position uses from value-position uses before enabling Var propagation.
- **Common subexpression elimination (CSE)** — `&arr` is recomputed on every array access; CSE would deduplicate these IAddrOf instructions within a basic block.
- **Register allocation** ✓ done — linear-scan allocator in `compiler/regalloc.py` assigns Temps to r10–r18 (caller-saved) and r19–r29 (callee-saved for call-crossing intervals); r7–r9 remain codegen scratch. Codegen emits 3-operand add/sub/mul and uses allocated regs directly in comparisons and branches. Total reduction from baseline: 855 → 617 instructions on hello.c (−28%).
- **Peephole: redundant stores** — `st r7, r30, N` immediately followed by `ld r7, r30, N` (or vice versa) can be eliminated at the assembly level.
- **Dead store elimination** — stores to locals that are never loaded again (requires liveness analysis over Vars, not just Temps).
- **Inlining** — small leaf functions (e.g. `putchar`) called in hot loops are good candidates.

## Known Issues

- Parser does not support array initializer syntax `{1, 2, 3}`
- `long` (32-bit) type has no code generation support
- Integer literals larger than 16 bits are passed through to codegen as-is; codegen does not handle multi-word constants
- `sizeof(struct T)` fails to parse — `sizeof` is not implemented in the parser
- Struct/union pass-by-value (hidden pointer ABI) not implemented; use pointers instead
- `typedef struct { ... } Name;` not supported; use tag names directly

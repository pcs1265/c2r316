# TODO

## IR Optimization Passes (`compiler/opt.py`)

- **Copy propagation** — eliminate `t1 = t0; use(t1)` → `use(t0)`
- **DCE (Dead Code Elimination)** — remove temps that are defined but never used
- These two together will eliminate most of the `&var → addr → load` chains
  that currently bloat every variable access into 3-4 instructions

## Parser

- **Array initializer syntax** — `int arr[] = {1, 2, 3};` (currently parse error)
- **Ternary operator** `?:` (currently lex error)

## Codegen / ABI

- **Stack arguments** — functions with more than 4 params currently broken
  (params beyond r1..r4 not passed via stack)

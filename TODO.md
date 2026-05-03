# TODO

## Known Issues

- **`long` shifts** — `<<` and `>>` for `long` are not implemented yet. Add constant-small-shift lowering first, then variable shifts.
- **`long` bitwise operators** — `&`, `|`, `^`, and `~` for `long` are not implemented yet. Lower independently on low/high halves.
- **`long` constant folding** — optimizer folds scalar constants only. Add fold support for `ILongBinOp`, `ILongUnaryOp`, and `ILongCompare`.
- **`long` inliner support** — scalar inliner currently skips functions containing long IR. Teach `compiler/inline.py` to clone/rename `ILong*` instructions before enabling long-function inlining.
- **`long` variadic edge cases** — `va_arg(ap, long)` and `%l` stdio formats work for supported fixed/variadic layouts; broaden tests for mixed long varargs beyond stdio.
- **`long` ABI alignment** — current implementation flattens long args as two consecutive argument words. Revisit even-register alignment/skipped argument registers if strict ABI section 2.2.1 compatibility is required.
- **Long literal suffix typing** — `L`/`UL` suffixes are accepted, but semantic typing is still broad/simple. Audit parser/semantic behavior for C-compatible literal type selection.
- **Struct/union pass-by-value** — hidden-pointer ABI is not generated; use explicit pointers for now.
- **Full GCC inline asm compatibility** — current asm supports only GCC-style sections with `=r`, `+r`, `r`, and clobbers. Missing pieces include constraint alternatives (`"rm"`, `"g"`, `"i"`, `"m"`), matching constraints (`"0"`), early-clobber (`=&r`), named operands (`%[name]`), operand modifiers (`%c0`, `%n0`, etc.), `asm volatile`, `asm goto`, true memory operands, full GCC clobber/register-allocation semantics, and `long` output operands.

## Not Implemented C Features

| Feature | Notes |
|---|---|
| `float`, `double` | No support at any level |
| Struct/union pass-by-value | Hidden pointer ABI not generated |
| `__func__` / `__FUNCTION__` | C99 implicit per-function string variable |
| Designated initializers | `{.field = val}` / `[index] = val` |
| Compound literals | `(Type){...}` |
| Full GCC inline asm compatibility | Current support is a small GCC-style subset |
| Bitfield struct members | `: N` fields |
| Variable-length arrays | Runtime-sized stack arrays |

## Long Support

- Add `long` bitwise ops: `&`, `|`, `^`, `~`.
- Add `long` shifts: constant small shifts first, then variable shifts.
- Extend stdio long formatting/parsing beyond `%ld`, `%lu`, and `%lx` if needed (`%lo`, `%lX`, width/precision edge cases).
- Teach inliner, fold, and DCE optimizations more long-specific simplifications.
- Add focused execution tests for arrays of long, struct fields of long, globals/statics, stack overflow args containing long, and function-pointer calls with long signatures.

## Refactoring

- **`compiler/utils/` package** — extract shared helpers into `compiler/utils/`:
  - `callgraph.py`: `_build_call_graph` and `_reachable_functions` are duplicated between `dce.py` and `inline.py`.
  - `errors.py`: source-location error helpers are reimplemented in lexer, parser, semantic, and irgen.
  - `types.py`: move `is_integer`, `is_pointer`, `is_scalar`, and `is_32bit` out of `ast_nodes.py`.

## Potential Optimizations

- Lower more builtins directly in IR/codegen instead of via auto-prepended C helpers where it materially reduces call overhead.
- Improve register allocation cost modeling for callee-saved registers in small functions.

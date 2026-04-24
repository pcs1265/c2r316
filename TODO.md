# TODO

## Known Issues

- Parser does not support array initializer syntax `{1, 2, 3}`
- `long` (32-bit) type has no code generation support
- Integer literals larger than 16 bits are passed through to codegen as-is; codegen does not handle multi-word constants
- `sizeof(struct T)` fails to parse — `sizeof` is not implemented in the parser
- Struct/union pass-by-value (hidden pointer ABI) not implemented; use pointers instead
- `typedef struct { ... } Name;` not supported; use tag names directly

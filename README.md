# c2r316: C to R316 Assembly Compiler

c2r316 is a robust C-to-R316 assembly cross-compiler written in Python. It compiles a subset of C into TPTASM assembly, specifically optimized for the **R316 virtual machine** (a 16-bit architecture with 32-bit registers commonly used in *The Powder Toy*).

## Compilation Pipeline

The compiler utilizes a strict six-stage transformation process to lower C source code into R316 machine instructions:

1.  **Preprocessor**: Handles `#include` and `#define`. It automatically prepends `runtime/stdlib.h` to every compilation unit to provide a standard execution environment.
2.  **Lexer**: A hand-written tokenizer that supports C standard literals, multi-character operators (e.g., `->`, `>>=`), and adjacent string literal concatenation.
3.  **Parser**: A recursive descent parser that constructs an Abstract Syntax Tree (AST), supporting standard C operator precedence and control flow.
4.  **Semantic Analyzer**: Manages symbol tables and nested scopes. It enforces C type safety, handles integer promotions, and calculates initial stack offsets for local variables.
5.  **IR Generator**: Lowers the AST into a linear **Three-Address Code** Intermediate Representation. Complex expressions (like short-circuiting `&&`/`||`) are expanded into explicit jumps and virtual temporaries.
6.  **Code Generator**: Translates IR into R316 assembly. It manages the function lifecycle (prologue/epilogue), saves the link register for non-leaf functions, and performs basic peephole optimizations to eliminate redundant load/store cycles.

## R316 Architecture & Runtime

### Hardware Specifications
- **Registers**: 32 general-purpose 32-bit registers (`r0`–`r31`).
  - `r0`: Hardware-wired to zero.
  - `r7`–`r9`: Reserved as volatile scratchpads by the compiler.
  - `r30` (sp): Stack Pointer.
  - `r31` (lr): Link Register.
- **Memory**: 16-bit word-addressed space (0x0000–0xFFFF).
- **Quasi-32-bit Constraint**: The VM cannot store four specific 32-bit values (0x0, 0x4, 0x8, 0xC in the MSB) in a single word. The compiler avoids this by managing `long` values as 16-bit pairs.

### Runtime Bootstrap (`runtime.asm`)
At boot, the runtime performs a **binary search** on the address space to detect the top of writable RAM. It then:
1.  Initializes the Stack Pointer (`r30`).
2.  Configures the terminal MMIO (geometry, colors, and newline handling).
3.  Clears the screen before jumping to `main`.

## Features & Usage

### Supported Constructs
- **Types**: `int`, `char`, `unsigned`, `void`, and pointers.
- **Flow Control**: `if/else`, `while`, `do-while`, `for`, `break`, `continue`.
- **Memory**: Array indexing, pointer arithmetic, and `sizeof`.
- **Inline Assembly**: Support for `asm()` blocks with operand substitution (`%0`–`%9`).

### Quick Start
```bash
# Compile a C program
python compiler.py examples/hello.c -o output.asm

# Compile with verbose stages and source annotations
python compiler.py examples/hello.c -o output.asm -v -g
```

### CLI Options
- `-o <file>`: Output assembly path.
- `-v, --verbose`: Print pipeline stages.
- `-g, --annotate`: Add C source lines as comments in the assembly.
- `--dump-ir`: View the Intermediate Representation before final codegen.

## Project Structure

- `compiler.py`: CLI entry point.
- `compiler/`: Frontend, Semantic analysis, and IR/Code generation logic.
- `runtime/`: `stdlib.h` (C primitives) and `runtime.asm` (Low-level bootstrap).
- `docs/ABI.md`: Full specification of calling conventions and register usage.

## License
Provided "as-is" for educational and hobbyist use in The Powder Toy community.

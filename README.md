# c2r316: C to R316 Assembly Compiler

c2r316 is a robust C-to-R316 assembly cross-compiler written in Python. It compiles a subset of C into TPTASM assembly, specifically optimized for the **R316 virtual machine** (a 16-bit architecture with 32-bit registers commonly used in *The Powder Toy*).

## Compilation Pipeline

The compiler utilizes a strict six-stage transformation process to lower C source code into R316 machine instructions:

1.  **Preprocessor**: Handles `#include` and `#define`. It automatically prepends `runtime/stdlib.h` to every compilation unit to provide a standard execution environment.
2.  **Lexer**: A hand-written tokenizer that supports C standard literals, multi-character operators (e.g., `->`, `>>=`), and adjacent string literal concatenation.
3.  **Parser**: A recursive descent parser that constructs an Abstract Syntax Tree (AST), supporting standard C operator precedence and control flow.
4.  **Semantic Analyzer**: Manages symbol tables and nested scopes. It enforces C type safety, handles integer promotions, and calculates initial stack offsets for local variables.
5.  **IR Generator**: Lowers the AST into a linear **Three-Address Code** Intermediate Representation. Complex expressions (like short-circuiting `&&`/`||`) are expanded into explicit jumps and virtual temporaries.
6.  **IR Optimizer**: A multi-pass optimizer that runs before code generation:
    - **Constant folding & copy propagation** — folds constant expressions and eliminates single-use copies (`x + 0 → x`, `t1 = 5; t2 = t1 → t2 = 5`).
    - **Dead code elimination** — removes instructions that produce unused results, and eliminates unreachable functions via call-graph reachability analysis from `main`.
7.  **Code Generator**: Translates IR into R316 assembly, with several backend optimizations:
    - **Linear-scan register allocation** — assigns IR temporaries to physical registers (r10–r18 caller-saved, r19–r29 callee-saved), reducing stack traffic by ~45% on typical programs.
    - **Compare-branch fusion** — folds `t = a < b; if t goto L` into a single `sub r0, a, b; jl L` without materializing the boolean.
    - **3-operand arithmetic** — emits `add dst, src1, src2` directly when the destination differs from the right operand, avoiding an extra move.
    - **Assembly peephole** — replaces `st Rx, r30, N; ld Ry, r30, N` pairs with `mov Ry, Rx`, turning stack reloads into register moves.

## R316 Architecture & Runtime

### Hardware Specifications
- **Registers**: 32 general-purpose 32-bit registers (`r0`–`r31`).
  - `r0`: Hardware-wired to zero.
  - `r1`–`r6`: Argument / return value registers (caller-saved).
  - `r7`–`r9`: Compiler scratch registers (never allocated to user temporaries).
  - `r10`–`r18`: Caller-saved temporaries (allocated by the register allocator).
  - `r19`–`r29`: Callee-saved registers (allocated for values that must survive calls).
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
- `-v, --verbose`: Print pipeline stages to stderr.
- `-g, --annotate`: Embed C source lines as comments in the output assembly.
- `--dump-tokens`: Dump lexer token stream to stderr.
- `--dump-ast`: Dump the parsed AST to stderr.
- `--dump-ir`: Dump the IR (after optimization) to stderr.
- `--stop-after {lex,parse,semantic,ir,codegen}`: Stop after the named stage.

## Project Structure

- `compiler.py` — CLI entry point.
- `compiler/lexer.py` — Tokenizer.
- `compiler/parser.py` — Recursive descent parser (tokens → AST).
- `compiler/semantic.py` — Type checking and symbol table.
- `compiler/irgen.py` — AST → Three-Address Code IR.
- `compiler/fold.py` — Constant folding and copy propagation pass.
- `compiler/dce.py` — Dead code and dead function elimination pass.
- `compiler/regalloc.py` — Linear-scan register allocator.
- `compiler/codegen.py` — IR → R316 assembly with backend optimizations.
- `runtime/stdlib.h` — C standard library declarations.
- `runtime/runtime.asm` — Bootstrap and runtime helpers (putchar, print_int, etc.).
- `docs/ABI.md` — Full calling convention and register usage specification.
- `docs/TODO.md` — Planned and completed optimization work.

## License
Provided "as-is" for educational and hobbyist use in The Powder Toy community.

# C → R316 Compiler

A compiler that lets you write C programs and run them on the R316 CPU inside The Powder Toy.

## Usage

```bash
python3 compiler.py input.c -o output.asm
```

Assemble the resulting `output.asm` with TPTASM and load it into the R316.

---

## File Structure

```
c2r316/
├── compiler.py    Entry point (assembles the pipeline)
├── lexer.py       Lexer
├── ast_nodes.py   AST node definitions
├── parser.py      Parser
├── semantic.py    Semantic analyzer
├── codegen.py     Code generator
└── runtime.asm    C runtime library (R316 assembly)
```

---

## Compilation Pipeline

```
C source (.c)
    │
    ▼
[Stage 1: Lexer]
    │  Character stream → Token stream
    │  e.g. "int x = 42;" →
    │       [INT] [IDENT "x"] [ASSIGN] [INT_LIT 42] [SEMICOLON]
    │
    ▼
[Stage 2: Parser]
    │  Token stream → Abstract Syntax Tree (AST)
    │  e.g. VarDecl(name="x", type=CInt, init=IntLit(42))
    │
    ▼
[Stage 3: Semantic Analyzer]
    │  · Build symbol table (tracks variable and function declarations)
    │  · Type inference and type checking
    │  · Calculate stack offsets for local variables
    │
    ▼
[Stage 4: Code Generator]
    │  AST → R316 assembly (TPTASM syntax)
    │  · Emit function prologues and epilogues
    │  · Allocate temporary registers
    │  · Lower control flow (if/while/for) to branch instructions
    │
    ▼
[Stage 5: Runtime Linking]
    │  Append runtime.asm to the generated assembly
    │  Provides putchar, print_int, strlen, etc.
    │
    ▼
R316 assembly (.asm)
    │
    ▼  (TPTASM)
R316 memory image → runs in The Powder Toy
```

---

## ABI

The calling convention used by all generated code.

| Register | Role |
|----------|------|
| `r1`–`r4` | Function arguments / return value (`r1` = return value) |
| `r5`–`r13` | Caller-saved temporaries (not preserved across calls) |
| `r14`–`r29` | Callee-saved (function must preserve these) |
| `r30` (`sp`) | Stack pointer (grows downward) |
| `r31` (`lr`) | Link register (return address) |

### Stack Frame Layout

```
sp before call  → ┌──────────────┐
                  │  ...         │  caller's area
                  ├──────────────┤
after prologue    │  saved lr    │  ← sp + local_size  (non-leaf only)
                  ├──────────────┤
                  │  local var 0 │  ← sp + 0
                  │  local var 1 │  ← sp + 1
                  │  ...         │
                  └──────────────┘  ← sp  (during execution)
```

### Function Call Example

```c
int add(int a, int b) {
    return a + b;
}
```

```asm
add:
    ; a = r1, b = r2  (argument registers)
    add r1, r2         ; r1 = a + b
    jmp r31            ; return (jump to lr)
```

---

## Supported C Features

### Types

| C type | Size | Notes |
|--------|------|-------|
| `int` | 16-bit (1 word) | Default integer |
| `unsigned int` | 16-bit | Unsigned |
| `char` | stored as 16-bit | 8-bit value |
| `long` | 32-bit (2 words) | Partial support |
| `T*` | 16-bit pointer | Address |
| `T[N]` | N words | Static array |

### Operators

| Category | Operators |
|----------|-----------|
| Arithmetic | `+` `-` `*` `/` `%` |
| Bitwise | `&` `\|` `^` `~` `<<` `>>` |
| Logical | `&&` `\|\|` `!` |
| Comparison | `==` `!=` `<` `>` `<=` `>=` |
| Assignment | `=` `+=` `-=` `*=` `/=` `&=` `\|=` `^=` |
| Increment | `++` `--` (prefix and postfix) |
| Pointer | `&` (address-of) `*` (dereference) |

### Control Flow

```c
if (cond) { ... } else { ... }
while (cond) { ... }
for (init; cond; step) { ... }
break;
continue;
return expr;
```

### Functions

- Up to 4 arguments (passed in `r1`–`r4`)
- Recursion supported
- Forward declarations required for external/runtime functions

---

## Runtime Library

All functions in `runtime.asm` are implemented directly in R316 assembly.

### Output

```c
void putchar(int c);        // Print a single character
void puts(char *s);         // Print a string followed by newline
void print_str(char *s);    // Print a string (no newline)
void print_int(int n);      // Print a signed integer
void print_uint(int n);     // Print an unsigned integer
void print_hex(int n);      // Print a 4-digit hex value
```

### Input

```c
int getchar(void);          // Wait for a key press and return it
```

### String / Memory

```c
int  strlen(char *s);
int  strcmp(char *a, char *b);       // 0 = equal
void memcpy(char *dst, char *src, int n);
void memset(char *dst, int val, int n);
```

---

## Code Generation Details

### Integer literal

```c
int x = 42;
```
```asm
mov r5, 42
st  r5, r30, 0    ; store into x's slot on the stack
```

### if/else → conditional branch

```c
if (a > 5) { foo(); } else { bar(); }
```
```asm
    sub r0, r5, r6       ; a - 5 (flags only, result discarded)
    jle ._c2r_else_1     ; a <= 5 → go to else
    jmp r31, foo
    jmp ._c2r_endif_2
._c2r_else_1:
    jmp r31, bar
._c2r_endif_2:
```

### for loop

```c
for (i = 0; i < 10; i++) { ... }
```
```asm
    mov r5, 0
    st  r5, r30, 0           ; i = 0
._c2r_fcond_1:
    ld  r5, r30, 0           ; load i
    mov r6, 10
    sub r0, r5, r6           ; i - 10
    jnl ._c2r_fend_3         ; i >= 10 → exit
    ...                      ; loop body
._c2r_fstep_2:
    ...                      ; i++
    jmp ._c2r_fcond_1
._c2r_fend_3:
```

### Function call

```c
result = add(3, 4);
```
```asm
    mov r1, 3
    mov r2, 4
    jmp r31, add        ; call (saves return address in r31)
    mov r5, r1          ; move return value out of r1
```

---

## Known Limitations

- Maximum 4 function arguments (`r1`–`r4`)
- No `struct` support
- No `float` / `double` (software FP from quadratic.asm planned)
- No `printf` (planned)
- Division (`/`, `%`) uses repeated subtraction — slow for large values
- Arguments beyond the 4th are not yet passed via the stack
- No preprocessor (`#define`, `#include`)

---

## Example

```c
void puts(char *s);
void print_int(int n);
void putchar(int c);

int factorial(int n) {
    if (n <= 1) return 1;
    return n * factorial(n - 1);
}

int main(void) {
    puts("Hello, R316!");
    int i;
    for (i = 1; i <= 7; i++) {
        print_int(factorial(i));
        putchar('\n');
    }
    return 0;
}
```

```bash
python3 compiler.py hello.c -o hello.asm
# Assemble with TPTASM, then load into The Powder Toy R316
```

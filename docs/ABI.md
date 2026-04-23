# R316 C Compiler ABI (Application Binary Interface)

This document specifies the calling convention, register usage, and stack frame
layout for the C→R316 compiler (c2r316).  All compiled C code and hand-written
assembly that interoperates with it MUST follow these rules.

---

## 1. Register Classification

| Register | Name  | Class          | Notes                                    |
|----------|-------|----------------|------------------------------------------|
| r0       | zero  | —              | Read-only; always reads as 0 (ALU view)  |
| r1       | a0    | arg / return   | 1st argument / return value (low half)   |
| r2       | a1    | arg / return   | 2nd argument / long return high half     |
| r3       | a2    | arg            | 3rd argument                             |
| r4       | a3    | arg            | 4th argument                             |
| r5       | a4    | arg            | 5th argument                             |
| r6       | a5    | arg            | 6th argument                             |
| r7       | t0    | caller-saved   | Temporary / scratch                      |
| r8       | t1    | caller-saved   | Temporary / scratch                      |
| r9       | t2    | caller-saved   | Temporary / scratch                      |
| r10      | t3    | caller-saved   | Temporary / scratch                      |
| r11      | t4    | caller-saved   | Temporary / scratch                      |
| r12      | t5    | caller-saved   | Temporary / scratch                      |
| r13      | t6    | caller-saved   | Temporary / scratch                      |
| r14      | t7    | caller-saved   | Temporary / scratch                      |
| r15      | t8    | caller-saved   | Temporary / scratch                      |
| r16      | t9    | caller-saved   | Temporary / scratch                      |
| r17      | t10   | caller-saved   | Temporary / scratch                      |
| r18      | t11   | caller-saved   | Temporary / scratch                      |
| r19      | s0/fp | callee-saved   | Frame pointer (optional; general-purpose)|
| r20      | s1    | callee-saved   |                                          |
| r21      | s2    | callee-saved   |                                          |
| r22      | s3    | callee-saved   |                                          |
| r23      | s4    | callee-saved   |                                          |
| r24      | s5    | callee-saved   |                                          |
| r25      | s6    | callee-saved   |                                          |
| r26      | s7    | callee-saved   |                                          |
| r27      | s8    | callee-saved   |                                          |
| r28      | s9    | callee-saved   |                                          |
| r29      | s10   | callee-saved   |                                          |
| r30      | sp    | —              | Stack pointer (software-managed)         |
| r31      | lr    | —              | Link register (return address)           |

### Register Classes

- **Caller-saved (volatile)**: The caller must save these registers if their
  values are needed across a function call.  The callee may freely clobber
  them.

- **Callee-saved (non-volatile)**: The callee MUST preserve these registers.
  If a function uses any of r19–r29, it MUST save them on entry and restore
  them before returning.  A function that does not use a callee-saved register
  need not save it.

- **Argument / return (a0–a5)**: These are caller-saved registers with a
  dedicated role in the calling convention (see §2 and §3).

---

## 2. Argument Passing

### 2.1 General Rules

Arguments are passed left-to-right in registers a0–a5 (r1–r6).  If a function
has more than 6 register-sized arguments (or fewer due to long arguments
consuming two registers — see §2.2), the remaining arguments are passed on the
stack (see §2.3).

### 2.2 Type-Specific Rules

| C Type              | Register Usage                                          |
|---------------------|---------------------------------------------------------|
| `int` (16-bit)      | 1 register (lower 16 bits; upper 16 bits unspecified)  |
| `unsigned int`      | 1 register (lower 16 bits; upper 16 bits unspecified)  |
| `char`              | 1 register (lower 8 bits; rest unspecified)             |
| `long` (32-bit)     | **2 consecutive registers** (even=low half, odd=high half) |
| `unsigned long`     | **2 consecutive registers** (even=low half, odd=high half) |
| pointer             | 1 register (16-bit address; upper 16 bits unspecified)  |
| `struct` / `union`  | By value: hidden pointer (see §2.4); by pointer: 1 register |

Because the R316 ALU operates on 16-bit halves, `long` (32-bit) values are
passed in **two consecutive registers**: the even-numbered register holds the
low 16 bits and the immediately following odd-numbered register holds the high
16 bits.  This allows 32-bit arithmetic to use `add`+`adc` / `sub`+`sbb`
instruction pairs directly, without the overhead of `exh`-based half-swapping
that a single-register approach would require.

#### 2.2.1 Long Argument Register Allocation

A `long` argument consumes two consecutive registers from the argument register
pool.  The first register must be even-numbered (a0, a2, or a4).  If the next
available register is odd-numbered, it is skipped (left unused) and the long
value is placed starting at the following even register.

**Examples:**

| Signature                               | Register Allocation                          |
|-----------------------------------------|----------------------------------------------|
| `f(int a, int b, int c)`               | a→a0, b→a1, c→a2                            |
| `f(long a, int b)`                     | a→a0(lo)+a1(hi), b→a2                       |
| `f(int a, long b)`                     | a→a0, **a1 skipped**, b→a2(lo)+a3(hi)       |
| `f(long a, long b)`                    | a→a0(lo)+a1(hi), b→a2(lo)+a3(hi)            |
| `f(int a, int b, long c)`              | a→a0, b→a1, c→a2(lo)+a3(hi)                 |
| `f(int a, int b, int c, long d)`       | a→a0, b→a1, c→a2, d→a3(lo)+a4(hi)           |
| `f(int a, int b, int c, int d, long e)`| a→a0, b→a1, c→a2, d→a3, **a4 skipped**, e→stack |

If a long argument cannot fit in the remaining argument registers (i.e., the
required even-odd pair is not fully available), the entire long value is passed
on the stack (see §2.3), and the remaining unused argument registers are
similarly skipped.

### 2.3 Stack Arguments (overflow)

Arguments that cannot fit in the argument registers are passed on the stack,
pushed right-to-left by the **caller**.  They are located at fixed offsets
relative to the callee's stack pointer after the prologue completes:

```
stack_arg_offset = frame_size + callee_save_n + (1 if non-leaf) + (arg_slot_index - reg_arg_count)
```

where:

- `frame_size` = callee's total local/spill slot count
- `callee_save_n` = number of callee-saved registers the callee actually saves
- `(1 if non-leaf)` = 1 if the callee saves the link register, 0 otherwise
- `arg_slot_index` = 0-based slot index of the overflow argument
  (each 16-bit value occupies 1 slot; each `long` occupies 2 consecutive slots)
- `reg_arg_count` = number of register argument slots consumed
  (6 maximum, but may be less if some are skipped due to long alignment)

**Note:** The exact offset is computed at code-generation time when all frame
dimensions are known.  The formula above is a specification for the compiler
implementor, not a runtime computation.

### 2.4 Struct / Union Passing

- **By value**: Structs and unions that do not fit in a single register are
  passed by hidden pointer.  The caller allocates space on its stack and passes
  the address as an additional first argument (shifts all explicit arguments by
  one position).  The hidden pointer occupies a0 (r1).

- **By pointer**: Structs and unions passed by pointer use one register, as
  with any pointer type.

---

## 3. Return Values

| C Type              | Return Convention                                       |
|---------------------|---------------------------------------------------------|
| `void`              | No value returned                                       |
| `int` / `char`      | r1 (a0), lower 16 bits; upper 16 bits unspecified      |
| `unsigned int`      | r1 (a0), lower 16 bits; upper 16 bits unspecified      |
| `long` (32-bit)     | r1 (a0) = low 16 bits, r2 (a1) = high 16 bits          |
| `unsigned long`     | r1 (a0) = low 16 bits, r2 (a1) = high 16 bits          |
| pointer             | r1 (a0), 16-bit address; upper 16 bits unspecified     |
| `struct` / `union`  | Returned via hidden pointer (see §3.1)                 |

### 3.1 Struct / Union Return

For struct/union return types that do not fit in a register, the caller
allocates space on its stack and passes a hidden first argument (in a0/r1)
pointing to this space.  All explicit arguments are shifted by one position
(i.e., the first explicit argument goes in a1/r2, etc.).  The callee writes
the return value to the hidden pointer and returns the same pointer in r1.

**Interaction with long arguments:** When a function has both a struct return
(hidden pointer in a0) and a `long` first explicit argument, the hidden
pointer occupies a0(r1), and the `long` argument starts at a2(r3) — skipping
a1(r2) to satisfy the even-register alignment rule for long values.

---

## 4. Stack Frame Layout

The stack grows **downward** (toward lower addresses).  r30 (sp) points to the
lowest address of the current frame.

```
High address
  ┌─────────────────────────────────┐
  │ Stack arguments (overflow)      │  ← caller's responsibility
  ├─────────────────────────────────┤
  │ Saved link register (r31)       │  [sp + F + CS]   (non-leaf only)
  ├─────────────────────────────────┤
  │ Saved callee-saved registers    │  [sp + F .. sp + F + CS - 1]
  │ (r19..r29, only those used)     │
  ├─────────────────────────────────┤
  │ Local variables / spill slots   │  [sp + 0 .. sp + F - 1]
  │ (32-bit words)                  │
  └─────────────────────────────────┘
Low address
                                        r30 (sp) points here

Where:
  F  = frame_size   (local/spill slots)
  CS = callee_save_n (saved callee registers)
```

### 4.1 Frame Components

| Component            | Size                       | Notes                          |
|----------------------|----------------------------|--------------------------------|
| Local / spill slots  | `F` words                  | Fixed at compile time          |
| Callee-saved saves   | `CS` words                 | Only registers actually used   |
| Link register save   | 1 word (non-leaf only)     | Only if function makes calls   |

Total stack allocation: `F + CS + (1 if non-leaf else 0)` words.

### 4.2 Frame Pointer (Optional)

r19 (s0) MAY be used as a frame pointer (fp).  When enabled, fp is set to
`sp + F` (the boundary between local slots and callee-saved saves).  This is
useful for:

- Variable-length arrays (VLA) / `alloca`
- Variadic functions (`va_arg`)
- Debug backtraces

When fp is not used, all local variable access is done via sp-relative
addressing.

### 4.3 Stack Argument Access

After the callee's prologue, stack arguments passed by the caller are located
above the saved link register:

```
7th argument:  [sp + F + CS + 1]      (non-leaf)
               [sp + F + CS]          (leaf)
8th argument:  [sp + F + CS + 2]      (non-leaf)
               [sp + F + CS + 1]      (leaf)
...etc.
```

### 4.4 Stack Argument Layout from Caller's Perspective

Before the call, the caller must arrange stack arguments so that after the
callee's prologue executes, the arguments land at the offsets described in
§4.3.  This means the caller must know (or the compiler must compute) the
callee's frame layout at the call site.

**Practical implementation:** The compiler emits stack argument stores at
compile-time-computed offsets from the caller's current sp.  These offsets
account for the callee's known frame size.

---

## 5. Function Call Sequence

### 5.1 Caller Responsibilities

1. **Save caller-saved registers** that must survive the call (r1–r18).
2. **Place arguments** in a0–a5 (r1–r6) following the rules in §2.2.
   Stack arguments are written to the appropriate stack slots (§4.3–4.4).
3. **Execute** `jmp r31, <target>`  (saves return address in r31, transfers
   control to target).
4. **Read return value** from r1 (a0), and r2 (a1) for long returns.
5. **Restore caller-saved registers** saved in step 1.

### 5.2 Callee Responsibilities

**Prologue:**

1. Allocate stack frame: `sub r30, F + CS + (1 if non-leaf)`
2. Save link register (non-leaf only): `st r31, r30, F + CS`
3. Save callee-saved registers used by this function:
   `st r19, r30, F + 0`, `st r20, r30, F + 1`, … (only those used)
4. Copy register arguments (a0–a5) to their spill slots if needed.

**Epilogue:**

1. Place return value in r1 (a0), and r2 (a1) for long returns.
2. Restore callee-saved registers: `ld r19, r30, F + 0`, …
3. Restore link register (non-leaf only): `ld r31, r30, F + CS`
4. Deallocate stack frame: `add r30, F + CS + (1 if non-leaf)`
5. Return: `jmp r31`

---

## 6. Flags

The ALU flags (Zf, Sf, Cf, Of) are **caller-saved**.  A function call may
clobber any or all flags.  Code that depends on flags across a call MUST save
them explicitly (e.g., store to a register or stack slot using conditional-set
patterns).

Comparison and conditional branch sequences must be emitted as adjacent
instruction groups (e.g., `sub r0, ... ; jz label`) to avoid flag clobbering.

---

## 7. Inline Assembly

The inline assembly syntax `asm("template" : "r"(e0), "r"(e1), ...)` maps input
operands to physical registers.  The compiler loads each input expression into
a register before emitting the template, and substitutes `%0`, `%1`, … in the
template with the corresponding register names.

Available register pool for inline asm inputs (in order):

```
%0 → r7  (t0)      %5 → r12 (t5)
%1 → r8  (t1)      %6 → r13 (t6)
%2 → r9  (t2)      %7 → r14 (t7)
%3 → r10 (t3)      %8 → r15 (t8)
%4 → r11 (t4)      %9 → r16 (t9)
```

Maximum 10 input operands per inline asm statement.

Inline asm MUST NOT modify callee-saved registers (r19–r29), sp (r30), or lr
(r31) unless it saves and restores them.  Caller-saved registers (r1–r18) may
be freely modified, but note that modifying r1–r6 will clobber any active
argument/return values.

---

## 8. Memory Model

### 8.1 Addressing

- **Address space**: 16-bit (0x0000–0xFFFF), word-addressed.
- **Word size**: 32 bits per address (quasi-32-bit).
- **Stack alignment**: No alignment requirement beyond single-word boundaries
  for 16-bit and 32-bit values.

### 8.2 Quasi-32-bit Caveats

The four values `0x00000000`, `0x40000000`, `0x80000000`, and `0xC0000000`
are *physically zero* and cannot be reliably stored in memory.  Writing them
results in a value with the `0x20000000` bit set; reading them yields
`0x0000001F`.  The compiler and runtime MUST avoid storing these values.
Notably, a zero 32-bit value (`long 0`) stored as two 16-bit halves
(low=0x0000, high=0x0000) avoids this issue because each half is stored in a
separate register/memory word and is never written as a combined 32-bit zero.

### 8.3 Global Variables

Global variables are placed in the data section after all functions.  Each
global occupies one 32-bit word (initialized to 0).  Access:

```asm
ld  r5, varname       ; load global variable
st  r5, varname       ; store global variable
mov r5, varname       ; load address of global variable
```

### 8.4 String Literals

String literals are stored in the data section as null-terminated arrays of
8-bit character codes, one character per 32-bit word (upper 24 bits zero).
The address of a string literal is obtained via `mov r, label`.

---

## 9. long (32-bit) Arithmetic Convention

Since the ALU operates on 16-bit halves, `long` values are stored in **two
consecutive registers** or **two consecutive stack slots**:

- **Low half** (even register/slot): bits 0–15
- **High half** (odd register/slot): bits 16–31

This layout enables efficient 32-bit arithmetic using instruction pairs:

| Operation   | Implementation                                              |
|-------------|-------------------------------------------------------------|
| long add    | `add r_lo, r_lo, src_lo` + `adc r_hi, r_hi, src_hi`       |
| long sub    | `sub r_lo, r_lo, src_lo` + `sbb r_hi, r_hi, src_hi`       |
| long mul    | `mul r_lo, a, b` + `mulh r_hi, a, b`                      |
| long neg    | `sub r_lo, r0, r_lo` (sets carry if r_lo≠0) + `sbb r_hi, r0, r_hi` |
| long shift  | See §9.1                                                    |
| long compare| `sub r0, r_lo, src_lo` + `sbb r0, r_hi, src_hi` → flags    |

For stack storage, a `long` occupies two consecutive 32-bit words (one word
per 16-bit half).  This wastes the upper 16 bits of each word but ensures
each half is independently addressable by the ALU without `exh`.

### 9.1 Long Shift Operations

```
Left shift by 1:
  shl r_lo, 1          ; low half shifted, bit 15 lost
  shl r_hi, 1          ; high half shifted
  adc r_hi, r0, r0     ; carry from low → high bit 0

Right shift by 1:
  shr r_hi, 1          ; high half shifted, bit 0 lost
  shr r_lo, 1          ; low half shifted
  ; bit 0 of r_hi → bit 15 of r_lo (requires exh or branch)
  ; Simplified: use exh to swap, shift, exh back for large shifts
```

For shifts by N > 1, a loop or repeated shift-by-1 is used.  Alternatively,
for small constants, inline the shift-by-1 pattern N times.

---

## 10. Variadic Functions

Variadic functions (e.g., `printf`) receive their fixed arguments in a0–a5 as
usual.  The variadic arguments are accessed via `va_list`, which is implemented
as a pointer to the stack area containing the variadic arguments.

The compiler MUST emit a prologue that spills all argument registers (a0–a5)
to the stack at the start of a variadic function, so that `va_start` can
compute the address of the first variadic argument and `va_arg` can walk
through the spill area before falling through to the stack argument area.

**Long arguments in variadic functions:** Since the compiler cannot know at
compile time which variadic arguments are `long`, `va_arg` must handle the
even-register alignment rule at runtime.  To simplify, variadic functions
should spill argument registers to aligned pairs of stack slots, preserving
the even-odd layout.

---

## 11. Design Rationale

| Decision | Rationale |
|----------|-----------|
| 6 argument registers | R316 has 32 general-purpose registers.  6 argument registers cover the vast majority of C function calls without stack overhead, while leaving ample registers for temporaries and callee-saved values. |
| No dedicated gp/tp | R316 has a 16-bit address space; global variables are directly accessible via `ld`/`mov` with absolute labels.  No global pointer optimization is needed. |
| 11 callee-saved registers | Consistent with RISC-V's 12 callee-saved registers on a 32-register machine.  Provides ample register preservation across calls, reducing caller-side save/restore overhead. |
| 12 caller-saved temporaries | Large pool for register allocation and inline assembly.  Eliminates the need for frequent spill/reload cycles. |
| Optional frame pointer | Most functions have fixed-size frames and can address all locals via sp.  FP is reserved for VLA, variadic, and debug scenarios. |
| Flags are caller-saved | R316 has no dedicated flags register; flags are a side-effect of ALU operations.  Preserving them across calls would require explicit save/restore in every prologue/epilogue, which is wasteful. |
| long in 2 registers | The R316 ALU operates on 16-bit halves.  Using two registers for `long` allows `add`+`adc` / `sub`+`sbb` pairs directly, which is far more efficient than the single-register approach that would require `exh`-based half-swapping for every 32-bit operation.  The two-register approach is used by ARM (which also has a 32-bit ALU and uses register pairs for 64-bit values), and is standard practice for sub-word ALU architectures. |
| Long even-register alignment | Requiring long values to start at even-numbered registers simplifies the `add`+`adc` / `sub`+`sbb` patterns, which always operate on consecutive register pairs.  Skipping an odd register to align is a small cost that eliminates complex half-swapping logic. |

---

## 12. Potential Pitfalls and Edge Cases

This section documents known edge cases that compiler implementors and
assembly programmers should be aware of.

### 12.1 Physically Zero Values

The four *physically zero* values (`0x00000000`, `0x40000000`, `0x80000000`,
`0xC0000000`) cannot be reliably stored in or read from memory.  Since `long`
values are stored as two separate 16-bit halves (each in its own 32-bit word),
the combined 32-bit value `0x00000000` is never written as a single word and
thus avoids this issue.  However, code that uses `exh` to manipulate the upper
16 bits of a register containing a small `int` value must be careful not to
create a *physically zero* value in the full 32-bit register.

### 12.2 Long Alignment Skipping

When a `long` argument follows one or more `int` arguments, the even-register
alignment rule may cause an argument register to be skipped.  The caller MUST
NOT place any argument in the skipped register.  The skipped register's value
is unspecified on entry to the callee.

Example: `f(int a, long b)` — a→a0(r1), a1(r2) is **skipped**, b→a2(r3, lo)
+ a3(r4, hi).  The caller must not put any value in r2.

### 12.3 Stack Argument Offset Dependency

The offset of stack arguments depends on the callee's `frame_size` and
`callee_save_n`.  This means the caller must know the callee's frame layout
at compile time.  For direct calls to known functions, this is trivial.  For
indirect calls (function pointers), the compiler must either:

- Use a fixed frame header size for all functions, or
- Restrict function pointer calls to functions with ≤6 arguments (no stack
  arguments), or
- Use a caller-allocated argument block with a standard calling convention.

The current compiler only supports direct calls, so this is not an immediate
concern.

### 12.4 Callee-saved Register Overhead

Functions that use many callee-saved registers will have longer prologues and
epilogues.  The compiler should prefer caller-saved temporaries (r7–r18) for
short-lived values and reserve callee-saved registers (r19–r29) for values
that must survive function calls.  The register allocator should consider the
save/restore cost when assigning callee-saved registers.

### 12.5 Inline asm and Argument Registers

Inline asm may modify r1–r6 (argument registers).  If inline asm appears in
a function before all argument values have been consumed (spilled or used),
the compiler MUST spill the affected arguments before the asm statement.
Similarly, if inline asm modifies r1, it will clobber any pending return
value from a prior call.

---

## Appendix A: Quick Reference Card

```
r0        zero       read-only
r1   a0   arg/ret    1st arg / return value (long: low half)
r2   a1   arg/ret    2nd arg / long return high half
r3   a2   arg        3rd arg
r4   a3   arg        4th arg
r5   a4   arg        5th arg
r6   a5   arg        6th arg
r7   t0   caller
r8   t1   caller
r9   t2   caller
r10  t3   caller
r11  t4   caller
r12  t5   caller
r13  t6   caller
r14  t7   caller
r15  t8   caller
r16  t9   caller
r17  t10  caller
r18  t11  caller
r19  s0/fp callee    frame pointer (optional)
r20  s1   callee
r21  s2   callee
r22  s3   callee
r23  s4   callee
r24  s5   callee
r25  s6   callee
r26  s7   callee
r27  s8   callee
r28  s9   callee
r29  s10  callee
r30  sp   —          stack pointer
r31  lr   —          link register
```

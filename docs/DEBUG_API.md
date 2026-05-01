# R316 Emulator Debugging API

This document describes the programmatic debugging API for the R316 emulator (`tests/r316_emu.py`). The API is designed to be used by AI agents and developers for debugging, testing, and analyzing R316 programs.

For CLI usage, see [DEBUG_CLI.md](DEBUG_CLI.md).

## Table of Contents

1. [Quick Start](#quick-start)
2. [State Inspection](#state-inspection)
3. [Execution Control](#execution-control)
4. [Breakpoints](#breakpoints)
5. [Execution Tracing](#execution-tracing)
6. [State Save/Restore](#state-saverestore)
7. [Complete API Reference](#complete-api-reference)
8. [Examples](#examples)
9. [Debugging C Source Files](#debugging-c-source-files)

---

## Quick Start

```python
from tests.r316_emu import parse_asm, Machine

# Load program
asm = '''
_C_main:
    mov r1, 10
    mov r2, 20
    add r3, r1, r2
    hlt
'''
prog = parse_asm(asm)
m = Machine(prog)
m.pc = prog.labels['_C_main']

# Step through execution
m.step(2)  # Execute 2 instructions
print(m.get_registers())  # {'r0': 0, 'r1': 10, 'r2': 20, ...}

# Run to completion
m.run()
print(f"r3 = {m.get_registers()['r3']}")  # r3 = 30
```

---

## State Inspection

### `get_registers() -> dict[str, int]`

Returns all 32 registers as a dictionary.

```python
regs = m.get_registers()
# {'r0': 0, 'r1': 10, 'r2': 20, ..., 'r30': 32768, 'r31': 57005}
print(f"r1 = {regs['r1']}")
```

**Note:** `r0` is always 0 (hardwired to zero). `r30` is the stack pointer (sp). `r31` is the link register (lr).

### `get_flags() -> dict[str, int]`

Returns the four CPU flags as a dictionary.

```python
flags = m.get_flags()
# {'Z': 0, 'S': 0, 'C': 0, 'O': 0}
```

| Flag | Name | Description |
|------|------|-------------|
| Z | Zero | Set when result is 0 |
| S | Sign | Set when result is negative (bit 15) |
| C | Carry | Set on carry/borrow |
| O | Overflow | Set on signed overflow |

### `get_pc() -> int`

Returns the current program counter (a memory address in the unified 64K word RAM — code and data share one address space).

```python
pc = m.get_pc()
print(f"At address 0x{pc:04X}")
```

### `get_memory(addr: int, count: int = 1) -> list[int]`

Reads `count` 16-bit words from memory starting at `addr`. Reads of un-clobbered code cells return 0 since we don't store real R316 opcode encodings.

```python
# Read 4 words starting at address 0x8000
mem = m.get_memory(0x8000, 4)
# [word0, word1, word2, word3]
```

### `get_current_instruction() -> dict | None`

Returns information about the current instruction, or `None` if halted *or* if `pc` points at a non-instruction cell (a `dw` word, poison, or a code cell that was overwritten by a store).

```python
insn = m.get_current_instruction()
# {'op': 'add', 'args': ['r3', 'r1', 'r2'], 'src_line': 3, 'scope': '_C_main'}
if insn:
    print(f"Executing: {insn['op']} {', '.join(insn['args'])}")
```

### `get_stdout() -> str`

Returns the captured stdout as a string.

```python
output = m.get_stdout()
print(f"Program output: {output}")
```

### `is_halted() -> bool`

Returns `True` if the machine has halted (executed `hlt` or returned from main).

```python
if m.is_halted():
    print("Program has finished")
```

### `snapshot() -> dict`

Returns a complete snapshot of the machine state for debugging.

```python
snap = m.snapshot()
# {
#   'pc': 5,
#   'cycles': 100,
#   'halted': False,
#   'regs': {...},
#   'flags': {...},
#   'stdout': 'Hello\n',
#   'stdin': [...],
#   'stdin_pos': 6,
#   'current_instruction': {...},
#   'breakpoints': [...],
#   'trace_count': 0
# }
```

---

## Execution Control

### `step(count: int = 1) -> bool`

Executes one or more instructions. Returns `True` if still running, `False` if halted.

```python
# Single step
m.step()

# Execute 5 instructions at once
m.step(5)

# Execute 0 instructions (no-op)
m.step(0)

# Run until halt
m.step(10000)  # Returns False when halted
```

### `run() -> None`

Runs the machine until it halts or hits the cycle limit.

```python
m.run()
```

### `run_until_breakpoint() -> bool`

Runs until a breakpoint is hit or the machine halts. Returns `True` if a breakpoint was hit.

```python
m.set_breakpoint("_C_main")
hit = m.run_until_breakpoint()
if hit:
    print(f"Breakpoint hit at PC={m.get_pc()}")
```

### `run_until_pc(target_pc: int) -> bool`

Runs until PC reaches `target_pc` or the machine halts. Returns `True` if target was reached.

```python
target = prog.labels['_C_main'] + 5
reached = m.run_until_pc(target)
if reached:
    print(f"Reached PC={target}")
```

---

## Breakpoints

### `set_breakpoint(label_or_pc) -> int`

Sets a breakpoint at a label or PC index. Returns the breakpoint ID.

```python
# Set by label
bp_id = m.set_breakpoint("_C_main")

# Set by PC index
bp_id = m.set_breakpoint(42)
```

### `clear_breakpoint(bp_id: int) -> bool`

Clears a breakpoint by ID. Returns `True` if found and removed.

```python
m.clear_breakpoint(bp_id)
```

### `clear_all_breakpoints() -> None`

Clears all breakpoints.

```python
m.clear_all_breakpoints()
```

### `list_breakpoints() -> list[dict]`

Returns a list of all breakpoints.

```python
bps = m.list_breakpoints()
# [{'id': 1, 'pc': 0, 'label': '_C_main'}, ...]
for bp in bps:
    print(f"Breakpoint {bp['id']}: PC={bp['pc']}")
```

---

## Execution Tracing

### `enable_trace() -> None`

Enables execution tracing. Each executed instruction is recorded.

```python
m.enable_trace()
```

### `disable_trace() -> None`

Disables execution tracing.

```python
m.disable_trace()
```

### `get_trace() -> list[dict]`

Returns the execution trace history. Each entry contains the instruction and state before/after.

```python
trace = m.get_trace()
for entry in trace:
    print(f"PC={entry['pc']}: {entry['op']} {entry['args']}")
    print(f"  Before: r1={entry['regs_before']['r1']}")
    print(f"  After:  r1={entry['regs_after']['r1']}")
```

Each trace entry has:
- `pc`: Memory address of the executed instruction
- `op`: Operation (e.g., 'mov', 'add')
- `args`: List of arguments
- `regs_before`: Register state before execution
- `regs_after`: Register state after execution
- `flags_before`: Flags before execution
- `flags_after`: Flags after execution

### `clear_trace() -> None`

Clears the execution trace history.

```python
m.clear_trace()
```

---

## State Save/Restore

### In-Memory

#### `save_state() -> dict`

Saves the complete machine state to a dictionary.

```python
state = m.save_state()
# {
#   'version': 1,
#   'pc': 5,
#   'cycles': 100,
#   'halted': False,
#   'regs': [0, 10, 20, ...],
#   'flags': {'Z': 0, 'S': 0, 'C': 0, 'O': 0},
#   'mem': [Insn(...) | int, ...],   # full 64K-cell list (Insns + ints)
#   'stdout': [72, 101, 108, 108, 111],
#   'stdin': [49, 50, 51],
#   'stdin_pos': 3,
#   'cursor_col': 0,
#   'cursor_row': 0,
#   'trace': [...],
#   'breakpoints': {...}
# }
```

#### `restore_state(state: dict) -> None`

Restores the machine state from a dictionary.

```python
m.restore_state(state)
print(f"Restored PC={m.get_pc()}")
```

### File-Based

#### `save_state_file(filepath: str) -> None`

Saves the complete machine state to a JSON file. Memory is dumped as a flat list covering the writable RAM region (`0..R316_RAM_WORDS` = 8192 words, the ceiling on real R316 hardware). Each cell is either an `int` (data) or a small dict `{"op": ..., "args": [...], "scope": ..., "src_line": ...}` for `Insn` cells. The dump is **self-contained** — restoring no longer relies on the original `Program` for memory contents, so source-code changes between save and load can't silently corrupt restored state. Files run ~75 KB for a typical program.

```python
m.save_state_file("debug_state.json")
```

#### `Machine.load_state_file(filepath: str, prog: Program) -> Machine`

Class method. Loads state from a JSON file and returns a new Machine instance. Memory is decoded directly from the file, not reconstructed from `prog.mem` — `prog` is still required for the constructor (label resolution at runtime), but mismatches between the saved program and `prog` only affect label-dependent behaviour, not the memory image itself.

```python
m2 = Machine.load_state_file("debug_state.json", prog)
print(f"Loaded PC={m2.get_pc()}")
```

---

## Complete API Reference

| Method | Returns | Description |
|--------|---------|-------------|
| `get_registers()` | `dict[str, int]` | Get all 32 registers |
| `get_flags()` | `dict[str, int]` | Get CPU flags (Z, S, C, O) |
| `get_pc()` | `int` | Get current program counter |
| `get_memory(addr, count)` | `list[int]` | Read words from memory |
| `get_current_instruction()` | `dict \| None` | Get current instruction info |
| `get_stdout()` | `str` | Get captured stdout |
| `is_halted()` | `bool` | Check if machine is halted |
| `snapshot()` | `dict` | Get complete state snapshot |
| `step(count)` | `bool` | Execute N instructions |
| `run()` | `None` | Run until halt |
| `run_until_breakpoint()` | `bool` | Run until breakpoint |
| `run_until_pc(pc)` | `bool` | Run until PC reaches target |
| `set_breakpoint(label_or_pc)` | `int` | Set breakpoint, return ID |
| `clear_breakpoint(id)` | `bool` | Clear breakpoint by ID |
| `clear_all_breakpoints()` | `None` | Clear all breakpoints |
| `list_breakpoints()` | `list[dict]` | List all breakpoints |
| `enable_trace()` | `None` | Enable execution tracing |
| `disable_trace()` | `None` | Disable execution tracing |
| `get_trace()` | `list[dict]` | Get trace history |
| `clear_trace()` | `None` | Clear trace history |
| `save_state()` | `dict` | Save state to dict |
| `restore_state(dict)` | `None` | Restore state from dict |
| `save_state_file(path)` | `None` | Save state to JSON file |
| `load_state_file(path, prog)` | `Machine` | Load state from JSON file |

---

## Examples

### Example 1: Basic Debugging

```python
from tests.r316_emu import parse_asm, Machine

asm = '''
_C_main:
    mov r1, 10
    mov r2, 20
    add r3, r1, r2
    hlt
'''
prog = parse_asm(asm)
m = Machine(prog)
m.pc = prog.labels['_C_main']

# Step through and inspect
while not m.is_halted():
    insn = m.get_current_instruction()
    print(f"PC={m.get_pc()}: {insn['op']} {insn['args']}")
    m.step()
    print(f"  Registers: r1={m.get_registers()['r1']}, r2={m.get_registers()['r2']}, r3={m.get_registers()['r3']}")
```

### Example 2: Breakpoint Debugging

```python
from tests.r316_emu import parse_asm, Machine

asm = '''
_C_main:
    mov r1, 0
_C_loop:
    add r1, r1, 1
    cmp r1, 5
    jne _C_loop
    hlt
'''
prog = parse_asm(asm)
m = Machine(prog)
m.pc = prog.labels['_C_main']

# Set breakpoint at loop
bp_id = m.set_breakpoint("_C_loop")

# Run and hit breakpoint multiple times
for i in range(3):
    hit = m.run_until_breakpoint()
    if not hit:
        break
    print(f"Loop iteration {i+1}: r1={m.get_registers()['r1']}")
    m.step()  # Step past breakpoint

m.clear_breakpoint(bp_id)
m.run()
print(f"Final: r1={m.get_registers()['r1']}")
```

### Example 3: Execution Tracing

```python
from tests.r316_emu import parse_asm, Machine

asm = '''
_C_main:
    mov r1, 5
    mov r2, 3
    mul r3, r1, r2
    hlt
'''
prog = parse_asm(asm)
m = Machine(prog)
m.pc = prog.labels['_C_main']

# Enable tracing
m.enable_trace()

# Run to completion
m.run()

# Analyze trace
trace = m.get_trace()
print(f"Executed {len(trace)} instructions:")
for entry in trace:
    print(f"  PC={entry['pc']}: {entry['op']} {entry['args']}")
    if entry['regs_before'] != entry['regs_after']:
        for reg in ['r1', 'r2', 'r3']:
            if entry['regs_before'][reg] != entry['regs_after'][reg]:
                print(f"    {reg}: {entry['regs_before'][reg]} -> {entry['regs_after'][reg]}")
```

### Example 4: State Save/Restore (Time-Travel Debugging)

```python
from tests.r316_emu import parse_asm, Machine

asm = '''
_C_main:
    mov r1, 10
    mov r2, 20
    add r3, r1, r2
    sub r4, r3, r1
    hlt
'''
prog = parse_asm(asm)
m = Machine(prog)
m.pc = prog.labels['_C_main']

# Run first 2 instructions
m.step(2)
print(f"After 2 steps: r1={m.get_registers()['r1']}, r2={m.get_registers()['r2']}")

# Save state
state = m.save_state()

# Continue execution
m.step(2)
print(f"After 4 steps: r3={m.get_registers()['r3']}, r4={m.get_registers()['r4']}")

# Restore to saved state
m.restore_state(state)
print(f"After restore: r1={m.get_registers()['r1']}, r2={m.get_registers()['r2']}")
print(f"  r3={m.get_registers()['r3']} (should be 0)")
```

### Example 5: Memory Inspection

```python
from tests.r316_emu import parse_asm, Machine

asm = '''
_C_main:
    mov r1, 0x8000
    mov r2, 42
    st r2, r1
    hlt
'''
prog = parse_asm(asm)
m = Machine(prog)
m.pc = prog.labels['_C_main']

# Run program
m.run()

# Inspect memory
mem = m.get_memory(0x8000, 4)
print(f"Memory at 0x8000: {mem}")
# [42, 0, 0, 0]
```

---

## Debugging C Source Files

To debug C source programmatically, compile it with `compile_c()` and load into the emulator.

### Loading the Compiler

```python
import importlib.util
from tests.r316_emu import parse_asm, Machine

# Load compile_c from compiler.py
spec = importlib.util.spec_from_file_location('compiler_main', 'compiler.py')
compiler_main = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compiler_main)
compile_c = compiler_main.compile_c
```

### Example: Compile and Debug C Code

```python
# Compile C source
c_source = '''
int add(int a, int b) {
    return a + b;
}

int main() {
    int result = add(5, 7);
    return result;
}
'''

asm = compile_c(c_source)
prog = parse_asm(asm)
m = Machine(prog)
m.pc = prog.labels['_C_main']

# Debug using the full API
m.enable_trace()
m.run()
trace = m.get_trace()
print(f"Executed {len(trace)} instructions")
print(f"Return value: {m.get_registers()['r1']}")
```

### Example: Breakpoint Debugging a C Function

```python
c_source = '''
int power(int base, int exp) {
    if (exp == 0)
        return 1;
    return base * power(base, exp - 1);
}

int main() {
    int result = power(2, 3);
    return result;
}
'''

asm = compile_c(c_source)
prog = parse_asm(asm)
m = Machine(prog)
m.pc = prog.labels['_C_main']

# Set breakpoint at _C_power
bp_id = m.set_breakpoint('_C_power')

# Run and hit breakpoint multiple times (recursive calls)
for i in range(3):
    hit = m.run_until_breakpoint()
    if not hit:
        break
    regs = m.get_registers()
    print(f"Call {i+1}: r7={regs['r7']}, r8={regs['r8']}")
    m.step()

m.clear_breakpoint(bp_id)
m.run()
print(f"Result: {m.get_registers()['r1']}")  # 8 (2^3)
```

### Symbol Naming Convention

All C functions and global variables are prefixed with `_C_` in assembly:

| C Symbol | Assembly Label |
|----------|----------------|
| `main` | `_C_main` |
| `power` | `_C_power` |
| `my_function` | `_C_my_function` |

### Understanding the ABI

For detailed information, see `docs/ABI.md`. Key points:

- **Arguments**: First 6 integer arguments passed in `r1`–`r6`, remaining on stack
- **Return value**: Integer return in `r1`
- **Stack pointer**: `r30` (sp)
- **Link register**: `r31` (lr)
- **Preserved registers**: `r16`–`r23` (callee-saved)

---

## Notes

### Register r0

`r0` is hardwired to zero. Writes to `r0` are discarded:

```python
# This has no effect
m.wr('r0', 42)  # r0 still 0
```

### Cycle Limit

By default, the machine has a cycle limit of 1,000,000 to prevent infinite loops:

```python
m = Machine(prog, max_cycles=10_000_000)  # 10 million cycles
m = Machine(prog, max_cycles=None)        # Unlimited cycles
```

### Interactive Mode

For interactive terminal input:

```python
m = Machine(prog, interactive=True)
```

This enables raw terminal input with no echo, cursor positioning, and color support.
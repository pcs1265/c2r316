# R316 Emulator CLI Usage

This document describes how to use the R316 emulator (`tests/r316_emu.py`) from the command line.

## Basic Usage

```bash
python3 tests/r316_emu.py <file>
```

The emulator accepts both `.asm` (assembly) and `.c` (C source) files.

## Options

| Option | Description |
|--------|-------------|
| `--cycles N` | Maximum emulated cycles (default: 1,000,000) |
| `--unlimited-cycles` | Run without a cycle limit |
| `--freq HZ` | Throttle emulation to HZ cycles/s (e.g., 1000000 for 1 MHz) |
| `--show-retval` | Print main() return value after execution |
| `--stdin STR` | Provide stdin input as a string |
| `--stdin-file FILE` | Read stdin input from a file |
| `--interactive` | Enable interactive terminal input |

---

## Running Assembly Files

```bash
# Run an assembly file
python3 tests/r316_emu.py output.asm

# With cycle limit
python3 tests/r316_emu.py output.asm --cycles 500000

# Show return value
python3 tests/r316_emu.py output.asm --show-retval
```

---

## Running C Files

The emulator can compile and run C source files directly:

```bash
# Compile and run a C file
python3 tests/r316_emu.py examples/hello.c

# Provide stdin input
python3 tests/r316_emu.py examples/hello.c --stdin "2
3
"

# Read stdin from a file
python3 tests/r316_emu.py examples/hello.c --stdin-file input.txt

# Show return value after execution
python3 tests/r316_emu.py examples/hello.c --stdin "2
3
" --show-retval

# Limit execution cycles
python3 tests/r316_emu.py examples/hello.c --cycles 500000

# Throttle emulation speed (e.g., 1 MHz)
python3 tests/r316_emu.py examples/hello.c --freq 1000000
```

---

## Interactive Mode

For programs that require interactive input:

```bash
python3 tests/r316_emu.py examples/terminal_demo.c --interactive
```

Interactive mode enables:
- Raw terminal input (no echo)
- Character-by-character input
- Cursor positioning support
- Color support

---

## Cycle Limits

By default, programs are limited to 1,000,000 cycles to prevent infinite loops:

```bash
# Custom cycle limit
python3 tests/r316_emu.py examples/hello.c --cycles 5000000

# Unlimited cycles (no timeout)
python3 tests/r316_emu.py examples/hello.c --unlimited-cycles
```

---

## Output

The emulator prints:
1. Program stdout (if any)
2. Cycle count: `[N cycles]`
3. Return value (if `--show-retval`): `[exit N]`

Example:
```
Enter base number: 2
Enter power number(positive integer): 3
2^3 = 8[4188 cycles]
[exit 0]
```

---

## Tips

### Symbol Naming Convention

C functions and global variables are prefixed with `_C_` in assembly:
- `main` → `_C_main`
- `power` → `_C_power`

### Annotated Assembly

Use the compiler's `-g` flag to generate assembly with source line comments:

```bash
python3 compiler.py examples/hello.c -o output.asm -g
```

### Understanding the ABI

See `docs/ABI.md` for details on how C constructs map to assembly:
- Arguments: First 6 in `r1`–`r6`
- Return value: `r1`
- Stack pointer: `r30`
- Link register: `r31`
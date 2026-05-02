"""Compatibility wrapper for the modular R316 emulator package.

The implementation lives in tests/emu. This module keeps existing imports and
`python tests/r316_emu.py ...` working.
"""

from __future__ import annotations

try:
    from emu import Flags, Insn, Machine, Program, R316_RAM_WORDS, parse_asm, run_main
except ModuleNotFoundError:
    from tests.emu import Flags, Insn, Machine, Program, R316_RAM_WORDS, parse_asm, run_main

__all__ = [
    'Flags',
    'Insn',
    'Machine',
    'Program',
    'R316_RAM_WORDS',
    'parse_asm',
    'run_main',
]


if __name__ == '__main__':
    try:
        from emu.cli import main
    except ModuleNotFoundError:
        from tests.emu.cli import main

    raise SystemExit(main())

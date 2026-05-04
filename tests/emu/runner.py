"""Public helpers for running R316 assembly."""

from __future__ import annotations

from .machine import Machine
from .parser import parse_asm


def run_main(asm: str, max_cycles: int | None = 1_000_000, stdin: str = '',
             freq: float | None = None,
             ram_words: int | None = 8192) -> tuple[int, str, int]:
    """Compile output -> (return_value_of_main, stdout, cycles). Starts at address 0.

    Defaults `ram_words` to 8192 (the maximum supported by the runtime's
    stack auto-detect, manual lines 56-58 + runtime.asm line 144) so the
    emu mirrors real R316's row-bounded address space. Tests that need a
    flat 64K window can pass ram_words=None explicitly.
    """
    prog = parse_asm(asm)
    m = Machine(prog, sp_init=0, max_cycles=max_cycles, stdin=stdin, freq=freq,
                ram_words=ram_words)
    m.run()
    return m.regs[1] & 0xFFFF, m.stdout_str(), m.cycles

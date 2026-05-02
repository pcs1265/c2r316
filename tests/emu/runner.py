"""Public helpers for running R316 assembly."""

from __future__ import annotations

from .machine import Machine
from .parser import parse_asm


def run_main(asm: str, max_cycles: int | None = 1_000_000, stdin: str = '',
             freq: float | None = None) -> tuple[int, str, int]:
    """Compile output -> (return_value_of_main, stdout, cycles). Starts at address 0."""
    prog = parse_asm(asm)
    m = Machine(prog, sp_init=0, max_cycles=max_cycles, stdin=stdin, freq=freq)
    m.run()
    return m.regs[1] & 0xFFFF, m.stdout_str(), m.cycles

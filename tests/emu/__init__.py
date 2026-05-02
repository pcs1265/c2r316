"""Modular R316 emulator package used by compiler tests."""

from .constants import R316_RAM_WORDS
from .machine import Machine
from .model import Flags, Insn, Program
from .parser import parse_asm
from .runner import run_main

__all__ = [
    'Flags',
    'Insn',
    'Machine',
    'Program',
    'R316_RAM_WORDS',
    'parse_asm',
    'run_main',
]

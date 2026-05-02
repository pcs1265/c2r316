"""Shared constants and integer helpers for the R316 emulator."""

_MASK16 = 0xFFFF
_BIT15 = 0x8000
R316_RAM_WORDS = 0x2000  # 8192 words, writable-RAM ceiling on real R316 hardware.


def _u16(x: int) -> int:
    return x & _MASK16


def _s16(x: int) -> int:
    x &= _MASK16
    return x - 0x10000 if x & _BIT15 else x

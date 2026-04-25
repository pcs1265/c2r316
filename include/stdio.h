/*
 * stdio.h — I/O for the R316 C compiler
 *
 * Provides terminal I/O via two MMIO primitives:
 *   _term_putch(c)  — st c → 0x9FB5 (terminal output)
 *   _term_getch()   — polling read on 0x9F80 (keyboard input)
 *
 * Public API:
 *   putchar(c), getchar()
 *   puts(s), print_str(s)
 *   print_int(n), print_uint(n), print_hex(n)
 *   printf(fmt, ...)  — %d %u %x %c %s %%
 */

#ifndef STDIO_H
#define STDIO_H

#include "runtime/stdarg.h"

/* ── MMIO primitives ────────────────────────────────────────────────────── */

__attribute__((always_inline)) static void _term_putch(int c) {
    asm("st %0, 0x9FB5" : "r"(c));
}

static int _term_getch(void) {
    int *port;
    int c;
    port = 0x9F80;
    c = *port;
    while (c == 0) {
        c = *port;
    }
    return c;
}

/* ── putchar / getchar ──────────────────────────────────────────────────── */

__attribute__((always_inline)) static void putchar(int c) {
    _term_putch(c);
}

__attribute__((always_inline)) static int getchar(void) {
    return _term_getch();
}

/* ── puts / print_str ───────────────────────────────────────────────────── */

static void puts(char *s) {
    while (*s) {
        _term_putch(*s);
        s++;
    }
    _term_putch(10);
}

static void print_str(char *s) {
    while (*s) {
        _term_putch(*s);
        s++;
    }
}

/* ── print_int / print_uint ─────────────────────────────────────────────── */

static void print_int(int n) {
    int digits[6];
    int count;
    int i;

    if (n & 0x8000) {
        _term_putch('-');
        n = 0 - n;
    }
    if (n == 0) {
        _term_putch('0');
        return;
    }
    count = 0;
    while (n != 0) {
        digits[count] = n % 10;
        n = n / 10;
        count++;
    }
    i = count - 1;
    while (i >= 0) {
        _term_putch(digits[i] + '0');
        i--;
    }
}

static void print_uint(unsigned int n) {
    int digits[6];
    int count;
    int i;

    if (n == 0) {
        _term_putch('0');
        return;
    }
    count = 0;
    while (n != 0) {
        digits[count] = n % 10;
        n = n / 10;
        count++;
    }
    i = count - 1;
    while (i >= 0) {
        _term_putch(digits[i] + '0');
        i--;
    }
}

/* ── print_hex ──────────────────────────────────────────────────────────── */

static void print_hex(unsigned int n) {
    int nibble;
    int shift;

    shift = 12;
    while (shift >= 0) {
        nibble = (n >> shift) & 0xF;
        if (nibble >= 10) {
            _term_putch(nibble + 55);
        } else {
            _term_putch(nibble + '0');
        }
        shift = shift - 4;
    }
}

/* ── printf ─────────────────────────────────────────────────────────────── */
/* Supports: %d %u %x %c %s %% — no width/precision/length modifiers.      */

static void printf(char *fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    while (*fmt) {
        if (*fmt != '%') {
            _term_putch(*fmt);
            fmt++;
        } else {
            fmt++;
            if (*fmt == 'd') {
                print_int(va_arg(ap, int));
            } else if (*fmt == 'u') {
                print_uint(va_arg(ap, int));
            } else if (*fmt == 'x') {
                print_hex(va_arg(ap, int));
            } else if (*fmt == 'c') {
                _term_putch(va_arg(ap, int));
            } else if (*fmt == 's') {
                print_str(va_arg(ap, char *));
            } else if (*fmt == '%') {
                _term_putch('%');
            }
            fmt++;
        }
    }
    va_end(ap);
}

#endif /* STDIO_H */

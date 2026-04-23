/*
 * stdlib.h — C standard library for the R316 C compiler
 *
 * Auto-prepended to every compilation unit by compiler.py.
 * Do not #include manually.
 *
 * I/O is implemented via two primitives:
 *   _term_putch(c)  — inline asm: st c → 0x9FB5 (terminal output)
 *   _term_getch()   — pointer read loop on 0x9F80 (keyboard input)
 *
 * Functions kept in runtime.asm (called by compiler internals):
 *   __udiv, __umod      — emitted by codegen for / and %
 *   __stack_init        — boot: detect RAM size, set SP
 *   __term_init         — boot: configure terminal geometry/colour
 */

#ifndef STDLIB_H
#define STDLIB_H

/* ── division helpers (called by compiler for / and %) ─────────────────── */

static int __udiv(unsigned int dividend, unsigned int divisor) {
    unsigned int remainder;
    unsigned int i;
    remainder = 0;
    i = 0;
    while (i < 16) {
        remainder = (remainder << 1) | (dividend >> 15);
        dividend = dividend << 1;
        if (remainder >= divisor) {
            remainder = remainder - divisor;
            dividend = dividend | 1;
        }
        i = i + 1;
    }
    return dividend;
}

static int __umod(unsigned int dividend, unsigned int divisor) {
    unsigned int remainder;
    unsigned int i;
    remainder = 0;
    i = 0;
    while (i < 16) {
        remainder = (remainder << 1) | (dividend >> 15);
        dividend = dividend << 1;
        if (remainder >= divisor) {
            remainder = remainder - divisor;
        }
        i = i + 1;
    }
    return remainder;
}

/* ── MMIO primitives ────────────────────────────────────────────────────── */

static void _term_putch(int c) {
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

static void putchar(int c) {
    _term_putch(c);
}

static int getchar(void) {
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

/* ── memset / memcpy ────────────────────────────────────────────────────── */

static void memset(char *dst, int val, int n) {
    while (n != 0) {
        *dst = val;
        dst++;
        n--;
    }
}

static void memcpy(char *dst, char *src, int n) {
    while (n != 0) {
        *dst = *src;
        dst++;
        src++;
        n--;
    }
}

/* ── strlen / strcmp ────────────────────────────────────────────────────── */

static int strlen(char *s) {
    char *p;
    p = s;
    while (*p) {
        p++;
    }
    return p - s;
}

static int strcmp(char *a, char *b) {
    while (*a && *a == *b) {
        a++;
        b++;
    }
    return *a - *b;
}

#endif /* STDLIB_H */

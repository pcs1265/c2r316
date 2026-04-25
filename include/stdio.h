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

#include <stdarg.h>

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

/* ── scanf ──────────────────────────────────────────────────────────────── */
/* Supports: %d %u %x %c %s — no width/precision/length modifiers.         */
/* Returns number of items successfully assigned (EOF=-1 not implemented).  */

static int _is_space(int c) {
    if (c == ' ') return 1;
    if (c == '\t') return 1;
    if (c == '\n') return 1;
    if (c == '\r') return 1;
    return 0;
}

static int _is_digit(int c) {
    if (c < '0') return 0;
    if (c > '9') return 0;
    return 1;
}

static int _is_xdigit(int c) {
    if (c >= '0' && c <= '9') return 1;
    if (c >= 'a' && c <= 'f') return 1;
    if (c >= 'A' && c <= 'F') return 1;
    return 0;
}

static int _xdigit_val(int c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    return c - 'A' + 10;
}

static int scanf(char *fmt, ...) {
    va_list ap;
    int assigned;
    int c;
    int neg;
    unsigned int uval;
    int *iptr;
    unsigned int *uptr;
    char *sptr;

    va_start(ap, fmt);
    assigned = 0;
    c = 0;

    while (*fmt) {
        if (*fmt == '%') {
            fmt++;
            if (*fmt == 'd' || *fmt == 'u' || *fmt == 'x') {
                /* skip leading whitespace */
                if (c == 0) c = _term_getch();
                while (_is_space(c)) c = _term_getch();

                if (*fmt == 'x') {
                    /* read hex integer */
                    uval = 0;
                    if (!_is_xdigit(c)) { fmt++; continue; }
                    while (_is_xdigit(c)) {
                        uval = uval * 16 + _xdigit_val(c);
                        c = _term_getch();
                    }
                    uptr = va_arg(ap, unsigned int *);
                    *uptr = uval;
                    assigned++;
                } else if (*fmt == 'u') {
                    /* read unsigned decimal */
                    uval = 0;
                    if (!_is_digit(c)) { fmt++; continue; }
                    while (_is_digit(c)) {
                        uval = uval * 10 + (c - '0');
                        c = _term_getch();
                    }
                    uptr = va_arg(ap, unsigned int *);
                    *uptr = uval;
                    assigned++;
                } else {
                    /* read signed decimal */
                    neg = 0;
                    if (c == '-') { neg = 1; c = _term_getch(); }
                    uval = 0;
                    if (!_is_digit(c)) { fmt++; continue; }
                    while (_is_digit(c)) {
                        uval = uval * 10 + (c - '0');
                        c = _term_getch();
                    }
                    iptr = va_arg(ap, int *);
                    if (neg) {
                        *iptr = 0 - uval;
                    } else {
                        *iptr = uval;
                    }
                    assigned++;
                }
                fmt++;
            } else if (*fmt == 'c') {
                /* read one character, no whitespace skipping */
                if (c == 0) c = _term_getch();
                iptr = va_arg(ap, int *);
                *iptr = c;
                c = 0;
                assigned++;
                fmt++;
            } else if (*fmt == 's') {
                /* read non-whitespace run into char* */
                if (c == 0) c = _term_getch();
                while (_is_space(c)) c = _term_getch();
                sptr = va_arg(ap, char *);
                while (c != 0 && !_is_space(c)) {
                    *sptr = c;
                    sptr++;
                    c = _term_getch();
                }
                *sptr = 0;
                assigned++;
                fmt++;
            } else {
                fmt++;
            }
        } else if (_is_space(*fmt)) {
            /* whitespace in format: skip any whitespace in input */
            if (c == 0) c = _term_getch();
            while (_is_space(c)) c = _term_getch();
            fmt++;
        } else {
            /* literal character match */
            if (c == 0) c = _term_getch();
            if (c != *fmt) break;
            c = 0;
            fmt++;
        }
    }

    va_end(ap);
    return assigned;
}

#endif /* STDIO_H */

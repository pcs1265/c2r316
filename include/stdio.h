/*
 * stdio.h — I/O for the R316 C compiler
 *
 * Builds on terminal.h for character I/O primitives.
 *
 * Public API:
 *   putchar(c), getchar()
 *   puts(s), print_str(s)
 *   print_int(n), print_uint(n), print_hex(n)
 *   printf(fmt, ...)  — %d %u %x %c %s %%
 *   scanf(fmt, ...)   — %d %u %x %c %s
 */

#ifndef STDIO_H
#define STDIO_H

#include <terminal.h>
#include <stdarg.h>

/* ── putchar / getchar ──────────────────────────────────────────────────── */

__attribute__((always_inline)) static void putchar(int c) {
    term_putch(c);
}

__attribute__((always_inline)) static int getchar(void) {
    return term_getch();
}

/* ── puts / print_str ───────────────────────────────────────────────────── */

static void puts(char *s) {
    while (*s) {
        term_putch(*s);
        s++;
    }
    term_putch('\n');
}

static void print_str(char *s) {
    while (*s) {
        term_putch(*s);
        s++;
    }
}

/* ── print_int / print_uint ─────────────────────────────────────────────── */

static void print_int(int n) {
    int digits[6];
    int count;
    int i;

    if (n & 0x8000) {
        term_putch('-');
        n = 0 - n;
    }
    if (n == 0) {
        term_putch('0');
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
        term_putch(digits[i] + '0');
        i--;
    }
}

static void print_uint(unsigned int n) {
    int digits[6];
    int count;
    int i;

    if (n == 0) {
        term_putch('0');
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
        term_putch(digits[i] + '0');
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
            term_putch(nibble + 55);
        } else {
            term_putch(nibble + '0');
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
            term_putch(*fmt);
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
                term_putch(va_arg(ap, int));
            } else if (*fmt == 's') {
                print_str(va_arg(ap, char *));
            } else if (*fmt == '%') {
                term_putch('%');
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
                if (c == 0) c = term_getch();
                while (_is_space(c)) c = term_getch();

                if (*fmt == 'x') {
                    uval = 0;
                    if (!_is_xdigit(c)) { fmt++; continue; }
                    while (_is_xdigit(c)) {
                        uval = uval * 16 + _xdigit_val(c);
                        c = term_getch();
                    }
                    uptr = va_arg(ap, unsigned int *);
                    *uptr = uval;
                    assigned++;
                } else if (*fmt == 'u') {
                    uval = 0;
                    if (!_is_digit(c)) { fmt++; continue; }
                    while (_is_digit(c)) {
                        uval = uval * 10 + (c - '0');
                        c = term_getch();
                    }
                    uptr = va_arg(ap, unsigned int *);
                    *uptr = uval;
                    assigned++;
                } else {
                    neg = 0;
                    if (c == '-') { neg = 1; c = term_getch(); }
                    uval = 0;
                    if (!_is_digit(c)) { fmt++; continue; }
                    while (_is_digit(c)) {
                        uval = uval * 10 + (c - '0');
                        c = term_getch();
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
                if (c == 0) c = term_getch();
                iptr = va_arg(ap, int *);
                *iptr = c;
                c = 0;
                assigned++;
                fmt++;
            } else if (*fmt == 's') {
                if (c == 0) c = term_getch();
                while (_is_space(c)) c = term_getch();
                sptr = va_arg(ap, char *);
                while (c != 0 && !_is_space(c)) {
                    *sptr = c;
                    sptr++;
                    c = term_getch();
                }
                *sptr = 0;
                assigned++;
                fmt++;
            } else {
                fmt++;
            }
        } else if (_is_space(*fmt)) {
            if (c == 0) c = term_getch();
            while (_is_space(c)) c = term_getch();
            fmt++;
        } else {
            if (c == 0) c = term_getch();
            if (c != *fmt) break;
            c = 0;
            fmt++;
        }
    }

    va_end(ap);
    return assigned;
}

#endif /* STDIO_H */

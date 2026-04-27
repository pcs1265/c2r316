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

static int puts(const char *s) {
    while (*s) {
        term_putch(*s);
        s++;
    }
    term_putch('\n');
    return 0;
}

static void print_str(const char *s) {
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
/* Supports: %[flags][width][.prec]specifier                                */
/*   flags:  - 0 + space #                                                  */
/*   width:  decimal integer                                                 */
/*   prec:   .decimal (min digits for integers; max chars for %s)           */
/*   specs:  d i u x X o c s %                                              */
/* Returns number of characters written.                                    */

static int printf(const char *fmt, ...) {
    va_list ap;
    int n;
    int flag_left, flag_zero, flag_plus, flag_space, flag_hash;
    int width, prec;
    int spec;
    int is_signed, negative;
    unsigned int uval;
    int ival;
    int buf[20];
    int prefix[4];
    int blen, plen, zero_pad, content_width, total_pad, pad;
    int lo, hi, bi, pi, zi, tmp;
    int d;
    unsigned int v;
    const char *s;
    int slen;

    va_start(ap, fmt);
    n = 0;
    while (*fmt) {
        if (*fmt != '%') {
            term_putch(*fmt);
            n++;
            fmt++;
        } else {
            fmt++;

            /* flags */
            flag_left = 0; flag_zero = 0; flag_plus = 0;
            flag_space = 0; flag_hash = 0;
            while (*fmt == '-' || *fmt == '0' || *fmt == '+' ||
                   *fmt == ' ' || *fmt == '#') {
                if (*fmt == '-')      flag_left  = 1;
                else if (*fmt == '0') flag_zero  = 1;
                else if (*fmt == '+') flag_plus  = 1;
                else if (*fmt == ' ') flag_space = 1;
                else if (*fmt == '#') flag_hash  = 1;
                fmt++;
            }

            /* width */
            width = 0;
            while (*fmt >= '0' && *fmt <= '9') {
                width = width * 10 + (*fmt - '0');
                fmt++;
            }

            /* precision */
            prec = -1;
            if (*fmt == '.') {
                fmt++;
                prec = 0;
                while (*fmt >= '0' && *fmt <= '9') {
                    prec = prec * 10 + (*fmt - '0');
                    fmt++;
                }
            }

            spec = *fmt;
            if (*fmt) fmt++;

            if (spec == '%') {
                term_putch('%'); n++;
            } else if (spec == 'c') {
                ival = va_arg(ap, int);
                if (!flag_left) {
                    pad = width - 1;
                    while (pad > 0) { term_putch(' '); n++; pad--; }
                }
                term_putch(ival); n++;
                if (flag_left) {
                    pad = width - 1;
                    while (pad > 0) { term_putch(' '); n++; pad--; }
                }
            } else if (spec == 's') {
                s = va_arg(ap, char *);
                slen = 0;
                while (s[slen]) slen++;
                if (prec >= 0 && slen > prec) slen = prec;
                pad = width - slen;
                if (!flag_left) {
                    while (pad > 0) { term_putch(' '); n++; pad--; }
                }
                bi = 0;
                while (bi < slen) { term_putch(s[bi]); n++; bi++; }
                if (flag_left) {
                    while (pad > 0) { term_putch(' '); n++; pad--; }
                }
            } else if (spec == 'd' || spec == 'i' || spec == 'u' ||
                       spec == 'x' || spec == 'X' || spec == 'o') {
                is_signed = (spec == 'd' || spec == 'i');
                negative = 0;
                if (is_signed) {
                    ival = va_arg(ap, int);
                    if (ival & 0x8000) {
                        negative = 1;
                        uval = (unsigned int)(0 - ival);
                    } else {
                        uval = (unsigned int)ival;
                    }
                } else {
                    ival = va_arg(ap, int);
                    uval = (unsigned int)ival;
                }

                /* convert to digits in buf[], least-significant first */
                blen = 0;
                if (uval == 0) {
                    if (prec != 0) { buf[0] = '0'; blen = 1; }
                } else {
                    v = uval;
                    if (spec == 'x') {
                        while (v) {
                            d = v & 0xF;
                            buf[blen] = (d < 10) ? '0' + d : 'a' + d - 10;
                            blen++;
                            v = v >> 4;
                        }
                    } else if (spec == 'X') {
                        while (v) {
                            d = v & 0xF;
                            buf[blen] = (d < 10) ? '0' + d : 'A' + d - 10;
                            blen++;
                            v = v >> 4;
                        }
                    } else if (spec == 'o') {
                        while (v) {
                            buf[blen] = '0' + (v & 7);
                            blen++;
                            v = v >> 3;
                        }
                    } else {
                        while (v) {
                            buf[blen] = '0' + v % 10;
                            blen++;
                            v = v / 10;
                        }
                    }
                    /* reverse digit string */
                    lo = 0; hi = blen - 1;
                    while (lo < hi) {
                        tmp = buf[lo]; buf[lo] = buf[hi]; buf[hi] = tmp;
                        lo++; hi--;
                    }
                }

                /* prefix string: sign / 0x / 0X / 0 */
                plen = 0;
                if (negative)        { prefix[plen] = '-'; plen++; }
                else if (flag_plus)  { prefix[plen] = '+'; plen++; }
                else if (flag_space) { prefix[plen] = ' '; plen++; }
                if (flag_hash) {
                    if (spec == 'x') {
                        prefix[plen] = '0'; plen++;
                        prefix[plen] = 'x'; plen++;
                    } else if (spec == 'X') {
                        prefix[plen] = '0'; plen++;
                        prefix[plen] = 'X'; plen++;
                    } else if (spec == 'o' && !(blen > 0 && buf[0] == '0')) {
                        prefix[plen] = '0'; plen++;
                    }
                }

                /* precision → extra leading zeros before digits */
                zero_pad = 0;
                if (prec > blen) zero_pad = prec - blen;

                /* '-' overrides '0' */
                if (flag_left) flag_zero = 0;

                content_width = plen + zero_pad + blen;
                total_pad = width - content_width;
                if (total_pad < 0) total_pad = 0;

                if (!flag_left && !flag_zero) {
                    pad = total_pad;
                    while (pad > 0) { term_putch(' '); n++; pad--; }
                }
                pi = 0;
                while (pi < plen) { term_putch(prefix[pi]); n++; pi++; }
                if (!flag_left && flag_zero) {
                    pad = total_pad;
                    while (pad > 0) { term_putch('0'); n++; pad--; }
                }
                zi = 0;
                while (zi < zero_pad) { term_putch('0'); n++; zi++; }
                bi = 0;
                while (bi < blen) { term_putch(buf[bi]); n++; bi++; }
                if (flag_left) {
                    pad = total_pad;
                    while (pad > 0) { term_putch(' '); n++; pad--; }
                }
            }
            /* unknown specifiers: skip */
        }
    }
    va_end(ap);
    return n;
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

static int scanf(const char *fmt, ...) {
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

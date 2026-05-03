/*
 * stdio.h — I/O for the R316 C compiler
 *
 * Builds on terminal.h for character I/O primitives.
 *
 * Public API:
 *   putchar(c), putc(c, stream), fputc(c, stream)
 *   getchar(), getc(stream), fgetc(stream), ungetc(c, stream)
 *   puts(s), print_str(s)
 *   fputs(s, stream), fgets(s, n, stream)
 *   fflush(stream)
 *   print_int(n), print_uint(n), print_long(n), print_ulong(n), print_hex(n)
 *   printf(fmt, ...)         — %d %u %x %ld %lu %lx %c %s %%
 *   fprintf(stream, fmt, ...)
 *   sprintf(buf, fmt, ...)
 *   snprintf(buf, n, fmt, ...)
 *   scanf(fmt, ...)          — %d %u %x %ld %lu %lx %c %s
 *   fscanf(stream, fmt, ...)
 */

#ifndef STDIO_H
#define STDIO_H

#include <terminal.h>
#include <stdarg.h>

/* ── FILE / streams / EOF ───────────────────────────────────────────────── */

typedef int FILE;

#define stdin  ((FILE *)0)
#define stdout ((FILE *)1)
#define stderr ((FILE *)2)
#define EOF    (-1)

/* ── Line discipline (cooked input) ─────────────────────────────────────── */
/* Owns the line buffer and ungetc slot. Builds line-buffered input with
   echo and backspace editing on top of raw term_getch / term_putch /
   term_erase_prev. */

#define _IBUF_SIZE 64
static char _ibuf[_IBUF_SIZE];
static int  _ibuf_len;
static int  _ibuf_pos;
static int  _ungetc_buf;
static int  _ungetc_valid;

static int _cooked_getch(void) {
    int c;

    if (_ungetc_valid) {
        c = _ungetc_buf;
        _ungetc_valid = 0;
        return c;
    }

    if (_ibuf_pos < _ibuf_len) {
        c = _ibuf[_ibuf_pos];
        _ibuf_pos++;
        return c;
    }

    _ibuf_len = 0;
    _ibuf_pos = 0;
    while (1) {
        c = term_getch();
        if (c == 8 || c == 127) {
            if (_ibuf_len > 0) {
                _ibuf_len--;
                term_erase_prev();
            }
        } else if (c == '\r' || c == '\n') {
            term_putch('\n');
            if (_ibuf_len < _IBUF_SIZE - 1) {
                _ibuf[_ibuf_len] = '\n';
                _ibuf_len++;
            }
            break;
        } else {
            if (_ibuf_len < _IBUF_SIZE - 1) {
                term_putch(c);
                _ibuf[_ibuf_len] = c;
                _ibuf_len++;
            }
        }
    }

    c = _ibuf[_ibuf_pos];
    _ibuf_pos++;
    return c;
}

/* ── putchar / getchar ──────────────────────────────────────────────────── */

__attribute__((always_inline)) static void putchar(int c) {
    term_putch(c);
}

__attribute__((always_inline)) static int putc(int c, FILE *stream) {
    (void)stream;
    term_putch(c);
    return c;
}

__attribute__((always_inline)) static int fputc(int c, FILE *stream) {
    (void)stream;
    term_putch(c);
    return c;
}

__attribute__((always_inline)) static int getchar(void) {
    return _cooked_getch();
}

/* Raw single-keypress read: no echo, no line buffering, no Enter required. */
__attribute__((always_inline)) static int getch(void) {
    return term_getch();
}

/* Raw single-character write — same as putchar, conio-style alias. */
__attribute__((always_inline)) static int putch(int c) {
    term_putch(c);
    return c;
}

__attribute__((always_inline)) static int getc(FILE *stream) {
    (void)stream;
    return _cooked_getch();
}

__attribute__((always_inline)) static int fgetc(FILE *stream) {
    (void)stream;
    return _cooked_getch();
}

static int ungetc(int c, FILE *stream) {
    (void)stream;
    _ungetc_buf = c;
    _ungetc_valid = 1;
    return c;
}

__attribute__((always_inline)) static int fflush(FILE *stream) {
    (void)stream;
    return 0;
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

/* ── fputs / fgets ──────────────────────────────────────────────────────── */
/* All streams map to the single terminal device.                            */

static int fputs(const char *s, FILE *stream) {
    (void)stream;
    while (*s) {
        term_putch(*s);
        s++;
    }
    return 0;
}

/* Reads at most n-1 chars, stops after '\n' (included) or EOF.
   Returns s on success, NULL if no characters were read.              */
static char *fgets(char *s, int n, FILE *stream) {
    int c;
    int i;
    (void)stream;
    if (n <= 0) return 0;
    i = 0;
    while (i < n - 1) {
        c = _cooked_getch();
        if (c == 0) break;
        s[i] = c;
        i++;
        if (c == '\n') break;
    }
    if (i == 0) return 0;
    s[i] = 0;
    return s;
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

static void print_long(long n) {
    int digits[11];
    int count;
    int i;
    unsigned long u;

    if (n < 0) {
        term_putch('-');
        u = 0 - n;
    } else {
        u = n;
    }
    if (u == 0) {
        term_putch('0');
        return;
    }
    count = 0;
    while (u != 0) {
        digits[count] = u % 10;
        u = u / 10;
        count++;
    }
    i = count - 1;
    while (i >= 0) {
        term_putch(digits[i] + '0');
        i--;
    }
}

static void print_ulong(unsigned long n) {
    int digits[11];
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
    int spec, length_long;
    int is_signed, negative;
    unsigned int uval;
    unsigned long ulval;
    unsigned long vl;
    long lval;
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

            length_long = 0;
            if (*fmt == 'l') {
                length_long = 1;
                fmt++;
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
                if (length_long && is_signed) {
                    lval = va_arg(ap, long);
                    if (lval < 0) {
                        negative = 1;
                        ulval = 0 - lval;
                    } else {
                        ulval = lval;
                    }
                } else if (length_long) {
                    ulval = va_arg(ap, unsigned long);
                } else if (is_signed) {
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
                if (length_long) {
                    if (ulval == 0) {
                        if (prec != 0) { buf[0] = '0'; blen = 1; }
                    } else {
                        vl = ulval;
                        if (spec == 'x' || spec == 'X' || spec == 'o') {
                            while (vl) {
                                if (spec == 'o') {
                                    d = vl % 8;
                                    buf[blen] = '0' + d;
                                    vl = vl / 8;
                                } else {
                                    d = vl % 16;
                                    if (spec == 'x') {
                                        buf[blen] = (d < 10) ? '0' + d : 'a' + d - 10;
                                    } else {
                                        buf[blen] = (d < 10) ? '0' + d : 'A' + d - 10;
                                    }
                                    vl = vl / 16;
                                }
                                blen++;
                            }
                        } else {
                            while (vl) {
                                d = vl % 10;
                                buf[blen] = '0' + d;
                                blen++;
                                vl = vl / 10;
                            }
                        }
                        lo = 0; hi = blen - 1;
                        while (lo < hi) {
                            tmp = buf[lo]; buf[lo] = buf[hi]; buf[hi] = tmp;
                            lo++; hi--;
                        }
                    }
                } else if (uval == 0) {
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

/* ── fprintf ────────────────────────────────────────────────────────────── */

static int fprintf(FILE *stream, const char *fmt, ...) {
    va_list ap;
    int n;
    (void)stream;
    va_start(ap, fmt);
    /* reuse printf's va_list path via vprintf-style forwarding not available;
       duplicate the call through printf by re-invoking with the same ap.
       Since printf takes (fmt, ...) we must call it directly. */
    n = 0;
    {
        /* inline: same body as printf but driven by ap already started */
        int flag_left, flag_zero, flag_plus, flag_space, flag_hash;
        int width, prec, spec, length_long, is_signed, negative;
        unsigned int uval; unsigned long ulval; unsigned long vl; long lval; int ival;
        int buf[20]; int prefix[4];
        int blen, plen, zero_pad, content_width, total_pad, pad;
        int lo, hi, bi, pi, zi, tmp, d;
        unsigned int v;
        const char *s; int slen;
        while (*fmt) {
            if (*fmt != '%') { term_putch(*fmt); n++; fmt++; }
            else {
                fmt++;
                flag_left=0; flag_zero=0; flag_plus=0; flag_space=0; flag_hash=0;
                while (*fmt=='-'||*fmt=='0'||*fmt=='+'||*fmt==' '||*fmt=='#') {
                    if (*fmt=='-') flag_left=1;
                    else if (*fmt=='0') flag_zero=1;
                    else if (*fmt=='+') flag_plus=1;
                    else if (*fmt==' ') flag_space=1;
                    else if (*fmt=='#') flag_hash=1;
                    fmt++;
                }
                width=0;
                while (*fmt>='0'&&*fmt<='9') { width=width*10+(*fmt-'0'); fmt++; }
                prec=-1;
                if (*fmt=='.') { fmt++; prec=0; while (*fmt>='0'&&*fmt<='9') { prec=prec*10+(*fmt-'0'); fmt++; } }
                length_long=0;
                if (*fmt=='l') { length_long=1; fmt++; }
                spec=*fmt; if (*fmt) fmt++;
                if (spec=='%') { term_putch('%'); n++; }
                else if (spec=='c') {
                    ival=va_arg(ap,int);
                    if (!flag_left) { pad=width-1; while(pad>0){term_putch(' ');n++;pad--;} }
                    term_putch(ival); n++;
                    if (flag_left) { pad=width-1; while(pad>0){term_putch(' ');n++;pad--;} }
                } else if (spec=='s') {
                    s=va_arg(ap,char*); slen=0; while(s[slen]) slen++;
                    if (prec>=0&&slen>prec) slen=prec;
                    pad=width-slen;
                    if (!flag_left) { while(pad>0){term_putch(' ');n++;pad--;} }
                    bi=0; while(bi<slen){term_putch(s[bi]);n++;bi++;}
                    if (flag_left) { while(pad>0){term_putch(' ');n++;pad--;} }
                } else if (spec=='d'||spec=='i'||spec=='u'||spec=='x'||spec=='X'||spec=='o') {
                    is_signed=(spec=='d'||spec=='i'); negative=0;
                    if (length_long&&is_signed) { lval=va_arg(ap,long); if(lval<0){negative=1;ulval=0-lval;}else ulval=lval; }
                    else if (length_long) { ulval=va_arg(ap,unsigned long); }
                    else if (is_signed) { ival=va_arg(ap,int); if(ival&0x8000){negative=1;uval=(unsigned int)(0-ival);}else uval=(unsigned int)ival; }
                    else { ival=va_arg(ap,int); uval=(unsigned int)ival; }
                    blen=0;
                    if (length_long) {
                        if (ulval==0) { if(prec!=0){buf[0]='0';blen=1;} }
                        else { vl=ulval;
                            if (spec=='x'||spec=='X'||spec=='o') { while(vl){ if(spec=='o'){d=vl%8;buf[blen]='0'+d;vl=vl/8;}else{d=vl%16;buf[blen]=(d<10)?'0'+d:((spec=='x')?'a'+d-10:'A'+d-10);vl=vl/16;} blen++; } }
                            else { while(vl){d=vl%10;buf[blen]='0'+d;blen++;vl=vl/10;} }
                            lo=0;hi=blen-1; while(lo<hi){tmp=buf[lo];buf[lo]=buf[hi];buf[hi]=tmp;lo++;hi--;}
                        }
                    } else if (uval==0) { if(prec!=0){buf[0]='0';blen=1;} }
                    else { v=uval;
                        if (spec=='x') { while(v){d=v&0xF;buf[blen]=(d<10)?'0'+d:'a'+d-10;blen++;v=v>>4;} }
                        else if (spec=='X') { while(v){d=v&0xF;buf[blen]=(d<10)?'0'+d:'A'+d-10;blen++;v=v>>4;} }
                        else if (spec=='o') { while(v){buf[blen]='0'+(v&7);blen++;v=v>>3;} }
                        else { while(v){buf[blen]='0'+v%10;blen++;v=v/10;} }
                        lo=0;hi=blen-1; while(lo<hi){tmp=buf[lo];buf[lo]=buf[hi];buf[hi]=tmp;lo++;hi--;}
                    }
                    plen=0;
                    if (negative){prefix[plen]='-';plen++;} else if(flag_plus){prefix[plen]='+';plen++;} else if(flag_space){prefix[plen]=' ';plen++;}
                    if (flag_hash){if(spec=='x'){prefix[plen]='0';plen++;prefix[plen]='x';plen++;}else if(spec=='X'){prefix[plen]='0';plen++;prefix[plen]='X';plen++;}else if(spec=='o'&&!(blen>0&&buf[0]=='0')){prefix[plen]='0';plen++;}}
                    zero_pad=0; if(prec>blen) zero_pad=prec-blen;
                    if (flag_left) flag_zero=0;
                    content_width=plen+zero_pad+blen; total_pad=width-content_width; if(total_pad<0)total_pad=0;
                    if (!flag_left&&!flag_zero){pad=total_pad;while(pad>0){term_putch(' ');n++;pad--;}}
                    pi=0; while(pi<plen){term_putch(prefix[pi]);n++;pi++;}
                    if (!flag_left&&flag_zero){pad=total_pad;while(pad>0){term_putch('0');n++;pad--;}}
                    zi=0; while(zi<zero_pad){term_putch('0');n++;zi++;}
                    bi=0; while(bi<blen){term_putch(buf[bi]);n++;bi++;}
                    if (flag_left){pad=total_pad;while(pad>0){term_putch(' ');n++;pad--;}}
                }
            }
        }
    }
    va_end(ap);
    return n;
}

/* ── vsnprintf / snprintf / sprintf ─────────────────────────────────────── */
/* vsnprintf writes at most size-1 chars to buf and always NUL-terminates.   */

static int vsnprintf(char *buf, int size, const char *fmt, va_list ap) {
    int n, rem;
    char *p;
    int flag_left, flag_zero, flag_plus, flag_space, flag_hash;
    int width, prec, spec, length_long, is_signed, negative;
    unsigned int uval; unsigned long ulval; unsigned long vl; long lval; int ival;
    int ibuf[20]; int prefix[4];
    int blen, plen, zero_pad, content_width, total_pad, pad;
    int lo, hi, bi, pi, zi, tmp, d;
    unsigned int v;
    const char *s; int slen;

#define _EMIT(c) do { if (rem > 0) { *p = (c); p++; rem--; } n++; } while (0)

    p = buf; rem = (size > 0) ? size - 1 : 0; n = 0;
    while (*fmt) {
        if (*fmt != '%') { _EMIT(*fmt); fmt++; }
        else {
            fmt++;
            flag_left=0; flag_zero=0; flag_plus=0; flag_space=0; flag_hash=0;
            while (*fmt=='-'||*fmt=='0'||*fmt=='+'||*fmt==' '||*fmt=='#') {
                if (*fmt=='-') flag_left=1;
                else if (*fmt=='0') flag_zero=1;
                else if (*fmt=='+') flag_plus=1;
                else if (*fmt==' ') flag_space=1;
                else if (*fmt=='#') flag_hash=1;
                fmt++;
            }
            width=0;
            while (*fmt>='0'&&*fmt<='9') { width=width*10+(*fmt-'0'); fmt++; }
            prec=-1;
            if (*fmt=='.') { fmt++; prec=0; while (*fmt>='0'&&*fmt<='9') { prec=prec*10+(*fmt-'0'); fmt++; } }
            length_long=0;
            if (*fmt=='l') { length_long=1; fmt++; }
            spec=*fmt; if (*fmt) fmt++;
            if (spec=='%') { _EMIT('%'); }
            else if (spec=='c') {
                ival=va_arg(ap,int);
                if (!flag_left) { pad=width-1; while(pad>0){_EMIT(' ');pad--;} }
                _EMIT(ival);
                if (flag_left) { pad=width-1; while(pad>0){_EMIT(' ');pad--;} }
            } else if (spec=='s') {
                s=va_arg(ap,char*); slen=0; while(s[slen]) slen++;
                if (prec>=0&&slen>prec) slen=prec;
                pad=width-slen;
                if (!flag_left) { while(pad>0){_EMIT(' ');pad--;} }
                bi=0; while(bi<slen){_EMIT(s[bi]);bi++;}
                if (flag_left) { while(pad>0){_EMIT(' ');pad--;} }
            } else if (spec=='d'||spec=='i'||spec=='u'||spec=='x'||spec=='X'||spec=='o') {
                is_signed=(spec=='d'||spec=='i'); negative=0;
                if (length_long&&is_signed) { lval=va_arg(ap,long); if(lval<0){negative=1;ulval=0-lval;}else ulval=lval; }
                else if (length_long) { ulval=va_arg(ap,unsigned long); }
                else if (is_signed) { ival=va_arg(ap,int); if(ival&0x8000){negative=1;uval=(unsigned int)(0-ival);}else uval=(unsigned int)ival; }
                else { ival=va_arg(ap,int); uval=(unsigned int)ival; }
                blen=0;
                if (length_long) {
                    if (ulval==0) { if(prec!=0){ibuf[0]='0';blen=1;} }
                    else { vl=ulval;
                        if (spec=='x'||spec=='X'||spec=='o') { while(vl){ if(spec=='o'){d=vl%8;ibuf[blen]='0'+d;vl=vl/8;}else{d=vl%16;ibuf[blen]=(d<10)?'0'+d:((spec=='x')?'a'+d-10:'A'+d-10);vl=vl/16;} blen++; } }
                        else { while(vl){d=vl%10;ibuf[blen]='0'+d;blen++;vl=vl/10;} }
                        lo=0;hi=blen-1; while(lo<hi){tmp=ibuf[lo];ibuf[lo]=ibuf[hi];ibuf[hi]=tmp;lo++;hi--;}
                    }
                } else if (uval==0) { if(prec!=0){ibuf[0]='0';blen=1;} }
                else { v=uval;
                    if (spec=='x') { while(v){d=v&0xF;ibuf[blen]=(d<10)?'0'+d:'a'+d-10;blen++;v=v>>4;} }
                    else if (spec=='X') { while(v){d=v&0xF;ibuf[blen]=(d<10)?'0'+d:'A'+d-10;blen++;v=v>>4;} }
                    else if (spec=='o') { while(v){ibuf[blen]='0'+(v&7);blen++;v=v>>3;} }
                    else { while(v){ibuf[blen]='0'+v%10;blen++;v=v/10;} }
                    lo=0;hi=blen-1; while(lo<hi){tmp=ibuf[lo];ibuf[lo]=ibuf[hi];ibuf[hi]=tmp;lo++;hi--;}
                }
                plen=0;
                if (negative){prefix[plen]='-';plen++;} else if(flag_plus){prefix[plen]='+';plen++;} else if(flag_space){prefix[plen]=' ';plen++;}
                if (flag_hash){if(spec=='x'){prefix[plen]='0';plen++;prefix[plen]='x';plen++;}else if(spec=='X'){prefix[plen]='0';plen++;prefix[plen]='X';plen++;}else if(spec=='o'&&!(blen>0&&ibuf[0]=='0')){prefix[plen]='0';plen++;}}
                zero_pad=0; if(prec>blen) zero_pad=prec-blen;
                if (flag_left) flag_zero=0;
                content_width=plen+zero_pad+blen; total_pad=width-content_width; if(total_pad<0)total_pad=0;
                if (!flag_left&&!flag_zero){pad=total_pad;while(pad>0){_EMIT(' ');pad--;}}
                pi=0; while(pi<plen){_EMIT(prefix[pi]);pi++;}
                if (!flag_left&&flag_zero){pad=total_pad;while(pad>0){_EMIT('0');pad--;}}
                zi=0; while(zi<zero_pad){_EMIT('0');zi++;}
                bi=0; while(bi<blen){_EMIT(ibuf[bi]);bi++;}
                if (flag_left){pad=total_pad;while(pad>0){_EMIT(' ');pad--;}}
            }
        }
    }
#undef _EMIT
    if (size > 0) *p = 0;
    return n;
}

static int snprintf(char *buf, int size, const char *fmt, ...) {
    va_list ap;
    int n;
    va_start(ap, fmt);
    n = vsnprintf(buf, size, fmt, ap);
    va_end(ap);
    return n;
}

static int sprintf(char *buf, const char *fmt, ...) {
    va_list ap;
    int n;
    va_start(ap, fmt);
    n = vsnprintf(buf, 32767, fmt, ap);
    va_end(ap);
    return n;
}

/* ── scanf ──────────────────────────────────────────────────────────────── */
/* Supports: %d %u %x %ld %lu %lx %c %s — no width/precision.              */
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
    unsigned long ulval;
    int *iptr;
    unsigned int *uptr;
    long *lptr;
    unsigned long *ulptr;
    char *sptr;
    int length_long;

    va_start(ap, fmt);
    assigned = 0;
    c = 0;

    while (*fmt) {
        if (*fmt == '%') {
            fmt++;
            length_long = 0;
            if (*fmt == 'l') {
                length_long = 1;
                fmt++;
            }
            if (*fmt == 'd' || *fmt == 'u' || *fmt == 'x') {
                /* skip leading whitespace */
                if (c == 0) c = _cooked_getch();
                while (_is_space(c)) c = _cooked_getch();

                if (*fmt == 'x') {
                    uval = 0;
                    ulval = 0;
                    if (!_is_xdigit(c)) { fmt++; continue; }
                    while (_is_xdigit(c)) {
                        if (length_long) {
                            ulval = ulval * 16 + _xdigit_val(c);
                        } else {
                            uval = uval * 16 + _xdigit_val(c);
                        }
                        c = _cooked_getch();
                    }
                    if (length_long) {
                        ulptr = va_arg(ap, unsigned long *);
                        *ulptr = ulval;
                    } else {
                        uptr = va_arg(ap, unsigned int *);
                        *uptr = uval;
                    }
                    assigned++;
                } else if (*fmt == 'u') {
                    uval = 0;
                    ulval = 0;
                    if (!_is_digit(c)) { fmt++; continue; }
                    while (_is_digit(c)) {
                        if (length_long) {
                            ulval = ulval * 10 + (c - '0');
                        } else {
                            uval = uval * 10 + (c - '0');
                        }
                        c = _cooked_getch();
                    }
                    if (length_long) {
                        ulptr = va_arg(ap, unsigned long *);
                        *ulptr = ulval;
                    } else {
                        uptr = va_arg(ap, unsigned int *);
                        *uptr = uval;
                    }
                    assigned++;
                } else {
                    neg = 0;
                    if (c == '-') { neg = 1; c = _cooked_getch(); }
                    uval = 0;
                    ulval = 0;
                    if (!_is_digit(c)) { fmt++; continue; }
                    while (_is_digit(c)) {
                        if (length_long) {
                            ulval = ulval * 10 + (c - '0');
                        } else {
                            uval = uval * 10 + (c - '0');
                        }
                        c = _cooked_getch();
                    }
                    if (length_long) {
                        lptr = va_arg(ap, long *);
                        if (neg) {
                            *lptr = 0 - ulval;
                        } else {
                            *lptr = ulval;
                        }
                    } else {
                        iptr = va_arg(ap, int *);
                        if (neg) {
                            *iptr = 0 - uval;
                        } else {
                            *iptr = uval;
                        }
                    }
                    assigned++;
                }
                fmt++;
            } else if (*fmt == 'c') {
                if (c == 0) c = _cooked_getch();
                iptr = va_arg(ap, int *);
                *iptr = c;
                c = 0;
                assigned++;
                fmt++;
            } else if (*fmt == 's') {
                if (c == 0) c = _cooked_getch();
                while (_is_space(c)) c = _cooked_getch();
                sptr = va_arg(ap, char *);
                while (c != 0 && !_is_space(c)) {
                    *sptr = c;
                    sptr++;
                    c = _cooked_getch();
                }
                *sptr = 0;
                assigned++;
                fmt++;
            } else {
                fmt++;
            }
        } else if (_is_space(*fmt)) {
            if (c == 0) c = _cooked_getch();
            while (_is_space(c)) c = _cooked_getch();
            fmt++;
        } else {
            if (c == 0) c = _cooked_getch();
            if (c != *fmt) break;
            c = 0;
            fmt++;
        }
    }

    va_end(ap);
    return assigned;
}

/* ── fscanf ─────────────────────────────────────────────────────────────── */

static int fscanf(FILE *stream, const char *fmt, ...) {
    va_list ap;
    int assigned;
    int c;
    int neg;
    unsigned int uval;
    unsigned long ulval;
    int *iptr;
    unsigned int *uptr;
    long *lptr;
    unsigned long *ulptr;
    char *sptr;
    int length_long;
    (void)stream;

    va_start(ap, fmt);
    assigned = 0;
    c = 0;

    while (*fmt) {
        if (*fmt == '%') {
            fmt++;
            length_long = 0;
            if (*fmt == 'l') {
                length_long = 1;
                fmt++;
            }
            if (*fmt == 'd' || *fmt == 'u' || *fmt == 'x') {
                if (c == 0) c = _cooked_getch();
                while (_is_space(c)) c = _cooked_getch();
                if (*fmt == 'x') {
                    uval = 0; ulval = 0;
                    if (!_is_xdigit(c)) { fmt++; continue; }
                    while (_is_xdigit(c)) { if(length_long){ulval=ulval*16+_xdigit_val(c);}else{uval=uval*16+_xdigit_val(c);} c = _cooked_getch(); }
                    if(length_long){ulptr=va_arg(ap,unsigned long *);*ulptr=ulval;}else{uptr = va_arg(ap, unsigned int *); *uptr = uval;} assigned++;
                } else if (*fmt == 'u') {
                    uval = 0; ulval = 0;
                    if (!_is_digit(c)) { fmt++; continue; }
                    while (_is_digit(c)) { if(length_long){ulval=ulval*10+(c-'0');}else{uval=uval*10+(c-'0');} c = _cooked_getch(); }
                    if(length_long){ulptr=va_arg(ap,unsigned long *);*ulptr=ulval;}else{uptr = va_arg(ap, unsigned int *); *uptr = uval;} assigned++;
                } else {
                    neg = 0;
                    if (c == '-') { neg = 1; c = _cooked_getch(); }
                    uval = 0; ulval = 0;
                    if (!_is_digit(c)) { fmt++; continue; }
                    while (_is_digit(c)) { if(length_long){ulval=ulval*10+(c-'0');}else{uval=uval*10+(c-'0');} c = _cooked_getch(); }
                    if(length_long){lptr=va_arg(ap,long *);if(neg){*lptr=0-ulval;}else{*lptr=ulval;}}
                    else{iptr = va_arg(ap, int *); *iptr = neg ? (int)(0 - uval) : (int)uval;}
                    assigned++;
                }
                fmt++;
            } else if (*fmt == 'c') {
                if (c == 0) c = _cooked_getch();
                iptr = va_arg(ap, int *); *iptr = c; c = 0; assigned++; fmt++;
            } else if (*fmt == 's') {
                if (c == 0) c = _cooked_getch();
                while (_is_space(c)) c = _cooked_getch();
                sptr = va_arg(ap, char *);
                while (c != 0 && !_is_space(c)) { *sptr = c; sptr++; c = _cooked_getch(); }
                *sptr = 0; assigned++; fmt++;
            } else {
                fmt++;
            }
        } else if (_is_space(*fmt)) {
            if (c == 0) c = _cooked_getch();
            while (_is_space(c)) c = _cooked_getch();
            fmt++;
        } else {
            if (c == 0) c = _cooked_getch();
            if (c != *fmt) break;
            c = 0; fmt++;
        }
    }

    va_end(ap);
    return assigned;
}

#endif /* STDIO_H */

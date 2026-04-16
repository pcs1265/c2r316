/*
 * r316.h — Standard header for C→R316 programs
 *
 * Include this at the top of your source file to get:
 *   - All runtime function declarations
 *   - Common type aliases (bool, NULL, etc.)
 *   - Useful macros (ABS, MIN, MAX, CLAMP, ...)
 *   - Terminal constants (screen size, colours)
 *
 * Usage:
 *   #include "runtime/r316.h"
 */

#ifndef R316_H
#define R316_H

/* ── Type aliases ────────────────────────────────────────────────────────── */

typedef int           bool;
typedef unsigned int  uint;
typedef char*         string;

#define true  1
#define false 0
#define NULL  0

/* ── Terminal constants ──────────────────────────────────────────────────── */

#define SCREEN_W   12   /* terminal width  (columns) */
#define SCREEN_H    8   /* terminal height (rows)    */

/* Colour byte: high nibble = background, low nibble = foreground
 * Nibble values: 0=black 1=grey 2=white 3=maroon 4=red 5=orange
 *                6=yellow 7=lime 8=green 9=teal A=cyan B=navy
 *                C=blue D=purple E=magenta F=pink               */
#define COLOR_GREEN_ON_BLACK  0x0A
#define COLOR_WHITE_ON_BLACK  0x02
#define COLOR_RED_ON_BLACK    0x04
#define COLOR_CYAN_ON_BLACK   0x0C

/* ── Math macros ─────────────────────────────────────────────────────────── */

#define ABS(x)          ((x) < 0 ? -(x) : (x))
#define MIN(a, b)       ((a) < (b) ? (a) : (b))
#define MAX(a, b)       ((a) > (b) ? (a) : (b))
#define CLAMP(v, lo, hi) ((v) < (lo) ? (lo) : (v) > (hi) ? (hi) : (v))

/* ── Output ──────────────────────────────────────────────────────────────── */

/* Print a single character */
int  putchar(int c);

/* Print a string followed by a newline */
void puts(char *s);

/* Print a string (no newline) */
void print_str(char *s);

/* Print a signed integer */
void print_int(int n);

/* Print an unsigned integer */
void print_uint(unsigned int n);

/* Print a 4-digit uppercase hex value */
void print_hex(unsigned int n);

/* Formatted output — supports: %d %u %x %s %c %% */
void printf(char *fmt, ...);

/* ── Input ───────────────────────────────────────────────────────────────── */

/* Wait for a key press and return its character code */
int  getchar(void);

/* ── String / Memory ─────────────────────────────────────────────────────── */

int  strlen(char *s);
int  strcmp(char *a, char *b);        /* 0 = equal, >0 = a>b, <0 = a<b */
void memcpy(char *dst, char *src, int n);
void memset(char *dst, int val, int n);

/* ── Variadic helpers (compiler intrinsics) ──────────────────────────────── */

void va_start(int *ap, int last);
int  va_arg(int *ap, int type);
void va_end(int *ap);

#endif /* R316_H */

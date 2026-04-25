/*
 * stdlib.h — C standard library for the R316 C compiler
 *
 * Provides memory, string, and division utilities.
 * For I/O functions (printf, puts, etc.) include runtime/stdio.h.
 *
 * Functions kept in runtime.asm:
 *   __stack_init        — boot: detect RAM size, set SP
 *   __term_init         — boot: configure terminal geometry/colour
 */

#ifndef STDLIB_H
#define STDLIB_H

#include "runtime/divmod.h"

/* ── memset / memcpy ────────────────────────────────────────────────────── */

static void memset(char *dst, int val, int n) {
    if (n == 0) return;
    asm(".memset_loop:\n"
        "st %1, %0, 0\n"
        "add %0, 1\n"
        "sub %2, 1\n"
        "jnz .memset_loop"
        : "r"(dst), "r"(val), "r"(n));
}

static void memcpy(char *dst, char *src, int n) {
    if (n == 0) return;
    asm(".memcpy_loop:\n"
        "ld r10, %1, 0\n"
        "st r10, %0, 0\n"
        "add %0, 1\n"
        "add %1, 1\n"
        "sub %2, 1\n"
        "jnz .memcpy_loop"
        : "r"(dst), "r"(src), "r"(n));
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

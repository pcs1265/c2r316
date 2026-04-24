/*
 * stdlib.h — C standard library for the R316 C compiler
 *
 * Auto-prepended to every compilation unit by compiler.py.
 * Do not #include manually.
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
    unsigned int res;
    asm(
        "mov r10, 0\n"
        "mov r11, 16\n"
        "._udiv_loop:\n"
        "add %0, %0\n"
        "adc r10, r10\n"
        "sub r12, r10, %1\n"
        "jc ._udiv_skip\n"
        "mov r10, r12\n"
        "or %0, 1\n"
        "._udiv_skip:\n"
        "sub r11, 1\n"
        "jnz ._udiv_loop\n"
        "st %0, %2"
        : "r"(dividend), "r"(divisor), "r"(&res)
    );
    return res;
}

static int __umod(unsigned int dividend, unsigned int divisor) {
    unsigned int res;
    asm(
        "mov r10, 0\n"
        "mov r11, 16\n"
        "._umod_loop:\n"
        "add %0, %0\n"
        "adc r10, r10\n"
        "sub r12, r10, %1\n"
        "jc ._umod_skip\n"
        "mov r10, r12\n"
        "._umod_skip:\n"
        "sub r11, 1\n"
        "jnz ._umod_loop\n"
        "st r10, %2"
        : "r"(dividend), "r"(divisor), "r"(&res)
    );
    return res;
}

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

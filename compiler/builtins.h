/*
 * builtins.h — compiler built-in helpers for the R316 C compiler
 *
 * Auto-prepended to every compilation unit by compiler.py.
 * Do not #include manually.
 *
 * All symbols use the __builtin_ prefix (compiler-owned namespace).
 * Unused helpers are eliminated by DCE.
 */

#ifndef BUILTINS_H
#define BUILTINS_H

/* ── Integer division / modulo ──────────────────────────────────────────── */

static unsigned int __builtin_udiv(unsigned int dividend, unsigned int divisor) {
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

static unsigned int __builtin_umod(unsigned int dividend, unsigned int divisor) {
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

static int __builtin_sdiv(int dividend, int divisor) {
    int neg;
    unsigned int udividend;
    unsigned int udivisor;
    unsigned int uresult;
    neg = 0;
    if (dividend & 0x8000) {
        dividend = 0 - dividend;
        neg = neg ^ 1;
    }
    if (divisor & 0x8000) {
        divisor = 0 - divisor;
        neg = neg ^ 1;
    }
    udividend = dividend;
    udivisor = divisor;
    uresult = __builtin_udiv(udividend, udivisor);
    if (neg) {
        return 0 - uresult;
    }
    return uresult;
}

static int __builtin_smod(int dividend, int divisor) {
    int neg;
    unsigned int udividend;
    unsigned int udivisor;
    unsigned int uresult;
    neg = 0;
    if (dividend & 0x8000) {
        dividend = 0 - dividend;
        neg = 1;
    }
    if (divisor & 0x8000) {
        divisor = 0 - divisor;
    }
    udividend = dividend;
    udivisor = divisor;
    uresult = __builtin_umod(udividend, udivisor);
    if (neg) {
        return 0 - uresult;
    }
    return uresult;
}

#endif /* BUILTINS_H */

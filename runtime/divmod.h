/*
 * divmod.h — integer division/modulo helpers for the R316 C compiler
 *
 * __udiv/__umod/__sdiv/__smod are emitted by the compiler for / and %
 * expressions.  Included by stdio.h and stdlib.h so they are available
 * whenever either standard header is in use.  Subject to DCE — only
 * the helpers actually called survive into the final binary.
 */

#ifndef DIVMOD_H
#define DIVMOD_H

static unsigned int __udiv(unsigned int dividend, unsigned int divisor) {
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

static unsigned int __umod(unsigned int dividend, unsigned int divisor) {
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

static int __sdiv(int dividend, int divisor) {
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
    uresult = __udiv(udividend, udivisor);
    if (neg) {
        return 0 - uresult;
    }
    return uresult;
}

static int __smod(int dividend, int divisor) {
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
    uresult = __umod(udividend, udivisor);
    if (neg) {
        return 0 - uresult;
    }
    return uresult;
}

#endif /* DIVMOD_H */

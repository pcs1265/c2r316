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
        :
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
        :
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

/* ── Long multiply / division / modulo ──────────────────────────────────── */

static unsigned long __builtin_ulmake(unsigned int lo, unsigned int hi) {
    unsigned long result;
    unsigned int *words;
    words = (unsigned int *)&result;
    words[0] = lo;
    words[1] = hi;
    return result;
}

static unsigned int __builtin_umulh(unsigned int left, unsigned int right) {
    unsigned int result;
    asm(
        "mulh %0, %1, %2"
        : "=r"(result)
        : "r"(left), "r"(right)
    );
    return result;
}

static unsigned long __builtin_ulmul(unsigned long left, unsigned long right) {
    unsigned int *lwords;
    unsigned int *rwords;
    unsigned int lo;
    unsigned int hi;
    lwords = (unsigned int *)&left;
    rwords = (unsigned int *)&right;
    lo = lwords[0] * rwords[0];
    hi = __builtin_umulh(lwords[0], rwords[0]);
    hi = hi + lwords[0] * rwords[1];
    hi = hi + lwords[1] * rwords[0];
    return __builtin_ulmake(lo, hi);
}

static unsigned long __builtin_ulshr1(unsigned long value) {
    unsigned int *words;
    unsigned int lo;
    unsigned int hi;
    words = (unsigned int *)&value;
    lo = words[0];
    hi = words[1];
    lo = (lo >> 1) | ((hi & 1) << 15);
    hi = hi >> 1;
    words[0] = lo;
    words[1] = hi;
    return value;
}

static unsigned long __builtin_uldiv(unsigned long dividend, unsigned long divisor) {
    unsigned long quotient;
    unsigned long bit;
    quotient = 0;
    bit = 1;
    if (divisor == 0) {
        return 0;
    }
    while (divisor <= dividend && divisor <= 0x7FFFFFFF) {
        divisor = divisor + divisor;
        bit = bit + bit;
    }
    while (bit != 0) {
        if (dividend >= divisor) {
            dividend = dividend - divisor;
            quotient = quotient + bit;
        }
        divisor = __builtin_ulshr1(divisor);
        bit = __builtin_ulshr1(bit);
    }
    return quotient;
}

static unsigned long __builtin_ulmod(unsigned long dividend, unsigned long divisor) {
    unsigned long bit;
    bit = 1;
    if (divisor == 0) {
        return 0;
    }
    while (divisor <= dividend && divisor <= 0x7FFFFFFF) {
        divisor = divisor + divisor;
        bit = bit + bit;
    }
    while (bit != 0) {
        if (dividend >= divisor) {
            dividend = dividend - divisor;
        }
        divisor = __builtin_ulshr1(divisor);
        bit = __builtin_ulshr1(bit);
    }
    return dividend;
}

static long __builtin_sldiv(long dividend, long divisor) {
    int neg;
    unsigned long udividend;
    unsigned long udivisor;
    unsigned long uresult;
    neg = 0;
    if (dividend < 0) {
        dividend = 0 - dividend;
        neg = neg ^ 1;
    }
    if (divisor < 0) {
        divisor = 0 - divisor;
        neg = neg ^ 1;
    }
    udividend = dividend;
    udivisor = divisor;
    uresult = __builtin_uldiv(udividend, udivisor);
    if (neg) {
        return 0 - uresult;
    }
    return uresult;
}

static long __builtin_slmod(long dividend, long divisor) {
    int neg;
    unsigned long udividend;
    unsigned long udivisor;
    unsigned long uresult;
    neg = 0;
    if (dividend < 0) {
        dividend = 0 - dividend;
        neg = 1;
    }
    if (divisor < 0) {
        divisor = 0 - divisor;
    }
    udividend = dividend;
    udivisor = divisor;
    uresult = __builtin_ulmod(udividend, udivisor);
    if (neg) {
        return 0 - uresult;
    }
    return uresult;
}

#endif /* BUILTINS_H */

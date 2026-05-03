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
        "add %1, %1\n"
        "adc r10, r10\n"
        "sub r12, r10, %2\n"
        "jc ._udiv_skip\n"
        "mov r10, r12\n"
        "or %1, 1\n"
        "._udiv_skip:\n"
        "sub r11, 1\n"
        "jnz ._udiv_loop\n"
        "add %0, %1, r0"
        : "=r"(res)
        : "r"(dividend), "r"(divisor)
        : "r10", "r11", "r12"
    );
    return res;
}

static unsigned int __builtin_umod(unsigned int dividend, unsigned int divisor) {
    unsigned int res;
    asm(
        "mov r10, 0\n"
        "mov r11, 16\n"
        "._umod_loop:\n"
        "add %1, %1\n"
        "adc r10, r10\n"
        "sub r12, r10, %2\n"
        "jc ._umod_skip\n"
        "mov r10, r12\n"
        "._umod_skip:\n"
        "sub r11, 1\n"
        "jnz ._umod_loop\n"
        "add %0, r10, r0"
        : "=r"(res)
        : "r"(dividend), "r"(divisor)
        : "r10", "r11", "r12"
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
    unsigned long result;
    unsigned int *dwords;
    unsigned int *vwords;
    unsigned int *rwords;
    dwords = (unsigned int *)&dividend;
    vwords = (unsigned int *)&divisor;
    rwords = (unsigned int *)&result;
    asm(
        "mov r15, %2\n"
        "or r15, %3\n"
        "jnz ._uldiv_nonzero\n"
        "st r0, %4\n"
        "st r0, %5\n"
        "jmp ._uldiv_done\n"
        "._uldiv_nonzero:\n"
        "mov r13, 0\n"
        "mov r14, 0\n"
        "mov r17, 32\n"
        "._uldiv_loop:\n"
        "add %0, %0\n"
        "adc %1, %1\n"
        "adc r13, r13\n"
        "adc r14, r14\n"
        "sub r15, r13, %2\n"
        "sbb r16, r14, %3\n"
        "jc ._uldiv_skip\n"
        "mov r13, r15\n"
        "mov r14, r16\n"
        "or %0, 1\n"
        "._uldiv_skip:\n"
        "sub r17, 1\n"
        "jnz ._uldiv_loop\n"
        "st %0, %4\n"
        "st %1, %5\n"
        "._uldiv_done:"
        :
        : "r"(dwords[0]), "r"(dwords[1]), "r"(vwords[0]), "r"(vwords[1]),
          "r"(&rwords[0]), "r"(&rwords[1])
        : "r13", "r14", "r15", "r16", "r17"
    );
    return result;
}

static unsigned long __builtin_ulmod(unsigned long dividend, unsigned long divisor) {
    unsigned long result;
    unsigned int *dwords;
    unsigned int *vwords;
    unsigned int *rwords;
    dwords = (unsigned int *)&dividend;
    vwords = (unsigned int *)&divisor;
    rwords = (unsigned int *)&result;
    asm(
        "mov r15, %2\n"
        "or r15, %3\n"
        "jnz ._ulmod_nonzero\n"
        "st r0, %4\n"
        "st r0, %5\n"
        "jmp ._ulmod_done\n"
        "._ulmod_nonzero:\n"
        "mov r13, 0\n"
        "mov r14, 0\n"
        "mov r17, 32\n"
        "._ulmod_loop:\n"
        "add %0, %0\n"
        "adc %1, %1\n"
        "adc r13, r13\n"
        "adc r14, r14\n"
        "sub r15, r13, %2\n"
        "sbb r16, r14, %3\n"
        "jc ._ulmod_skip\n"
        "mov r13, r15\n"
        "mov r14, r16\n"
        "._ulmod_skip:\n"
        "sub r17, 1\n"
        "jnz ._ulmod_loop\n"
        "st r13, %4\n"
        "st r14, %5\n"
        "._ulmod_done:"
        :
        : "r"(dwords[0]), "r"(dwords[1]), "r"(vwords[0]), "r"(vwords[1]),
          "r"(&rwords[0]), "r"(&rwords[1])
        : "r13", "r14", "r15", "r16", "r17"
    );
    return result;
}

static unsigned int __builtin_uldivmod10(unsigned long dividend, unsigned long *quotient) {
    unsigned int rem;
    unsigned int *dwords;
    unsigned int *qwords;
    dwords = (unsigned int *)&dividend;
    qwords = (unsigned int *)quotient;
    asm(
        "mov r13, 0\n"
        "mov r14, 0\n"
        "mov r17, 32\n"
        "._uldivmod10_loop:\n"
        "add %1, %1\n"
        "adc %2, %2\n"
        "adc r13, r13\n"
        "adc r14, r14\n"
        "sub r15, r13, 10\n"
        "sbb r16, r14, r0\n"
        "jc ._uldivmod10_skip\n"
        "mov r13, r15\n"
        "mov r14, r16\n"
        "or %1, 1\n"
        "._uldivmod10_skip:\n"
        "sub r17, 1\n"
        "jnz ._uldivmod10_loop\n"
        "st %1, %3\n"
        "st %2, %4\n"
        "add %0, r13, r0"
        : "=r"(rem)
        : "r"(dwords[0]), "r"(dwords[1]), "r"(&qwords[0]), "r"(&qwords[1])
        : "r13", "r14", "r15", "r16", "r17"
    );
    return rem;
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

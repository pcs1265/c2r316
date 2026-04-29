/*
 * test_asm.c
 *
 * Verifies inline-asm code generation and register-allocation correctness.
 * Tests are grouped by scenario:
 *
 *   A. Basic asm mechanics (original suite)
 *   B. Many-operand asm — exercises clobber tracking for r10-r13+
 *   C. Value live across multi-operand asm — catches wrong reg assignment
 *   D. Asm inside a loop — temps from loop variables cross asm sites
 *   E. Asm + function call in the same function — both crossing types
 *   F. Consecutive asm statements — per-site forbidden sets
 *
 * Terminal memory map (from runtime.asm):
 *   0x9FB5 : term_term  (character output)
 */

#include <stdlib.h>
#include <stdio.h>

int pass_count;
int fail_count;

void check(char *name, int got, int expected) {
    if (got == expected) {
        print_str(name);
        puts(": PASS");
        pass_count = pass_count + 1;
    } else {
        print_str(name);
        print_str(": FAIL got=");
        print_int(got);
        print_str(" exp=");
        print_int(expected);
        putchar(10);
        fail_count = fail_count + 1;
    }
}

/* ── A. Basic asm mechanics ──────────────────────────────────────────────── */

void asm_putchar(int c) {
    asm("st %0, 0x9FB5" : "r"(c));
}

void asm_memset(int *dst, int val, int n) {
    int i;
    for (i = 0; i < n; i++) dst[i] = val;
}

void asm_memcpy(int *dst, int *src, int n) {
    int i;
    for (i = 0; i < n; i++) dst[i] = src[i];
}

int asm_strlen(char *s) {
    int n;
    n = 0;
    while (s[n] != 0) n = n + 1;
    return n;
}

int asm_strcmp(char *a, char *b) {
    int i;
    i = 0;
    while (1) {
        int ca; int cb;
        ca = a[i]; cb = b[i];
        if (ca != cb) return ca - cb;
        if (ca == 0)  return 0;
        i = i + 1;
    }
    return 0;
}

/* 2-operand asm (%0,%1 → r7,r8): clobbers r7,r8 — both scratch, no allocatable regs */
void asm_add(int a, int b, int *out) {
    asm("add %0, %1\nst %0, %2" : "r"(a), "r"(b), "r"(out));
}

/* 4-operand asm (%0..%3 → r7..r10): clobbers r7-r10, includes allocatable r10 */
void asm_multiline(int a, int b, int c, int *out) {
    asm("add %0, %1\n"
        "mul %0, %0, %2\n"
        "st %0, %3"
        : "r"(a), "r"(b), "r"(c), "r"(out));
}

/* ── B. Many-operand asm ─────────────────────────────────────────────────── */

/*
 * 5-operand asm (%0..%4 → r7..r11): clobbers r7-r11.
 * Allocatable regs r10, r11 are in the clobber set.
 * Computes a*w1 + b*w2.
 */
void asm_weighted_sum(int a, int w1, int b, int w2, int *out) {
    asm("mul %0, %0, %1\n"
        "mul %2, %2, %3\n"
        "add %0, %2\n"
        "st %0, %4"
        : "r"(a), "r"(w1), "r"(b), "r"(w2), "r"(out));
}

/*
 * 7-operand asm (%0..%6 → r7..r13): clobbers r7-r13.
 * Allocatable regs r10-r13 are all in the clobber set.
 * Computes a+b+c+d+e+f and stores to *out.
 */
void asm_sum6(int a, int b, int c, int d, int e, int f, int *out) {
    asm("add %0, %1\n"
        "add %0, %2\n"
        "add %0, %3\n"
        "add %0, %4\n"
        "add %0, %5\n"
        "st %0, %6"
        : "r"(a), "r"(b), "r"(c), "r"(d), "r"(e), "r"(f), "r"(out));
}

/* ── C. Value live across multi-operand asm ──────────────────────────────── */

/*
 * Computes pre = a+b, runs a 4-operand asm that clobbers r10, then uses pre.
 * If pre's temp were (wrongly) allocated to r10, it would be overwritten by
 * loading %3=c into r10, corrupting the return value.
 *
 * Returns pre + asm_result  =  (a+b) + (a+b+c)  =  2*(a+b) + c.
 */
int live_across_4op_asm(int a, int b, int c) {
    int pre;
    int asm_result;
    int *p = &asm_result;
    pre = a + b;
    /* 4-operand asm: %0=a(r7), %1=b(r8), %2=c(r9), %3=&asm_result(r10) */
    asm("add %0, %1\n"
        "add %0, %2\n"
        "st %0, %3"
        : "r"(a), "r"(b), "r"(c), "r"(p));
    return pre + asm_result;
}

/*
 * Same idea with a 7-operand asm (clobbers r7-r13).
 * Any temp allocated to r10-r13 that lives across the asm would be corrupted.
 *
 * Returns pre + asm_result  =  (a+b) + (a+b+c+d+e+f)  =  2*(a+b)+c+d+e+f.
 */
int live_across_7op_asm(int a, int b, int c, int d, int e, int f) {
    int pre;
    int asm_result;
    int *p = &asm_result;
    pre = a + b;
    /* 7-operand asm: %0..%5=values(r7..r12), %6=&asm_result(r13) */
    asm("add %0, %1\n"
        "add %0, %2\n"
        "add %0, %3\n"
        "add %0, %4\n"
        "add %0, %5\n"
        "st %0, %6"
        : "r"(a), "r"(b), "r"(c), "r"(d), "r"(e), "r"(f), "r"(p));
    return pre + asm_result;
}

/* ── D. Asm inside a loop ────────────────────────────────────────────────── */

/*
 * Accumulates sum = 0+1+2+...+(n-1) using a 3-operand asm in the loop body.
 * The loop variable i and running sum are live across each asm invocation.
 * Clobbers: r7(%0), r8(%1), r9(%2) — all scratch; loop vars should be safe.
 * But if the allocator is confused about asm sites inside loops, it may
 * produce wrong results.
 */
int asm_accumulate(int n) {
    int sum;
    int i;
    sum = 0;
    for (i = 0; i < n; i++) {
        int tmp;
        int *ptmp = &tmp;
        asm("add %0, %1\nst %0, %2" : "r"(sum), "r"(i), "r"(ptmp));
        sum = tmp;
    }
    return sum;  /* n*(n-1)/2 */
}

/*
 * Same loop but with a 5-operand asm (clobbers r7-r11, allocatable r10,r11).
 * Doubles each element of arr in-place using asm.
 */
void asm_double_array(int *arr, int n) {
    int i;
    for (i = 0; i < n; i++) {
        int val;
        int doubled;
        val = arr[i];
        int *pdoubled = &doubled;
        /* 3-operand asm: %0=val(r7), %1=val(r8), %2=&doubled(r9) */
        asm("add %0, %1\nst %0, %2" : "r"(val), "r"(val), "r"(pdoubled));
        arr[i] = doubled;
    }
}

/* ── E. Asm + function call in the same function ─────────────────────────── */

/*
 * A helper called from within asm_call_mix — forces a genuine call site
 * so the allocator must handle both call-crossing and asm-crossing.
 */
int square(int x) { return x * x; }

/*
 * Computes sq = square(a), then runs a 4-operand asm, then uses sq again.
 * sq's temp crosses both a call site (square) and (potentially) the asm site.
 * Without proper handling of both crossings, sq would be corrupted.
 *
 * Returns sq + asm_result  =  a^2 + (b+c).
 */
int asm_call_mix(int a, int b, int c) {
    int sq;
    int asm_result;
    int *p = &asm_result;
    sq = square(a);
    /* 4-operand asm: %0=b(r7), %1=c(r8), %2=b(r9), %3=&asm_result(r10) */
    asm("add %0, %1\n"
        "st %0, %3"
        : "r"(b), "r"(c), "r"(b), "r"(p));
    return sq + asm_result;
}

/*
 * Call AFTER asm: the call-crossing fix (start < ci < end, strictly).
 * A temp whose last use IS a function call does not need a callee-saved reg.
 * This is a correctness + efficiency check — the result must be right.
 */
int asm_then_call(int a, int b) {
    int asm_result;
    int *p = &asm_result;
    /* 3-operand asm */
    asm("add %0, %1\nst %0, %2" : "r"(a), "r"(b), "r"(p));
    return square(asm_result);   /* last use of asm_result IS the call arg */
}

/* ── F. Consecutive asm statements ──────────────────────────────────────── */

/*
 * Two back-to-back asm statements — tests per-site forbidden-set computation.
 * A temp live between the two asm sites must avoid both clobber sets.
 *
 * Step 1 (3-operand asm): r1_val = a + b
 * Step 2 (3-operand asm): result = r1_val * c
 * Returns (a+b)*c.
 */
int asm_two_steps(int a, int b, int c) {
    int r1_val;
    int result;
    int *p1 = &r1_val;
    int *p2 = &result;
    asm("add %0, %1\nst %0, %2" : "r"(a), "r"(b), "r"(p1));
    asm("mul %0, %0, %1\nst %0, %2" : "r"(r1_val), "r"(c), "r"(p2));
    return result;
}

/*
 * Three asm statements each with growing operand counts.
 * step1 (2-op): t = a+b      clobbers r7,r8
 * step2 (4-op): u = t*c      clobbers r7-r10
 * step3 (5-op): v = u+d+e    clobbers r7-r11
 * Returns (a+b)*c + d + e.
 */
int asm_three_steps(int a, int b, int c, int d, int e) {
    int t;
    int u;
    int v;
    int *pt = &t;
    int *pu = &u;
    int *pv = &v;
    asm("add %0, %1\nst %0, %2"
        : "r"(a), "r"(b), "r"(pt));
    asm("mul %0, %0, %1\nst %0, %3"
        : "r"(t), "r"(c), "r"(t), "r"(pu));
    asm("add %0, %1\n"
        "add %0, %2\n"
        "st %0, %3"
        : "r"(u), "r"(d), "r"(e), "r"(pv));
    return v;
}

/* ── main ────────────────────────────────────────────────────────────────── */

int main(void) {
    pass_count = 0;
    fail_count = 0;

    print_str("=== test_asm ===\n");

    /* A. Basic mechanics */
    print_str("asm_putchar: ");
    asm_putchar('O'); asm_putchar('K'); asm_putchar(10);

    check("strlen_hello",  asm_strlen("hello"), 5);
    check("strlen_empty",  asm_strlen(""),       0);
    check("strlen_one",    asm_strlen("x"),      1);

    check("strcmp_eq",     asm_strcmp("abc", "abc"),  0);
    check("strcmp_lt",     asm_strcmp("abc", "abd") < 0, 1);
    check("strcmp_gt",     asm_strcmp("abd", "abc") > 0, 1);
    check("strcmp_prefix", asm_strcmp("ab",  "abc") < 0, 1);

    int buf[4];
    buf[0] = 1; buf[1] = 2; buf[2] = 3; buf[3] = 4;
    asm_memset(buf, 7, 4);
    check("memset[0]", buf[0], 7);
    check("memset[1]", buf[1], 7);
    check("memset[2]", buf[2], 7);
    check("memset[3]", buf[3], 7);

    int src[3]; int dst[3];
    src[0] = 10; src[1] = 20; src[2] = 30;
    dst[0] =  0; dst[1] =  0; dst[2] =  0;
    asm_memcpy(dst, src, 3);
    check("memcpy[0]", dst[0], 10);
    check("memcpy[1]", dst[1], 20);
    check("memcpy[2]", dst[2], 30);

    int result;
    result = 0;
    asm_add(12, 30, &result);
    check("asm_add", result, 42);

    result = 0;
    asm_multiline(10, 20, 3, &result);
    check("asm_multiline", result, 90);

    /* B. Many-operand asm */
    result = 0;
    asm_weighted_sum(3, 4, 5, 6, &result);
    check("weighted_sum", result, 42);   /* 3*4 + 5*6 = 12+30 = 42 */

    result = 0;
    asm_sum6(1, 2, 3, 4, 5, 6, &result);
    check("asm_sum6", result, 21);       /* 1+2+3+4+5+6 = 21 */

    /* C. Value live across multi-operand asm */
    /*  live_across_4op_asm(3,4,5): pre=7, asm_result=12 → 7+12=19 */
    check("live_across_4op", live_across_4op_asm(3, 4, 5), 19);

    /*  live_across_7op_asm(1,2,3,4,5,6): pre=3, asm_result=21 → 24 */
    check("live_across_7op", live_across_7op_asm(1, 2, 3, 4, 5, 6), 24);

    /* D. Asm inside a loop */
    check("accumulate_0",  asm_accumulate(0),  0);
    check("accumulate_1",  asm_accumulate(1),  0);
    check("accumulate_5",  asm_accumulate(5),  10);
    check("accumulate_10", asm_accumulate(10), 45);

    int arr[4];
    arr[0] = 3; arr[1] = 7; arr[2] = 1; arr[3] = 5;
    asm_double_array(arr, 4);
    check("double_arr[0]", arr[0],  6);
    check("double_arr[1]", arr[1], 14);
    check("double_arr[2]", arr[2],  2);
    check("double_arr[3]", arr[3], 10);

    /* E. Asm + call in same function */
    /* asm_call_mix(3,5,7): sq=9, asm_result=12 → 9+12=21 */
    check("asm_call_mix",  asm_call_mix(3, 5, 7),  21);
    /* asm_then_call(4,6): asm_result=10 → square(10)=100 */
    check("asm_then_call", asm_then_call(4, 6),    100);

    /* F. Consecutive asm statements */
    /* asm_two_steps(3,4,5): r1=7, result=35 */
    check("two_steps",   asm_two_steps(3, 4, 5),          35);
    /* asm_three_steps(2,3,4,5,6): t=5, u=20, v=20+5+6=31 */
    check("three_steps", asm_three_steps(2, 3, 4, 5, 6),  31);

    /* summary */
    puts("================");
    print_str("PASS: "); print_int(pass_count); putchar(10);
    print_str("FAIL: "); print_int(fail_count); putchar(10);
    puts("=== done ===");
    return 0;
}

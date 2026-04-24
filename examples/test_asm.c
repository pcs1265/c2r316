/*
 * test_asm.c
 *
 * Verifies inline-asm implementations of runtime functions.
 * Each function below replaces its runtime.asm counterpart; the
 * same print_str/putchar/print_int helpers are declared extern so
 * the linker still pulls the originals for the test harness itself.
 *
 * Terminal memory map (from runtime.asm):
 *   0x9F80 : term_input   (keyboard read)
 *   0x9FB5 : term_term    (character output, handles newline)
 */

#include "runtime/stdlib.h"
#include "runtime/stdio.h"

int pass_count;
int fail_count;

void check(char *name, int got, int expected) {
    if (got == expected) {
        print_str(name);
        print_str(": PASS\n");
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

/* ── inline-asm implementations ─────────────────────────────────────────── */

/*
 * asm_putchar: write one character to the terminal.
 * ABI: r1 = c (first arg), output register is term_term.
 */
void asm_putchar(int c) {
    asm("st %0, 0x9FB5" : "r"(c));
}

/*
 * asm_memset: fill n words starting at dst with val.
 * Pure C — no special instructions needed; included here as a
 * sanity-check that asm and plain C can coexist in the same file.
 */
void asm_memset(int *dst, int val, int n) {
    int i;
    for (i = 0; i < n; i++) {
        dst[i] = val;
    }
}

/*
 * asm_memcpy: copy n words from src to dst.
 */
void asm_memcpy(int *dst, int *src, int n) {
    int i;
    for (i = 0; i < n; i++) {
        dst[i] = src[i];
    }
}

/*
 * asm_strlen: count characters until null terminator.
 */
int asm_strlen(char *s) {
    int n;
    n = 0;
    while (s[n] != 0) {
        n = n + 1;
    }
    return n;
}

/*
 * asm_strcmp: lexicographic comparison.
 * Returns 0 if equal, non-zero otherwise (sign matches a-b at first diff).
 */
int asm_strcmp(char *a, char *b) {
    int i;
    i = 0;
    while (1) {
        int ca;
        int cb;
        ca = a[i];
        cb = b[i];
        if (ca != cb) return ca - cb;
        if (ca == 0)  return 0;
        i = i + 1;
    }
    return 0;
}

/*
 * asm_putchar_via_reg: same as asm_putchar but loads c into an explicit
 * register operand to exercise the %0 substitution path in codegen.
 */
void asm_putchar_via_reg(int c) {
    asm("st %0, 0x9FB5" : "r"(c));
}

/*
 * asm_add: trivial two-operand asm to exercise %0/%1 substitution.
 * Computes a+b using the R316 add instruction and stores the result
 * back through a pointer so the return value is observable.
 */
void asm_add(int a, int b, int *out) {
    asm("add %0, %1\nst %0, %2" : "r"(a), "r"(b), "r"(out));
}

/*
 * asm_multiline: exercise multi-line ASM using C string concatenation.
 * This computes (a + b) * c and stores it in *out.
 */
void asm_multiline(int a, int b, int c, int *out) {
    asm("add %0, %1\n"
        "mul %0, %0, %2\n"
        "st %0, %3"
        : "r"(a), "r"(b), "r"(c), "r"(out));
}

/* ── main ────────────────────────────────────────────────────────────────── */
int main(void) {
    pass_count = 0;
    fail_count = 0;

    print_str("=== test_asm ===\n");

    /* 1. asm_putchar emits the character and returns cleanly */
    print_str("asm_putchar: ");
    asm_putchar('O');
    asm_putchar('K');
    asm_putchar(10);           /* newline */

    /* 2. asm_strlen */
    check("strlen_hello",  asm_strlen("hello"), 5);
    check("strlen_empty",  asm_strlen(""),       0);
    check("strlen_one",    asm_strlen("x"),      1);

    /* 3. asm_strcmp */
    check("strcmp_eq",     asm_strcmp("abc", "abc"),  0);
    check("strcmp_lt",     asm_strcmp("abc", "abd") < 0, 1);
    check("strcmp_gt",     asm_strcmp("abd", "abc") > 0, 1);
    check("strcmp_prefix", asm_strcmp("ab",  "abc") < 0, 1);

    /* 4. asm_memset */
    int buf[4];
    buf[0] = 1; buf[1] = 2; buf[2] = 3; buf[3] = 4;
    asm_memset(buf, 7, 4);
    check("memset[0]", buf[0], 7);
    check("memset[1]", buf[1], 7);
    check("memset[2]", buf[2], 7);
    check("memset[3]", buf[3], 7);

    /* 5. asm_memcpy */
    int src[3];
    int dst[3];
    src[0] = 10; src[1] = 20; src[2] = 30;
    dst[0] =  0; dst[1] =  0; dst[2] =  0;
    asm_memcpy(dst, src, 3);
    check("memcpy[0]", dst[0], 10);
    check("memcpy[1]", dst[1], 20);
    check("memcpy[2]", dst[2], 30);

    /* 6. two-operand %0/%1 substitution via asm_add */
    int result;
    result = 0;
    asm_add(12, 30, &result);
    check("asm_add", result, 42);

    /* 7. multi-line string concatenation */
    result = 0;
    asm_multiline(10, 20, 3, &result);
    check("asm_multiline", result, 90);

    /* summary */
    print_str("================\n");
    print_str("PASS: "); print_int(pass_count); putchar(10);
    print_str("FAIL: "); print_int(fail_count); putchar(10);
    print_str("=== done ===\n");
    return 0;
}

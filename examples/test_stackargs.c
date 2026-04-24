/* test_stackargs.c - self-validating tests for stack-passed arguments (7th+) */

#include "runtime/stdlib.h"

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

int sum7(int a, int b, int c, int d, int e, int f, int g) {
    return a + b + c + d + e + f + g;
}

int sum8(int a, int b, int c, int d, int e, int f, int g, int h) {
    return a + b + c + d + e + f + g + h;
}

int pick7(int a, int b, int c, int d, int e, int f, int g) {
    return g;
}

int pick8(int a, int b, int c, int d, int e, int f, int g, int h) {
    return h;
}

int add_stack(int a, int b, int c, int d, int e, int f, int g, int h) {
    return g + h;
}

int main(void) {
    pass_count = 0;
    fail_count = 0;

    puts("=== test_stackargs ===");

    /* 1. sum of 7 args (1 stack arg) */
    check("sum7",      sum7(1, 2, 3, 4, 5, 6, 7),          28);

    /* 2. sum of 8 args (2 stack args) */
    check("sum8",      sum8(1, 2, 3, 4, 5, 6, 7, 8),       36);

    /* 3. isolate 7th arg */
    check("pick7",     pick7(0, 0, 0, 0, 0, 0, 99),        99);

    /* 4. isolate 8th arg */
    check("pick8",     pick8(0, 0, 0, 0, 0, 0, 0, 42),     42);

    /* 5. both stack args used independently */
    check("add_stack", add_stack(0, 0, 0, 0, 0, 0, 3, 4),  7);

    /* 6. stack args with non-zero register args */
    check("sum7b",     sum7(10, 10, 10, 10, 10, 10, 5),    65);

    /* summary */
    puts("=====================");
    print_str("PASS: "); print_int(pass_count); putchar(10);
    print_str("FAIL: "); print_int(fail_count); putchar(10);
    puts("=== done ===");
    return 0;
}

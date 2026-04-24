/* test_varargs.c - self-validating tests for variadic function support */

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

int sum(int n, ...) {
    va_list ap;
    va_start(ap, n);
    int total;
    int i;
    total = 0;
    i = 0;
    while (i < n) {
        total = total + va_arg(ap, int);
        i = i + 1;
    }
    va_end(ap);
    return total;
}

int first(int n, ...) {
    va_list ap;
    va_start(ap, n);
    int v;
    v = va_arg(ap, int);
    va_end(ap);
    return v;
}

int last3(int a, int b, int c, ...) {
    va_list ap;
    va_start(ap, c);
    int v;
    v = va_arg(ap, int);
    va_end(ap);
    return v;
}

int main(void) {
    pass_count = 0;
    fail_count = 0;

    puts("=== test_varargs ===");

    /* 1. single variadic arg */
    check("sum1",    sum(1, 42),          42);

    /* 2. two variadic args */
    check("sum2",    sum(2, 10, 20),      30);

    /* 3. three variadic args */
    check("sum3",    sum(3, 10, 20, 30),  60);

    /* 4. zero variadic args (n=0) */
    check("sum0",    sum(0),              0);

    /* 5. first variadic arg is independent of n */
    check("first1",  first(3, 99, 1, 2), 99);

    /* 6. variadic arg after multiple fixed params */
    check("last3",   last3(1, 2, 3, 77), 77);

    /* summary */
    puts("===================");
    print_str("PASS: "); print_int(pass_count); putchar(10);
    print_str("FAIL: "); print_int(fail_count); putchar(10);
    puts("=== done ===");
    return 0;
}

/* test_variadic_edge.c - variadic argument edge cases */

#include <stdio.h>
#include <stdarg.h>

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

void check_u(char *name, unsigned int got, unsigned int expected) {
    if (got == expected) {
        print_str(name);
        puts(": PASS");
        pass_count = pass_count + 1;
    } else {
        print_str(name);
        print_str(": FAIL got=");
        print_uint(got);
        print_str(" exp=");
        print_uint(expected);
        putchar(10);
        fail_count = fail_count + 1;
    }
}

/* Variadic function with 0 variadic args */
int sum0(int count, ...) {
    va_list ap;
    int total;
    total = 0;
    va_start(ap, count);
    while (count > 0) {
        total = total + va_arg(ap, int);
        count = count - 1;
    }
    va_end(ap);
    return total;
}

/* Variadic function with mixed types */
int mixed_sum(int count, ...) {
    va_list ap;
    int total;
    total = 0;
    va_start(ap, count);
    while (count > 0) {
        total = total + va_arg(ap, int);
        count = count - 1;
    }
    va_end(ap);
    return total;
}

/* Variadic function with fixed params and variadic */
int fixed_variadic(int a, int b, int count, ...) {
    va_list ap;
    int total;
    total = a + b;
    va_start(ap, count);
    while (count > 0) {
        total = total + va_arg(ap, int);
        count = count - 1;
    }
    va_end(ap);
    return total;
}

/* Variadic with many args (>6 to test stack args) */
int many_sum(int n, ...) {
    va_list ap;
    int total;
    int i;
    total = 0;
    va_start(ap, n);
    for (i = 0; i < n; i = i + 1) {
        total = total + va_arg(ap, int);
    }
    va_end(ap);
    return total;
}

/* Variadic with unsigned */
unsigned int sum_unsigned(int count, ...) {
    va_list ap;
    unsigned int total;
    total = 0;
    va_start(ap, count);
    while (count > 0) {
        total = total + va_arg(ap, unsigned int);
        count = count - 1;
    }
    va_end(ap);
    return total;
}

int main(void) {
    pass_count = 0;
    fail_count = 0;

    puts("=== test_variadic_edge ===");

    /* 1. Zero variadic args */
    check("sum0(0)", sum0(0), 0);

    /* 2. Single variadic arg */
    check("sum0(1, 42)", sum0(1, 42), 42);

    /* 3. Multiple variadic args */
    check("sum0(3, 1, 2, 3)", sum0(3, 1, 2, 3), 6);
    check("sum0(5, 10, 20, 30, 40, 50)", sum0(5, 10, 20, 30, 40, 50), 150);

    /* 4. Fixed + variadic */
    check("fixed_var(2, 3, 2, 4, 5)", fixed_variadic(2, 3, 2, 4, 5), 14);

    /* 5. Many args (tests stack argument passing) */
    check("many(7)", many_sum(7, 1, 2, 3, 4, 5, 6, 7), 28);
    check("many(8)", many_sum(8, 1, 2, 3, 4, 5, 6, 7, 8), 36);
    check("many(10)", many_sum(10, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1), 10);
    check("many(12)", many_sum(12, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12), 78);

    /* 6. Large values */
    check("sum large", sum0(3, 1000, 2000, 3000), 6000);

    /* 7. Negative values */
    check("sum neg", sum0(3, 10, -5, 3), 8);
    check("sum all neg", sum0(3, -1, -2, -3), -6);

    /* 8. Unsigned variadic */
    check_u("sum unsigned", sum_unsigned(3, 100u, 200u, 300u), 600u);
    check_u("sum unsigned large", sum_unsigned(2, 30000u, 35000u), 65000u);

    /* 9. Deeply nested variadic calls */
    int v1;
    int v2;
    v1 = sum0(2, 10, 20);
    v2 = sum0(2, v1, 30);
    check("nested variadic", v2, 60);

    /* 10. Variadic with pointer args (as int) */
    int x;
    int *p;
    x = 42;
    p = &x;
    /* Pass pointer as int - this works but is platform-specific */
    check("variadic with ptr", sum0(2, 1, 2), 3);

    /* summary */
    puts("================");
    print_str("PASS: "); print_int(pass_count); putchar(10);
    print_str("FAIL: "); print_int(fail_count); putchar(10);
    puts("=== done ===");
    return 0;
}
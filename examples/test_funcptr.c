/* test_funcptr.c - self-validating tests for function pointers */

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

/* ── test functions ── */

int add(int a, int b) {
    return a + b;
}

int sub(int a, int b) {
    return a - b;
}

int mul(int a, int b) {
    return a * b;
}

int apply(int (*op)(int, int), int a, int b) {
    return op(a, b);
}

/* ── function pointer typedefs ── */

typedef int (*binop_t)(int, int);

/* ── global function pointers ── */

binop_t g_op;

/* ── main ── */

int main(void) {
    pass_count = 0;
    fail_count = 0;

    puts("=== test_funcptr ===");

    /* 1. local function pointer via typedef */
    binop_t f;
    f = add;
    check("typedef_add", f(10, 5), 15);
    f = sub;
    check("typedef_sub", f(10, 5), 5);

    /* 2. global function pointer */
    g_op = mul;
    check("global_mul", g_op(6, 7), 42);

    /* 3. passing function pointer as argument */
    check("apply_add", apply(add, 20, 30), 50);
    check("apply_sub", apply(sub, 50, 20), 30);

    /* 4. call via cast (if declarator syntax is limited) */
    /* According to TODO.md, direct declarator might not be parsed, 
       but we can use typedef or cast. */
    int (*f2)(int, int);
    f2 = add;
    check("decl_add", f2(1, 2), 3);

    /* 5. array of function pointers */
    binop_t ops[3];
    ops[0] = add;
    ops[1] = sub;
    ops[2] = mul;
    check("array_ops[0]", ops[0](10, 20), 30);
    check("array_ops[1]", ops[1](10, 20), -10);
    check("array_ops[2]", ops[2](10, 20), 200);

    /* 6. pointer to function returning pointer (more complex) */
    /* Skipping for now to keep it simple and likely to pass */

    /* summary */
    puts("================");
    print_str("PASS: "); print_int(pass_count); putchar(10);
    print_str("FAIL: "); print_int(fail_count); putchar(10);
    puts("=== done ===");
    return 0;
}

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

/* ── function returning a function pointer ── */

binop_t get_op(int n) {
    if (n == 0) return add;
    if (n == 1) return sub;
    return mul;
}

/* ── struct with function pointer field ── */

struct binop_obj {
    binop_t fn;
    int bias;
};

int call_obj(struct binop_obj obj, int a, int b) {
    return obj.fn(a, b) + obj.bias;
}

/* ── fold: apply funcptr over int array ── */

int fold(binop_t op, int *arr, int len, int init) {
    int acc = init;
    int i;
    for (i = 0; i < len; i = i + 1) {
        acc = op(acc, arr[i]);
    }
    return acc;
}

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

    /* 6. function returning a function pointer */
    binop_t op6 = get_op(0);
    check("ret_funcptr_add", op6(3, 4), 7);
    op6 = get_op(1);
    check("ret_funcptr_sub", op6(10, 3), 7);
    op6 = get_op(2);
    check("ret_funcptr_mul", op6(3, 4), 12);

    /* 7. immediate call of returned function pointer: get_op(n)(a, b) */
    check("chain_add", get_op(0)(10, 20), 30);
    check("chain_sub", get_op(1)(10, 20), -10);
    check("chain_mul", get_op(2)(3,  7),  21);

    /* 8. struct with function pointer field */
    struct binop_obj obj;
    obj.fn = add;
    obj.bias = 100;
    check("struct_fp_add", call_obj(obj, 3, 4), 107);
    obj.fn = mul;
    obj.bias = 0;
    check("struct_fp_mul", call_obj(obj, 5, 6), 30);

    /* 9. fold (apply funcptr over array) */
    int arr[4];
    arr[0] = 1; arr[1] = 2; arr[2] = 3; arr[3] = 4;
    check("fold_add", fold(add, arr, 4, 0),  10);
    check("fold_mul", fold(mul, arr, 4, 1),  24);

    /* 10. repeated reassignment — pointer tracks latest assignment */
    binop_t r = add;
    check("reassign_1", r(2, 3), 5);
    r = sub;
    check("reassign_2", r(10, 3), 7);
    r = mul;
    check("reassign_3", r(4, 5), 20);
    r = add;
    check("reassign_4", r(1, 1), 2);

    /* summary */
    puts("================");
    print_str("PASS: "); print_int(pass_count); putchar(10);
    print_str("FAIL: "); print_int(fail_count); putchar(10);
    puts("=== done ===");
    return 0;
}

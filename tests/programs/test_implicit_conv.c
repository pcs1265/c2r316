/* test_implicit_conv.c - tests for implicit conversions */

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

int truthy(int x) {
    return x;
}

int main(void) {
    pass_count = 0;
    fail_count = 0;

    puts("=== test_implicit_conv ===");

    /* 1. pointer in condition (null check) */
    int *p;
    p = 0;
    if (p) {
        check("null ptr cond", 0, 1);  /* should not execute */
    } else {
        check("null ptr cond", 1, 1);  /* should execute */
    }

    int x;
    int *q;
    q = &x;
    if (q) {
        check("non-null ptr cond", 1, 1);  /* should execute */
    } else {
        check("non-null ptr cond", 0, 1);  /* should not execute */
    }

    /* 2. integer in condition */
    int n;
    n = 0;
    if (n) {
        check("int 0 cond", 0, 1);
    } else {
        check("int 0 cond", 1, 1);
    }
    n = 1;
    if (n) {
        check("int 1 cond", 1, 1);
    } else {
        check("int 1 cond", 0, 1);
    }
    n = -5;
    if (n) {
        check("int -5 cond", 1, 1);
    } else {
        check("int -5 cond", 0, 1);
    }

    /* 3. pointer comparison to null */
    p = 0;
    check("ptr == 0", p == 0, 1);
    check("ptr != 0", p != 0, 0);
    q = &x;
    check("ptr != 0 non-null", q != 0, 1);
    check("ptr == 0 non-null", q == 0, 0);

    /* 4. ternary operator result type */
    int a;
    int b;
    a = 10;
    b = 20;
    int tern1;
    tern1 = 1 ? a : b;
    check("ternary true", tern1, 10);
    tern1 = 0 ? a : b;
    check("ternary false", tern1, 20);

    /* 5. ternary with different signedness */
    unsigned int ua;
    ua = 100;
    n = 1 ? ua : 1;  /* should promote to unsigned */
    check_u("ternary mixed", n, 100);

    /* 6. assignment conversion */
    char c;
    c = 65;
    check("int to char", c, 65);
    c = 300;  /* truncates to 300 - 256 = 44 */
    check("int to char trunc", c, 44);

    /* 7. pointer to pointer assignment */
    int arr[5];
    int *r1;
    int *r2;
    r1 = arr;
    r2 = r1;
    check("ptr to ptr", r2 == arr, 1);

    /* 8. function argument conversion */
    n = truthy(0);
    check("func arg 0", n, 0);
    n = truthy(42);
    check("func arg 42", n, 42);

    /* 9. return value conversion */
    char cret;
    cret = 'A';
    n = cret;  /* char promoted to int */
    check("char to int", n, 65);

    /* 10. array to pointer decay */
    int nums[3];
    int *np;
    nums[0] = 100;
    np = nums;  /* array decays to pointer */
    check("array decay", np[0], 100);

    /* 11. implicit int literal to unsigned */
    unsigned int uval;
    uval = -1;  /* -1 converted to unsigned is 0xFFFF */
    check_u("int to uint", uval, 0xFFFF);

    /* 12. logical operators return int */
    int bool_result;
    bool_result = 1 && 0;
    check("&& result", bool_result, 0);
    bool_result = 1 || 0;
    check("|| result", bool_result, 1);
    bool_result = !0;
    check("! result", bool_result, 1);

    /* summary */
    puts("================");
    print_str("PASS: "); print_int(pass_count); putchar(10);
    print_str("FAIL: "); print_int(fail_count); putchar(10);
    puts("=== done ===");
    return 0;
}
/* test_init.c - self-validating tests for multi-declarations and array initializers */

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

/* ── global multi-declarations ── */

int g_a, g_b, g_c;

/* global array initializer */
int g_arr[4] = {10, 20, 30, 40};

/* global scalar with init + multi */
int g_x = 5, g_y, g_z = 7;

int g_arr_sum(void) {
    return g_arr[0] + g_arr[1] + g_arr[2] + g_arr[3];
}

int main(void) {
    pass_count = 0;
    fail_count = 0;

    puts("=== test_init ===");

    /* 1. global multi-decl defaults to zero */
    check("g_a_zero", g_a, 0);
    check("g_b_zero", g_b, 0);
    check("g_c_zero", g_c, 0);

    /* 2. global multi-decl assignment */
    g_a = 1; g_b = 2; g_c = 3;
    check("g_a", g_a, 1);
    check("g_b", g_b, 2);
    check("g_c", g_c, 3);

    /* 3. global array initializer */
    check("g_arr[0]",  g_arr[0], 10);
    check("g_arr[1]",  g_arr[1], 20);
    check("g_arr[2]",  g_arr[2], 30);
    check("g_arr[3]",  g_arr[3], 40);
    check("g_arr_sum", g_arr_sum(), 100);

    /* 4. global scalar initializer in multi-decl */
    check("g_x", g_x, 5);
    check("g_y", g_y, 0);
    check("g_z", g_z, 7);

    /* 5. local multi-decl, no init */
    int a, b, c;
    a = 10; b = 20; c = 30;
    check("a", a, 10);
    check("b", b, 20);
    check("c", c, 30);

    /* 6. local multi-decl with init */
    int x = 1, y = 2, z = 3;
    check("x", x, 1);
    check("y", y, 2);
    check("z", z, 3);

    /* 7. local multi-decl: first init, rest not */
    int p = 99, q, r;
    q = 0; r = 0;
    check("p_init", p, 99);
    check("q_zero", q, 0);

    /* 8. local array initializer with explicit size */
    int arr[4] = {1, 2, 4, 8};
    check("arr[0]", arr[0], 1);
    check("arr[1]", arr[1], 2);
    check("arr[2]", arr[2], 4);
    check("arr[3]", arr[3], 8);

    /* 9. local array initializer with inferred size */
    int brr[] = {5, 10, 15};
    check("brr[0]", brr[0], 5);
    check("brr[1]", brr[1], 10);
    check("brr[2]", brr[2], 15);

    /* 10. partial initializer: remaining elements zero */
    int crr[4] = {7, 8};
    check("crr[0]", crr[0], 7);
    check("crr[1]", crr[1], 8);
    check("crr[2]", crr[2], 0);
    check("crr[3]", crr[3], 0);

    /* 10b. {0} zero-fills entire array */
    int zerr[5] = {0};
    check("zerr[0]", zerr[0], 0);
    check("zerr[1]", zerr[1], 0);
    check("zerr[2]", zerr[2], 0);
    check("zerr[3]", zerr[3], 0);
    check("zerr[4]", zerr[4], 0);

    /* 11. initializer + mutation */
    int drr[] = {100, 200, 300};
    drr[1] = drr[1] + 1;
    check("drr_mut", drr[1], 201);

    /* 12. sum via loop over initialized array */
    int sum;
    int i;
    int vals[] = {3, 7, 11, 13};
    sum = 0;
    for (i = 0; i < 4; i++) {
        sum = sum + vals[i];
    }
    check("loop_sum", sum, 34);

    /* 13. global array write then re-read */
    g_arr[2] = 0;
    check("g_arr_wr", g_arr_sum(), 70);

    /* summary */
    puts("=================");
    print_str("PASS: "); print_int(pass_count); putchar(10);
    print_str("FAIL: "); print_int(fail_count); putchar(10);
    puts("=== done ===");
    return 0;
}

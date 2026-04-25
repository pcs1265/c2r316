/* test_call.c - self-validating tests for calling conventions
   Covers: register args, stack args (7th+), variadics, struct pass-by-value,
   struct return. */

#include "runtime/stdio.h"

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

/* ── register arguments (≤6) ── */

int reg1(int a) { return a; }
int reg2(int a, int b) { return a + b; }
int reg6(int a, int b, int c, int d, int e, int f) {
    return a + b + c + d + e + f;
}

/* ── stack arguments (7th+) ── */

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

/* ── variadic functions ── */

int sum_va(int n, ...) {
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

int first_va(int n, ...) {
    va_list ap;
    va_start(ap, n);
    int v;
    v = va_arg(ap, int);
    va_end(ap);
    return v;
}

int last3_va(int a, int b, int c, ...) {
    va_list ap;
    va_start(ap, c);
    int v;
    v = va_arg(ap, int);
    va_end(ap);
    return v;
}

/* ── struct pass-by-value and return ── */

struct point {
    int x;
    int y;
};

struct rect {
    int x;
    int y;
    int w;
    int h;
};

int point_sum(struct point p) {
    return p.x + p.y;
}

int point_diff(struct point p) {
    return p.x - p.y;
}

struct point point_add(struct point a, struct point b) {
    struct point r;
    r.x = a.x + b.x;
    r.y = a.y + b.y;
    return r;
}

struct point point_scale(struct point p, int s) {
    struct point r;
    r.x = p.x * s;
    r.y = p.y * s;
    return r;
}

int rect_area(struct rect r) {
    return r.w * r.h;
}

int rect_perimeter(struct rect r) {
    return 2 * (r.w + r.h);
}

/* ── main ── */

int main(void) {
    pass_count = 0;
    fail_count = 0;

    puts("=== test_call ===");

    /* 1. register args */
    check("reg1",      reg1(7),                       7);
    check("reg2",      reg2(3, 4),                    7);
    check("reg6",      reg6(1, 2, 3, 4, 5, 6),        21);

    /* 2. stack args (7th+) */
    check("sum7",      sum7(1, 2, 3, 4, 5, 6, 7),     28);
    check("sum8",      sum8(1, 2, 3, 4, 5, 6, 7, 8),  36);
    check("pick7",     pick7(0, 0, 0, 0, 0, 0, 99),   99);
    check("pick8",     pick8(0, 0, 0, 0, 0, 0, 0, 42),42);
    check("add_stack", add_stack(0,0,0,0,0,0, 3, 4),  7);
    check("sum7b",     sum7(10,10,10,10,10,10, 5),     65);

    /* 3. variadic */
    check("va_sum1",   sum_va(1, 42),                 42);
    check("va_sum2",   sum_va(2, 10, 20),             30);
    check("va_sum3",   sum_va(3, 10, 20, 30),         60);
    check("va_sum0",   sum_va(0),                     0);
    check("va_first",  first_va(3, 99, 1, 2),         99);
    check("va_last3",  last3_va(1, 2, 3, 77),         77);

    /* 4. struct pass-by-value */
    struct point p1;
    p1.x = 10;
    p1.y = 3;
    check("pt_sum",    point_sum(p1),                 13);
    check("pt_diff",   point_diff(p1),                7);

    struct rect rc;
    rc.x = 0; rc.y = 0; rc.w = 5; rc.h = 4;
    check("rect_area", rect_area(rc),                 20);
    check("rect_peri", rect_perimeter(rc),            18);

    /* 5. struct return */
    struct point p2;
    p2.x = 1;
    p2.y = 2;
    struct point p3;
    p3.x = 3;
    p3.y = 4;
    struct point r1;
    r1 = point_add(p1, p2);
    check("pt_add_x",  r1.x,                         11);
    check("pt_add_y",  r1.y,                         5);
    struct point r2;
    r2 = point_scale(p2, 3);
    check("pt_scale_x", r2.x,                        3);
    check("pt_scale_y", r2.y,                        6);

    /* 6. chained struct operations */
    struct point r3;
    r3 = point_add(point_scale(p2, 2), p3);
    check("chain_x",   r3.x,                         5);
    check("chain_y",   r3.y,                         8);

    /* summary */
    puts("================");
    print_str("PASS: "); print_int(pass_count); putchar(10);
    print_str("FAIL: "); print_int(fail_count); putchar(10);
    puts("=== done ===");
    return 0;
}

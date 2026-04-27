/* test_nested_struct.c - deeply nested struct tests */

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

/* Deeply nested struct hierarchy */
struct A {
    int a_val;
};

struct B {
    struct A a_inner;
    int b_val;
};

struct C {
    struct B b_inner;
    int c_val;
};

struct D {
    struct C c_inner;
    int d_val;
};

struct E {
    struct D d_inner;
    int e_val;
};

/* Struct containing array */
struct WithArray {
    int data[4];
    int count;
};

/* Struct containing struct array */
struct Inner {
    int x;
    int y;
};

struct Outer {
    struct Inner items[3];
    int total;
};

/* Mixed nested */
struct Mixed {
    int val;
    struct Inner arr[2];
    struct A single;
};

int main(void) {
    pass_count = 0;
    fail_count = 0;

    puts("=== test_nested_struct ===");

    /* 1. Basic nested access */
    struct B b;
    b.a_inner.a_val = 10;
    b.b_val = 20;
    check("b.a_inner.a_val", b.a_inner.a_val, 10);
    check("b.b_val", b.b_val, 20);

    /* 2. Three levels deep */
    struct C c;
    c.b_inner.a_inner.a_val = 100;
    c.b_inner.b_val = 200;
    c.c_val = 300;
    check("c.b_inner.a_inner.a_val", c.b_inner.a_inner.a_val, 100);
    check("c.b_inner.b_val", c.b_inner.b_val, 200);
    check("c.c_val", c.c_val, 300);

    /* 3. Four levels deep */
    struct D d;
    d.c_inner.b_inner.a_inner.a_val = 1000;
    d.c_inner.b_inner.b_val = 2000;
    d.c_inner.c_val = 3000;
    d.d_val = 4000;
    check("d.c_inner.b_inner.a_inner.a_val", d.c_inner.b_inner.a_inner.a_val, 1000);
    check("d.d_val", d.d_val, 4000);

    /* 4. Five levels deep */
    struct E e;
    e.d_inner.c_inner.b_inner.a_inner.a_val = 10000;
    e.d_inner.c_inner.b_inner.b_val = 20000;
    e.d_inner.c_inner.c_val = 30000;
    e.d_inner.d_val = 40000;
    e.e_val = 50000;
    check("e.d_inner.c_inner.b_inner.a_inner.a_val", e.d_inner.c_inner.b_inner.a_inner.a_val, 10000);
    check("e.e_val", e.e_val, 50000);

    /* 5. Struct containing array */
    struct WithArray wa;
    wa.data[0] = 1;
    wa.data[1] = 2;
    wa.data[2] = 3;
    wa.data[3] = 4;
    wa.count = 4;
    check("wa.data[0]", wa.data[0], 1);
    check("wa.data[3]", wa.data[3], 4);
    check("wa.count", wa.count, 4);

    /* 6. Struct containing struct array */
    struct Outer o;
    o.items[0].x = 1;
    o.items[0].y = 2;
    o.items[1].x = 3;
    o.items[1].y = 4;
    o.items[2].x = 5;
    o.items[2].y = 6;
    o.total = 21;
    check("o.items[0].x", o.items[0].x, 1);
    check("o.items[1].y", o.items[1].y, 4);
    check("o.items[2].x", o.items[2].x, 5);
    check("o.total", o.total, 21);

    /* 7. Mixed nested struct */
    struct Mixed m;
    m.val = 42;
    m.arr[0].x = 10;
    m.arr[0].y = 20;
    m.arr[1].x = 30;
    m.arr[1].y = 40;
    m.single.a_val = 100;
    check("m.val", m.val, 42);
    check("m.arr[0].x", m.arr[0].x, 10);
    check("m.arr[1].y", m.arr[1].y, 40);
    check("m.single.a_val", m.single.a_val, 100);

    /* 8. Nested struct via pointer */
    struct B *bp;
    bp = &b;
    bp->a_inner.a_val = 999;
    bp->b_val = 888;
    check("bp->a_inner.a_val", bp->a_inner.a_val, 999);
    check("bp->b_val", bp->b_val, 888);

    /* 9. Nested struct assignment */
    struct B b2;
    b2 = b;
    check("b2.a_inner.a_val", b2.a_inner.a_val, 999);
    check("b2.b_val", b2.b_val, 888);

    /* 10. Array of deeply nested structs */
    struct D darr[2];
    darr[0].c_inner.b_inner.a_inner.a_val = 1;
    darr[0].d_val = 10;
    darr[1].c_inner.b_inner.a_inner.a_val = 2;
    darr[1].d_val = 20;
    check("darr[0].c_inner.b_inner.a_inner.a_val", darr[0].c_inner.b_inner.a_inner.a_val, 1);
    check("darr[1].d_val", darr[1].d_val, 20);

    /* summary */
    puts("================");
    print_str("PASS: "); print_int(pass_count); putchar(10);
    print_str("FAIL: "); print_int(fail_count); putchar(10);
    puts("=== done ===");
    return 0;
}
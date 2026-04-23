/* test_struct.c - self-validating tests for struct and union support */

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

/* ── struct definitions ── */

struct Point {
    int x;
    int y;
};

struct Rect {
    struct Point tl;
    struct Point br;
};

union Val {
    int i;
    char c;
};

/* ── helper functions ── */

int point_sum(struct Point *p) {
    return p->x + p->y;
}

void point_scale(struct Point *p, int factor) {
    p->x = p->x * factor;
    p->y = p->y * factor;
}

int rect_area(struct Rect *r) {
    int w;
    int h;
    w = r->br.x - r->tl.x;
    h = r->br.y - r->tl.y;
    return w * h;
}

int main(void) {
    pass_count = 0;
    fail_count = 0;

    puts("=== test_struct ===");

    /* 1. basic field read/write via dot */
    struct Point a;
    a.x = 10;
    a.y = 20;
    check("dot.x",  a.x, 10);
    check("dot.y",  a.y, 20);

    /* 2. field mutation */
    a.x = a.x + 5;
    check("mut.x",  a.x, 15);

    /* 3. pointer field access via arrow */
    struct Point *pa;
    pa = &a;
    check("arrow->x", pa->x, 15);
    check("arrow->y", pa->y, 20);

    /* 4. write through pointer */
    pa->x = 99;
    check("arrow_wr->x", a.x, 99);
    a.x = 15;

    /* 5. pass-by-pointer to function */
    check("fn_sum",  point_sum(&a), 35);

    /* 6. mutation through function pointer param */
    point_scale(&a, 2);
    check("scale.x", a.x, 30);
    check("scale.y", a.y, 40);

    /* 7. two independent structs */
    struct Point b;
    b.x = 1;
    b.y = 2;
    check("two_a.x", a.x, 30);
    check("two_b.x", b.x, 1);

    /* 8. struct pointer arithmetic (array of structs) */
    struct Point pts[3];
    pts[0].x = 10;  pts[0].y = 11;
    pts[1].x = 20;  pts[1].y = 21;
    pts[2].x = 30;  pts[2].y = 31;
    check("arr[0].x", pts[0].x, 10);
    check("arr[1].x", pts[1].x, 20);
    check("arr[2].y", pts[2].y, 31);

    /* 9. nested struct (struct containing struct) */
    struct Rect r;
    r.tl.x = 2;
    r.tl.y = 3;
    r.br.x = 8;
    r.br.y = 7;
    check("rect_tl.x",  r.tl.x, 2);
    check("rect_br.y",  r.br.y, 7);
    check("rect_area",  rect_area(&r), 24);

    /* 10. union: write as int, read same field */
    union Val v;
    v.i = 42;
    check("union.i", v.i, 42);

    /* 11. union: fields share same word */
    v.c = 65;
    check("union.c", v.c, 65);
    check("union_overlap", v.i, 65);

    /* summary */
    puts("==================");
    print_str("PASS: "); print_int(pass_count); putchar(10);
    print_str("FAIL: "); print_int(fail_count); putchar(10);
    puts("=== done ===");
    return 0;
}

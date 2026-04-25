/* test_struct.c - self-validating tests for struct and union support */

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

/* ── global structs ── */

struct Point g_origin;
struct Point g_cursor;
struct Rect  g_viewport;

void g_cursor_move(int dx, int dy) {
    g_cursor.x = g_cursor.x + dx;
    g_cursor.y = g_cursor.y + dy;
}

struct Point g_pts[3];

void g_pts_init(void) {
    g_pts[0].x = 5;  g_pts[0].y = 6;
    g_pts[1].x = 7;  g_pts[1].y = 8;
    g_pts[2].x = 9;  g_pts[2].y = 10;
}

int g_pts_xsum(void) {
    return g_pts[0].x + g_pts[1].x + g_pts[2].x;
}

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

    /* 12. global structs */
    g_origin.x = 0;
    g_origin.y = 0;
    check("g_origin.x", g_origin.x, 0);
    check("g_origin.y", g_origin.y, 0);

    g_cursor.x = 10;
    g_cursor.y = 20;
    g_cursor_move(3, -5);
    check("g_cursor.x", g_cursor.x, 13);
    check("g_cursor.y", g_cursor.y, 15);

    /* mutation through pointer to global */
    struct Point *gp;
    gp = &g_cursor;
    gp->x = 100;
    check("g_cursor_ptr", g_cursor.x, 100);

    /* global nested struct */
    g_viewport.tl.x = 0;
    g_viewport.tl.y = 0;
    g_viewport.br.x = 12;
    g_viewport.br.y = 8;
    check("g_vp_area", rect_area(&g_viewport), 96);
    g_viewport.br.x = 6;
    check("g_vp_mutate", rect_area(&g_viewport), 48);

    /* global array of structs */
    g_pts_init();
    check("g_pts_xsum",   g_pts_xsum(), 21);
    check("g_pts[1].y",   g_pts[1].y,   8);
    g_pts[1].x = 0;
    check("g_pts_xsum2",  g_pts_xsum(), 14);

    /* global struct survives unrelated call */
    g_cursor.x = 55;
    point_sum(&a);
    check("g_after_call", g_cursor.x, 55);

    /* summary */
    puts("==================");
    print_str("PASS: "); print_int(pass_count); putchar(10);
    print_str("FAIL: "); print_int(fail_count); putchar(10);
    puts("=== done ===");
    return 0;
}

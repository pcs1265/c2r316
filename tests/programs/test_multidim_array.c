/* Multi-dimensional array tests */
#include <stdio.h>

static int pass_count = 0;
static int fail_count = 0;

static void check(const char *name, int got, int expected) {
    if (got == expected) {
        printf("PASS: %s\n", name);
        pass_count++;
    } else {
        printf("FAIL: %s  got=%d  expected=%d\n", name, got, expected);
        fail_count++;
    }
}

/* Global 2D array with initializer */
int g2d[2][3] = {{10, 20, 30}, {40, 50, 60}};

/* Global 3D array */
int g3d[2][2][2] = {{{1, 2}, {3, 4}}, {{5, 6}, {7, 8}}};

int sum_2d(int a[][3], int rows) {
    int s = 0;
    int i, j;
    for (i = 0; i < rows; i++)
        for (j = 0; j < 3; j++)
            s += a[i][j];
    return s;
}

int main(void) {
    /* --- global 2D read --- */
    check("g2d[0][0]", g2d[0][0], 10);
    check("g2d[0][2]", g2d[0][2], 30);
    check("g2d[1][1]", g2d[1][1], 50);
    check("g2d[1][2]", g2d[1][2], 60);

    /* --- global 3D read --- */
    check("g3d[0][0][0]", g3d[0][0][0], 1);
    check("g3d[0][1][1]", g3d[0][1][1], 4);
    check("g3d[1][0][1]", g3d[1][0][1], 6);
    check("g3d[1][1][1]", g3d[1][1][1], 8);

    /* --- local 2D array, manual fill --- */
    int a[2][4];
    int i, j;
    for (i = 0; i < 2; i++)
        for (j = 0; j < 4; j++)
            a[i][j] = i * 4 + j;
    check("a[0][0]", a[0][0], 0);
    check("a[0][3]", a[0][3], 3);
    check("a[1][0]", a[1][0], 4);
    check("a[1][3]", a[1][3], 7);

    /* --- local 2D with brace initializer --- */
    int b[2][3] = {{1, 2, 3}, {4, 5, 6}};
    check("b[0][0]", b[0][0], 1);
    check("b[1][2]", b[1][2], 6);

    /* --- write then read --- */
    b[0][1] = 99;
    check("b[0][1] after write", b[0][1], 99);

    /* --- 3D local array --- */
    int c[2][2][2];
    c[0][0][0] = 10; c[0][0][1] = 20;
    c[0][1][0] = 30; c[0][1][1] = 40;
    c[1][0][0] = 50; c[1][0][1] = 60;
    c[1][1][0] = 70; c[1][1][1] = 80;
    check("c[0][0][0]", c[0][0][0], 10);
    check("c[1][1][1]", c[1][1][1], 80);
    check("c[1][0][1]", c[1][0][1], 60);

    /* --- pass 2D array to function --- */
    check("sum g2d", sum_2d(g2d, 2), 210);
    check("sum b",   sum_2d(b, 2),   1 + 99 + 3 + 4 + 5 + 6);

    printf("passed=%d  failed=%d\n", pass_count, fail_count);
    puts("=== done ===");
    return fail_count;
}

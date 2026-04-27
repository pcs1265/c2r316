/* test_array_bounds.c - array subscripting edge cases */

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

struct Point {
    int x;
    int y;
};

int main(void) {
    pass_count = 0;
    fail_count = 0;

    puts("=== test_array_bounds ===");

    /* 1. Simple 1D array bounds */
    int arr[5];
    arr[0] = 10;
    arr[1] = 20;
    arr[2] = 30;
    arr[3] = 40;
    arr[4] = 50;
    check("arr[0]", arr[0], 10);
    check("arr[1]", arr[1], 20);
    check("arr[2]", arr[2], 30);
    check("arr[3]", arr[3], 40);
    check("arr[4]", arr[4], 50);

    /* 2. Multi-dimensional array basic */
    int mat[3][3];
    mat[0][0] = 1; mat[0][1] = 2; mat[0][2] = 3;
    mat[1][0] = 4; mat[1][1] = 5; mat[1][2] = 6;
    mat[2][0] = 7; mat[2][1] = 8; mat[2][2] = 9;
    check("mat[0][0]", mat[0][0], 1);
    check("mat[0][1]", mat[0][1], 2);
    check("mat[1][0]", mat[1][0], 4);
    check("mat[2][2]", mat[2][2], 9);

    /* 3. Verify row-major order: mat[i][j] vs flat[i*COLS + j] */
    int flat[9];
    int i;
    int j;
    for (i = 0; i < 3; i = i + 1) {
        for (j = 0; j < 3; j = j + 1) {
            flat[i * 3 + j] = mat[i][j];
        }
    }
    check("flat[0]", flat[0], 1);
    check("flat[1]", flat[1], 2);
    check("flat[3]", flat[3], 4);
    check("flat[8]", flat[8], 9);

    /* 4. 3D array */
    int cube[2][2][2];
    cube[0][0][0] = 100;
    cube[0][0][1] = 101;
    cube[0][1][0] = 110;
    cube[0][1][1] = 111;
    cube[1][0][0] = 200;
    cube[1][0][1] = 201;
    cube[1][1][0] = 210;
    cube[1][1][1] = 211;
    check("cube[0][0][0]", cube[0][0][0], 100);
    check("cube[0][1][0]", cube[0][1][0], 110);
    check("cube[1][0][1]", cube[1][0][1], 201);
    check("cube[1][1][1]", cube[1][1][1], 211);

    /* 5. Array of structs */
    struct Point pts[3];
    pts[0].x = 1; pts[0].y = 2;
    pts[1].x = 3; pts[1].y = 4;
    pts[2].x = 5; pts[2].y = 6;
    check("pts[0].x", pts[0].x, 1);
    check("pts[0].y", pts[0].y, 2);
    check("pts[1].x", pts[1].x, 3);
    check("pts[2].y", pts[2].y, 6);

    /* 6. Array of arrays of structs */
    struct Point grid[2][2];
    grid[0][0].x = 1; grid[0][0].y = 2;
    grid[0][1].x = 3; grid[0][1].y = 4;
    grid[1][0].x = 5; grid[1][0].y = 6;
    grid[1][1].x = 7; grid[1][1].y = 8;
    check("grid[0][0].x", grid[0][0].x, 1);
    check("grid[0][1].y", grid[0][1].y, 4);
    check("grid[1][0].x", grid[1][0].x, 5);
    check("grid[1][1].y", grid[1][1].y, 8);

    /* 7. Variable index subscripting */
    int idx;
    int vals[5];
    vals[0] = 100;
    vals[1] = 200;
    vals[2] = 300;
    vals[3] = 400;
    vals[4] = 500;
    idx = 0;
    check("vals[idx] 0", vals[idx], 100);
    idx = 2;
    check("vals[idx] 2", vals[idx], 300);
    idx = 4;
    check("vals[idx] 4", vals[idx], 500);

    /* 8. Expression as index */
    check("vals[idx-2]", vals[idx-2], 300);
    check("vals[1+1]", vals[1+1], 300);

    /* 9. Character arrays */
    char str[6];
    str[0] = 'h';
    str[1] = 'e';
    str[2] = 'l';
    str[3] = 'l';
    str[4] = 'o';
    str[5] = 0;
    check("str[0]", str[0], 104);  /* 'h' */
    check("str[4]", str[4], 111);  /* 'o' */

    /* 10. Pointer to array element */
    int *p;
    p = &vals[2];
    check("*p", *p, 300);
    p = p + 1;
    check("*(p+1)", *p, 400);

    /* summary */
    puts("================");
    print_str("PASS: "); print_int(pass_count); putchar(10);
    print_str("FAIL: "); print_int(fail_count); putchar(10);
    puts("=== done ===");
    return 0;
}
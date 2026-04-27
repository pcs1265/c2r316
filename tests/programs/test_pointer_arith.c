/* test_pointer_arith.c - tests for pointer arithmetic scaling */

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

    puts("=== test_pointer_arith ===");

    /* 1. char pointer arithmetic - should scale by 1 */
    char carr[10];
    char *cp;
    cp = carr;
    check("char* init", cp - carr, 0);
    cp = cp + 1;
    check("char* + 1", cp - carr, 1);
    cp = cp + 5;
    check("char* + 5", cp - carr, 6);
    cp = carr + 9;
    check("char* + 9", cp - carr, 9);

    /* 2. int pointer arithmetic - should scale by 1 (1 word) */
    int iarr[10];
    int *ip;
    ip = iarr;
    check("int* init", ip - iarr, 0);
    ip = ip + 1;
    check("int* + 1", ip - iarr, 1);
    ip = ip + 5;
    check("int* + 5", ip - iarr, 6);

    /* 3. struct pointer arithmetic - should scale by struct size */
    struct Point parr[5];
    struct Point *pp;
    pp = parr;
    check("struct* init", pp - parr, 0);
    pp = pp + 1;
    check("struct* + 1", pp - parr, 1);
    pp = pp + 2;
    check("struct* + 2", pp - parr, 3);

    /* 4. pointer subtraction */
    int *ip1;
    int *ip2;
    ip1 = iarr + 3;
    ip2 = iarr + 7;
    check("ptr diff", ip2 - ip1, 4);

    /* 5. multi-level pointers */
    int a;
    int *ap;
    int **app;
    a = 42;
    ap = &a;
    app = &ap;
    check("int** deref", **app, 42);

    /* 6. pointer increment/decrement */
    int iarr2[5];
    int *p;
    p = iarr2;
    p[0] = 10;
    p[1] = 20;
    p[2] = 30;
    p = p + 1;
    check("p[0] after ++", p[0], 20);
    p = p - 1;
    check("p[0] after --", p[0], 10);

    /* 7. pointer with array subscript */
    int nums[5];
    nums[0] = 100;
    nums[1] = 200;
    nums[2] = 300;
    int *np;
    np = nums;
    check("np[0]", np[0], 100);
    check("np[1]", np[1], 200);
    check("np[2]", np[2], 300);

    /* 8. pointer arithmetic with sizeof */
    int vals[10];
    int *vp;
    vp = vals;
    check("sizeof(int)", sizeof(int), 1);
    check("sizeof(int*)", sizeof(int*), 1);

    /* summary */
    puts("================");
    print_str("PASS: "); print_int(pass_count); putchar(10);
    print_str("FAIL: "); print_int(fail_count); putchar(10);
    puts("=== done ===");
    return 0;
}
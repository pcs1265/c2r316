/* test_all.c - self-validating tests */

#include "runtime/stdlib.h"

/* ── test helpers ── */

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

/* ── recursive functions ── */
int factorial(int n) {
    if (n <= 1) return 1;
    return n * factorial(n - 1);
}

int fib(int n) {
    if (n <= 1) return n;
    return fib(n - 1) + fib(n - 2);
}

int array_sum(int *arr, int len) {
    int i;
    int sum;
    sum = 0;
    for (i = 0; i < len; i++) {
        sum += arr[i];
    }
    return sum;
}

void swap(int *a, int *b) {
    int tmp;
    tmp = *a;
    *a  = *b;
    *b  = tmp;
}

/* ── main ── */
int main(void) {
    pass_count = 0;
    fail_count = 0;

    puts("=== test_all ===");

    /* 1. arithmetic */
    check("3+4",      3 + 4,     7);
    check("10-3",     10 - 3,    7);
    check("6*7",      6 * 7,     42);
    check("20/4",     20 / 4,    5);
    check("17%5",     17 % 5,    2);
    check("0+0",      0 + 0,     0);
    check("0*99",     0 * 99,    0);
    check("1*1",      1 * 1,     1);
    check("100/1",    100 / 1,   100);
    check("100%1",    100 % 1,   0);
    check("7/7",      7 / 7,     1);
    check("7%7",      7 % 7,     0);
    check("1000/7",   1000 / 7,  142);
    check("1000%7",   1000 % 7,  6);
    check("255*255",  255 * 255, 65025);
    check("1+2+3",    1 + 2 + 3, 6);
    check("10-3-2",   10 - 3 - 2, 5);
    check("2*3+4",    2 * 3 + 4,  10);
    check("4+3*2",    4 + 3 * 2,  10);

    /* 2. bitwise */
    check("5&3",      5 & 3,      1);
    check("5|3",      5 | 3,      7);
    check("5^3",      5 ^ 3,      6);
    check("~0",       ~0,         65535);
    check("1<<4",     1 << 4,     16);
    check("32>>2",    32 >> 2,    8);
    check("0xFF&0x0F",0xFF & 0x0F,15);
    check("0xF0|0x0F",0xF0 | 0x0F,255);
    check("0xFF^0xFF",0xFF ^ 0xFF, 0);
    check("1<<0",     1 << 0,     1);
    check("1<<15",    1 << 15,    32768);
    check("32768>>15",32768 >> 15,1);
    check("0>>5",     0 >> 5,     0);
    check("~1",       ~1,         65534);

    /* 3. comparison / logical */
    check("3==3",   3 == 3,   1);
    check("3==4",   3 == 4,   0);
    check("3!=4",   3 != 4,   1);
    check("3!=3",   3 != 3,   0);
    check("2<5",    2 < 5,    1);
    check("5<2",    5 < 2,    0);
    check("5>2",    5 > 2,    1);
    check("2>5",    2 > 5,    0);
    check("3<=3",   3 <= 3,   1);
    check("4<=3",   4 <= 3,   0);
    check("3>=3",   3 >= 3,   1);
    check("2>=3",   2 >= 3,   0);
    check("&&T",    1 && 1,   1);
    check("&&F",    1 && 0,   0);
    check("||T",    0 || 1,   1);
    check("||F",    0 || 0,   0);
    check("!0",     !0,       1);
    check("!1",     !1,       0);

    /* 4. compound assignment */
    int x;
    x = 10;
    x += 5;  check("+=",  x, 15);
    x -= 3;  check("-=",  x, 12);
    x *= 2;  check("*=",  x, 24);
    x /= 4;  check("/=",  x, 6);
    x = 0xFF;
    x &= 5;  check("&=",  x, 5);
    x |= 8;  check("|=",  x, 13);
    x ^= 3;  check("^=",  x, 14);

    /* 5. prefix / postfix increment */
    int y;
    y = 5;
    check("++y", ++y, 6);
    check("y++", y++, 6);
    check("y",   y,   7);
    check("--y", --y, 6);

    /* 6. if/else */
    int a;
    a = 7;
    check("if>5", a > 5, 1);
    a = 3;
    check("if<5", a > 5, 0);

    /* 7. while + break + continue */
    int w;
    int wsum;
    w = 0;
    wsum = 0;
    while (w < 10) {
        w++;
        if (w == 3) continue;
        if (w == 7) break;
        wsum += w;
    }
    /* w goes 1,2,(skip 3),4,5,6,(break at 7) → sum = 1+2+4+5+6 = 18 */
    check("while", wsum, 18);

    /* 8. for */
    int fsum;
    int fi;
    fsum = 0;
    for (fi = 0; fi < 5; fi++) {
        fsum += fi;
    }
    check("for", fsum, 10);

    /* for with continue */
    int fsum2;
    fsum2 = 0;
    for (fi = 0; fi < 6; fi++) {
        if (fi == 3) continue;
        fsum2 += fi;
    }
    /* 0+1+2+4+5 = 12 */
    check("for+cont", fsum2, 12);

    /* nested for */
    int nsum;
    int ni;
    int nj;
    nsum = 0;
    for (ni = 0; ni < 3; ni++) {
        for (nj = 0; nj < 3; nj++) {
            nsum += 1;
        }
    }
    check("nested_for", nsum, 9);

    /* do-while */
    int dw;
    dw = 0;
    do {
        dw += 1;
    } while (dw < 5);
    check("do-while", dw, 5);

    /* do-while executes at least once */
    int dw2;
    dw2 = 0;
    do {
        dw2 = 42;
    } while (0);
    check("do-while0", dw2, 42);

    /* 9. recursion */
    check("5!",   factorial(5), 120);
    check("fib7", fib(7),       13);

    /* 10. arrays */
    int arr[5];
    arr[0] = 10;
    arr[1] = 20;
    arr[2] = 30;
    arr[3] = 40;
    arr[4] = 50;
    check("arr_sum",  array_sum(arr, 5), 150);
    check("arr[0]",   arr[0], 10);
    check("arr[4]",   arr[4], 50);

    /* pointer arithmetic */
    int *p2;
    p2 = arr;
    check("ptr[0]",   *p2,     10);
    check("ptr[1]",   *(p2+1), 20);
    check("ptr[4]",   *(p2+4), 50);
    p2 = p2 + 2;
    check("ptr+2",    *p2,     30);

    /* array write through pointer */
    *p2 = 99;
    check("ptr_wr",   arr[2],  99);
    arr[2] = 30;

    /* 11. pointers + swap */
    int p;
    int q;
    p = 11;
    q = 22;
    swap(&p, &q);
    check("swap_p", p, 22);
    check("swap_q", q, 11);

    /* 12. string functions */
    char *s1;
    char *s2;
    s1 = "hello";
    s2 = "hello";
    check("strlen5",   strlen(s1),        5);
    check("strlen0",   strlen(""),        0);
    check("strlen1",   strlen("x"),       1);
    check("strcmp_eq", strcmp(s1, s2),    0);
    check("strcmp_gt", strcmp("b","a")>0, 1);
    check("strcmp_lt", strcmp("a","b")<0, 1);
    check("strcmp_pre",strcmp("ab","a")>0,1);

    /* 13. char */
    char c;
    c = 65;
    check("char", c, 65);

    /* summary */
    puts("================");
    print_str("PASS: "); print_int(pass_count); putchar(10);
    print_str("FAIL: "); print_int(fail_count); putchar(10);
    puts("=== done ===");
    return 0;
}

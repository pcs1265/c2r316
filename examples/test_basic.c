/* test_basic.c - self-validating tests */

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

/* ── global variables ── */

int g_counter;
int g_accum;
int g_flag;

void g_reset(void) {
    g_counter = 0;
    g_accum   = 0;
    g_flag    = 0;
}

void g_increment(void) {
    g_counter = g_counter + 1;
    g_accum  += g_counter;
}

int g_get_counter(void) { return g_counter; }
int g_get_accum(void)   { return g_accum;   }

/* shared state mutated across two functions */
int g_shared;

void g_write(int v) { g_shared = v; }
int  g_read(void)   { return g_shared; }

/* global array */
int g_arr[4];

void g_arr_fill(void) {
    g_arr[0] = 1;
    g_arr[1] = 2;
    g_arr[2] = 4;
    g_arr[3] = 8;
}

int g_arr_sum(void) {
    return g_arr[0] + g_arr[1] + g_arr[2] + g_arr[3];
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

    puts("=== test_basic ===");

    /* 1. arithmetic — non-trivial cases only */
    check("6*7",      6 * 7,     42);
    check("17%5",     17 % 5,    2);
    check("1000/7",   1000 / 7,  142);
    check("1000%7",   1000 % 7,  6);
    check("255*255",  255 * 255, 65025);
    check("2*3+4",    2 * 3 + 4,  10);
    check("4+3*2",    4 + 3 * 2,  10);
    check("10-3-2",   10 - 3 - 2, 5);

    /* 2. bitwise */
    check("5&3",       5 & 3,       1);
    check("5|3",       5 | 3,       7);
    check("5^3",       5 ^ 3,       6);
    check("~0",        ~0,          65535);
    check("~1",        ~1,          65534);
    check("1<<4",      1 << 4,      16);
    check("1<<15",     1 << 15,     32768);
    check("32768>>15", 32768 >> 15, 1);
    check("0xFF&0x0F", 0xFF & 0x0F, 15);
    check("0xFF^0xFF", 0xFF ^ 0xFF, 0);

    /* 3. comparison / logical */
    check("3!=4",   3 != 4,   1);
    check("5>2",    5 > 2,    1);
    check("3<=3",   3 <= 3,   1);
    check("4<=3",   4 <= 3,   0);
    check("&&F",    1 && 0,   0);
    check("||T",    0 || 1,   1);
    check("!0",     !0,       1);
    check("ternary",      1 ? 10 : 20, 10);
    check("ternary_else", 0 ? 10 : 20, 20);

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
    x = 17;
    x %= 5;  check("%=",  x, 2);

    /* 5. prefix / postfix increment */
    int y;
    y = 5;
    check("++y", ++y, 6);
    check("y++", y++, 6);
    check("y",   y,   7);
    check("--y", --y, 6);

    /* 6. while + break + continue */
    int w;
    int wsum;
    w = 0; wsum = 0;
    while (w < 10) {
        w++;
        if (w == 3) continue;
        if (w == 7) break;
        wsum += w;
    }
    /* 1+2+(skip 3)+4+5+6+(break) = 18 */
    check("while", wsum, 18);

    /* 7. for + continue */
    int fsum;
    int fi;
    fsum = 0;
    for (fi = 0; fi < 6; fi++) {
        if (fi == 3) continue;
        fsum += fi;
    }
    /* 0+1+2+(skip 3)+4+5 = 12 */
    check("for+cont", fsum, 12);

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

    /* do-while executes at least once */
    int dw;
    dw = 0;
    do { dw = 42; } while (0);
    check("do-while0", dw, 42);

    /* 8. recursion */
    check("5!",   factorial(5), 120);
    check("fib7", fib(7),       13);

    /* 9. arrays + pointer arithmetic */
    int arr[5];
    arr[0] = 10; arr[1] = 20; arr[2] = 30; arr[3] = 40; arr[4] = 50;
    check("arr_sum",  array_sum(arr, 5), 150);

    int *p2;
    p2 = arr;
    check("ptr[1]",  *(p2+1), 20);
    p2 = p2 + 2;
    check("ptr+2",   *p2,     30);
    *p2 = 99;
    check("ptr_wr",  arr[2],  99);
    arr[2] = 30;

    /* 10. pointers + swap */
    int p;
    int q;
    p = 11; q = 22;
    swap(&p, &q);
    check("swap_p", p, 22);
    check("swap_q", q, 11);

    /* 11. string functions */
    char *s1;
    char *s2;
    s1 = "hello";
    s2 = "hello";
    check("strlen5",    strlen(s1),         5);
    check("strcmp_eq",  strcmp(s1, s2),     0);
    check("strcmp_gt",  strcmp("b","a")>0,  1);
    check("strcmp_pre", strcmp("ab","a")>0, 1);

    /* 12. global variables */
    g_reset();
    check("g_reset_ctr",  g_get_counter(), 0);
    check("g_reset_acc",  g_get_accum(),   0);

    g_increment();
    g_increment();
    g_increment();
    /* counter: 1→2→3; accum: 1+2+3 = 6 */
    check("g_counter",    g_get_counter(), 3);
    check("g_accum",      g_get_accum(),   6);

    g_write(1234);
    check("g_shared_wr",  g_read(), 1234);
    g_write(g_read() + 1);
    check("g_shared_inc", g_read(), 1235);

    g_arr_fill();
    check("g_arr_sum",    g_arr_sum(), 15);
    g_arr[2] = 0;
    check("g_arr_write",  g_arr_sum(), 11);

    /* global survives across unrelated local call */
    g_write(99);
    factorial(5);
    check("g_after_call", g_read(), 99);

    /* global flag toggled via ternary */
    g_flag = 0;
    g_flag = g_flag ? 0 : 1;
    check("g_flag_toggle", g_flag, 1);
    g_flag = g_flag ? 0 : 1;
    check("g_flag_toggle2", g_flag, 0);

    /* summary */
    puts("================");
    print_str("PASS: "); print_int(pass_count); putchar(10);
    print_str("FAIL: "); print_int(fail_count); putchar(10);
    puts("=== done ===");
    return 0;
}

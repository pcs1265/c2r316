/* test_all.c - self-validating tests */

void putchar(int c);
void print_int(int n);
void print_uint(int n);
void print_hex(int n);
void puts(char *s);
void print_str(char *s);
int  getchar(void);
int  strlen(char *s);
int  strcmp(char *a, char *b);
void memset(char *dst, int val, int n);
void memcpy(char *dst, char *src, int n);

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
    check("3+4",   3 + 4,   7);
    check("10-3",  10 - 3,  7);
    check("6*7",   6 * 7,   42);
    check("20/4",  20 / 4,  5);
    check("17%5",  17 % 5,  2);

    /* 2. bitwise */
    check("5&3",   5 & 3,   1);
    check("5|3",   5 | 3,   7);
    check("5^3",   5 ^ 3,   6);
    check("~0",    ~0,      65535);
    check("1<<4",  1 << 4,  16);
    check("32>>2", 32 >> 2, 8);

    /* 3. comparison / logical */
    check("3==3",  3 == 3,  1);
    check("3!=4",  3 != 4,  1);
    check("2<5",   2 < 5,   1);
    check("5>2",   5 > 2,   1);
    check("&&",    1 && 1,  1);
    check("||",    0 || 1,  1);
    check("!",     !0,      1);

    /* 4. compound assignment */
    int x;
    x = 10;
    x += 5;  check("+=", x, 15);
    x -= 3;  check("-=", x, 12);
    x *= 2;  check("*=", x, 24);
    x /= 4;  check("/=", x, 6);
    x &= 5;  check("&=", x, 4);
    x |= 8;  check("|=", x, 12);
    x ^= 3;  check("^=", x, 15);

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
    check("sum", array_sum(arr, 5), 150);

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
    check("strlen", strlen(s1),     5);
    check("strcmp", strcmp(s1, s2), 0);

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

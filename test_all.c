/* test_all.c - 현재 지원 기능 전체 테스트 */

/* 런타임 함수 선언 */
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

/* ── 헬퍼 ── */
void newline(void) {
    putchar(10);
}

void print_label(char *s) {
    print_str(s);
    print_str(": ");
}

void print_ok(void) {
    puts("OK");
}

/* ── 재귀: 팩토리얼 ── */
int factorial(int n) {
    if (n <= 1) return 1;
    return n * factorial(n - 1);
}

/* ── 재귀: 피보나치 ── */
int fib(int n) {
    if (n <= 1) return n;
    return fib(n - 1) + fib(n - 2);
}

/* ── 배열 합산 ── */
int array_sum(int *arr, int len) {
    int i;
    int sum;
    sum = 0;
    for (i = 0; i < len; i++) {
        sum += arr[i];
    }
    return sum;
}

/* ── 포인터로 스왑 ── */
void swap(int *a, int *b) {
    int tmp;
    tmp = *a;
    *a  = *b;
    *b  = tmp;
}

/* ── main ── */
int main(void) {

    /* 1. 기본 출력 */
    puts("=== test_all ===");

    /* 2. 사칙연산 */
    print_label("3+4");   print_int(3 + 4);   newline();
    print_label("10-3");  print_int(10 - 3);  newline();
    print_label("6*7");   print_int(6 * 7);   newline();
    print_label("20/4");  print_int(20 / 4);  newline();
    print_label("17%5");  print_int(17 % 5);  newline();

    /* 3. 비트 연산 */
    print_label("5&3");   print_int(5 & 3);   newline();
    print_label("5|3");   print_int(5 | 3);   newline();
    print_label("5^3");   print_int(5 ^ 3);   newline();
    print_label("~0");    print_int(~0);       newline();
    print_label("1<<4");  print_int(1 << 4);  newline();
    print_label("32>>2"); print_int(32 >> 2); newline();

    /* 4. 비교 / 논리 */
    print_label("3==3");  print_int(3 == 3);  newline();
    print_label("3!=4");  print_int(3 != 4);  newline();
    print_label("2<5");   print_int(2 < 5);   newline();
    print_label("5>2");   print_int(5 > 2);   newline();
    print_label("&&");    print_int(1 && 1);  newline();
    print_label("||");    print_int(0 || 1);  newline();
    print_label("!");     print_int(!0);      newline();

    /* 5. 복합 대입 */
    int x;
    x = 10;
    x += 5;  print_label("+="); print_int(x); newline();
    x -= 3;  print_label("-="); print_int(x); newline();
    x *= 2;  print_label("*="); print_int(x); newline();
    x /= 4;  print_label("/="); print_int(x); newline();
    x &= 5;  print_label("&="); print_int(x); newline();
    x |= 8;  print_label("|="); print_int(x); newline();
    x ^= 3;  print_label("^="); print_int(x); newline();

    /* 6. 전위 / 후위 증감 */
    int y;
    y = 5;
    print_label("++y"); print_int(++y); newline();
    print_label("y++"); print_int(y++); newline();
    print_label("y");   print_int(y);   newline();
    print_label("--y"); print_int(--y); newline();

    /* 7. if / else */
    int a;
    a = 7;
    if (a > 5) {
        print_str("if:T"); newline();
    } else {
        print_str("if:F"); newline();
    }

    /* 8. while + break + continue */
    int w;
    w = 0;
    print_str("while:");
    while (w < 10) {
        w++;
        if (w == 3) continue;
        if (w == 7) break;
        print_int(w);
        putchar(' ');
    }
    newline();

    /* 9. for */
    print_str("for:");
    int fi;
    for (fi = 0; fi < 5; fi++) {
        print_int(fi);
        putchar(' ');
    }
    newline();

    /* 10. 재귀: 팩토리얼 */
    print_label("5!");   print_int(factorial(5));  newline();
    print_label("fib7"); print_int(fib(7));        newline();

    /* 11. 배열 */
    int arr[5];
    arr[0] = 10;
    arr[1] = 20;
    arr[2] = 30;
    arr[3] = 40;
    arr[4] = 50;
    print_label("sum"); print_int(array_sum(arr, 5)); newline();

    /* 12. 포인터 + swap */
    int p;
    int q;
    p = 11;
    q = 22;
    swap(&p, &q);
    print_label("p"); print_int(p); newline();
    print_label("q"); print_int(q); newline();

    /* 13. 문자열 함수 */
    char *s1;
    char *s2;
    s1 = "hello";
    s2 = "hello";
    print_label("len");  print_int(strlen(s1));      newline();
    print_label("cmp");  print_int(strcmp(s1, s2));  newline();

    /* 14. print_hex */
    print_label("hex"); print_hex(0xABCD); newline();

    /* 15. char */
    char c;
    c = 'Z';
    print_label("chr"); putchar(c); newline();

    puts("=== done ===");
    return 0;
}

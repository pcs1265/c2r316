/* test_all.c - Full feature test for the C->R316 compiler */

#include "../runtime/r316.h"

/* ── Helpers ── */
void newline(void) {
    putchar('\n');
}

void print_label(char *s) {
    print_str(s);
    print_str(": ");
}

/* ── Recursion: factorial ── */
int factorial(int n) {
    if (n <= 1) return 1;
    return n * factorial(n - 1);
}

/* ── Recursion: fibonacci ── */
int fib(int n) {
    if (n <= 1) return n;
    return fib(n - 1) + fib(n - 2);
}

/* ── Array sum ── */
int array_sum(int *arr, int len) {
    int i;
    int sum;
    sum = 0;
    for (i = 0; i < len; i++) {
        sum += arr[i];
    }
    return sum;
}

/* ── Pointer swap ── */
void swap(int *a, int *b) {
    int tmp;
    tmp = *a;
    *a  = *b;
    *b  = tmp;
}

/* ── do-while sum ── */
int do_while_sum(int n) {
    int sum = 0;
    do {
        sum += n;
        n--;
    } while (n > 0);
    return sum;
}

/* ── switch dispatch ── */
int switch_val(int x) {
    int result = 0;
    switch (x) {
        case 0: result = 10; break;
        case 1: result = 20; break;
        default: result = 99; break;
    }
    return result;
}

/* ── goto counter ── */
int goto_count(void) {
    int i = 0;
loop:
    i++;
    if (i < 5) goto loop;
    return i;
}

/* ── enum ── */
enum Color { RED = 0, GREEN, BLUE };

int enum_val(void) {
    return GREEN;
}

/* ── typedef ── */
typedef int myint;

myint typedef_add(myint a, myint b) {
    return a + b;
}

/* ── main ── */
int main(void) {

    /* 1. Basic output */
    puts("=== test_all ===");

    /* 2. Arithmetic */
    print_label("3+4");   print_int(3 + 4);   newline();
    print_label("10-3");  print_int(10 - 3);  newline();
    print_label("6*7");   print_int(6 * 7);   newline();
    print_label("20/4");  print_int(20 / 4);  newline();
    print_label("17%5");  print_int(17 % 5);  newline();

    /* 3. Bitwise */
    print_label("5&3");   print_int(5 & 3);   newline();
    print_label("5|3");   print_int(5 | 3);   newline();
    print_label("5^3");   print_int(5 ^ 3);   newline();
    print_label("~0");    print_int(~0);       newline();
    print_label("1<<4");  print_int(1 << 4);  newline();
    print_label("32>>2"); print_int(32 >> 2); newline();

    /* 4. Comparison / logical */
    print_label("3==3");  print_int(3 == 3);  newline();
    print_label("3!=4");  print_int(3 != 4);  newline();
    print_label("2<5");   print_int(2 < 5);   newline();
    print_label("5>2");   print_int(5 > 2);   newline();
    print_label("&&");    print_int(1 && 1);  newline();
    print_label("||");    print_int(0 || 1);  newline();
    print_label("!");     print_int(!0);      newline();

    /* 5. Compound assignment */
    int x;
    x = 10;
    x += 5;  print_label("+="); print_int(x); newline();
    x -= 3;  print_label("-="); print_int(x); newline();
    x *= 2;  print_label("*="); print_int(x); newline();
    x /= 4;  print_label("/="); print_int(x); newline();
    x &= 5;  print_label("&="); print_int(x); newline();
    x |= 8;  print_label("|="); print_int(x); newline();
    x ^= 3;  print_label("^="); print_int(x); newline();

    /* 6. Prefix / postfix increment */
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

    /* 10. do-while */
    print_label("dowhile"); print_int(do_while_sum(4)); newline();

    /* 11. switch */
    print_label("sw0"); print_int(switch_val(0)); newline();
    print_label("sw1"); print_int(switch_val(1)); newline();
    print_label("sw9"); print_int(switch_val(9)); newline();

    /* 12. goto */
    print_label("goto"); print_int(goto_count()); newline();

    /* 13. enum */
    print_label("enum"); print_int(enum_val()); newline();

    /* 14. typedef */
    print_label("typedef"); print_int(typedef_add(3, 4)); newline();

    /* 15. Recursion: factorial / fibonacci */
    print_label("5!");   print_int(factorial(5));  newline();
    print_label("fib7"); print_int(fib(7));        newline();

    /* 16. Array */
    int arr[5];
    arr[0] = 10; arr[1] = 20; arr[2] = 30; arr[3] = 40; arr[4] = 50;
    print_label("sum"); print_int(array_sum(arr, 5)); newline();

    /* 17. Local array init */
    int arr2[] = {1, 2, 3};
    print_label("arr2"); print_int(arr2[2]); newline();

    /* 18. Pointer + swap */
    int p; int q;
    p = 11; q = 22;
    swap(&p, &q);
    print_label("p"); print_int(p); newline();
    print_label("q"); print_int(q); newline();

    /* 19. String functions */
    char *s1; char *s2;
    s1 = "hello"; s2 = "hello";
    print_label("len");  print_int(strlen(s1));      newline();
    print_label("cmp");  print_int(strcmp(s1, s2));  newline();

    /* 20. print_hex */
    print_label("hex"); print_hex(0xABCD); newline();

    /* 21. char */
    char c;
    c = 'Z';
    print_label("chr"); putchar(c); newline();

    /* 22. Header macros (MIN, MAX, ABS, CLAMP) */
    print_label("MIN");   print_int(MIN(3, 7));         newline();
    print_label("MAX");   print_int(MAX(3, 7));         newline();
    print_label("ABS");   print_int(ABS(-5));           newline();
    print_label("CLAMP"); print_int(CLAMP(15, 0, 10)); newline();

    puts("=== done ===");
    return 0;
}

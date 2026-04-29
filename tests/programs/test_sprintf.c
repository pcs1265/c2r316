/* test_sprintf.c — verify sprintf, snprintf, fprintf, fscanf, fflush, ungetc */

#include <stdio.h>

int pass_count;
int fail_count;

void check_str(char *name, char *got, char *exp) {
    int i;
    int ok;
    ok = 1;
    i = 0;
    while (exp[i]) {
        if (got[i] != exp[i]) { ok = 0; break; }
        i++;
    }
    if (ok && got[i] != 0) ok = 0;
    if (ok) {
        print_str(name); puts(": PASS");
        pass_count++;
    } else {
        print_str(name); puts(": FAIL");
        print_str("  got: "); puts(got);
        print_str("  exp: "); puts(exp);
        fail_count++;
    }
}

void check(char *name, int got, int expected) {
    if (got == expected) {
        print_str(name); puts(": PASS");
        pass_count++;
    } else {
        print_str(name); puts(": FAIL");
        print_str("  got: "); print_int(got); putchar(10);
        print_str("  exp: "); print_int(expected); putchar(10);
        fail_count++;
    }
}

int main(void) {
    char buf[32];
    int n;
    int x;

    puts("=== test_sprintf ===");

    /* sprintf basic */
    n = sprintf(buf, "hello %d", 42);
    check("sprintf_ret", n, 8);
    check_str("sprintf_str", buf, "hello 42");

    /* sprintf %s */
    n = sprintf(buf, "%s!", "world");
    check_str("sprintf_s", buf, "world!");

    /* sprintf %x */
    sprintf(buf, "%x", 255);
    check_str("sprintf_x", buf, "ff");

    /* snprintf fits */
    n = snprintf(buf, 32, "%d+%d=%d", 1, 2, 3);
    check("snprintf_ret", n, 5);
    check_str("snprintf_str", buf, "1+2=3");

    /* snprintf truncation */
    n = snprintf(buf, 4, "abcdef");
    check("snprintf_trunc_ret", n, 6);
    check_str("snprintf_trunc_buf", buf, "abc");

    /* fprintf (writes to terminal, return value) */
    n = fprintf(stdout, "fprintf:%d\n", 7);
    check("fprintf_ret", n, 10);

    /* fflush no-op */
    n = fflush(stdout);
    check("fflush_ret", n, 0);

    /* ungetc + getchar */
    ungetc('Z', stdin);
    x = getchar();
    check("ungetc_getchar", x, 'Z');

    /* fscanf %d */
    fscanf(stdin, "%d", &x);
    check("fscanf_d", x, 99);

    puts("===================");
    print_int(pass_count); putchar(10);
    print_int(fail_count); putchar(10);
    puts("=== done ===");
    return 0;
}

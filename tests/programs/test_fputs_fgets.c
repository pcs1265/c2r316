/* test_fputs_fgets.c — verify fputs and fgets */

#include <stdio.h>

int pass_count;
int fail_count;

void check(char *name, int got, int expected) {
    if (got == expected) {
        print_str(name);
        puts(": PASS");
        pass_count++;
    } else {
        print_str(name);
        puts(": FAIL");
        print_str("  got: "); print_int(got); putchar(10);
        print_str("  exp: "); print_int(expected); putchar(10);
        fail_count++;
    }
}

int main(void) {
    char buf[32];
    char *ret;
    int r;

    puts("=== test_fputs_fgets ===");

    /* fputs to stdout — no trailing newline added */
    r = fputs("hello\n", stdout);
    check("fputs_ret", r, 0);

    /* fputs to stderr — maps to same terminal */
    r = fputs("err\n", stderr);
    check("fputs_stderr_ret", r, 0);

    /* fgets — reads "world\n" from stdin */
    ret = fgets(buf, 32, stdin);
    check("fgets_ret_nonnull", ret != 0, 1);
    check("fgets_buf_0", buf[0], 'w');
    check("fgets_buf_1", buf[1], 'o');
    check("fgets_buf_2", buf[2], 'r');
    check("fgets_buf_3", buf[3], 'l');
    check("fgets_buf_4", buf[4], 'd');
    check("fgets_buf_5", buf[5], '\n');
    check("fgets_buf_6", buf[6], 0);

    /* fgets — truncation: only n-1 chars stored */
    ret = fgets(buf, 4, stdin);
    check("fgets_trunc_ret", ret != 0, 1);
    check("fgets_trunc_0", buf[0], 'a');
    check("fgets_trunc_1", buf[1], 'b');
    check("fgets_trunc_2", buf[2], 'c');
    check("fgets_trunc_3", buf[3], 0);

    puts("=======================");
    print_int(pass_count); putchar(10);
    print_int(fail_count); putchar(10);
    puts("=== done ===");
    return 0;
}

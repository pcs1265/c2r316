/* test_scanf.c — verify scanf %d %u %x %c %s */

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

int main() {
    int d;
    unsigned int u;
    unsigned int x;
    long ld;
    unsigned long lu;
    unsigned long lx;
    int c;
    char s[16];
    int ret;

    puts("=== test_scanf ===");

    /* %d positive */
    ret = scanf("%d", &d);
    check("scanf_ret_d", ret, 1);
    check("scanf_d_pos", d, 42);

    /* %d negative */
    ret = scanf("%d", &d);
    check("scanf_d_neg", d, -7);

    /* %u */
    ret = scanf("%u", &u);
    check("scanf_u", u, 65535);

    /* %x */
    ret = scanf("%x", &x);
    check("scanf_x", x, 0xFF);

    /* %ld */
    ret = scanf("%ld", &ld);
    check("scanf_ld_ret", ret, 1);
    check("scanf_ld", ld == -70000, 1);

    /* %lu */
    ret = scanf("%lu", &lu);
    check("scanf_lu_ret", ret, 1);
    check("scanf_lu", lu == 305419896UL, 1);

    /* %lx */
    ret = scanf("%lx", &lx);
    check("scanf_lx_ret", ret, 1);
    check("scanf_lx", lx == 0x12345678, 1);

    /* %c */
    ret = scanf(" %c", &c);
    check("scanf_c", c, 'A');

    /* %s */
    ret = scanf("%s", s);
    check("scanf_s_ret", ret, 1);
    check("scanf_s_0", s[0], 'h');
    check("scanf_s_1", s[1], 'i');
    check("scanf_s_2", s[2], 0);

    /* multiple in one call */
    ret = scanf("%d %d", &d, &c);
    check("scanf_multi_ret", ret, 2);
    check("scanf_multi_0", d, 10);
    check("scanf_multi_1", c, 20);

    puts("================");
    print_int(pass_count); putchar(10);
    print_int(fail_count); putchar(10);
    puts("=== done ===");
    return 0;
}

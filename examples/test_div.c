/* test_div.c - Comprehensive division and modulo tests */

#include "runtime/stdlib.h"

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

int main(void) {
    pass_count = 0;
    fail_count = 0;

    puts("=== test_div ===");

    /* Basic division */
    check("10 / 2", 10 / 2, 5);
    check("10 / 3", 10 / 3, 3);
    check("10 / 10", 10 / 10, 1);
    check("10 / 1", 10 / 1, 10);
    check("0 / 5", 0 / 5, 0);

    /* Basic modulo */
    check("10 % 2", 10 % 2, 0);
    check("10 % 3", 10 % 3, 1);
    check("10 % 10", 10 % 10, 0);
    check("10 % 1", 10 % 1, 0);
    check("0 % 5", 0 % 5, 0);

    /* Larger numbers */
    check("1000 / 7", 1000 / 7, 142);
    check("1000 % 7", 1000 % 7, 6);
    check("32767 / 1", 32767 / 1, 32767);
    check("32767 % 1", 32767 % 1, 0);
    check("32767 / 2", 32767 / 2, 16383);
    check("32767 % 2", 32767 % 2, 1);

    /* Unsigned-like behavior (R316 ints are effectively unsigned in many contexts) */
    /* 65535 is 0xFFFF */
    check("65535 / 1", 65535 / 1, 65535);
    check("65535 / 2", 65535 / 2, 32767);
    check("65535 % 2", 65535 % 2, 1);
    check("65535 / 256", 65535 / 256, 255);
    check("65535 % 256", 65535 % 256, 255);

    /* Power of 2 */
    check("1024 / 2", 1024 / 2, 512);
    check("1024 / 4", 1024 / 4, 256);
    check("1024 / 8", 1024 / 8, 128);
    check("1024 / 16", 1024 / 16, 64);
    check("1024 / 32", 1024 / 32, 32);
    check("1024 / 64", 1024 / 64, 16);
    check("1024 / 128", 1024 / 128, 8);
    check("1024 / 256", 1024 / 256, 4);
    check("1024 / 512", 1024 / 512, 2);
    check("1024 / 1024", 1024 / 1024, 1);

    /* Modulo with powers of 2 */
    check("1023 % 2", 1023 % 2, 1);
    check("1023 % 4", 1023 % 4, 3);
    check("1023 % 8", 1023 % 8, 7);
    check("1023 % 16", 1023 % 16, 15);
    check("1023 % 32", 1023 % 32, 31);
    check("1023 % 64", 1023 % 64, 63);
    check("1023 % 128", 1023 % 128, 127);
    check("1023 % 256", 1023 % 256, 255);
    check("1023 % 512", 1023 % 512, 511);
    check("1023 % 1024", 1023 % 1024, 1023);

    /* Prime numbers */
    check("13 / 5", 13 / 5, 2);
    check("13 % 5", 13 % 5, 3);
    check("17 / 13", 17 / 13, 1);
    check("17 % 13", 17 % 13, 4);
    check("19 / 3", 19 / 3, 6);
    check("19 % 3", 19 % 3, 1);

    /* Compound assignment */
    int x;
    x = 100;
    x /= 3;
    check("100 /= 3", x, 33);
    x = 100;
    x %= 3;
    check("100 %= 3", x, 1);

    /* Multiple operations */
    check("(100 / 2) / 2", (100 / 2) / 2, 25);
    check("(100 % 30) % 7", (100 % 30) % 7, 3);
    check("100 / (2 * 2)", 100 / (2 * 2), 25);

    /* Summary */
    puts("================");
    print_str("PASS: "); print_int(pass_count); putchar(10);
    print_str("FAIL: "); print_int(fail_count); putchar(10);
    puts("=== done ===");

    return 0;
}

/* test_integer_promo.c - tests for integer promotion rules */

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

void check_u(char *name, unsigned int got, unsigned int expected) {
    if (got == expected) {
        print_str(name);
        puts(": PASS");
        pass_count = pass_count + 1;
    } else {
        print_str(name);
        print_str(": FAIL got=");
        print_uint(got);
        print_str(" exp=");
        print_uint(expected);
        putchar(10);
        fail_count = fail_count + 1;
    }
}

int main(void) {
    pass_count = 0;
    fail_count = 0;

    puts("=== test_integer_promo ===");

    /* 1. char + char should promote to int */
    char a;
    char b;
    int result;
    a = 100;
    b = 50;
    result = a + b;
    check("char+char", result, 150);

    /* 2. char arithmetic overflow (should wrap as int then truncate) */
    a = 127;
    b = 1;
    result = a + b;  /* 128 as int, but stored as int it's fine */
    check("char 127+1", result, 128);

    /* 3. unsigned char to int promotion */
    unsigned char uc;
    uc = 255;
    result = uc + 1;  /* 256 as int */
    check("uchar 255+1", result, 256);

    /* 4. char promotion (unsigned char behavior - zero-extends) */
    char c;
    c = -1;  /* 0xFF = 255 */
    result = c + 0;  /* char is unsigned in this compiler, promotes to 255 */
    check("char -1", result, 255);  /* 255, not -1 (char is unsigned) */

    /* 5. char multiplication */
    a = 10;
    b = 10;
    result = a * b;
    check("char*char", result, 100);

    /* 6. mixed char and int */
    a = 50;
    result = a + 100;
    check("char+int", result, 150);

    /* 7. short arithmetic */
    short s1;
    short s2;
    s1 = 1000;
    s2 = 2000;
    result = s1 + s2;
    check("short+short", result, 3000);

    /* 8. unsigned short arithmetic */
    unsigned short us;
    us = 50000;
    result = us + 1;
    check("ushort+1", result, 50001);

    /* 9. mixed signedness */
    int si;
    unsigned int ui;
    si = -1;
    ui = 1;
    /* -1 + 1u should yield 0u (unsigned arithmetic) */
    check_u("int+uint", si + ui, 0);

    /* 10. char negation */
    a = 5;
    result = -a;
    check("char negate", result, -5);

    /* 11. char comparison */
    a = 10;
    b = 20;
    check("char cmp <", a < b, 1);
    check("char cmp >", a > b, 0);

    /* 12. bitwise operations on char */
    a = 0x0F;
    b = 0xF0;
    result = a | b;
    check("char|char", result, 0xFF);
    result = a & b;
    check("char&char", result, 0);
    result = a ^ b;
    check("char^char", result, 0xFF);

    /* 13. shift operations on char */
    a = 1;
    result = a << 4;
    check("char<<4", result, 16);
    a = 16;
    result = a >> 2;
    check("char>>2", result, 4);

    /* 14. char in condition */
    a = 0;
    if (a) {
        check("char cond 0", 0, 1);  /* should not execute */
    } else {
        check("char cond 0", 1, 1);  /* should execute */
    }
    a = 42;
    if (a) {
        check("char cond 42", 1, 1);  /* should execute */
    } else {
        check("char cond 42", 0, 1);  /* should not execute */
    }

    /* 15. int/long usual arithmetic conversions */
    long l;
    unsigned long ul;
    l = 0x10000;
    result = (l + 5) == 0x10005;
    check("long+int promotes", result, 1);
    result = (5 + l) == 0x10005;
    check("int+long promotes", result, 1);

    /* 16. unsigned int promotes into long without losing high half */
    ui = 0xFFFF;
    result = (l + ui) == 0x1FFFF;
    check("long+uint promotes", result, 1);

    /* 17. unsigned long dominates mixed signedness */
    ul = 0xFFFFFFFF;
    l = -1;
    result = ul == l;
    check("ulong==long bits", result, 1);
    ul = 1;
    result = l < ul;
    check("long<ulong unsigned", result, 0);

    /* 18. assignment still performs explicit destination conversion */
    l = 0x12345678;
    result = l;
    check("long assign int trunc", result, 0x5678);

    /* summary */
    puts("================");
    print_str("PASS: "); print_int(pass_count); putchar(10);
    print_str("FAIL: "); print_int(fail_count); putchar(10);
    puts("=== done ===");
    return 0;
}

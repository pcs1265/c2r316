/* test_long.c - self-validating tests for long and unsigned long */

#include <stdio.h>

int pass_count;
int fail_count;

long g_long = 0x12345678;
unsigned long g_ulong = 0x87654321;
long g_long_arr[3] = { 0x10000, 0x20000, 0x30000 };

struct LongBox {
    int tag;
    long value;
    unsigned long uvalue;
};

struct LongBox g_box;

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

long id_long(long x) {
    return x;
}

unsigned long id_ulong(unsigned long x) {
    return x;
}

int eq_long(long x, long y) {
    return x == y;
}

int eq_ulong(unsigned long x, unsigned long y) {
    return x == y;
}

int split_reg_stack_args(int a, int b, int c, int d, int e, long x) {
    return a == 1 && b == 2 && c == 3 && d == 4 && e == 5 && x == 0x12345678;
}

int stack_long_args(int a, int b, int c, int d, int e, int f, long x, unsigned long y) {
    return a == 1 && b == 2 && c == 3 && d == 4 && e == 5 && f == 6 &&
           x == 0x12345678 && y == 0x87654321;
}

long static_long_next(void) {
    static long value = 0xFFFF;
    value = value + 1;
    return value;
}

int main(void) {
    long la;
    long lb;
    long lc;
    unsigned long ua;
    unsigned long ub;
    long arr[3];
    long *lp;
    struct LongBox box;
    int i;
    int (*pred)(long, long);

    pass_count = 0;
    fail_count = 0;

    puts("=== test_long ===");

    la = 0x12345678;
    check("long const full", la == 0x12345678, 1);
    i = la;
    check("long to int low", i, 0x5678);

    ua = 0x87654321;
    check("ulong const full", ua == 0x87654321, 1);
    i = ua;
    check("ulong to int low", i, 0x4321);

    la = 0xFFFF;
    la = la + 1;
    check("long add carry", la == 0x10000, 1);

    la += 0x20000;
    check("long add assign", la == 0x30000, 1);

    la = 0x30000;
    la = la - 1;
    check("long sub borrow", la == 0x2FFFF, 1);

    la -= 0xFFFF;
    check("long sub assign", la == 0x20000, 1);

    la = 0x10000;
    lb = 3;
    lc = la * lb;
    check("long mul high", lc == 0x30000, 1);

    lc = 0x10000;
    lc *= 3;
    check("long mul assign", lc == 0x30000, 1);

    la = -70000;
    check("signed long div", (la / 10) == -7000, 1);

    la = -70003;
    check("signed long mod", (la % 10) == -3, 1);

    ua = 0x12345678;
    check("ulong div", (ua / 0x10000) == 0x1234, 1);
    check("ulong mod", (ua % 0x10000) == 0x5678, 1);

    ua = 0x12345678;
    ua /= 0x10000;
    check("ulong div assign", ua == 0x1234, 1);

    ua = 0x12345678;
    ua %= 0x10000;
    check("ulong mod assign", ua == 0x5678, 1);

    ua = 0xFFFFFFFF;
    ub = 0x7FFFFFFF;
    check("ulong compare", ua > ub, 1);

    la = -1;
    lb = 1;
    check("signed compare", la < lb, 1);

    la = 0x10000;
    if (la) {
        check("long condition high", 1, 1);
    } else {
        check("long condition high", 0, 1);
    }

    check("long return", id_long(0x12345678) == 0x12345678, 1);
    check("ulong return", id_ulong(0x87654321) == 0x87654321, 1);
    check("long args", eq_long(0x10000, 0x10000), 1);
    check("ulong args", eq_ulong(0x87654321, 0x87654321), 1);
    check("split reg stack", split_reg_stack_args(1, 2, 3, 4, 5, 0x12345678), 1);
    check("stack long args", stack_long_args(1, 2, 3, 4, 5, 6, 0x12345678, 0x87654321), 1);

    pred = eq_long;
    check("func ptr long", pred(0x12345678, 0x12345678), 1);

    check("global long init", g_long == 0x12345678, 1);
    check("global ulong init", g_ulong == 0x87654321, 1);
    g_long = g_long + 0x10000;
    g_ulong = g_ulong - 0x10000;
    check("global long write", g_long == 0x12355678, 1);
    check("global ulong write", g_ulong == 0x87644321, 1);

    arr[0] = 0x10000;
    arr[1] = 0x20000;
    arr[2] = arr[0] + arr[1];
    check("local long array", arr[2] == 0x30000, 1);

    lp = &arr[1];
    check("long pointer load", *lp == 0x20000, 1);
    lp[1] = 0x40000;
    check("long pointer store", arr[2] == 0x40000, 1);

    check("global long array 0", g_long_arr[0] == 0x10000, 1);
    check("global long array 2", g_long_arr[2] == 0x30000, 1);
    g_long_arr[1] = g_long_arr[1] + 0x10000;
    check("global long array write", g_long_arr[1] == 0x30000, 1);

    box.tag = 7;
    box.value = 0x12345678;
    box.uvalue = 0x87654321;
    check("struct long field", box.value == 0x12345678, 1);
    check("struct ulong field", box.uvalue == 0x87654321, 1);
    check("struct int neighbor", box.tag, 7);

    g_box.tag = 9;
    g_box.value = box.value + 0x10000;
    g_box.uvalue = box.uvalue - 0x10000;
    check("global struct long", g_box.value == 0x12355678, 1);
    check("global struct ulong", g_box.uvalue == 0x87644321, 1);
    check("global struct int", g_box.tag, 9);

    check("static long 1", static_long_next() == 0x10000, 1);
    check("static long 2", static_long_next() == 0x10001, 1);

    check("sizeof long", sizeof(long), 2);
    check("sizeof ulong", sizeof(unsigned long), 2);

    puts("================");
    print_str("PASS: "); print_int(pass_count); putchar(10);
    print_str("FAIL: "); print_int(fail_count); putchar(10);
    puts("=== done ===");
    return 0;
}

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

int grade(int score) {
    switch (score) {
        case 1: return 10;
        case 2: return 20;
        case 3: return 30;
        default: return 99;
    }
}

int fallthrough_test(int x) {
    int r = 0;
    switch (x) {
        case 1:
            r = r + 1;
        case 2:
            r = r + 2;
            break;
        case 3:
            r = r + 10;
            break;
        default:
            r = r + 100;
    }
    return r;
}

int no_default(int x) {
    int r = 0;
    switch (x) {
        case 5: r = 50; break;
        case 6: r = 60; break;
    }
    return r;
}

int nested_switch(int a, int b) {
    int r = 0;
    switch (a) {
        case 1:
            switch (b) {
                case 10: r = 110; break;
                case 20: r = 120; break;
                default: r = 100; break;
            }
            break;
        case 2:
            r = 200;
            break;
        default:
            r = 0;
    }
    return r;
}

int switch_in_loop(int n) {
    int sum = 0;
    int i;
    for (i = 0; i < n; i++) {
        switch (i % 3) {
            case 0: sum = sum + 1; break;
            case 1: sum = sum + 10; break;
            case 2: sum = sum + 100; break;
        }
    }
    return sum;
}

int main() {
    pass_count = 0;
    fail_count = 0;
    puts("=== test_switch ===");

    check("case 1",       grade(1), 10);
    check("case 2",       grade(2), 20);
    check("case 3",       grade(3), 30);
    check("default",      grade(9), 99);

    check("fallthrough 1->2", fallthrough_test(1), 3);
    check("no-fallthrough 2", fallthrough_test(2), 2);
    check("no-fallthrough 3", fallthrough_test(3), 10);
    check("default ft",       fallthrough_test(9), 100);

    check("no-default hit",  no_default(5), 50);
    check("no-default hit2", no_default(6), 60);
    check("no-default miss", no_default(7), 0);

    check("nested 1,10",  nested_switch(1, 10), 110);
    check("nested 1,20",  nested_switch(1, 20), 120);
    check("nested 1,99",  nested_switch(1, 99), 100);
    check("nested 2,x",   nested_switch(2, 10), 200);
    check("nested def",   nested_switch(9, 10), 0);

    check("switch in loop n=6", switch_in_loop(6), 222);

    puts("================");
    print_str("PASS: "); print_int(pass_count); putchar(10);
    print_str("FAIL: "); print_int(fail_count); putchar(10);
    puts("=== done ===");
    return 0;
}

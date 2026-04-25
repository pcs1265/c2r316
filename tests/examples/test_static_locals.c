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

int counter() {
    static int n = 0;
    n = n + 1;
    return n;
}

int get_id() {
    static int next_id = 10;
    return next_id++;
}

int accumulate(int x) {
    static int total = 0;
    total = total + x;
    return total;
}

int two_statics() {
    static int a = 1;
    static int b = 100;
    a = a + 1;
    b = b + 10;
    return a + b;
}

int main() {
    pass_count = 0;
    fail_count = 0;
    puts("=== test_static_locals ===");

    check("counter 1", counter(), 1);
    check("counter 2", counter(), 2);
    check("counter 3", counter(), 3);

    check("get_id 1", get_id(), 10);
    check("get_id 2", get_id(), 11);
    check("get_id 3", get_id(), 12);

    check("accumulate 5",  accumulate(5), 5);
    check("accumulate 3",  accumulate(3), 8);
    check("accumulate 7",  accumulate(7), 15);

    check("two_statics 1", two_statics(), 2 + 110);
    check("two_statics 2", two_statics(), 3 + 120);

    puts("================");
    print_str("PASS: "); print_int(pass_count); putchar(10);
    print_str("FAIL: "); print_int(fail_count); putchar(10);
    puts("=== done ===");
    return 0;
}

/* test_stack_args.c - functions with 7+ arguments (stack argument passing) */

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

/* Exactly 6 args - all in registers */
int six_args(int a, int b, int c, int d, int e, int f) {
    return a + b + c + d + e + f;
}

/* 7 args - first 6 in registers, 7th on stack */
int seven_args(int a, int b, int c, int d, int e, int f, int g) {
    return a + b + c + d + e + f + g;
}

/* 8 args */
int eight_args(int a, int b, int c, int d, int e, int f, int g, int h) {
    return a + b + c + d + e + f + g + h;
}

/* 10 args */
int ten_args(int a, int b, int c, int d, int e, int f, int g, int h, int i, int j) {
    return a + b + c + d + e + f + g + h + i + j;
}

/* 12 args - stress test stack args */
int twelve_args(int a, int b, int c, int d, int e, int f, int g, int h, int i, int j, int k, int l) {
    return a + b + c + d + e + f + g + h + i + j + k + l;
}

/* Function with stack args calling another function with stack args */
int caller_stack(void) {
    return seven_args(1, 2, 3, 4, 5, 6, 7);
}

/* Nested calls with stack args */
int nested_a(int x) {
    return x * 2;
}

int nested_b(int a, int b, int c, int d, int e, int f, int g) {
    return nested_a(a) + nested_a(b) + nested_a(c) + nested_a(d) + nested_a(e) + nested_a(f) + nested_a(g);
}

/* Function pointer call with many args */
typedef int (*Func7)(int, int, int, int, int, int, int);

int via_func_ptr(Func7 fn, int a, int b, int c, int d, int e, int f, int g) {
    return fn(a, b, c, d, e, f, g);
}

int main(void) {
    pass_count = 0;
    fail_count = 0;

    puts("=== test_stack_args ===");

    /* 1. Six args (register boundary) */
    check("six(1..6)", six_args(1, 2, 3, 4, 5, 6), 21);
    check("six(10..60)", six_args(10, 20, 30, 40, 50, 60), 210);

    /* 2. Seven args (first stack arg) */
    check("seven(1..7)", seven_args(1, 2, 3, 4, 5, 6, 7), 28);
    check("seven(10..70)", seven_args(10, 20, 30, 40, 50, 60, 70), 280);

    /* 3. Eight args */
    check("eight(1..8)", eight_args(1, 2, 3, 4, 5, 6, 7, 8), 36);

    /* 4. Ten args */
    check("ten(1..10)", ten_args(1, 2, 3, 4, 5, 6, 7, 8, 9, 10), 55);

    /* 5. Twelve args (stress test) */
    check("twelve(1..12)", twelve_args(1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12), 78);
    check("twelve(12..1)", twelve_args(12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1), 78);

    /* 6. Large values in stack args */
    check("seven large", seven_args(1000, 2000, 3000, 4000, 5000, 6000, 7000), 28000);

    /* 7. Negative values in stack args */
    check("seven neg", seven_args(1, 1, 1, 1, 1, 1, -6), 0);

    /* 8. Caller with stack args */
    check("caller_stack", caller_stack(), 28);

    /* 9. Nested calls with stack args */
    check("nested_b", nested_b(1, 2, 3, 4, 5, 6, 7), 56);  /* 2+4+6+8+10+12+14 */

    /* 10. Function pointer with many args */
    check("via func ptr", via_func_ptr(seven_args, 1, 2, 3, 4, 5, 6, 7), 28);

    /* 11. Multiple calls in sequence */
    check("seq 1", seven_args(1, 1, 1, 1, 1, 1, 1), 7);
    check("seq 2", seven_args(2, 2, 2, 2, 2, 2, 2), 14);
    check("seq 3", seven_args(3, 3, 3, 3, 3, 3, 3), 21);

    /* 12. Stack args with expression results */
    int x;
    x = 10;
    check("expr args", seven_args(x, x+1, x+2, x+3, x+4, x+5, x+6), 70 + 21);

    /* summary */
    puts("================");
    print_str("PASS: "); print_int(pass_count); putchar(10);
    print_str("FAIL: "); print_int(fail_count); putchar(10);
    puts("=== done ===");
    return 0;
}
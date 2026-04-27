/* test_switch_edge.c - edge cases for switch statements */

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

int test_dense(int x) {
    int result;
    result = 0;
    switch (x) {
        case 0: result = 10; break;
        case 1: result = 20; break;
        case 2: result = 30; break;
        case 3: result = 40; break;
        case 4: result = 50; break;
        default: result = 99; break;
    }
    return result;
}

int test_sparse(int x) {
    int result;
    result = 0;
    switch (x) {
        case 0: result = 1; break;
        case 100: result = 2; break;
        case 1000: result = 3; break;
        case 10000: result = 4; break;
        default: result = 99; break;
    }
    return result;
}

int test_fallthrough(int x) {
    int result;
    result = 0;
    switch (x) {
        case 1: result = result + 1;
        case 2: result = result + 2;
        case 3: result = result + 4;
        case 4: result = result + 8;
        case 5: result = result + 16; break;
        default: result = 99; break;
    }
    return result;
}

int test_default_first(int x) {
    int result;
    result = 0;
    switch (x) {
        default: result = 99; break;
        case 1: result = 1; break;
        case 2: result = 2; break;
    }
    return result;
}

int test_default_middle(int x) {
    int result;
    result = 0;
    switch (x) {
        case 1: result = 1; break;
        default: result = 99; break;
        case 2: result = 2; break;
    }
    return result;
}

int test_nested_outer(int x, int y) {
    int result;
    result = 0;
    switch (x) {
        case 1:
            switch (y) {
                case 1: result = 11; break;
                case 2: result = 12; break;
                default: result = 19; break;
            }
            break;
        case 2:
            switch (y) {
                case 1: result = 21; break;
                case 2: result = 22; break;
                default: result = 29; break;
            }
            break;
        default: result = 99; break;
    }
    return result;
}

int test_no_default(int x) {
    int result;
    result = 0;
    switch (x) {
        case 1: result = 1; break;
        case 2: result = 2; break;
    }
    return result;
}

int test_single_case(int x) {
    int result;
    result = 0;
    switch (x) {
        case 42: result = 100; break;
    }
    return result;
}

int main(void) {
    pass_count = 0;
    fail_count = 0;

    puts("=== test_switch_edge ===");

    /* 1. Dense cases (0-4) */
    check("dense 0", test_dense(0), 10);
    check("dense 1", test_dense(1), 20);
    check("dense 2", test_dense(2), 30);
    check("dense 3", test_dense(3), 40);
    check("dense 4", test_dense(4), 50);
    check("dense 5 (default)", test_dense(5), 99);

    /* 2. Sparse cases */
    check("sparse 0", test_sparse(0), 1);
    check("sparse 100", test_sparse(100), 2);
    check("sparse 1000", test_sparse(1000), 3);
    check("sparse 10000", test_sparse(10000), 4);
    check("sparse 50 (default)", test_sparse(50), 99);

    /* 3. Fallthrough chain */
    check("fall 1", test_fallthrough(1), 31);  /* 1+2+4+8+16 = 31 */
    check("fall 2", test_fallthrough(2), 30);  /* 2+4+8+16 = 30 */
    check("fall 3", test_fallthrough(3), 28);  /* 4+8+16 = 28 */
    check("fall 4", test_fallthrough(4), 24);  /* 8+16 = 24 */
    check("fall 5", test_fallthrough(5), 16);  /* just 16 */
    check("fall 0 (default)", test_fallthrough(0), 99);

    /* 4. Default first */
    check("default first 1", test_default_first(1), 1);
    check("default first 2", test_default_first(2), 2);
    check("default first 3", test_default_first(3), 99);

    /* 5. Default middle */
    check("default mid 1", test_default_middle(1), 1);
    check("default mid 2", test_default_middle(2), 2);
    check("default mid 3", test_default_middle(3), 99);

    /* 6. Nested switches */
    check("nested 1,1", test_nested_outer(1, 1), 11);
    check("nested 1,2", test_nested_outer(1, 2), 12);
    check("nested 1,3", test_nested_outer(1, 3), 19);
    check("nested 2,1", test_nested_outer(2, 1), 21);
    check("nested 2,2", test_nested_outer(2, 2), 22);
    check("nested 3,1", test_nested_outer(3, 1), 99);

    /* 7. No default */
    check("no default 1", test_no_default(1), 1);
    check("no default 2", test_no_default(2), 2);
    check("no default 3", test_no_default(3), 0);  /* result stays 0 */

    /* 8. Single case */
    check("single 42", test_single_case(42), 100);
    check("single 0", test_single_case(0), 0);

    /* 9. Switch with negative case values */
    int neg_result;
    neg_result = 0;
    switch (-1) {
        case -1: neg_result = -1; break;
        case -2: neg_result = -2; break;
        default: neg_result = 0; break;
    }
    check("negative case", neg_result, -1);

    /* summary */
    puts("================");
    print_str("PASS: "); print_int(pass_count); putchar(10);
    print_str("FAIL: "); print_int(fail_count); putchar(10);
    puts("=== done ===");
    return 0;
}
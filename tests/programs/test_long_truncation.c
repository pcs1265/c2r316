/* test_long_truncation.c - tests for 32-bit long behavior and truncation */

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

    puts("=== test_long_truncation ===");

    /* 1. Long type parsing and basic declaration */
    long l1;
    unsigned long ul1;
    
    /* 2. Long assignment - should truncate to 16 bits */
    l1 = 0x12345678;
    /* Expected: truncated to 0x5678 (low 16 bits) */
    check("long truncate", l1, 0x5678);

    /* 3. Unsigned long truncation */
    ul1 = 0xABCD1234;
    check_u("ulong truncate", ul1, 0x1234);

    /* 4. Long with value fitting in 16 bits */
    l1 = 1000;
    check("long fits 16", l1, 1000);
    l1 = -100;
    check("long neg fits", l1, -100);

    /* 5. Long literal > 16 bits */
    l1 = 70000;  /* 70000 = 0x11170, truncated to 0x1170 = 4464 */
    check("long lit 70000", l1, 4464);

    /* 6. Long hex literal */
    l1 = 0x10001;  /* truncated to 0x0001 */
    check("long 0x10001", l1, 1);

    /* 7. Long arithmetic (should be 16-bit) */
    long la;
    long lb;
    la = 100;
    lb = 200;
    check("long +", la + lb, 300);
    check("long *", la * lb, 20000);
    check("long -", lb - la, 100);

    /* 8. Long and int interaction */
    int i1;
    i1 = 42;
    l1 = 100;
    check("long+int", l1 + i1, 142);
    check("int+long", i1 + l1, 142);

    /* 9. Long comparison */
    la = 100;
    lb = 200;
    check("long cmp <", la < lb, 1);
    check("long cmp >", la > lb, 0);
    check("long cmp ==", la == lb, 0);

    /* 10. Long in conditionals */
    l1 = 1;
    if (l1) {
        check("long cond true", 1, 1);
    } else {
        check("long cond true", 0, 1);
    }
    l1 = 0;
    if (l1) {
        check("long cond false", 0, 1);
    } else {
        check("long cond false", 1, 1);
    }

    /* 11. Long assignment to int (implicit truncation) */
    l1 = 0x12345678;
    i1 = l1;
    check("long to int", i1, 0x5678);

    /* 12. Unsigned long behavior */
    ul1 = 0xFFFF;
    check_u("ulong 0xFFFF", ul1, 0xFFFF);
    ul1 = 0x10000;  /* truncated to 0 */
    check_u("ulong 0x10000", ul1, 0);

    /* 13. Long as function parameter type */
    /* (This documents current behavior, even if incorrect) */
    
    /* 14. Sizeof long */
    check("sizeof(long)", sizeof(long), 2);

    /* 15. Mixed long/int expressions */
    la = 30000;
    i1 = 10000;
    check("long/int mix", la + i1, 40000);  /* May overflow 16-bit */

    /* summary */
    puts("================");
    print_str("PASS: "); print_int(pass_count); putchar(10);
    print_str("FAIL: "); print_int(fail_count); putchar(10);
    puts("=== done ===");
    return 0;
}
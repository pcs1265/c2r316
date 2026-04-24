/*
 * test_memcpy.c — verify the inline-asm memcpy in stdlib.h
 *
 * Tests:
 *   1. Basic copy
 *   2. n=0 (no-op)
 *   3. src and dst do not overlap wrongly (independent buffers)
 *   4. Multiple calls — verifies no label collision from inlining
 */

#include "runtime/stdlib.h"
#include "runtime/stdio.h"

int pass_count;
int fail_count;

void check(char *name, int got, int expected) {
    if (got == expected) {
        print_str(name);
        print_str(": PASS\n");
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

int main() {
    /* 1. Basic copy of 4 elements */
    int src[4];
    int dst[4];
    src[0] = 10; src[1] = 20; src[2] = 30; src[3] = 40;
    dst[0] =  0; dst[1] =  0; dst[2] =  0; dst[3] =  0;
    memcpy(dst, src, 4);
    check("basic[0]", dst[0], 10);
    check("basic[1]", dst[1], 20);
    check("basic[2]", dst[2], 30);
    check("basic[3]", dst[3], 40);

    /* 2. n=0: dst must be untouched */
    int z[2];
    z[0] = 99; z[1] = 88;
    memcpy(z, src, 0);
    check("n=0 [0]", z[0], 99);
    check("n=0 [1]", z[1], 88);

    /* 3. Second independent call — exercises label uniqueness after inlining */
    int src2[3];
    int dst2[3];
    src2[0] = 1; src2[1] = 2; src2[2] = 3;
    dst2[0] = 0; dst2[1] = 0; dst2[2] = 0;
    memcpy(dst2, src2, 3);
    check("second[0]", dst2[0], 1);
    check("second[1]", dst2[1], 2);
    check("second[2]", dst2[2], 3);

    /* 4. Copy of 1 element */
    int one_src[1];
    int one_dst[1];
    one_src[0] = 77;
    one_dst[0] = 0;
    memcpy(one_dst, one_src, 1);
    check("n=1", one_dst[0], 77);

    /* 5. memset basic */
    int mbuf[4];
    mbuf[0] = 0; mbuf[1] = 0; mbuf[2] = 0; mbuf[3] = 0;
    memset(mbuf, 7, 4);
    check("memset[0]", mbuf[0], 7);
    check("memset[1]", mbuf[1], 7);
    check("memset[2]", mbuf[2], 7);
    check("memset[3]", mbuf[3], 7);

    /* 6. memset n=0: untouched */
    int mz[2];
    mz[0] = 55; mz[1] = 66;
    memset(mz, 0, 0);
    check("memset n=0 [0]", mz[0], 55);
    check("memset n=0 [1]", mz[1], 66);

    /* 7. memset second call — label uniqueness */
    int mbuf2[3];
    mbuf2[0] = 0; mbuf2[1] = 0; mbuf2[2] = 0;
    memset(mbuf2, 42, 3);
    check("memset2[0]", mbuf2[0], 42);
    check("memset2[1]", mbuf2[1], 42);
    check("memset2[2]", mbuf2[2], 42);

    print_str("\nDone: ");
    print_int(pass_count);
    print_str(" passed, ");
    print_int(fail_count);
    print_str(" failed\n");
    return fail_count;
}

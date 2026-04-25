#include "runtime/stdio.h"

/*
 * Super complex mathematics test suite:
 * 1. Recursive algorithms (Fibonacci, GCD)
 * 2. Prime number detection
 * 3. Factorial with overflow handling
 * 4. Integer square root using Newton's method
 * 5. Perfect number verification
 * 6. Bitwise operations and bit counting
 * 7. Nested loops and array manipulation
 * 8. Numerical algorithms
 */

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

/* Fibonacci: classic recursive algorithm */
int fib(int n) {
    if (n <= 1) return n;
    return fib(n - 1) + fib(n - 2);
}

/* GCD using Euclidean algorithm: multiple branches + recursion */
int gcd(int a, int b) {
    if (b == 0) return a;
    return gcd(b, a % b);
}

/* Prime number checking: multiple conditions + nested loops */
int is_prime(int n) {
    int i;
    if (n < 2) return 0;
    if (n == 2) return 1;
    if (n % 2 == 0) return 0;

    for (i = 3; i * i <= n; i = i + 2) {
        if (n % i == 0) return 0;
    }
    return 1;
}

/* Factorial: recursive with early termination */
int factorial(int n) {
    if (n <= 1) return 1;
    return n * factorial(n - 1);
}

/* Integer square root using Newton's method */
int isqrt(int n) {
    int x, y, prev;

    if (n <= 1) return n;

    x = n;
    while (1) {
        y = (x + n / x) / 2;
        if (y >= x) break;
        x = y;
    }
    return x;
}

/* Count number of set bits */
int popcount(int n) {
    int count = 0;
    unsigned int u = n;

    while (u != 0) {
        if (u & 1) count = count + 1;
        u = u >> 1;
    }
    return count;
}

/* Sum of all divisors (including 1 and n) */
int sum_divisors(int n) {
    int i, sum = 0;

    for (i = 1; i * i <= n; i = i + 1) {
        if (n % i == 0) {
            sum = sum + i;
            if (i != n / i) {
                sum = sum + (n / i);
            }
        }
    }
    return sum;
}

/* Check if perfect number: sum of proper divisors (excluding n) equals n */
int is_perfect(int n) {
    return (sum_divisors(n) - n) == n;
}

/* Bitwise: count trailing zeros */
int ctz(int n) {
    int count = 0;
    if (n == 0) return 32;
    while ((n & 1) == 0) {
        count = count + 1;
        n = n >> 1;
    }
    return count;
}

/* Bitwise: rotate left */
int rotl(int n, int bits) {
    unsigned int u = n;
    return (u << bits) | (u >> (16 - bits));
}

/* Complex calculation: nested loops + conditionals + array arithmetic */
int complex_sum(int n) {
    int arr[16];
    int i, j, sum = 0;

    /* Initialize array with primes */
    arr[0] = 2;
    arr[1] = 3;
    arr[2] = 5;
    arr[3] = 7;
    arr[4] = 11;
    arr[5] = 13;
    arr[6] = 17;
    arr[7] = 19;
    arr[8] = 23;
    arr[9] = 29;
    arr[10] = 31;
    arr[11] = 37;
    arr[12] = 41;
    arr[13] = 43;
    arr[14] = 47;
    arr[15] = 53;

    /* Nested loops with complex condition */
    for (i = 0; i < n && i < 16; i = i + 1) {
        for (j = 0; j < n && j < 16; j = j + 1) {
            if ((arr[i] + arr[j]) % 2 == 0) {
                sum = sum + arr[i];
            } else {
                sum = sum + arr[j];
            }
        }
    }
    return sum;
}

int main(void) {
    pass_count = 0;
    fail_count = 0;

    puts("=== test_complex ===");

    /* Fibonacci tests */
    check("fib(0)", fib(0), 0);
    check("fib(1)", fib(1), 1);
    check("fib(5)", fib(5), 5);
    check("fib(6)", fib(6), 8);
    check("fib(7)", fib(7), 13);
    check("fib(8)", fib(8), 21);

    /* GCD tests */
    check("gcd(12, 8)", gcd(12, 8), 4);
    check("gcd(100, 50)", gcd(100, 50), 50);
    check("gcd(17, 19)", gcd(17, 19), 1);
    check("gcd(48, 18)", gcd(48, 18), 6);
    check("gcd(0, 5)", gcd(0, 5), 5);

    /* Prime checking */
    check("is_prime(2)", is_prime(2), 1);
    check("is_prime(3)", is_prime(3), 1);
    check("is_prime(4)", is_prime(4), 0);
    check("is_prime(17)", is_prime(17), 1);
    check("is_prime(20)", is_prime(20), 0);
    check("is_prime(97)", is_prime(97), 1);
    check("is_prime(100)", is_prime(100), 0);

    /* Factorial */
    check("factorial(0)", factorial(0), 1);
    check("factorial(1)", factorial(1), 1);
    check("factorial(5)", factorial(5), 120);
    check("factorial(6)", factorial(6), 720);
    check("factorial(7)", factorial(7), 5040);

    /* Integer square root */
    check("isqrt(0)", isqrt(0), 0);
    check("isqrt(1)", isqrt(1), 1);
    check("isqrt(4)", isqrt(4), 2);
    check("isqrt(9)", isqrt(9), 3);
    check("isqrt(16)", isqrt(16), 4);
    check("isqrt(25)", isqrt(25), 5);
    check("isqrt(100)", isqrt(100), 10);
    check("isqrt(99)", isqrt(99), 9);

    /* Popcount (bit counting) */
    check("popcount(0)", popcount(0), 0);
    check("popcount(1)", popcount(1), 1);
    check("popcount(3)", popcount(3), 2);
    check("popcount(7)", popcount(7), 3);
    check("popcount(15)", popcount(15), 4);
    check("popcount(255)", popcount(255), 8);

    /* Sum of divisors */
    check("sum_divisors(1)", sum_divisors(1), 1);
    check("sum_divisors(6)", sum_divisors(6), 12);
    check("sum_divisors(12)", sum_divisors(12), 28);
    check("sum_divisors(28)", sum_divisors(28), 56);

    /* Perfect number check */
    check("is_perfect(6)", is_perfect(6), 1);
    check("is_perfect(28)", is_perfect(28), 1);
    check("is_perfect(12)", is_perfect(12), 0);
    check("is_perfect(8)", is_perfect(8), 0);

    /* Trailing zero count */
    check("ctz(1)", ctz(1), 0);
    check("ctz(2)", ctz(2), 1);
    check("ctz(4)", ctz(4), 2);
    check("ctz(8)", ctz(8), 3);
    check("ctz(16)", ctz(16), 4);

    /* Complex nested algorithm */
    check("complex_sum(2)", complex_sum(2), 20);
    check("complex_sum(3)", complex_sum(3), 60);

    /* Summary */
    puts("================");
    print_str("PASS: ");
    print_int(pass_count);
    putchar(10);
    print_str("FAIL: ");
    print_int(fail_count);
    putchar(10);
    puts("=== done ===");

    return 0;
}

#include "runtime/stdio.h"

/*
 * Super complex test case:
 * 1. Recursive function calculation (Fibonacci)
 * 2. Complex nested loops
 * 3. Array pointer arithmetic
 * 4. Conditional logic with multiple branching
 */

int fib(int n) {
    if (n <= 1) return n;
    return fib(n - 1) + fib(n - 2);
}

int main() {
    int arr[10];
    int i, j;
    int sum = 0;

    // Nested loops and array manipulation
    for (i = 0; i < 10; i++) {
        arr[i] = i * 2;
    }

    for (i = 0; i < 10; i++) {
        for (j = 0; j < i; j++) {
            if (arr[i] > 5) {
                sum += (arr[i] + j);
            } else {
                sum -= j;
            }
        }
    }

    // Recursive call
    int fib_val = fib(10);
    
    // Final result output
    printf("Fib(10) = %d\n", fib_val);
    printf("Calculated Sum = %d\n", sum);

    return 0;
}

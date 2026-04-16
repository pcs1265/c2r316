/* First C program running on the R316 */

#include "../runtime/r316.h"

int factorial(int n) {
    if (n <= 1) return 1;
    return n * factorial(n - 1);
}

int main(void) {
    int i;
    printf("Hello, R316!\n");
    for (i = 1; i <= 7; i++) {
        printf("%d! = %d\n", i, factorial(i));
    }
    return 0;
}

/* First C program running on R316 */

#include "runtime/stdio.h"



int main() {
    printf("Hello, R316!\n");
    for (int i = 0; i < 1024; i++) {
        putchar(*(char*)i);
    }

    return 0;
}

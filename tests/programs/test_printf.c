// Test printf format specifiers: %d %u %x %c %s %%

#include <stdio.h>

int main() {
    puts("=== test_printf ===");
    printf("%d\n", 42);
    printf("%d\n", -7);
    printf("%u\n", 65535);
    printf("%x\n", 255);
    printf("%c\n", 65);
    printf("%s\n", "hello");
    printf("100%%\n");
    printf("%d %d %d\n", 1, 2, 3);
    puts("=== done ===");
    return 0;
}

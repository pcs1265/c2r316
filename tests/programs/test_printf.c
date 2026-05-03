// Test printf format specifiers: %d %u %x %ld %lu %lx %c %s %%

#include <stdio.h>

int main() {
    long sl;
    unsigned long ul;
    sl = -70000;
    ul = 305419896;

    puts("=== test_printf ===");
    printf("%d\n", 42);
    printf("%d\n", -7);
    printf("%u\n", 65535);
    printf("%x\n", 255);
    printf("%ld\n", sl);
    printf("%lu\n", ul);
    printf("%lx\n", ul);
    printf("%c\n", 65);
    printf("%s\n", "hello");
    printf("100%%\n");
    printf("%d %d %d\n", 1, 2, 3);
    puts("=== done ===");
    return 0;
}

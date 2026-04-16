/* R316에서 실행되는 첫 C 프로그램 */

void putchar(int c);
void print_int(int n);
void puts(char *s);
void printf(char *fmt, ...);        // Formatted output: %d %u %x %s %c %%

int main() {
    printf("Hello, R316!");

    int i;
    for (i = 1; i <= 10; i++) {
        printf("Value:%d\n", i);
    }

    return 0;
}

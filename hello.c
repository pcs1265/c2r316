/* R316에서 실행되는 첫 C 프로그램 */

void putchar(int c);
void print_int(int n);
void puts(char *s);

int main() {
    puts("Hello, R316!");

    int i;
    for (i = 1; i <= 10; i++) {
        print_int(i);
        putchar('\n');
    }

    return 0;
}

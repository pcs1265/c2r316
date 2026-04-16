/* Test: do-while, switch, goto, enum, local array init, typedef */

typedef int myint;

enum Color { RED = 0, GREEN, BLUE };

int test_do_while(int n) {
    int sum = 0;
    do {
        sum = sum + n;
        n = n - 1;
    } while (n > 0);
    return sum;
}

int test_switch(int x) {
    int result = 0;
    switch (x) {
        case 0:
            result = 10;
            break;
        case 1:
            result = 20;
            break;
        default:
            result = 99;
            break;
    }
    return result;
}

int test_goto() {
    int i = 0;
loop:
    i = i + 1;
    if (i < 5) goto loop;
    return i;
}

int test_enum() {
    int c = GREEN;
    return c;
}

int test_local_array() {
    int arr[3];
    arr[0] = 10;
    arr[1] = 20;
    arr[2] = 30;
    return arr[1];
}

int test_local_array_init() {
    int arr[] = {1, 2, 3};
    return arr[2];
}

int test_typedef(myint x) {
    myint y = x + 1;
    return y;
}

int main() {
    return 0;
}

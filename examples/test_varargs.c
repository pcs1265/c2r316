// Test variadic argument support
// sum(n, ...) returns the sum of n integers

int sum(int n, ...) {
    va_list ap;
    va_start(ap, n);
    int total = 0;
    int i;
    for (i = 0; i < n; i = i + 1) {
        total = total + va_arg(ap, int);
    }
    va_end(ap);
    return total;
}

int main() {
    return sum(3, 10, 20, 30);  // expected: 60
}

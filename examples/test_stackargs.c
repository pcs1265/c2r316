// Test stack arguments for 7th+ parameters (ABI §2.3)

int sum7(int a, int b, int c, int d, int e, int f, int g) {
    return a + b + c + d + e + f + g;
}

int sum8(int a, int b, int c, int d, int e, int f, int g, int h) {
    return a + b + c + d + e + f + g + h;
}

// Verify the 7th arg is independent of the others
int pick7(int a, int b, int c, int d, int e, int f, int g) {
    return g;
}

int pick8(int a, int b, int c, int d, int e, int f, int g, int h) {
    return h;
}

int main() {
    // 1+2+3+4+5+6+7 = 28
    int r1;
    r1 = sum7(1, 2, 3, 4, 5, 6, 7);
    if (r1 != 28) return 1;

    // 1+2+3+4+5+6+7+8 = 36
    int r2;
    r2 = sum8(1, 2, 3, 4, 5, 6, 7, 8);
    if (r2 != 36) return 2;

    // 7th arg only
    int r3;
    r3 = pick7(0, 0, 0, 0, 0, 0, 99);
    if (r3 != 99) return 3;

    // 8th arg only
    int r4;
    r4 = pick8(0, 0, 0, 0, 0, 0, 0, 42);
    if (r4 != 42) return 4;

    return 0;
}

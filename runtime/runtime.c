/*
 * C→R316 Runtime Library (C implementation)
 *
 * Hardware primitives (putchar, getchar, __udiv, __umod) live in
 * runtime_core.asm — only their declarations appear here.
 */

/* Hardware primitives — provided by runtime_core.asm */
int putchar(int c);
int getchar(void);

/* Variadic compiler intrinsic declarations */
void va_start(int* ap, int last);
int  va_arg(int* ap, int type);
void va_end(int* ap);

/* -- _print_digits ----------------------------------------------------------
 * Recursively prints the decimal digits of n (n > 0).
 * Uses recursion instead of an array to get the digit order right.
 */
void _print_digits(unsigned int n) {
    unsigned int q;
    int r;
    q = n / 10;
    r = n % 10;
    if (q) {
        _print_digits(q);
    }
    putchar('0' + r);
}

/* -- print_uint(unsigned int n) -----------------------------------------*/
void print_uint(unsigned int n) {
    if (n == 0) {
        putchar('0');
        return;
    }
    _print_digits(n);
}

/* -- print_int(int n) ---------------------------------------------------*/
void print_int(int n) {
    if (n < 0) {
        putchar('-');
        n = -n;
    }
    print_uint(n);
}

/* -- print_hex(unsigned int n) ------------------------------------------
 * Prints a 4-digit uppercase hex value.
 */
void print_hex(unsigned int n) {
    int i;
    int nibble;
    for (i = 0; i < 4; i++) {
        nibble = (n >> 12) & 15;
        if (nibble >= 10) {
            putchar('A' + nibble - 10);
        } else {
            putchar('0' + nibble);
        }
        n = n << 4;
    }
}

/* -- print_str(char *s) -------------------------------------------------
 * Prints a string (no newline).
 */
void print_str(char* s) {
    while (*s) {
        putchar(*s);
        s++;
    }
}

/* -- puts(char *s) ------------------------------------------------------
 * Prints a string followed by a newline.
 */
void puts(char* s) {
    print_str(s);
    putchar('\n');
}

/* -- strlen(char *s) -> int ---------------------------------------------*/
int strlen(char* s) {
    int n;
    n = 0;
    while (*s) {
        s++;
        n++;
    }
    return n;
}

/* -- strcmp(char *a, char *b) -> int ------------------------------------
 * Returns 0 if equal, positive if a > b, negative if a < b.
 */
int strcmp(char* a, char* b) {
    while (*a && *a == *b) {
        a++;
        b++;
    }
    return *a - *b;
}

/* -- memset(void *dst, int val, int n) ----------------------------------*/
void memset(char* dst, int val, int n) {
    while (n > 0) {
        *dst = val;
        dst++;
        n--;
    }
}

/* -- memcpy(void *dst, void *src, int n) --------------------------------*/
void memcpy(char* dst, char* src, int n) {
    while (n > 0) {
        *dst = *src;
        dst++;
        src++;
        n--;
    }
}

/* -- printf(char *fmt, ...) ---------------------------------------------
 * Supported format specifiers: %d %u %x %s %c %%
 */
void printf(char* fmt, ...) {
    int* ap;
    int ch;
    int val;
    char* str;
    va_start(ap, fmt);
    ch = *fmt;
    while (ch) {
        if (ch == '%') {
            fmt = fmt + 1;
            ch = *fmt;
            if (ch == 'd') {
                val = va_arg(ap, int);
                print_int(val);
            } else if (ch == 'u') {
                val = va_arg(ap, int);
                print_uint(val);
            } else if (ch == 'x') {
                val = va_arg(ap, int);
                print_hex(val);
            } else if (ch == 's') {
                str = (char*)va_arg(ap, int);
                print_str(str);
            } else if (ch == 'c') {
                val = va_arg(ap, int);
                putchar(val);
            } else if (ch == '%') {
                putchar('%');
            }
        } else {
            putchar(ch);
        }
        fmt = fmt + 1;
        ch = *fmt;
    }
    va_end(ap);
}

/*
 * C→R316 런타임 라이브러리 (C 구현)
 *
 * 하드웨어 프리미티브(putchar, getchar, __udiv, __umod)는
 * runtime_core.asm에 있으므로 여기서는 선언만 합니다.
 */

/* 하드웨어 프리미티브 선언 (runtime_core.asm에서 제공) */
int putchar(int c);
int getchar(void);

/* ── _print_digits ───────────────────────────────────────────────────────────
 * n > 0 인 정수의 10진 자릿수를 재귀적으로 출력
 * 배열 없이 재귀를 이용해 자릿수 순서를 맞춤
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

/* ── print_uint(unsigned int n) ─────────────────────────────────────────────*/
void print_uint(unsigned int n) {
    if (n == 0) {
        putchar('0');
        return;
    }
    _print_digits(n);
}

/* ── print_int(int n) ────────────────────────────────────────────────────────*/
void print_int(int n) {
    if (n < 0) {
        putchar('-');
        n = -n;
    }
    print_uint(n);
}

/* ── print_hex(unsigned int n) ───────────────────────────────────────────────
 * 4자리 16진수 출력 (대문자)
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

/* ── print_str(char *s) ──────────────────────────────────────────────────────
 * 문자열 출력 (개행 없음)
 */
void print_str(char* s) {
    while (*s) {
        putchar(*s);
        s++;
    }
}

/* ── puts(char *s) ───────────────────────────────────────────────────────────
 * 문자열 출력 후 개행
 */
void puts(char* s) {
    print_str(s);
    putchar('\n');
}

/* ── strlen(char *s) → int ───────────────────────────────────────────────────*/
int strlen(char* s) {
    int n;
    n = 0;
    while (*s) {
        s++;
        n++;
    }
    return n;
}

/* ── strcmp(char *a, char *b) → int ─────────────────────────────────────────
 * 출력: 0(같음), 양수(a>b), 음수(a<b)
 */
int strcmp(char* a, char* b) {
    while (*a && *a == *b) {
        a++;
        b++;
    }
    return *a - *b;
}

/* ── memset(void *dst, int val, int n) ───────────────────────────────────────*/
void memset(char* dst, int val, int n) {
    while (n > 0) {
        *dst = val;
        dst++;
        n--;
    }
}

/* ── memcpy(void *dst, void *src, int n) ────────────────────────────────────*/
void memcpy(char* dst, char* src, int n) {
    while (n > 0) {
        *dst = *src;
        dst++;
        src++;
        n--;
    }
}

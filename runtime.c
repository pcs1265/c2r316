/*
 * C→R316 런타임 라이브러리 (C 구현)
 *
 * 하드웨어 프리미티브(putchar, getchar, __udiv, __umod)는
 * runtime_core.asm에 있으므로 여기서는 선언만 합니다.
 *
 * 주의사항 (현재 컴파일러 제약):
 *   - 파라미터에 직접 대입 불가 → 지역변수에 복사 후 사용
 *   - > 와 >= 비교 연산자에 버그 있음 → <, <=, ==, != 만 사용
 *   - 파라미터 포인터를 직접 산술하면 원본 레지스터가 파괴됨
 *     → 반드시 지역변수에 복사 후 사용
 */

/* 하드웨어 프리미티브 선언 (runtime_core.asm에서 제공) */
int putchar(int c);
int getchar(void);

/* ── _print_digits ───────────────────────────────────────────────────────────
 * n > 0 인 정수의 10진 자릿수를 재귀적으로 출력
 * 배열 없이 재귀를 이용해 자릿수 순서를 맞춤
 * (unsigned int 범위 0‥65535 모두 정확히 처리)
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

/* ── print_uint(unsigned int n) ─────────────────────────────────────────────
 * 부호 없는 16비트 정수 출력
 */
void print_uint(unsigned int n) {
    if (n == 0) {
        putchar('0');
        return;
    }
    _print_digits(n);
}

/* ── print_int(int n) ────────────────────────────────────────────────────────
 * 부호 있는 16비트 정수 출력
 * 주의: n = -32768일 때 -n이 오버플로우되는 엣지 케이스 존재
 */
void print_int(int n) {
    int abs_n;
    if (n < 0) {
        putchar('-');
        abs_n = -n;
    } else {
        abs_n = n;
    }
    print_uint(abs_n);
}

/* ── print_hex(unsigned int n) ───────────────────────────────────────────────
 * 4자리 16진수 출력 (대문자)
 * v에 n을 복사한 뒤 루프 안에서 v를 변경 (파라미터 직접 수정 금지)
 */
void print_hex(unsigned int n) {
    unsigned int v;
    int i;
    int nibble;
    v = n;
    i = 0;
    while (i < 4) {
        nibble = (v >> 12) & 15;
        if (nibble < 10) {
            putchar('0' + nibble);
        } else {
            putchar('A' + nibble - 10);
        }
        v = v << 4;
        i = i + 1;
    }
}

/* ── print_str(char *s) ──────────────────────────────────────────────────────
 * 문자열 출력 (개행 없음)
 * s를 지역변수 p에 복사 후 순회 (파라미터 포인터 직접 수정 금지)
 */
void print_str(char* s) {
    char* p;
    int ch;
    p = s;
    ch = *p;
    while (ch) {
        putchar(ch);
        p = p + 1;
        ch = *p;
    }
}

/* ── puts(char *s) ───────────────────────────────────────────────────────────
 * 문자열 출력 후 개행 (10 = '\n')
 */
void puts(char* s) {
    print_str(s);
    putchar(10);
}

/* ── strlen(char *s) → int ───────────────────────────────────────────────────
 * null 종료 문자열의 길이 반환
 */
int strlen(char* s) {
    char* p;
    int n;
    p = s;
    n = 0;
    while (*p) {
        p = p + 1;
        n = n + 1;
    }
    return n;
}

/* ── strcmp(char *a, char *b) → int ─────────────────────────────────────────
 * 문자열 비교: 0(같음), 양수(a>b), 음수(a<b)
 */
int strcmp(char* a, char* b) {
    char* pa;
    char* pb;
    int ca;
    int cb;
    pa = a;
    pb = b;
    ca = *pa;
    cb = *pb;
    while (ca && ca == cb) {
        pa = pa + 1;
        pb = pb + 1;
        ca = *pa;
        cb = *pb;
    }
    return ca - cb;
}

/* ── memset(char *dst, int val, int n) ───────────────────────────────────────
 * 메모리 영역을 val로 채움
 */
void memset(char* dst, int val, int n) {
    char* p;
    int i;
    p = dst;
    i = n;
    while (i) {
        *p = val;
        p = p + 1;
        i = i - 1;
    }
}

/* ── memcpy(char *dst, char *src, int n) ────────────────────────────────────
 * 메모리 영역 복사
 */
void memcpy(char* dst, char* src, int n) {
    char* pd;
    char* ps;
    int i;
    pd = dst;
    ps = src;
    i = n;
    while (i) {
        *pd = *ps;
        pd = pd + 1;
        ps = ps + 1;
        i = i - 1;
    }
}

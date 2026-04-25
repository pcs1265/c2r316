/*
 * string.h — string and memory utilities for the R316 C compiler
 */

#ifndef STRING_H
#define STRING_H

/* ── memset / memcpy / memmove / memcmp ─────────────────────────────────── */

static void memset(char *dst, int val, int n) {
    if (n == 0) return;
    asm(".memset_loop:\n"
        "st %1, %0, 0\n"
        "add %0, 1\n"
        "sub %2, 1\n"
        "jnz .memset_loop"
        : "r"(dst), "r"(val), "r"(n));
}

static void memcpy(char *dst, char *src, int n) {
    if (n == 0) return;
    asm(".memcpy_loop:\n"
        "ld r10, %1, 0\n"
        "st r10, %0, 0\n"
        "add %0, 1\n"
        "add %1, 1\n"
        "sub %2, 1\n"
        "jnz .memcpy_loop"
        : "r"(dst), "r"(src), "r"(n));
}

static void memmove(char *dst, char *src, int n) {
    int i;
    if (n == 0) return;
    if (dst <= src) {
        i = 0;
        while (i < n) {
            dst[i] = src[i];
            i++;
        }
    } else {
        i = n - 1;
        while (i >= 0) {
            dst[i] = src[i];
            i--;
        }
    }
}

static int memcmp(char *a, char *b, int n) {
    int i;
    i = 0;
    while (i < n) {
        if (a[i] != b[i])
            return a[i] - b[i];
        i++;
    }
    return 0;
}

/* ── strlen / strcpy / strcat ───────────────────────────────────────────── */

static int strlen(char *s) {
    char *p;
    p = s;
    while (*p) {
        p++;
    }
    return p - s;
}

static char *strcpy(char *dst, char *src) {
    char *d;
    d = dst;
    while (*src) {
        *d = *src;
        d++;
        src++;
    }
    *d = 0;
    return dst;
}

static char *strncpy(char *dst, char *src, int n) {
    char *d;
    d = dst;
    while (n > 0 && *src) {
        *d = *src;
        d++;
        src++;
        n--;
    }
    while (n > 0) {
        *d = 0;
        d++;
        n--;
    }
    return dst;
}

static char *strcat(char *dst, char *src) {
    char *d;
    d = dst;
    while (*d) {
        d++;
    }
    while (*src) {
        *d = *src;
        d++;
        src++;
    }
    *d = 0;
    return dst;
}

static char *strncat(char *dst, char *src, int n) {
    char *d;
    d = dst;
    while (*d) {
        d++;
    }
    while (n > 0 && *src) {
        *d = *src;
        d++;
        src++;
        n--;
    }
    *d = 0;
    return dst;
}

/* ── strcmp / strncmp ───────────────────────────────────────────────────── */

static int strcmp(char *a, char *b) {
    while (*a && *a == *b) {
        a++;
        b++;
    }
    return *a - *b;
}

static int strncmp(char *a, char *b, int n) {
    while (n > 0 && *a && *a == *b) {
        a++;
        b++;
        n--;
    }
    if (n == 0) return 0;
    return *a - *b;
}

/* ── strchr / strstr ────────────────────────────────────────────────────── */

static char *strchr(char *s, int c) {
    while (*s) {
        if (*s == c)
            return s;
        s++;
    }
    if (c == 0)
        return s;
    return 0;
}

static char *strstr(char *hay, char *needle) {
    int nlen;
    nlen = strlen(needle);
    if (nlen == 0)
        return hay;
    while (*hay) {
        if (memcmp(hay, needle, nlen) == 0)
            return hay;
        hay++;
    }
    return 0;
}

#endif /* STRING_H */

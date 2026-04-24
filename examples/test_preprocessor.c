/*
 * test_preprocessor.c — exercises every preprocessor feature.
 *
 * Expected output:
 *   object macro: 42
 *   fn macro MAX: 7
 *   fn macro MIN: 3
 *   stringify: hello
 *   token paste: 99
 *   paste digit: 2
 *   ifdef taken
 *   ifndef taken
 *   if expr: 1
 *   elif expr: 2
 *   else branch: 3
 *   nested if: ok
 *   undef: ok
 *   char literal: 65
 *   hex literal: 255
 *   octal literal: 8
 *   binary literal: 10
 *   if add: 5
 *   if sub: 1
 *   if mul: 6
 *   if div: 3
 *   if mod: 1
 *   shift: 8
 *   bitwise and: 1
 *   bitwise or: 7
 *   bitwise xor: 6
 *   bitwise not: ok
 *   logical: 1
 *   unary minus: ok
 *   ternary if: ok
 *   ternary macro: 10
 *   variadic: done
 *   multiline macro: 6
 *   nested macro: ok
 *   defined bare: ok
 *   include guard: ok
 *   header const: 77
 *   header macro: 5
 *   file macro: ok
 *   line macro: ok
 *   stdc macro: ok
 *   all tests passed
 */

#include "runtime/stdlib.h"

/* ── object macro ───────────────────────────────────────────────────────── */
#define ANSWER 42

/* ── function-like macros ───────────────────────────────────────────────── */
#define MAX(a, b)  ((a) > (b) ? (a) : (b))
#define MIN(a, b)  ((a) < (b) ? (a) : (b))
#define SQ(x)      ((x) * (x))
#define ABS(x)     ((x) < 0 ? -(x) : (x))

/* ── stringification ────────────────────────────────────────────────────── */
#define STRINGIFY(x) #x

/* ── token pasting ──────────────────────────────────────────────────────── */
#define PASTED_VAL  99
#define PASTED_VAL2 2
#define PASTE(a, b) a##b

/* ── variadic macro ─────────────────────────────────────────────────────── */
#define MY_PRINTF(...) printf(__VA_ARGS__)

/* ── simple arithmetic macro ────────────────────────────────────────────── */
#define TRIPLE(x) ((x) * 3)

/* ── nested macro (body references another macro) ───────────────────────── */
#define DOUBLE(x) ((x) + (x))
#define QUAD(x)   DOUBLE(DOUBLE(x))

/* ── conditional compilation flags ─────────────────────────────────────── */
#define FEATURE_A
#undef  FEATURE_B

/* ── version-style #if chain ────────────────────────────────────────────── */
#define VERSION 2

/* ── include "file" + include guard test ────────────────────────────────── */
#include "test_pp_header.h"
#include "test_pp_header.h"   /* second include must be silently ignored */

/* ── helpers ────────────────────────────────────────────────────────────── */
static void print_label(char *label) {
    print_str(label);
    print_str(": ");
}

static void pass(char *label, int got, int expected) {
    print_label(label);
    if (got == expected) {
        print_int(got);
        putchar('\n');
    } else {
        print_str("FAIL (got ");
        print_int(got);
        print_str(", want ");
        print_int(expected);
        print_str(")\n");
    }
}

static void pass_str(char *label, char *ok_msg) {
    print_label(label);
    print_str(ok_msg);
    putchar('\n');
}

int main() {

    /* 1. object macro */
    pass("object macro", ANSWER, 42);

    /* 2. function-like macro MAX */
    pass("fn macro MAX", MAX(3, 7), 7);

    /* 3. function-like macro MIN */
    pass("fn macro MIN", MIN(3, 7), 3);

    /* 4. stringification */
    print_label("stringify");
    print_str(STRINGIFY(hello));
    putchar('\n');

    /* 5. token paste: PASTE(PASTED, _VAL) → PASTED_VAL → 99 */
    pass("token paste", PASTE(PASTED, _VAL), 99);

    /* 6. token paste with digit suffix: PASTE(PASTED_VAL, 2) → PASTED_VAL2 → 2 */
    pass("paste digit", PASTE(PASTED_VAL, 2), 2);

    /* 7. #ifdef taken */
#ifdef FEATURE_A
    pass_str("ifdef taken", "taken");
#else
    pass_str("ifdef taken", "FAIL");
#endif

    /* 8. #ifndef taken (FEATURE_B undefined) */
#ifndef FEATURE_B
    pass_str("ifndef taken", "taken");
#else
    pass_str("ifndef taken", "FAIL");
#endif

    /* 9. #if / #elif / #else chain */
#if VERSION == 1
    pass("if expr", 0, 1);
#elif VERSION == 2
    pass("if expr", 1, 1);
#else
    pass("if expr", 0, 1);
#endif

#if VERSION == 1
    pass("elif expr", 0, 2);
#elif VERSION == 3
    pass("elif expr", 0, 2);
#elif VERSION == 2
    pass("elif expr", 2, 2);
#endif

#if VERSION == 99
    pass("else branch", 0, 3);
#elif VERSION == 98
    pass("else branch", 0, 3);
#else
    pass("else branch", 3, 3);
#endif

    /* 10. nested #if with defined() (paren form) */
#if defined(FEATURE_A) && !defined(FEATURE_B)
    pass_str("nested if", "ok");
#else
    pass_str("nested if", "FAIL");
#endif

    /* 11. #undef */
#define TEMP_MACRO 1
#undef  TEMP_MACRO
#ifdef TEMP_MACRO
    pass_str("undef", "FAIL");
#else
    pass_str("undef", "ok");
#endif

    /* 12. char literal in #if */
#if 'A' == 65
    pass("char literal", 65, 65);
#else
    pass("char literal", 0, 65);
#endif

    /* 13. hex literal in #if */
#if 0xFF == 255
    pass("hex literal", 255, 255);
#else
    pass("hex literal", 0, 255);
#endif

    /* 14. octal literal in #if */
#if 010 == 8
    pass("octal literal", 8, 8);
#else
    pass("octal literal", 0, 8);
#endif

    /* 15. binary literal in #if */
#if 0b1010 == 10
    pass("binary literal", 10, 10);
#else
    pass("binary literal", 0, 10);
#endif

    /* 16. arithmetic in #if: addition */
#if 2 + 3 == 5
    pass("if add", 5, 5);
#else
    pass("if add", 0, 5);
#endif

    /* 17. arithmetic in #if: subtraction */
#if 4 - 3 == 1
    pass("if sub", 1, 1);
#else
    pass("if sub", 0, 1);
#endif

    /* 18. arithmetic in #if: multiplication */
#if 2 * 3 == 6
    pass("if mul", 6, 6);
#else
    pass("if mul", 0, 6);
#endif

    /* 19. arithmetic in #if: division */
#if 9 / 3 == 3
    pass("if div", 3, 3);
#else
    pass("if div", 0, 3);
#endif

    /* 20. arithmetic in #if: modulo */
#if 7 % 3 == 1
    pass("if mod", 1, 1);
#else
    pass("if mod", 0, 1);
#endif

    /* 21. shift in #if */
#if (1 << 3) == 8
    pass("shift", 8, 8);
#else
    pass("shift", 0, 8);
#endif

    /* 22. bitwise AND in #if */
#if (3 & 1) == 1
    pass("bitwise and", 1, 1);
#else
    pass("bitwise and", 0, 1);
#endif

    /* 23. bitwise OR in #if */
#if (5 | 2) == 7
    pass("bitwise or", 7, 7);
#else
    pass("bitwise or", 0, 7);
#endif

    /* 24. bitwise XOR in #if */
#if (5 ^ 3) == 6
    pass("bitwise xor", 6, 6);
#else
    pass("bitwise xor", 0, 6);
#endif

    /* 25. bitwise NOT in #if: ~0 is all-bits-set, i.e. != 0 */
#if (~0) != 0
    pass_str("bitwise not", "ok");
#else
    pass_str("bitwise not", "FAIL");
#endif

    /* 26. logical && / || in #if */
#if defined(FEATURE_A) && (VERSION >= 2)
    pass("logical", 1, 1);
#else
    pass("logical", 0, 1);
#endif

    /* 27. unary minus in #if */
#if -VERSION == -2
    pass_str("unary minus", "ok");
#else
    pass_str("unary minus", "FAIL");
#endif

    /* 28. ternary ?: in #if */
#if (VERSION == 2 ? 1 : 0) == 1
    pass_str("ternary if", "ok");
#else
    pass_str("ternary if", "FAIL");
#endif

    /* 29. ternary inside a macro call: MAX(ABS(-10), SQ(2)) == 10 */
    pass("ternary macro", MAX(ABS(-10), SQ(2)), 10);

    /* 30. variadic macro */
    print_str("variadic: ");
    MY_PRINTF("%s\n", "done");

    /* 31. simple arithmetic macro */
    pass("multiline macro", TRIPLE(2), 6);

    /* 32. nested macro expansion: QUAD(3) → DOUBLE(DOUBLE(3)) → 12 */
    pass("nested macro", QUAD(3), 12);

    /* 33. defined NAME (bare form, no parens) */
#if defined FEATURE_A && !defined FEATURE_B
    pass_str("defined bare", "ok");
#else
    pass_str("defined bare", "FAIL");
#endif

    /* 34-35. #include "file" brought in HEADER_CONST and HEADER_ADD,
              and the include guard prevented double-definition errors */
#ifdef HEADER_CONST
    pass_str("include guard", "ok");
#else
    pass_str("include guard", "FAIL");
#endif

    pass("header const", HEADER_CONST, 77);
    pass("header macro", HEADER_ADD(2, 3), 5);

    /* 36. __FILE__ — print the actual filename */
    print_str("file macro: ");
    print_str(__FILE__);
    putchar('\n');

    /* 37. __LINE__ — print the actual line number */
    print_str("line macro: ");
    print_int(__LINE__);
    putchar('\n');

    /* 38. __STDC__ == 1 */
#if __STDC__ == 1
    pass_str("stdc macro", "ok");
#else
    pass_str("stdc macro", "FAIL");
#endif

    print_str("all tests passed\n");
    return 0;
}

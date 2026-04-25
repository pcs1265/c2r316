/*
 * stdint.h — fixed-width integer types for the R316 C compiler
 *
 * R316 is a 16-bit word-addressed machine:
 *   int / unsigned int  — 16-bit (native word)
 *   long / unsigned long — 32-bit (two words; arithmetic not yet fully implemented)
 *
 * There is no native 8-bit type; int8_t / uint8_t alias int / unsigned int.
 */

#ifndef STDINT_H
#define STDINT_H

/* ── Exact-width types ──────────────────────────────────────────────────── */

typedef int             int8_t;
typedef unsigned int    uint8_t;
typedef int             int16_t;
typedef unsigned int    uint16_t;
typedef long            int32_t;
typedef unsigned long   uint32_t;

/* ── Least-width types ──────────────────────────────────────────────────── */

typedef int             int_least8_t;
typedef unsigned int    uint_least8_t;
typedef int             int_least16_t;
typedef unsigned int    uint_least16_t;
typedef long            int_least32_t;
typedef unsigned long   uint_least32_t;

/* ── Fast types (same as least on this target) ──────────────────────────── */

typedef int             int_fast8_t;
typedef unsigned int    uint_fast8_t;
typedef int             int_fast16_t;
typedef unsigned int    uint_fast16_t;
typedef long            int_fast32_t;
typedef unsigned long   uint_fast32_t;

/* ── Pointer-sized types (16-bit address space) ─────────────────────────── */

typedef int             intptr_t;
typedef unsigned int    uintptr_t;
typedef int             ptrdiff_t;
typedef unsigned int    size_t;

/* ── Maximum-width type ─────────────────────────────────────────────────── */

typedef long            intmax_t;
typedef unsigned long   uintmax_t;

/* ── Limits ─────────────────────────────────────────────────────────────── */

#define INT8_MIN    (-128)
#define INT8_MAX    127
#define UINT8_MAX   255

#define INT16_MIN   (-32768)
#define INT16_MAX   32767
#define UINT16_MAX  65535

#define INT32_MIN   (-2147483648)
#define INT32_MAX   2147483647
#define UINT32_MAX  4294967295

#define INTPTR_MIN  INT16_MIN
#define INTPTR_MAX  INT16_MAX
#define UINTPTR_MAX UINT16_MAX

#define INTMAX_MIN  INT32_MIN
#define INTMAX_MAX  INT32_MAX
#define UINTMAX_MAX UINT32_MAX

#define SIZE_MAX    UINT16_MAX
#define PTRDIFF_MIN INT16_MIN
#define PTRDIFF_MAX INT16_MAX

/* ── Constant macros ─────────────────────────────────────────────────────── */

#define INT8_C(x)   (x)
#define UINT8_C(x)  (x)
#define INT16_C(x)  (x)
#define UINT16_C(x) (x)
#define INT32_C(x)  (x)
#define UINT32_C(x) (x)
#define INTMAX_C(x) (x)
#define UINTMAX_C(x) (x)

#endif /* STDINT_H */

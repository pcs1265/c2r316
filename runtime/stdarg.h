/*
 * stdarg.h — variadic argument support for the R316 C compiler
 *
 * __builtin_va_list, __builtin_va_start, __builtin_va_arg, and
 * __builtin_va_end are compiler built-ins recognised by the parser
 * and IR generator.  The user-facing names (va_list, va_start, etc.)
 * are defined here as a typedef and macros, mirroring the GCC style.
 */

#ifndef STDARG_H
#define STDARG_H

typedef __builtin_va_list va_list;

#define va_start(v, l)  __builtin_va_start(v, l)
#define va_arg(v, l)    __builtin_va_arg(v, l)
#define va_end(v)       __builtin_va_end(v)

#endif /* STDARG_H */

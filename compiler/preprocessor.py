"""
C to R316 Compiler - Preprocessor

Handles a subset of C preprocessor directives before lexing:
  #include "file"   — file inclusion (relative to the including file)
  #define NAME val  — object-like macros (token replacement)
  #define NAME(p)   — function-like macros (simple text substitution)
  #undef NAME       — remove a macro
  #ifdef / #ifndef / #else / #endif — conditional compilation
  #if 0 / #if 1    — simple constant conditionals

Limitations:
  - No #include <...> (system headers); angle-bracket includes are ignored
  - Macro expansion is not recursive (no macro-calling-macro)
  - #if supports only literal 0/1 and defined(NAME)
"""

import os
import re


class PreprocError(Exception):
    pass


# Matches a valid C identifier
_IDENT_RE = re.compile(r'[A-Za-z_]\w*')


def preprocess(src: str, filepath: str, _seen: set | None = None,
               _defines: 'dict | None' = None) -> str:
    """
    Preprocess `src` (contents of `filepath`).
    Returns the expanded source string.
    `_seen` tracks included paths to detect circular includes.
    `_defines` is the shared macro table (passed into recursive includes so that
    macros defined in headers are visible in the including file).
    """
    if _seen is None:
        _seen = set()
    base_dir = os.path.dirname(os.path.abspath(filepath))

    # Share one defines dict across the whole inclusion tree
    defines: dict[str, tuple[list[str] | None, str]]
    if _defines is not None:
        defines = _defines
    else:
        defines = {}
    # defines[name] = (params_or_None, body)
    # params_or_None: None  -> object-like macro
    #                 list  -> function-like macro (param names)

    lines = src.splitlines(keepends=True)
    output: list[str] = []

    # Conditional compilation stack: list of booleans (True = currently emitting)
    cond_stack: list[bool] = []

    def _emitting() -> bool:
        return all(cond_stack) if cond_stack else True

    def _expand(text: str) -> str:
        """Expand all macros in text (single pass, not recursive)."""
        result = text

        # Function-like macros first (longest match wins via sort by name length desc)
        for name, (params, body) in sorted(defines.items(),
                                           key=lambda kv: -len(kv[0])):
            if params is None:
                continue
            # Match: NAME(arg1, arg2, ...)
            pattern = r'\b' + re.escape(name) + r'\s*\(([^)]*)\)'
            def _replace_func(m, p=params, b=body):
                raw_args = [a.strip() for a in m.group(1).split(',')]
                repl = b
                for pname, arg in zip(p, raw_args):
                    repl = re.sub(r'\b' + re.escape(pname) + r'\b', arg, repl)
                return repl
            result = re.sub(pattern, _replace_func, result)

        # Object-like macros
        for name, (params, body) in sorted(defines.items(),
                                           key=lambda kv: -len(kv[0])):
            if params is not None:
                continue
            result = re.sub(r'\b' + re.escape(name) + r'\b', body, result)

        return result

    def _eval_condition(expr: str) -> bool:
        expr = expr.strip()
        # defined(NAME) or defined NAME
        m = re.match(r'^defined\s*\(?\s*([A-Za-z_]\w*)\s*\)?$', expr)
        if m:
            return m.group(1) in defines
        # Try expanding and evaluating as integer
        expanded = _expand(expr)
        try:
            return bool(int(expanded.strip()))
        except ValueError:
            # Non-zero string counts as true, 0 / empty as false
            return expanded.strip() not in ('', '0')

    i = 0
    while i < len(lines):
        raw = lines[i]
        stripped = raw.strip()

        # Handle line continuations (backslash-newline)
        while stripped.endswith('\\\n') or stripped.endswith('\\'):
            i += 1
            if i >= len(lines):
                break
            stripped = stripped.rstrip('\\\n').rstrip('\\') + ' ' + lines[i].strip()
        i += 1

        if not stripped.startswith('#'):
            if _emitting():
                output.append(_expand(raw) if defines else raw)
            else:
                output.append('\n')
            continue

        # Directive line
        directive_body = stripped[1:].lstrip()
        parts = directive_body.split(None, 1)
        directive = parts[0] if parts else ''
        rest = parts[1] if len(parts) > 1 else ''

        if directive == 'include':
            if not _emitting():
                output.append('\n')
                continue
            # Only handle "..." style
            m = re.match(r'^"([^"]+)"', rest.strip())
            if not m:
                # angle-bracket include: skip silently
                output.append('\n')
                continue
            inc_path = os.path.normpath(os.path.join(base_dir, m.group(1)))
            if inc_path in _seen:
                output.append('\n')  # already included (include guard)
                continue
            _seen.add(inc_path)
            try:
                with open(inc_path, 'r', encoding='utf-8') as f:
                    inc_src = f.read()
            except FileNotFoundError:
                raise PreprocError(f'#include file not found: {inc_path}')
            # Recursively preprocess the included file (shares macro table)
            expanded_inc = preprocess(inc_src, inc_path, _seen, _defines=defines)
            # Inject line markers so errors point to the right file (simplified)
            output.append(f'// <included: {m.group(1)}>\n')
            output.append(expanded_inc)
            output.append(f'// </included: {m.group(1)}>\n')

        elif directive == 'define':
            if not _emitting():
                output.append('\n')
                continue
            # Function-like: NAME(p1,p2) body
            m_func = re.match(r'([A-Za-z_]\w*)\(([^)]*)\)\s*(.*)', rest)
            m_obj  = re.match(r'([A-Za-z_]\w*)\s*(.*)', rest)
            if m_func:
                name   = m_func.group(1)
                params = [p.strip() for p in m_func.group(2).split(',') if p.strip()]
                body   = m_func.group(3).strip()
                defines[name] = (params, body)
            elif m_obj:
                name = m_obj.group(1)
                body = m_obj.group(2).strip()
                defines[name] = (None, body)
            output.append('\n')

        elif directive == 'undef':
            if not _emitting():
                output.append('\n')
                continue
            m = re.match(r'([A-Za-z_]\w*)', rest.strip())
            if m:
                defines.pop(m.group(1), None)
            output.append('\n')

        elif directive == 'ifdef':
            name = rest.strip()
            cond_stack.append(name in defines)
            output.append('\n')

        elif directive == 'ifndef':
            name = rest.strip()
            cond_stack.append(name not in defines)
            output.append('\n')

        elif directive == 'if':
            cond_stack.append(_eval_condition(rest))
            output.append('\n')

        elif directive == 'elif':
            if not cond_stack:
                raise PreprocError('#elif without #if')
            # Flip: if we were in a true branch, now we're done; if false, evaluate
            if cond_stack[-1]:
                cond_stack[-1] = False
            else:
                cond_stack[-1] = _eval_condition(rest)
            output.append('\n')

        elif directive == 'else':
            if not cond_stack:
                raise PreprocError('#else without #if')
            cond_stack[-1] = not cond_stack[-1]
            output.append('\n')

        elif directive == 'endif':
            if not cond_stack:
                raise PreprocError('#endif without #if')
            cond_stack.pop()
            output.append('\n')

        elif directive == 'pragma' or directive == 'error' or directive == 'warning':
            # Silently ignore #pragma; raise on #error when emitting
            if directive == 'error' and _emitting():
                raise PreprocError(f'#error: {rest}')
            output.append('\n')

        else:
            # Unknown directive — pass through if emitting, otherwise skip
            if _emitting():
                output.append(raw)
            else:
                output.append('\n')

    return ''.join(output)

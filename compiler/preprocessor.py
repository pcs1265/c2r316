"""
C to R316 Compiler - Preprocessor
Text-level macro expansion and file inclusion, run before the lexer.

Supported directives:
  #include "file"         — include file relative to the including file's dir
  #define NAME            — define a flag (no value)
  #define NAME value      — define an object macro (single token replacement)
  #undef NAME             — remove a macro
  #ifdef NAME / #ifndef NAME / #else / #endif — conditional compilation
"""

from __future__ import annotations
import os
import re


class PreprocessorError(Exception):
    def __init__(self, msg: str, filename: str = '', line: int = 0):
        self.filename = filename
        self.line = line
        super().__init__(f'{filename}:{line}: {msg}' if filename else msg)


def preprocess(src: str, src_path: str = '', defines: dict = None) -> str:
    """
    Run the preprocessor over `src` and return the expanded source text.
    `src_path` is the path of the file being processed (used to resolve
    relative #include paths).  `defines` is an optional initial macro dict.
    """
    defines = dict(defines) if defines else {}
    src_dir = os.path.dirname(os.path.abspath(src_path)) if src_path else os.getcwd()
    return _process(src, src_path or '<stdin>', src_dir, defines, set())


def _process(src: str, filename: str, base_dir: str,
             defines: dict, include_stack: set) -> str:
    lines = src.split('\n')
    out = []
    # Conditional stack: each entry is (taking, ever_taken)
    # taking     = are we currently emitting lines?
    # ever_taken = has any branch of this if/else been taken?
    cond_stack = []

    def _taking() -> bool:
        return all(taking for taking, _ in cond_stack)

    for lineno, line in enumerate(lines, 1):
        stripped = line.strip()

        if not stripped.startswith('#'):
            if _taking():
                # expand macros in non-directive lines
                out.append(_expand(line, defines))
            else:
                out.append('')
            continue

        # directive
        directive_line = stripped[1:].strip()
        directive, _, rest = directive_line.partition(' ')
        rest = rest.strip()

        if directive == 'ifdef':
            name = rest.split()[0] if rest else ''
            taking = name in defines
            cond_stack.append((taking and _taking(), taking))
            out.append('')

        elif directive == 'ifndef':
            name = rest.split()[0] if rest else ''
            taking = name not in defines
            cond_stack.append((taking and _taking(), taking))
            out.append('')

        elif directive == 'else':
            if not cond_stack:
                raise PreprocessorError('#else without #ifdef', filename, lineno)
            taking, ever_taken = cond_stack[-1]
            new_taking = (not ever_taken) and _taking_parent(cond_stack)
            cond_stack[-1] = (new_taking, ever_taken or new_taking)
            out.append('')

        elif directive == 'endif':
            if not cond_stack:
                raise PreprocessorError('#endif without #ifdef', filename, lineno)
            cond_stack.pop()
            out.append('')

        elif not _taking():
            # skip all other directives inside a false conditional block
            out.append('')

        elif directive == 'include':
            m = re.match(r'^"([^"]+)"$', rest)
            if not m:
                raise PreprocessorError(
                    f'#include syntax error: expected "file"', filename, lineno)
            inc_path_rel = m.group(1)
            inc_path = os.path.join(base_dir, inc_path_rel)
            if not os.path.isfile(inc_path):
                raise PreprocessorError(
                    f'#include file not found: {inc_path_rel}', filename, lineno)
            real_inc = os.path.realpath(inc_path)
            if real_inc in include_stack:
                out.append('')  # guard: already included
                continue
            new_stack = include_stack | {real_inc}
            inc_src = open(inc_path, encoding='utf-8').read()
            inc_dir = os.path.dirname(inc_path)
            expanded = _process(inc_src, inc_path, inc_dir, defines, new_stack)
            out.append(expanded)

        elif directive == 'define':
            parts = rest.split(None, 1)
            if not parts:
                raise PreprocessorError('#define requires a name', filename, lineno)
            name = parts[0]
            value = parts[1] if len(parts) > 1 else ''
            defines[name] = value
            out.append('')

        elif directive == 'undef':
            name = rest.split()[0] if rest else ''
            defines.pop(name, None)
            out.append('')

        else:
            raise PreprocessorError(
                f'Unknown preprocessor directive: #{directive}', filename, lineno)

    if cond_stack:
        raise PreprocessorError('unterminated #ifdef / #ifndef', filename, len(lines))

    return '\n'.join(out)


def _taking_parent(cond_stack: list) -> bool:
    """Are all enclosing conditionals currently taking?"""
    return all(taking for taking, _ in cond_stack[:-1])


def _expand(line: str, defines: dict) -> str:
    """Replace all defined macro names in `line` with their values."""
    if not defines:
        return line
    # Sort longest name first to avoid partial replacements
    for name in sorted(defines, key=len, reverse=True):
        value = defines[name]
        if value:
            line = re.sub(r'\b' + re.escape(name) + r'\b', value, line)
    return line

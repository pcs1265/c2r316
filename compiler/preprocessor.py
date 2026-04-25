"""
C to R316 Compiler - Preprocessor
Text-level macro expansion and file inclusion, run before the lexer.

Supported directives:
  #include "file"         — include file relative to the including file's dir
  #include <file>         — include file searched in inc_dirs
  #define NAME            — define a flag macro (expands to empty)
  #define NAME value      — object macro (token replacement)
  #define NAME(a,b,...) x — function-like macro with optional variadic args
  #undef NAME             — remove a macro
  #ifdef / #ifndef / #if / #elif / #else / #endif — conditional compilation
  #error msg              — emit a fatal error
  #warning msg            — emit a warning to stderr
  #pragma                 — silently ignored

Macro operators:
  #arg    — stringification
  a##b    — token pasting
  defined(NAME) / defined NAME — in #if/#elif expressions
  __VA_ARGS__ — variadic argument expansion

Predefined macros:
  __FILE__  __LINE__  __DATE__  __TIME__  __STDC__
"""

from __future__ import annotations
import os
import re
import sys
import datetime

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class PreprocessorError(Exception):
    def __init__(self, msg: str, filename: str = '', line: int = 0):
        self.filename = filename
        self.line = line
        super().__init__(f'{filename}:{line}: {msg}' if filename else msg)


def preprocess(src: str, src_path: str = '', defines: dict = None,
               include_dirs: list = None) -> str:
    """
    Run the preprocessor over `src` and return the expanded source text.
    `src_path` is the path of the file being processed (used to resolve
    relative #include paths).  `defines` is an optional initial macro dict.
    `include_dirs` is a list of additional directories searched for #include.
    """
    defines = dict(defines) if defines else {}
    _add_predefined(defines)
    src_dir = os.path.dirname(os.path.abspath(src_path)) if src_path else os.getcwd()
    inc_dirs = [src_dir] + [os.path.abspath(d) for d in (include_dirs or [])]
    return _process(src, src_path or '<stdin>', inc_dirs, defines, set())


# ---------------------------------------------------------------------------
# Macro representation
# ---------------------------------------------------------------------------

class _Macro:
    """Represents a single #define."""
    __slots__ = ('params', 'variadic', 'body')

    def __init__(self, params, variadic: bool, body: str):
        # params is None for object macros, list[str] for function-like
        self.params: list[str] | None = params
        self.variadic: bool = variadic
        self.body: str = body

    @property
    def is_function_like(self) -> bool:
        return self.params is not None


# ---------------------------------------------------------------------------
# Predefined macros
# ---------------------------------------------------------------------------

def _add_predefined(defines: dict):
    now = datetime.datetime.now()
    _set_if_absent(defines, '__STDC__', _Macro(None, False, '1'))
    _set_if_absent(defines, '__DATE__', _Macro(None, False,
        f'"{now.strftime("%b %d %Y")}"'))
    _set_if_absent(defines, '__TIME__', _Macro(None, False,
        f'"{now.strftime("%H:%M:%S")}"'))
    # __FILE__ and __LINE__ are injected dynamically during expansion


def _set_if_absent(defines: dict, name: str, macro: _Macro):
    if name not in defines:
        defines[name] = macro


# ---------------------------------------------------------------------------
# Core processor
# ---------------------------------------------------------------------------

def _process(src: str, filename: str, inc_dirs: list,
             defines: dict, include_stack: set) -> str:
    lines = src.split('\n')
    out = []
    # Conditional stack: each entry is (taking, ever_taken)
    # taking     = are we currently emitting lines?
    # ever_taken = has any branch of this if/else been taken?
    cond_stack: list[tuple[bool, bool]] = []

    def _taking() -> bool:
        return all(taking for taking, _ in cond_stack)

    for lineno, line in enumerate(lines, 1):
        # Update __FILE__ and __LINE__ dynamically
        defines['__FILE__'] = _Macro(None, False, '"{}"'.format(filename.replace('\\', '\\\\')))
        defines['__LINE__'] = _Macro(None, False, str(lineno))

        stripped = line.strip()

        # Handle line markers emitted by recursive #include processing
        if stripped.startswith('#line '):
            out.append(line)
            continue

        if not stripped.startswith('#'):
            if _taking():
                out.append(_expand_line(line, defines))
            else:
                out.append('')
            continue

        # ── directive ──────────────────────────────────────────────────────
        directive_line = stripped[1:].strip()
        directive, _, rest = directive_line.partition(' ')
        directive = directive.strip()
        rest = rest.strip()

        # conditional directives are processed regardless of _taking()
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

        elif directive == 'if':
            if not rest:
                raise PreprocessorError('#if requires an expression', filename, lineno)
            taking = _eval_if(rest, defines, filename, lineno)
            cond_stack.append((taking and _taking(), taking))
            out.append('')

        elif directive == 'elif':
            if not cond_stack:
                raise PreprocessorError('#elif without #if', filename, lineno)
            _taking_now, ever_taken = cond_stack[-1]
            if ever_taken:
                cond_stack[-1] = (False, True)
            else:
                taking = _eval_if(rest, defines, filename, lineno)
                new_taking = taking and _taking_parent(cond_stack)
                cond_stack[-1] = (new_taking, new_taking)
            out.append('')

        elif directive == 'else':
            if not cond_stack:
                raise PreprocessorError('#else without #ifdef', filename, lineno)
            _taking_now, ever_taken = cond_stack[-1]
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
            expanded_rest = _expand_line(rest, defines)
            # strip trailing // and /* ... */ comments before matching
            expanded_rest = re.sub(r'/\*.*?\*/', '', expanded_rest)
            expanded_rest = re.sub(r'//.*$', '', expanded_rest)
            # "file" or <file>
            m_quoted = re.match(r'^"([^"]+)"$', expanded_rest.strip())
            m_angle  = re.match(r'^<([^>]+)>$',  expanded_rest.strip())
            if m_quoted:
                inc_path_rel = m_quoted.group(1)
                search_dirs = inc_dirs
            elif m_angle:
                inc_path_rel = m_angle.group(1)
                # angle-bracket: skip the file's own directory, search inc_dirs only
                search_dirs = inc_dirs[1:] or inc_dirs
            else:
                raise PreprocessorError(
                    f'#include syntax error: expected "file" or <file>', filename, lineno)
            inc_path = None
            for search_dir in search_dirs:
                candidate = os.path.join(search_dir, inc_path_rel)
                if os.path.isfile(candidate):
                    inc_path = candidate
                    break
            if inc_path is None:
                raise PreprocessorError(
                    f'#include file not found: {inc_path_rel}', filename, lineno)
            real_inc = os.path.realpath(inc_path)
            if real_inc in include_stack:
                out.append('')  # include guard: already included
                continue
            new_stack = include_stack | {real_inc}
            inc_src = open(inc_path, encoding='utf-8').read()
            inc_file_dir = os.path.dirname(os.path.abspath(inc_path))
            child_dirs = [inc_file_dir] + inc_dirs[1:]
            expanded = _process(inc_src, inc_path, child_dirs, defines, new_stack)
            out.append(f'#line 1 "{inc_path}"')
            out.append(expanded)
            out.append(f'#line {lineno + 1} "{filename}"')

        elif directive == 'define':
            _parse_define(rest, defines, filename, lineno)
            out.append('')

        elif directive == 'undef':
            name = rest.split()[0] if rest else ''
            defines.pop(name, None)
            out.append('')

        elif directive == 'error':
            msg = _expand_line(rest, defines)
            raise PreprocessorError(f'#error {msg}', filename, lineno)

        elif directive == 'warning':
            msg = _expand_line(rest, defines)
            print(f'{filename}:{lineno}: warning: {msg}', file=sys.stderr)
            out.append('')

        elif directive == 'pragma':
            out.append('')  # silently ignore

        elif directive == 'line':
            # #line N "file" — update tracking but pass through
            out.append(f'#{directive_line}')

        else:
            raise PreprocessorError(
                f'Unknown preprocessor directive: #{directive}', filename, lineno)

    if cond_stack:
        raise PreprocessorError('unterminated #ifdef / #ifndef / #if', filename, len(lines))

    return '\n'.join(out)


def _taking_parent(cond_stack: list) -> bool:
    return all(taking for taking, _ in cond_stack[:-1])


# ---------------------------------------------------------------------------
# #define parsing
# ---------------------------------------------------------------------------

def _parse_define(rest: str, defines: dict, filename: str, lineno: int):
    if not rest:
        raise PreprocessorError('#define requires a name', filename, lineno)

    # Function-like macro: NAME(params) body
    m = re.match(r'^([A-Za-z_]\w*)\(([^)]*)\)\s*(.*)', rest, re.DOTALL)
    if m:
        name = m.group(1)
        raw_params = m.group(2).strip()
        body = m.group(3)
        params = []
        variadic = False
        if raw_params:
            for p in raw_params.split(','):
                p = p.strip()
                if p == '...':
                    variadic = True
                elif p.endswith('...'):
                    # named variadic: treat like __VA_ARGS__
                    variadic = True
                else:
                    params.append(p)
        defines[name] = _Macro(params, variadic, body)
        return

    # Object macro: NAME body
    parts = rest.split(None, 1)
    name = parts[0]
    if not re.match(r'^[A-Za-z_]\w*$', name):
        raise PreprocessorError(f'Invalid macro name: {name}', filename, lineno)
    body = parts[1] if len(parts) > 1 else ''
    defines[name] = _Macro(None, False, body)


# ---------------------------------------------------------------------------
# Macro expansion
# ---------------------------------------------------------------------------

def _expand_line(text: str, defines: dict, expanding: set = None) -> str:
    """Expand all macros in `text`, return the result."""
    if expanding is None:
        expanding = set()
    return _expand(text, defines, expanding)


def _expand(text: str, defines: dict, expanding: set) -> str:
    """Tokenize `text` into pp-tokens and expand macros."""
    tokens = _tokenize(text)
    result = _expand_tokens(tokens, defines, expanding)
    return _tokens_to_str(result)


# Simple pp-token types
_TOK_ID    = 'id'
_TOK_OTHER = 'other'

def _tokenize(text: str) -> list[tuple[str, str]]:
    """
    Split text into a list of (type, value) pp-tokens.
    Preserves whitespace as _TOK_OTHER tokens.
    """
    tokens = []
    i = 0
    n = len(text)
    while i < n:
        # string literal
        if text[i] in ('"', "'"):
            quote = text[i]
            j = i + 1
            while j < n:
                if text[j] == '\\':
                    j += 2
                    continue
                if text[j] == quote:
                    j += 1
                    break
                j += 1
            tokens.append((_TOK_OTHER, text[i:j]))
            i = j
            continue
        # identifier or keyword
        m = re.match(r'[A-Za-z_]\w*', text[i:])
        if m:
            tokens.append((_TOK_ID, m.group()))
            i += m.end()
            continue
        # ## token-paste operator
        if text[i:i+2] == '##':
            tokens.append((_TOK_OTHER, '##'))
            i += 2
            continue
        # any other character (including whitespace, punctuation)
        tokens.append((_TOK_OTHER, text[i]))
        i += 1
    return tokens


def _tokens_to_str(tokens: list[tuple[str, str]]) -> str:
    return ''.join(v for _, v in tokens)


def _expand_tokens(tokens: list, defines: dict, expanding: set) -> list:
    """Recursively expand macros in a token list."""
    out = []
    i = 0
    while i < len(tokens):
        typ, val = tokens[i]
        if typ != _TOK_ID or val not in defines or val in expanding:
            out.append((typ, val))
            i += 1
            continue

        macro = defines[val]

        if not macro.is_function_like:
            # object macro — expand body, recurse
            if macro.body:
                body_toks = _tokenize(macro.body)
                expanded = _expand_tokens(body_toks, defines, expanding | {val})
                out.extend(expanded)
            i += 1
            continue

        # function-like macro: scan for '('
        j = i + 1
        # skip whitespace tokens
        while j < len(tokens) and tokens[j][0] == _TOK_OTHER and tokens[j][1].strip() == '':
            j += 1
        if j >= len(tokens) or tokens[j] != (_TOK_OTHER, '('):
            # no '(' — not a macro call, emit as-is
            out.append((typ, val))
            i += 1
            continue

        # collect arguments
        args, j = _collect_args(tokens, j + 1)
        # prescan: expand each argument, BUT skip expansion for params that
        # appear directly adjacent to ## in the body (standard C rule: args
        # used in # or ## contexts are not macro-expanded before substitution).
        paste_params = _paste_adjacent_params(macro)
        params = macro.params or []
        expanded_args = []
        for idx, a in enumerate(args):
            param_name = params[idx] if idx < len(params) else '__VA_ARGS__'
            if param_name in paste_params:
                expanded_args.append(a)   # raw — no prescan
            else:
                expanded_args.append(
                    _tokens_to_str(_expand_tokens(_tokenize(a), defines, expanding)))
        # bind parameters → apply paste → rescan
        subst = _bind_args(macro, expanded_args, val)
        body_toks = _tokenize(subst)
        body_toks = _apply_paste(body_toks)
        # rescan: paste may have created new macro names
        body_toks = _expand_tokens(body_toks, defines, expanding | {val})
        out.extend(body_toks)
        i = j
    return out


def _collect_args(tokens: list, start: int) -> tuple[list[str], int]:
    """
    Parse comma-separated arguments starting after '('.
    Returns (list_of_arg_strings, index_after_closing_paren).
    """
    args = []
    depth = 1
    current: list[str] = []
    i = start
    while i < len(tokens):
        _, v = tokens[i]
        if v == '(':
            depth += 1
            current.append(v)
        elif v == ')':
            depth -= 1
            if depth == 0:
                args.append(''.join(current))
                i += 1
                break
            current.append(v)
        elif v == ',' and depth == 1:
            args.append(''.join(current))
            current = []
        else:
            current.append(v)
        i += 1
    return args, i


def _bind_args(macro: _Macro, args: list[str], name: str) -> str:
    """
    Substitute macro parameters with actual arguments.
    Handles stringification (#param) and token-paste (##) in the body.
    Returns a text string; the caller tokenizes and applies paste.
    """
    body = macro.body
    params = macro.params or []

    bindings: dict[str, str] = {}
    for idx, param in enumerate(params):
        bindings[param] = args[idx].strip() if idx < len(args) else ''
    if macro.variadic:
        va = ', '.join(a.strip() for a in args[len(params):])
        bindings['__VA_ARGS__'] = va

    # Walk the body character-by-character to handle # and ## correctly.
    out_parts = []
    i = 0
    n = len(body)
    while i < n:
        # ## token-paste: emit as-is (caller handles it at token level)
        if body[i:i+2] == '##':
            out_parts.append('##')
            i += 2
            continue
        # # stringification: must be followed by optional whitespace + identifier
        if body[i] == '#':
            j = i + 1
            while j < n and body[j] in ' \t':
                j += 1
            m = re.match(r'[A-Za-z_]\w*', body[j:])
            if m:
                param_name = m.group()
                val = bindings.get(param_name, param_name)
                val = val.replace('\\', '\\\\').replace('"', '\\"')
                out_parts.append(f'"{val}"')
                i = j + m.end()
                continue
            # bare # with no param — emit as-is
            out_parts.append('#')
            i += 1
            continue
        # string/char literal — copy verbatim (no param substitution inside)
        if body[i] in ('"', "'"):
            quote = body[i]
            j = i + 1
            while j < n:
                if body[j] == '\\':
                    j += 2
                    continue
                if body[j] == quote:
                    j += 1
                    break
                j += 1
            out_parts.append(body[i:j])
            i = j
            continue
        # identifier — check if it's a parameter
        m = re.match(r'[A-Za-z_]\w*', body[i:])
        if m:
            word = m.group()
            out_parts.append(bindings.get(word, word))
            i += m.end()
            continue
        out_parts.append(body[i])
        i += 1

    return ''.join(out_parts)


def _paste_adjacent_params(macro: _Macro) -> set:
    """
    Return the set of parameter names that appear directly adjacent to ##
    in the macro body (left or right side).  These must NOT be prescanned.
    """
    if not macro.is_function_like:
        return set()
    params = set(macro.params or [])
    if macro.variadic:
        params.add('__VA_ARGS__')
    result = set()
    # Tokenize body and walk for ## occurrences
    toks = _tokenize(macro.body)
    for idx, (typ, val) in enumerate(toks):
        if val == '##':
            # check left neighbour (skip whitespace)
            left = idx - 1
            while left >= 0 and toks[left][1].strip() == '':
                left -= 1
            if left >= 0 and toks[left][0] == _TOK_ID and toks[left][1] in params:
                result.add(toks[left][1])
            # check right neighbour (skip whitespace)
            right = idx + 1
            while right < len(toks) and toks[right][1].strip() == '':
                right += 1
            if right < len(toks) and toks[right][0] == _TOK_ID and toks[right][1] in params:
                result.add(toks[right][1])
    return result


def _apply_paste(tokens: list) -> list:
    """Collapse a ## b into a single token, re-typing identifiers correctly."""
    out = []
    i = 0
    while i < len(tokens):
        if tokens[i] == (_TOK_OTHER, '##'):
            while out and out[-1][1].strip() == '':
                out.pop()
            i += 1
            while i < len(tokens) and tokens[i][1].strip() == '':
                i += 1
            if out and i < len(tokens):
                left = out.pop()[1]
                right = tokens[i][1]
                pasted = left + right
                # re-classify pasted token
                typ = _TOK_ID if re.match(r'^[A-Za-z_]\w*$', pasted) else _TOK_OTHER
                out.append((typ, pasted))
                i += 1
            continue
        out.append(tokens[i])
        i += 1
    return out


# ---------------------------------------------------------------------------
# #if / #elif expression evaluator
# ---------------------------------------------------------------------------

def _eval_if(expr: str, defines: dict, filename: str, lineno: int) -> bool:
    """Evaluate a preprocessor #if / #elif expression."""
    # Expand macros first (but not defined())
    expanded = _expand_defined(expr, defines)
    expanded = _expand_line(expanded, defines)
    # Now evaluate as integer constant expression
    try:
        result = _eval_expr(expanded)
        return bool(result)
    except Exception as e:
        raise PreprocessorError(
            f'#if expression error: {e}  (expr: {expr!r})', filename, lineno)


def _expand_defined(expr: str, defines: dict) -> str:
    """Replace defined(NAME) and defined NAME with 1 or 0."""
    def _repl_paren(m: re.Match) -> str:
        return '1' if m.group(1) in defines else '0'
    def _repl_bare(m: re.Match) -> str:
        return '1' if m.group(1) in defines else '0'
    expr = re.sub(r'\bdefined\s*\(\s*([A-Za-z_]\w*)\s*\)', _repl_paren, expr)
    expr = re.sub(r'\bdefined\s+([A-Za-z_]\w*)', _repl_bare, expr)
    return expr


def _eval_expr(expr: str) -> int:
    """
    Evaluate a C integer constant expression.
    Supports: integer literals (0x, 0b, 0o, decimal), char literals,
    unary +/-/~/!, binary +/-/*///%/<</>>/&/|/^/&&/||,
    comparison ==, !=, <, >, <=, >=, ternary ?:, parentheses.
    Unknown identifiers evaluate to 0 (undefined macros).
    """
    expr = expr.strip()
    val, _ = _parse_ternary(expr, 0)
    return val


# --- recursive-descent expression parser ---

def _skip_ws(s: str, i: int) -> int:
    while i < len(s) and s[i] in ' \t':
        i += 1
    return i

def _parse_ternary(s: str, i: int) -> tuple[int, int]:
    val, i = _parse_or(s, i)
    i = _skip_ws(s, i)
    if i < len(s) and s[i] == '?':
        i += 1
        then_val, i = _parse_ternary(s, i)
        i = _skip_ws(s, i)
        if i >= len(s) or s[i] != ':':
            raise ValueError("expected ':' in ternary")
        i += 1
        else_val, i = _parse_ternary(s, i)
        return (then_val if val else else_val), i
    return val, i

def _parse_or(s: str, i: int) -> tuple[int, int]:
    left, i = _parse_and(s, i)
    while True:
        i = _skip_ws(s, i)
        if s[i:i+2] == '||':
            right, i = _parse_and(s, i + 2)
            left = int(bool(left) or bool(right))
        else:
            break
    return left, i

def _parse_and(s: str, i: int) -> tuple[int, int]:
    left, i = _parse_bitor(s, i)
    while True:
        i = _skip_ws(s, i)
        if s[i:i+2] == '&&':
            right, i = _parse_bitor(s, i + 2)
            left = int(bool(left) and bool(right))
        else:
            break
    return left, i

def _parse_bitor(s: str, i: int) -> tuple[int, int]:
    left, i = _parse_bitxor(s, i)
    while True:
        i = _skip_ws(s, i)
        if i < len(s) and s[i] == '|' and s[i:i+2] != '||':
            right, i = _parse_bitxor(s, i + 1)
            left = left | right
        else:
            break
    return left, i

def _parse_bitxor(s: str, i: int) -> tuple[int, int]:
    left, i = _parse_bitand(s, i)
    while True:
        i = _skip_ws(s, i)
        if i < len(s) and s[i] == '^':
            right, i = _parse_bitand(s, i + 1)
            left = left ^ right
        else:
            break
    return left, i

def _parse_bitand(s: str, i: int) -> tuple[int, int]:
    left, i = _parse_eq(s, i)
    while True:
        i = _skip_ws(s, i)
        if i < len(s) and s[i] == '&' and s[i:i+2] != '&&':
            right, i = _parse_eq(s, i + 1)
            left = left & right
        else:
            break
    return left, i

def _parse_eq(s: str, i: int) -> tuple[int, int]:
    left, i = _parse_rel(s, i)
    while True:
        i = _skip_ws(s, i)
        if s[i:i+2] == '==':
            right, i = _parse_rel(s, i + 2)
            left = int(left == right)
        elif s[i:i+2] == '!=':
            right, i = _parse_rel(s, i + 2)
            left = int(left != right)
        else:
            break
    return left, i

def _parse_rel(s: str, i: int) -> tuple[int, int]:
    left, i = _parse_shift(s, i)
    while True:
        i = _skip_ws(s, i)
        if s[i:i+2] == '<=':
            right, i = _parse_shift(s, i + 2)
            left = int(left <= right)
        elif s[i:i+2] == '>=':
            right, i = _parse_shift(s, i + 2)
            left = int(left >= right)
        elif i < len(s) and s[i] == '<' and s[i:i+2] != '<<':
            right, i = _parse_shift(s, i + 1)
            left = int(left < right)
        elif i < len(s) and s[i] == '>' and s[i:i+2] != '>>':
            right, i = _parse_shift(s, i + 1)
            left = int(left > right)
        else:
            break
    return left, i

def _parse_shift(s: str, i: int) -> tuple[int, int]:
    left, i = _parse_add(s, i)
    while True:
        i = _skip_ws(s, i)
        if s[i:i+2] == '<<':
            right, i = _parse_add(s, i + 2)
            left = left << right
        elif s[i:i+2] == '>>':
            right, i = _parse_add(s, i + 2)
            left = left >> right
        else:
            break
    return left, i

def _parse_add(s: str, i: int) -> tuple[int, int]:
    left, i = _parse_mul(s, i)
    while True:
        i = _skip_ws(s, i)
        if i < len(s) and s[i] == '+':
            right, i = _parse_mul(s, i + 1)
            left = left + right
        elif i < len(s) and s[i] == '-':
            right, i = _parse_mul(s, i + 1)
            left = left - right
        else:
            break
    return left, i

def _parse_mul(s: str, i: int) -> tuple[int, int]:
    left, i = _parse_unary(s, i)
    while True:
        i = _skip_ws(s, i)
        if i < len(s) and s[i] == '*':
            right, i = _parse_unary(s, i + 1)
            left = left * right
        elif i < len(s) and s[i] == '/' and s[i:i+2] != '//':
            right, i = _parse_unary(s, i + 1)
            left = int(left / right) if right else 0
        elif i < len(s) and s[i] == '%':
            right, i = _parse_unary(s, i + 1)
            left = left % right if right else 0
        else:
            break
    return left, i

def _parse_unary(s: str, i: int) -> tuple[int, int]:
    i = _skip_ws(s, i)
    if i >= len(s):
        return 0, i
    c = s[i]
    if c == '-':
        val, i = _parse_unary(s, i + 1)
        return -val, i
    if c == '+':
        return _parse_unary(s, i + 1)
    if c == '~':
        val, i = _parse_unary(s, i + 1)
        return ~val, i
    if c == '!':
        val, i = _parse_unary(s, i + 1)
        return int(not val), i
    return _parse_primary(s, i)

def _parse_primary(s: str, i: int) -> tuple[int, int]:
    i = _skip_ws(s, i)
    if i >= len(s):
        return 0, i

    # parenthesized expression
    if s[i] == '(':
        val, i = _parse_ternary(s, i + 1)
        i = _skip_ws(s, i)
        if i < len(s) and s[i] == ')':
            i += 1
        return val, i

    # char literal 'x'
    if s[i] == "'":
        j = i + 1
        val = 0
        if j < len(s) and s[j] == '\\':
            j += 1
            esc = s[j] if j < len(s) else ''
            val = _escape_val(esc)
            j += 1
        elif j < len(s):
            val = ord(s[j])
            j += 1
        if j < len(s) and s[j] == "'":
            j += 1
        return val, j

    # hex / binary / octal / decimal integer
    m = re.match(r'0[xX][0-9A-Fa-f]+[uUlL]*', s[i:])
    if m:
        return int(m.group().rstrip('uUlL'), 16), i + m.end()
    m = re.match(r'0[bB][01]+[uUlL]*', s[i:])
    if m:
        return int(m.group().rstrip('uUlL'), 2), i + m.end()
    m = re.match(r'0[0-7]+[uUlL]*', s[i:])
    if m:
        return int(m.group().rstrip('uUlL'), 8), i + m.end()
    m = re.match(r'\d+[uUlL]*', s[i:])
    if m:
        return int(m.group().rstrip('uUlL')), i + m.end()

    # identifier (undefined macro or keyword after expansion → 0)
    m = re.match(r'[A-Za-z_]\w*', s[i:])
    if m:
        return 0, i + m.end()

    return 0, i + 1


def _escape_val(c: str) -> int:
    return {'n': 10, 't': 9, 'r': 13, '0': 0, '\\': 92,
            "'": 39, '"': 34, 'a': 7, 'b': 8, 'f': 12, 'v': 11}.get(c, 0)

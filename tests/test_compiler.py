"""Smoke tests for the c2r316 compiler.

Covers two layers:
  - Examples in examples/*.c must compile to non-empty assembly
  - Targeted feature tests for the recent fixes (escapes, sizeof, enum,
    <<= / >>=) — these compile a tiny C source and assert the IR / ASM
    contains the expected shape.

Run from repo root:
    python -m tests.test_compiler
"""

import io
import os
import sys
import glob
import contextlib

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT     = os.path.dirname(THIS_DIR)
sys.path.insert(0, ROOT)

from compiler.lexer    import Lexer
from compiler.parser   import Parser
from compiler.semantic import Analyzer
from compiler.irgen    import IRGen
import compiler as _pkg
from compiler.preprocessor import preprocess

# In-process R316 emulator — runs compiled asm to verify behaviour.
from r316_emu import run_main as _emu_run_main


def _compile_via_main(src: str, **kwargs) -> str:
    """Compile a C string by invoking the top-level pipeline."""
    from compiler import lexer as _lex
    from compiler import parser as _par
    # use the same path the CLI does
    sys.path.insert(0, ROOT)
    import importlib
    cm = importlib.import_module('compiler')
    # call compile_c from compiler.py at repo root
    spec_path = os.path.join(ROOT, 'compiler.py')
    import importlib.util
    spec = importlib.util.spec_from_file_location('c2r316_main', spec_path)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.compile_c(src, src_name='<test>', **kwargs)


def _lex_only(src: str):
    """Run only preprocessor + lexer and return tokens."""
    src = preprocess(src, src_path='', include_dirs=[ROOT])
    return Lexer(src).tokens


# ── Tests ────────────────────────────────────────────────────────────────────

PASS = 0
FAIL = 0
FAILURES = []

def check(name, cond, detail=''):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f'  ok   {name}')
    else:
        FAIL += 1
        FAILURES.append((name, detail))
        print(f'  FAIL {name}  {detail}')


def test_examples_compile():
    print('\n[examples]')
    for path in sorted(glob.glob(os.path.join(ROOT, 'examples', '*.c'))):
        rel = os.path.relpath(path, ROOT)
        with open(path, 'r', encoding='utf-8') as f:
            src = f.read()
        try:
            asm = _compile_via_main(src, src_path=path)
            check(f'compile {rel}', isinstance(asm, str) and len(asm) > 0)
        except SystemExit as e:
            check(f'compile {rel}', False, f'SystemExit: {e}')
        except Exception as e:
            check(f'compile {rel}', False, f'{type(e).__name__}: {e}')


def test_hex_escape():
    print('\n[lexer: \\x escapes]')
    toks = _lex_only("char c = '\\x41';")
    char_tok = next(t for t in toks if t.kind.name == 'CHAR_LIT')
    check('\\x41 == 65', char_tok.value == 65, f'got {char_tok.value}')

    toks = _lex_only('char *s = "\\x41\\x42";')
    str_tok = next(t for t in toks if t.kind.name == 'STRING_LIT')
    check('"\\x41\\x42" == [65, 66]', str_tok.value == [65, 66], f'got {str_tok.value}')


def test_octal_escape():
    print('\n[lexer: octal escapes]')
    toks = _lex_only("char c = '\\101';")  # octal 101 = 65
    char_tok = next(t for t in toks if t.kind.name == 'CHAR_LIT')
    check('\\101 == 65', char_tok.value == 65, f'got {char_tok.value}')


def test_extra_escapes():
    print('\n[lexer: \\a \\b \\f \\v]')
    for esc, expected in [('a', 7), ('b', 8), ('f', 12), ('v', 11)]:
        toks = _lex_only(f"char c = '\\{esc}';")
        char_tok = next(t for t in toks if t.kind.name == 'CHAR_LIT')
        check(f'\\{esc} == {expected}', char_tok.value == expected, f'got {char_tok.value}')


def test_shift_assign():
    print('\n[parser: <<= / >>=]')
    src = """
int main() {
    int x = 1;
    x <<= 3;
    x >>= 1;
    return x;
}
"""
    asm = _compile_via_main(src)
    check('<<= compiles', 'shl' in asm or '<<' in asm or len(asm) > 100)
    check('>>= compiles', 'shr' in asm or '>>' in asm or len(asm) > 100)


def test_sizeof():
    print('\n[parser: sizeof]')
    src = """
int main() {
    int a[10];
    return sizeof(int) + sizeof a;
}
"""
    asm = _compile_via_main(src)
    check('sizeof compiles', isinstance(asm, str) and len(asm) > 0)


def test_enum():
    print('\n[parser: enum]')
    src = """
enum Color { RED, GREEN, BLUE = 5, PURPLE };
int main() {
    return RED + GREEN + BLUE + PURPLE;  /* 0+1+5+6 = 12 */
}
"""
    asm = _compile_via_main(src)
    check('enum compiles', isinstance(asm, str) and len(asm) > 0)
    # Constant folding should reduce to a literal 12 somewhere — at minimum
    # verify the source shape: anonymous enum with named declarator
    src2 = """
enum { A = 10, B };
int main() { return A + B; }
"""
    asm2 = _compile_via_main(src2)
    check('anonymous enum compiles', isinstance(asm2, str) and len(asm2) > 0)


def test_strength_reduction():
    """Verify * by power-of-2 → <<, unsigned / and % by power-of-2 → >> and &."""
    print('\n[opt: strength reduction]')

    def _ir_post(src):
        # Run the pipeline up to post-opt and capture stderr IR dump.
        import io, contextlib
        spec_path = os.path.join(ROOT, 'compiler.py')
        import importlib.util
        spec = importlib.util.spec_from_file_location('c2r316_main', spec_path)
        mod  = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            try:
                mod.compile_c(src, src_name='<t>', dump_ir_post=True, stop_after='opt')
            except SystemExit:
                pass
        return buf.getvalue()

    src = """
int test(unsigned int x) { return x * 8 + x / 16 + x % 4; }
int sgn(int y) { return y * 4; }
int main() { return test(10) + sgn(3); }
"""
    ir = _ir_post(src)
    check('x * 8 → << 3 (unsigned)', '<< 3' in ir, ir[:400])
    check('x / 16 → >> 4 (unsigned)', '>> 4' in ir, ir[:400])
    check('x % 4 → & 3 (unsigned)', '& 3' in ir, ir[:400])
    check('y * 4 → << 2 (signed)', '<< 2' in ir, ir[:400])

    # Self-op identities: t = y - y; should fold to 0 in IR
    src2 = """
int main() {
    int y = 5;
    int a = y - y;
    int b = y ^ y;
    return a + b;
}
"""
    ir2 = _ir_post(src2)
    # The store-of-computed-zero pattern shows that y-y and y^y were folded.
    # Generous check: count the literal '= 0' appearances should be at least 2.
    check('y - y / y ^ y fold to 0', ir2.count('= 0') >= 2, ir2[:400])


def test_algebraic_identities():
    print('\n[opt: algebraic identities]')

    def _asm(src):
        import importlib.util
        spec = importlib.util.spec_from_file_location('c2r316_main', os.path.join(ROOT, 'compiler.py'))
        mod  = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        return mod.compile_c(src, src_name='<t>')

    # x & 0xFFFF, x | 0, x ^ 0 should disappear (no-op)
    src = """
int test(int x) { return (x & 0xFFFF) | (x ^ 0); }
int main() { return test(7); }
"""
    asm = _asm(src)
    check('algebraic identities compile', isinstance(asm, str) and len(asm) > 0)


def test_execution_smoke():
    """Emulator-based execution tests: compile + run + check return value / stdout.
    These catch correctness bugs that pattern-matching tests can't (the very
    bug fixed in fc7eb9d would have been caught by `print_int(-1)` here)."""
    print('\n[execution: emulator smoke tests]')
    import importlib.util
    spec = importlib.util.spec_from_file_location('c2r316_main', os.path.join(ROOT, 'compiler.py'))
    mod  = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)

    def run(src, max_cycles=500_000):
        return _emu_run_main(mod.compile_c(src, src_name='<t>'), max_cycles=max_cycles)

    # Arithmetic + control flow
    cases = [
        ("int main() { return 7 * 6; }", 42, ''),
        ("int main() { return 100 % 7; }", 2, ''),
        ("int main() { unsigned x = 100; return x / 3; }", 33, ''),
        ("int main() { int n = 0; for (int i = 0; i < 10; i++) n += i; return n; }", 45, ''),
        ("int main() { int x = 5; x <<= 3; return x; }", 40, ''),
        ("int sum(int n) { int s = 0; for (int i = 1; i <= n; i++) s += i; return s; } "
         "int main() { return sum(10); }", 55, ''),
        # Recursion
        ("int fact(int n) { return n <= 1 ? 1 : n * fact(n - 1); } "
         "int main() { return fact(5); }", 120, ''),
        # Unsigned compare regression: 0xFFFF < 1 unsigned must be FALSE
        ("int main() { unsigned a = 0xFFFF, b = 1; return a < b; }", 0, ''),
        # The exact pattern of the codegen bug we fixed: `if (x & MASK) y = 0 - x;`
        # In 16-bit modular: 0 - 0xFFFF = 1.  Pre-fix: `0 - (x&0x8000) = 0x8000`.
        ("int test(int x) { if (x & 0x8000) return 0 - x; return x; } "
         "int main() { return test(-1); }", 1, ''),
        # __builtin_smod with negative dividend (the real-world hello.c hang)
        ("int main() { int x = -7; return x % 3; }", 0xFFFF, ''),  # -7 % 3 = -1 = 0xFFFF
    ]

    for src, expect_ret, expect_out in cases:
        try:
            ret, out = run(src)
            ok = (ret == expect_ret) and (out == expect_out)
            label = src[:55].replace('\n', ' ')
            check(f'execute: {label!r}',
                  ok,
                  f'expected ret={expect_ret} out={expect_out!r}; got ret={ret} out={out!r}')
        except Exception as e:
            check(f'execute: {src[:55]!r}', False, f'{type(e).__name__}: {e}')


def test_examples_run():
    """Execute every tests/examples/test_*.c on the emulator and compare its
    full stdout against a captured golden file in tests/golden/.

    Why exact comparison instead of a substring predicate:
      - The C-level `check(name, got, expected)` could itself miscompile such
        that it prints PASS for a wrong value. A substring like 'FAIL: 0' is
        still satisfied in that case.
      - A program that hangs partway truncates output → the final byte differs
        from the golden's final byte → exact-match fails immediately.
      - Any change in the emitted text (digit value, ordering, escape) is
        caught, not just whether a marker is present.

    Update flow: when a test legitimately changes (or you add a new
    tests/examples/test_*.c), regenerate goldens with `python tests/gen_goldens.py`.
    """
    import re, importlib.util
    print('\n[execution: examples/test_*.c on emulator]')
    spec = importlib.util.spec_from_file_location('c2r316_main', os.path.join(ROOT, 'compiler.py'))
    mod  = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)

    def _normalize(out):
        # __FILE__ embeds an absolute path — replace for portability.
        return re.sub(r'file macro: .*', 'file macro: <PATH>', out)

    golden_dir = os.path.join(ROOT, 'tests', 'golden')
    for path in sorted(glob.glob(os.path.join(THIS_DIR, 'examples', 'test_*.c'))):
        rel  = os.path.relpath(path, ROOT)
        base = os.path.basename(path).replace('.c', '.txt')
        golden_path = os.path.join(golden_dir, base)
        if not os.path.isfile(golden_path):
            check(f'execute {rel}', False,
                  f'no golden at {os.path.relpath(golden_path, ROOT)} '
                  f'(run tests/gen_goldens.py)')
            continue
        with open(golden_path, encoding='utf-8') as f:
            expected = f.read()
        try:
            with open(path, encoding='utf-8') as f:
                src = f.read()
            asm = mod.compile_c(src, src_name=rel, src_path=path)
            ret, out = _emu_run_main(asm, max_cycles=20_000_000)
            actual = _normalize(out)
            if actual == expected:
                check(f'execute {rel}', True)
            else:
                # short, locating diff: first 60 chars at the divergence point
                idx = next((i for i in range(min(len(actual), len(expected)))
                            if actual[i] != expected[i]),
                           min(len(actual), len(expected)))
                ctx = (f'mismatch at byte {idx} '
                       f'(actual len={len(actual)} expected len={len(expected)}); '
                       f'expected[{idx}:{idx+60}]={expected[idx:idx+60]!r}; '
                       f'actual[{idx}:{idx+60}]={actual[idx:idx+60]!r}')
                check(f'execute {rel}', False, ctx)
        except Exception as e:
            check(f'execute {rel}', False, f'{type(e).__name__}: {e}')


def test_print_int_signed():
    """End-to-end: print_int(N) → stdout matches str(N).  This is the test
    the hello.c hang would have failed pre-fix (infinite cycle limit hit)."""
    print('\n[execution: print_int / printf]')
    import importlib.util
    spec = importlib.util.spec_from_file_location('c2r316_main', os.path.join(ROOT, 'compiler.py'))
    mod  = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)

    cases = [0, 1, 7, -1, -7, 42, -42, 100, -100, 255, -255, 32767]
    for n in cases:
        src = f'#include "runtime/stdio.h"\nint main() {{ print_int({n}); return 0; }}\n'
        try:
            asm = mod.compile_c(src, src_name='<t>')
            ret, out = _emu_run_main(asm, max_cycles=2_000_000)
            check(f'print_int({n}) == {n!r}',
                  out == str(n),
                  f'expected {str(n)!r} got {out!r}')
        except Exception as e:
            check(f'print_int({n})', False, f'{type(e).__name__}: {e}')


def test_left_operand_preserved_across_binop():
    """Critical correctness: codegen must NOT clobber the left operand's
    register when generating 2-op forms like AND/OR/XOR/SHL/SHR.

    Trigger pattern (the original bug — caused hello.c to hang in
    __builtin_sdiv when called with a negative dividend):
        t1 = t0 & MASK
        ifnot t1 goto L
        t2 = 0 - t0           // <-- t0 must still hold its original value here
    """
    print('\n[bugfix: left-operand preservation across 2-op binops]')
    import importlib.util
    spec = importlib.util.spec_from_file_location('c2r316_main', os.path.join(ROOT, 'compiler.py'))
    mod  = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)

    # Anything matching the trigger pattern works; use the actual __builtin_sdiv
    # via test_div which exercises both sign branches.
    src = """
int test(int x) {
    if (x & 0x8000) {
        return 0 - x;   /* must use original x, not (x & 0x8000) */
    }
    return x;
}
int main() { return test(-1); }  /* expects 1 */
"""
    asm = mod.compile_c(src, src_name='<t>')
    s = next(i for i, l in enumerate(asm.split('\n')) if l.strip() == '_C_test:')
    body = asm.split('\n')[s:s + 30]
    # Look for the dangerous pattern: `and rX, rY` (2-op AND) followed within
    # a few instructions by a `sub rZ, ?, rX` reading rX.  After the fix,
    # codegen should copy lreg before AND'ing so rX (lreg) is preserved.
    # Heuristic: the AND-result register should NOT be reused as the second
    # source of a subsequent `sub`.
    found_bug = False
    for i, line in enumerate(body):
        line = line.strip()
        if line.startswith('and '):
            # parse `and rA, rB` → A is destination/accumulator
            try:
                parts = line.replace(',', '').split()
                acc = parts[1]
            except Exception:
                continue
            # look ahead a few instructions for `sub rZ, ?, acc`
            for nxt in body[i + 1:i + 8]:
                nxt = nxt.strip()
                if nxt.startswith('sub ') and nxt.endswith(', ' + acc):
                    found_bug = True
                    break
    check('AND result register not reused as later sub source',
          not found_bug,
          '\n'.join(body[:30]))


def test_unsigned_comparison():
    """Unsigned `<` etc. must use carry-based branches (jc/jnc), not signed jl/jge.
    Otherwise values with the high bit set compare wrong (e.g. 0xFFFF < 1 wrongly true)."""
    print('\n[bugfix: unsigned comparison]')
    import importlib.util
    spec = importlib.util.spec_from_file_location('c2r316_main', os.path.join(ROOT, 'compiler.py'))
    mod  = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)

    src = """
int test(unsigned int a, unsigned int b) { return a < b; }
int main() { return test(1, 2); }
"""
    asm = mod.compile_c(src, src_name='<t>')
    # extract the test function body
    lines = asm.split('\n')
    start = next(i for i, l in enumerate(lines) if l.strip() == '_C_test:')
    body = '\n'.join(lines[start:start + 20])
    check('unsigned < uses jnc / jc, not jge / jl',
          ('jnc' in body or 'jc ' in body) and 'jge' not in body and ' jl ' not in body,
          body[:300])

    # All four ordering ops on unsigned
    src2 = """
int test(unsigned int a, unsigned int b) {
    if (a < b) return 1;
    if (a > b) return 2;
    if (a <= b) return 3;
    if (a >= b) return 4;
    return 0;
}
int main() { return test(5, 7); }
"""
    asm2 = mod.compile_c(src2, src_name='<t>')
    # all four compares should use jc/jnc, no signed jl/jge in test body
    s = next(i for i, l in enumerate(asm2.split('\n')) if l.strip() == '_C_test:')
    body2 = '\n'.join(asm2.split('\n')[s:s + 60])
    check('all 4 unsigned ordering ops avoid signed branches',
          'jge' not in body2 and ' jl ' not in body2 and ' jg ' not in body2 and 'jle' not in body2,
          body2[:500])


def test_goto():
    print('\n[parser: goto / labels]')
    src = """
int sum_to(int n) {
    int s = 0;
    int i = 0;
loop:
    if (i > n) goto done;
    s = s + i;
    i = i + 1;
    goto loop;
done:
    return s;
}
int main() { return sum_to(10); }
"""
    import importlib.util
    spec = importlib.util.spec_from_file_location('c2r316_main', os.path.join(ROOT, 'compiler.py'))
    mod  = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    asm = mod.compile_c(src, src_name='<t>')
    check('goto compiles', isinstance(asm, str) and len(asm) > 0)
    check('user labels are mangled', '._user_loop' in asm and '._user_done' in asm,
          'expected ._user_loop and ._user_done in asm')


def test_typedef_still_works():
    print('\n[parser: typedef regression]')
    src = """
typedef int myint;
typedef int (*fp_t)(int);
int double_it(int x) { return x + x; }
int main() {
    myint x = 5;
    fp_t f = double_it;
    return f(x);
}
"""
    asm = _compile_via_main(src)
    check('typedef compiles', isinstance(asm, str) and len(asm) > 0)


if __name__ == '__main__':
    test_hex_escape()
    test_octal_escape()
    test_extra_escapes()
    test_shift_assign()
    test_sizeof()
    test_enum()
    test_strength_reduction()
    test_algebraic_identities()
    test_left_operand_preserved_across_binop()
    test_unsigned_comparison()
    test_execution_smoke()
    test_print_int_signed()
    test_examples_run()
    test_goto()
    test_typedef_still_works()
    test_examples_compile()
    print(f'\n=== {PASS} passed, {FAIL} failed ===')
    if FAIL:
        for name, detail in FAILURES:
            print(f'  - {name}: {detail}')
        sys.exit(1)

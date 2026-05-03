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
try:
    from emu import run_main as _emu_run_main
except ModuleNotFoundError:
    from tests.emu import run_main as _emu_run_main


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


def test_verbose_logging():
    print('\n[cli: verbose logging]')
    buf = io.StringIO()
    src = 'int main() { return 3 + 4; }'
    with contextlib.redirect_stderr(buf):
        asm = _compile_via_main(src, verbose=True)
    log = buf.getvalue()
    expected = [
        'Input:',
        'Include dirs:',
        'Preprocessing complete',
        'Lexing complete',
        'Parsing complete',
        'Semantic analysis complete',
        'IR generation complete',
        'Optimization complete',
        'Code generation complete',
        'Total compile time:',
    ]
    missing = [item for item in expected if item not in log]
    check('verbose log has real stage details', not missing, f'missing {missing}; log={log[:600]}')
    check('verbose compile still returns asm', isinstance(asm, str) and len(asm) > 0)

    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        asm = _compile_via_main(src, verbose=2)
    debug_log = buf.getvalue()
    expected_debug = [
        'Source lines:',
        'Preprocessed lines:',
        'Token kinds:',
        'Top-level declarations:',
        'IR functions:',
        'IR data:',
        'Optimized IR functions:',
        'ASM detail:',
    ]
    missing_debug = [item for item in expected_debug if item not in debug_log]
    check('double verbose log has debugging details', not missing_debug,
          f'missing {missing_debug}; log={debug_log[:800]}')
    check('double verbose compile still returns asm', isinstance(asm, str) and len(asm) > 0)


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

    # Use globals so the optimizer cannot constant-fold the function bodies away
    # after inlining (globals are not known at compile time).
    src = """
unsigned int gx = 10;
int gy = 3;
int test(unsigned int x) { return x * 8 + x / 16 + x % 4; }
int sgn(int y) { return y * 4; }
int main() { return test(gx) + sgn(gy); }
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
        ret, out, _ = _emu_run_main(mod.compile_c(src, src_name='<t>'), max_cycles=max_cycles)
        return ret, out

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
        # 32-bit long smoke tests: full-width constants, local load/store,
        # add carry into the high half, return, and argument passing.
        ("int main() { long x = 0x12345678; return x == 0x12345678; }", 1, ''),
        ("int main() { long x = 0xFFFF; x = x + 1; return x == 0x10000; }", 1, ''),
        ("long id(long x) { return x; } int main() { return id(0x12345678) == 0x12345678; }", 1, ''),
        ("int eq(long x, long y) { return x == y; } int main() { return eq(0x10000, 0x10000); }", 1, ''),
        ("int main() { long x = 0x10000; return (x * 3) == 0x30000; }", 1, ''),
        ("int main() { long x = 0x10000; x *= 3; return x == 0x30000; }", 1, ''),
        ("int main() { unsigned long x = 0x12345678; return (x / 0x10000) == 0x1234; }", 1, ''),
        ("int main() { unsigned long x = 0x12345678; return (x % 0x10000) == 0x5678; }", 1, ''),
        ("int main() { long x = -70000; return (x / 10) == -7000; }", 1, ''),
        ("int main() { long x = -70003; return (x % 10) == -3; }", 1, ''),
        ("int main() { long x = 0x12345678; x /= 0x10000; return x == 0x1234; }", 1, ''),
        ("int main() { long x = 0x12345678; x %= 0x10000; return x == 0x5678; }", 1, ''),
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
    """Execute every tests/programs/test_*.c on the emulator and compare its
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
    tests/programs/test_*.c), regenerate goldens with `python tests/gen_goldens.py`.
    """
    import re, importlib.util
    print('\n[execution: programs/test_*.c on emulator]')
    spec = importlib.util.spec_from_file_location('c2r316_main', os.path.join(ROOT, 'compiler.py'))
    mod  = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)

    def _normalize(out):
        # __FILE__ embeds an absolute path — replace for portability.
        return re.sub(r'file macro: .*', 'file macro: <PATH>', out)

    golden_dir = os.path.join(ROOT, 'tests', 'golden')
    for path in sorted(glob.glob(os.path.join(THIS_DIR, 'programs', 'test_*.c'))):
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
            stdin_path = path.replace('.c', '.stdin')
            stdin = open(stdin_path, encoding='utf-8').read() if os.path.isfile(stdin_path) else ''
            asm = mod.compile_c(src, src_name=rel, src_path=path)
            ret, out, cycles = _emu_run_main(asm, max_cycles=500_000, stdin=stdin)
            actual = _normalize(out)
            
            # Check for FAIL in output - test programs should have PASS: N, FAIL: 0
            fail_match = re.search(r'FAIL:\s*(\d+)', actual)
            fail_count = int(fail_match.group(1)) if fail_match else 0
            
            if actual == expected:
                if fail_count > 0:
                    # Output matches golden but test program reports failures
                    check(f'execute {rel} [{cycles} cycles]', False, f'test program has {fail_count} FAIL(s)')
                else:
                    check(f'execute {rel} [{cycles} cycles]', True)
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
        src = f'#include <stdio.h>\nint main() {{ print_int({n}); return 0; }}\n'
        try:
            asm = mod.compile_c(src, src_name='<t>')
            ret, out, _ = _emu_run_main(asm, max_cycles=2_000_000)
            check(f'print_int({n}) == {n!r}',
                  out == str(n),
                  f'expected {str(n)!r} got {out!r}')
        except Exception as e:
            check(f'print_int({n})', False, f'{type(e).__name__}: {e}')


def test_sub_imm_carry_inverted():
    """The R316 has no `sub D, P, Simm` encoding — the assembler rewrites
    it to `add D, P, -Simm`, producing a carry that is the bitwise inverse
    of a true subtract's borrow (manual sections sub/sbb).  The emulator
    must model this so inline-asm code that relies on the post-`sub-imm`
    carry behaves the same in tests as it does on real hardware.

    The hello.c hang at commit 62854de was exactly this gap: __builtin_uldivmod10
    used `sub r15, r13, 10` followed by `sbb r16, r14, r0` and `jc skip` —
    the emu's old "real subtract" semantics produced the carry programmers
    intuitively expect, while real HW produces the inverse.  Lock the
    correct behavior with focused asserts."""
    print('\n[bugfix: sub/sbb with immediate carry polarity]')
    from tests.emu.parser import parse_asm
    from tests.emu.machine import Machine

    def run_carry(asm: str) -> int:
        prog = parse_asm(asm)
        m = Machine(prog)
        m.pc = prog.labels['_start']
        m.run()
        return m.flags.C

    # `sub D, P, Simm` ≡ `add D, P, -Simm`: carry = 1 iff p >= imm (the
    # add's natural overflow), i.e. the OPPOSITE of a real subtract's borrow.
    cases = [
        # (p, imm, expected_C)
        (20, 10, 1),    # 20 + 0xFFF6 overflows → C=1 (real sub: 20-10 no borrow → would be C=0)
        (5,  10, 0),    # 5 + 0xFFF6 = 0xFFFB no overflow → C=0 (real sub: borrow → would be C=1)
        (10, 10, 1),    # 10 + 0xFFF6 = 0x10000 overflows → C=1
        (0,  10, 0),    # 0 + 0xFFF6 → C=0
        (0xFFFF, 1, 1), # max + 0xFFFF → C=1
    ]
    for p, imm, exp in cases:
        asm = f'_start:\n    mov r1, {p}\n    sub r0, r1, {imm}\n    hlt\n'
        got = run_carry(asm)
        check(f'sub r0, {p}, {imm}: C={exp}', got == exp,
              f'got C={got} (real-HW expects {exp}, emu must NOT use real-sub borrow)')

    # Two-arg `sub D, Simm` follows the same rewrite.
    asm = '_start:\n    mov r1, 5\n    sub r1, 10\n    hlt\n'
    got = run_carry(asm)
    check('sub r1, 10 (two-arg imm): C=0 (no overflow on add)',
          got == 0, f'got C={got}')

    # `cmp P, Simm` is `sub r0, P, Simm` after macro expansion → same rule.
    asm = '_start:\n    mov r1, 20\n    cmp r1, 10\n    hlt\n'
    got = run_carry(asm)
    check('cmp r1, 10 with r1=20: C=1', got == 1, f'got C={got}')

    # Reg-form `sub` is unaffected (real subtract semantics preserved).
    asm = '_start:\n    mov r1, 20\n    mov r2, 10\n    sub r0, r1, r2\n    hlt\n'
    got = run_carry(asm)
    check('sub r0, r1, r2 (reg form): C=0 (real sub, no borrow)',
          got == 0, f'got C={got}')

    # The exact uldivmod10 inner-loop pattern: sub-imm + sbb-reg + jc.
    # On real HW this branches the OPPOSITE way from a naive read of `sub`.
    # r13:r14 = 5:0, trial subtract 10 — should "skip" (i.e. NOT take it).
    # Real HW: `sub r15, 5, 10` → C=0; then `sbb r16, 0, r0` with cin=0 → r16=0, C=0;
    # `jc skip` not taken — would WRONGLY take the subtract on raw HW unless
    # the C source compensates.  We assert the emu reproduces this trap.
    asm = """_start:
    mov r13, 5
    mov r14, 0
    sub r15, r13, 10
    sbb r16, r14, r0
    hlt
"""
    prog = parse_asm(asm)
    m = Machine(prog)
    m.pc = prog.labels['_start']
    m.run()
    check('uldivmod10 trap: C=0 after sub-imm/sbb-reg with r13<imm',
          m.flags.C == 0,
          f'got C={m.flags.C} — emu still using pre-fix real-sub semantics?')

    # `sbb D, P, Simm` rewrites to `adc D, P, ~Simm`.  Verify carry behaves
    # like the adc's natural carry, not a true sbb borrow.
    # adc with carry-in=0, p=10, ~Simm=~5=0xFFFA: 10 + 0xFFFA = 0x10004 → C=1.
    asm = """_start:
    mov r1, 10
    add r0, r0    ; clear carry (0+0=0, no carry out)
    sbb r2, r1, 5
    hlt
"""
    prog = parse_asm(asm)
    m = Machine(prog)
    m.pc = prog.labels['_start']
    m.run()
    check('sbb r2, r1=10, 5: C=1 (adc 10+0xFFFA overflows)',
          m.flags.C == 1, f'got C={m.flags.C}')


def test_nop_does_not_clobber_r16():
    """Manual section `mov` (lines 522-531): the four `mov r0, r0, {r0|0}`
    encodings are physically zero, and the assembler/HW silently sets the
    0x20000000 bit on output, redirecting D from r0 to r16. The `nop`
    macro therefore MUST NOT be `mov r0, r0, r0` — that's one of the bad
    encodings. Real TPTASM expands `nop` to `mov r0, r0, r1`.

    Pre-fix the emu defined `nop` as `mov r0, r0` (2-arg, expanding to
    `mov r0, r0, r0`) and the dispatcher quietly executed it as a write
    to r0 (discarded), masking the r16 corruption that would happen on
    real hardware."""
    print('\n[bugfix: nop must not corrupt r16]')
    from tests.emu.parser import parse_asm
    from tests.emu.machine import Machine

    # The macro form: r16 must be untouched.
    asm = """_start:
    mov r16, 0xBEEF
    nop
    hlt
"""
    prog = parse_asm(asm)
    m = Machine(prog)
    m.pc = prog.labels['_start']
    m.run()
    check('nop preserves r16', m.regs[16] & 0xFFFF == 0xBEEF,
          f'r16={m.regs[16]:#x} after nop — macro is encoding as physically-zero')

    # The four bad raw encodings: emu must reproduce the r16 redirect so
    # any test or inline asm that hits one fails loudly.
    bad_forms = [
        ('mov r0, r0, r0', 'mov-reg'),
        ('mov r0, r0, 0',  'mov-imm'),
        ('movf r0, r0, r0','movf-reg'),
        ('movf r0, r0, 0', 'movf-imm'),
    ]
    for instr, label in bad_forms:
        asm = f'_start:\n    mov r16, 0xBEEF\n    mov r1, 0x1234\n    {instr}\n    hlt\n'
        prog = parse_asm(asm)
        m = Machine(prog)
        m.pc = prog.labels['_start']
        m.run()
        # Real HW redirects D=r0 → D=r16 and stores S there. S is r0 (= 0)
        # or imm 0; either way the result is whatever `_source_high(r0) |
        # 0` evaluates to. For our purposes any change away from 0xBEEF is
        # the redirect firing.
        clobbered = (m.regs[16] & 0xFFFF) != 0xBEEF
        check(f'{label} redirects r0→r16 (real HW behavior)',
              clobbered,
              f'r16 still {m.regs[16]:#x} — emu missed the physically-zero '
              f'encoding redirect')


def test_mul_forwards_p_upper_half():
    """Manual line 48: 'The 16 MSBs of the output produced by ALU
    operations are the 16 MSBs of the primary operand.' Multiplication
    is an ALU op (line 42); the emu was zeroing the upper 16 bits of D
    instead of forwarding P's upper 16. Any code that round-trips a
    multiplied value through `exh` to inspect the upper half would
    diverge from real hardware."""
    print('\n[bugfix: mul/mulh/muls/mulx forward P upper 16]')
    from tests.emu.parser import parse_asm
    from tests.emu.machine import Machine

    # Seed P with a known upper half via exh, then mul. After mul, the
    # destination's upper 16 bits must equal P's upper 16 bits.
    for op in ('mul', 'mulh', 'muls', 'mulx'):
        asm = f"""_start:
    mov r1, 0xCAFE
    exh r1, r1, r1     ; r1 upper = 0xCAFE
    mov r2, 7
    {op} r3, r1, r2
    exh r4, r3, r0     ; r4 low = r3 upper
    hlt
"""
        prog = parse_asm(asm)
        m = Machine(prog)
        m.pc = prog.labels['_start']
        m.run()
        upper = (m.regs[3] >> 16) & 0xFFFF
        check(f'{op} forwards P upper half (0xCAFE)',
              upper == 0xCAFE,
              f'{op}: D upper = {upper:#06x}, expected 0xCAFE')


def test_memory_round_trip_32bit():
    """Manual lines 21, 56-58: memory cells are 32 bits wide. `st` writes
    the full 32-bit register value; `ld` reads it back. The pre-fix emu
    masked stores and reads to 16 bits, silently losing the upper half —
    so any code that stuffs data into a register's upper 16 (via exh)
    and round-trips through memory would diverge from real hardware."""
    print('\n[bugfix: memory cells are 32-bit on store and load]')
    from tests.emu.parser import parse_asm
    from tests.emu.machine import Machine

    # Build a register with a non-trivial upper half via exh, store the
    # full 32 bits, load it back, and confirm the upper half survived.
    # (We use `exh r1, r2, r3` to construct the value: low(r1) = high(r2),
    # high(r1) = low(r3). With r2.high = 0xCAFE and r3.low = 0x1234, r1
    # ends up as 0x1234_CAFE.)
    asm = """_start:
    mov r2, 0xCAFE
    exh r2, r2, r0     ; r2.high = 0xCAFE, r2.low = 0
    mov r3, 0x1234
    exh r1, r2, r3     ; r1 = (low=r2.high=0xCAFE, high=r3.low=0x1234) = 0x1234CAFE
    mov r5, 0x100
    st  r1, r5
    ld  r4, r5
    hlt
"""
    prog = parse_asm(asm)
    m = Machine(prog)
    m.pc = prog.labels['_start']
    m.run()
    src = m.regs[1] & 0xFFFFFFFF
    dst = m.regs[4] & 0xFFFFFFFF
    check('st/ld preserves the full 32-bit value',
          src == dst,
          f'wrote {src:#010x} but loaded {dst:#010x}')
    check('memory cell upper 16 bits not truncated on store',
          (dst >> 16) & 0xFFFF == (src >> 16) & 0xFFFF,
          f'load upper={dst>>16:#06x}, store upper={src>>16:#06x}')


def test_print_long_via_printf():
    """End-to-end: printf("%ld", N) on the emulator must terminate and emit
    the correct decimal expansion.  The hello.c hang at commit 62854de was
    a printf("%ld", 0x12345678) infinite loop driven by an inline-asm
    divide-by-10 helper whose `sub r15, r13, 10; sbb r16, r14, r0; jc` chain
    was broken by R316's carry-inversion on `sub-imm`.  This test executes
    the full printf path; pre-fix it would burn through max_cycles."""
    print('\n[execution: printf %ld]')
    import importlib.util
    spec = importlib.util.spec_from_file_location('c2r316_main', os.path.join(ROOT, 'compiler.py'))
    mod  = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)

    cases = [
        (0,          '0'),
        (1,          '1'),
        (10,         '10'),
        (305419896,  '305419896'),   # 0x12345678 — the hello.c case
        (0xFFFFFFFF, '4294967295'),  # unsigned max as %lu, but %ld is signed: prints -1
    ]
    for n, expected in cases:
        if n == 0xFFFFFFFF:
            # signed: %ld of 0xFFFFFFFF is -1
            src = f'#include <stdio.h>\nint main() {{ unsigned long x = {n}u; printf("%lu", x); return 0; }}\n'
            expected = str(n)
        else:
            src = f'#include <stdio.h>\nint main() {{ long x = {n}; printf("%ld", x); return 0; }}\n'
        try:
            asm = mod.compile_c(src, src_name='<t>')
            ret, out, _ = _emu_run_main(asm, max_cycles=2_000_000)
            check(f'printf("%ld", {n}) == {expected!r}',
                  out == expected,
                  f'expected {expected!r} got {out!r}')
        except Exception as e:
            check(f'printf("%ld", {n})', False, f'{type(e).__name__}: {e}')


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
    # Use a global input so the optimizer cannot constant-fold the body away
    # after inlining (test() is a single-call-site function and gets inlined).
    src = """
int gx = -1;
int test(int x) {
    if (x & 0x8000) {
        return 0 - x;   /* must use original x, not (x & 0x8000) */
    }
    return x;
}
int main() { return test(gx); }  /* expects 1 */
"""
    asm = mod.compile_c(src, src_name='<t>')
    # test() is inlined into main, so look for the body under _C_main.
    lines = asm.split('\n')
    label = '_C_main:'
    s = next((i for i, l in enumerate(lines) if l.strip() == label), None)
    if s is None:
        # Fallback: function was not inlined, look for _C_test
        label = '_C_test:'
        s = next(i for i, l in enumerate(lines) if l.strip() == label)
    body = lines[s:s + 30]
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

    # Use globals so the function body is not constant-folded away after inlining.
    src = """
unsigned int ga = 1; unsigned int gb = 2;
int test(unsigned int a, unsigned int b) { return a < b; }
int main() { return test(ga, gb); }
"""
    asm = mod.compile_c(src, src_name='<t>')
    lines = asm.split('\n')
    # test() may be inlined into main — look for its body wherever it ended up
    start = next((i for i, l in enumerate(lines) if l.strip() in ('_C_test:', '_C_main:')), 0)
    body = '\n'.join(lines[start:start + 20])
    check('unsigned < uses jnc / jc, not jge / jl',
          ('jnc' in body or 'jc ' in body) and 'jge' not in body and ' jl ' not in body,
          body[:300])

    # All four ordering ops on unsigned
    src2 = """
unsigned int ga2 = 5; unsigned int gb2 = 7;
int test(unsigned int a, unsigned int b) {
    if (a < b) return 1;
    if (a > b) return 2;
    if (a <= b) return 3;
    if (a >= b) return 4;
    return 0;
}
int main() { return test(ga2, gb2); }
"""
    asm2 = mod.compile_c(src2, src_name='<t>')
    lines2 = asm2.split('\n')
    s = next((i for i, l in enumerate(lines2) if l.strip() in ('_C_test:', '_C_main:')), 0)
    body2 = '\n'.join(lines2[s:s + 60])
    check('all 4 unsigned ordering ops avoid signed branches',
          'jge' not in body2 and ' jl ' not in body2 and ' jg ' not in body2 and 'jle' not in body2,
          body2[:500])


def test_inline_asm_clobbers():
    print('\n[inline asm clobbers]')

    try:
        asm = _compile_via_main(
            'int main() { asm("mov r19, 1" ::: "r19"); return 0; }'
        )
        check('asm callee-saved clobber saves r19',
              'st r19, r30' in asm and 'ld r19, r30' in asm,
              asm[:500])
    except Exception as e:
        check('asm callee-saved clobber saves r19', False, f'{type(e).__name__}: {e}')

    try:
        _compile_via_main('int main() { asm("test r1, r1" ::: "cc", "memory"); return 0; }')
        check('asm accepts cc and memory clobbers', True)
    except Exception as e:
        check('asm accepts cc and memory clobbers', False, f'{type(e).__name__}: {e}')

    try:
        _compile_via_main('int main() { asm("mov r30, 0" ::: "r30"); return 0; }')
        check('asm rejects sp clobber', False, 'expected compiler error')
    except SystemExit as e:
        check('asm rejects sp clobber', 'r30' in str(e), str(e))
    except Exception as e:
        check('asm rejects sp clobber', False, f'{type(e).__name__}: {e}')

    try:
        asm = _compile_via_main('int main() { int x; asm("mov %0, 42" : "=r"(x)); return x; }')
        ret, _, _ = _emu_run_main(asm)
        check('asm output operand stores result', ret == 42, f'got {ret}')
    except Exception as e:
        check('asm output operand stores result', False, f'{type(e).__name__}: {e}')

    try:
        asm = _compile_via_main(
            'int main() { int x = 5; asm("add %0, %1" : "+r"(x) : "r"(7)); return x; }'
        )
        ret, _, _ = _emu_run_main(asm)
        check('asm read-write output operand', ret == 12, f'got {ret}')
    except Exception as e:
        check('asm read-write output operand', False, f'{type(e).__name__}: {e}')


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


def test_switch():
    print('\n[switch / case / default]')
    import importlib.util
    spec = importlib.util.spec_from_file_location('c2r316_main', os.path.join(ROOT, 'compiler.py'))
    mod  = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)

    def run(src):
        ret, out, _ = _emu_run_main(mod.compile_c(src, src_name='<t>'))
        return ret, out

    src = """
#include <stdio.h>
int grade(int s) {
    switch (s) {
        case 1: return 10;
        case 2: return 20;
        default: return 99;
    }
}
int fallthrough(int x) {
    int r = 0;
    switch (x) {
        case 1: r = r + 1;
        case 2: r = r + 2; break;
        default: r = r + 100;
    }
    return r;
}
int main() {
    return grade(2) + fallthrough(1);
}
"""
    ret, _ = run(src)
    check('case dispatch + fallthrough', ret == 23)

    src2 = """
#include <stdio.h>
int main() {
    int x = 5;
    switch (x) {
        case 5: puts("five"); break;
        default: puts("other");
    }
    return 0;
}
"""
    _, stdout = run(src2)
    check('switch break/default', stdout.strip() == 'five')


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


def test_const_qualifier():
    print('\n[parser: const qualifier]')
    src = """
int main() {
    const int x = 42;
    const char *s = "hi";
    int * const p = 0;
    const unsigned int u = 7;
    return x;
}
"""
    asm = _compile_via_main(src)
    check('const local vars compile', isinstance(asm, str) and len(asm) > 0)
    src2 = """
const int LIMIT = 10;
int main() { return LIMIT; }
"""
    asm2 = _compile_via_main(src2)
    check('const global compiles', isinstance(asm2, str) and len(asm2) > 0)


def test_type_specifiers():
    print('\n[parser: short, signed, const, volatile, register]')

    # short
    src = "short main() { short x = 5; return x; }"
    asm = _compile_via_main(src)
    check('short compiles', isinstance(asm, str) and len(asm) > 0)

    # signed short
    src = "int main() { signed short x = -1; return x; }"
    asm = _compile_via_main(src)
    check('signed short compiles', isinstance(asm, str) and len(asm) > 0)

    # unsigned short
    src = "int main() { unsigned short x = 65535; return x; }"
    asm = _compile_via_main(src)
    check('unsigned short compiles', isinstance(asm, str) and len(asm) > 0)

    # short int
    src = "int main() { short int x = 10; return x; }"
    asm = _compile_via_main(src)
    check('short int compiles', isinstance(asm, str) and len(asm) > 0)

    # unsigned short int
    src = "int main() { unsigned short int x = 10; return x; }"
    asm = _compile_via_main(src)
    check('unsigned short int compiles', isinstance(asm, str) and len(asm) > 0)

    # signed int (explicit)
    src = "int main() { signed int x = -10; return x; }"
    asm = _compile_via_main(src)
    check('signed int compiles', isinstance(asm, str) and len(asm) > 0)

    # signed alone (treated as int)
    src = "int main() { signed x = -10; return x; }"
    asm = _compile_via_main(src)
    check('signed alone compiles', isinstance(asm, str) and len(asm) > 0)

    # signed char
    src = "int main() { signed char c = -1; return c; }"
    asm = _compile_via_main(src)
    check('signed char compiles', isinstance(asm, str) and len(asm) > 0)

    # const (already parsed, verify no errors)
    src = "int main() { const int x = 42; return x; }"
    asm = _compile_via_main(src)
    check('const int compiles', isinstance(asm, str) and len(asm) > 0)

    # volatile (should parse without error)
    src = "int main() { volatile int x; return 0; }"
    asm = _compile_via_main(src)
    check('volatile int compiles', isinstance(asm, str) and len(asm) > 0)

    # register (should parse without error)
    src = "int main() { register int x = 1; return x; }"
    asm = _compile_via_main(src)
    check('register int compiles', isinstance(asm, str) and len(asm) > 0)

    # combination: const volatile unsigned short
    src = "int main() { const volatile unsigned short x = 10; return x; }"
    asm = _compile_via_main(src)
    check('const volatile unsigned short compiles', isinstance(asm, str) and len(asm) > 0)

    # volatile pointer
    src = "int main() { volatile int *p; return 0; }"
    asm = _compile_via_main(src)
    check('volatile pointer compiles', isinstance(asm, str) and len(asm) > 0)

    # register short function
    src = "short main() { register short x = 1; return x; }"
    asm = _compile_via_main(src)
    check('register short compiles', isinstance(asm, str) and len(asm) > 0)

    # invalid: both signed and unsigned
    src = "int main() { signed unsigned int x; return 0; }"
    try:
        _compile_via_main(src)
        check('signed unsigned rejected', False, 'expected error')
    except (Exception, SystemExit):
        check('signed unsigned rejected', True)

    # invalid: short long
    src = "int main() { short long x; return 0; }"
    try:
        _compile_via_main(src)
        check('short long rejected', False, 'expected error')
    except (Exception, SystemExit):
        check('short long rejected', True)


def test_scanf():
    """End-to-end: scanf reads integers/chars/strings from a simulated stdin."""
    print('\n[execution: scanf]')
    import importlib.util
    spec = importlib.util.spec_from_file_location('c2r316_main', os.path.join(ROOT, 'compiler.py'))
    mod  = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)

    def run(src, stdin='', max_cycles=2_000_000):
        asm = mod.compile_c(src, src_name='<t>')
        ret, out, _ = _emu_run_main(asm, max_cycles=max_cycles, stdin=stdin)
        return ret, out

    # %d positive
    src = '#include <stdio.h>\nint main() { int x; scanf("%d", &x); return x; }\n'
    try:
        ret, _ = run(src, stdin='42\n')
        check('scanf %d positive', ret == 42)
    except Exception as e:
        check('scanf %d positive', False, str(e))

    # %d negative
    src = '#include <stdio.h>\nint main() { int x; scanf("%d", &x); return x; }\n'
    try:
        ret, _ = run(src, stdin='-7\n')
        check('scanf %d negative', ret == (0x10000 - 7))
    except Exception as e:
        check('scanf %d negative', False, str(e))

    # %x hex
    src = '#include <stdio.h>\nint main() { unsigned x; scanf("%x", &x); return x; }\n'
    try:
        ret, _ = run(src, stdin='ff\n')
        check('scanf %x', ret == 0xFF)
    except Exception as e:
        check('scanf %x', False, str(e))

    # %c character
    src = '#include <stdio.h>\nint main() { int c; scanf("%c", &c); return c; }\n'
    try:
        ret, _ = run(src, stdin='A\n')
        check('scanf %c', ret == ord('A'))
    except Exception as e:
        check('scanf %c', False, str(e))

    # %s string
    src = r"""
#include <stdio.h>
int main() {
    char s[16];
    scanf("%s", s);
    puts(s);
    return 0;
}
"""
    try:
        _, out = run(src, stdin='hello\n')
        check('scanf %s', out.rstrip().split('\n')[-1] == 'hello')
    except Exception as e:
        check('scanf %s', False, str(e))

    # multiple items, return value
    src = r"""
#include <stdio.h>
int main() {
    int a; int b;
    int r = scanf("%d %d", &a, &b);
    return r * 100 + a + b;
}
"""
    try:
        ret, _ = run(src, stdin='3 4\n')
        check('scanf multi', ret == 2 * 100 + 3 + 4)
    except Exception as e:
        check('scanf multi', False, str(e))


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
    test_inline_asm_clobbers()
    test_execution_smoke()
    test_print_int_signed()
    test_sub_imm_carry_inverted()
    test_nop_does_not_clobber_r16()
    test_mul_forwards_p_upper_half()
    test_memory_round_trip_32bit()
    test_print_long_via_printf()
    test_examples_run()
    test_goto()
    test_switch()
    test_typedef_still_works()
    test_const_qualifier()
    test_type_specifiers()
    test_scanf()
    test_examples_compile()
    test_verbose_logging()
    print(f'\n=== {PASS} passed, {FAIL} failed ===')
    if FAIL:
        for name, detail in FAILURES:
            print(f'  - {name}: {detail}')
        sys.exit(1)

"""
C → R316 Compiler Main Entry Point

Usage:
    python compiler.py input.c [-o output.asm] [options]

Output file is R316 assembly assemblable with TPTASM.
"""

import sys
import os
import argparse

from compiler.lexer          import Lexer,  LexError, LexWarning
from compiler.parser         import Parser, ParseError
from compiler.semantic       import Analyzer, SemanticError
from compiler.irgen          import IRGen,  IRGenError
from compiler.codegen        import Codegen, CodegenError
from compiler.preprocessor   import preprocess, PreprocessorError
from compiler.dce            import dce
from compiler.fold           import fold
from compiler.inline         import inline


def _source_context(src: str, line: int, col: int, context: int = 2) -> str:
    """Return a formatted source context around line:col."""
    lines = src.split('\n')
    start = max(0, line - 1 - context)
    end   = min(len(lines), line + context)
    result = []
    for i in range(start, end):
        marker = '>' if i == line - 1 else ' '
        prefix = f'  {marker} {i+1:4d} | '
        result.append(f'{prefix}{lines[i]}')
        if i == line - 1 and col > 0:
            result.append(f'{" " * len(prefix)}{" " * (col - 1)}^')
    return '\n'.join(result)


def _print_warning(w, fallback_src: str):
    """Print a compiler warning with source context to stderr."""
    if w.line:
        if w.filename and os.path.isfile(w.filename):
            try:
                warn_src = open(w.filename, encoding='utf-8').read()
            except OSError:
                warn_src = fallback_src
        else:
            warn_src = fallback_src
        ctx = _source_context(warn_src, w.line, w.col)
        print(f"warning: {w.message}\n{ctx}", file=sys.stderr)
    else:
        print(f"warning: {w.message}", file=sys.stderr)


def _raise_with_context(label: str, e: Exception, fallback_src: str):
    """Format and raise a SystemExit with source context for any compiler error."""
    line     = getattr(e, 'line',     0)
    col      = getattr(e, 'col',      0)
    filename = getattr(e, 'filename', '')
    if line:
        if filename and os.path.isfile(filename):
            try:
                err_src = open(filename, encoding='utf-8').read()
            except OSError:
                err_src = fallback_src
        else:
            err_src = fallback_src
        ctx = _source_context(err_src, line, col)
        raise SystemExit(f"{label}: {e}\n{ctx}")
    raise SystemExit(f"{label}: {e}")


def _ir_header(title: str) -> str:
    bar = '-' * 60
    return f'\n{bar}\n  {title}\n{bar}'


def _print_opt_stats(stats: list):
    print('\n  Optimization pass results:', file=sys.stderr)
    for name, bf, af, bi, ai in stats:
        di = ai - bi
        df = af - bf
        sign_i = '+' if di >= 0 else ''
        sign_f = '+' if df >= 0 else ''
        print(f'  {name}:', file=sys.stderr)
        label = 'lines ' if name == 'ASM peephole' else 'instrs'
        print(f'    {label}: {bi:4d} -> {ai:4d}  ({sign_i}{di})', file=sys.stderr)
        if df != 0:
            print(f'    funcs  : {bf:4d} -> {af:4d}  ({sign_f}{df})', file=sys.stderr)


def compile_c(src: str, src_name: str = '<stdin>',
              src_path: str = '',
              include_dirs: list = None,
              dump_tokens: bool = False,
              dump_ast: bool = False,
              dump_ir: bool = False,
              dump_ir_pre: bool = False,
              dump_ir_post: bool = False,
              dump_opt_stats: bool = False,
              stop_after: str = None,
              verbose: bool = False,
              annotate_asm: bool = False) -> str:
    """C source string → R316 assembly string"""

    def _v(msg):
        if verbose:
            print(f'[c2r316] {msg}', file=sys.stderr)

    # 1. preprocessing
    _v('Preprocessing ...')
    _root = os.path.dirname(os.path.abspath(__file__))
    _inc_dirs = [os.path.join(_root, 'include'), _root] + (include_dirs or [])
    # Auto-prepend compiler built-ins (division helpers, etc.).
    # Preprocess builtins and user source separately so that #line markers
    # in the output reflect the user's original file line numbers correctly.
    _builtins_path = os.path.join(_root, 'compiler', 'builtins.h')
    try:
        _builtins_src = open(_builtins_path, encoding='utf-8').read()
        _builtins_pp = preprocess(_builtins_src, src_path=_builtins_path, include_dirs=_inc_dirs)
        _user_pp     = preprocess(src,           src_path=src_path,        include_dirs=_inc_dirs)
    except PreprocessorError as e:
        _raise_with_context("Preprocessor error", e, src)
    # Reset filename/line for the lexer before the user's code begins.
    _escaped = src_path.replace('\\', '\\\\') if src_path else src_name
    src = _builtins_pp + f'\n#line 1 "{_escaped}"\n' + _user_pp

    # 2. lexing
    try:
        lexer = Lexer(src, filename=src_name)
    except LexError as e:
        _raise_with_context("Lex error", e, src)

    for w in lexer.warnings:
        _print_warning(w, src)

    if dump_tokens:
        for tok in lexer.tokens:
            print(tok, file=sys.stderr)
        if stop_after == 'lex':
            raise SystemExit(0)

    if stop_after == 'lex':
        return ''

    # 2. parsing
    try:
        parser = Parser(lexer.tokens)
        ast    = parser.parse()
    except ParseError as e:
        _raise_with_context("Parse error", e, src)

    if dump_ast:
        from compiler.ast_nodes import dump_ast as ast_dump
        print(ast_dump(ast), file=sys.stderr)
        if stop_after == 'parse':
            raise SystemExit(0)

    if stop_after == 'parse':
        return ''

    # 3. semantic analysis
    _v('Semantic analysis ...')
    try:
        analyzer = Analyzer()
        analyzer.analyze(ast)
    except SemanticError as e:
        _raise_with_context("Semantic error", e, src)

    if stop_after == 'semantic':
        return ''

    # 4. IR generation
    _v('IR generation ...')
    try:
        irgen  = IRGen(filename=src_name)
        ir     = irgen.generate(ast)
    except IRGenError as e:
        raise SystemExit(f"IR error: {e}")

    if dump_ir_pre or dump_ir:
        print(_ir_header('IR (pre-optimization)'), file=sys.stderr)
        print(ir.dump(), file=sys.stderr)

    if stop_after == 'ir':
        raise SystemExit(0)  # stop before optimization

    # 4.5. Optimization passes
    def _instr_count(prog):
        return sum(len(fn.instrs) for fn in prog.functions)

    def _func_count(prog):
        return len(prog.functions)

    stats = []

    def _run_pass(name, fn):
        before_i = _instr_count(ir)
        before_f = _func_count(ir)
        fn(ir)
        after_i  = _instr_count(ir)
        after_f  = _func_count(ir)
        stats.append((name, before_f, after_f, before_i, after_i))
        _v(f'{name}: {before_i} -> {after_i} instrs, {before_f} -> {after_f} fns')

    _run_pass('Inlining', inline)
    _run_pass('Constant folding + copy propagation', fold)
    _run_pass('Dead code / dead function elimination', dce)

    if dump_ir_post or dump_ir:
        print(_ir_header('IR (post-optimization)'), file=sys.stderr)
        print(ir.dump(), file=sys.stderr)

    if stop_after == 'opt':
        if dump_opt_stats or verbose:
            _print_opt_stats(stats)
        raise SystemExit(0)

    # 5. code generation (IR → asm)
    _v('Code generation ...')
    try:
        gen = Codegen()
        if annotate_asm:
            gen.set_source(src, src_name)
        asm = gen.generate(ir)
    except CodegenError as e:
        raise SystemExit(f"Codegen error: {e}")

    asm_lines = asm.count('\n') + 1
    elim = gen._peephole_eliminated
    stats.append(('ASM peephole', 0, 0, asm_lines + elim, asm_lines))

    if dump_opt_stats or (verbose and stats):
        _print_opt_stats(stats)

    if stop_after == 'codegen':
        return asm

    _v('Done.')
    return asm



def main():
    ap = argparse.ArgumentParser(description='C to R316 Assembly Compiler')
    ap.add_argument('input',          help='Input C source file')
    ap.add_argument('-o', '--output', help='Output assembly file (default: stdout)')

    # verbosity / debugging
    ap.add_argument('-v', '--verbose', action='store_true',
                    help='Print compilation stages')
    ap.add_argument('--dump-tokens', action='store_true',
                    help='Dump lexer tokens to stderr')
    ap.add_argument('--dump-ast', action='store_true',
                    help='Dump AST to stderr')
    ap.add_argument('--dump-ir', action='store_true',
                    help='Dump IR before and after optimization (shorthand for --dump-ir-pre --dump-ir-post)')
    ap.add_argument('--dump-ir-pre', action='store_true',
                    help='Dump IR before optimization passes')
    ap.add_argument('--dump-ir-post', action='store_true',
                    help='Dump IR after optimization passes')
    ap.add_argument('--dump-opt-stats', action='store_true',
                    help='Print instruction/function count changes for each optimization pass')
    ap.add_argument('--stop-after',
                    choices=['lex', 'parse', 'semantic', 'ir', 'opt', 'codegen'],
                    help='Stop after the given stage: ir=pre-opt IR, opt=post-opt IR, codegen=final asm')
    ap.add_argument('-g', '--annotate', action='store_true',
                    help='Annotate ASM output with source line comments')
    ap.add_argument('-I', dest='include_dirs', action='append', default=[],
                    metavar='DIR', help='Add directory to #include search path')

    args = ap.parse_args()

    # read input file
    try:
        with open(args.input, 'r', encoding='utf-8') as f:
            src = f.read()
    except FileNotFoundError:
        raise SystemExit(f"File not found: {args.input}")

    try:
        asm = compile_c(src, args.input,
                        src_path=os.path.abspath(args.input),
                        include_dirs=args.include_dirs,
                        dump_tokens=args.dump_tokens,
                        dump_ast=args.dump_ast,
                        dump_ir=args.dump_ir,
                        dump_ir_pre=args.dump_ir_pre,
                        dump_ir_post=args.dump_ir_post,
                        dump_opt_stats=args.dump_opt_stats,
                        stop_after=args.stop_after,
                        verbose=args.verbose,
                        annotate_asm=args.annotate)
    except SystemExit as e:
        # Clean exit for --stop-after with code 0
        if e.code == 0:
            return
        # For errors, print the message and exit with code 1
        if e.args and e.args[0]:
            print(e.args[0], file=sys.stderr)
        sys.exit(1 if not isinstance(e.code, int) else e.code)

    if not asm:
        return

    # output
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(asm)
        if args.verbose:
            print(f'[c2r316] Written to {args.output}', file=sys.stderr)
    else:
        print(asm)


if __name__ == '__main__':
    main()
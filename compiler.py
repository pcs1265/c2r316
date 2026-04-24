"""
C → R316 Compiler Main Entry Point

Usage:
    python compiler.py input.c [-o output.asm] [options]

Output file is R316 assembly assemblable with TPTASM.
"""

import sys
import os
import argparse

from compiler.lexer          import Lexer,  LexError
from compiler.parser         import Parser, ParseError
from compiler.semantic       import Analyzer, SemanticError
from compiler.irgen          import IRGen,  IRGenError
from compiler.codegen        import Codegen, CodegenError
from compiler.preprocessor   import preprocess, PreprocessorError
from compiler.dce            import dce
from compiler.fold           import fold


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


def compile_c(src: str, src_name: str = '<stdin>',
              src_path: str = '',
              include_dirs: list = None,
              dump_tokens: bool = False,
              dump_ast: bool = False,
              dump_ir: bool = False,
              stop_after: str = None,
              verbose: bool = False,
              annotate_asm: bool = False) -> str:
    """C source string → R316 assembly string"""

    def _v(msg):
        if verbose:
            print(f'[c2r316] {msg}', file=sys.stderr)

    # 1. preprocessing
    _v('Preprocessing ...')
    # Always search the compiler's own root so #include "runtime/stdlib.h" works
    _root = os.path.dirname(os.path.abspath(__file__))
    _inc_dirs = [_root] + (include_dirs or [])
    try:
        src = preprocess(src, src_path=src_path, include_dirs=_inc_dirs)
    except PreprocessorError as e:
        raise SystemExit(f"Preprocessor error: {e}")

    # 2. lexing
    try:
        lexer = Lexer(src, filename=src_name)
    except LexError as e:
        ctx = _source_context(src, e.line if hasattr(e, 'line') else 0,
                              e.col if hasattr(e, 'col') else 0)
        raise SystemExit(f"Lex error: {e}\n{ctx}")

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
        err_file, err_line, err_col = _parse_error_location(e)
        if err_file and os.path.isfile(err_file):
            try:
                err_src = open(err_file, encoding='utf-8').read()
            except OSError:
                err_src = src
        else:
            err_src = src
        ctx = _source_context(err_src, err_line, err_col)
        raise SystemExit(f"Parse error: {e}\n{ctx}")

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
        err_file, err_line, _col = _parse_error_location(e)
        if err_line:
            if err_file and os.path.isfile(err_file):
                try:
                    err_src = open(err_file, encoding='utf-8').read()
                except OSError:
                    err_src = src
            else:
                err_src = src
            ctx = _source_context(err_src, err_line, 0)
            raise SystemExit(f"Semantic error: {e}\n{ctx}")
        raise SystemExit(f"Semantic error: {e}")

    if stop_after == 'semantic':
        return ''

    # 4. IR generation
    _v('IR generation ...')
    try:
        irgen  = IRGen(filename=src_name)
        ir     = irgen.generate(ast)
    except IRGenError as e:
        raise SystemExit(f"IR error: {e}")

    if dump_ir:
        print(ir.dump(), file=sys.stderr)

    if stop_after == 'ir':
        raise SystemExit(0)

    # 4.5. Optimization: constant folding → DCE
    _v('Constant folding + copy propagation ...')
    fold(ir)
    _v('Dead code elimination ...')
    dce(ir)

    # 5. code generation (IR → asm)
    _v('Code generation ...')
    try:
        gen = Codegen()
        if annotate_asm:
            gen.set_source(src, src_name)
        asm = gen.generate(ir)
    except CodegenError as e:
        raise SystemExit(f"Codegen error: {e}")

    if stop_after == 'codegen':
        return asm

    _v('Done.')
    return asm


def _parse_error_location(e: Exception):
    """Return (filename, line, col) from an error message.

    Handles:
      'file:N:col: ...'   — parse errors (new style)
      'Line N:col: ...'   — parse errors (old style)
      'file:N: ...'       — semantic errors
      'Line N: ...'       — semantic errors (old style)
    """
    import re
    msg = str(e)
    # file:N:col:
    m = re.match(r'^(.+):(\d+):(\d+):', msg)
    if m:
        return m.group(1), int(m.group(2)), int(m.group(3))
    # file:N:
    m = re.match(r'^(.+):(\d+):', msg)
    if m:
        return m.group(1), int(m.group(2)), 0
    # Line N:col:
    m = re.match(r'Line (\d+):(\d+):', msg)
    if m:
        return '', int(m.group(1)), int(m.group(2))
    # Line N:
    m = re.match(r'Line (\d+):', msg)
    if m:
        return '', int(m.group(1)), 0
    return '', 0, 0


def _extract_line(e: Exception) -> int:
    return _parse_error_location(e)[1]


def _extract_col(e: Exception) -> int:
    return _parse_error_location(e)[2]


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
                    help='Dump IR to stderr before codegen')
    ap.add_argument('--stop-after',
                    choices=['lex', 'parse', 'semantic', 'ir', 'codegen'],
                    help='Stop after the given compilation stage')
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
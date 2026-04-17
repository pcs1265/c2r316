"""
C -> R316 Compiler entry point

Usage:
    python compiler/compiler.py input.c [-o output.asm] [-O]

Output file is R316 assembly that can be assembled with TPTASM.
"""

import sys
import os
import argparse

# load modules from the same directory
sys.path.insert(0, os.path.dirname(__file__))

from lexer         import Lexer,  LexError
from parser        import Parser, ParseError
from semantic      import Analyzer, SemanticError
from codegen       import Codegen, CodegenError
from preprocessor  import preprocess, PreprocError


def _compile_pipeline(src: str, label: str, filepath: str = '<string>',
                      library_mode: bool = False,
                      optimize: bool = False) -> str:
    """Shared compilation pipeline. label is the error message prefix."""

    try:
        src = preprocess(src, filepath)
    except PreprocError as e:
        raise SystemExit(f"{label} preprocessor error: {e}")

    try:
        lexer = Lexer(src)
    except LexError as e:
        raise SystemExit(f"{label} lex error: {e}")

    try:
        parser = Parser(lexer.tokens)
        ast    = parser.parse()
    except ParseError as e:
        raise SystemExit(f"{label} parse error: {e}")

    try:
        analyzer = Analyzer()
        analyzer.analyze(ast)
        for i, sl in enumerate(analyzer.string_lits):
            sl.label = f'_str_{i}'
    except SemanticError as e:
        raise SystemExit(f"{label} semantic error: {e}")

    try:
        gen = Codegen(library_mode=library_mode, optimize=optimize)
        return gen.generate(ast)
    except CodegenError as e:
        raise SystemExit(f"{label} codegen error: {e}")


def compile_library(src: str, filepath: str = '<runtime>',
                    optimize: bool = False) -> str:
    """Compile a library (e.g. runtime.c) with no entry point"""
    return _compile_pipeline(src, label='[runtime.c]', filepath=filepath,
                             library_mode=True, optimize=optimize)


def compile_c(src: str, src_name: str = '<stdin>',
              optimize: bool = False) -> str:
    """Compile a C source string to an R316 assembly string"""

    asm = _compile_pipeline(src, label=src_name, filepath=src_name,
                            library_mode=False, optimize=optimize)

    runtime_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', 'runtime'))

    # compile and append runtime.c
    runtime_c_path = os.path.join(runtime_dir, 'runtime.c')
    if os.path.exists(runtime_c_path):
        with open(runtime_c_path, 'r', encoding='utf-8') as f:
            runtime_c_src = f.read()
        asm += '\n\n; -- runtime library (compiled from runtime.c) --\n'
        asm += compile_library(runtime_c_src, filepath=runtime_c_path,
                               optimize=optimize)

    # hardware primitives (must be in assembly)
    # Path is relative to the output .asm file (assumed to be at repo root)
    asm += '\n\n; -- runtime core (asm) --\n'
    asm += '%include "runtime/runtime_core.asm"\n'

    return asm


def main():
    ap = argparse.ArgumentParser(description='C to R316 Assembly Compiler')
    ap.add_argument('input',          help='Input C source file')
    ap.add_argument('-o', '--output', help='Output assembly file (default: stdout)')
    ap.add_argument('-O', '--optimize', action='store_true',
                    help='Enable optimizations (direct conditional branches, peephole)')
    ap.add_argument('-v', '--verbose', action='store_true',
                    help='Print compilation steps')
    args = ap.parse_args()

    # read input file
    try:
        with open(args.input, 'r', encoding='utf-8') as f:
            src = f.read()
    except FileNotFoundError:
        raise SystemExit(f"File not found: {args.input}")

    if args.verbose:
        print(f'[c2r316] Compiling {args.input} ...', file=sys.stderr)

    asm = compile_c(src, args.input, optimize=args.optimize)

    # write output
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(asm)
        if args.verbose:
            print(f'[c2r316] Written to {args.output}', file=sys.stderr)
    else:
        print(asm)


if __name__ == '__main__':
    main()

"""
C → R316 Compiler Main Entry Point

Usage:
    python compiler.py input.c [-o output.asm]

Output file is R316 assembly assemblable with TPTASM.
"""

import sys
import os
import argparse

from compiler.lexer    import Lexer,  LexError
from compiler.parser   import Parser, ParseError
from compiler.semantic import Analyzer, SemanticError
from compiler.irgen    import IRGen,  IRGenError
from compiler.codegen  import Codegen, CodegenError


def compile_c(src: str, src_name: str = '<stdin>',
              dump_ir: bool = False) -> str:
    """C source string → R316 assembly string"""

    # 1. lexing
    try:
        lexer = Lexer(src)
    except LexError as e:
        raise SystemExit(f"Lex error: {e}")

    # 2. parsing
    try:
        parser = Parser(lexer.tokens)
        ast    = parser.parse()
    except ParseError as e:
        raise SystemExit(f"Parse error: {e}")

    # 3. semantic analysis
    try:
        analyzer = Analyzer()
        analyzer.analyze(ast)
    except SemanticError as e:
        raise SystemExit(f"Semantic error: {e}")

    # 4. IR generation
    try:
        irgen  = IRGen(filename=src_name)
        ir     = irgen.generate(ast)
    except IRGenError as e:
        raise SystemExit(f"IR error: {e}")

    if dump_ir:
        print(ir.dump(), file=sys.stderr)

    # 5. code generation (IR → asm)
    try:
        gen = Codegen()
        asm = gen.generate(ir)
    except CodegenError as e:
        raise SystemExit(f"Codegen error: {e}")

    # 5. include runtime library
    asm += '\n\n; -- runtime library --\n'
    asm += '%include "runtime\\runtime.asm"\n'

    return asm


def main():
    ap = argparse.ArgumentParser(description='C to R316 Assembly Compiler')
    ap.add_argument('input',          help='Input C source file')
    ap.add_argument('-o', '--output', help='Output assembly file (default: stdout)')
    ap.add_argument('-v', '--verbose', action='store_true',
                    help='Print compilation steps')
    ap.add_argument('--dump-ir', action='store_true',
                    help='Dump IR to stderr before codegen (for debugging)')
    args = ap.parse_args()

    # read input file
    try:
        with open(args.input, 'r', encoding='utf-8') as f:
            src = f.read()
    except FileNotFoundError:
        raise SystemExit(f"File not found: {args.input}")

    if args.verbose:
        print(f'[c2r316] Compiling {args.input} ...', file=sys.stderr)

    asm = compile_c(src, args.input, dump_ir=args.dump_ir)

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

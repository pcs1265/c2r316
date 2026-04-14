"""
C → R316 컴파일러 메인 진입점

사용법:
    python compiler.py input.c [-o output.asm]

출력 파일은 TPTASM으로 어셈블 가능한 R316 어셈블리입니다.
"""

import sys
import os
import argparse

# 같은 디렉터리에서 모듈 로드
sys.path.insert(0, os.path.dirname(__file__))

from lexer    import Lexer,  LexError
from parser   import Parser, ParseError
from semantic import Analyzer, SemanticError
from codegen  import Codegen, CodegenError


def _compile_pipeline(src: str, label: str, library_mode: bool = False) -> str:
    """공통 컴파일 파이프라인. label은 오류 메시지 접두어."""

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
        gen = Codegen(library_mode=library_mode)
        return gen.generate(ast)
    except CodegenError as e:
        raise SystemExit(f"{label} codegen error: {e}")


def compile_library(src: str) -> str:
    """runtime.c 등 라이브러리용 컴파일 (entry point 없음)"""
    return _compile_pipeline(src, label='[runtime.c]', library_mode=True)


def compile_c(src: str, src_name: str = '<stdin>') -> str:
    """C 소스 문자열 → R316 어셈블리 문자열"""

    asm = _compile_pipeline(src, label=src_name, library_mode=False)

    base = os.path.dirname(__file__)

    # runtime.c 컴파일하여 삽입
    runtime_c_path = os.path.join(base, 'runtime.c')
    if os.path.exists(runtime_c_path):
        with open(runtime_c_path, 'r', encoding='utf-8') as f:
            runtime_c_src = f.read()
        asm += '\n\n; ── runtime library (compiled from runtime.c) ──\n'
        asm += compile_library(runtime_c_src)

    # 하드웨어 프리미티브 (어셈블리 필수)
    core_path = os.path.join(base, 'runtime_core.asm')
    asm += '\n\n; ── runtime core (asm) ──\n'
    asm += f'%include "{core_path}"\n'

    return asm


def main():
    ap = argparse.ArgumentParser(description='C to R316 Assembly Compiler')
    ap.add_argument('input',          help='Input C source file')
    ap.add_argument('-o', '--output', help='Output assembly file (default: stdout)')
    ap.add_argument('-v', '--verbose', action='store_true',
                    help='Print compilation steps')
    args = ap.parse_args()

    # 입력 파일 읽기
    try:
        with open(args.input, 'r', encoding='utf-8') as f:
            src = f.read()
    except FileNotFoundError:
        raise SystemExit(f"File not found: {args.input}")

    if args.verbose:
        print(f'[c2r316] Compiling {args.input} ...', file=sys.stderr)

    asm = compile_c(src, args.input)

    # 출력
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(asm)
        if args.verbose:
            print(f'[c2r316] Written to {args.output}', file=sys.stderr)
    else:
        print(asm)


if __name__ == '__main__':
    main()

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


def compile_c(src: str, src_name: str = '<stdin>') -> str:
    """C 소스 문자열 → R316 어셈블리 문자열"""

    # 1. 렉싱
    try:
        lexer = Lexer(src)
    except LexError as e:
        raise SystemExit(f"Lex error: {e}")

    # 2. 파싱
    try:
        parser = Parser(lexer.tokens)
        ast    = parser.parse()
    except ParseError as e:
        raise SystemExit(f"Parse error: {e}")

    # 3. 시맨틱 분석
    try:
        analyzer = Analyzer()
        analyzer.analyze(ast)
        # 문자열 리터럴 레이블을 AST에 반영
        for i, sl in enumerate(analyzer.string_lits):
            sl.label = f'_str_{i}'
    except SemanticError as e:
        raise SystemExit(f"Semantic error: {e}")

    # 4. 코드 생성
    try:
        gen = Codegen()
        asm = gen.generate(ast)
    except CodegenError as e:
        raise SystemExit(f"Codegen error: {e}")

    # 5. 런타임 라이브러리 포함
    runtime_path = os.path.join(os.path.dirname(__file__), 'runtime.asm')
    asm += '\n\n; ── runtime library ──\n'
    asm += f'%include "{runtime_path}"\n'

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

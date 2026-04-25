"""Regenerate tests/golden/test_*.txt from the current tests/programs/test_*.c.

Run from the repo root:
    python tests/gen_goldens.py

Use this when:
  - You add a new tests/programs/test_*.c file.
  - A legitimate code change updates a test's expected output.
  - The emulator gains support for new instructions and previously
    failing tests now produce known-good output.

DO NOT run this to "make tests pass" after a suspicious change — that
defeats the point. Verify the new output by eye first.
"""

import sys
import os
import glob
import re

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT     = os.path.dirname(THIS_DIR)
sys.path.insert(0, ROOT)
sys.path.insert(0, THIS_DIR)

import importlib.util
spec = importlib.util.spec_from_file_location('c2r316_main', os.path.join(ROOT, 'compiler.py'))
mod  = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
from r316_emu import run_main

GOLDEN_DIR = os.path.join(THIS_DIR, 'golden')
os.makedirs(GOLDEN_DIR, exist_ok=True)


def _normalize(out: str) -> str:
    # __FILE__ embeds an absolute path — replace for portability.
    return re.sub(r'file macro: .*', 'file macro: <PATH>', out)


def main() -> int:
    n = 0
    for path in sorted(glob.glob(os.path.join(THIS_DIR, 'programs', 'test_*.c'))):
        base  = os.path.basename(path).replace('.c', '.txt')
        out_path = os.path.join(GOLDEN_DIR, base)
        with open(path, encoding='utf-8') as f:
            src = f.read()
        stdin_path = path.replace('.c', '.stdin')
        stdin = open(stdin_path, encoding='utf-8').read() if os.path.isfile(stdin_path) else ''
        asm = mod.compile_c(src, src_name=os.path.relpath(path, ROOT), src_path=path)
        ret, out = run_main(asm, max_cycles=20_000_000, stdin=stdin)
        normalized = _normalize(out)
        with open(out_path, 'w', encoding='utf-8', newline='') as f:
            f.write(normalized)
        print(f'  {os.path.relpath(out_path, ROOT)}: {len(normalized):4d} chars (ret={ret})')
        n += 1
    print(f'wrote {n} golden file(s) to {os.path.relpath(GOLDEN_DIR, ROOT)}')
    return 0


if __name__ == '__main__':
    sys.exit(main())

"""Command-line entry point for the R316 emulator."""

from __future__ import annotations

from .machine import Machine
from .parser import parse_asm


def main() -> int:
    import argparse
    import os
    import sys

    ap = argparse.ArgumentParser(
        description='Run a .asm or .c file through the R316 emulator.')
    ap.add_argument('file', help='.asm file (or .c file, compiled first)')
    ap.add_argument('--cycles', '-c', type=int, default=1_000_000,
                    metavar='N', help='max emulated cycles (default: 1 000 000)')
    ap.add_argument('--unlimited-cycles', '-u', action='store_true',
                    help='run without a cycle limit (no timeout guard)')
    ap.add_argument('--freq', '-f', type=float, default=None,
                    metavar='HZ', help='throttle emulation to HZ cycles/s (e.g. 1000000 for 1 MHz)')
    ap.add_argument('--show-retval', '-r', action='store_true',
                    help='print main() return value after program output')
    ap.add_argument('--stdin', '-s', type=str, default=None,
                    metavar='STR', help='provide stdin input as a string')
    ap.add_argument('--stdin-file', type=str, default=None,
                    metavar='FILE', help='read stdin input from a file')
    ap.add_argument('--interactive', '-i', action='store_true',
                    help='enable interactive terminal input (no echo, char-by-char)')
    ap.add_argument('--ram-words', type=int, default=None,
                    help='simulate a machine with this many words of RAM (e.g. 2048)')
    args = ap.parse_args()
    if args.unlimited_cycles:
        args.cycles = None

    # Determine stdin input
    stdin_input = ''
    if args.stdin is not None:
        stdin_input = args.stdin
    elif args.stdin_file is not None:
        with open(args.stdin_file, 'r', encoding='utf-8') as f:
            stdin_input = f.read()

    # Interactive mode is opt-in. Auto-enabling it for any TTY makes scripted
    # runs and compiler tests unexpectedly switch the user's terminal to raw
    # mode when a program polls terminal input.
    interactive = args.interactive

    path = args.file
    if path.endswith('.c'):
        # Import compiler from repo root (works whether run as
        # `python tests/r316_emu.py` or from the repo root).
        _this_dir = os.path.dirname(os.path.abspath(__file__))
        _root = os.path.dirname(os.path.dirname(_this_dir))
        if _root not in sys.path:
            sys.path.insert(0, _root)
        import importlib.util as _ilu
        _spec = _ilu.spec_from_file_location('_compiler_main',
                    os.path.join(_root, 'compiler.py'))
        _mod = _ilu.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        compile_c = _mod.compile_c
        with open(path, encoding='utf-8') as fh:
            src = fh.read()
        asm = compile_c(src, src_name=os.path.basename(path),
                        src_path=os.path.abspath(path))
    else:
        with open(path, encoding='utf-8') as fh:
            asm = fh.read()

    # Create machine with interactive mode if needed
    prog = parse_asm(asm)
    m = Machine(prog, sp_init=0, max_cycles=args.cycles, stdin=stdin_input, freq=args.freq, interactive=interactive, ram_words=args.ram_words)

    try:
        m.run()
    except RuntimeError as e:
        m._restore_terminal()
        print(f"\nerror: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        m._restore_terminal()

    out = m.stdout_str()
    retval = m.regs[1] & 0xFFFF
    cycles = m.cycles

    # In interactive mode, output was already printed in real-time
    if not interactive:
        sys.stdout.write(out)
    print(f'[{cycles} cycles]')
    if args.show_retval:
        print(f'[exit {retval}]')
    return int(retval)

if __name__ == '__main__':
    raise SystemExit(main())

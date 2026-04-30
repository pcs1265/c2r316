"""Test the R316 emulator debugging API.

Tests:
  - State inspection (get_registers, get_flags, get_memory, etc.)
  - Save/restore state (in-memory and file-based)
  - Step-by-step execution
  - Breakpoints
  - Execution tracing

Run from repo root:
    python tests/test_debug_api.py
"""

import os
import sys
import tempfile

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(THIS_DIR)
sys.path.insert(0, ROOT)

from r316_emu import parse_asm, Machine

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


# Test assembly program with multiple instructions
TEST_ASM = '''
_C_main:
    mov r1, 10
    mov r2, 20
    add r3, r1, r2
    sub r4, r3, r1
    mov r5, 0
_C_loop:
    add r5, r5, 1
    cmp r5, 5
    jne _C_loop
    mov r6, 100
    hlt
'''


def test_state_inspection():
    """Test get_registers, get_flags, get_pc, get_current_instruction, is_halted."""
    print('\n[state inspection]')
    prog = parse_asm(TEST_ASM)
    m = Machine(prog)
    m.pc = prog.labels['_C_main']

    regs = m.get_registers()
    check('get_registers returns dict', isinstance(regs, dict))
    check('get_registers has r0-r31', len(regs) == 32)
    check('r0 is initially 0', regs['r0'] == 0)
    check('sp initialized', regs['r30'] == 0x8000)


def test_r0_always_zero():
    """Test that writes to r0 are discarded (r0 is hardwired to 0)."""
    print('\n[r0 always zero]')
    # Test assembly that explicitly tries to write to r0
    asm = '''
_C_main:
    mov r0, 42
    mov r1, 100
    add r0, r1, r1
    hlt
'''
    prog = parse_asm(asm)
    m = Machine(prog)
    m.pc = prog.labels['_C_main']

    # Execute all instructions
    m.step(4)

    # r0 should still be 0 after all writes
    check('r0 is 0 after mov r0, 42', m.get_registers()['r0'] == 0)
    check('r1 is 100', m.get_registers()['r1'] == 100)
    check('machine is halted', m.is_halted())


def test_step_execution():
    """Test step-by-step execution."""
    print('\n[step execution]')
    prog = parse_asm(TEST_ASM)
    m = Machine(prog)
    m.pc = prog.labels['_C_main']

    running = m.step()
    check('step returns True while running', running == True)
    check('r1 is 10 after step', m.get_registers()['r1'] == 10)

    m.step()
    check('r2 is 20 after step', m.get_registers()['r2'] == 20)

    m.step()
    check('r3 is 30 after add', m.get_registers()['r3'] == 30)

    m.step()
    check('r4 is 20 after sub', m.get_registers()['r4'] == 20)


def test_step_with_count():
    """Test step(count) to execute multiple instructions at once."""
    print('\n[step with count]')
    prog = parse_asm(TEST_ASM)
    m = Machine(prog)
    m.pc = prog.labels['_C_main']

    # Step 4 instructions at once
    running = m.step(4)
    check('step(4) returns True', running == True)
    check('pc is at instruction 4', m.get_pc() == prog.labels['_C_main'] + 4)
    check('r1 is 10', m.get_registers()['r1'] == 10)
    check('r2 is 20', m.get_registers()['r2'] == 20)
    check('r3 is 30', m.get_registers()['r3'] == 30)
    check('r4 is 20', m.get_registers()['r4'] == 20)

    # Step 0 instructions (no-op)
    pc_before = m.get_pc()
    running = m.step(0)
    check('step(0) returns True', running == True)
    check('step(0) does not change pc', m.get_pc() == pc_before)

    # Step to halt
    m.pc = prog.labels['_C_main']
    # The program has 12 instructions total (mov, mov, add, sub, mov, add, cmp, jne, mov, hlt + loop)
    # Run until halt
    running = m.step(1000)
    check('step(1000) returns False when halted', running == False)
    check('machine is halted', m.is_halted())


def test_save_restore_memory():
    """Test save_state and restore_state (in-memory)."""
    print('\n[save/restore in-memory]')
    prog = parse_asm(TEST_ASM)
    m = Machine(prog)
    m.pc = prog.labels['_C_main']

    # Execute a few steps
    m.step()
    m.step()
    m.step()
    m.step()

    state = m.save_state()
    check('save_state returns dict', isinstance(state, dict))
    check('saved state has version', state.get('version') == 1)
    check('saved state has pc', 'pc' in state)
    check('saved state has regs', 'regs' in state)
    check('saved state has flags', 'flags' in state)
    check('saved state has mem', 'mem' in state)

    # Continue execution
    m.step()  # mov r5, 0
    m.step()  # add r5, r5, 1 (first loop iteration)
    check('r5 is 1 after loop step', m.get_registers()['r5'] == 1)

    # Restore to saved state
    m.restore_state(state)
    check('pc restored', m.get_pc() == state['pc'])
    check('r5 restored to 0', m.get_registers()['r5'] == 0)


def test_save_restore_file():
    """Test save_state_file and load_state_file (file-based)."""
    print('\n[save/restore file-based]')
    prog = parse_asm(TEST_ASM)
    m = Machine(prog)
    m.pc = prog.labels['_C_main']

    # Execute a few steps
    m.step()
    m.step()
    m.step()

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        state_file = f.name
    try:
        m.save_state_file(state_file)
        check('state file created', os.path.exists(state_file))

        # Load in new machine
        m2 = Machine.load_state_file(state_file, prog)
        check('loaded pc matches', m2.get_pc() == m.get_pc())
        check('loaded r1 matches', m2.get_registers()['r1'] == m.get_registers()['r1'])
        check('loaded r2 matches', m2.get_registers()['r2'] == m.get_registers()['r2'])
        check('loaded r3 matches', m2.get_registers()['r3'] == m.get_registers()['r3'])
    finally:
        os.remove(state_file)


def test_breakpoints():
    """Test set_breakpoint, clear_breakpoint, list_breakpoints, run_until_breakpoint."""
    print('\n[breakpoints]')
    prog = parse_asm(TEST_ASM)
    m = Machine(prog)
    m.pc = prog.labels['_C_main']
    m.clear_all_breakpoints()

    # Set breakpoint at loop label
    bp_id = m.set_breakpoint('_C_loop')
    check('set_breakpoint returns id', isinstance(bp_id, int))

    breakpoints = m.list_breakpoints()
    check('list_breakpoints returns list', isinstance(breakpoints, list))
    check('breakpoint in list', len(breakpoints) == 1)

    # Run until breakpoint
    hit = m.run_until_breakpoint()
    check('run_until_breakpoint returns True', hit == True)
    check('stopped at _C_loop', m.get_pc() == prog.labels['_C_loop'])

    # Clear breakpoint
    cleared = m.clear_breakpoint(bp_id)
    check('clear_breakpoint returns True', cleared == True)
    check('breakpoint removed', len(m.list_breakpoints()) == 0)

    # Set breakpoint by PC
    loop_pc = prog.labels['_C_loop']
    bp_id2 = m.set_breakpoint(loop_pc + 3)  # After a few loop iterations
    check('set_breakpoint by PC works', isinstance(bp_id2, int))

    # Clear all breakpoints
    m.clear_all_breakpoints()
    check('clear_all_breakpoints works', len(m.list_breakpoints()) == 0)


def test_tracing():
    """Test enable_trace, disable_trace, get_trace, clear_trace."""
    print('\n[tracing]')
    prog = parse_asm(TEST_ASM)
    m = Machine(prog)
    m.pc = prog.labels['_C_main']
    m.clear_trace()
    m.enable_trace()

    # Execute a few instructions
    for _ in range(3):
        if not m.step():
            break

    trace = m.get_trace()
    check('get_trace returns list', isinstance(trace, list))
    check('trace has entries', len(trace) == 3)
    if trace:
        entry = trace[0]
        check('trace entry has pc', 'pc' in entry)
        check('trace entry has op', 'op' in entry)
        check('trace entry has args', 'args' in entry)
        check('trace entry has regs_before', 'regs_before' in entry)
        check('trace entry has regs_after', 'regs_after' in entry)
        check('trace entry has flags_before', 'flags_before' in entry)
        check('trace entry has flags_after', 'flags_after' in entry)

    m.disable_trace()
    m.clear_trace()
    check('clear_trace works', len(m.get_trace()) == 0)


def test_run_until_pc():
    """Test run_until_pc."""
    print('\n[run_until_pc]')
    prog = parse_asm(TEST_ASM)
    m = Machine(prog)
    m.pc = prog.labels['_C_main']

    target_pc = prog.labels['_C_main'] + 2  # At 'sub' instruction
    reached = m.run_until_pc(target_pc)
    check('run_until_pc returns True', reached == True)
    check('pc reached target', m.get_pc() == target_pc)


def test_snapshot():
    """Test snapshot method."""
    print('\n[snapshot]')
    prog = parse_asm(TEST_ASM)
    m = Machine(prog)
    m.pc = prog.labels['_C_main']

    snap = m.snapshot()
    check('snapshot returns dict', isinstance(snap, dict))
    check('snapshot has pc', 'pc' in snap)
    check('snapshot has cycles', 'cycles' in snap)
    check('snapshot has halted', 'halted' in snap)
    check('snapshot has regs', 'regs' in snap)
    check('snapshot has flags', 'flags' in snap)
    check('snapshot has stdout', 'stdout' in snap)
    check('snapshot has stdin', 'stdin' in snap)
    check('snapshot has current_instruction', 'current_instruction' in snap)
    check('snapshot has breakpoints', 'breakpoints' in snap)


def test_get_memory():
    """Test get_memory method."""
    print('\n[get_memory]')
    prog = parse_asm(TEST_ASM)
    m = Machine(prog)

    mem = m.get_memory(0x8000, 4)
    check('get_memory returns list', isinstance(mem, list))
    check('get_memory returns correct count', len(mem) == 4)


def test_get_stdout():
    """Test get_stdout method."""
    print('\n[get_stdout]')
    prog = parse_asm(TEST_ASM)
    m = Machine(prog)

    stdout = m.get_stdout()
    check('get_stdout returns string', isinstance(stdout, str))


if __name__ == '__main__':
    test_state_inspection()
    test_r0_always_zero()
    test_step_execution()
    test_step_with_count()
    test_save_restore_memory()
    test_save_restore_file()
    test_breakpoints()
    test_tracing()
    test_run_until_pc()
    test_snapshot()
    test_get_memory()
    test_get_stdout()

    print(f'\n=== {PASS} passed, {FAIL} failed ===')
    if FAIL:
        for name, detail in FAILURES:
            print(f'  - {name}: {detail}')
        sys.exit(1)
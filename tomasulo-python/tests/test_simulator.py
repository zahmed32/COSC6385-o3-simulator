"""Architectural oracle, pipeline invariants, and regressions (stdlib only)."""
import contextlib
import io
from pathlib import Path
import random
import re
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'code'))
from main import simulate
from init import read_instruction


def reference(path):
    instructions, _, ri, rf, memory, _ = read_instruction(path)
    pc, count = 0, 0
    while 0 <= pc < len(instructions):
        count += 1
        if count > 10000:
            raise RuntimeError('Reference loop limit')
        op, *args = instructions[pc].split()
        next_pc = pc + 1
        def value(reg):
            return (ri if reg[0] == 'R' else rf)[int(reg[1:])]
        if op in ('Beq', 'Bne'):
            if (value(args[0]) == value(args[1])) == (op == 'Beq'):
                next_pc += int(args[2])
        elif op in ('Ld', 'Sd'):
            offset, base = re.fullmatch(r'([+-]?\d+)\((R\d+)\)', args[1]).groups()
            address = int(offset) + value(base)
            if address < 0 or address > 252 or address % 4:
                raise ValueError('Bad reference address')
            if op == 'Ld':
                rf[int(args[0][1:])] = memory[address]
            else:
                memory[address] = value(args[0])
        else:
            a = value(args[1])
            b = int(args[2]) if op == 'Addi' else value(args[2])
            result = a - b if op in ('Sub', 'Sub.d') else a * b if op == 'Mult.d' else a + b
            regs = ri if args[0][0] == 'R' else rf
            regs[int(args[0][1:])] = result
        ri[0] = 0
        pc = next_pc
    return ri, rf, memory, count


def run_text(text, width=1):
    text = re.sub(r'(?im)^Issue width\s*=.*$', '', text)
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / 'program.in'
        path.write_text(f'Issue width = {width}\n' + text)
        expected = reference(path)
        with contextlib.redirect_stdout(io.StringIO()):
            actual = simulate(path, max_cycles=10000)
    return actual, expected


class SimulatorTests(unittest.TestCase):
    def check_program(self, text, width):
        actual, expected = run_text(text, width)
        self.assertEqual(actual['registers_int'], expected[0])
        self.assertEqual(actual['registers_fp'], expected[1])
        self.assertEqual(actual['memory'], expected[2])
        self.assertEqual(len(actual['completed']), expected[3])
        writes, commits, issues, port = set(), set(), {}, set()
        for entry in actual['completed']:
            op = actual['instructions'][entry.PC].split()[0]
            self.assertLess(entry.issue[0], entry.exe[0])
            self.assertLess(entry.exe[-1], entry.commit[0])
            issues[entry.issue[0]] = issues.get(entry.issue[0], 0) + 1
            self.assertLessEqual(issues[entry.issue[0]], width)
            self.assertNotIn(entry.commit[-1], commits)
            commits.add(entry.commit[-1])
            if entry.cdb:
                self.assertLess(entry.exe[-1], entry.cdb[0])
                self.assertLess(entry.cdb[0], entry.commit[0])
                self.assertNotIn(entry.cdb[0], writes)
                writes.add(entry.cdb[0])
            if entry.mem:
                self.assertLess(entry.exe[-1], entry.mem[0])
                self.assertLess(entry.mem[-1], entry.cdb[0])
            access = entry.commit if op == 'Sd' else entry.mem
            # One-cycle loads may be forwarded, so only stores and multi-cycle
            # loads uniquely identify occupancy of the physical memory port.
            if access and (op == 'Sd' or access[-1] > access[0]):
                cycles = set(range(access[0], access[-1] + 1))
                self.assertFalse(port & cycles)
                port |= cycles
        return actual

    def test_benchmarks_all_widths(self):
        paths = list((ROOT / 'code').glob('*.in')) + list((ROOT / 'tests/benchmarks').glob('*.in'))
        for path in paths:
            for width in range(1, 5):
                with self.subTest(program=path.name, width=width):
                    result = self.check_program(path.read_text(), width)
                    if path.stem == 'forwarding':
                        loads = [entry for entry in result['completed']
                                 if result['instructions'][entry.PC].startswith('Ld ')]
                        self.assertTrue(all(entry.mem[0] == entry.mem[-1] for entry in loads))

    def test_speculative_load_replay(self):
        result = self.check_program((ROOT / 'tests/benchmarks/load_replay.in').read_text(), 4)
        self.assertGreater(result['load_replays'], 0)
        self.assertEqual(result['registers_fp'][3], 38)

    def test_exact_single_instruction_timing(self):
        result = self.check_program('Addi R1 R0 7', 4)
        entry = result['completed'][0]
        self.assertEqual((entry.issue, entry.exe, entry.cdb, entry.commit),
                         ([1], [2, 2], [3], [4]))

    def test_recovery_delay(self):
        result = self.check_program('Beq R0 R0 1\nAddi R1 R0 99\nAddi R1 R0 7', 4)
        branch, target = result['completed']
        self.assertEqual(target.issue[0], branch.exe[-1] + 2)

    def test_capacity_stalls(self):
        text = 'ROB entries = 1\nInteger adder 1 3 1\n' + '\n'.join(f'Addi R{i} R0 {i}' for i in range(1, 8))
        for width in range(1, 5):
            self.check_program(text, width)

    def test_seeded_random_programs(self):
        for seed in range(30):
            rng = random.Random(seed)
            lines = ['Integer adder 3 2 2', 'FP adder 3 3 2', 'FP multiplier 3 5 2',
                     'Load/store unit 4 2 3 2', 'ROB entries = 9', 'F1=2, F2=3, F3=4']
            for _ in range(45):
                op = rng.choice(['Addi', 'Add', 'Sub', 'Add.d', 'Sub.d', 'Mult.d', 'Ld', 'Sd'])
                d, a, b = (rng.randrange(7) for _ in range(3))
                if op in ('Ld', 'Sd'):
                    lines.append(f'{op} F{d} {rng.randrange(8)*4}(R0)')
                elif op == 'Addi':
                    lines.append(f'{op} R{d} R{a} {b-3}')
                else:
                    kind = 'F' if '.' in op else 'R'
                    lines.append(f'{op} {kind}{d} {kind}{a} {kind}{b}')
            for width in range(1, 5):
                with self.subTest(seed=seed, width=width):
                    self.check_program('\n'.join(lines), width)

    def test_pipelining_and_multiple_units(self):
        for count in (1, 2, 3):
            text = f'FP adder 8 4 {count}\n' + '\n'.join(
                f'Add.d F{i} F0 F0' for i in range(1, 7))
            result = self.check_program(text, 4)
            starts = [e.exe[0] for e in result['completed']]
            self.assertEqual(starts.count(2), count)
            self.assertTrue(all(e.exe[-1] - e.exe[0] + 1 == 4
                                for e in result['completed']))

    def test_branch_alias_and_repeated_recovery(self):
        text = ('Integer adder 6 2 2\nR1=5\n'
                'Addi R2 R2 1\nBeq R0 R0 1\nSd F0 -4(R0)\n'
                'Addi R3 R3 1\nAddi R4 R4 1\nAddi R5 R5 1\n'
                'Addi R6 R6 1\nAddi R7 R7 1\nAddi R1 R1 -1\n'
                'Bne R1 R0 -10\n')
        for width in range(1, 5):
            self.check_program(text, width)

    def test_invalid_input(self):
        for text in ('Issue width = 5', 'ROB entries = 0', 'Add R32 R0 R1',
                     'Add F1 R0 R1', 'Ld F1 nope', 'R0=5', 'Mem[3]=2',
                     'FP adder 2 0 1', 'Addi R1 R0', 'Bogus R1 R2 R3'):
            with self.subTest(text=text), tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / 'bad.in'
                path.write_text(text)
                with self.assertRaises(ValueError):
                    read_instruction(path)

    def test_address_fault_and_cycle_limit(self):
        for text, error in [('Ld F1 -4(R0)', ValueError),
                            ('Beq R0 R0 -1', RuntimeError)]:
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / 'bad.in'
                path.write_text(text)
                with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(error):
                    simulate(path, max_cycles=100)

if __name__ == '__main__':
    unittest.main()

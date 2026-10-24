# Qing 
# 21st May 2017 

from types import SimpleNamespace
import re

# Mutable records with independent defaults for every dynamic instruction.
def rs_entry():
    return SimpleNamespace(busy=0, op=None, tag_1st=None, value_1st=0,
                           valid_1st=0, tag_2nd=None, value_2nd=0,
                           valid_2nd=0, dest_tag=None)

def fu_entry():
    return SimpleNamespace(cycle=0)

def fu_result():
    return SimpleNamespace()

def ld_sd_entry():
    return SimpleNamespace(ready=0, executing=False, in_memory=False,
                           address=None, data=None, reg_tag=None, valid=0)

def ld_sd_exe():
    return SimpleNamespace(busy=0)

def ld_sd_mem():
    return SimpleNamespace(busy=0)

def cdb():
    return SimpleNamespace(valid=0)

def ROB_entry():
    return SimpleNamespace(issue=[], exe=[], mem=[], cdb=[], commit=[],
                           address=None, fault=None)

def PC():
    return SimpleNamespace()

def normalize_instruction(line):
    opcode_names = {
        'ld': 'Ld',
        'sd': 'Sd',
        'add': 'Add',
        'addi': 'Addi',
        'sub': 'Sub',
        'add.d': 'Add.d',
        'sub.d': 'Sub.d',
        'mult.d': 'Mult.d',
        'beq': 'Beq',
        'bne': 'Bne',
    }

    # Treat commas and spaces as operand separators.
    line = line.replace(',', ' ')

    # Normalize memory operands such as 8 ( r1 ) into 8(R1).
    line = re.sub(r'\s*\(\s*', '(', line)
    line = re.sub(r'\s*\)', ')', line)

    parts = line.split()
    opcode = parts[0].lower()

    if opcode not in opcode_names:
        raise ValueError(f"Unknown instruction: {parts[0]}")

    operands = [operand.upper() for operand in parts[1:]]

    op = opcode_names[opcode]
    def register(value, kind):
        return re.fullmatch(kind + r'(?:[0-9]|[12][0-9]|3[01])', value)
    def integer(value):
        return re.fullmatch(r'[+-]?\d+', value)
    valid = False
    if op in ('Ld', 'Sd') and len(operands) == 2:
        match = re.fullmatch(r'([+-]?\d+)\((R\d+)\)', operands[1])
        valid = register(operands[0], 'F') and match and register(match[2], 'R')
    elif len(operands) == 3:
        if op in ('Add', 'Sub'):
            valid = all(register(x, 'R') for x in operands)
        elif op in ('Add.d', 'Sub.d', 'Mult.d'):
            valid = all(register(x, 'F') for x in operands)
        elif op == 'Addi':
            valid = all(register(x, 'R') for x in operands[:2]) and integer(operands[2])
        elif op in ('Beq', 'Bne'):
            valid = all(register(x, 'R') for x in operands[:2]) and integer(operands[2])
    if not valid:
        raise ValueError(f"Invalid operands: {line}")
    return ' '.join([op] + operands)

# function: read instructions
def read_instruction(codefile):
    instructions = []
    issue_width = 1
    reg_int = [0] * 32
    reg_fp = [0.0] * 32
    memory = [0.0] * 256

    config = {
        'rob_entries': 64,
        'int': (4, 1, 1),
        'fp_add': (3, 4, 1),
        'fp_mul': (2, 15, 1),
        'load_store': (5, 1, 5, 1),
    }

    unit_names = {
        'integer adder': 'int',
        'fp adder': 'fp_add',
        'fp multiplier': 'fp_mul',
        'load/store unit': 'load_store',
    }

    with open(codefile) as f:
        for line_number, raw_line in enumerate(f, start=1):
            line = raw_line.split('#', 1)[0].strip()

            if not line:
                continue

            if line.lower().startswith('issue width'):
                key, separator, value = line.partition('=')

                if separator != '=' or key.strip().lower() != 'issue width':
                    raise ValueError(
                        f"Line {line_number}: expected Issue width = number"
                    )

                issue_width = int(value.strip())
                if issue_width not in (1, 2, 3, 4):
                    raise ValueError("" \
                    "Issue width must be between 1 and 4")

            elif line.lower().startswith('rob entries'):
                key, separator, value = line.partition('=')

                if not separator or key.strip().lower() != 'rob entries':
                    raise ValueError("Expected ROB entries = number")

                config['rob_entries'] = int(value.strip())
                if config['rob_entries'] < 1:
                    raise ValueError("ROB entries must be positive")

            elif any(
                line.lower().startswith(name) for name in unit_names
            ):
                for name, config_key in unit_names.items():
                    if line.lower().startswith(name):
                        values = tuple(
                            int(value)
                            for value in line[len(name):].split()
                        )

                        expected = 4 if config_key == 'load_store' else 3
                        if len(values) != expected:
                            raise ValueError(
                                f"{name}: expected {expected} numbers"
                            )

                        if any(value < 1 for value in values):
                            raise ValueError(
                                f"{name}: all values must be positive"
                            )

                        config[config_key] = values
                        break


            elif '=' in line:
                # Examples: R1=12, F20=3.0, Mem[4]=3.0
                for assignment in line.split(','):
                    name, separator, value = assignment.partition('=')
                    if not separator:
                        raise ValueError(
                            f"Line {line_number}: invalid assignment"
                        )

                    name = re.sub(r'\s+', '', name).upper()
                    value = value.strip()

                    register = re.fullmatch(r'([RF])(\d+)', name)
                    location = re.fullmatch(r'MEM\[(\d+)\]', name)

                    if register:
                        kind, number = register.groups()
                        number = int(number)

                        if not 0 <= number < 32:
                            raise ValueError("Register number must be 0–31")

                        if kind == 'R':
                            initial_value = int(value)
                            if number == 0 and initial_value != 0:
                                raise ValueError("R0 must remain zero")
                            reg_int[number] = initial_value
                        else:
                            reg_fp[number] = float(value)

                    elif location:
                        address = int(location.group(1))

                        if not 0 <= address <= 252 or address % 4 != 0:
                            raise ValueError(
                                "Memory address must be word-aligned, "
                                "between 0 and 252"
                            )

                        memory[address] = float(value)

                    else:
                        raise ValueError(
                            f"Line {line_number}: unknown setting {name}"
                        )

            else:
                instructions.append(normalize_instruction(line))

    return instructions, issue_width, reg_int, reg_fp, memory, config
# function: build rs
def build_rs(num):
    rs = []
    for _ in range(num):
        temp = rs_entry()
        temp.busy = 0
        rs.extend([temp])
    return rs


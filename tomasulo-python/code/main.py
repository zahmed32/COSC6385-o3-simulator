# Qing
# 21st May 2017

from copy import deepcopy
from collections import deque
from init import read_instruction, build_rs, ld_sd_exe, ld_sd_mem, cdb as make_cdb, PC
from issue import issue
from exe import exe
from mem import mem
from wb import wb
from commit import commit
def simulate(codefile, max_cycles=100000):
    """Run one independent simulation, print its trace, and return structured results."""
    '''initialize'''
    # read instructions into a list
    instructions, issue_width, reg_int, reg_fp, memory, config = (
        read_instruction(codefile)
    )
    '''initialize register mappings from input values'''
    rat_int = deepcopy(reg_int)
    rat_fp = deepcopy(reg_fp)
    '''intialize reservation stations'''
    size_rs_int_adder = config['int'][0]
    rs_int_adder = build_rs(size_rs_int_adder)
    size_rs_fp_adder = config['fp_add'][0]
    rs_fp_adder = build_rs(size_rs_fp_adder)
    size_rs_fp_multi = config['fp_mul'][0]
    rs_fp_multi = build_rs(size_rs_fp_multi)
    '''initilize function unit'''
    fu_int_adder = [deque() for _ in range(config['int'][-1])]
    time_fu_int_adder = config['int'][1]
    fu_fp_adder = [deque() for _ in range(config['fp_add'][-1])]
    time_fu_fp_adder = config['fp_add'][1]
    fu_fp_multi = [deque() for _ in range(config['fp_mul'][-1])]
    time_fu_fp_multi = config['fp_mul'][1]
    '''initialize load/store queue'''
    ld_sd_queue = deque()
    size_ld_sd_queue = config['load_store'][0]
    address_units = [ld_sd_exe() for _ in range(config['load_store'][-1])]
    time_ld_sd_exe = config['load_store'][1]
    memory_unit = ld_sd_mem()
    time_ld_sd_mem = config['load_store'][2]
    '''initialize ROB'''
    ROB = deque()
    size_ROB = config['rob_entries']
    '''initialize CDB'''
    results_buffer = deque()
    cdb = make_cdb()
    cdb.valid = 0
    """issue first instruction"""
    # instruction pointer
    pc = PC()
    pc.PC = 0
    pc.valid = 1
    pc.branch_history = {}
    pc.btb = [None] * 8
    pc.recovery = None
    pc.resume_cycle = 0
    pc.next_tag = 0
    completed = []
    branch_misses = 0
    load_replays = 0
    cycle = 1

    # print title
    item = ''.ljust(30)
    item += 'ISSUE'.ljust(15)
    item += 'EXE'.ljust(15)
    item += 'MEM'.ljust(15)
    item += 'WB'.ljust(15)
    item += 'COMMIT'.ljust(15)
    print (item)


    def recover_speculation():
        if pc.recovery is None:
            return

        branch_tag, correct_pc = pc.recovery

        # Remove instructions younger than the mispredicted branch.
        while ROB and ROB[-1].ROB_tag != branch_tag:
            ROB.pop()

        live_tags = {entry.ROB_tag for entry in ROB}

        # Clear wrong-path reservation stations.
        for station in (rs_int_adder, rs_fp_adder, rs_fp_multi):
            for entry in station:
                if entry.busy == 1 and entry.dest_tag not in live_tags:
                    entry.busy = 0
                    entry.tag_1st = None
                    entry.tag_2nd = None
                    entry.valid_1st = 0
                    entry.valid_2nd = 0

        # Remove wrong-path execution, result, and memory-queue entries.
        for queue in (*fu_int_adder, *fu_fp_adder, *fu_fp_multi,
                      results_buffer, ld_sd_queue):
            survivors = [
                entry for entry in queue
                if entry.dest_tag in live_tags
            ]
            queue.clear()
            queue.extend(survivors)

        live_ls_tags = {entry.ld_sd_tag for entry in ld_sd_queue}

        for unit in address_units:
            if unit.busy and unit.dest_tag not in live_ls_tags:
                unit.busy = 0
        if memory_unit.busy and memory_unit.entry.dest_tag not in live_tags:
            memory_unit.busy = 0

        if cdb.valid == 1 and cdb.dest_tag not in live_tags:
            cdb.valid = 0

        # Begin with committed register values.
        rat_int[:] = reg_int
        rat_fp[:] = reg_fp

        # Reapply surviving producers in program order.
        for entry in ROB:
            destination = entry.dest_tag

            if not isinstance(destination, str):
                continue

            if destination.startswith('R') and destination[1:].isdigit():
                number = int(destination[1:])
                if number != 0:
                    rat_int[number] = (
                        entry.value if entry.cdb else entry.ROB_tag
                    )

            elif destination.startswith('F') and destination[1:].isdigit():
                number = int(destination[1:])
                rat_fp[number] = (
                    entry.value if entry.cdb else entry.ROB_tag
                )

        rat_int[0] = 0
        pc.PC = correct_pc
        pc.valid = 0
        pc.resume_cycle = cycle + 2
        pc.recovery = None

    # main
    while ROB or pc.recovery is not None or 0 <= pc.PC < len(instructions):
        if cycle > max_cycles:
            raise RuntimeError(f"Simulation exceeded {max_cycles} cycles; check for an infinite loop")
        if pc.valid == 0 and cycle >= pc.resume_cycle:
            pc.valid = 1

        '''ISSUE stage'''
        for _ in range(issue_width):
            if not (0 <= pc.PC < len(instructions)) or pc.valid != 1:
                break

            rob_count_before = len(ROB)

            issue(cycle, pc, instructions, ROB, size_ROB,
                  rs_int_adder,
                  rs_fp_adder,
                  rs_fp_multi,
                  ld_sd_queue, size_ld_sd_queue,
                  rat_int, rat_fp)

            if len(ROB) == rob_count_before:
                break

        '''EXE stage'''
        exe(fu_int_adder, time_fu_int_adder,
            fu_fp_adder, time_fu_fp_adder,
            fu_fp_multi, time_fu_fp_multi, results_buffer,
            rs_int_adder, rs_fp_adder, rs_fp_multi,
            address_units, time_ld_sd_exe, ld_sd_queue,
            cycle, ROB, pc)

        if pc.recovery is not None:
            branch_misses += 1
            recover_speculation()

        '''MEM stage'''
        mem(ld_sd_queue, memory_unit, time_ld_sd_mem, results_buffer,
            memory, ROB, cycle)

        '''CDB stage'''
        wb(cdb, rat_int, rat_fp,
            rs_int_adder, rs_fp_adder, rs_fp_multi,
            ld_sd_queue, ROB, cycle,
            results_buffer)

        '''COMMIT stage'''
        if ROB and ROB[0].fault:
            raise ValueError(f"{instructions[ROB[0].PC]}: {ROB[0].fault}")
        # All older stores have committed by the time a load reaches the head.
        # Validate speculative loads before exposing their values architecturally.
        if (ROB and instructions[ROB[0].PC].startswith('Ld ')
                and ROB[0].cdb and ROB[0].cdb[-1] < cycle
                and ROB[0].value != memory[ROB[0].address]):
            restart_pc = ROB[0].PC
            ROB.clear()
            pc.recovery = (None, restart_pc)
            load_replays += 1
            recover_speculation()
        elif ROB:
            head = ROB[0]
            commit(ROB, reg_int, reg_fp, cycle, instructions)
            if not ROB or ROB[0] is not head:
                completed.append(head)

        # cycle number
        cycle +=1

    print("\nREGISTER VALUES")

    print("Integer registers:")
    for i, value in enumerate(reg_int):
        print(f"R{i} = {value}")

    print("\nFloating-point registers:")
    for i, value in enumerate(reg_fp):
        print(f"F{i} = {value}")

    print("\nNON-ZERO MEMORY VALUES")
    print("Address    Value")
    for address, value in enumerate(memory):
        if value != 0:
            print(f"{address:<10} {value}")


    print(f"\nTotal cycles: {cycle - 1}")
    print(f"Committed instructions: {len(completed)}")
    print(f"Branch mispredictions: {branch_misses}")
    print(f"Load replays: {load_replays}")
    return dict(registers_int=reg_int, registers_fp=reg_fp, memory=memory,
                completed=completed, instructions=instructions, cycles=cycle - 1,
                branch_misses=branch_misses, load_replays=load_replays)


if __name__ == '__main__':
    import argparse
    from pathlib import Path
    parser = argparse.ArgumentParser(description="Tomasulo multi-issue simulator")
    parser.add_argument('input', nargs='?', default=str(Path(__file__).with_name('code.in')))
    parser.add_argument('--max-cycles', type=int, default=100000)
    args = parser.parse_args()
    try:
        simulate(args.input, args.max_cycles)
    except (ValueError, RuntimeError, OSError) as error:
        parser.exit(1, f"Error: {error}\n")

# Qing 
# 24th May 2017

''' 
1. calculate valid instructions
    -- for ALU instructions, write results into fu_results, remove that fu entry  
    -- for LD/SD, write address result immediately back to ld_sd_queue
2. fetch instructions into function unit with spare space
    -- remove ALU instructions from rs
    -- don't remove ld/sd instructions
'''
from init import fu_entry, fu_result

# function: add entry into fu 
def add_entry_into_fu(fu, ins_in_rs):
    fu[-1].cycle = 0
    fu[-1].op = ins_in_rs.op
    fu[-1].value1 = ins_in_rs.value_1st
    fu[-1].value2 = ins_in_rs.value_2nd
    fu[-1].dest_tag = ins_in_rs.dest_tag

# function: find ROB entry by tag
def find_ROB_entry(ROB, tag):
    for index, entry in enumerate(ROB):
        if entry.ROB_tag == tag:
            return index
    raise RuntimeError(f"No live ROB entry for {tag}")


# function: functional units execution 
def fu_exe(fu, fu_results, ROB, time_fu, cycle, PC):
    if len(fu)!=0:
        for element in fu:
            element.cycle += 1
        # write starting cycle 
        if fu[-1].cycle == 1:
            index = find_ROB_entry(ROB, fu[-1].dest_tag)
            ROB[index].exe.append(cycle)
        # finish cycle
        if fu[0].cycle == time_fu:
            index = find_ROB_entry(ROB, fu[0].dest_tag)
            ROB[index].exe.append(cycle)
            # calculation result
            fu_results.append(fu_result())
            fu_results[-1].dest_tag = fu[0].dest_tag
            if (fu[0].op=='Add')|(fu[0].op=='Add.d')|(fu[0].op=='Addi'):
                fu_results[-1].value = fu[0].value1 + fu[0].value2
            elif (fu[0].op=='Sub')|(fu[0].op=='Sub.d'):
                fu_results[-1].value = fu[0].value1 - fu[0].value2
            elif (fu[0].op=='Mult.d'):
                fu_results[-1].value = fu[0].value1 * fu[0].value2
            elif fu[0].op in ('Beq', 'Bne'):
                fu_results.pop()

                index = find_ROB_entry(ROB, fu[0].dest_tag)
                branch_index = ROB[index].PC
                offset = ROB[index].dest_tag

                equal = fu[0].value1 == fu[0].value2
                taken = equal if fu[0].op == 'Beq' else not equal
                actual_next = (
                    branch_index + 1 + offset
                    if taken else branch_index + 1
                )

                ROB[index].mispredicted = (
                    ROB[index].predicted_next != actual_next
                )

                ROB[index].taken = taken
                PC.branch_history[branch_index] = taken
                PC.btb[branch_index & 7] = (branch_index, branch_index + 1 + offset)
                if ROB[index].mispredicted:
                    if PC.recovery is None or index < find_ROB_entry(ROB, PC.recovery[0]):
                        PC.recovery = (ROB[index].ROB_tag, actual_next)
            else:
                pass
            # remove from fu 
            fu.popleft()

# function: ld_sd_execution 
def ld_sd_execution(ld_sd_exe, time_ld_sd_exe, ld_sd_queue, ROB, cycle):
    if ld_sd_exe.busy == 1:
        # write down starting cycle
        if ld_sd_exe.cycle == 0:            
            for element in ld_sd_queue:
                if element.ld_sd_tag == ld_sd_exe.dest_tag:
                    break
            index = find_ROB_entry(ROB, element.dest_tag)
            ROB[index].exe.append(cycle)
            # execute 
        ld_sd_exe.cycle += 1
        # write address back to ld_sd_queue
        if ld_sd_exe.cycle == time_ld_sd_exe:
            address = ld_sd_exe.value1 + ld_sd_exe.value2
            for element in ld_sd_queue:
                if element.ld_sd_tag == ld_sd_exe.dest_tag:
                    element.address = address
                    element.ready = 1
                    element.executing = False
                    break
            # write down finish cycle
            index = find_ROB_entry(ROB, element.dest_tag)
            ROB[index].exe.append(cycle)
            ROB[index].address = address
            if not isinstance(address, int) or not 0 <= address <= 252 or address % 4:
                ROB[index].fault = f"Invalid word address: {address} (expected 0..252, multiple of 4)"
            ld_sd_exe.busy = 0

# function: execution
def exe(fu_int_adder, time_fu_int_adder,
        fu_fp_adder, time_fu_fp_adder,
        fu_fp_multi, time_fu_fp_multi, results_buffer,
        rs_int_adder, rs_fp_adder, rs_fp_multi,
        ld_sd_exe, time_ld_sd_exe, ld_sd_queue,
        cycle, ROB, PC):

    def dispatch(station, unit):
        candidates = [entry for entry in station
                      if entry.busy and entry.valid_1st and entry.valid_2nd
                      and ROB[find_ROB_entry(ROB, entry.dest_tag)].issue[0] < cycle]
        if candidates:
            entry = min(candidates, key=lambda e: find_ROB_entry(ROB, e.dest_tag))
            unit.append(fu_entry())
            add_entry_into_fu(unit, entry)
            entry.busy = 0

    for units, station, pipelined in (
            (fu_int_adder, rs_int_adder, False),
            (fu_fp_adder, rs_fp_adder, True),
            (fu_fp_multi, rs_fp_multi, True)):
        for unit in units:
            if pipelined or not unit:
                dispatch(station, unit)

    for unit in ld_sd_exe:
        if not unit.busy:
            for entry in ld_sd_queue:
                if not entry.valid or entry.ready or entry.executing:
                    continue
                if ROB[find_ROB_entry(ROB, entry.dest_tag)].issue[0] >= cycle:
                    continue
                entry.executing = True
                unit.busy = 1
                unit.cycle = 0
                unit.value1 = entry.reg_value
                unit.value2 = entry.immediate
                unit.dest_tag = entry.ld_sd_tag
                break

    for units, latency in ((fu_int_adder, time_fu_int_adder),
                           (fu_fp_adder, time_fu_fp_adder),
                           (fu_fp_multi, time_fu_fp_multi)):
        for unit in units:
            fu_exe(unit, results_buffer, ROB, latency, cycle, PC)
    for unit in ld_sd_exe:
        ld_sd_execution(unit, time_ld_sd_exe, ld_sd_queue, ROB, cycle)

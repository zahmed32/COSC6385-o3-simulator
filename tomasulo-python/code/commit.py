# Qing 
# 29th may 2017
'''
1. commit ROB_buffer
2. fetch header into ROB_buffer
'''

# function: print ROB entry 
def print_ROB(entry, instructions):
    item = instructions[entry.PC].ljust(30)
    item += str(entry.issue).ljust(15) 
    item += str(entry.exe).ljust(15) 
    item += str(entry.mem).ljust(15)
    item += str(entry.cdb).ljust(15)
    item += str(entry.commit)
    print(item)
# function: modify architectual reg
def modify_arch_reg(entry, reg_int, reg_fp):
    if entry.dest_tag[0] == 'F':
        reg_fp[int(entry.dest_tag[1:])] = entry.value
    elif entry.dest_tag[0] == 'R':
        register = int(entry.dest_tag[1:])
        if register != 0:
            reg_int[register] = entry.value
    else:
        pass

# function: commit
def commit(ROB, reg_int, reg_fp, cycle, instructions):
    if not ROB:
        return

    entry = ROB[0]
    op = instructions[entry.PC].split()[0]

    if op in ('Bne', 'Beq'):
        # Wait until branch execution has finished.
        if len(entry.exe) < 2 or entry.exe[-1] >= cycle:
            return
        entry.commit.append(cycle)

    elif op == 'Sd':
        # Stores retire only after their COMMIT memory interval finishes.
        if not entry.commit or entry.commit[-1] > cycle:
            return

    else:
        # Commit no earlier than the cycle after writeback.
        if not entry.cdb or entry.cdb[-1] >= cycle:
            return
        entry.commit.append(cycle)
        modify_arch_reg(entry, reg_int, reg_fp)

    ROB.popleft()
    print_ROB(entry, instructions)

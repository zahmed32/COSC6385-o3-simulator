"""One non-pipelined memory port plus one-cycle store-to-load forwarding."""
from init import fu_result


def mem(queue, unit, latency, results, memory, ROB, cycle):
    entries = {entry.ROB_tag: entry for entry in ROB}

    def finish_load(entry, value):
        result = fu_result()
        result.dest_tag, result.value = entry.dest_tag, value
        results.append(result)
        queue.remove(entry)

    # A load may forward only from the youngest matching older store.
    # Unknown older store addresses cause speculative memory access instead.
    for entry in list(queue):
        rob = entries[entry.dest_tag]
        if entry.op != 'Ld' or not entry.ready or entry.in_memory or rob.exe[-1] >= cycle or rob.fault:
            continue
        older = list(queue)[:list(queue).index(entry)]
        for store in reversed(older):
            if store.op != 'Sd':
                continue
            if not store.ready:
                break
            if store.address == entry.address:
                if isinstance(store.data, (int, float)):
                    rob.mem = [cycle, cycle]
                    finish_load(entry, store.data)
                break

    # Select a new access before advancing the port: no two memory accesses
    # occupy the same cycle, even when the previous access finishes now.
    if not unit.busy:
        for entry in queue:
            rob = entries[entry.dest_tag]
            if not entry.ready or entry.in_memory or rob.exe[-1] >= cycle or rob.fault:
                continue
            if entry.op == 'Sd':
                if rob is not ROB[0] or not isinstance(entry.data, (int, float)):
                    continue
            else:
                # A known matching store with unavailable data must be waited for.
                blocked = False
                for store in reversed(list(queue)[:list(queue).index(entry)]):
                    if store.op != 'Sd':
                        continue
                    if not store.ready:
                        break
                    if store.address == entry.address:
                        blocked = True
                        break
                if blocked:
                    continue
            unit.busy, unit.cycle, unit.entry = 1, 0, entry
            entry.in_memory = True
            if entry.op == 'Sd':
                rob.commit = [cycle, cycle + latency - 1]
            else:
                rob.mem = [cycle, cycle + latency - 1]
            break

    if unit.busy:
        unit.cycle += 1
        if unit.cycle == latency:
            entry = unit.entry
            unit.busy = 0
            if entry.op == 'Ld':
                finish_load(entry, memory[entry.address])
            else:
                memory[entry.address] = entry.data
                queue.remove(entry)

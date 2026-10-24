Zarif Ahmed
PSID- 2281643

# Tomasulo Simulator

Requires Python 3. No extra packages are needed to run the simulator or tests.
Run the following commands from the tomasulo-python folder.

## Run the simulator


python3 code/main.py


This runs code/code.in and prints instruction stage cycles, final registers,
nonzero memory, and total cycles.

To run another input:


python3 code/main.py tests/benchmarks/branch_loop.in


Set Issue width = 1, 2, 3, or 4 in the input file to select the issue width.
The default is 1 when omitted.

## Run correctness tests


python3 -m unittest discover -s tests -v


## Reproduce the report results


python3 tools/run_benchmarks.py
cat results/summary.csv


This regenerates all 44 benchmark traces at issue widths 1-4 and checks that
all widths produce the same final registers and memory.

Full traces are saved as results folder. For example:


cat results/issue_overlap_w1.txt
cat results/issue_overlap_w4.txt


The issue_overlap benchmark should take 35, 29, 27, and 26 cycles at widths
1, 2, 3, and 4, respectively.


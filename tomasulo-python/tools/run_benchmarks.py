"""Regenerate full traces and the report's measured results (standard library)."""
import contextlib
import csv
import io
from pathlib import Path
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'code'))
from main import simulate


def main():
    output = ROOT / 'results'
    output.mkdir(exist_ok=True)
    paths = sorted((ROOT / 'code').glob('*.in')) + sorted((ROOT / 'tests/benchmarks').glob('*.in'))
    rows = []
    for source in paths:
        baseline = None
        for width in range(1, 5):
            text = re.sub(r'(?im)^Issue width\s*=.*$', '', source.read_text())
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / 'program.in'
                path.write_text(f'Issue width = {width}\n' + text)
                captured = io.StringIO()
                with contextlib.redirect_stdout(captured):
                    result = simulate(path)
            state = (result['registers_int'], result['registers_fp'], result['memory'])
            if baseline is None:
                baseline = state
            if state != baseline:
                raise AssertionError(f'{source.name}: width {width} differs from width 1')
            (output / f'{source.stem}_w{width}.txt').write_text(captured.getvalue())
            rows.append(dict(benchmark=source.stem, issue_width=width,
                             cycles=result['cycles'], committed=len(result['completed']),
                             branch_misses=result['branch_misses'], load_replays=result['load_replays']))
    with (output / 'summary.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    print(f'Wrote {len(rows)} traces and summary.csv to {output}')


if __name__ == '__main__':
    main()

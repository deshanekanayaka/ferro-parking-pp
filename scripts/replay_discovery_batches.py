"""Replay owner-provided exceptions.csv source records through discovery.

No sheet access. Uses a local CSV export and postcodes.io's existing cache/client.
The baseline is the table supplied in the 9 Nov 2026 task, not a reconstructed run.
"""
import argparse
import csv
import json
from pathlib import Path

from ferro_parking.discover import run
from ferro_parking.london import LondonFilter
from ferro_parking.run_paths import new_run_dir, reserve_output
from ferro_parking.sources import generic

BASELINE = {'heathrow': (20, 0, 20), 'lcy': (4, 0, 4), 'nr3': (125, 0, 125), 'havering': (27, 0, 27)}


def replay(sheet_csv, batches, output, london_filter):
    with Path(sheet_csv).open(newline='', encoding='utf-8-sig') as stream:
        sheet_rows = list(csv.DictReader(stream))
    comparison = []
    for name, file in batches.items():
        with Path(file).open(newline='', encoding='utf-8-sig') as stream:
            records = [json.loads(row['source']) for row in csv.DictReader(stream)]
        folder = reserve_output(output / name)
        sources = folder / 'sources.json'
        with sources.open('x') as stream:
            json.dump(records, stream, indent=2)
        summary = run(generic(sources), sheet_rows, folder, london_filter)
        baseline = BASELINE[name]
        comparison.append({'batch': name, 'before': {'listed': baseline[0], 'matched': baseline[1], 'exceptions': baseline[2]},
                           'after': {key: summary[key] for key in ('listed', 'matched', 'exceptions')},
                           'same_listed_count': summary['listed'] == baseline[0],
                           'majority_matched': summary['matched'] > summary['listed'] / 2})
    with (output / 'comparison.json').open('x') as stream:
        json.dump({'baseline_source': 'Owner-provided 9 Nov 2026 task table', 'batches': comparison}, stream, indent=2)
    return comparison


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sheet-csv', required=True)
    parser.add_argument('--runs-dir', required=True, help='Root containing 2026-11-09-heathrow, -lcy, -nr3 and -havering')
    parser.add_argument('--cache', default='data/cache/postcodes')
    parser.add_argument('--out')
    args = parser.parse_args(argv)
    batches = {name: Path(args.runs_dir) / f'2026-11-09-{name}' / 'exceptions.csv' for name in BASELINE}
    missing = [str(path) for path in batches.values() if not path.is_file()]
    if missing:
        parser.error('Missing batch inputs: ' + ', '.join(missing))
    output = reserve_output(args.out) if args.out else new_run_dir('discovery_replay')
    comparison = replay(args.sheet_csv, batches, output, LondonFilter(args.cache))
    for row in comparison:
        print(f"{row['batch']}: before={row['before']} after={row['after']} majority={row['majority_matched']}")
    print(f'Replay outputs: {output}')
    return 0 if all(row['same_listed_count'] and row['majority_matched'] for row in comparison) else 1


if __name__ == '__main__':
    raise SystemExit(main())

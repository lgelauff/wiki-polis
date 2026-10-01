"""polis_stats — basic statistics and charts from a Polis conversation export.

    python -m tools.polis_stats EXPORT [-o OUT] [--vote-sign polis-export|raw]
                                [--min-votes 10] [--majority 0.70] [--split 0.35] [--max-pass 0.50] [--allow-errors]

EXPORT is a folder or a .zip with Polis's CSV export (summary.csv, comments.csv, votes.csv,
participants-votes.csv). Writes report.html, stats.json, statements.csv, issues.csv and charts/*.svg to OUT.
Exit codes: 0 written; 1 the export failed a cross-check (report written
only with --allow-errors); 2 the export could not be read.
"""

from __future__ import annotations

import argparse
import sys

from .export import ExportError, read_export
from .report import write
from .stats import Thresholds, compute


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog='polis_stats', description=__doc__.split('\n\n')[0])
    p.add_argument('export')
    p.add_argument('-o', '--out', default='polis-stats')
    p.add_argument('--vote-sign', choices=('polis-export', 'raw'), default='polis-export',
                   help="'polis-export' (agree=+1, Polis's CSV export) or 'raw' (agree=-1, Polis's database and API)")
    p.add_argument('--min-votes', type=int, default=Thresholds.min_votes)
    p.add_argument('--majority', type=float, default=Thresholds.majority_share)
    p.add_argument('--split', type=float, default=Thresholds.split_min_share)
    p.add_argument('--max-pass', type=float, default=Thresholds.max_pass_share)
    p.add_argument('--allow-errors', action='store_true', help='write the report even if a cross-check failed')
    a = p.parse_args(argv)
    try:
        export = read_export(a.export, vote_sign=a.vote_sign)
    except (ExportError, OSError, ValueError) as e:
        print(f'polis_stats: cannot read export: {e}', file=sys.stderr)
        return 2
    for i in export.issues:
        print(f'{i.level:7} {i.code} ({i.count}): {i.message}', file=sys.stderr)
    errors = [i for i in export.issues if i.level == 'error']
    if errors and not a.allow_errors:
        print(f'polis_stats: {len(errors)} cross-check error(s); nothing written (use --allow-errors to write anyway)', file=sys.stderr)
        return 1
    report = compute(export, Thresholds(a.min_votes, a.majority, a.split, a.max_pass))
    path = write(export, report, a.out)
    print(path)
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())

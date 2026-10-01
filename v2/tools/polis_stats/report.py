"""Write the results: stats.json and the CSV tables (statements, issues)."""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path

from .export import Export
from .stats import Report, wilson


def write(export: Export, report: Report, out: str | Path) -> Path:
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)

    with open(out / 'statements.csv', 'w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh)
        w.writerow(['statement', 'moderated', 'seed', 'votes', 'agree', 'disagree', 'pass',
                    'agree_share', 'disagree_share', 'pass_share', 'agree_of_decided',
                    'agree_of_decided_ci_low', 'agree_of_decided_ci_high', 'label', 'text'])
        for s in report.statements:
            ci = wilson(s.agree, s.decided)
            w.writerow([s.id, s.moderated, '' if s.is_seed is None else int(s.is_seed), s.votes, s.agree,
                        s.disagree, s.passes,
                        *(f'{x:.4f}' if x is not None else '' for x in (s.share(s.agree), s.share(s.disagree), s.share(s.passes), s.agree_of_decided())),
                        *((f'{x:.4f}' for x in ci) if ci else ('', '')),
                        report.label(s.id), _cell(s.text)])

    with open(out / 'issues.csv', 'w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh)
        w.writerow(['level', 'code', 'count', 'message'])
        for i in export.issues:
            w.writerow([i.level, i.code, i.count, i.message])

    data = {
        'source': export.source,
        'generated': datetime.now().astimezone().isoformat(timespec='seconds'),
        'summary': {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in report.summary.items()},
        'thresholds': vars(report.thresholds),
        'labels': {'majority_agree': report.majority_agree, 'majority_disagree': report.majority_disagree,
                   'split': report.split, 'mostly_pass': report.mostly_pass, 'too_few_votes': report.too_few_votes},
        'labels_note': 'Overall vote per statement. Not Polis group-informed consensus or representativeness.',
        'issues': [vars(i) for i in export.issues],
    }
    (out / 'stats.json').write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding='utf-8')
    return out / 'stats.json'


def _cell(text: str) -> str:
    """Neutralise spreadsheet formulas: a cell starting with = + - @ (or tab/CR) gets a leading quote."""
    return "'" + text if text[:1] in ('=', '+', '-', '@', '\t', '\r') else text

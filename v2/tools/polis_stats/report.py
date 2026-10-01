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
                        _label(report, s.id), s.text])

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
        'consensus_agree': report.consensus_agree,
        'consensus_disagree': report.consensus_disagree,
        'divisive': report.divisive,
        'too_few_votes': report.too_few_votes,
        'issues': [vars(i) for i in export.issues],
    }
    (out / 'stats.json').write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding='utf-8')
    return out / 'stats.json'


def _label(report: Report, sid: int) -> str:
    if sid in report.consensus_agree:
        return 'consensus-agree'
    if sid in report.consensus_disagree:
        return 'consensus-disagree'
    if sid in report.divisive:
        return 'divisive'
    if sid in report.too_few_votes:
        return 'too-few-votes'
    return ''

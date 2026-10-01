"""Write the results: report.html (charts + tables), stats.json, CSV tables and the charts as SVG."""

from __future__ import annotations

import csv
import json
from datetime import datetime
from html import escape
from pathlib import Path

from . import charts
from .export import Export
from .stats import Report, wilson


def _pct(n: int, d: int) -> str:
    return f'{100 * n / d:.0f}%' if d else '—'


def write(export: Export, report: Report, out: str | Path) -> Path:
    out = Path(out)
    (out / 'charts').mkdir(parents=True, exist_ok=True)
    svgs = {
        'statements.svg': charts.statement_bars(report.opinions(),
                                                min_votes=report.thresholds.min_votes),
        'votes-per-participant.svg': charts.votes_per_participant(report.votes_per_participant),
        'votes-per-day.svg': charts.votes_per_day(report.votes_per_day),
    }
    for name, svg in svgs.items():
        (out / 'charts' / name).write_text(svg, encoding='utf-8')

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
    (out / 'report.html').write_text(_html(export, report, svgs, data), encoding='utf-8')
    return out / 'report.html'


def _cell(text: str) -> str:
    """Neutralise spreadsheet formulas: a cell starting with = + - @ (or tab/CR) gets a leading quote."""
    return "'" + text if text[:1] in ('=', '+', '-', '@', '\t', '\r') else text


def _html(export: Export, report: Report, svgs: dict[str, str], data: dict) -> str:
    s, t = report.summary, report.thresholds
    by_id = {x.id: x for x in report.statements}
    tiles = [
        ('Participants who voted', s['participants_voting']),
        ('Statements (accepted / unmoderated / rejected)',
         f"{s['statements_accepted']} / {s['statements_unmoderated']} / {s['statements_rejected']}"),
        ('Current votes (all statements)', s['votes_current']),
        ('Opinion votes: agree · pass · disagree', f"{_pct(s['agree'], s['opinion_votes'])} · {_pct(s['pass'], s['opinion_votes'])} · {_pct(s['disagree'], s['opinion_votes'])}"),
        ('Median votes per participant', s['votes_per_participant_median'] if s['votes_per_participant_median'] is not None else '—'),
    ]
    issue_rows = ''.join(
        f'<tr><td>{escape(i.level)}</td><td><code>{escape(i.code)}</code></td><td class="n">{i.count}</td><td>{escape(i.message)}</td></tr>'
        for i in export.issues) or '<tr><td colspan="4">No issues: every cross-check passed.</td></tr>'

    def stmt_list(ids: list[int]) -> str:
        if not ids:
            return '<p class="muted">None.</p>'
        return '<ul>' + ''.join(
            f'<li><b>#{i}</b> {escape(by_id[i].text)} <span class="muted">— {by_id[i].agree} agree, '
            f'{by_id[i].disagree} disagree, {by_id[i].passes} pass</span></li>' for i in ids) + '</ul>'

    table = ''.join(
        f'<tr><td class="n">{x.id}</td><td class="txt">{escape(x.text)}</td><td>{ {1: "accepted", 0: "unmoderated", -1: "rejected"}.get(x.moderated, x.moderated)}</td>'
        f'<td class="n">{x.votes}</td><td class="n">{x.agree}</td><td class="n">{x.passes}</td><td class="n">{x.disagree}</td>'
        f'<td class="n">{_pct(x.agree, x.votes)}</td><td class="n">{_pct(x.agree, x.decided)}</td>'
        f'<td class="lbl">{escape(report.label(x.id))}</td></tr>'
        for x in report.statements)

    title = s['title'] or 'Polis export'
    period = ''
    if s['first_vote'] and s['last_vote']:
        period = f"{s['first_vote']:%Y-%m-%d} to {s['last_vote']:%Y-%m-%d} (UTC)"
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(title)} — statistics</title>
<style>
:root{{--bg:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;--line:#e1e0d9}}
@media (prefers-color-scheme:dark){{:root{{--bg:#0d0d0d;--surface:#1a1a19;--ink:#fff;--ink2:#c3c2b7;--line:#2c2c2a}}}}
body{{background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif;margin:0 auto;max-width:1000px;padding:24px 16px}}
h1{{font-size:24px;margin:0 0 4px}}h2{{font-size:18px;margin:32px 0 8px}}
.muted{{color:var(--muted)}}.tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin:16px 0}}
.tile{{background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:12px}}
.tile b{{display:block;font-size:22px}}.tile span{{color:var(--ink2);font-size:13px}}
table{{border-collapse:collapse;width:100%;background:var(--surface);font-size:13px}}
th,td{{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}}
td.n{{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}}td.txt{{min-width:260px}}.wide{{width:min(calc(100vw - 32px),1400px);position:relative;left:50%;transform:translateX(-50%)}}td.lbl{{white-space:nowrap}}.scroll{{overflow-x:auto}}
figure{{margin:16px 0;overflow-x:auto}}svg{{max-width:100%;height:auto}}code{{font-size:12px}}
</style></head><body>
<h1>{escape(title)}</h1>
<p class="muted">{escape(s['url'])} {escape(period)} · source: {escape(export.source)} · vote sign: {escape(s['vote_sign'])} · generated {escape(data['generated'])}</p>
<div class="tiles">{''.join(f'<div class="tile"><b>{escape(str(v))}</b><span>{escape(k)}</span></div>' for k, v in tiles)}</div>
<h2>Checks</h2>
<p class="muted">The export is cross-checked before anything is counted: current votes are the latest vote per participant and statement in votes.csv, compared with participants-votes.csv cell by cell and with the agree/disagree counts in comments.csv. Errors mean the numbers below should not be used until they are explained.</p>
<table><tr><th>Level</th><th>Check</th><th>Count</th><th>Meaning</th></tr>{issue_rows}</table>
<h2>Votes per statement</h2>
<p class="muted">Rejected statements are left out. Bars are sorted by the agree share of all votes, with statements below {t.min_votes} agree + disagree votes last; hover a segment for counts and text. Every number is in the table below.</p>
<figure>{svgs['statements.svg']}</figure>
<h2>Where people agree, disagree, or split</h2>
<p class="muted">The overall vote on each statement, among statements with at least {t.min_votes} agree + disagree votes. Majority: agree (or disagree) at least {t.majority_share:.0%} of agree + disagree. Split: both sides at least {t.split_min_share:.0%}. Mostly pass: more than {t.max_pass_share:.0%} of all votes were passes. These are not Polis's group-informed consensus or representativeness, which compare opinion groups. {len(report.too_few_votes)} statement(s) had too few votes to label.</p>
<h3>Majority agrees</h3>{stmt_list(report.majority_agree)}
<h3>Majority disagrees</h3>{stmt_list(report.majority_disagree)}
<h3>Split</h3>{stmt_list(report.split)}
<h3>Mostly passed</h3>{stmt_list(report.mostly_pass)}
<h2>Participation</h2>
<figure>{svgs['votes-per-participant.svg']}</figure>
<figure>{svgs['votes-per-day.svg']}</figure>
<h2>All statements</h2>
<p class="muted">Every statement, rejected ones included. Agree %: share of all votes. Agree of decided: share of agree + disagree (passes left out). Labels use the thresholds above; rejected statements get no label.</p>
<div class="scroll wide"><table><tr><th>#</th><th>Statement</th><th>Moderation</th><th>Votes</th><th>Agree</th><th>Pass</th><th>Disagree</th><th>Agree %</th><th>Agree of decided</th><th>Label</th></tr>{table}</table></div>
<p class="muted">Also written next to this file: stats.json, statements.csv (with 95% Wilson intervals), issues.csv, charts/*.svg.</p>
</body></html>"""


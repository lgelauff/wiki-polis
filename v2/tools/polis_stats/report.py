"""Write the results: report.html (charts + tables), stats.json, CSV tables and the charts as SVG."""

from __future__ import annotations

import csv
import json
from datetime import datetime
from html import escape
from pathlib import Path

from . import charts, groups as groupviz
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
    if report.groups:
        svgs['groups-heatmap.svg'] = groupviz.heatmap(report.statements, report.groups)
        svgs['participant-map.svg'] = groupviz.participant_map(
            groupviz.project(export), export.groups, list(report.groups), export.group_source)
    for name, svg in svgs.items():
        (out / 'charts' / name).write_text(svg, encoding='utf-8')

    with open(out / 'statements.csv', 'w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh)
        w.writerow(['statement', 'moderated', 'seed', 'meta', 'votes', 'agree', 'disagree', 'pass',
                    'agree_share', 'disagree_share', 'pass_share', 'agree_of_decided',
                    'agree_of_decided_ci_low', 'agree_of_decided_ci_high', 'label',
                    *(f'group_{g}_{k}' for g in report.groups for k in ('agree', 'disagree', 'pass', 'agree_of_decided')),
                    *(['group_spread'] if report.groups else []), 'text'])
        for s in report.statements:
            ci = wilson(s.agree, s.decided)
            gcols = []
            for d in report.groups.values():
                c = d['statements'].get(s.id) or {'agree': 0, 'disagree': 0, 'pass': 0}
                dec = c['agree'] + c['disagree']
                gcols += [c['agree'], c['disagree'], c['pass'], f"{c['agree'] / dec:.4f}" if dec else '']
            if report.groups:
                sp = groupviz.spread(report.groups, s.id, 5)
                gcols.append(f'{sp:.4f}' if sp is not None else '')
            w.writerow([s.id, s.moderated, '' if s.is_seed is None else int(s.is_seed), int(s.is_meta), s.votes, s.agree,
                        s.disagree, s.passes,
                        *(f'{x:.4f}' if x is not None else '' for x in (s.share(s.agree), s.share(s.disagree), s.share(s.passes), s.agree_of_decided())),
                        *((f'{x:.4f}' for x in ci) if ci else ('', '')),
                        report.label(s.id), *gcols, _cell(s.text)])

    if report.groups:
        with open(out / 'groups.csv', 'w', newline='', encoding='utf-8') as fh:
            w = csv.writer(fh)
            w.writerow(['group', 'members', 'statement', 'agree', 'disagree', 'pass'])
            for g, data in report.groups.items():
                for sid, c in data['statements'].items():
                    w.writerow([g, data['members'], sid, c['agree'], c['disagree'], c['pass']])

    if report.meta:
        with open(out / 'meta_crosstab.csv', 'w', newline='', encoding='utf-8') as fh:
            w = csv.writer(fh)
            w.writerow(['meta_statement', 'meta_answer', 'statement', 'agree', 'disagree', 'pass'])
            for mid, m in report.meta.items():
                for sid, by_answer in m['statements'].items():
                    for answer, c in by_answer.items():
                        w.writerow([mid, answer, sid, c['agree'], c['disagree'], c['pass']])

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
        ('Meta (demographic) statements', s['statements_meta']),
        ('Current votes (all statements)', s['votes_current']),
        ('Opinion votes: agree · pass · disagree', f"{_pct(s['agree'], s['opinion_votes'])} · {_pct(s['pass'], s['opinion_votes'])} · {_pct(s['disagree'], s['opinion_votes'])}"),
        ('Opinion groups', s['groups']),
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

    def group_cells(sid: int) -> str:
        cells = []
        for d in report.groups.values():
            c = d['statements'].get(sid)
            dec = (c['agree'] + c['disagree']) if c else 0
            cells.append(f'<td class="n">{_pct(c["agree"], dec) if dec else "—"}'
                         f'<span class="muted"> n={dec}</span></td>' if c else '<td class="n muted">—</td>')
        if report.groups:
            sp = groupviz.spread(report.groups, sid, 5)
            cells.append(f'<td class="n">{f"{sp * 100:.0f} pts" if sp is not None else "—"}</td>')
        return ''.join(cells)

    group_heads = ''.join(f'<th>Group {escape(g)}<br><span class="muted">n={d["members"]}</span></th>'
                          for g, d in report.groups.items())
    if report.groups:
        group_heads += '<th>Group spread</th>'
    table = ''.join(
        f'<tr><td class="n">{x.id}</td><td class="txt">{escape(x.text)}</td><td>{ {1: "accepted", 0: "unmoderated", -1: "rejected"}.get(x.moderated, x.moderated)}</td>'
        f'<td class="n">{x.votes}</td><td class="n">{x.agree}</td><td class="n">{x.passes}</td><td class="n">{x.disagree}</td>'
        f'<td class="n">{_pct(x.agree, x.votes)}</td><td class="n">{_pct(x.agree, x.decided)}</td>'
        f'<td class="lbl">{escape("meta (demographic)" if x.is_meta else report.label(x.id))}</td>{group_cells(x.id)}</tr>'
        for x in report.statements)

    groups_html = ''
    if report.groups:
        groups_html = (f'<h2>Opinion groups</h2><p class="muted">Groups: <b>{escape(export.group_source)}</b>. '
                       f'Groups are an input to this report, not a finding: Polis forms them by clustering a '
                       f'projection of the votes, and another method could draw them differently '
                       f'(<code>--groups FILE</code> uses your own). The map below is our own projection, so it '
                       f'shows whether these groups actually separate. It includes participants with at least '
                       f'7 current votes (or half the statements, if there are fewer than 14).</p>'
                       f'<figure>{svgs["groups-heatmap.svg"]}</figure><figure>{svgs["participant-map.svg"]}</figure>'
                       f'<p class="muted">Every statement\'s numbers per group are in the table at the end.</p>')

    title = s['title'] or 'Polis export'
    period = ''
    if s['first_vote'] and s['last_vote']:
        period = f"{s['first_vote']:%Y-%m-%d} to {s['last_vote']:%Y-%m-%d} (UTC)"
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(title)} — statistics</title>
<style>
:root{{--bg:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#6b6a66;--line:#e1e0d9}}
@media (prefers-color-scheme:dark){{:root{{--bg:#0d0d0d;--surface:#1a1a19;--ink:#fff;--ink2:#c3c2b7;--muted:#9a9891;--line:#2c2c2a}}}}
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
<p class="muted">Rejected and meta statements are left out. Bars are sorted by the agree share of all votes, with statements below {t.min_votes} agree + disagree votes last; hover a segment for counts and text. Every number is in the table below.</p>
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
{groups_html}
{_meta_html(report)}
<h2>All statements</h2>
<p class="muted">Every statement, rejected ones included. Agree %: share of all votes. Agree of decided: share of agree + disagree (passes left out). Group columns: agree of decided within the group, with its number of decided votes; spread: largest difference between groups (groups with fewer than 5 decided votes left out). Labels use the thresholds above; rejected statements get no label, and meta statements are marked as demographic (for them the group columns describe who the groups are, not an opinion).</p>
<div class="scroll wide"><table><tr><th>#</th><th>Statement</th><th>Moderation</th><th>Votes</th><th>Agree</th><th>Pass</th><th>Disagree</th><th>Agree %</th><th>Agree of decided</th><th>Label</th>{group_heads}</tr>{table}</table></div>
<p class="muted">Also written next to this file: stats.json, statements.csv (with 95% Wilson intervals), groups.csv, meta_crosstab.csv, issues.csv, charts/*.svg.</p>
</body></html>"""


def _meta_html(report: Report) -> str:
    """Meta statements as demographics: who answered what, and how each answer group voted."""
    metas = [x for x in report.statements if x.is_meta]
    if not metas:
        return ''
    by_id = {x.id: x for x in report.statements}
    out = ['<h2>Meta statements (demographics)</h2>',
           '<p class="muted">Meta statements ask about the participant, not about the topic (for example '
           '\u201cI am an administrator\u201d), so they are treated as demographics: they are left out of the '
           'opinion totals, the statement labels, the group heatmap and the participant map. '
           'Polis also leaves them out of its clustering. Below: how many answered each way, and how '
           'every opinion statement was voted by those who agreed with the meta statement compared with '
           'those who disagreed (agree as a share of agree + disagree, with the number of decided votes; '
           'rows sorted by the size of the difference). Full numbers: meta_crosstab.csv.</p>']
    for m in metas:
        if m.moderated == -1:
            out.append(f'<h3>#{m.id} {escape(m.text)}</h3><p class="muted">Rejected; not analysed.</p>')
            continue
        data = report.meta.get(m.id, {'answers': {}, 'statements': {}})
        a = data['answers']
        total = sum(a.values())
        out.append(f'<h3>#{m.id} {escape(m.text)}</h3><p>Agree {a.get("agree", 0)} ({_pct(a.get("agree", 0), total)}) · '
                   f'disagree {a.get("disagree", 0)} ({_pct(a.get("disagree", 0), total)}) · '
                   f'pass {a.get("pass", 0)} ({_pct(a.get("pass", 0), total)}) · {total} answered</p>')
        rows = []
        for sid, by_answer in data['statements'].items():
            ya, na = by_answer['agree'], by_answer['disagree']
            yd, nd = ya['agree'] + ya['disagree'], na['agree'] + na['disagree']
            ys, ns = (ya['agree'] / yd if yd else None), (na['agree'] / nd if nd else None)
            diff = abs(ys - ns) if ys is not None and ns is not None else -1
            rows.append((diff, sid, ya, yd, na, nd))
        rows.sort(key=lambda r: (-r[0], r[1]))
        body = ''.join(
            f'<tr><td class="n">{sid}</td><td class="txt">{escape(by_id[sid].text)}</td>'
            f'<td class="n">{_pct(ya["agree"], yd)}<span class="muted"> n={yd}</span></td>'
            f'<td class="n">{_pct(na["agree"], nd)}<span class="muted"> n={nd}</span></td>'
            f'<td class="n">{f"{diff * 100:.0f} pts" if diff >= 0 else "—"}</td></tr>'
            for diff, sid, ya, yd, na, nd in rows)
        out.append('<div class="scroll"><table><tr><th>#</th><th>Opinion statement</th>'
                   '<th>Agreed with meta</th><th>Disagreed with meta</th><th>Difference</th></tr>'
                   f'{body or "<tr><td colspan=5>No overlapping votes.</td></tr>"}</table></div>')
    return ''.join(out)

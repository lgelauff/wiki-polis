#!/usr/bin/env python3
"""Deterministic reports for two Polis conversations with the same statements (e.g. a before/after pair).

    python3 v2/tools/polis_report/polis_report.py config.json          # build from the export folders in the config
    python3 v2/tools/polis_report/polis_report.py config.json --fetch  # first download fresh CSVs from pol.is (report ids in the config)
    cd v2 && python -m tools.polis_report config.json                   # the same, as a module

Standard library only. Writes to the config's "out" folder:
  poll-<key>-report.html     one report per poll (statement bars, group comparison, full table, map, roles)
  poll-ab-compared.html      the two polls side by side, ONLY participants with the same xid in both polls
  poll-ab-transitions.html   for those matched participants: vote transitions in both directions, movers, who came/left
  *.csv                      every table as counts; no xid or participant id is ever written
  *.pdf                      if a Chromium/Chrome binary is found (config "chrome" or $CHROME)

Every sentence is a fixed template filled from the data: the same input gives the same output.

Rules (all in the config):
  since                 votes before this UTC time are dropped (whole rows, before taking the latest vote)
  exclude_participants  participant ids left out entirely (the moderator's automatic passes), per poll
  meta                  role/demographic statements, by text; left out of opinion totals, labels, groups, map
  labels                among agree + disagree: >= 70% agree -> broadly agreed, >= 70% disagree -> broadly rejected,
                        otherwise divided (thresholds: label_share)
  current vote          latest row per (participant, statement); equal timestamps keep file order
  groups                Polis's group-id from participant-votes.csv
  statements            the second poll's statements are matched to the first by exact text (whitespace-normalised)
                        and shown with the first poll's numbers
"""
import argparse, csv, datetime as dt, glob, html, json, math, os, random, shutil, subprocess, urllib.request
from collections import Counter, defaultdict
from pathlib import Path

POLIS_FILES = ['summary', 'comments', 'votes', 'participant-votes', 'comment-groups', 'participant-importance']
VOTES = ['agree', 'disagree', 'pass']
CODE = {1: 'agree', -1: 'disagree', 0: 'pass', None: 'no vote'}
RANK = {'agree': 2, 'pass': 1, 'disagree': 0}
LETTERS = 'ABCDEFGH'
LABEL_TEXT = {'agree': 'broadly agreed', 'reject': 'broadly rejected', 'divided': 'divided'}


def norm(s):
    return ' '.join(s.split())


def esc(s):
    return html.escape(str(s), quote=True)


def ids(cs):
    """Statement list in numeric order."""
    key = lambda c: (0, int(c)) if str(c).isdigit() else (1, str(c))
    return ', '.join(f'#{c}' for c in sorted(cs, key=key)) or 'none'


def word(n):
    return {0: 'no', 1: 'one', 2: 'two', 3: 'three', 4: 'four', 5: 'five', 6: 'six'}.get(n, str(n))


def pct(x, n):
    return 0.0 if not n else 100.0 * x / n


# ------------------------------------------------------------------ fetching
def fetch(poll, base):
    """Download the public export CSVs of one report into <dir> (overwrites)."""
    d = base / poll['dir']
    d.mkdir(parents=True, exist_ok=True)
    for f in POLIS_FILES:
        url = f"https://pol.is/api/v3/reportExport/{poll['report']}/{f}.csv"
        with urllib.request.urlopen(url, timeout=60) as r:
            (d / f'{f}.csv').write_bytes(r.read())
    stamp = dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    (d / 'PULLED').write_text(stamp + '\n')
    print(f"fetched {poll['name']} into {d} at {stamp}")


# ------------------------------------------------------------------ loading
class Poll:
    def __init__(self, cfg, pcfg, base, ref_text=None):
        self.cfg, self.key, self.name = cfg, pcfg['key'], pcfg['name']
        self.url, self.report = pcfg.get('url', ''), pcfg.get('report', '')
        d = base / pcfg['dir']
        pulled = d / 'PULLED'
        self.pulled = pulled.read_text().strip() if pulled.exists() else pcfg.get('pulled', 'unknown')
        since = int(dt.datetime.fromisoformat(cfg['since'].replace('Z', '+00:00')).timestamp())
        self.exclude = set(pcfg.get('exclude_participants', []))

        # statements, renumbered to the reference poll by text
        rows = list(csv.DictReader(open(d / 'comments.csv', newline='', encoding='utf-8-sig')))
        own = {r['comment-id']: norm(r['comment-body']) for r in rows}
        if ref_text is None:
            self.map = {k: k for k in own}
            self.renumbered = False
        else:
            by_text = {t: k for k, t in ref_text.items()}
            self.map = {k: by_text.get(t, f'{self.key}{k}') for k, t in own.items()}
            self.renumbered = any(k != v for k, v in self.map.items())
        self.text = {self.map[k]: t for k, t in own.items()}
        self.moderated = {self.map[r['comment-id']]: r['moderated'] for r in rows}
        meta_texts = {norm(t) for t in cfg.get('meta', [])}
        self.meta = {c for c, t in self.text.items() if t in meta_texts}
        accepted = {c for c, m in self.moderated.items() if m == '1'}
        self.opinion = sorted((c for c in accepted if c not in self.meta), key=self._key)
        self.roles = sorted((c for c in accepted if c in self.meta), key=self._key)
        self.unmatched = sorted(c for c in self.text if not c.isdigit())

        # votes: drop rows before `since`, then latest per (participant, statement)
        raw = list(csv.DictReader(open(d / 'votes.csv', newline='', encoding='utf-8-sig')))
        self.raw_rows = len(raw)
        kept = [r for r in raw if int(r['timestamp']) >= since]
        self.removed_rows = len(raw) - len(kept)
        self.removed_only_early = sorted({r['voter-id'] for r in raw} - {r['voter-id'] for r in kept}, key=int)
        self.last_vote = dt.datetime.fromtimestamp(max(int(r['timestamp']) for r in raw), dt.timezone.utc).strftime('%H:%M UTC')
        self.revotes = len(kept) - len({(r['voter-id'], r['comment-id']) for r in kept})
        latest = {}
        for i, r in enumerate(kept):
            k = (r['voter-id'], self.map[r['comment-id']])
            st = (int(r['timestamp']), i)
            if k not in latest or st >= latest[k][0]:
                latest[k] = (st, int(r['vote']))
        self.vote = {k: v for k, (_, v) in latest.items() if k[0] not in self.exclude}
        self.people = sorted({p for p, _ in self.vote}, key=int)

        # groups and the matrix cross-check (matrix vs latest of ALL rows, as Polis builds it)
        pv = d / 'participant-votes.csv'
        if not pv.exists():
            pv = d / 'participants-votes.csv'
        mrows = list(csv.DictReader(open(pv, newline='', encoding='utf-8-sig')))
        self.group = {r['participant']: r['group-id'] for r in mrows if r.get('group-id', '') != ''}
        allest = {}
        for i, r in enumerate(raw):
            k = (r['voter-id'], r['comment-id']); st = (int(r['timestamp']), i)
            if k not in allest or st >= allest[k][0]:
                allest[k] = (st, int(r['vote']))
        self.mismatch = 0
        for r in mrows:
            for cid in own:
                cell = r.get(cid, '')
                lv = allest.get((r['participant'], cid))
                if (cell == '' and lv is not None) or (cell != '' and (lv is None or int(cell) != lv[1])):
                    self.mismatch += 1
        gids = sorted({g for p, g in self.group.items() if p in self.people}, key=int)
        self.groups = gids
        self.letter = {g: LETTERS[i] for i, g in enumerate(gids)}
        self.members = {g: [p for p in self.people if self.group.get(p) == g] for g in gids}
        self.ungrouped = [p for p in self.people if self.group.get(p) not in gids]

        # xids
        self.xid = {}
        if pcfg.get('xid') and (base / pcfg['xid']).exists():
            self.xid = {r['participant']: r['xid'] for r in csv.DictReader(open(base / pcfg['xid'], newline='', encoding='utf-8-sig'))}

    @staticmethod
    def _key(c):
        return (0, int(c)) if c.isdigit() else (1, c)

    def tally(self, c, who=None):
        a = d = s = 0
        for p in (self.people if who is None else who):
            v = self.vote.get((p, c))
            if v == 1: a += 1
            elif v == -1: d += 1
            elif v == 0: s += 1
        return a, d, s


def label(t, share):
    a, d, _ = t
    if a + d == 0:
        return 'divided'
    if a >= share * (a + d): return 'agree'
    if d >= share * (a + d): return 'reject'
    return 'divided'


# ------------------------------------------------------------------ PCA map (stdlib, seeded)
def project(P, min_votes=7, iterations=200):
    sids = P.opinion
    col = {s: i for i, s in enumerate(sids)}
    by = defaultdict(dict)
    for (p, s), v in P.vote.items():
        if s in col:
            by[p][s] = v
    cutoff = min(min_votes, max(2, len(sids) // 2))
    voters = sorted((p for p, vs in by.items() if len(vs) >= cutoff), key=int)
    if len(voters) < 3:
        return {}, cutoff
    means = []
    for s in sids:
        seen = [by[p][s] for p in voters if s in by[p]]
        means.append(sum(seen) / len(seen) if seen else 0.0)
    X = [[by[p].get(s, means[j]) - means[j] for j, s in enumerate(sids)] for p in voters]
    rng = random.Random(0)
    comps = []
    for _ in range(2):
        v = [rng.uniform(-1, 1) for _ in sids]
        for _ in range(iterations):
            xv = [sum(a * b for a, b in zip(row, v)) for row in X]
            w = [sum(X[i][j] * xv[i] for i in range(len(X))) for j in range(len(sids))]
            for c in comps:
                dd = sum(a * b for a, b in zip(w, c))
                w = [a - dd * b for a, b in zip(w, c)]
            n = math.sqrt(sum(a * a for a in w)) or 1.0
            v = [a / n for a in w]
        comps.append(v)
    out = {}
    for p, row in zip(voters, X):
        sc = math.sqrt(len(sids) / len(by[p]))
        out[p] = (sc * sum(a * b for a, b in zip(row, comps[0])), sc * sum(a * b for a, b in zip(row, comps[1])))
    return out, cutoff


def map_svg(P, pts):
    W, H, pad = 640, 440, 28
    if not pts:
        return '<p class="note">Too few participants to draw a map.</p>'
    xs = [x for x, _ in pts.values()]; ys = [y for _, y in pts.values()]
    span = max(max(xs) - min(xs), max(ys) - min(ys)) or 1
    cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
    k = (min(W, H) - 2 * pad) / span

    def tx(x): return W / 2 + (x - cx) * k
    def ty(y): return H / 2 - (y - cy) * k
    dots, cent = [], defaultdict(list)
    for p, (x, y) in sorted(pts.items(), key=lambda t: int(t[0])):
        g = P.group.get(p)
        cls = f'g{P.groups.index(g)}' if g in P.groups else 'gx'
        dots.append(f'<circle cx="{tx(x):.1f}" cy="{ty(y):.1f}" r="4.5" class="{cls}"/>')
        if g in P.groups:
            cent[g].append((tx(x), ty(y)))
    labels = ''.join(f'<text x="{sum(a for a, _ in v) / len(v):.0f}" y="{sum(b for _, b in v) / len(v) - 10:.0f}" class="glab">{P.letter[g]}</text>'
                     for g, v in cent.items())
    return (f'<svg class="map" viewBox="0 0 {W} {H}" role="img" aria-label="Participants by opinion group">'
            f'<rect width="{W}" height="{H}" class="mapbg"/><line x1="{tx(0):.1f}" y1="0" x2="{tx(0):.1f}" y2="{H}" class="axl"/>'
            f'<line x1="0" y1="{ty(0):.1f}" x2="{W}" y2="{ty(0):.1f}" class="axl"/>{"".join(dots)}{labels}</svg>')


# ------------------------------------------------------------------ html pieces
CSS = (Path(__file__).with_name('report.css')).read_text() if Path(__file__).with_name('report.css').exists() else ''
EXTRA_CSS = '''
.g4{background:#e87ba4}.g5{background:#008300}
svg .g0{fill:var(--g0)} svg .g1{fill:var(--g1)} svg .g2{fill:var(--g2)} svg .g3{fill:var(--g3)} svg .g4{fill:#e87ba4} svg .g5{fill:#008300} svg .gx{fill:none;stroke:var(--muted)}
svg .mapbg{fill:var(--surface)} svg .axl{stroke:var(--rule)} svg .glab{fill:var(--ink);font:600 13px system-ui,sans-serif;text-anchor:middle}
svg circle{stroke:var(--surface);stroke-width:1}
.crow{display:grid;grid-template-columns:minmax(0,1.2fr) minmax(0,1fr) 84px;gap:14px;align-items:center;padding:8px 0;border-top:1px solid var(--rule)}
.crow .stmt{font-size:14px} .lab{display:block;font-size:12px;color:var(--ink2);margin-top:2px}
.pair{display:grid;grid-template-columns:16px minmax(0,1fr) 70px;gap:8px;align-items:center;margin:3px 0}
.who{font-size:12px;font-weight:600;color:var(--ink2)}
.delta{font-size:15px;font-weight:600;text-align:right;font-variant-numeric:tabular-nums} .delta small{font-size:11px;font-weight:400;color:var(--ink2)}
.mvd{display:block;font-size:11px;font-weight:400;color:var(--ink2)}
.vt td.lab2{text-align:left;color:var(--ink2);white-space:nowrap}
.mrow{display:grid;grid-template-columns:minmax(0,1.2fr) minmax(0,1fr) 130px;gap:14px;align-items:center;padding:7px 0;border-top:1px solid var(--rule)}
.mrow .stmt{font-size:14px}
.mbar{display:flex;height:14px} .mbar .half{flex:1;display:flex} .mbar .half.left{justify-content:flex-end;border-right:1px solid var(--muted)}
.mbar .half.left .seg{border-radius:4px 0 0 4px} .mbar .half.right .seg{border-radius:0 4px 4px 0}
table.tm{border-collapse:collapse;font-size:12px;font-variant-numeric:tabular-nums;margin:4px 0}
table.tm th,table.tm td{padding:3px 7px;text-align:center;border:1px solid var(--rule)}
table.tm th{color:var(--ink2);font-weight:600} table.tm th.corner{font-weight:400;font-size:11px}
table.tm td.diag{color:var(--ink2);background:var(--page)}
table.tm td.up{background:color-mix(in srgb,var(--agr) calc(var(--k)*55%),transparent);font-weight:600}
table.tm td.down{background:color-mix(in srgb,var(--dis) calc(var(--k)*55%),transparent);font-weight:600}
table.tm td.gap{color:var(--muted)} table.tm td.zero{color:var(--muted);font-weight:400;background:none}
table.tm.big{font-size:14px} table.tm.big th,table.tm.big td{padding:6px 14px}
.mfoot{font-size:12px;color:var(--ink2);margin:4px 0 0}
@media (max-width:640px){.crow,.mrow{grid-template-columns:1fr}.delta{text-align:left}}
@media print{.crow,.mrow{break-inside:avoid}}
'''
TIP_JS = '''<div id="tip" role="tooltip"></div><script>
const tip=document.getElementById('tip');
document.querySelectorAll('[data-tip]').forEach(el=>{
 el.addEventListener('mousemove',e=>{tip.textContent=el.dataset.tip;tip.style.display='block';
  tip.style.left=Math.min(e.clientX+12,innerWidth-290)+'px';tip.style.top=(e.clientY+14)+'px';});
 el.addEventListener('mouseleave',()=>tip.style.display='none');});
</script>'''


def page(title, h1, sub, body, footer, banner):
    b = f'<p class="prelim">{esc(banner)}</p>\n' if banner else ''
    return (f'<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{esc(title)}</title><style>{CSS}{EXTRA_CSS}</style></head><body><main>\n{b}<h1>{esc(h1)}</h1>\n<p class="sub">{sub}</p>\n'
            f'{body}\n<footer>{footer}</footer>\n</main>\n{TIP_JS}\n</body></html>')


def stack(a, d, s, cls='stack'):
    n = a + d + s
    return (f'<div class="{cls}"><div class="seg agr" style="width:{pct(a, n):.1f}%"></div><div class="seg pas" style="width:{pct(s, n):.1f}%"></div>'
            f'<div class="seg dis" style="width:{pct(d, n):.1f}%"></div></div>')


def legend(items):
    return '<div class="legend">' + ''.join(f'<span><i class="key {c}"></i>{t}</span>' for c, t in items) + '</div>'


LEG_ADP = [('agr', 'Agree'), ('pas', 'Pass'), ('dis', 'Disagree')]


# ------------------------------------------------------------------ single-poll report
def poll_report(P, cfg, out):
    share = cfg.get('label_share', 0.7)
    overall = {c: P.tally(c) for c in P.opinion}
    lab = {c: label(overall[c], share) for c in P.opinion}
    order = sorted(P.opinion, key=lambda c: -(overall[c][0] - overall[c][1]))
    by_label = {k: [c for c in order if lab[c] == k] for k in ('agree', 'reject', 'divided')}
    tot = [sum(overall[c][i] for c in P.opinion) for i in range(3)]
    nv = sum(tot)
    med = sorted(sum(1 for c in P.opinion if (p, c) in P.vote) for p in P.people)
    median = (med[(len(med) - 1) // 2] + med[len(med) // 2]) / 2 if med else 0
    sizes = ', '.join(f'{P.letter[g]} {len(P.members[g])}' for g in P.groups)
    small = [g for g in P.groups if len(P.members[g]) < 5]
    min_group = 5 if sum(len(P.members[g]) >= 5 for g in P.groups) >= 2 else 3

    def spread(c):
        sh = []
        for g in P.groups:
            a, d, s = P.tally(c, P.members[g])
            if len(P.members[g]) >= min_group and a + d + s:
                sh.append((a - d) / (a + d + s))
        return max(sh) - min(sh) if len(sh) >= 2 else 0
    differ = sorted(P.opinion, key=lambda c: (-spread(c), P._key(c)))[:cfg.get('n_differ', 5)]
    split = min(P.opinion, key=lambda c: (abs(overall[c][0] - overall[c][1]) / max(1, sum(overall[c])), P._key(c)))

    # chart 1
    sec = [('agree', 'Broadly agreed', f'At least {share:.0%} of agree + disagree votes agree.'),
           ('reject', 'Broadly rejected', f'At least {share:.0%} of agree + disagree votes disagree.'),
           ('divided', 'Divided', f'Neither side reaches {share:.0%}.')]
    ch1 = ''
    for k, t, note in sec:
        rows = by_label[k]
        if not rows:
            continue
        ch1 += f'<div class="block{" keep" if len(rows) <= 4 else ""}"><h3>{t} <span class="count">{len(rows)}</span></h3><p class="note">{note}</p>'
        for c in rows:
            a, d, s = overall[c]; n = a + d + s
            tip = f'#{c}: {a} agree · {d} disagree · {s} pass (n={n})'
            ch1 += (f'<div class="row" data-tip="{esc(tip)}"><div class="stmt"><span class="num">#{c}</span> {esc(P.text[c])}</div>'
                    f'<div class="div-bar"><div class="half left"><div class="seg dis" style="width:{pct(d, n):.1f}%"></div></div>'
                    f'<div class="half right"><div class="seg agr" style="width:{pct(a, n):.1f}%"></div></div></div>'
                    f'<div class="nums">{a} · {d} · {s}</div></div>')
        ch1 += '</div>'

    # chart 2
    ch2 = ''
    for c in differ:
        ch2 += f'<div class="mult"><p class="mtitle"><span class="num">#{c}</span> {esc(P.text[c])}</p>'
        for g in P.groups:
            a, d, s = P.tally(c, P.members[g])
            tip = f'Group {P.letter[g]} on #{c}: {a} agree · {s} pass · {d} disagree'
            ch2 += (f'<div class="grow{" small" if len(P.members[g]) < 5 else ""}" data-tip="{esc(tip)}"><div class="glabel"><span class="dot g{P.groups.index(g)}"></span>'
                    f'{P.letter[g]} <span class="muted">({len(P.members[g])})</span></div>{stack(a, d, s)}<div class="gnums">{a} · {s} · {d}</div></div>')
        ch2 += '</div>'

    # full table
    cols = [('All', P.people, None)] + [(f'Group {P.letter[g]}', P.members[g], g) for g in P.groups]
    head1 = '<th rowspan="2" class="sc">Statement</th>' + ''.join(
        f'<th colspan="3" class="first">{f"<span class={chr(34)}dot g{P.groups.index(g)}{chr(34)}></span>" if g else ""}{n} <span class="muted">({len(w)})</span></th>' for n, w, g in cols)
    head2 = ''.join('<th class="first">Agr</th><th>Dis</th><th>Pass</th>' for _ in cols)
    body = ''
    csv_rows = []
    for title, sids in (('Opinion statements', order), ('Role questions', P.roles)):
        if not sids:
            continue
        body += f'<tr class="sect"><td colspan="{1 + 3 * len(cols)}">{title}</td></tr>'
        for c in sids:
            body += f'<tr><td class="sc"><span class="num">#{c}</span> {esc(P.text[c])}</td>'
            rec = [c, P.text[c], 'role' if c in P.meta else lab[c]]
            for _, w, _g in cols:
                a, d, s = P.tally(c, w)
                ca = 'ca' if a + d and a >= share * (a + d) else ''
                cd = 'cd' if a + d and d >= share * (a + d) else ''
                body += f'<td class="first {ca}">{a}</td><td class="{cd}">{d}</td><td class="pc">{s}</td>'
                rec += [a, d, s]
            body += '</tr>'
            csv_rows.append(rec)
    table = f'<div class="tablewrap"><table class="vt"><thead><tr>{head1}</tr><tr>{head2}</tr></thead><tbody>{body}</tbody></table></div>'
    with open(out / f'poll-{P.key}-statements.csv', 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['statement', 'text', 'label'] + [f'{n}_{x}' for n, _, _ in cols for x in ('agree', 'disagree', 'pass')])
        w.writerows(csv_rows)

    # map
    pts, cutoff = project(P)
    svg = map_svg(P, pts)
    placed = Counter(P.group.get(p) for p in pts)

    # roles
    role_html = split_html = ''
    if P.roles:
        for c in P.roles:
            a, d, s = P.tally(c)
            role_html += (f'<div class="row role"><div class="stmt"><span class="num">#{c}</span> {esc(P.text[c])}</div>{stack(a, d, s, "stack wide")}'
                          f'<div class="nums">{a} yes · {s} pass · {d} no</div></div>')
        r0 = P.roles[0]
        yes = [p for p in P.people if P.vote.get((p, r0)) == 1]
        no = [p for p in P.people if P.vote.get((p, r0)) == -1]
        for nm, who in ((f'Yes to #{r0}', yes), (f'No to #{r0}', no)):
            a, d, s = P.tally(split, who)
            split_html += (f'<div class="grow"><div class="glabel wide-label">{esc(nm)} <span class="muted">({len(who)})</span></div>'
                           f'{stack(a, d, s)}<div class="gnums">{a} · {s} · {d}</div></div>')

    tiles = (f'<div class="tiles"><div class="tile"><b>{len(P.people)}</b><span>participants with a vote in the window</span></div>'
             f'<div class="tile"><b>{len(P.opinion)}</b><span>opinion statements, plus {len(P.roles)} role question(s)</span></div>'
             f'<div class="tile"><b>{nv}</b><span>opinion votes: {round(pct(tot[0], nv))}% agree · {round(pct(tot[2], nv))}% pass · {round(pct(tot[1], nv))}% disagree</span></div>'
             f'<div class="tile"><b>{len(by_label["agree"])} · {len(by_label["reject"])} · {len(by_label["divided"])}</b><span>statements broadly agreed · rejected · divided</span></div></div>')
    summary = (f'<div class="card"><b>Summary.</b> Of {len(P.opinion)} opinion statements, {len(by_label["agree"])} are broadly agreed ({ids(by_label["agree"])}), '
               f'{len(by_label["reject"])} broadly rejected ({ids(by_label["reject"])}) and {len(by_label["divided"])} divided ({ids(by_label["divided"])}). '
               f'Polis formed {word(len(P.groups))} opinion group{"" if len(P.groups) == 1 else "s"} (sizes: {sizes}). '
               f'The {word(len(differ))} statements with the largest difference between groups are {ids(differ)}.</div>')
    removed_who = []
    if P.removed_only_early:
        mods = [p for p in P.removed_only_early if p in P.exclude]
        others = [p for p in P.removed_only_early if p not in P.exclude]
        if mods: removed_who.append('the excluded moderator')
        if others: removed_who.append(f'{len(others)} participant(s) who voted only before the window')
    caveats = [
        f'<li><b>Window:</b> only votes cast from {esc(cfg["since"])} count; {P.removed_rows} earlier vote rows are left out'
        f'{" (" + " and ".join(removed_who) + ")" if removed_who else ""}. Last vote in the export: {P.last_vote}; exported {esc(P.pulled)}.</li>',
        f'<li><b>Excluded participants:</b> {len(P.exclude)} (the moderator, whose automatic passes on their own statements are not opinions).</li>',
        f'<li><b>Current vote</b> = each participant\'s latest vote per statement ({P.revotes} earlier re-vote rows superseded). '
        f'{P.mismatch} cell(s) of Polis\'s own participant-votes matrix differ from the latest vote in votes.csv.</li>',
        f'<li><b>Opinion groups</b> are Polis\'s own (group-id). Sizes: {sizes}; {len(P.ungrouped)} participant(s) without a group count in "All" only. '
        f'Participants voted on a median of {median:g} of {len(P.opinion)} opinion statements.</li>',
        f'<li><b>Labels</b> use the {share:.0%} rule on agree + disagree, not Polis\'s group-informed consensus.</li>',
    ]
    if P.unmatched:
        caveats.append(f'<li>Statements not found in the reference poll: {ids(P.unmatched)}.</li>')
    body = f'''{tiles}{summary}
<h2>How each statement was voted</h2>
<p class="note">Bars run left for disagree and right for agree, as a share of all votes on the statement; the remainder is passes. Numbers are agree · disagree · pass.</p>
{legend([('agr', 'Agree'), ('dis', 'Disagree'), ('pas', 'Pass (numbers only)')])}
<div class="card"><div class="axis"><div></div><div><span>100% disagree</span><span>0</span><span>100% agree</span></div><div></div></div>{ch1}</div>
<h2>Where the opinion groups differ</h2>
<p class="note">The {word(len(differ))} statements with the largest difference in (agree − disagree) share between groups with at least {min_group} members. Numbers are agree · pass · disagree.{f" Groups with fewer than 5 members are faded: {', '.join(P.letter[g] for g in small)}." if small else ""}</p>
{legend(LEG_ADP)}<div class="mults">{ch2}</div>
<h2>All votes by group</h2>
<p class="note">Agree · disagree · pass, overall and per group, in the order of the first chart. A coloured count marks a column where at least {share:.0%} of agree + disagree went that way.</p>
{table}
<h2>Map of participants</h2>
<p class="note">Two-component PCA of the opinion votes (missing votes = statement mean; participants with fewer votes scaled up, as in Polis), coloured by Polis group; not Polis's own map.
Participants with at least {cutoff} opinion votes are placed: {len(pts)} of {len(P.people)} ({", ".join(f"{P.letter[g]} {placed.get(g, 0)}" for g in P.groups)}).</p>
<div class="legend">{"".join(f'<span><span class="dot g{i}"></span>Group {P.letter[g]} ({len(P.members[g])})</span>' for i, g in enumerate(P.groups))}</div>
<div class="card map-card">{svg}</div>
{f"""<h2>Role questions</h2><p class="note">Left out of everything above.</p>{legend([('agr', 'Yes'), ('pas', 'Pass'), ('dis', 'No')])}<div class="card">{role_html}</div>
<div class="keep"><h3>#{split} by answer to #{P.roles[0]}</h3><p class="note">#{split} is the opinion statement with the smallest gap between agree and disagree. Numbers are agree · pass · disagree.</p>
{legend(LEG_ADP)}<div class="card">{split_html}</div></div>""" if P.roles else ""}
<h2>Method and caveats</h2><ul class="caveats">{''.join(caveats)}</ul>'''
    sub = (f'Polis conversation {esc(P.url)} · report {esc(P.report)}'
           f'{" · statements numbered as in " + esc(cfg["polls"][0]["name"]) + " (matched by text)" if P.renumbered else ""}')
    (out / f'poll-{P.key}-report.html').write_text(page(f'{cfg.get("banner", "")} {P.name}'.strip(), f'{cfg["title"]}: {P.name}', sub, body,
                                                        f'Built by polis_report.py from the public Polis export of report {esc(P.report)}.', cfg.get('banner')))
    return {'overall': overall, 'label': lab}


# ------------------------------------------------------------------ matched comparison
def matched(PA, PB):
    ia = {PA.xid[p]: p for p in PA.people if p in PA.xid}
    ib = {PB.xid[p]: p for p in PB.people if p in PB.xid}
    both = sorted(set(ia) & set(ib))
    return ia, ib, both


def sign_test(up, down):
    n = up + down
    if n == 0:
        return 1.0
    k = min(up, down)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def compare_reports(PA, PB, cfg, out):
    share = cfg.get('label_share', 0.7)
    ia, ib, both = matched(PA, PB)
    N = len(both)
    files_both = len(set(PA.xid.values()) & set(PB.xid.values()))
    only_a = [x for x in ia if x not in ib]; only_b = [x for x in ib if x not in ia]
    common = [c for c in PA.opinion if c in PB.opinion]
    roles = [c for c in PA.roles if c in PB.roles]

    def cat(P, idx, x, c):
        return CODE[P.vote.get((idx[x], c))]

    tabs = {}
    for c in common + roles:
        t = Counter()
        for x in both:
            t[(cat(PA, ia, x, c), cat(PB, ib, x, c))] += 1
        tabs[c] = t

    def movers(t):
        up = sum(n for (a, b), n in t.items() if a in RANK and b in RANK and RANK[b] > RANK[a])
        down = sum(n for (a, b), n in t.items() if a in RANK and b in RANK and RANK[b] < RANK[a])
        stay = sum(n for (a, b), n in t.items() if a == b and a in RANK)
        gap = sum(n for (a, b), n in t.items() if 'no vote' in (a, b))
        return up, down, stay, gap

    mv = {c: movers(tabs[c]) for c in tabs}
    flips = {c: (tabs[c][('agree', 'disagree')], tabs[c][('disagree', 'agree')]) for c in tabs}
    pv = {c: sign_test(mv[c][0], mv[c][1]) for c in common}
    holm, run = {}, 0.0
    for i, c in enumerate(sorted(common, key=lambda c: (pv[c], PA._key(c)))):
        run = max(run, min(1.0, (len(common) - i) * pv[c])); holm[c] = run
    pooled = Counter()
    for c in common:
        pooled.update(tabs[c])
    A = {c: [sum(n for (a, b), n in tabs[c].items() if a == v) for v in VOTES] for c in common}
    B = {c: [sum(n for (a, b), n in tabs[c].items() if b == v) for v in VOTES] for c in common}
    labA = {c: label(A[c], share) for c in common}; labB = {c: label(B[c], share) for c in common}

    # CSVs (counts only)
    cats = VOTES + ['no vote']
    with open(out / 'transitions_by_statement.csv', 'w', newline='') as f:
        w = csv.writer(f); w.writerow(['statement', 'text', 'A_vote', 'B_vote', 'n'])
        for c in common + roles:
            for a in cats:
                for b in cats:
                    w.writerow([c, PA.text[c], a, b, tabs[c][(a, b)]])
    with open(out / 'transitions_pooled.csv', 'w', newline='') as f:
        w = csv.writer(f); w.writerow(['A_vote'] + [f'B_{b}' for b in cats])
        for a in cats:
            w.writerow([a] + [pooled[(a, b)] for b in cats])
    mv_order = sorted(common, key=lambda c: (-(mv[c][0] + mv[c][1]), PA._key(c)))
    with open(out / 'movers.csv', 'w', newline='') as f:
        w = csv.writer(f); w.writerow(['statement', 'text', 'toward_agree', 'toward_disagree', 'stayed', 'no_vote_in_one_poll',
                                       'agree_to_disagree', 'disagree_to_agree', 'sign_test_p', 'holm_p'])
        for c in mv_order:
            w.writerow([c, PA.text[c], *mv[c], *flips[c], f'{pv[c]:.3f}', f'{holm[c]:.3f}'])
    comp = {}
    with open(out / 'composition.csv', 'w', newline='') as f:
        w = csv.writer(f); w.writerow(['statement', 'text', 'A_returners_agree', 'A_returners_n', 'A_only_agree', 'A_only_n',
                                       'B_returners_agree', 'B_returners_n', 'B_only_agree', 'B_only_n'])
        for c in common:
            def agr(P, people):
                vals = [P.vote[(p, c)] for p in people if (p, c) in P.vote]
                return sum(v == 1 for v in vals), len(vals)
            r = [*agr(PA, [ia[x] for x in both]), *agr(PA, [ia[x] for x in only_a]), *agr(PB, [ib[x] for x in both]), *agr(PB, [ib[x] for x in only_b])]
            comp[c] = r
            w.writerow([c, PA.text[c], *r])

    sub_common = (f'{N} participants with the same Polis xid in {esc(PA.name)} ({esc(PA.url)}) and {esc(PB.name)} ({esc(PB.url)}), '
                  f'each with a vote in both windows · statements numbered as in {esc(PA.name)}')
    footer = f'Built by polis_report.py from the public Polis exports of reports {esc(PA.report)} and {esc(PB.report)} and the xid files. Counts only.'
    sig = [c for c in common if holm[c] < 0.05]
    raw_sig = [c for c in common if pv[c] < 0.05]
    excluded_note = (f'<li><b>Matching:</b> {files_both} xids appear in both xid files; {N} of them have a vote in both windows and are compared. '
                     f'{len(only_a)} participant(s) voted only in {esc(PA.name)} and {len(only_b)} only in {esc(PB.name)}; they are not in the comparison.</li>')
    test_note = (f'<li><b>Test:</b> exact two-sided sign test per statement on the direction of movement (toward agree vs toward disagree, on the order agree · pass · disagree), '
                 f'Holm-corrected for {len(common)} statements. Uncorrected p &lt; 0.05: {ids(raw_sig)}; after correction: {ids(sig)}.</li>')

    # --- compared
    corder = sorted(common, key=lambda c: (-abs(B[c][0] - A[c][0]), -(mv[c][0] + mv[c][1]), PA._key(c)))

    def pair(t, who):
        a, d, s = t
        return f'<div class="pair"><span class="who">{who}</span>{stack(a, d, s)}<span class="gnums">{a} · {s} · {d}</span></div>'
    rows = ''
    for c in corder:
        lb = f'<span class="lab">{LABEL_TEXT[labA[c]]} → <b>{LABEL_TEXT[labB[c]]}</b></span>' if labA[c] != labB[c] else ''
        rows += (f'<div class="crow"><div class="stmt"><span class="num">#{c}</span> {esc(PA.text[c])}{lb}</div>'
                 f'<div class="bars">{pair(A[c], "A")}{pair(B[c], "B")}</div>'
                 f'<div class="delta">{B[c][0] - A[c][0]:+d}<small> agree</small><span class="mvd">{mv[c][1]}↘ {mv[c][0]}↗</span></div></div>')
    trows = ''.join(f'<tr><td class="sc"><span class="num">#{c}</span> {esc(PA.text[c])}</td><td class="first">{A[c][0]}</td><td>{A[c][1]}</td><td class="pc">{A[c][2]}</td>'
                    f'<td class="first">{B[c][0]}</td><td>{B[c][1]}</td><td class="pc">{B[c][2]}</td><td class="first lab2">{LABEL_TEXT[labA[c]]}</td><td class="lab2">{LABEL_TEXT[labB[c]]}</td>'
                    f'<td class="first">{B[c][0] - A[c][0]:+d}</td><td>{mv[c][1]}</td><td>{mv[c][0]}</td></tr>' for c in common)
    ta = [sum(A[c][i] for c in common) for i in range(3)]; tb = [sum(B[c][i] for c in common) for i in range(3)]
    nv = sum(ta)
    cl = lambda L: f"{list(L.values()).count('agree')} · {list(L.values()).count('reject')} · {list(L.values()).count('divided')}"
    changed = [c for c in common if labA[c] != labB[c]]
    left_agree = Counter(b for c in common for (a, b), n in tabs[c].items() for _ in range(n) if a == 'agree' and b != 'agree')
    body = f'''<div class="tiles"><div class="tile"><b>{N}</b><span>matched participants</span></div>
<div class="tile"><b>{round(pct(ta[0], nv))}% → {round(pct(tb[0], nv))}%</b><span>of their opinion votes agree</span></div>
<div class="tile"><b>{round(pct(ta[2], nv))}% → {round(pct(tb[2], nv))}%</b><span>of their opinion votes pass</span></div>
<div class="tile"><b>{cl(labA)} → {cl(labB)}</b><span>statements agreed · rejected · divided</span></div></div>
<div class="card"><b>Summary.</b> {len(common)} statements appear in both polls. Label changes among the {N}: {ids(changed)}.
Votes that left agree went to pass {left_agree.get("pass", 0)} times and to disagree {left_agree.get("disagree", 0)} times.
Statements with a Holm-corrected sign-test p below 0.05: {ids(sig)}.</div>
<h2>Statement by statement</h2>
<p class="note">Top bar {esc(PA.name)}, bottom bar {esc(PB.name)}, for the same {N} people; numbers are agree · pass · disagree. Right: change in the number agreeing, and how many moved toward disagree (↘) and toward agree (↗). Sorted by the size of the change.</p>
{legend(LEG_ADP)}<div class="card">{rows}</div>
<h2>All counts</h2>
<div class="tablewrap"><table class="vt"><thead><tr><th rowspan="2" class="sc">Statement</th><th colspan="3" class="first">{esc(PA.name)}</th><th colspan="3" class="first">{esc(PB.name)}</th><th colspan="2" class="first">Label</th><th colspan="3" class="first">Change</th></tr>
<tr><th class="first">Agr</th><th>Dis</th><th>Pass</th><th class="first">Agr</th><th>Dis</th><th>Pass</th><th class="first">A</th><th>B</th><th class="first">Agree</th><th>↘</th><th>↗</th></tr></thead><tbody>{trows}</tbody></table></div>
<h2>Method and caveats</h2><ul class="caveats">{excluded_note}{test_note}
<li><b>Opinion groups</b> are not compared: Polis forms them over everyone in each poll.</li>
<li><b>Labels</b> use the {share:.0%} rule on agree + disagree. Each poll's window, exclusions and current-vote rule are those of its own report.</li></ul>'''
    (out / 'poll-ab-compared.html').write_text(page(f'{cfg.get("banner", "")} {PA.name} and {PB.name} compared'.strip(),
                                                    f'{cfg["title"]}: {PA.name} and {PB.name} compared', sub_common, body, footer, cfg.get('banner')))

    # --- transitions
    SH = {'agree': 'Agr', 'disagree': 'Dis', 'pass': 'Pass', 'no vote': '—'}

    def matrix(t, big=False):
        mx = max([n for (a, b), n in t.items() if a != b] + [1])
        h = '<tr><th class="corner">A ↓ · B →</th>' + ''.join(f'<th>{SH[b]}</th>' for b in cats) + '</tr>'
        r = ''
        for a in cats:
            r += f'<tr><th>{SH[a]}</th>'
            for b in cats:
                n = t[(a, b)]
                if a == b: cls, st = 'diag', ''
                elif a in RANK and b in RANK:
                    cls = 'up' if RANK[b] > RANK[a] else 'down'; st = f' style="--k:{0.15 + 0.85 * n / mx if n else 0:.2f}"'
                else: cls, st = 'gap', ''
                r += f'<td class="{cls}{" zero" if n == 0 else ""}"{st}>{n}</td>'
            r += '</tr>'
        return f'<table class="tm{" big" if big else ""}">{h}{r}</table>'
    scale = max(5, 5 * math.ceil(max(max(mv[c][0], mv[c][1]) for c in common) / 5))
    mrows = ''.join(
        f'<div class="mrow"><div class="stmt"><span class="num">#{c}</span> {esc(PA.text[c])}</div>'
        f'<div class="mbar"><div class="half left"><div class="seg dis" style="width:{100 * mv[c][1] / scale:.1f}%"></div></div>'
        f'<div class="half right"><div class="seg agr" style="width:{100 * mv[c][0] / scale:.1f}%"></div></div></div>'
        f'<div class="nums">{mv[c][1]} ← · → {mv[c][0]}<br><span class="muted">{mv[c][2]} same · {mv[c][3]} gap · flips {flips[c][0]}↘ {flips[c][1]}↗</span></div></div>'
        for c in mv_order)
    grid = ''.join(f'<div class="mult"><p class="mtitle"><span class="num">#{c}</span> {esc(PA.text[c])}</p>{matrix(tabs[c])}'
                   f'<p class="mfoot">{mv[c][0]} toward agree · {mv[c][1]} toward disagree · agree→disagree {flips[c][0]} · disagree→agree {flips[c][1]} · sign test p = {pv[c]:.2f}</p></div>'
                   for c in mv_order)
    pu, pdn, ps, pg = movers(pooled)
    two_way = [c for c in common if mv[c][0] and mv[c][1]]
    one_way = [c for c in common if bool(mv[c][0]) != bool(mv[c][1])]
    none = [c for c in common if not mv[c][0] and not mv[c][1]]
    fr = lambda a, n: f'{a}/{n}' if n else '—'
    crow = ''.join(f'<tr><td class="sc"><span class="num">#{c}</span> {esc(PA.text[c])}</td><td class="first">{fr(comp[c][0], comp[c][1])}</td><td>{fr(comp[c][2], comp[c][3])}</td>'
                   f'<td class="first">{fr(comp[c][4], comp[c][5])}</td><td>{fr(comp[c][6], comp[c][7])}</td></tr>' for c in common)
    role_changes = ', '.join(f'#{c}: {sum(n for (a, b), n in tabs[c].items() if a != b and a in RANK and b in RANK)}' for c in roles)
    body = f'''<div class="tiles"><div class="tile"><b>{N}</b><span>matched participants ({files_both} xids in both files)</span></div>
<div class="tile"><b>{round(pct(ps, pu + pdn + ps))}%</b><span>of paired opinion votes unchanged</span></div>
<div class="tile"><b>{pu} · {pdn}</b><span>moved toward agree · toward disagree; of these {pooled[('disagree', 'agree')]} disagree→agree and {pooled[('agree', 'disagree')]} agree→disagree</span></div>
<div class="tile"><b>{len(only_a)} · {len(only_b)}</b><span>voted only in {esc(PA.name)} · only in {esc(PB.name)}</span></div></div>
<div class="card"><b>Summary.</b> Movement in both directions: {ids(two_way)}. One direction only: {ids(one_way)}. No change: {ids(none)}.
Straight reversals: {pooled[('agree', 'disagree')]} agree→disagree and {pooled[('disagree', 'agree')]} disagree→agree.
Statements with a Holm-corrected sign-test p below 0.05: {ids(sig)}.</div>
<h2>Movers per statement</h2>
<p class="note">How many of the {N} moved toward disagree (left) and toward agree (right) on the order agree · pass · disagree; both directions, never only the net. "Gap": voted in one poll only. "Flips": agree→disagree ↘ and disagree→agree ↗. Each half-bar runs to {scale} people. Sorted by total movement.</p>
{legend([('dis', 'Toward disagree'), ('agr', 'Toward agree')])}<div class="card">{mrows}</div>
<h2>All statements together</h2><p class="note">Rows: vote in {esc(PA.name)}; columns: vote in {esc(PB.name)}; "—" = no vote. Diagonal = unchanged; blue = toward agree, red = toward disagree.</p>
<div class="card">{matrix(pooled, True)}</div>
<h2>Transition table per statement</h2><div class="mults">{grid}</div>
<h2>Who came, who left</h2><p class="note">Agree votes / all votes on the statement, for the matched participants and for those who voted in only one poll.</p>
<div class="tablewrap"><table class="vt"><thead><tr><th rowspan="2" class="sc">Statement</th><th colspan="2" class="first">In {esc(PA.name)}</th><th colspan="2" class="first">In {esc(PB.name)}</th></tr>
<tr><th class="first">Matched ({N})</th><th>Only {esc(PA.name)} ({len(only_a)})</th><th class="first">Matched ({N})</th><th>Only {esc(PB.name)} ({len(only_b)})</th></tr></thead><tbody>{crow}</tbody></table></div>
<h2>Method and caveats</h2><ul class="caveats">{excluded_note}{test_note}
<li><b>Bowker's symmetry test</b> is not reported: per statement most off-diagonal cells hold very few people.</li>
<li><b>Order used for "toward":</b> agree · pass · disagree; pass is treated as the middle.</li>
<li><b>Role questions</b> as a consistency check, number of matched participants whose answer differs between the polls: {role_changes or "n/a"}.</li>
<li>Only counts are shown; xids are used for matching only.</li></ul>'''
    (out / 'poll-ab-transitions.html').write_text(page(f'{cfg.get("banner", "")} {PA.name} to {PB.name}, same people'.strip(),
                                                       f'{PA.name} to {PB.name}: votes of the same people', sub_common, body, footer, cfg.get('banner')))
    return N


# ------------------------------------------------------------------ main
def find_chrome(cfg):
    for c in [cfg.get('chrome'), os.environ.get('CHROME')] + sorted(glob.glob(os.path.expanduser('~/.cache/ms-playwright/chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell'))) + \
             [shutil.which(n) for n in ('chromium', 'chromium-browser', 'google-chrome', 'chrome')] + ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome']:
        if c and Path(c).exists():
            return c
    return None


def run(config, fetch_first=False, pdf=True):
    """Build every report for one config file; returns the output folder."""
    cfgp = Path(config).resolve()
    cfg = json.loads(cfgp.read_text())
    base = cfgp.parent
    if not CSS:
        raise SystemExit('report.css must sit next to polis_report.py')
    if fetch_first:
        for p in cfg['polls']:
            fetch(p, base)
    out = base / cfg.get('out', 'out')
    out.mkdir(parents=True, exist_ok=True)
    PA = Poll(cfg, cfg['polls'][0], base)
    polls = [PA] + [Poll(cfg, p, base, ref_text=PA.text) for p in cfg['polls'][1:]]
    for P in polls:
        poll_report(P, cfg, out)
        print(f'{P.name}: {len(P.people)} participants, {len(P.opinion)} opinion statements, groups {[len(P.members[g]) for g in P.groups]}')
    if len(polls) >= 2 and polls[0].xid and polls[1].xid:
        n = compare_reports(polls[0], polls[1], cfg, out)
        print(f'matched participants: {n}')
    else:
        print('xid files missing: comparison reports skipped')
    if pdf:
        chrome = find_chrome(cfg)
        if chrome:
            for h in sorted(out.glob('*.html')):
                subprocess.run([chrome, '--headless', '--no-sandbox', '--no-pdf-header-footer', f'--print-to-pdf={h.with_suffix(".pdf")}', h.as_uri()],
                               check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print(f'PDFs written with {chrome}')
        else:
            print('no Chrome/Chromium found: PDFs skipped (set "chrome" in the config or $CHROME)')
    print(f'output: {out}')
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('config')
    ap.add_argument('--fetch', action='store_true', help='download fresh CSVs from pol.is for every poll first')
    ap.add_argument('--no-pdf', action='store_true')
    a = ap.parse_args(argv)
    run(a.config, fetch_first=a.fetch, pdf=not a.no_pdf)


if __name__ == '__main__':
    main()

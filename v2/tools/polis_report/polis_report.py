#!/usr/bin/env python3
"""Deterministic reports for two Polis conversations with the same statements (e.g. a before/after pair).

    python3 v2/tools/polis_report/polis_report.py config.json          # build from the export folders in the config
    python3 v2/tools/polis_report/polis_report.py config.json --fetch  # first download fresh CSVs from pol.is (report ids in the config)
    cd v2 && python -m tools.polis_report config.json                   # the same, as a module

Standard library only. Writes to the config's "out" folder:
  poll-<key>-report.html     one report per poll
  poll-ab-compared.html      the two polls side by side, ONLY participants with the same xid in both polls
  poll-ab-transitions.html   for those matched participants: vote transitions in both directions, movers, one-poll-only voters
  *.csv                      every table as counts; no xid or participant id is ever written
  *.pdf                      if a Chromium/Chrome binary is found (config "chrome" or $CHROME)

Every sentence is a fixed template filled from the data: the same input and code give byte-identical HTML and CSV.

Rules (all in the config):
  since                 votes before this UTC time are dropped (whole rows, before taking the latest vote)
  timezone              IANA zone for local times in the report (default UTC)
  automatic votes       a vote by a statement's author on that statement, cast at the second the statement was created,
                        is the platform's automatic vote and is not counted; all other votes count, whoever casts them
  exclude_participants  optional manual override: participant ids left out entirely, per poll (exclude_reason says why)
  statement_pairs       optional [[text in first poll, text in second poll], ...] for statements edited between polls
  min_participants_for_groups  groups are shown only with at least this many participants (default 25)
  meta                  role/demographic statements, by text; left out of opinion totals, labels, groups, map
  include_unmoderated   also treat statements with moderated == 0 as opinion statements (default: only accepted, 1)
  label_share           among agree + disagree: >= share agree / >= share disagree / neither (default 0.7)
  current vote          latest row per (participant, statement) in votes.csv; equal timestamps keep file order
  min_total             the fewest responses behind a percentage, bar or label, and the fewest people in a Polis group
                        shown on its own (default 10); below it the counts are shown without them. Every count is exact.
  groups                Polis's group-id from participant-votes.csv; groups under min_total participants are merged into "Other"
  statements            the second poll's statements are matched to the first by text and shown with the first poll's numbers
"""
import argparse, csv, datetime as dt, glob, hashlib, html, json, math, os, platform, random, shutil, statistics, subprocess, urllib.request
from collections import Counter, defaultdict
from fractions import Fraction
from pathlib import Path

POLIS_FILES = ['summary', 'comments', 'votes', 'participant-votes', 'comment-groups', 'participant-importance']
VOTES = ['agree', 'disagree', 'pass']
CODE = {1: 'agree', -1: 'disagree', 0: 'pass', None: 'no vote'}
RANK = {'agree': 2, 'pass': 1, 'disagree': 0}


def norm(s):
    """Whitespace-normalised text with typographic apostrophes and quotes made plain, for matching."""
    return ' '.join(s.replace('’', "'").replace('‘', "'").replace('“', '"').replace('”', '"').split())


def esc(s):
    return html.escape(str(s), quote=True)


def skey(c):
    return (0, int(c)) if str(c).isdigit() else (1, str(c))


def ids(cs):
    return ', '.join(f'#{c}' for c in sorted(cs, key=skey)) or 'none'


def word(n):
    return {0: 'no', 1: 'one', 2: 'two', 3: 'three', 4: 'four', 5: 'five', 6: 'six'}.get(n, str(n))


def plural(n, one, many=None):
    return f'{n} {one if n == 1 else (many or one + "s")}'


def pct(x, n):
    return 0.0 if not n else 100.0 * x / n


def share_of(x, n, k):
    """A whole percent from at least k responses, otherwise the count itself ("x of n")."""
    return f'{round(pct(x, n))}%' if n >= k else f'{x} of {n}'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:12]


def read_csv(path):
    with open(path, newline='', encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))


def write_csv(path, header, rows):
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


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
    (d / 'PULLED').write_text(stamp + '\n', encoding='utf-8')
    print(f"fetched {poll['name']} into {d} at {stamp}")


# ------------------------------------------------------------------ loading
class Poll:
    def __init__(self, cfg, pcfg, base, ref_text=None):
        self.cfg, self.key, self.name = cfg, pcfg['key'], pcfg['name']
        self.url, self.report = pcfg.get('url', ''), pcfg.get('report', '')
        self.warnings = []
        d = base / pcfg['dir']
        self.dir = d
        pulled = d / 'PULLED'
        self.pulled = pulled.read_text(encoding='utf-8').strip() if pulled.exists() else pcfg.get('pulled', 'unknown')
        self.since = int(dt.datetime.fromisoformat(cfg['since'].replace('Z', '+00:00')).timestamp())
        self.exclude = set(pcfg.get('exclude_participants', []))
        self.exclude_reason = pcfg.get('exclude_reason', cfg.get('exclude_reason', 'listed in the config'))
        self.since_reason = pcfg.get('since_reason', cfg.get('since_reason', ''))

        # statements, renumbered to the reference poll by text
        rows = read_csv(d / 'comments.csv')
        own = {r['comment-id']: norm(r['comment-body']) for r in rows}
        dup = [t for t, n in Counter(own.values()).items() if n > 1]
        if dup:
            raise SystemExit(f'{self.name}: {len(dup)} statement text(s) occur more than once; matching by text is ambiguous')
        if ref_text is None:
            self.map = {k: k for k in own}
            self.renumbered = False
        else:
            by_text = {norm(t): k for k, t in ref_text.items()}
            for ta, tb in cfg.get('statement_pairs', []):
                if norm(ta) in by_text:
                    by_text[norm(tb)] = by_text[norm(ta)]
            self.map = {k: by_text.get(t, f'{self.key}{k}') for k, t in own.items()}
            self.renumbered = any(k != v for k, v in self.map.items())
        self.own_id = {v: k for k, v in self.map.items()}
        self.text = {self.map[r['comment-id']]: ' '.join(r['comment-body'].split()) for r in rows}
        self.moderated = {self.map[r['comment-id']]: r['moderated'] for r in rows}
        self.created = {self.map[r['comment-id']]: int(r['timestamp']) for r in rows}
        auto_key = {(r['author-id'], r['comment-id'], int(r['timestamp'])) for r in rows}
        self.n_rejected = sum(1 for m in self.moderated.values() if m == '-1')
        self.n_unmoderated = sum(1 for m in self.moderated.values() if m == '0')
        meta_texts = {norm(t) for t in cfg.get('meta', [])}
        self.meta = {c for c in self.text if norm(self.text[c]) in meta_texts}
        missing = meta_texts - {norm(self.text[c]) for c in self.meta}
        if missing:
            self.warnings.append(f'{len(missing)} meta text(s) from the config not found in this poll')
        ok = {'1', '0'} if cfg.get('include_unmoderated') else {'1'}
        shown = {c for c, m in self.moderated.items() if m in ok}
        self.opinion = sorted((c for c in shown if c not in self.meta), key=skey)
        self.roles = sorted((c for c in shown if c in self.meta), key=skey)
        self.unmatched = sorted((c for c in self.text if not c.isdigit()), key=skey)

        # votes: drop rows before `since`, then latest per (participant, statement)
        raw_all = read_csv(d / 'votes.csv')
        is_auto = lambda r: (r['voter-id'], r['comment-id'], int(r['timestamp'])) in auto_key
        raw = [r for r in raw_all if not is_auto(r)]
        self.auto_votes = len(raw_all) - len(raw)
        auto_values = Counter(int(r['vote']) for r in raw_all if is_auto(r))
        self.auto_by_value = {name: auto_values.get(v, 0) for v, name in ((0, 'pass'), (1, 'agree'), (-1, 'disagree'))}
        self.auto_only = sorted({r['voter-id'] for r in raw_all if is_auto(r)} - {r['voter-id'] for r in raw}, key=int)
        kept = [r for r in raw if int(r['timestamp']) >= self.since]
        self.removed_rows = len(raw) - len(kept)
        self.removed_only_early = sorted({r['voter-id'] for r in raw} - {r['voter-id'] for r in kept}, key=int)
        self.excluded_rows = sum(1 for r in kept if r['voter-id'] in self.exclude)
        ts = [int(r['timestamp']) for r in kept if r['voter-id'] not in self.exclude]
        self.first_ts, self.last_ts = (min(ts), max(ts)) if ts else (None, None)
        self.last_export_vote = max(int(r['timestamp']) for r in raw_all)
        self.revotes = len(kept) - len({(r['voter-id'], r['comment-id']) for r in kept})
        self.tie_rows = sum(n - 1 for n in Counter((r['voter-id'], r['comment-id'], r['timestamp']) for r in kept).values() if n > 1)
        latest = {}
        for i, r in enumerate(kept):
            k = (r['voter-id'], self.map[r['comment-id']])
            st = (int(r['timestamp']), i)
            if k not in latest or st >= latest[k][0]:
                latest[k] = (st, int(r['vote']))
        self.vote = {k: v for k, (_, v) in latest.items() if k[0] not in self.exclude}
        opinion_set = set(self.opinion)
        self.people = sorted({p for (p, c) in self.vote if c in opinion_set}, key=int)   # at least one opinion vote

        # groups and the matrix cross-check (participant-votes.csv vs latest of ALL rows by time)
        pv = d / 'participant-votes.csv'
        if not pv.exists():
            pv = d / 'participants-votes.csv'
        mrows = read_csv(pv)
        self.group = {r['participant']: r['group-id'] for r in mrows if r.get('group-id', '') != ''}
        self.polis_sizes = Counter(self.group.values())
        allest = {}
        for i, r in enumerate(raw_all):
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
        people = set(self.people)
        self.excluded_in_groups = sorted({self.group[p] for p in set(self.exclude) | set(self.auto_only) if p in self.group}, key=int)
        self.grouped_not_counted = sum(1 for p in self.group if p not in people and p not in self.exclude and p not in self.auto_only)
        self.group_floor = cfg.get('min_participants_for_groups', 25)
        self.min_total = max(1, int(cfg.get('min_total', 10)))
        self.groups_computed = len(self.people) >= self.group_floor
        gids = sorted({g for p, g in self.group.items() if p in people}, key=int) if self.groups_computed else []
        self.members = {g: [p for p in self.people if self.group.get(p) == g] for g in gids}
        self.groups = [g for g in gids if len(self.members[g]) >= self.min_total]      # shown groups
        self.small = [g for g in gids if len(self.members[g]) < self.min_total]        # merged into "Other"
        self.gname = {g: f'Group {i + 1}' for i, g in enumerate(gids)}
        self.other = [p for g in self.small for p in self.members[g]]
        self.ungrouped = [p for p in self.people if self.group.get(p) not in gids]

        # statements created after the first counted vote: who could not have seen them
        self.late = []
        if self.first_ts is not None:
            last_by = {}
            for r in kept:
                if r['voter-id'] in people:
                    last_by[r['voter-id']] = max(last_by.get(r['voter-id'], 0), int(r['timestamp']))
            for c in self.opinion:
                if self.created[c] > self.first_ts:
                    self.late.append((c, self.created[c], sum(1 for t in last_by.values() if t < self.created[c])))

        # xids
        self.xid = {}
        if pcfg.get('xid') and (base / pcfg['xid']).exists():
            self.xid_path = base / pcfg['xid']
            self.xid = {r['participant']: r['xid'] for r in read_csv(self.xid_path)}

    def tally(self, c, who=None):
        a = d = s = 0
        for p in (self.people if who is None else who):
            v = self.vote.get((p, c))
            if v == 1: a += 1
            elif v == -1: d += 1
            elif v == 0: s += 1
        return a, d, s

    def local(self, ts):
        if ts is None:
            return 'n/a'
        tzname = self.cfg.get('timezone', 'UTC')
        try:
            from zoneinfo import ZoneInfo
            tz = ZoneInfo(tzname)
        except Exception:
            tz, tzname = dt.timezone.utc, 'UTC'
        t = dt.datetime.fromtimestamp(ts, dt.timezone.utc)
        return f"{t.strftime('%Y-%m-%d %H:%M')} UTC ({t.astimezone(tz).strftime('%H:%M')} {tzname})"


def to_change(t, share):
    """How many responses would have to change for the label to change, as a sentence (descriptive, not an interval)."""
    a, d, _ = t
    n, q = a + d, Fraction(str(share))
    if n == 0:
        return ''
    if a >= q * n:          # fewest agree -> disagree changes that bring agree below the share
        j, frm, to = math.floor(a - q * n) + 1, 'agree', 'disagree'
    elif d >= q * n:
        j, frm, to = math.floor(d - q * n) + 1, 'disagree', 'agree'
    else:                   # fewest changes that bring one side up to the share
        j, frm, to = min((math.ceil(q * n - a), 'disagree', 'agree'), (math.ceil(q * n - d), 'agree', 'disagree'))
    return f'{plural(j, "response")} changing from {frm} to {to} would change this label'


def label(t, share, k):
    """agree / disagree / neither by share of agree + disagree; 'few' below k agree + disagree responses."""
    a, d, _ = t
    if a + d < k:
        return 'few'
    if a >= share * (a + d): return 'agree'
    if d >= share * (a + d): return 'disagree'
    return 'neither'


def label_text(k, share):
    return {'agree': f'≥{share:.0%} agree', 'disagree': f'≥{share:.0%} disagree', 'neither': f'neither ≥{share:.0%}',
            'few': 'too few responses for a label'}[k]


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


SHAPES = ['circle', 'square', 'triangle', 'diamond', 'cross', 'star']


def marker(i, x, y, r=5):
    kind = SHAPES[i % len(SHAPES)] if i >= 0 else 'ring'
    cls = f'm{i}' if i >= 0 else 'mo'
    if kind == 'circle':
        return f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" class="{cls}"/>'
    if kind == 'ring':
        return f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r - 1}" class="{cls}"/>'
    if kind == 'square':
        return f'<rect x="{x - r + .5:.1f}" y="{y - r + .5:.1f}" width="{2 * r - 1}" height="{2 * r - 1}" class="{cls}"/>'
    if kind == 'triangle':
        return f'<polygon points="{x:.1f},{y - r - 1:.1f} {x + r + .5:.1f},{y + r - .5:.1f} {x - r - .5:.1f},{y + r - .5:.1f}" class="{cls}"/>'
    if kind == 'diamond':
        return f'<polygon points="{x:.1f},{y - r - 1:.1f} {x + r + 1:.1f},{y:.1f} {x:.1f},{y + r + 1:.1f} {x - r - 1:.1f},{y:.1f}" class="{cls}"/>'
    return f'<rect x="{x - r:.1f}" y="{y - 1.5:.1f}" width="{2 * r}" height="3" class="{cls}"/><rect x="{x - 1.5:.1f}" y="{y - r:.1f}" width="3" height="{2 * r}" class="{cls}"/>'


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
    dots = []
    for p, (x, y) in sorted(pts.items(), key=lambda t: int(t[0])):
        g = P.group.get(p)
        i = P.groups.index(g) if g in P.groups else -1
        dots.append(marker(i, tx(x), ty(y)))
    counts = Counter(P.group.get(p) for p in pts)
    alt = (f'Scatter plot of {len(pts)} participants placed by similarity of their opinion votes; '
           + '; '.join(f'{P.gname[g]}: {counts.get(g, 0)}' for g in P.groups)
           + (f'; Other: {sum(counts.get(g, 0) for g in P.small)}' if P.small else '') + '.')
    return (f'<svg class="map" viewBox="0 0 {W} {H}" role="img" aria-label="{esc(alt)}"><title>{esc(alt)}</title>'
            f'<rect width="{W}" height="{H}" class="mapbg"/><line x1="{tx(0):.1f}" y1="0" x2="{tx(0):.1f}" y2="{H}" class="axl"/>'
            f'<line x1="0" y1="{ty(0):.1f}" x2="{W}" y2="{ty(0):.1f}" class="axl"/>{"".join(dots)}</svg>')


def map_legend(P):
    items = ''.join(f'<span><svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">{marker(i, 7, 7, 5)}</svg> {P.gname[g]} ({len(P.members[g])})</span>'
                    for i, g in enumerate(P.groups))
    if P.small:
        items += f'<span><svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">{marker(-1, 7, 7, 5)}</svg> Other ({len(P.other)})</span>'
    return f'<div class="legend">{items}</div>'


# ------------------------------------------------------------------ html pieces
_here = Path(__file__).with_name('report.css')
CSS = _here.read_text(encoding='utf-8') if _here.exists() else ''
EXTRA_CSS = '''
:root{--m0:#4a3aa7;--m1:#eb6834;--m2:#1baf7a;--m3:#e87ba4;--m4:#52514e;--m5:#008300}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--m0:#9085e9;--m1:#d95926;--m2:#199e70;--m3:#d55181;--m4:#c3c2b7;--m5:#2fa52f}}
svg .m0{fill:var(--m0)} svg .m1{fill:var(--m1)} svg .m2{fill:var(--m2)} svg .m3{fill:var(--m3)} svg .m4{fill:var(--m4)} svg .m5{fill:var(--m5)}
svg .mo{fill:none;stroke:var(--muted);stroke-width:1.5}
svg .mapbg{fill:var(--surface)} svg .axl{stroke:var(--rule)}
.legend svg{vertical-align:-2px}
.grow.small .stack{opacity:.7}
.grow{grid-template-columns:96px minmax(0,1fr) 72px}
.crow{display:grid;grid-template-columns:minmax(0,1.2fr) minmax(0,1fr) 84px;gap:14px;align-items:center;padding:8px 0;border-top:1px solid var(--rule)}
.crow .stmt{font-size:14px} .lab{display:block;font-size:12px;color:var(--ink2);margin-top:2px}
.pair{display:grid;grid-template-columns:16px minmax(0,1fr) 70px;gap:8px;align-items:center;margin:3px 0}
.who{font-size:12px;font-weight:600;color:var(--ink2)}
.delta{font-size:15px;font-weight:600;text-align:right;font-variant-numeric:tabular-nums} .delta small{font-size:11px;font-weight:400;color:var(--ink2)}
.mvd{display:block;font-size:11px;font-weight:400;color:var(--ink2)}
.vt td.lab2{text-align:left;color:var(--ink2);white-space:nowrap}
.vt th.sc{white-space:normal;font-weight:400;color:var(--ink);font-size:13px;text-align:left}
@media print{.vt th.sc{font-size:9.5px}}
.vt caption{text-align:left;font-size:12px;color:var(--ink2);padding:8px 8px 4px}
.mrow{display:grid;grid-template-columns:minmax(0,1.2fr) minmax(0,1fr) 150px;gap:14px;align-items:center;padding:7px 0;border-top:1px solid var(--rule)}
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
.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
.repro{font-size:12px;color:var(--ink2)} .repro td{padding:2px 10px 2px 0;vertical-align:top} .repro code{font-size:11px}
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
ORDER_NOTE = 'Numbers are always agree · disagree · pass.'
SELF_SELECTED = 'Self-selected participants; counts describe these voters only.'


def page(title, h1, sub, body, footer, banner):
    b = f'<p class="prelim">{esc(banner)}</p>\n' if banner else ''
    return (f'<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{esc(title)}</title><style>{CSS}{EXTRA_CSS}</style></head><body><main>\n{b}<h1>{esc(h1)}</h1>\n<p class="sub">{sub}</p>\n'
            f'{body}\n<footer>{footer}</footer>\n</main>\n{TIP_JS}\n</body></html>')


def stack(a, d, s, cls='stack', label_text_='', *, k):
    n = a + d + s
    if n < k:
        return f'<div class="{cls} few"><span class="muted">fewer than {k} responses</span></div>'
    aria = f' role="img" aria-label="{esc(label_text_ or f"{a} agree, {d} disagree, {s} pass")}"'
    return (f'<div class="{cls}"{aria}><div class="seg agr" style="width:{pct(a, n):.1f}%"></div><div class="seg dis" style="width:{pct(d, n):.1f}%"></div>'
            f'<div class="seg pas" style="width:{pct(s, n):.1f}%"></div></div>')


def legend(items):
    return '<div class="legend">' + ''.join(f'<span><i class="key {c}"></i>{t}</span>' for c, t in items) + '</div>'


LEG_ADP = [('agr', 'Agree'), ('dis', 'Disagree'), ('pas', 'Pass')]


def write_page(path, html_text):
    path.write_text(html_text, encoding='utf-8')


# ------------------------------------------------------------------ reproducibility
def repro_block(cfg, cfgp, polls):
    here = Path(__file__).resolve()
    try:
        head = subprocess.run(['git', '-C', str(here.parent), 'rev-parse', '--short=12', 'HEAD'], capture_output=True, text=True, check=True).stdout.strip()
        dirty = subprocess.run(['git', '-C', str(here.parent), 'status', '--porcelain', '--', here.name, 'report.css'], capture_output=True, text=True).stdout.strip()
        git = head + (' (with uncommitted changes)' if dirty else '')
    except Exception:
        git = 'not a git checkout'
    rows = [('Script', f'polis_report.py · git {esc(git)} · sha256 {sha(here)}'),
            ('Config', f'{esc(cfgp.name)} · sha256 {sha(cfgp)}'),
            ('Python', esc(platform.python_version())),
            ('Window', f'votes from {esc(polls[0].local(polls[0].since))}')]
    for P in polls:
        files = ['comments.csv', 'votes.csv', 'participant-votes.csv' if (P.dir / 'participant-votes.csv').exists() else 'participants-votes.csv']
        h = ' · '.join(f'{f} {sha(P.dir / f)}' for f in files)
        if P.xid:
            h += f' · xid file {sha(P.xid_path)}'
        rows.append((esc(P.name), f'exported {esc(P.pulled)} · report {esc(P.report)} · sha256 {h}'))
    return ('<h2>Reproducibility</h2><table class="repro">'
            + ''.join(f'<tr><td>{k}</td><td><code>{v}</code></td></tr>' for k, v in rows) + '</table>')


# ------------------------------------------------------------------ single-poll report
def excluded_html(P):
    """Every response counts unless excluded; one line per exclusion with its rule, reason and count (METHODOLOGY §4)."""
    v = P.auto_by_value
    lines = [
        f'<li><b>Automatic responses</b> (rule: a response by a statement\'s author on that statement, at the second the statement was created; '
        f'reason: Polis records it automatically, it is not a choice): {plural(P.auto_votes, "response")} excluded '
        f'({v["pass"]} pass · {v["agree"]} agree · {v["disagree"]} disagree); {plural(len(P.auto_only), "participant")} cast only automatic responses. '
        f'Polis\'s own counts include them. All other responses count, including those of statement authors.</li>',
        f'<li><b>Before {esc(P.local(P.since))}</b> (rule: <code>since</code>; reason: {esc(P.since_reason) or "none given in the config"}): '
        f'{plural(P.removed_rows, "response")} excluded; '
        f'{plural(len([p for p in P.removed_only_early if p not in P.exclude]), "participant")} responded only before it.</li>',
    ]
    if P.exclude:
        lines.append(f'<li><b>Listed participants</b> (rule: <code>exclude_participants</code>; reason: {esc(P.exclude_reason)}): '
                     f'{plural(P.excluded_rows, "response")} from {plural(len(P.exclude), "participant")} excluded.</li>')
    return f'<ul class="caveats">{"".join(lines)}</ul>'


def poll_report(P, cfg, out, repro, other_labels=None):
    share = cfg.get('label_share', 0.7)
    k = P.min_total
    overall = {c: P.tally(c) for c in P.opinion}
    lab = {c: label(overall[c], share, k) for c in P.opinion}
    tested = run_slot(cfg, 'pass_rate', {c: (overall[c][2], overall[c][0] + overall[c][1]) for c in P.opinion})
    order = sorted(P.opinion, key=lambda c: (-(overall[c][0] - overall[c][1]), skey(c)))
    by_label = {key: [c for c in order if lab[c] == key] for key in ('agree', 'disagree', 'neither', 'few')}
    tot = [sum(overall[c][i] for c in P.opinion) for i in range(3)]
    nv = sum(tot)
    counts = [sum(1 for c in P.opinion if (p, c) in P.vote) for p in P.people]
    median = statistics.median(counts) if counts else 0
    sizes = ', '.join([f'{P.gname[g]} {len(P.members[g])}' for g in P.groups] + ([f'Other {len(P.other)}'] if P.small else []))
    measure_ok = len(P.groups) >= 2

    def spread(c):
        sh = []
        for g in P.groups:
            a, d, s = P.tally(c, P.members[g])
            if a + d + s:
                sh.append((a - d) / (a + d + s))
        return max(sh) - min(sh) if len(sh) >= 2 else 0
    differ = sorted(P.opinion, key=lambda c: (-spread(c), skey(c)))[:cfg.get('n_differ', 5)] if measure_ok else []

    # chart 1: statements by label
    ch1 = ''
    for key in ('agree', 'disagree', 'neither', 'few'):
        rows = by_label[key]
        if not rows:
            continue
        head = (f'{label_text(key, share)} (of agree + disagree)' if key != 'few' else
                f'Too few responses for a label (fewer than {k} agree + disagree)')
        ch1 += f'<div class="block{" keep" if len(rows) <= 4 else ""}"><h3>{head} <span class="count">{len(rows)}</span></h3>'
        for c in rows:
            a, d, s = overall[c]; n = a + d + s
            sens = to_change(overall[c], share) if key != 'few' else ''
            tip = f'#{c}: {a} agree · {d} disagree · {s} pass (n={n})' + (f'; {sens}' if sens else '') + (f'; {tested[c]}' if c in tested else '')
            bar = (f'<div class="div-bar" role="img" aria-label="{esc(tip)}"><div class="half left"><div class="seg dis" style="width:{pct(d, n):.1f}%"></div></div>'
                   f'<div class="half right"><div class="seg agr" style="width:{pct(a, n):.1f}%"></div></div></div>' if n >= k else
                   f'<div class="div-bar few"><span class="muted">fewer than {k} responses</span></div>')
            ch1 += (f'<div class="row" data-tip="{esc(tip)}"><div class="stmt"><span class="num">#{c}</span> {esc(P.text[c])}</div>'
                    f'{bar}<div class="nums">{a} · {d} · {s}</div></div>')
        ch1 += '</div>'

    # chart 2: groups (only groups with >= min_total members)
    ch2 = ''
    for c in differ:
        ch2 += f'<div class="mult"><p class="mtitle"><span class="num">#{c}</span> {esc(P.text[c])}</p>'
        for g in P.groups:
            a, d, s = P.tally(c, P.members[g])
            ch2 += (f'<div class="grow"><div class="glabel">{P.gname[g]} <span class="muted">({len(P.members[g])})</span></div>'
                    f'{stack(a, d, s, k=k)}<div class="gnums">{a} · {d} · {s}</div></div>')
        ch2 += '</div>'

    # full table: All, shown groups, Other (small cells suppressed); role rows never crossed with Other
    cols = [('All', P.people, 'all')] + [(P.gname[g], P.members[g], 'group') for g in P.groups] + ([('Other', P.other, 'other')] if P.small else [])
    head1 = '<th rowspan="2" scope="col" class="sc">Statement</th>' + ''.join(
        f'<th colspan="3" scope="colgroup" class="first">{n} <span class="muted">({len(w)})</span></th>' for n, w, _ in cols)
    head2 = ''.join('<th scope="col" class="first">Agr</th><th scope="col">Dis</th><th scope="col">Pass</th>' for _ in cols)
    body = ''
    csv_rows = []
    for title, sids in (('Opinion statements', order), ('Role questions', P.roles)):
        if not sids:
            continue
        body += f'<tr class="sect"><td colspan="{1 + 3 * len(cols)}">{title}</td></tr>'
        for c in sids:
            role = c in P.meta
            body += f'<tr><th scope="row" class="sc"><span class="num">#{c}</span> {esc(P.text[c])}</th>'
            rec = [c, P.text[c], 'role' if role else label_text(lab[c], share), '' if role or lab[c] == 'few' else to_change(overall[c], share),
                   tested.get(c, '')]
            for _, w, kind in cols:
                a, d, s = P.tally(c, w)
                if role and kind != 'all':      # role answers are not split by group (METHODOLOGY §7, §11)
                    body += '<td class="first pc">—</td><td class="pc">—</td><td class="pc">—</td>'
                    rec += ['', '', '']
                    continue
                ca = 'ca' if a + d >= k and a >= share * (a + d) else ''
                cd = 'cd' if a + d >= k and d >= share * (a + d) else ''
                body += f'<td class="first {ca}">{a}</td><td class="{cd}">{d}</td><td class="pc">{s}</td>'
                rec += [a, d, s]
            body += '</tr>'
            csv_rows.append(rec)
    table = (f'<div class="tablewrap"><table class="vt"><caption>Agree · disagree · pass per statement, overall and per Polis group. {ORDER_NOTE}</caption>'
             f'<thead><tr>{head1}</tr><tr>{head2}</tr></thead><tbody>{body}</tbody></table></div>')
    write_csv(out / f'poll-{P.key}-statements.csv', ['statement', 'text', 'label', 'label_sensitivity', 'test'] + [f'{n}_{x}' for n, _, _ in cols for x in ('agree', 'disagree', 'pass')], csv_rows)

    # map
    pts, cutoff = project(P)
    svg = map_svg(P, pts)

    # roles: their own counts only; no other result is split by a role answer (METHODOLOGY §7)
    role_html = ''
    if P.roles:
        for c in P.roles:
            a, d, s = P.tally(c)
            role_html += (f'<div class="row role"><div class="stmt"><span class="num">#{c}</span> {esc(P.text[c])}</div>'
                          f'{stack(a, d, s, "stack wide", f"{a} yes, {d} no, {s} pass", k=k)}<div class="nums">{a} yes · {d} no · {s} pass</div></div>')

    # text
    reconcile = ''
    if other_labels:
        n_m, labs_m, other_name = other_labels
        diff_l = [c for c in P.opinion if c in labs_m and labs_m[c] != lab[c]]
        reconcile = (f' Among the {n_m} participants who also voted in {esc(other_name)} (matched by xid), the label differs from this page on: {ids(diff_l)}.'
                     f' Paired results on the comparison pages describe those {n_m} only.')
    few_note = f'; {len(by_label["few"])} with too few responses for a label' if by_label['few'] else ''
    few_sum = (f'while {len(by_label["few"])} have fewer than {k} agree + disagree responses, too few for a label ({ids(by_label["few"])}); '
               if by_label['few'] else '')
    tiles = (f'<div class="tiles"><div class="tile"><b>{len(P.people)}</b><span>participants with an opinion vote in the window</span></div>'
             f'<div class="tile"><b>{len(P.opinion)}</b><span>opinion statements, plus {plural(len(P.roles), "role question")}</span></div>'
             f'<div class="tile"><b>{nv}</b><span>opinion votes: {share_of(tot[0], nv, k)} agree · {share_of(tot[1], nv, k)} disagree · {share_of(tot[2], nv, k)} pass</span></div>'
             f'<div class="tile"><b>{len(by_label["agree"])} · {len(by_label["disagree"])} · {len(by_label["neither"])}</b><span>statements {label_text("agree", share)} · {label_text("disagree", share)} · neither'
             f'{few_note}</span></div></div>')
    summary = (f'<div class="card"><b>Summary.</b> Of {len(P.opinion)} opinion statements, {len(by_label["agree"])} have {label_text("agree", share)} ({ids(by_label["agree"])}), '
               f'{len(by_label["disagree"])} have {label_text("disagree", share)} ({ids(by_label["disagree"])}) and {len(by_label["neither"])} neither ({ids(by_label["neither"])}), '
               f'{few_sum}counting agree + disagree only. Polis groups shown: {sizes or "none"}.{reconcile} {SELF_SELECTED}</div>')
    differ_note = (f'<p class="note">Measure (this report\'s own, not Polis\'s representativeness or group-informed consensus): for each statement, the range across '
                   f'groups of (agree − disagree) / all votes in the group, over groups with at least {k} members. The {word(len(differ))} statements with the '
                   f'largest range are shown. Descriptive only: the groups were formed from these same votes, so no test is applied. {ORDER_NOTE}</p>'
                   if measure_ok else
                   (f'<p class="note">Not computed: fewer than two Polis groups have at least {k} members ({sizes}).</p>' if P.groups_computed else
                    f'<p class="note">Not computed: {len(P.people)} participants, fewer than the {P.group_floor} needed before opinion groups are shown.</p>'))
    excl = excluded_html(P)
    late = ('; '.join(f'#{c} created {esc(P.local(t))}, after {n} participant(s) had cast their last vote' for c, t, n in P.late) or 'none')
    stmt_line = (f'<li><b>Statements:</b> {len(P.opinion)} opinion and {plural(len(P.roles), "role question")} counted; '
                 f'{P.n_rejected} rejected and {P.n_unmoderated} unmoderated statement(s) '
                 f'{"included" if cfg.get("include_unmoderated") else "left out"}{" (unmoderated ones included)" if cfg.get("include_unmoderated") else ""}. '
                 f'Statements created after voting in the window had started: {late}. Each statement is reported with its own number of votes.</li>')
    caveats = [
        f'<li><b>Window:</b> votes from {esc(P.local(P.since))}. '
        f'Opinion votes in the window: first {esc(P.local(P.first_ts))}, last {esc(P.local(P.last_ts))}. Exported {esc(P.pulled)}.</li>',
        stmt_line,
        f'<li><b>Current vote</b> = each participant\'s latest row per statement in votes.csv ({P.revotes} earlier re-vote rows superseded; '
        f'{plural(P.tie_rows, "row shares", "rows share")} a timestamp with another row for the same participant and statement and {"is" if P.tie_rows == 1 else "are"} ordered by file position). '
        f'{P.mismatch} cells of participant-votes.csv differ from this; that file keeps the last row per participant and statement in id order, not time order.</li>',
        f'<li><b>Polis groups</b> (group-id) are a snapshot at export time, computed by Polis over all votes, including votes before the window and automatic votes; participants with only automatic votes '
        f'are{"" if P.excluded_in_groups else " not"} in a Polis group{" (in Polis " + ", ".join(P.gname.get(g, "group " + g) for g in P.excluded_in_groups) + ")" if P.excluded_in_groups else ""}. '
        f'{plural(P.grouped_not_counted, "participant")} with a group-id {"has" if P.grouped_not_counted == 1 else "have"} no opinion vote in this window. Polis group sizes as exported: '
        f'{", ".join(f"{P.gname.get(g, chr(35) + g)} {n}" for g, n in sorted(P.polis_sizes.items(), key=lambda t: int(t[0])))}. '
        f'Groups are shown only with at least {P.group_floor} participants (here {len(P.people)}: {"shown" if P.groups_computed else "not shown"}); '
        f'groups with fewer than {k} participants are merged into "Other"; {plural(len(P.ungrouped), "participant")} without a group count in "All" only.</li>',
        f'<li><b>Left out, for focus:</b> every count is exact. A bar needs at least {k} responses and a label at least {k} agree + disagree responses; '
        f'below that the counts are shown on their own. Role answers are not shown for "Other". These limits are about how much a number can carry, not about privacy.</li>',
        f'<li><b>Participation:</b> median {median:g} of {len(P.opinion)} opinion statements per participant. Polis chooses the order in which each participant sees statements.</li>',
        '<li><b>No significance:</b> this report shows observed counts and rule-based descriptions only; it applies no test and marks nothing as significant.</li>',
        f'<li><b>Labels</b> use {share:.0%} of agree + disagree; passes are not in the denominator. They are not Polis\'s group-informed consensus. '
        f'The hover text and the CSV give how many responses would have to change for a label to change; that describes these responses and is not a confidence interval. Role answers are self-reported.</li>',
    ]
    if P.unmatched:
        caveats.append(f'<li>Statements not found in the reference poll: {ids(P.unmatched)}.</li>')
    for w in P.warnings:
        caveats.append(f'<li><b>Warning:</b> {esc(w)}.</li>')
    role_sec = ''
    if P.roles:
        role_sec = (f'<h2>Role questions</h2><p class="note">Left out of everything above, and not used to split other results. Answers are self-reported. '
                    f'Numbers are yes · no · pass.</p>'
                    f'{legend([("agr", "Yes"), ("dis", "No"), ("pas", "Pass")])}<div class="card">{role_html}</div>')
    body = f'''{tiles}{summary}
<h2>How each statement was voted</h2>
<p class="note">Bars run left for disagree and right for agree, as a share of all votes on the statement; the remainder is passes. {ORDER_NOTE}</p>
{legend([('agr', 'Agree'), ('dis', 'Disagree'), ('pas', 'Pass (numbers only)')])}
<div class="card"><div class="axis"><div></div><div><span>100% disagree</span><span>0</span><span>100% agree</span></div><div></div></div>{ch1}</div>
<h2>Statements with the largest difference between Polis groups</h2>
{differ_note}
{legend(LEG_ADP) + f'<div class="mults">{ch2}</div>' if measure_ok else ''}
<h2>All votes by group</h2>
<p class="note">In the order of the first chart. A coloured count marks a column where at least {share:.0%} of agree + disagree went that way. {ORDER_NOTE}</p>
{table}
<h2>Map of participants</h2>
<p class="note">Two-component PCA of the opinion votes (missing vote = statement mean; participants with fewer votes scaled up, as in Polis); not Polis's own map.
Axes have no units and their orientation is arbitrary; closeness means similar vote patterns. Participants with at least {cutoff} opinion votes are placed: {len(pts)} of {len(P.people)}.</p>
{map_legend(P)}<div class="card map-card">{svg}</div>
{role_sec}
<h2>Excluded responses</h2>{excl}
<h2>Method and caveats</h2><ul class="caveats">{''.join(caveats)}</ul>
{repro}'''
    sub = (f'Polis conversation {esc(P.url)} · report {esc(P.report)}'
           f'{" · statements numbered as in " + esc(cfg["polls"][0]["name"]) + " (matched by text)" if P.renumbered else ""}')
    write_page(out / f'poll-{P.key}-report.html', page(f'{cfg.get("banner", "")} {P.name}'.strip(), f'{cfg["title"]}: {P.name}', sub, body,
                                                       f'Built by polis_report.py from the public Polis export of report {esc(P.report)}.', cfg.get('banner')))
    return lab


# ------------------------------------------------------------------ matched comparison
def matched(PA, PB):
    ia = {PA.xid[p]: p for p in PA.people if p in PA.xid}
    ib = {PB.xid[p]: p for p in PB.people if p in PB.xid}
    return ia, ib, sorted(set(ia) & set(ib))


# Significance slots: empty and switched off (METHODOLOGY §2 and §11). Owner, 2026-10-31: reports give observed
# values only and mark nothing as significant. These are the "first" places of §11, kept so a test can be added later
# as a small change. None of the tests named here has been reviewed: each is a suggestion, not the method, and §11
# lists the questions to answer first (level and sides, family, correction, exact or approximate, marker form, not
# tested versus not significant, minimum). A test may only add to what is shown; it never changes a count or a
# reading. Each slot is a function {statement: counts} -> {statement: sentence}, given every statement at once so a
# correction could be applied. A slot runs only when the config setting `significance` is true AND a function is set
# here; none is set.
SLOTS = {
    'shift': None,          # Direction of shift per statement: (toward agree, toward disagree). Suggested, not reviewed: exact sign test
    'switches': None,       # Direct agree<->disagree switches: (agree->disagree, disagree->agree). Suggested, not reviewed: exact McNemar
    'pass_change': None,    # Change in pass rate: (into pass, out of pass). Suggested, not reviewed: exact McNemar
    'pass_rate': None,      # Statements passed more often than others: (pass, not pass). Suggested, not reviewed: Cochran's Q,
                            # then McNemar per statement; that would need per-participant counts, not only these totals
}


def run_slot(cfg, name, family):
    """The sentences of one switched-on slot, or {} (the default: observed values only)."""
    test = SLOTS.get(name)
    return test(family) if cfg.get('significance') and test else {}


def matched_labels(PA, PB, share):
    ia, ib, both = matched(PA, PB)
    common = [c for c in PA.opinion if c in PB.opinion]
    la = {c: label(PA.tally(c, [ia[x] for x in both]), share, PA.min_total) for c in common}
    lb = {c: label(PB.tally(c, [ib[x] for x in both]), share, PA.min_total) for c in common}
    return len(both), la, lb


def compare_reports(PA, PB, cfg, out, repro):
    share = cfg.get('label_share', 0.7)
    k = PA.min_total
    ia, ib, both = matched(PA, PB)
    N = len(both)
    files_both = len(set(PA.xid.values()) & set(PB.xid.values()))
    only_a = [x for x in ia if x not in ib]; only_b = [x for x in ib if x not in ia]
    common = [c for c in PA.opinion if c in PB.opinion]
    roles = [c for c in PA.roles if c in PB.roles]
    cats = VOTES + ['no vote']

    def cat(P, idx, x, c):
        return CODE[P.vote.get((idx[x], c))]

    tabs = {}
    for c in common:
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

    mv = {c: movers(tabs[c]) for c in common}
    flips = {c: (tabs[c][('agree', 'disagree')], tabs[c][('disagree', 'agree')]) for c in common}
    m = len(common)
    to_pass = {c: sum(n for (a, b), n in tabs[c].items() if b == 'pass' and a in ('agree', 'disagree')) for c in common}
    from_pass = {c: sum(n for (a, b), n in tabs[c].items() if a == 'pass' and b in ('agree', 'disagree')) for c in common}
    tested = {}
    for name, family in (('shift', {c: (mv[c][0], mv[c][1]) for c in common}), ('switches', flips),
                         ('pass_change', {c: (to_pass[c], from_pass[c]) for c in common})):
        for c, sentence in run_slot(cfg, name, family).items():
            tested.setdefault(c, []).append(sentence)
    tested = {c: '; '.join(v) for c, v in tested.items()}

    def reading(c):
        """What was observed, as a rule-based sentence; never causal. A test's sentence follows only if the slot is on."""
        up, down = mv[c][0], mv[c][1]
        if up + down == 0:
            text = 'No observed movement.'
        elif up == down:
            text = f'{up} moved toward agree and {down} toward disagree.'
        else:
            side, more, less = ('agree', up, down) if up > down else ('disagree', down, up)
            text = f'More moved toward {side} ({more}) than the other way ({less}).'
        return text + (f' ({tested[c]})' if c in tested else '')
    pooled = Counter()
    for c in common:
        pooled.update(tabs[c])
    A = {c: list(PA.tally(c, [ia[x] for x in both])) for c in common}
    B = {c: list(PB.tally(c, [ib[x] for x in both])) for c in common}
    labA = {c: label(A[c], share, k) for c in common}; labB = {c: label(B[c], share, k) for c in common}
    allA = {c: label(PA.tally(c), share, k) for c in common}; allB = {c: label(PB.tally(c), share, k) for c in common}

    # noise baselines
    net = {c: mv[c][0] - mv[c][1] for c in common}
    with_net = [c for c in common if net[c]]

    def a_side(c):
        a, d, _ = A[c]
        return 1 if a > d else -1 if d > a else 0
    toward_mid = [c for c in with_net if a_side(c) and (net[c] > 0) != (a_side(c) > 0)]

    # participants: role breakdown (small cells suppressed), times
    def role_counts(P, people, c):
        return P.tally(c, people)
    groups3 = [('Matched', PA, [ia[x] for x in both]), (f'Only {PA.name}', PA, [ia[x] for x in only_a]), (f'Only {PB.name}', PB, [ib[x] for x in only_b])]
    role_rows = ''
    for c in roles:
        role_rows += f'<tr><th scope="row" class="sc"><span class="num">#{c}</span> {esc(PA.text[c])}</th>'
        for _, P, people in groups3:
            a, d, s = role_counts(P, people, c)
            role_rows += f'<td class="first">{a}</td><td>{d}</td><td class="pc">{s}</td>'
        role_rows += '</tr>'
    role_table = (f'<div class="tablewrap"><table class="vt"><caption>Answers to the role questions (yes · no · pass), as given in the poll each group voted in '
                  f'(matched: {esc(PA.name)}). Self-reported.</caption><thead><tr><th rowspan="2" scope="col" class="sc">Role question</th>'
                  + ''.join(f'<th colspan="3" scope="colgroup" class="first">{esc(n)} ({len(p)})</th>' for n, _, p in groups3)
                  + '</tr><tr>' + ''.join('<th scope="col" class="first">Yes</th><th scope="col">No</th><th scope="col">Pass</th>' for _ in groups3)
                  + f'</tr></thead><tbody>{role_rows}</tbody></table></div>') if roles else ''
    gap_h = (PB.first_ts - PA.last_ts) / 3600 if PA.last_ts and PB.first_ts else None
    who_block = (f'<h2>Participants</h2><p class="note">{SELF_SELECTED} {N} participants have the same xid in both polls and an opinion vote in both windows '
                 f'({files_both} xids occur in both xid files); {len(only_a)} voted only in {esc(PA.name)}, {len(only_b)} only in {esc(PB.name)}. '
                 f'Matching assumes one xid per person. Opinion votes: {esc(PA.name)} {esc(PA.local(PA.first_ts))} to {esc(PA.local(PA.last_ts))}; '
                 f'{esc(PB.name)} {esc(PB.local(PB.first_ts))} to {esc(PB.local(PB.last_ts))}'
                 f'{f"; from the last {PA.name} vote to the first {PB.name} vote: {gap_h:.1f} h" if gap_h is not None else ""}. '
                 f'The two conversations number the statements differently (matched by text) and Polis chooses the order in which each participant sees them.</p>{role_table}')

    # CSVs (counts only; role answers are not compared between polls)
    write_csv(out / 'transitions_by_statement.csv', ['statement', 'text', 'A_vote', 'B_vote', 'n'],
              [[c, PA.text[c], a, b, tabs[c][(a, b)]] for c in common for a in cats for b in cats])
    write_csv(out / 'transitions_pooled.csv', ['A_vote'] + [f'B_{b}' for b in cats], [[a] + [pooled[(a, b)] for b in cats] for a in cats])
    write_csv(out / 'movers.csv', ['statement', 'text', 'toward_agree', 'toward_disagree', 'stayed', 'no_vote_in_one_poll', 'agree_to_disagree',
                                   'disagree_to_agree', 'movers', 'reading', 'test'],
              [[c, PA.text[c], *mv[c], *flips[c], mv[c][0] + mv[c][1], reading(c), tested.get(c, '')] for c in common])
    comp = {}
    for c in common:
        def agr(P, people):
            vals = [P.vote[(p, c)] for p in people if (p, c) in P.vote]
            return sum(v == 1 for v in vals), len(vals)
        comp[c] = [*agr(PA, [ia[x] for x in both]), *agr(PA, [ia[x] for x in only_a]), *agr(PB, [ib[x] for x in both]), *agr(PB, [ib[x] for x in only_b])]
    write_csv(out / 'composition.csv', ['statement', 'text', 'A_matched_agree', 'A_matched_n', 'A_only_agree', 'A_only_n',
                                        'B_matched_agree', 'B_matched_n', 'B_only_agree', 'B_only_n'], [[c, PA.text[c], *comp[c]] for c in common])

    sub_common = (f'{N} participants with the same Polis xid in {esc(PA.name)} ({esc(PA.url)}) and {esc(PB.name)} ({esc(PB.url)}) · '
                  f'statements numbered as in {esc(PA.name)}')
    footer = f'Built by polis_report.py from the public Polis exports of reports {esc(PA.report)} and {esc(PB.report)} and the xid files. Counts only.'
    noise_line = (f'Baseline: of {len(with_net)} statements with net movement, {len(toward_mid)} moved away from the side that led in {esc(PA.name)} among these participants '
                  f'(toward the middle).')
    test_note = ('<li><b>No significance:</b> this report shows observed counts only and applies no test. The counts describe these participants; '
                 'a difference between the two polls is not a claim that it would recur. A test of the direction of movement per statement is planned.</li>'
                 if not tested else
                 '<li><b>Test:</b> the sentence in brackets after each reading comes from the test switched on in the report builder.</li>')
    scope_note = (f'<li><b>Scope:</b> paired results describe these {N} returners only. Labels among all voters differ from the labels among the {N} on: '
                  f'{esc(PA.name)} {ids([c for c in common if allA[c] != labA[c]])}; {esc(PB.name)} {ids([c for c in common if allB[c] != labB[c]])}. '
                  f'Statements in only one poll (not compared): {esc(PA.name)} {ids([c for c in PA.opinion if c not in common])}; '
                  f'{esc(PB.name)} {ids([c for c in PB.opinion if c not in common])}. Statements are the same when their text matches '
                  f'(ignoring spacing and apostrophe style) or when the config pairs them.</li>')

    # --- compared
    def pair(t, who):
        a, d, s = t
        return f'<div class="pair"><span class="who">{who}</span>{stack(a, d, s, k=k)}<span class="gnums">{a} · {d} · {s}</span></div>'
    rows = ''
    for c in common:
        lb = f'<span class="lab">{label_text(labA[c], share)} → <b>{label_text(labB[c], share)}</b></span>' if labA[c] != labB[c] else ''
        lb += f'<span class="lab">{esc(reading(c))}</span>'
        rows += (f'<div class="crow"><div class="stmt"><span class="num">#{c}</span> {esc(PA.text[c])}{lb}</div>'
                 f'<div class="bars">{pair(A[c], "A")}{pair(B[c], "B")}</div>'
                 f'<div class="delta">{B[c][0] - A[c][0]:+d}<small> agree</small><span class="mvd">{mv[c][1]}↘ {mv[c][0]}↗</span></div></div>')
    trows = ''.join(f'<tr><th scope="row" class="sc"><span class="num">#{c}</span> {esc(PA.text[c])}</th><td class="first">{A[c][0]}</td><td>{A[c][1]}</td><td class="pc">{A[c][2]}</td>'
                    f'<td class="first">{B[c][0]}</td><td>{B[c][1]}</td><td class="pc">{B[c][2]}</td><td class="first lab2">{label_text(labA[c], share)}</td><td class="lab2">{label_text(labB[c], share)}</td>'
                    f'<td class="first">{B[c][0] - A[c][0]:+d}</td><td>{mv[c][1]}</td><td>{mv[c][0]}</td></tr>' for c in common)
    ta = [sum(A[c][i] for c in common) for i in range(3)]; tb = [sum(B[c][i] for c in common) for i in range(3)]
    na, nb = sum(ta), sum(tb)  # each poll's share is out of that poll's own responses

    def cl(L):
        v = list(L.values())
        return f"{v.count('agree')} · {v.count('disagree')} · {v.count('neither')}" + (f" · {v.count('few')} too few" if 'few' in v else '')
    changed = [c for c in common if labA[c] != labB[c]]
    left_agree = Counter(b for c in common for (a, b), n in tabs[c].items() for _ in range(n) if a == 'agree' and b != 'agree')
    body = f'''<div class="tiles"><div class="tile"><b>{N}</b><span>matched participants; all figures on this page are among these {N}</span></div>
<div class="tile"><b>{share_of(ta[0], na, k)} → {share_of(tb[0], nb, k)}</b><span>of opinion votes agree, among the {N}</span></div>
<div class="tile"><b>{share_of(ta[2], na, k)} → {share_of(tb[2], nb, k)}</b><span>of opinion votes pass, among the {N}</span></div>
<div class="tile"><b>{cl(labA)} → {cl(labB)}</b><span>statements {label_text("agree", share)} · {label_text("disagree", share)} · neither, among the {N}</span></div></div>
<div class="card"><b>Summary.</b> {m} statements appear in both polls. Label changes among the {N}: {ids(changed)}.
Votes that left agree went to disagree {left_agree.get("disagree", 0)} times and to pass {left_agree.get("pass", 0)} times.
{noise_line}</div>
<h2>Statement by statement</h2>
<p class="note">Top bar {esc(PA.name)}, bottom bar {esc(PB.name)}, for the same {N} people. Right: change in the number agreeing, and how many moved toward disagree (↘) and toward agree (↗). In statement order. {ORDER_NOTE}</p>
{legend(LEG_ADP)}<div class="card">{rows}</div>
<h2>All counts</h2>
<div class="tablewrap"><table class="vt"><caption>Votes of the {N} matched participants in each poll. {ORDER_NOTE}</caption><thead><tr><th rowspan="2" scope="col" class="sc">Statement</th><th colspan="3" scope="colgroup" class="first">{esc(PA.name)}</th><th colspan="3" scope="colgroup" class="first">{esc(PB.name)}</th><th colspan="2" scope="colgroup" class="first">Label</th><th colspan="3" scope="colgroup" class="first">Change</th></tr>
<tr><th scope="col" class="first">Agr</th><th scope="col">Dis</th><th scope="col">Pass</th><th scope="col" class="first">Agr</th><th scope="col">Dis</th><th scope="col">Pass</th><th scope="col" class="first">A</th><th scope="col">B</th><th scope="col" class="first">Agree</th><th scope="col">↘</th><th scope="col">↗</th></tr></thead><tbody>{trows}</tbody></table></div>
{who_block}
<h2>Method and caveats</h2><ul class="caveats">{scope_note}{test_note}
<li><b>Polis groups</b> are not compared: Polis forms them over everyone in each poll.</li>
<li><b>Labels</b> use {share:.0%} of agree + disagree and need at least {k} agree + disagree responses; bars need at least {k} responses. Every count is exact. Each poll's window, exclusions and current-vote rule are those of its own report.</li></ul>
{repro}'''
    write_page(out / 'poll-ab-compared.html', page(f'{cfg.get("banner", "")} {PA.name} and {PB.name} compared'.strip(),
                                                   f'{cfg["title"]}: {PA.name} and {PB.name} compared', sub_common, body, footer, cfg.get('banner')))

    # --- transitions
    SH = {'agree': 'Agr', 'disagree': 'Dis', 'pass': 'Pass', 'no vote': '—'}

    def matrix(t, cap, big=False):
        mx = max([n for (a, b), n in t.items() if a != b] + [1])
        h = '<tr><th scope="col" class="corner">A ↓ · B →</th>' + ''.join(f'<th scope="col">{SH[b]}</th>' for b in cats) + '</tr>'
        r = ''
        for a in cats:
            r += f'<tr><th scope="row">{SH[a]}</th>'
            for b in cats:
                n = t[(a, b)]
                if a == b: cls, st = 'diag', ''
                elif a in RANK and b in RANK:
                    cls = 'up' if RANK[b] > RANK[a] else 'down'; st = f' style="--k:{0.15 + 0.85 * n / mx if n else 0:.2f}"'
                else: cls, st = 'gap', ''
                r += f'<td class="{cls}{" zero" if n == 0 else ""}"{st}>{n}</td>'
            r += '</tr>'
        return f'<table class="tm{" big" if big else ""}"><caption class="sr">{esc(cap)}</caption>{h}{r}</table>'
    scale = max(5, 5 * math.ceil(max([max(mv[c][0], mv[c][1]) for c in common] + [1]) / 5))
    mrows = ''.join(
        f'<div class="mrow"><div class="stmt"><span class="num">#{c}</span> {esc(PA.text[c])}</div>'
        f'<div class="mbar" role="img" aria-label="{mv[c][1]} toward disagree, {mv[c][0]} toward agree"><div class="half left"><div class="seg dis" style="width:{100 * mv[c][1] / scale:.1f}%"></div></div>'
        f'<div class="half right"><div class="seg agr" style="width:{100 * mv[c][0] / scale:.1f}%"></div></div></div>'
        f'<div class="nums">{mv[c][1]} ← · → {mv[c][0]}<br><span class="muted">{mv[c][2]} same · {mv[c][3]} gap · agree↔disagree {flips[c][0]}↘ {flips[c][1]}↗</span></div></div>'
        for c in common)
    grid = ''.join(f'<div class="mult"><p class="mtitle"><span class="num">#{c}</span> {esc(PA.text[c])}</p>{matrix(tabs[c], f"Transitions for #{c}")}'
                   f'<p class="mfoot">{mv[c][0]} toward agree · {mv[c][1]} toward disagree · agree→disagree {flips[c][0]} · disagree→agree {flips[c][1]} · '
                   f'{mv[c][0] + mv[c][1]} movers</p><p class="mfoot"><b>{esc(reading(c))}</b></p></div>' for c in common)
    pu, pdn, ps, pg = movers(pooled)
    two_way = [c for c in common if mv[c][0] and mv[c][1]]
    one_way = [c for c in common if bool(mv[c][0]) != bool(mv[c][1])]
    none = [c for c in common if not mv[c][0] and not mv[c][1]]

    def fr(a, n):
        return f'{a}/{n}' if n else '—'
    crow = ''.join(f'<tr><th scope="row" class="sc"><span class="num">#{c}</span> {esc(PA.text[c])}</th><td class="first">{fr(comp[c][0], comp[c][1])}</td><td>{fr(comp[c][2], comp[c][3])}</td>'
                   f'<td class="first">{fr(comp[c][4], comp[c][5])}</td><td>{fr(comp[c][6], comp[c][7])}</td></tr>' for c in common)
    body = f'''<div class="tiles"><div class="tile"><b>{N}</b><span>matched participants ({files_both} xids in both files)</span></div>
<div class="tile"><b>{share_of(ps, pu + pdn + ps, k)}</b><span>of paired opinion votes unchanged</span></div>
<div class="tile"><b>{pu} · {pdn}</b><span>moved toward agree · toward disagree; agree↔disagree switches: {pooled[('agree', 'disagree')]} agree→disagree, {pooled[('disagree', 'agree')]} disagree→agree</span></div>
<div class="tile"><b>{len(only_a)} · {len(only_b)}</b><span>voted only in {esc(PA.name)} · only in {esc(PB.name)}</span></div></div>
<div class="card"><b>Summary.</b> Movement in both directions: {ids(two_way)}. One direction only: {ids(one_way)}. No observed movement: {ids(none)}.
Agree↔disagree switches: {pooled[('agree', 'disagree')]} agree→disagree and {pooled[('disagree', 'agree')]} disagree→agree.
{noise_line}</div>
<h2>Movers per statement</h2>
<p class="note">How many of the {N} moved toward disagree (left) and toward agree (right) on the order agree · pass · disagree; both directions, never only the net. "Gap": voted in one poll only. Each half-bar runs to {scale} people. In statement order.</p>
{legend([('dis', 'Toward disagree'), ('agr', 'Toward agree')])}<div class="card">{mrows}</div>
<h2>All statements together</h2><p class="note">Rows: vote in {esc(PA.name)}; columns: vote in {esc(PB.name)}; "—" = no vote. Diagonal = unchanged; blue = toward agree, red = toward disagree.
The {m} statements are summed, so one person counts up to {m} times.</p>
<div class="card">{matrix(pooled, "All statements", True)}</div>
<h2>Transition table per statement</h2><div class="mults">{grid}</div>
<h2>Agree counts: matched vs one-poll-only</h2><p class="note">Agree votes / all votes on the statement, for the matched participants and for those who voted in only one poll.</p>
<div class="tablewrap"><table class="vt"><caption>Agree / all votes per statement</caption><thead><tr><th rowspan="2" scope="col" class="sc">Statement</th><th colspan="2" scope="colgroup" class="first">In {esc(PA.name)}</th><th colspan="2" scope="colgroup" class="first">In {esc(PB.name)}</th></tr>
<tr><th scope="col" class="first">Matched ({N})</th><th scope="col">Only {esc(PA.name)} ({len(only_a)})</th><th scope="col" class="first">Matched ({N})</th><th scope="col">Only {esc(PB.name)} ({len(only_b)})</th></tr></thead><tbody>{crow}</tbody></table></div>
{who_block}
<h2>Method and caveats</h2><ul class="caveats">{scope_note}{test_note}
<li><b>Order used for "toward":</b> agree · pass · disagree; pass is treated as the middle.</li>
<li>Only counts are shown; xids are used for matching only. Role answers are not compared between polls.</li></ul>
{repro}'''
    write_page(out / 'poll-ab-transitions.html', page(f'{cfg.get("banner", "")} {PA.name} to {PB.name}, same people'.strip(),
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
    cfg = json.loads(cfgp.read_text(encoding='utf-8'))
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
    repro = repro_block(cfg, cfgp, polls)
    share = cfg.get('label_share', 0.7)
    paired = len(polls) >= 2 and polls[0].xid and polls[1].xid
    ml = matched_labels(polls[0], polls[1], share) if paired else None
    for i, P in enumerate(polls):
        other = None
        if ml and i < 2:
            other = (ml[0], ml[1] if i == 0 else ml[2], polls[1 - i].name)
        poll_report(P, cfg, out, repro, other)
        for w in P.warnings:
            print(f'warning ({P.name}): {w}')
        print(f'{P.name}: {len(P.people)} participants, {len(P.opinion)} opinion statements, groups shown {[len(P.members[g]) for g in P.groups]}, other {len(P.other)}')
    if paired:
        print(f'matched participants: {compare_reports(polls[0], polls[1], cfg, out, repro)}')
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

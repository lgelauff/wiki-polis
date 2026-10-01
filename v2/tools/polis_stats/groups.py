"""Opinion groups: where they come from, how they differ, and whether they separate at all.

Groups are an input, not a finding. By default they are Polis's own clusters (``group-id`` in
participants-votes.csv: k-means on Polis's projection of the vote matrix); ``--groups FILE`` replaces
them with any other assignment. Two views:

* a heatmap of agree share per statement and group, rows sorted by how far the groups differ;
* a participant map: our own two-component PCA of the vote matrix (not Polis's map), each
  participant a dot coloured by group, so one can see whether the groups really separate.
"""

from __future__ import annotations

import csv
import math
import random
from html import escape
from pathlib import Path

from .charts import _svg
from .export import Export

# Categorical group colours (validated light/dark; blue and red are left to agree/disagree).
GROUP_LIGHT = ['#eb6834', '#1baf7a', '#4a3aa7', '#eda100', '#e87ba4', '#008300']
GROUP_DARK = ['#d95926', '#199e70', '#9085e9', '#c98500', '#d55181', '#008300']
MAX_GROUPS = len(GROUP_LIGHT)
SPREAD_MIN = 10    # decided votes a group needs before it counts in the spread (a descriptive gap, not a test)
MAP_MIN_VOTES = 7  # opinion votes a participant needs to be placed on the map


def load_groups(path: str | Path) -> dict[int, int | None]:
    """Read a ``participant,group`` CSV (header required; an empty group = not grouped)."""
    with open(path, newline='', encoding='utf-8-sig') as fh:
        rows = list(csv.DictReader(fh))
    if not rows or not {'participant', 'group'} <= set(rows[0]):
        raise ValueError(f'{path}: need a header with participant,group')
    out: dict[int, int | None] = {}
    for line, r in enumerate(rows, start=2):
        p, g = (r['participant'] or '').strip(), (r['group'] or '').strip()
        try:
            pid, gid = int(p), (int(g) if g else None)
        except ValueError:
            raise ValueError(f'{path}, line {line}: participant and group must be whole numbers') from None
        if pid in out:
            raise ValueError(f'{path}, line {line}: participant {pid} appears twice')
        out[pid] = gid
    return out


def group_style() -> str:
    light = ''.join(f'.g{i}{{fill:{c};stroke:{c}}}' for i, c in enumerate(GROUP_LIGHT))
    dark = ''.join(f'.g{i}{{fill:{c};stroke:{c}}}' for i, c in enumerate(GROUP_DARK))
    return (f'<style>{light}.gx{{fill:none;stroke:#898781}}.pt{{stroke:#fcfcfb}}.halo{{stroke:#fcfcfb}}'
            f'@media (prefers-color-scheme:dark){{{dark}.pt{{stroke:#1a1a19}}.halo{{stroke:#1a1a19}}}}</style>')


def _cls(i: int) -> str:
    """Colour class for the i-th group; beyond the palette, groups share the neutral style (never cycled)."""
    return f'g{i}' if i < MAX_GROUPS else 'gx'


# ── heatmap ────────────────────────────────────────────────────────────────────────────────

def spread(statement_groups: dict[str, dict], sid: int, min_n: int) -> float | None:
    """Largest difference in agree share between any two groups with at least min_n decided votes."""
    shares = []
    for g in statement_groups.values():
        c = g['statements'].get(sid)
        if c and c['agree'] + c['disagree'] >= min_n:
            shares.append(c['agree'] / (c['agree'] + c['disagree']))
    return (max(shares) - min(shares)) if len(shares) >= 2 else None


def _cell_fill(share: float) -> tuple[str, float]:
    """Diverging fill: red below 0.5, blue above, grey at the midpoint; opacity carries distance."""
    if abs(share - 0.5) < 0.05:
        return 'pa', 0.9
    return ('ag' if share > 0.5 else 'di'), 0.18 + 0.62 * abs(share - 0.5) * 2


def heatmap(statements, groups: dict[str, dict], min_n: int = 5,
            title: str = 'Agree share per statement and group') -> str:
    rows = [s for s in statements if s.moderated != -1 and not s.is_meta]
    rows.sort(key=lambda s: (-(spread(groups, s.id, SPREAD_MIN) or -1), s.id))
    names = list(groups)
    label_w, cell_w, cell_h, top = 64, 112, 26, 102
    width = label_w + cell_w * len(names) + 150
    height = top + cell_h * max(len(rows), 1) + 24
    body = [f'<text class="t1" x="0" y="16" style="font-weight:600">{escape(title)}</text>',
            f'<text class="t2 small" x="0" y="34">Cell: agree as a share of agree + disagree within the group '
            f'(blue = agree, red = disagree, grey = split).</text>'
            f'<text class="t2 small" x="0" y="50">Dashed: fewer than {min_n} votes. Rows: largest difference '
            f'between groups first.</text>'
            f'<text class="t2 small" x="0" y="66">Spread counts groups with at least {SPREAD_MIN} votes; it is '
            f'descriptive, not a test.</text>']
    for j, g in enumerate(names):
        cx = label_w + j * cell_w + cell_w / 2
        body.append(f'<rect class="{_cls(j)}" x="{cx - 34}" y="{top - 22}" width="10" height="10" rx="2"/>'
                    f'<text class="t2 small" x="{cx - 20}" y="{top - 13}">Group {escape(g)} · {groups[g]["members"]}</text>')
    for i, s in enumerate(rows):
        y = top + i * cell_h
        body.append(f'<text class="t2 small" x="{label_w - 8}" y="{y + 17}" text-anchor="end">#{s.id}</text>')
        for j, g in enumerate(names):
            x = label_w + j * cell_w
            c = groups[g]['statements'].get(s.id)
            n = (c['agree'] + c['disagree']) if c else 0
            tip = f'#{s.id} · group {g}: ' + (f"{c['agree']} agree, {c['disagree']} disagree, {c['pass']} pass" if c else 'no votes')
            if n < min_n:
                body.append(f'<rect class="s" x="{x + 1}" y="{y + 1}" width="{cell_w - 2}" height="{cell_h - 2}" rx="3" '
                            f'style="stroke:#c9c7c0;stroke-dasharray:2 3"><title>{escape(tip)} — {escape(s.text[:120])}</title></rect>'
                            f'<text class="mu small" x="{x + cell_w / 2}" y="{y + 17}" text-anchor="middle">n={n}</text>')
                continue
            share = c['agree'] / n
            cls, op = _cell_fill(share)
            body.append(f'<rect class="{cls}" x="{x + 1}" y="{y + 1}" width="{cell_w - 2}" height="{cell_h - 2}" rx="3" '
                        f'fill-opacity="{op:.2f}"><title>{escape(tip)} — {escape(s.text[:120])}</title></rect>'
                        f'<text class="t1 small" x="{x + cell_w / 2}" y="{y + 17}" text-anchor="middle">'
                        f'{100 * share:.0f}% <tspan class="t2">n={n}</tspan></text>')
        sp = spread(groups, s.id, SPREAD_MIN)
        body.append(f'<text class="mu small" x="{label_w + cell_w * len(names) + 8}" y="{y + 17}">'
                    f'{"spread " + format(sp * 100, ".0f") + " pts" if sp is not None else "—"}</text>')
    return _svg(width, height, group_style() + ''.join(body), title)


# ── participant map ────────────────────────────────────────────────────────────────────────

def map_cutoff(export: Export, min_votes: int = MAP_MIN_VOTES) -> int:
    """Opinion votes needed to be placed: ``min_votes``, capped at half the opinion statements."""
    n = sum(1 for s in export.statements.values() if s.moderated != -1 and not s.is_meta)
    return min(min_votes, max(2, n // 2))


def project(export: Export, min_votes: int = MAP_MIN_VOTES, iterations: int = 200) -> dict[int, tuple[float, float]]:
    """Two-component PCA of the participant × statement vote matrix (stdlib only).

    Rows: participants with at least ``min_votes`` current votes (Polis's own cut-off is 7; for a
    conversation with few statements it is capped at half of them). Columns: opinion statements only,
    i.e. not rejected and not meta (meta statements are demographics; Polis leaves them out too).
    A missing vote takes the column mean of the observed votes, then columns are centred. Top two
    components by power iteration with deflation (seeded, so the result is reproducible).
    """
    sids = sorted(s.id for s in export.statements.values() if s.moderated != -1 and not s.is_meta)
    col = {sid: i for i, sid in enumerate(sids)}
    by_voter: dict[int, dict[int, int]] = {}
    for (voter, sid), v in export.votes.items():
        if sid in col:
            by_voter.setdefault(voter, {})[sid] = v.value
    cutoff = map_cutoff(export, min_votes)
    voters = sorted(p for p, vs in by_voter.items() if len(vs) >= cutoff)
    if len(voters) < 3 or len(sids) < 2:
        return {}
    means = []
    for sid in sids:
        seen = [by_voter[p][sid] for p in voters if sid in by_voter[p]]
        means.append(sum(seen) / len(seen) if seen else 0.0)
    X = [[(by_voter[p].get(sid, means[j]) - means[j]) for j, sid in enumerate(sids)] for p in voters]

    rng = random.Random(0)
    comps = []
    for _ in range(2):
        v = [rng.uniform(-1, 1) for _ in sids]
        for _ in range(iterations):
            xv = [sum(a * b for a, b in zip(row, v)) for row in X]           # X v
            w = [sum(X[i][j] * xv[i] for i in range(len(X))) for j in range(len(sids))]   # Xᵀ X v
            for c in comps:                                                    # deflate
                d = sum(a * b for a, b in zip(w, c))
                w = [a - d * b for a, b in zip(w, c)]
            norm = math.sqrt(sum(a * a for a in w)) or 1.0
            v = [a / norm for a in w]
        comps.append(v)
    # Like Polis, scale each participant by sqrt(statements / own votes), so that people who
    # voted on few statements are not pulled towards the centre by the imputed zeros.
    out = {}
    for p, row in zip(voters, X):
        scale = math.sqrt(len(sids) / len(by_voter[p]))
        out[p] = (scale * sum(a * b for a, b in zip(row, comps[0])),
                  scale * sum(a * b for a, b in zip(row, comps[1])))
    return out


def participant_map(points: dict[int, tuple[float, float]], groups: dict[int, int | None],
                    group_order: list[str], source: str, title: str = 'Participants by opinion group',
                    cutoff: int = MAP_MIN_VOTES) -> str:
    size, pad, top = 440, 28, 98
    grouped = sum(1 for g in groups.values() if g is not None)
    placed = sum(1 for p in points if groups.get(p) is not None)
    width, height = size + 2 * pad + 180, size + top + pad
    body = [f'<text class="t1" x="0" y="16" style="font-weight:600">{escape(title)}</text>',
            f'<text class="t2 small" x="0" y="34">Our own 2-component PCA of the vote matrix; position is '
            f'not Polis’s map.</text>'
            f'<text class="t2 small" x="0" y="50">Colour: {escape(source)}.</text>'
            f'<text class="t2 small" x="0" y="66">Dots are nudged slightly so that participants who voted '
            f'identically do not hide each other.</text>'
            f'<text class="t2 small" x="0" y="82">Placed: {placed} of {grouped} participants with a group '
            f'(those with at least {cutoff} opinion votes; Polis uses its own rule).</text>']
    if not points:
        return _svg(width, height, ''.join(body) + f'<text class="t2" x="{pad}" y="{top + 20}">Too few participants to project.</text>', title)
    xs, ys = [p[0] for p in points.values()], [p[1] for p in points.values()]
    span = max(max(xs) - min(xs), max(ys) - min(ys)) or 1.0
    cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
    sx = lambda x: pad + size / 2 + (x - cx) / span * (size - 16)          # noqa: E731 — equal scale on both axes
    sy = lambda y: top + size / 2 - (y - cy) / span * (size - 16)          # noqa: E731
    body.append(f'<rect class="s grid" x="{pad}" y="{top}" width="{size}" height="{size}"/>'
                f'<line class="grid" x1="{sx(0):.1f}" x2="{sx(0):.1f}" y1="{top}" y2="{top + size}"/>'
                f'<line class="grid" x1="{pad}" x2="{pad + size}" y1="{sy(0):.1f}" y2="{sy(0):.1f}"/>')
    index = {g: i for i, g in enumerate(group_order)}
    centroids: dict[str, list] = {}
    jitter = random.Random(1)                                # same nudge every run
    for p, (x, y) in sorted(points.items()):
        x += jitter.uniform(-0.02, 0.02) * span
        y += jitter.uniform(-0.02, 0.02) * span
        g = groups.get(p)
        gname = None if g is None else str(g)
        cls = 'gx' if gname not in index else _cls(index[gname])
        tip = f'participant {p} · ' + ('no group' if gname is None else f'group {gname}')
        ring = '' if cls == 'gx' else ' pt'
        body.append(f'<circle class="{cls}{ring}" cx="{sx(x):.1f}" cy="{sy(y):.1f}" r="4.5" fill-opacity="0.75" '
                    f'stroke-width="1.5"><title>{escape(tip)}</title></circle>')
        if gname in index:
            centroids.setdefault(gname, []).append((sx(x), sy(y)))
    for gname, pts in centroids.items():                                     # direct labels
        mx, my = sum(a for a, _ in pts) / len(pts), sum(b for _, b in pts) / len(pts)
        body.append(f'<text class="t1 small halo" x="{mx:.1f}" y="{my - 10:.1f}" text-anchor="middle" '
                    f'style="font-weight:600;paint-order:stroke;stroke-width:3px">Group {escape(gname)}</text>')
    lx = pad + size + 16
    for i, gname in enumerate(group_order):
        n = sum(1 for p in points if str(groups.get(p)) == gname)
        body.append(f'<circle class="{_cls(i)}" cx="{lx + 5}" cy="{top + 10 + i * 20}" r="5"/>'
                    f'<text class="t2 small" x="{lx + 16}" y="{top + 14 + i * 20}">Group {escape(gname)} · {n}</text>')
    ungrouped = sum(1 for p in points if groups.get(p) is None)
    k = len(group_order)
    if k > MAX_GROUPS:                                      # colours are never reused; say so
        body.append(f'<text class="mu small" x="{lx}" y="{top + 14 + (k + 1) * 20}">Groups after the '
                    f'{MAX_GROUPS}th share the grey outline.</text>')
    if ungrouped:
        body.append(f'<circle class="gx" cx="{lx + 5}" cy="{top + 10 + k * 20}" r="4.5" stroke-width="1.5"/>'
                    f'<text class="t2 small" x="{lx + 16}" y="{top + 14 + k * 20}">no group · {ungrouped}</text>')
    return _svg(width, height, group_style() + ''.join(body), title)

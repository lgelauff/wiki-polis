"""Self-contained SVG charts (no plotting library). Each SVG carries its own light/dark style.

Colours: agree = blue, disagree = red (a validated diverging pair, light and dark), pass = the
neutral grey midpoint. The grey is below 3:1 against the light surface, so every chart has a
legend, hover titles on every mark, and the report repeats every number in a table.
"""

from __future__ import annotations

from html import escape

STYLE = """<style>
.s{fill:#fcfcfb}.ag{fill:#2a78d6}.di{fill:#e34948}.pa{fill:#c9c7c0}.bar{fill:#2a78d6}
.t1{fill:#0b0b0b}.t2{fill:#52514e}.mu{fill:#6b6a66}.grid{stroke:#e1e0d9;stroke-width:1}
text{font:12px system-ui,-apple-system,Segoe UI,sans-serif}.small{font-size:11px}
@media (prefers-color-scheme:dark){.s{fill:#1a1a19}.ag{fill:#3987e5}.di{fill:#e66767}
.pa{fill:#5c5b57}.bar{fill:#3987e5}.t1{fill:#fff}.t2{fill:#c3c2b7}.mu{fill:#9a9891}.grid{stroke:#2c2c2a}}
</style>"""


def _svg(width: int, height: int, body: str, title: str) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
            f'width="{width}" height="{height}" role="img" aria-label="{escape(title)}">'
            f'<title>{escape(title)}</title>{STYLE}<rect class="s" width="{width}" height="{height}"/>{body}</svg>')


def _legend(x: int, y: int) -> str:
    out = []
    for i, (cls, label) in enumerate((('ag', 'Agree'), ('pa', 'Pass'), ('di', 'Disagree'))):
        cx = x + i * 92
        out.append(f'<rect class="{cls}" x="{cx}" y="{y - 9}" width="12" height="12" rx="2"/>'
                   f'<text class="t2" x="{cx + 18}" y="{y + 1}">{label}</text>')
    return ''.join(out)


def _bar_path(x: float, y: float, w: float, h: float, left: bool, right: bool, r: float = 4) -> str:
    """A rectangle with rounded corners only on the ends that are the ends of the whole bar."""
    r = min(r, w / 2, h / 2)
    rl, rr = (r if left else 0), (r if right else 0)
    return (f'M{x + rl:.1f},{y:.1f}H{x + w - rr:.1f}' + (f'A{rr},{rr} 0 0 1 {x + w:.1f},{y + rr:.1f}' if rr else '')
            + f'V{y + h - rr:.1f}' + (f'A{rr},{rr} 0 0 1 {x + w - rr:.1f},{y + h:.1f}' if rr else '')
            + f'H{x + rl:.1f}' + (f'A{rl},{rl} 0 0 1 {x:.1f},{y + h - rl:.1f}' if rl else '')
            + f'V{y + rl:.1f}' + (f'A{rl},{rl} 0 0 1 {x + rl:.1f},{y:.1f}' if rl else '') + 'Z')


def statement_bars(statements, title: str = 'Votes per statement', min_votes: int = 0) -> str:
    """100% stacked bars, one per statement, sorted by agree share of all votes (highest first).

    Statements with fewer than ``min_votes`` agree + disagree votes go last and say so, so a
    100% from four votes never heads the chart.
    """
    rows = sorted((s for s in statements if s.votes),
                  key=lambda s: (s.decided < min_votes, -(s.agree / s.votes), s.id))
    label_w, bar_w, row_h, bar_h, top = 64, 560, 20, 14, 44
    width, height = label_w + bar_w + 170, top + row_h * max(len(rows), 1) + 16
    body = [f'<text class="t1" x="0" y="16" style="font-weight:600">{escape(title)}</text>', _legend(label_w, 34)]
    for i, s in enumerate(rows):
        y = top + i * row_h
        x = float(label_w)
        parts = [(c, n, lbl) for c, n, lbl in (('ag', s.agree, 'agree'), ('pa', s.passes, 'pass'), ('di', s.disagree, 'disagree')) if n]
        for j, (cls, n, lbl) in enumerate(parts):
            w = bar_w * n / s.votes
            gap = 2 if j < len(parts) - 1 else 0          # 2px surface gap between segments
            tip = f'#{s.id}: {n} {lbl} of {s.votes} votes ({100 * n / s.votes:.0f}%) — {s.text[:160]}'
            body.append(f'<path class="{cls}" d="{_bar_path(x, y, max(w - gap, 0.5), bar_h, j == 0, j == len(parts) - 1)}">'
                        f'<title>{escape(tip)}</title></path>')
            x += w
        body.append(f'<text class="t2 small" x="{label_w - 8}" y="{y + 11}" text-anchor="end">#{s.id}</text>'
                    f'<text class="mu small" x="{label_w + bar_w + 8}" y="{y + 11}">'
                    f'{100 * s.agree / s.votes:.0f}% · n={s.votes}{" · few votes" if s.decided < min_votes else ""}</text>')
    if not rows:
        body.append(f'<text class="t2" x="{label_w}" y="{top + 12}">No votes.</text>')
    return _svg(width, height, ''.join(body), title)


def _columns(values: list[tuple[str, int]], title: str, x_label: str, y_label: str) -> str:
    """Vertical bars for one series; labels on the first and last bar and the maximum."""
    left, top, plot_w, plot_h = 48, 48, 640, 200
    width, height = left + plot_w + 16, top + plot_h + 48
    body = [f'<text class="t1" x="0" y="16" style="font-weight:600">{escape(title)}</text>']
    if not values:
        return _svg(width, height, ''.join(body) + f'<text class="t2" x="{left}" y="{top + 20}">No data.</text>', title)
    peak = max(n for _, n in values) or 1
    for k in range(5):                                     # recessive gridlines
        gy = top + plot_h - plot_h * k / 4
        body.append(f'<line class="grid" x1="{left}" x2="{left + plot_w}" y1="{gy:.1f}" y2="{gy:.1f}"/>'
                    f'<text class="mu small" x="{left - 6}" y="{gy + 4:.1f}" text-anchor="end">{round(peak * k / 4)}</text>')
    step = plot_w / len(values)
    w = max(min(step - 2, 40), 1)
    for i, (label, n) in enumerate(values):
        if n == 0:                                         # an empty bin is a gap, not a sliver
            continue
        h = plot_h * n / peak
        x = left + i * step + (step - w) / 2
        y = top + plot_h - h
        body.append(f'<path class="bar" d="{_bar_path(x, y, w, max(h, 0.5), True, True) if h >= 8 else f"M{x:.1f},{y:.1f}h{w:.1f}v{max(h, 0.5):.1f}h{-w:.1f}Z"}">'
                    f'<title>{escape(f"{x_label} {label}: {n}")}</title></path>')
    ticks = {0, len(values) - 1}
    peak_i = max(range(len(values)), key=lambda i: values[i][1])
    if all(abs(peak_i - i) * step >= 48 for i in ticks):   # label the tallest bar unless it would collide
        ticks.add(peak_i)
    for i in sorted(ticks):
        body.append(f'<text class="mu small" x="{left + i * step + step / 2:.1f}" y="{top + plot_h + 16}" '
                    f'text-anchor="middle">{escape(values[i][0])}</text>')
    body.append(f'<text class="t2 small" x="{left + plot_w / 2}" y="{height - 6}" text-anchor="middle">{escape(x_label)}</text>'
                f'<text class="t2 small" x="0" y="{top - 8}">{escape(y_label)}</text>')
    return _svg(width, height, ''.join(body), title)


def votes_per_participant(counts: list[int]) -> str:
    """Histogram of how many statements each participant voted on (current votes)."""
    if not counts:
        return _columns([], 'Votes per participant (all statements)', 'votes', 'participants')
    top = max(counts)
    size = max(1, -(-top // 30))                           # at most ~30 bins
    bins = [0] * (top // size + 1)
    for c in counts:
        bins[c // size] += 1
    labels = [(f'{i * size}' if size == 1 else f'{i * size}–{i * size + size - 1}', n) for i, n in enumerate(bins)]
    return _columns(labels, 'Votes per participant (all statements)', 'votes cast', 'participants')


def votes_per_day(days: list[tuple[str, int]]) -> str:
    return _columns(days, 'Votes per day (all vote rows, re-votes included)', 'day (UTC)', 'votes')

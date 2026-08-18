"""Figures and the standalone HTML report.

Palette is the validated default from the dataviz reference instance: categorical
slots 1 and 2 (blue `#2a78d6`, orange `#eb6834`), which clear every check on the
all-pairs list — worst CVD ΔE 24.7, worst normal-vision ΔE 33.6. Two opinion groups
is the only categorical need here; nothing cycles.

Agreement percentages use a diverging encoding (the same two hues either side of a
neutral grey midpoint) because agree-vs-disagree is polarity, not magnitude. The
co-assignment heatmap uses a single-hue sequential ramp because it is magnitude.

Identity is never carried by colour alone: every figure with two series carries a
legend, and the group marks are also distinguished by shape.
"""
from __future__ import annotations

import difflib
import html
import io
import re as _re
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.lines import Line2D

from pipeline import (POLIS_VOTE_THRESHOLD, RAW_AGREE, RAW_DISAGREE,
                      auto_agree_votes)

#: People who voted decisively on BOTH wordings before a diff gets a comparison
#: rather than 'not enough people'. Matches the engine's own participation cutoff.
MIN_COMPARABLE = POLIS_VOTE_THRESHOLD

#: Similarity above which two versions inside one family are near-identical to each
#: other. Higher than the threshold that forms the families themselves: this flags
#: parallel effort — two people separately narrowing the same statement the same
#: way — rather than mere relatedness.
NEAR_IDENTICAL = 0.95

SURFACE = '#fcfcfb'
INK = '#0b0b0b'
INK_SOFT = '#52514e'
INK_MUTED = '#8a8880'
GRID = '#e5e4e0'
SERIES = ['#2a78d6', '#eb6834']          # categorical slots 1, 2
MARKERS = ['o', 's']                      # secondary encoding, so never colour-alone
NEUTRAL = '#b8b6ae'
SEQUENTIAL = LinearSegmentedColormap.from_list('wp_seq', ['#fcfcfb', '#2a78d6'])

plt.rcParams.update({
    'figure.facecolor': SURFACE, 'axes.facecolor': SURFACE,
    'savefig.facecolor': SURFACE,
    'text.color': INK, 'axes.labelcolor': INK_SOFT,
    'xtick.color': INK_SOFT, 'ytick.color': INK_SOFT,
    'axes.edgecolor': GRID, 'grid.color': GRID, 'grid.linewidth': 0.8,
    'font.size': 10, 'axes.titlesize': 12, 'axes.titleweight': 'normal',
    'axes.spines.top': False, 'axes.spines.right': False,
    'figure.dpi': 110,
})


def _finish(ax, title: str, subtitle: str = '') -> None:
    ax.set_title(title, loc='left', pad=18 if subtitle else 10, color=INK)
    if subtitle:
        ax.text(0, 1.02, subtitle, transform=ax.transAxes, fontsize=9,
                color=INK_SOFT, va='bottom')


# ── figures ──────────────────────────────────────────────────────────────────

def plot_funnel(funnel: pd.DataFrame):
    """Descending bars. One series, so no legend — the title names it."""
    data = funnel.iloc[::-1]
    fig, ax = plt.subplots(figsize=(8, 0.5 * len(data) + 1.6))
    bars = ax.barh(data['step'], data['n_people'], height=0.62,
                   color=SERIES[0], zorder=3)
    # 4px rounded data-ends would need a patch path; a flat end plus a direct label
    # reads cleanly at this size.
    for bar, n in zip(bars, data['n_people']):
        ax.text(bar.get_width() + max(data['n_people']) * 0.015,
                bar.get_y() + bar.get_height() / 2, f'{n:,}',
                va='center', fontsize=9, color=INK)
    ax.set_xlim(0, max(data['n_people']) * 1.12)
    ax.xaxis.set_visible(False)
    ax.grid(False)
    for spine in ax.spines.values():
        spine.set_visible(False)
    _finish(ax, 'How many people reached each step',
            'the results page reports the "voted on ≥1" row')
    fig.tight_layout()
    return fig


def plot_opinion_map(b, conv_key: str, server: dict):
    """Polis's own projection — base-cluster coordinates from math_main, not a
    recomputation. Point area is proportional to how many participants sit in that
    base cluster."""
    payload = b.math.get((conv_key, 2))
    if payload is None or not server.get('available'):
        return None
    base = payload['data'].get('base-clusters')
    groups = payload['data'].get('group-clusters')
    if not base or not groups:
        return None
    # Real math_main carries projected coordinates on the base clusters; a partial
    # capture may not. Without them there is no map to draw.
    if not all(k in base for k in ('x', 'y', 'id')):
        return None

    ids = base['id']
    xs, ys, counts = base['x'], base['y'], base.get('count', [1] * len(ids))
    group_of = {int(bid): gi for gi, g in enumerate(groups) for bid in g['members']}

    fig, ax = plt.subplots(figsize=(7, 5.4))
    for gi in sorted(set(group_of.values())):
        idx = [i for i, bid in enumerate(ids) if group_of.get(int(bid)) == gi]
        if not idx:
            continue
        ax.scatter([xs[i] for i in idx], [ys[i] for i in idx],
                   s=[28 + 26 * counts[i] for i in idx],
                   c=SERIES[gi % len(SERIES)], marker=MARKERS[gi % len(MARKERS)],
                   edgecolors=SURFACE, linewidths=2, alpha=0.9, zorder=3,
                   label=f'group {gi + 1}')
    ax.axhline(0, color=GRID, lw=0.8, zorder=1)
    ax.axvline(0, color=GRID, lw=0.8, zorder=1)
    ax.set_xticks([]); ax.set_yticks([])
    # The legend used to sit unframed inside the axes, at marker sizes inherited from
    # the scatter — so it read as more data points rather than as a key. Fixed-size
    # proxy handles, its own surface, and a position outside the plotting area keep
    # the two apart: the map is only marks, the key is only key.
    keys = [Line2D([], [], linestyle='none', markersize=9,
                   marker=MARKERS[gi % len(MARKERS)],
                   markerfacecolor=SERIES[gi % len(SERIES)],
                   markeredgecolor=SURFACE, markeredgewidth=1.5,
                   label=f'group {gi + 1}')
            for gi in sorted(set(group_of.values()))]
    legend = ax.legend(handles=keys, loc='upper left', bbox_to_anchor=(1.015, 1.0),
                       frameon=True, facecolor=SURFACE, edgecolor=GRID,
                       framealpha=1.0, borderpad=0.75, labelspacing=0.7,
                       handletextpad=0.7, fontsize=9.5)
    legend.get_frame().set_linewidth(1.0)
    for text in legend.get_texts():
        text.set_color(INK)
    _finish(ax, 'The opinion map Polis computed',
            'each mark is a cluster of participants; larger means more people')
    fig.tight_layout()
    return fig


def plot_stability_heatmap(stability: dict, server: dict):
    """Sequential single hue: how often each pair landed in the same community."""
    if not stability.get('available'):
        return None
    matrix = stability['co_assignment'].copy()
    labels = server.get('labels', {}) if server.get('available') else {}
    order = sorted(matrix.index, key=lambda pid: (labels.get(pid, 99), pid))
    matrix = matrix.loc[order, order]

    fig, ax = plt.subplots(figsize=(6.4, 5.6))
    im = ax.imshow(matrix.values, cmap=SEQUENTIAL, vmin=0, vmax=1, interpolation='nearest')
    ax.set_xticks([]); ax.set_yticks([])
    ax.grid(False)

    # Mark where the server's groups divide, so the blocks can be read against them.
    if labels:
        boundary = 0
        previous = labels.get(order[0], 99)
        for i, pid in enumerate(order):
            if labels.get(pid, 99) != previous:
                boundary = i
                previous = labels.get(pid, 99)
                ax.axhline(boundary - 0.5, color=INK, lw=1.1)
                ax.axvline(boundary - 0.5, color=INK, lw=1.1)

    bar = fig.colorbar(im, ax=ax, fraction=0.042, pad=0.03)
    bar.set_label('share of runs in the same community', fontsize=9, color=INK_SOFT)
    bar.outline.set_visible(False)
    _finish(ax, 'Do the same people keep grouping together?',
            f'{stability["n_runs"]} runs; black lines mark the groups Polis reported')
    fig.tight_layout()
    return fig


def plot_agreement_matrix(b, conv_key: str, server: dict, phase: int = 2):
    """Every participant against every other, shaded by how often they voted alike.

    This is what "a group" means, drawn rather than asserted: people are ordered by
    the group they were assigned to, so if the grouping reflects something real the
    squares along the diagonal are darker than the rest. If the whole square looks
    uniform, the groups are a cut through a gradient rather than two camps — and the
    reader can see that instead of taking a statistic on trust.

    Agreement counts only statements both people voted on decisively; passes are
    excluded, since skipping is not agreeing.
    """
    import methods as _m
    from pipeline import POLIS_VOTE_THRESHOLD, build_matrix, real_vote_counts

    if not server.get('available'):
        return None
    matrix = build_matrix(b, conv_key, phase)
    counts = real_vote_counts(b, conv_key, phase)
    eligible = [p for p in matrix.pids if counts.get(p, 0) >= POLIS_VOTE_THRESHOLD]
    if len(eligible) < 3:
        return None
    pids, weights, _ = _m.agreement_graph(matrix, restrict_pids=eligible)

    labels = server['labels']
    order = sorted(range(len(pids)), key=lambda i: (labels.get(pids[i], 99), pids[i]))
    shown = weights[np.ix_(order, order)].copy()
    np.fill_diagonal(shown, 1.0)

    fig, ax = plt.subplots(figsize=(6.2, 5.4))
    im = ax.imshow(shown, cmap=SEQUENTIAL, vmin=0, vmax=1, interpolation='nearest')
    ax.set_xticks([]); ax.set_yticks([])
    ax.grid(False)

    previous = labels.get(pids[order[0]], 99)
    for position, i in enumerate(order):
        current = labels.get(pids[i], 99)
        if current != previous:
            ax.axhline(position - 0.5, color=INK, lw=1.1)
            ax.axvline(position - 0.5, color=INK, lw=1.1)
            previous = current

    bar = fig.colorbar(im, ax=ax, fraction=0.042, pad=0.03)
    bar.set_label('how often the two agreed', fontsize=9, color=INK_SOFT)
    bar.outline.set_visible(False)
    _finish(ax, 'Who agrees with whom',
            'people ordered by their group; black lines mark the boundaries')
    fig.tight_layout()
    return fig


def statement_divergence(b, conv_key: str, server: dict, phase: int = 2) -> pd.DataFrame:
    """Per statement, the agreement rate inside each opinion group.

    Agreement is over *decided* votes (agree or disagree); passes are excluded from
    the denominator, so a much-passed statement is not made to look contested.
    """
    votes = b.phase('votes_latest', conv_key, phase)
    statements = b.phase('statements', conv_key, phase).set_index('tid')
    if not server.get('available'):
        return pd.DataFrame()

    participants = b.phase('participants', conv_key, phase)
    key_by_pid = dict(zip(participants['pid'], participants['person_key']))
    group_by_key = {key_by_pid[pid]: lab for pid, lab in server['labels'].items()
                    if pid in key_by_pid}
    votes = votes.assign(opinion_group=votes['person_key'].map(group_by_key))
    votes = votes[votes['opinion_group'].notna()]

    rows = []
    for tid, block in votes.groupby('tid'):
        # Overall agreement, ignoring the grouping entirely. This is the quantity that
        # survives the finding that the grouping is indistinguishable from noise, so it
        # is what the selection tables rank on; the per-group split is context.
        all_decided = int(((block['vote'] == RAW_AGREE) |
                           (block['vote'] == RAW_DISAGREE)).sum())
        overall = ((block['vote'] == RAW_AGREE).sum() / all_decided * 100
                   if all_decided else np.nan)
        row = {'tid': tid, 'statement': statements['txt'].get(tid, ''),
               'n_voters': len(block), 'n_decided': all_decided,
               'agree_pct': round(overall, 1) if overall == overall else np.nan}
        rates = {}
        for gid, sub in block.groupby('opinion_group'):
            decided = int(((sub['vote'] == RAW_AGREE) | (sub['vote'] == RAW_DISAGREE)).sum())
            rate = (sub['vote'] == RAW_AGREE).sum() / decided * 100 if decided else np.nan
            rates[int(gid)] = rate
            row[f'agree_group{int(gid) + 1}'] = round(rate, 1) if rate == rate else np.nan
            row[f'n_group{int(gid) + 1}'] = len(sub)
            # The page tells the reader to "check the number of voters beside it", and
            # the number that matters is how many in that group took a side — a 100%
            # resting on two votes is the whole problem with the small group.
            row[f'decided_group{int(gid) + 1}'] = decided
        valid = [r for r in rates.values() if r == r]
        row['gap'] = round(max(valid) - min(valid), 1) if len(valid) > 1 else np.nan
        rows.append(row)

    out = pd.DataFrame(rows)
    return out.sort_values('gap', ascending=False, na_position='last').reset_index(drop=True)


def plot_divergence(divergence: pd.DataFrame, top: int = 16):
    """A dumbbell per statement: where each group sits, and how far apart they are."""
    cols = [c for c in divergence.columns if c.startswith('agree_group')]
    if len(cols) < 2 or divergence.empty:
        return None
    data = divergence.dropna(subset=['gap']).head(top).iloc[::-1]
    if data.empty:
        return None

    fig, ax = plt.subplots(figsize=(9.5, 0.42 * len(data) + 1.8))
    y = np.arange(len(data))
    a, bb = data[cols[0]].values, data[cols[1]].values
    ax.hlines(y, np.minimum(a, bb), np.maximum(a, bb), color=NEUTRAL, lw=2, zorder=2)
    ax.scatter(a, y, s=64, c=SERIES[0], marker=MARKERS[0], edgecolors=SURFACE,
               linewidths=2, zorder=3, label='group 1')
    ax.scatter(bb, y, s=64, c=SERIES[1], marker=MARKERS[1], edgecolors=SURFACE,
               linewidths=2, zorder=3, label='group 2')

    ax.set_yticks(y)
    ax.set_yticklabels([(t[:78] + '…') if len(t) > 78 else t for t in data['statement']],
                       fontsize=8.5)
    ax.set_xlim(-2, 102)
    ax.set_xlabel('agreed, as a share of those who took a side (%)')
    ax.xaxis.grid(True, zorder=1)
    ax.legend(frameon=False, ncol=2, fontsize=9, loc='lower right')
    _finish(ax, 'Where the groups split', 'widest disagreements first')
    fig.tight_layout()
    return fig


def plot_similarity_distribution(pairs: pd.DataFrame, threshold: float = 0.85):
    """Is the near-duplicate threshold cutting a real gap, or an arbitrary point?"""
    if pairs.empty:
        return None
    fig, ax = plt.subplots(figsize=(8, 3.4))
    ax.hist(pairs['similarity'], bins=48, color=SERIES[0], zorder=3)
    ax.axvline(threshold, color=SERIES[1], lw=2, zorder=4)
    ax.text(threshold, ax.get_ylim()[1] * 0.94, f'  threshold {threshold}',
            color=SERIES[1], fontsize=9, va='top')
    ax.set_xlabel('similarity between two statements')
    ax.set_ylabel('pairs')
    ax.yaxis.grid(True, zorder=1)
    _finish(ax, 'How similar are the statements to each other?',
            'a clear gap to the right of the threshold means it is cutting a real join')
    fig.tight_layout()
    return fig


#: Every statistical term the reports use, linked to its Wikipedia article. A reader
#: who meets "modularity" or "silhouette" for the first time should not have to take
#: the number on faith, and a footnote they cannot follow is no better than none.
GLOSSARY = {
    'k-means': 'https://en.wikipedia.org/wiki/K-means_clustering',
    'Leiden': 'https://en.wikipedia.org/wiki/Leiden_algorithm',
    'modularity': 'https://en.wikipedia.org/wiki/Modularity_(networks)',
    'silhouette': 'https://en.wikipedia.org/wiki/Silhouette_(clustering)',
    'adjusted Rand index': 'https://en.wikipedia.org/wiki/Rand_index#Adjusted_Rand_index',
    'principal component analysis':
        'https://en.wikipedia.org/wiki/Principal_component_analysis',
    'cosine similarity': 'https://en.wikipedia.org/wiki/Cosine_similarity',
    'multiple comparisons': 'https://en.wikipedia.org/wiki/Multiple_comparisons_problem',
    'false discovery rate': 'https://en.wikipedia.org/wiki/False_discovery_rate',
    'multilayer network': 'https://en.wikipedia.org/wiki/Multidimensional_network',
    'p-value': 'https://en.wikipedia.org/wiki/P-value',
    'permutation test': 'https://en.wikipedia.org/wiki/Permutation_test',
    'outlier': 'https://en.wikipedia.org/wiki/Outlier',
}


def term(name: str, shown: str | None = None) -> str:
    """Link a statistical term to its Wikipedia article."""
    url = GLOSSARY.get(name)
    label = shown or name
    return (f'<a class="term" href="{url}" target="_blank" rel="noopener">{label}</a>'
            if url else label)


def _family_summary(results, decisive, comparable) -> str:
    """One phrase describing what a family is worth reading for."""
    gained = [c for c in results if c['improved']]
    if gained:
        return (f'{len(gained)} rewrite{"" if len(gained) == 1 else "s"} gained support'
                + (f', {len(decisive) - len(gained)} lost it'
                   if len(decisive) > len(gained) else ''))
    if decisive:
        return f'{len(decisive)} rewrite{"" if len(decisive) == 1 else "s"} lost support'
    if comparable:
        return f'{len(comparable)} compared, no clear difference'
    return 'nothing comparable'


def word_diff(old: str, new: str) -> str:
    """Wikipedia-style inline word diff of two statements.

    Word-level rather than character-level, because these are rewrites of prose and
    a character diff of Dutch compounds is unreadable. Removals and additions carry
    strikethrough and underline as well as colour, so the diff survives greyscale
    printing and colour-blind reading.
    """
    tokens = lambda t: _re.findall(r'\s+|\w+|[^\w\s]', t or '')
    a, b = tokens(old), tokens(new)
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b).get_opcodes():
        if op == 'equal':
            out.append(html.escape(''.join(a[i1:i2])))
        else:
            if op in ('replace', 'delete'):
                gone = ''.join(a[i1:i2])
                if gone.strip():
                    out.append(f'<del>{html.escape(gone)}</del>')
            if op in ('replace', 'insert'):
                added = ''.join(b[j1:j2])
                if added.strip():
                    out.append(f'<ins>{html.escape(added)}</ins>')
    return ''.join(out)


# ── HTML report ──────────────────────────────────────────────────────────────

def _with_contents(document: str) -> str:
    """Give every section an anchor and put a contents list above the first one.

    Done on the finished document rather than at each `parts.append` so that adding a
    section anywhere cannot forget to register itself — the list is derived, never
    maintained. Headings that already carry an id keep it, so existing links (#by-chance)
    stay valid.
    """
    used: set[str] = set()

    def slug(text: str) -> str:
        base = _re.sub(r'[^a-z0-9]+', '-',
                       html.unescape(_re.sub(r'<[^>]+>', '', text)).lower()).strip('-')
        base = base[:48] or 'section'
        candidate, n = base, 2
        while candidate in used:
            candidate, n = f'{base}-{n}', n + 1
        used.add(candidate)
        return candidate

    entries: list[tuple[int, str, str]] = []

    def register(match):
        level, attrs, text = int(match.group(1)), match.group(2), match.group(3)
        existing = _re.search(r'id="([^"]+)"', attrs or '')
        anchor = existing.group(1) if existing else slug(text)
        if existing:
            used.add(anchor)
        entries.append((level, anchor, text))
        return (f'<h{level}{attrs} id="{anchor}">{text}</h{level}>' if not existing
                else match.group(0))

    document = _re.sub(r'<h([23])([^>]*)>(.*?)</h\1>', register, document, flags=_re.S)
    if len(entries) < 3:
        return document

    items = []
    depth = 2
    for level, anchor, text in entries:
        label = html.unescape(_re.sub(r'<[^>]+>', '', text)).strip()
        if level == 3 and depth == 2:
            items.append('<ol>')
        elif level == 2 and depth == 3:
            items.append('</ol>')
        depth = level
        items.append(f'<li><a href="#{anchor}">{html.escape(label)}</a></li>')
    if depth == 3:
        items.append('</ol>')
    toc = ('<nav class="toc"><b>On this page</b><ol>' + ''.join(items) + '</ol></nav>')

    first = _re.search(r'<h2', document)
    return document[:first.start()] + toc + document[first.start():] if first else document


def _svg(fig) -> str:
    if fig is None:
        return '<p class="missing">Not available for this consultation.</p>'
    buf = io.StringIO()
    fig.savefig(buf, format='svg', bbox_inches='tight')
    plt.close(fig)
    svg = buf.getvalue()
    return svg[svg.index('<svg'):]


def _table(df: pd.DataFrame, max_rows: int = 40) -> str:
    if df is None or (hasattr(df, 'empty') and df.empty):
        return '<p class="missing">Nothing to show.</p>'
    return df.head(max_rows).to_html(index=False, border=0, na_rep='—',
                                     classes='data', justify='left')


CSS = """
:root { --surface:#fcfcfb; --ink:#0b0b0b; --soft:#52514e; --muted:#8a8880;
        --rule:#e5e4e0; --g1:#2a78d6; --g2:#eb6834; --improved:#eef4ea;
        --quiet:#6e6c63; --good:#1b7f4d; }
* { box-sizing:border-box; }
body { margin:0; background:var(--surface); color:var(--ink);
       font:16px/1.62 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,sans-serif; }
main { max-width:860px; margin:0 auto; padding:56px 24px 96px; }
h1 { font-size:2rem; line-height:1.22; margin:0 0 .3em; letter-spacing:-.01em; }
h2 { font-size:1.32rem; margin:2.8em 0 .6em; padding-top:1.4em; border-top:1px solid var(--rule); }
h3 { font-size:1.05rem; margin:2em 0 .4em; }
p, li { color:#1c1c1a; }
.lede { font-size:1.09rem; color:var(--soft); margin-bottom:2.4em; }
figure { margin:1.8em 0; }
figure svg { max-width:100%; height:auto; display:block; }
.figwrap { overflow-x:auto; }
table.data { border-collapse:collapse; font-size:.87rem; width:100%; margin:1.2em 0; }
table.data th { text-align:left; font-weight:600; color:var(--soft);
                border-bottom:1.5px solid var(--rule); padding:7px 10px 7px 0; }
table.data td { border-bottom:1px solid var(--rule); padding:7px 10px 7px 0;
                vertical-align:top; }
.tablewrap { overflow-x:auto; }
.check { font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:.82rem;
         color:var(--soft); }
.check .ok { color:#1b7f4d; } .check .bad { color:#c0362c; font-weight:600; }
.missing { color:var(--quiet); font-style:italic; }
.footnote { font-size:.82rem; color:var(--quiet); border-left:2px solid var(--rule);
            padding-left:12px; max-width:64ch; }
.toc { border-top:1px solid var(--rule); border-bottom:1px solid var(--rule);
       padding:.9em 0; margin:2em 0; font-size:.88rem; }
.toc b { display:block; font-size:.78rem; letter-spacing:.06em; text-transform:uppercase;
         color:var(--quiet); margin-bottom:.5em; font-weight:600; }
.toc ol { list-style:none; margin:0; padding:0; }
.toc li { margin:.25em 0; }
.toc ol ol { margin:.15em 0 .4em 1.1em; }
.toc ol ol li { color:var(--quiet); font-size:.95em; }
.toc a { color:inherit; text-decoration:none; border-bottom:1px solid transparent; }
.toc a:hover { border-bottom-color:var(--quiet); }
figcaption { font-size:.82rem; color:var(--quiet); max-width:70ch; margin-top:.6em;
             line-height:1.5; }
.temporary { border:1px dashed var(--rule); border-left:3px solid var(--quiet);
             padding:.2em 1.1em 1em; margin:2.4em 0; }
.temporary h2 { margin-top:.8em; }
.tag { display:inline-block; vertical-align:middle; margin-left:.6em; padding:.15em .5em;
       border:1px solid var(--quiet); border-radius:3px; font-size:.6em;
       letter-spacing:.08em; text-transform:uppercase; color:var(--quiet);
       font-weight:600; }
a.term { color:inherit; text-decoration:underline dotted; text-underline-offset:3px;
         text-decoration-color:var(--quiet); }
a.term:hover { text-decoration-style:solid; color:var(--g1); }
.family { border-top:1px solid var(--rule); padding:.5em 0; }
.family > summary { cursor:pointer; font-size:.88rem; color:var(--soft); padding:.15em 0; }
.family > summary:hover { color:var(--ink); }
.family[open] > summary { margin-bottom:.35em; }
.diff { margin:.5em 0 .85em; padding-left:12px; border-left:2px solid var(--rule);
        font-size:.85rem; }
.diff .ids { font-size:.71rem; color:var(--quiet); font-family:ui-monospace,Menlo,monospace;
             margin-bottom:.3em; }
.diff p.text { margin:.15em 0 .3em; line-height:1.55; }
.diff del { text-decoration:line-through; color:#a8341f; background:#fbeae6;
            padding:0 2px; border-radius:2px; }
.diff ins { text-decoration:underline; color:#0f5f3f; background:#e4f2ea;
            padding:0 2px; border-radius:2px; }
.parallel { font-size:.78rem; color:var(--quiet); margin:.1em 0 .5em; }
.parallel > summary { cursor:pointer; color:var(--quiet); }
.parallel > summary:hover { color:var(--soft); }
.parallel p { margin:.25em 0 .4em 1.1em; color:var(--quiet); max-width:62ch; }
.famroot { color:var(--soft); font-size:.83rem; margin:.1em 0 .6em;
           padding-left:14px; border-left:3px solid var(--rule); }
.callout { background:var(--improved); border-left:3px solid var(--good);
           padding:.7em 14px; border-radius:0 5px 5px 0; }
.callout a { color:var(--good); font-weight:600; }
.callout .infam { color:var(--quiet); font-size:.86em; font-weight:400; }
.diff.improved { border-left:3px solid var(--good); background:var(--improved);
                 padding:.5em 12px .35em; border-radius:0 4px 4px 0; }
.diff .sim { float:right; font-size:.68rem; color:var(--quiet); }
.diff .verdictline { font-size:.76rem; color:var(--quiet); margin:.15em 0 0; }
.diff .badge { display:inline-block; margin-left:8px; padding:1px 7px; border-radius:9px;
               background:var(--good); color:#fff; font-size:.66rem; letter-spacing:.03em;
               text-transform:uppercase; vertical-align:1px; }
.diff .verdict { font-size:.78rem; color:var(--soft); margin:.1em 0 0; }
.diff .verdict summary { cursor:pointer; color:var(--soft); }
.diff .verdict summary::marker { color:var(--muted); }
.diff .verdict p { margin:.4em 0 0; color:var(--quiet); max-width:60ch; }
@media (prefers-color-scheme: dark) {
  .diff del { color:#f0a08c; background:#3a1e18; }
  .diff ins { color:#8fd8b4; background:#16301f; }
}
.caveats { background:#f4f3ef; border-radius:10px; padding:20px 24px; margin:2.4em 0; }
.caveats h2 { border:0; padding:0; margin:0 0 .5em; font-size:1.1rem; }
.roster { font-size:.8rem; color:var(--quiet); line-height:1.75; }
.roster summary { cursor:pointer; color:var(--soft); font-size:.92rem; }
.roster b { color:var(--soft); font-weight:600; }
.meta { font-size:.82rem; color:var(--quiet); margin-top:3.5em;
        border-top:1px solid var(--rule); padding-top:1.2em; }
@media (prefers-color-scheme: dark) {
  :root { --surface:#1a1a19; --ink:#fff; --soft:#c3c2b7; --muted:#8a8880;
          --rule:#33322f; --g1:#3987e5; --g2:#d95926; --improved:#15251c;
          --quiet:#a3a199; --good:#5cc48d; }
  p, li { color:#e8e7e1; }
  .caveats { background:#232320; }
}
"""



#: Every statistical term the reports use, linked to its Wikipedia article. A reader
#: who meets "modularity" or "silhouette" for the first time should not have to take
#: the number on faith, and a footnote they cannot follow is no better than none.
GLOSSARY = {
    'k-means': 'https://en.wikipedia.org/wiki/K-means_clustering',
    'Leiden': 'https://en.wikipedia.org/wiki/Leiden_algorithm',
    'modularity': 'https://en.wikipedia.org/wiki/Modularity_(networks)',
    'silhouette': 'https://en.wikipedia.org/wiki/Silhouette_(clustering)',
    'adjusted Rand index': 'https://en.wikipedia.org/wiki/Rand_index#Adjusted_Rand_index',
    'principal component analysis':
        'https://en.wikipedia.org/wiki/Principal_component_analysis',
    'cosine similarity': 'https://en.wikipedia.org/wiki/Cosine_similarity',
    'multiple comparisons': 'https://en.wikipedia.org/wiki/Multiple_comparisons_problem',
    'false discovery rate': 'https://en.wikipedia.org/wiki/False_discovery_rate',
    'multilayer network': 'https://en.wikipedia.org/wiki/Multidimensional_network',
    'p-value': 'https://en.wikipedia.org/wiki/P-value',
    'permutation test': 'https://en.wikipedia.org/wiki/Permutation_test',
    'outlier': 'https://en.wikipedia.org/wiki/Outlier',
}


def term(name: str, shown: str | None = None) -> str:
    """Link a statistical term to its Wikipedia article."""
    url = GLOSSARY.get(name)
    label = shown or name
    return (f'<a class="term" href="{url}" target="_blank" rel="noopener">{label}</a>'
            if url else label)


def _family_summary(results, decisive, comparable) -> str:
    """One phrase describing what a family is worth reading for."""
    gained = [c for c in results if c['improved']]
    if gained:
        return (f'{len(gained)} rewrite{"" if len(gained) == 1 else "s"} gained support'
                + (f', {len(decisive) - len(gained)} lost it'
                   if len(decisive) > len(gained) else ''))
    if decisive:
        return f'{len(decisive)} rewrite{"" if len(decisive) == 1 else "s"} lost support'
    if comparable:
        return f'{len(comparable)} compared, no clear difference'
    return 'nothing comparable'


def word_diff(old: str, new: str) -> str:
    """Wikipedia-style inline word diff of two statements.

    Word-level rather than character-level, because these are rewrites of prose and
    a character diff of Dutch compounds is unreadable. Removals and additions carry
    strikethrough and underline as well as colour, so the diff survives greyscale
    printing and colour-blind reading.
    """
    tokens = lambda t: _re.findall(r'\s+|\w+|[^\w\s]', t or '')
    a, b = tokens(old), tokens(new)
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b).get_opcodes():
        if op == 'equal':
            out.append(html.escape(''.join(a[i1:i2])))
        else:
            if op in ('replace', 'delete'):
                gone = ''.join(a[i1:i2])
                if gone.strip():
                    out.append(f'<del>{html.escape(gone)}</del>')
            if op in ('replace', 'insert'):
                added = ''.join(b[j1:j2])
                if added.strip():
                    out.append(f'<ins>{html.escape(added)}</ins>')
    return ''.join(out)


# ── HTML report ──────────────────────────────────────────────────────────────

#: Which sections each audience gets. The two reports answer different questions,
#: so this is a genuine split rather than one document with bits hidden: an
#: organiser is choosing statements to carry forward, a participant is trying to
#: understand where they landed and whether to believe it.
AUDIENCES = {
    # 'groups_brief' comes before anything that mentions groups. The organiser
    # report is full of per-group percentages, and a reader who has not been told
    # what a group is will reasonably assume it means a faction someone belongs to.
    'organiser': ['intro', 'participation_brief', 'groups_brief', 'deduplication',
                  'methods_compared', 'ladder', 'consensus',
                  'divergence', 'wording', 'families', 'generations', 'shortlist',
                  'caveats', 'meta'],
    'participant': ['intro', 'participation', 'groups', 'stability', 'divergence',
                    'roster', 'caveats', 'meta'],
}


def write_report(*, bundle, conv_key, checks, funnel, server, gate, sweep, stability,
                 divergence, groups, pairs, head_to_heads, effect, roster,
                 participation=None, families=None, generations=None,
                 descendants=None, representatives=None, redundant=None,
                 comparison_figure=None, method_comparison=None, ladder=None,
                 significance=None, audience='participant', out='report.html') -> Path:
    """Render one self-contained HTML file for one audience."""
    if audience not in AUDIENCES:
        raise ValueError(f'audience must be one of {sorted(AUDIENCES)}')
    show = set(AUDIENCES[audience])
    b = bundle
    row = b.app['conversations']
    title = row.loc[row['conv_key'] == conv_key, 'title']
    title = title.iloc[0] if len(title) else conv_key

    def esc(x):
        return html.escape(str(x))

    machine = b.machine.get((conv_key, 2), {})
    n_real = int(b.phase('votes_latest', conv_key, 2)['person_key'].nunique())

    # Whether the grouping survived its own significance test. Two sections below rank
    # statements by how far apart the groups fall, and they read very differently
    # depending on the answer — so the answer travels with them instead of staying in
    # the section that computed it, several screens up. The threshold is corrected for
    # the number of tests run, matching what that section says in words.
    grouping_is_weak = False
    if significance is not None and not significance.empty:
        p_values = significance['p (permutation test)']
        grouping_is_weak = bool(p_values.min() > 0.05 / len(p_values))
    weak_note = ''
    if grouping_is_weak:
        where = ('<a href="#by-chance">see <i>Could this have happened by chance?</i></a>'
                 if 'ladder' in show else 'see <i>How solid is that split?</i> above')
        weak_note = (
            f'<p class="footnote"><b>These gaps describe individuals, not camps.</b> '
            f'The grouping they rest on is not statistically distinguishable from no '
            f'grouping at all ({where}), and the smaller group is small enough that one '
            f'person accounts for much of any gap. Read a wide gap as a statement worth '
            f'discussing, not as evidence of a division in the community.</p>')

    parts = ['<!doctype html><html lang="en"><head><meta charset="utf-8">',
             '<meta name="viewport" content="width=device-width,initial-scale=1">',
             f'<title>{esc(title)} — '
             f'{"choosing statements" if audience == "organiser" else "results"}</title>',
             f'<style>{CSS}</style></head><body><main>']

    # ── intro ────────────────────────────────────────────────────────────────
    parts.append(f'<h1>{esc(title)}</h1>')
    if audience == 'organiser':
        parts.append(
            '<p class="lede">Which statements carry support, which divide the room, '
            'and — where the same idea was written several ways — which wording did '
            'best. Intended for deciding what goes forward to a draft.</p>')
        parts.append(
            '<p>The recommendations come first, below the participation numbers: one '
            'wording per group of rewrites, plus the statements nobody rewrote. '
            'Everything after them is the working that produced them — including the '
            'reason the group columns on this page carry a warning.</p>')
    else:
        parts.append(
            '<p class="lede">What came out of the consultation: how many people took '
            'part, what the opinion groups are, and how solid that grouping turns out '
            'to be.</p>')

    # Machine-made accounts are excluded silently: they are a defect in the tool,
    # not a finding about the consultation. The one exception is when participants
    # can see the live results page for themselves — then the totals visibly
    # disagree, and leaving that unexplained is worse than a short note.
    conv_row = b.app['conversations']
    public_results = bool(conv_row.loc[conv_row['conv_key'] == conv_key,
                                       'phase_public_results'].iloc[0]) \
        if 'phase_public_results' in conv_row.columns and len(conv_row) else False
    if machine and public_results:
        parts.append(
            f'<p>If you have seen the results page in the tool itself, it reports a '
            f'higher number of participants than this page does. That count includes '
            f'{len(machine)} entries the software created automatically rather than '
            f'people — submitting a statement registers an automatic agreement with it. '
            f'This analysis counts only the {n_real} people.</p>')

    # ── participation ────────────────────────────────────────────────────────
    if 'participation' in show:
        parts.append('<h2>Who took part</h2>')
        parts.append(
            '<p>“Participants” can mean several things. '
            'Someone who gave one opinion and someone who worked through eighty are '
            'both counted once on the results page. The opinion groups are built only '
            'from people who gave enough opinions for the clustering to place them.</p>')
        parts.append(f'<div class="tablewrap">{_table(funnel.drop(columns=["pct_of_voters"]))}</div>')
        parts.append(
            '<p>How many people opened the page is not recorded — wiki-polis does not '
            'log page views — so “joined” is the earliest honest number.</p>')
    statements_all = b.phase('statements', conv_key, 2)
    prov_all = b.app['statement_provenance']
    n_seeded = int(statements_all['is_seed'].astype(bool).sum())
    derived_tids = set(prov_all.loc[prov_all['conv_key'] == conv_key,
                                    'polis_statement_id']) if not prov_all.empty else set()
    n_improved = int(statements_all['tid'].isin(derived_tids).sum())
    n_new = len(statements_all) - n_seeded - n_improved
    voted_tids = set(b.phase('votes_latest', conv_key, 2)['tid'])
    n_unvoted = int((~statements_all['tid'].isin(voted_tids)).sum())

    if {'participation', 'participation_brief'} & show:
        parts.append(
            f'<p><b>{len(statements_all)} statements</b> were put to participants: '
            f'{n_seeded} written by the organiser to start the consultation, '
            f'{n_new} proposed by participants as new ideas, and {n_improved} '
            f'submitted as an improved wording of an existing statement. '
            f'{n_unvoted} of the {len(statements_all)} drew no opinion from anyone '
            f'who was shown them — because they were never shown. This conversation '
            f'moderates strictly: a statement reaches participants only once the '
            f'organiser accepts it.</p>')
        n_accepted = int((statements_all['mod'] == 1).sum())
        n_rejected = int((statements_all['mod'] == -1).sum())
        n_pending = int((statements_all['mod'] == 0).sum())
        # "Of those" used to open this sentence, with the previous paragraph's "43 never
        # voted on" as its nearest antecedent — but 60 + 28 + 19 is 107. A reader doing
        # the arithmetic against 43 concludes the page cannot add up.
        parts.append(
            f'<p>Across all {len(statements_all)}, the organiser accepted '
            f'<b>{n_accepted}</b> and rejected {n_rejected}; {n_pending} were never '
            f'moderated either way. Nothing is shown to participants until it is '
            f'accepted, so those {n_pending} were never seen by anyone. A rejected '
            f'statement stops being shown, but opinions already given on it remain in '
            f'the data.</p>')

        # Submitting a statement casts a vote on it. Whether that vote is inside the
        # percentages below depends on where it landed, which is a property of a bug
        # rather than of the consultation — so it is stated from the data each time
        # rather than assumed, and the wording changes if the bug is fixed.
        auto = auto_agree_votes(b, conv_key, phase=2)
        if auto['total']:
            parts.append(
                f'<p><b>Submitting a statement also records an opinion on it.</b> The '
                f'tool records the submitter as agreeing with what they have just '
                f'written, for new statements and rewordings alike — {auto["total"]} '
                f'such opinions here, one per statement.</p>')
            if auto['on_real'] == 0:
                parts.append(
                    f'<p>None of them are counted below. Every one was recorded against '
                    f'an account the software created at the moment of submission rather '
                    f'than against the person submitting, and those accounts are excluded '
                    f'from this analysis. So no statement here carries the <i>automatic</i> '
                    f'agreement generated when it was submitted — every percentage is '
                    f'made of opinions given by someone who was shown the statement and '
                    f'responded to it.</p>')
            elif auto['on_machine'] == 0:
                parts.append(
                    f'<p><b>All {auto["on_real"]} are counted below as ordinary '
                    f'agreements.</b> Each statement therefore starts with one agreement '
                    f'that nobody chose to give it, which raises its apparent support — '
                    f'most visibly on statements few people gave an opinion on, and '
                    f'systematically on rewordings, since every rewording brings one '
                    f'with it.</p>')
            else:
                parts.append(
                    f'<p>{auto["on_machine"]} of them were recorded against accounts the '
                    f'software created rather than against people, and are excluded. The '
                    f'remaining <b>{auto["on_real"]} are counted below as ordinary '
                    f'agreements</b>, so those statements carry one agreement that '
                    f'nobody chose to give them.</p>')
            parts.append(
                '<p class="footnote">Whether anyone went on to give an opinion on a '
                'statement they wrote cannot be told apart here, in either direction: who '
                'wrote which statement was left out of the data this was built from.</p>')

    # Both audiences see 22 analysed and 24 placed, a few lines apart, and both are
    # entitled to know why one exceeds the other. This used to live in `groups_brief`,
    # which only the organiser gets — so the participant report showed the discrepancy
    # bare, under a lede promising the groups are built from people who voted enough.
    if {'participation', 'participation_brief'} & show and server.get('available'):
        n_placed = len({p for p in server['labels'] if p not in machine})
        analysed = funnel.loc[funnel['step'].str.startswith('ANALYSED'), 'n_people']
        analysed = int(analysed.iloc[0]) if len(analysed) else 0
        if analysed and n_placed != analysed:
            parts.append(
                f'<p class="footnote">Those two rows do not match, and the difference is '
                f'not people being dropped. The tool placed {n_placed} people into '
                f'groups using its own count of who had given enough opinions; the checks '
                f'on this page rerun the grouping on the {analysed} who clear the '
                f'threshold applied here. It is a disagreement about who counts as having '
                f'given enough opinions, not about anybody’s opinions.</p>')

    if 'participation_brief' in show:
        parts.append(
            f'<p>{n_real} people took part; {int((funnel["step"].str.startswith("ANALYSED")).any() and funnel.loc[funnel["step"].str.startswith("ANALYSED"), "n_people"].iloc[0])} '
            f'of them gave opinions on enough statements to be included in the group '
            f'analysis. '
            f'Everything below rests on those numbers, which are small.</p>')

    # ── groups ───────────────────────────────────────────────────────────────
    if 'groups' in show and server.get('available'):
        real_labels = {p: g for p, g in server['labels'].items() if p not in machine}
        sizes = pd.Series(list(real_labels.values())).value_counts().sort_index()
        listing = ' and '.join(f'{n} people' for n in sizes.values)
        parts.append('<h2>The opinion groups</h2>')
        parts.append(
            f'<p>The clustering sorted participants into <b>{len(sizes)} groups</b> — '
            f'{listing} — based only on their opinions, not on anything they said. '
            f'A group is a set of people whose opinions resemble each other more than '
            f'they resemble the rest.</p>')
        parts.append(f'<figure class="figwrap">{_svg(plot_opinion_map(b, conv_key, server))}</figure>')
        if len(sizes) and sizes.min() < 5:
            parts.append(
                f'<p><b>The smaller group has {sizes.min()} people in it.</b> That is few '
                f'enough that it describes those individuals rather than a faction, and '
                f'a single person changing a few opinions could dissolve it.</p>')

    # ── stability ────────────────────────────────────────────────────────────
    if 'stability' in show:
        parts.append('<h2>How solid is that split?</h2>')
        parts.append(
            '<p>The software always reports between two and five groups. It has no way '
            'of reporting “these people do not really divide”. So the same opinions were '
            'given to a completely different method and run repeatedly under different '
            'settings, to see whether the same people keep landing together.</p>')
        if stability.get('available'):
            parts.append(
                f'<p>Across {stability["n_runs"]} runs of the second method — different '
                f'settings, different starting points — only '
                f'<b>{stability["pairs_decided"]:.0%}</b> of the pairs of people in '
                f'{stability["n_people"]} landed together nearly every time, or apart '
                f'nearly every time. If the consultation really divided into camps this '
                f'would be close to 100%: two people in the same camp would keep '
                f'turning up together whatever the settings. Instead almost every pair '
                f'changes sides depending on how the method is set.</p>')
            parts.append(f'<figure class="figwrap">'
                         f'{_svg(plot_stability_heatmap(stability, server))}</figure>')
        if comparison_figure is not None:
            parts.append(
                '<p>The picture that follows is the check itself, and it is worth reading '
                'slowly. Every small square compares two people: dark means they agreed '
                'most of the time, pale means they often disagreed. In the '
                'first two panels the same 22 people appear in both rows and columns — '
                'first ordered by the groups the tool’s own method produces when rerun '
                'here, then by the groups the second method found. Black lines mark the '
                'boundaries between groups.</p>')
            parts.append(
                '<p><b>What a real division would look like:</b> dark squares along the '
                'diagonal, inside the black boxes, against a pale background everywhere '
                'else — people agreeing with their own group and disagreeing with the '
                'other. That is not what either panel shows. The shading is much the '
                'same inside the boxes as outside them, under both orderings.</p>')
            # The paragraph above describes a pattern that is *absent*, directly over a
            # figure of real measurements — so a reader cannot tell whether they are
            # looking at this consultation or at an illustration of one. Say which.
            parts.append(
                f'<figure class="figwrap">{_svg(comparison_figure)}'
                f'<figcaption>Both panels are the opinions actually recorded in this '
                f'consultation — the same {stability.get("n_people", 22)} people, '
                f'ordered two different ways. Nothing here is simulated or drawn for '
                f'illustration. The pattern described above is the one that is '
                f'<i>absent</i>: were it present, it would show as dark blocks inside '
                f'the black boxes.</figcaption></figure>')
            parts.append(
                f'<p>The third panel explains why. {term("modularity", "Modularity")} asks '
                'whether people are '
                'more densely connected to their own group than chance would predict. '
                'In the shaded stretch on the left the second method declines to split '
                'at all and puts everyone in one community — a score of zero there means '
                '“no split attempted”, not “a perfect split”. Once it is pushed to '
                'divide people, the score goes <i>below</i> zero: the divisions it makes '
                'are worse than random.</p>')
            parts.append(
                '<p>The second method’s own two-way split, when it is forced to make '
                'one, lands somewhere else entirely — and it scores that split below '
                'zero. It is not proposing a different line; it is declining to draw '
                'one. Opinion in this consultation looks '
                'like a spread — people who mostly agree, differing by degree — rather '
                'than two camps. The tool reports groups because reporting groups is '
                'what it does; it has no way to say “these people do not divide”.</p>')

        median_overlap = sweep.attrs.get('median_overlap', float('nan'))
        if median_overlap == median_overlap and median_overlap < 3:
            parts.append(
                f'<p><b>This check could not be completed properly.</b> Two participants '
                f'shared a median of {median_overlap:.0f} statements that they both gave '
                f'an opinion on, because there were many statements and most people saw '
                f'a small share of them. With so little overlap the second method has almost '
                f'nothing to work from, and its answer here should be disregarded rather '
                f'than read as disagreement.</p>')

    # The recommendations are written last — they depend on everything above them —
    # but they are what the organiser opened the page for, and they used to sit at the
    # foot behind ~1400 lines of method. The section is spliced in here instead, after
    # the framing numbers and before the working, so skimming for decisions reaches
    # them first. Everything from here to the significance test then reads as the
    # reason the picks are hedged the way they are.
    shortlist_anchor = len(parts)

    # ── what a group is ──────────────────────────────────────────────────────
    if 'groups_brief' in show and server.get('available'):
        real_labels = {p: g for p, g in server['labels'].items() if p not in machine}
        sizes = pd.Series(list(real_labels.values())).value_counts().sort_index()
        parts.append('<h2>First: what “a group” means here</h2>')
        parts.append(
            '<p>Several tables below break results down by group, so it is worth being '
            'precise about what that word is doing.</p>')
        parts.append(
            '<p>A group is <b>not</b> a faction, a camp, or anything participants signed '
            'up to. Nobody chose a group and nobody was told they were in one. The '
            'software compared people’s opinions and sorted them so that those who gave '
            'similar opinions ended up together. A group is therefore a description of '
            'opinion patterns on <i>these particular statements</i>, and it would very likely '
            'come out differently on a different set of statements.</p>')
        if len(sizes):
            listing = ', '.join(f'<b>group {g + 1}</b> with {n} '
                                f'{"person" if n == 1 else "people"}'
                                for g, n in sizes.items())
            parts.append(
                f'<p>In this consultation the clustering produced {len(sizes)} groups: '
                f'{listing}. The numbering is arbitrary — group 1 is not the majority '
                f'view or the first to arrive; it is just a label.</p>')
            parts.append(f'<figure class="figwrap">'
                         f'{_svg(plot_opinion_map(b, conv_key, server))}</figure>')
            parts.append(
                f'<p class="footnote">These sizes are the tool’s own, covering '
                f'{int(sizes.sum())} people. The checks further down rerun the grouping '
                f'from scratch on the participants who clear the threshold applied here, '
                f'so the sizes they report differ slightly — see the note under the '
                f'participation table above.</p>')
            if sizes.min() < 5:
                parts.append(
                    f'<p><b>This matters for how much weight the group columns can '
                    f'carry.</b> The smaller group has {sizes.min()} people in it, so a '
                    f'column reporting “0% agreement in group {int(sizes.idxmin()) + 1}” '
                    f'may rest on two or three opinions. Where a split looks dramatic below, '
                    f'check the number of people beside it before drawing a conclusion.</p>')

    # ── deduplication, reviewable ────────────────────────────────────────────
    if 'deduplication' in show and redundant is not None and not redundant.empty:
        stmts_all = b.phase('statements', conv_key, 2).set_index('tid')['txt'].to_dict()
        merged = redundant[redundant['verdict'].str.startswith('redundant')]
        distinct = redundant[redundant['verdict'].str.startswith('distinct')]
        unknown = redundant[redundant['verdict'].str.startswith('undecided')]
        # Pairs where one side was never voted on at all. They cannot be judged by
        # votes and so fall outside the three buckets above — but they are the ones
        # where the organiser's own reading is the only thing available, so omitting
        # them would make "every pair is listed below" false.
        aside = redundant[redundant['verdict'].str.startswith('set aside')]

        parts.append('<h3>How the groups were worked out</h3>')
        parts.append(
            '<p>The grouping is computed from opinions alone. One thing has to be settled '
            'first: when the same idea appears twice in slightly different words, it '
            'gets counted twice, and the clustering then treats that idea as twice as '
            'important. So near-identical statements are merged before grouping.</p>')
        parts.append(
            '<p>Deciding which are really the same cannot be done on wording alone — '
            '“at least a thousand edits” and “at least five hundred edits” are almost '
            'identical as text and quite different as proposals. So each candidate pair '
            'is judged by the opinions of the people who gave one on <i>both</i>: if '
            'they agreed nearly every time, the second version adds nothing '
            'and is merged. The one exception is wording that carries no meaning at all '
            '— where two statements are word-for-word the same once spelling and number '
            'format are normalised (“2 weken” and “twee weken”), they are the same '
            'statement whether or not anybody gave an opinion on them.</p>')
        parts.append(
            f'<p><b>Every pair with opinions on both statements is listed below, so the '
            f'judgement can be overridden</b> — {len(merged) + len(distinct) + len(unknown)} '
            f'of the {len(redundant)} pairs the wording flagged as similar. On '
            f'{len(unknown)} of those, too few people gave an opinion on both for the '
            f'opinions to decide anything. If you can see that two statements are the '
            f'same and the data could not tell, say so and they can be merged by hand.</p>')

        def pair_rows(frame, note_field=True):
            out = []
            for r in frame.itertuples():
                note = (f'{r.n_common} gave an opinion on both, agreeing '
                        f'{r.vote_concordance:.0%} of the time'
                        if r.n_common and r.vote_concordance == r.vote_concordance
                        else f'only {r.n_common} gave an opinion on both')
                out.append(
                    f'<div class="diff"><div class="ids">#{r.tid_a} → #{r.tid_b}'
                    f'<span class="sim">text {r.similarity:.2f}</span></div>'
                    f'<p class="text">{word_diff(stmts_all.get(int(r.tid_a), r.text_a), stmts_all.get(int(r.tid_b), r.text_b))}</p>'
                    f'<p class="verdictline">{esc(note)}</p></div>')
            return out

        parts.append(
            f'<details class="family" open><summary><b>Merged — treated as one '
            f'statement</b> ({len(merged)} pairs)</summary>'
            + ''.join(pair_rows(merged)) + '</details>')
        parts.append(
            f'<details class="family"><summary><b>Kept separate — people gave different '
            f'opinions on them</b> ({len(distinct)} pairs)</summary>'
            f'<p class="famroot">These look alike but the opinions say otherwise. Merging '
            f'them would erase a real disagreement.</p>'
            + ''.join(pair_rows(distinct)) + '</details>')
        parts.append(
            f'<details class="family"><summary><b>Kept separate — too few people gave '
            f'an opinion on both to tell</b> ({len(unknown)} pairs)</summary>'
            f'<p class="famroot">No judgement was possible here, so both were kept. '
            f'This is the list to look through: where you can see two are the same, '
            f'they should be merged.</p>'
            + ''.join(pair_rows(unknown)) + '</details>')
        # The pairs that could not be judged because one side was never voted on are
        # not worth listing as pairs: what the organiser needs from them is the
        # statements themselves. Every one of these is a statement that took no part in
        # anything on this page, and is still available to put to people.
        if n_unvoted:
            unvoted_rows = statements_all[~statements_all['tid'].isin(voted_tids)]
            parts.append(
                f'<details class="family"><summary><b>Statements nobody gave an opinion '
                f'on</b> '
                f'({n_unvoted} of {len(statements_all)}, taking no part in any of the '
                f'above)</summary>'
                f'<p class="famroot">Submitted too late to be shown, or never shown. '
                f'They cannot be compared with anything and they carry no weight in the '
                f'grouping, so they are simply absent from every number on this page — '
                f'including the merging judgements above, {len(aside)} of which involve '
                f'one of them. Nothing has been decided about these: they are still '
                f'available to put to people in the next round.</p>'
                + ''.join(
                    f'<div class="diff"><div class="ids">#{int(r.tid)}</div>'
                    f'<p class="text">{esc(r.txt)}</p></div>'
                    for r in unvoted_rows.itertuples())
                + '</details>')

    # ── two methods, compared ────────────────────────────────────────────────
    if 'methods_compared' in show and method_comparison is not None:
        mc = method_comparison
        parts.append('<h3>Two ways of finding groups, and whether they agree</h3>')
        parts.append(
            '<p>Any grouping is the product of a method, so it is worth knowing that '
            'two quite different methods were tried, and what each concluded.</p>')
        parts.append(
            '<p><b>The first is what the tool itself uses:</b> it places every '
            'participant on a map according to their opinions — people who agreed end '
            'up near each other — and then cuts that map into a fixed number of pieces '
            f'({term("k-means", "<i>k-means</i>")}). It is built to produce groups, and will produce them '
            'from any set of opinions at all. It cannot report that there are none.</p>')
        parts.append(
            f'<p><b>The second treats the participants as a network</b> '
            f'({term("Leiden", "<i>Leiden community detection</i>")}). Each person is '
            'connected to everyone they tend '
            'to agree with, and the method looks for clumps that are more tightly '
            'connected inside than to the rest. Crucially, it <i>can</i> come back and '
            'say there are no clumps — which is the reason for using it here.</p>')
        rows = [{'method': 'k-means on the opinion map (what the tool uses)',
                 'groups found': mc['k_polis'], 'sizes': mc['sizes_polis'],
                 'its own score for that split':
                     f'{mc["silhouette_polis"]:.3f} (silhouette)'
                     if 'silhouette_polis' in mc else ''},
                {'method': 'Leiden community detection',
                 'groups found': mc['k_leiden'], 'sizes': mc['sizes_leiden'],
                 'its own score for that split':
                     f'{mc["modularity_leiden"]:.3f} (modularity)'
                     if 'modularity_leiden' in mc else ''}]
        columns = ['method', 'groups found', 'sizes', 'its own score for that split']
        if not any(r['its own score for that split'] for r in rows):
            columns = columns[:-1]
        parts.append(
            f'<div class="tablewrap">{_table(pd.DataFrame(rows)[columns])}</div>')
        if mc.get('n_analysed'):
            drift = mc.get('ari_vs_server')
            drift_text = (
                f' Run on that smaller population the first method draws a slightly '
                f'different line — it agrees with the published grouping at '
                f'{drift:.2f} rather than exactly, moving a couple of people across.'
                if drift is not None and drift == drift else '')
            exact = (' Given the tool’s own population it reproduces the published '
                     'grouping exactly.' if gate and gate.get('passed') else '')
            parts.append(
                f'<p class="footnote">Both methods were rerun here on the '
                f'{mc["n_analysed"]} participants who cleared the opinion threshold, which '
                f'is why the first row’s group sizes are not the tool’s published ones '
                f'quoted earlier.{drift_text}{exact}</p>')
        parts.append(
            f'<p><b>They agree very little.</b> Measured on a scale where 1.0 means '
            f'identical groupings and 0.0 means no more alike than chance '
            f'({term("adjusted Rand index")}), the two '
            f'score <b>{mc["ari"]:.2f}</b>. The table below shows where each person '
            f'ended up under both methods — if the two were finding the same division, '
            f'the numbers would sit along a diagonal.</p>')
        parts.append(f'<div class="tablewrap">{mc["crosstab_html"]}</div>')
        score = mc.get('modularity_leiden')
        parts.append(
            f'<p><b>The second row has to be read with its score.</b> The second method '
            f'also reports <i>how much</i> group structure it found, and here it found '
            f'none. It returns two communities in the table above only because it was '
            f'held to one fixed setting so that the two methods could be compared at '
            f'all; it scores that division at '
            f'{f"{score:.3f}" if score is not None else "at or below zero"} — '
            f'{"below" if (score is None or score < 0) else "at"} zero, meaning the '
            f'split is no better than dividing the same people at random. Allowed to '
            f'choose for itself it puts everybody in a single community. So the '
            f'disagreement above is not two methods drawing the line in different '
            f'places. It is one method saying there is no line to draw.</p>')
        if comparison_figure is not None:
            parts.append(
                f'<figure class="figwrap">{_svg(comparison_figure)}'
                f'<figcaption>Real data, not an illustration: these are the opinions '
                f'recorded in this consultation, the same people ordered two different '
                f'ways. A genuine division would appear as dark blocks inside the black '
                f'boxes — which is what to look for, and what is not there.</figcaption>'
                f'</figure>')
            parts.append(
                '<p>In the first two panels every small square compares two people — '
                'dark means they agreed. People are ordered by their group, first '
                'under one method then the other, with black lines at the boundaries. A '
                'real division would show dark blocks inside the boxes against a pale '
                'background; neither ordering does. The third panel is the structure '
                'score: in the shaded stretch the method declined to split at all, and '
                'beyond it the score falls below zero.</p>')

    # ── the refinement ladder + significance ─────────────────────────────────
    if 'ladder' in show and ladder is not None:
        parts.append('<h3>How much the answer depends on the choices made</h3>')
        parts.append(
            '<p>Neither method is applied only once. Each was run three times, with a '
            'more careful preparation of the data each time. Statements nobody gave an '
            'opinion on are removed throughout — they carry no information at any level.</p>')
        parts.append(
            '<ul><li><b>naive</b> — the method as the tool applies it</li>'
            '<li><b>deduplicated</b> — near-identical statements merged, so one idea '
            'written several ways stops counting several times</li>'
            f'<li><b>layered</b> — statements split by subject and each subject grouped '
            f'separately, then combined. Only this level can represent someone who '
            f'agrees with you about elections and disagrees about blocks; a single '
            f'grouping cannot ({term("multilayer network", "multilayer methods")})</li></ul>')
        parts.append(f'<div class="tablewrap">{_table(ladder)}</div>')
        parts.append(
            '<p>Read down each method. The number of groups the first method reports '
            'changes at every level — two, then three, then four — and its agreement '
            'with its own first answer falls to 0.22. The second method declines to '
            'divide anyone at all until the layered level forces it to. If the groups '
            'described something solid about these participants, neither of those '
            'things would happen.</p>')

    if 'ladder' in show and significance is not None and not significance.empty:
        parts.append('<h3 id="by-chance">Could this have happened by chance?</h3>')
        parts.append(
            '<p>A grouping method always returns an answer and always returns a score. '
            'The question is whether the score means anything. To find out, the same '
            'procedure was run 100 times on deliberately scrambled data — each '
            'statement keeps its own opinions, but they are reassigned to different people '
            'at random, so any pattern connecting one statement to another is '
            'destroyed. That is what "no groups" looks like. If the real data scores no '
            'better than the scrambled data, the grouping cannot be told apart from '
            'noise.</p>')
        parts.append(f'<div class="tablewrap">{_table(significance)}</div>')
        parts.append(
            f'<p><b>Scrambled data scores almost as well as the real data.</b> The '
            f'quality score for the first method sits around 0.37 on data with no '
            f'groups in it at all, against 0.46–0.48 here — a gap small enough that it '
            f'arises by chance about one time in eleven without deduplication, and about '
            f'one in twenty with it. The second method scores identically on real and '
            f'scrambled data, because on both it declines to split anyone — those two '
            f'rows are degenerate rather than independent evidence. That leaves two real '
            f'tests, and the better of the two does not survive the usual correction for '
            f'{term("multiple comparisons", "testing several things at once")}. With 100 '
            f'shuffles the p-values also come in steps of about 0.01, so 0.049 and 0.05 '
            f'are not meaningfully different numbers.</p>')
        parts.append(
            f'<p class="footnote">The last column is a '
            f'{term("p-value", "permutation p-value")}: the fraction of 100 scrambled '
            f'datasets that scored at least as well as the real data, with the standard '
            f'+1 correction applied to both counts. It is not the '
            f'same quantity as the {term("adjusted Rand index")} in the table above, '
            f'which measures how far two groupings agree with each other.</p>')
        parts.append(
            '<p>So the honest summary is this: <b>the opinion groups in this '
            'consultation are not statistically distinguishable from no groups at '
            'all.</b> That is not a fault of the consultation, and it does not mean '
            'people agreed about everything — the disagreements shown elsewhere in this '
            'report are real. It means the disagreements do not line up into camps, and '
            'the group labels should not be used as though they identify factions.</p>')

    # ── consensus / divergence ───────────────────────────────────────────────
    if 'consensus' in show and not divergence.empty:
        # This table used to sort on min(group1, group2). With three people in group 1,
        # every entry's group-1 figure rested on one to three votes, so the sort never
        # selected on that group's level — it only dropped statements where one or two
        # of those three happened to dissent, excluding several of the best-supported
        # statements in the consultation while admitting one at 69%. Ranked on overall
        # agreement instead, which is the quantity that does not depend on a grouping
        # this report goes on to show is indistinguishable from noise.
        agreed = divergence[divergence['agree_pct'].notna()].copy()
        cols = [c for c in agreed.columns if c.startswith('agree_group')]
        floor = max(5, POLIS_VOTE_THRESHOLD)
        broad = agreed[agreed['n_decided'] >= floor].sort_values(
            ['agree_pct', 'n_decided'], ascending=False).head(12)
        if not broad.empty:
            parts.append('<h2>Statements with the broadest support</h2>')
            parts.append(
                f'<p>Ranked by the share of people who agreed, counting only those who '
                f'took a side, and only statements at least {floor} people decided on. '
                f'These are the safest candidates to carry forward, and this ranking '
                f'does not depend on the opinion groups at all — which matters, because '
                f'the groups do not survive the checks below.</p>')
            table = broad[['tid', 'statement', 'agree_pct', 'n_decided'] + cols].rename(
                columns={'agree_pct': 'agreed %', 'n_decided': 'people who took a side'})
            parts.append(f'<div class="tablewrap">{_table(table)}</div>')
            small = [c for c in cols
                     if broad[c.replace('agree_group', 'decided_group')].max() < 5]
            if small:
                parts.append(
                    '<p class="footnote">The group columns are shown for context only. '
                    'Where a group is very small its percentage can rest on one or two '
                    'opinions, so read the overall figure first.</p>')

    if 'divergence' in show and not divergence.empty:
        parts.append('<h2>Where the groups disagree</h2>')
        parts.append(
            '<p>Each statement appears once, showing how much each group agreed with it, '
            'counting only people who took a side. The further apart the marks, the more '
            'that statement divides the room.</p>')
        parts.append(f'<figure class="figwrap">{_svg(plot_divergence(divergence))}</figure>')
        parts.append(weak_note)

    # ── alterations ──────────────────────────────────────────────────────────
    if 'wording' in show and descendants is not None and not descendants.empty:
        parts.append('<h2>Statements that were rewritten, and how</h2>')
        parts.append(
            '<p>Where a participant proposed a rewording, the change itself is shown '
            'below: <del>struck-through</del> text was removed, <ins>underlined</ins> '
            'text was added. Most of these turn on a single qualifier, and that is '
            'usually where the real decision sits.</p>')
        parts.append(
            '<p>Families are listed with the ones where rewriting made a measurable '
            'difference first, then the largest. Inside each family the same applies: '
            'the rewrites that moved something come before the ones with too few '
            'opinions to judge.</p>')

        stmts = b.phase('statements', conv_key, 2).set_index('tid')['txt'].to_dict()
        votes = b.phase('votes_latest', conv_key, 2)

        def compare(parent: int, child: int):
            """Verdict for one rewrite, plus what it is worth. None if unusable."""
            old, new = stmts.get(parent, ''), stmts.get(child, '')
            if not old or not new:
                return None
            decisive = votes['vote'].isin([RAW_AGREE, RAW_DISAGREE])
            va = votes[(votes['tid'] == parent) & decisive][['person_key', 'vote']]
            vb = votes[(votes['tid'] == child) & decisive][['person_key', 'vote']]
            both = va.merge(vb, on='person_key', suffixes=('_old', '_new'))
            if len(both) < MIN_COMPARABLE:
                return dict(parent=parent, child=child, old=old, new=new, delta=0.0,
                            comparable=False, improved=False,
                            headline='Not enough opinions to compare',
                            detail=f'{len(both)} {"person" if len(both) == 1 else "people"} '
                                   f'gave a clear opinion on both wordings. At least '
                                   f'{MIN_COMPARABLE} are needed before the two can be '
                                   f'compared at all.')
            old_pct = (both['vote_old'] == RAW_AGREE).mean() * 100
            new_pct = (both['vote_new'] == RAW_AGREE).mean() * 100
            delta = new_pct - old_pct
            headline = ('No meaningful difference' if abs(delta) < 10 else
                        'This rewrite did better' if delta > 0 else
                        'The earlier wording did better')
            detail = (f'{len(both)} people gave a clear opinion on both. {old_pct:.0f}% '
                      f'agreed with the earlier wording, {new_pct:.0f}% with this one — a '
                      f'difference of {abs(delta):.0f} percentage points. ')
            detail += ('With this few people, a gap this size is not distinguishable from '
                       'chance.' if abs(delta) < 10 else
                       'Individually this is still within what chance produces at this '
                       'number of people; it is a prompt to read the wording, not a result.')
            return dict(parent=parent, child=child, old=old, new=new, delta=delta,
                        comparable=True, headline=headline, detail=detail,
                        improved=delta >= 10)

        # Families are ordered by what they can actually tell an organiser: those with
        # a measurable difference first, then those measured and found equivalent, then
        # those nobody voted on enough to compare. Ordering by family size instead would
        # put the largest pile of unusable diffs at the top.
        blocks = []
        for family in (families or []):
            rewrites = [m for m in family['members'].itertuples()
                        if m.improves_on is not None and m.improves_on == m.improves_on]
            results = [c for c in (compare(int(m.improves_on), int(m.tid))
                                   for m in rewrites) if c]
            if not results:
                continue
            # Within a family, put the rewrites that actually moved something first.
            # A family of nine is mostly untestable pairs; leading with those buries
            # the one comparison that carries information.
            results.sort(key=lambda c: (c['comparable'] and abs(c['delta']) >= 10,
                                        abs(c['delta']), c['comparable']), reverse=True)
            decisive = [c for c in results if c['comparable'] and abs(c['delta']) >= 10]
            comparable = [c for c in results if c['comparable']]
            # Near-identical siblings: people independently making the same edit.
            # Grouped by simple transitive closure so a run of three appears once.
            member_tids = set(int(t) for t in family['members']['tid'])
            close = [(int(r.tid_a), int(r.tid_b)) for r in pairs.itertuples()
                     if r.similarity >= NEAR_IDENTICAL
                     and int(r.tid_a) in member_tids and int(r.tid_b) in member_tids]
            parent = {t: t for t in member_tids}
            def _find(x):
                while parent[x] != x:
                    parent[x] = parent[parent[x]]
                    x = parent[x]
                return x
            for a, bb in close:
                ra, rb = _find(a), _find(bb)
                if ra != rb:
                    parent[rb] = ra
            clusters = {}
            for t in member_tids:
                clusters.setdefault(_find(t), []).append(t)
            parallel = [sorted(v) for v in clusters.values() if len(v) > 1]

            blocks.append({
                'root': family['root'], 'n_versions': family['size'], 'results': results,
                'parallel': parallel,
                # Families where rewriting actually gained support come first, then
                # those where it made any measurable difference, then the largest.
                # An organiser reading top-down meets the actionable ones first.
                'sort': (len([c for c in results if c['improved']]),
                         len(decisive), family['size']),
                'summary': _family_summary(results, decisive, comparable),
                'n_decisive': len(decisive),
            })
        blocks.sort(key=lambda x: x['sort'], reverse=True)
        pairs_shown = sum(len(x['results']) for x in blocks)

        improvements = [(block['root'], c) for block in blocks
                        for c in block['results'] if c['improved']]
        if pairs_shown:
            if improvements:
                named = ', '.join(
                    f'<a href="#diff-{c["parent"]}-{c["child"]}">#{c["parent"]} → '
                    f'#{c["child"]}</a> <span class="infam">(#{root} family, '
                    f'+{c["delta"]:.0f} points)</span>'
                    for root, c in sorted(improvements, key=lambda x: -x[1]['delta']))
                # The threshold behind `improvements` is a display cutoff (a 10-point
                # margin), not a test. Stating it as "drew more support" promoted two
                # eyeballed gaps to findings, in a report whose own corrected test
                # clears none of them. The number stays — it is a useful place to look —
                # but it is now labelled as what it is, with the tested answer beside it.
                tested = (effect.get('reading') if isinstance(effect, dict) else None) or (
                    'None of the comparisons with enough opinions survives correction for '
                    'testing many pairs at once.')
                parts.append(
                    f'<p class="callout"><b>{len(improvements)} of {pairs_shown} rewrites '
                    f'show a margin of 10 points or more over the wording they replaced</b>, '
                    f'among the people who gave an opinion on both: {named}. That is a '
                    f'margin, not '
                    f'a result — {esc(tested)} Read them as the places most worth looking '
                    f'at by eye.</p>')
            else:
                parts.append(
                    f'<p>None of the {pairs_shown} rewrites drew more support than the '
                    f'wording it replaced, among the people who gave an opinion on '
                    f'both.</p>')

        for block in blocks:
            informative = block['n_decisive'] > 0
            parts.append(
                f'<details class="family"{" open" if informative else ""}>'
                f'<summary><b>#{block["root"]} family</b> — '
                f'{block["n_versions"]} versions · {block["summary"]}</summary>')
            parts.append(f'<p class="famroot">{esc(stmts.get(block["root"], ""))}</p>')
            if block['parallel']:
                for cluster in block['parallel']:
                    ids = ', '.join(f'#{t}' for t in cluster)
                    parts.append(
                        f'<details class="parallel"><summary>Versions {ids} look '
                        f'near-identical</summary><p>Separate attempts at the same '
                        f'change. Worth deciding whether they need to stay separate '
                        f'options in the next round.</p></details>')
            for c in block['results']:
                parts.append(
                    f'<div class="diff{" improved" if c["improved"] else ""}" '
                    f'id="diff-{c["parent"]}-{c["child"]}">'
                    f'<div class="ids">#{c["parent"]} → #{c["child"]}'
                    + ('<span class="badge">improvement</span>' if c['improved'] else '')
                    + '</div>'
                    f'<p class="text">{word_diff(c["old"], c["new"])}</p>'
                    f'<details class="verdict"><summary>{esc(c["headline"])}</summary>'
                    f'<p>{esc(c["detail"])}</p></details></div>')
            parts.append('</details>')

        if not pairs_shown:
            parts.append('<p class="missing">No declared rewrites in this consultation.</p>')
        elif effect.get('available') and effect.get('order_effect_share_earlier') is not None:
            # This was written as a wording effect measured over people. It is neither:
            # the denominator is discordant pair-instances, not people (one person
            # inside a large family generates many), and because variants are compared
            # in submission order it measures order and exposure, not wording.
            n_disc = effect.get('n_discordant_pairs')
            parts.append(
                f'<p><b>Statements submitted earlier drew more agreement than later '
                f'ones.</b> Across the '
                f'{f"{n_disc:,} occasions" if n_disc else "occasions"} where somebody '
                f'gave different opinions on two similar wordings, the earlier one won '
                f'{effect["order_effect_share_earlier"]:.0%} of the time.</p>')
            parts.append(
                '<p>That is an ordering effect, and it is not the same claim as '
                '“rewriting costs support”. Variants are compared in the order they were '
                'submitted, and later statements were shown to fewer people, so exposure '
                'and order are mixed into this number. It also counts occasions, not '
                'people: one person inside a large family of rewrites contributes many. '
                'No individual pair above is distinguishable from chance at this number '
                'of participants, so treat each as a prompt to read the wording rather '
                'than as a verdict.</p>')

    # ── families ─────────────────────────────────────────────────────────────
    if 'families' in show and descendants is not None and not descendants.empty:
        rewritten = int((descendants['n_children'] > 0).sum())
        derivative = int(descendants['improves_on'].notna().sum())
        parts.append('<h2>Which statements attracted the most rewriting</h2>')
        parts.append(
            f'<p>Participants can propose a rewording of a statement. Here {derivative} '
            f'of {len(descendants)} statements are declared rewrites of another, and '
            f'{rewritten} statements prompted at least one rewrite. A statement with many '
            f'descendants is one people kept trying to get right — a different signal '
            f'from disagreement, and usually a better guide to what still needs work.</p>')
        rename = {'n_children': 'direct rewrites', 'n_descendants': 'rewrites incl. later',
                  'n_voters': 'people', 'agree_pct': 'agreed %', 'text': 'statement'}
        cols = ['tid', 'n_children', 'n_descendants', 'n_voters', 'agree_pct', 'text']
        rewritten_rows = descendants[descendants['n_descendants'] > 0]
        parts.append(f'<div class="tablewrap">'
                     f'{_table(rewritten_rows.head(5)[cols].rename(columns=rename))}</div>')
        rest = rewritten_rows.iloc[5:]
        if not rest.empty:
            parts.append(
                f'<details class="family"><summary>The remaining {len(rest)} statements '
                f'that were rewritten</summary>'
                f'<div class="tablewrap">{_table(rest[cols].rename(columns=rename), max_rows=60)}</div>'
                f'</details>')

        # Parallel rewrites: several people separately making the same change. Sits
        # here rather than inside each family, because the useful question — "where is
        # effort being duplicated?" — is asked across the whole consultation at once.
        parallel_rows = []
        for family in (families or []):
            member_tids = set(int(t) for t in family['members']['tid'])
            close = [(int(r.tid_a), int(r.tid_b)) for r in pairs.itertuples()
                     if r.similarity >= NEAR_IDENTICAL
                     and int(r.tid_a) in member_tids and int(r.tid_b) in member_tids]
            if not close:
                continue
            parent_of = {t: t for t in member_tids}

            def find(x):
                while parent_of[x] != x:
                    parent_of[x] = parent_of[parent_of[x]]
                    x = parent_of[x]
                return x

            for a, bb in close:
                ra, rb = find(a), find(bb)
                if ra != rb:
                    parent_of[rb] = ra
            clusters = {}
            for t in member_tids:
                clusters.setdefault(find(t), []).append(t)
            for members in clusters.values():
                if len(members) > 1:
                    parallel_rows.append({
                        'family': f'#{family["root"]}',
                        'near-identical versions': ', '.join(f'#{t}' for t in sorted(members)),
                        'how many': len(members),
                    })
        if parallel_rows:
            parts.append('<h3>Where the same change was made more than once</h3>')
            parts.append(
                f'<p>{len(parallel_rows)} sets of versions are near-identical to each '
                f'other within their family — separate attempts at the same edit, rather '
                f'than a sequence of improvements. Each set is a candidate for being '
                f'reduced to one option in the next round.</p>')
            parts.append(f'<div class="tablewrap">'
                         f'{_table(pd.DataFrame(parallel_rows), max_rows=40)}</div>')

    if 'generations' in show and generations is not None and not generations.empty:
        parts.append('<h3>Did rewriting build support?</h3>')
        parts.append(
            '<p>Generation 0 is an original statement, generation 1 a rewrite of it, and '
            'so on. Agreement is weighted by how many people gave a clear opinion, so a '
            'statement two people saw does not count the same as one twenty people saw.</p>')
        parts.append(f'<div class="tablewrap">{_table(generations)}</div>')
        parts.append(
            '<p class="footnote">Later generations were also shown to fewer people, so '
            'this decline cannot be separated from falling exposure. It is not evidence '
            'that rewriting makes statements worse.</p>')

    # ── roster ───────────────────────────────────────────────────────────────
    # A pseudonym roster was tried here and removed: looking yourself up in a list of
    # names to learn which group you were put in is a poor thing to ask of a reader,
    # and it is worse when the page has just finished showing that the groups are not
    # distinguishable from no groups. It invited people to adopt a label the analysis
    # does not support. `cluster_roster` is left in place for anyone who needs the
    # mapping for a different purpose.
    if 'roster' in show and roster is not None:
        # Marked as scaffolding rather than as a finding: the honest answer today is
        # "not yet", and a reader should be able to see at a glance that this is the
        # part of the page still being built.
        parts.append('<section class="temporary">')
        parts.append('<h2>Which group were you in? <span class="tag">temporary</span></h2>')
        parts.append(
            '<p><b>This section is temporary and will be replaced when the '
            'consultation finishes.</b></p>')
        # Leading with "we won't tell you" reads as withholding. The true reason is a
        # cannot, not a won't: the analysis was built from data carrying no usernames,
        # so no individual can be looked up in it — including by whoever wrote this.
        parts.append(
            '<p>This page cannot tell you yet. It was built from an export that carries '
            'no usernames and no record of who wrote which statement, so there is no way '
            'to look anyone up in it — including by whoever produced this page.</p>')
        parts.append(
            '<p>That is a limitation of this draft, not the final position. '
            '<b>At the end of the process we intend to publish the data in a form that '
            'lets you find your own opinions in it</b>, through a number the platform '
            'will show only to you.</p>')
        parts.append(
            '<p>Worth being clear about what that will mean: the published data will '
            'show everyone’s opinions side by side, identified by number rather than by '
            'name. Yours will be the only number you can place — but the pattern of how '
            'each person responded will be visible, which is the point of publishing it '
            'at all.</p>')
        parts.append(
            '<p>In the meantime, the groups you would be looking yourself up in are the '
            'ones shown above to be indistinguishable from no grouping at all, so the '
            'label would not have told you much. What is solid here is the opinions '
            'themselves: which statements drew broad agreement and which split the '
            'room.</p>')
        parts.append('</section>')

    # ── shortlist ────────────────────────────────────────────────────────────
    shortlist_start = len(parts)
    if 'shortlist' in show and representatives is not None and not representatives.empty:
        parts.append('<h2>What to put in the next round</h2>')
        parts.append(
            '<p>Where one idea was written several ways, carrying every version forward '
            'asks people to give an opinion repeatedly on the same thing. One version '
            'has to stand '
            'for each family. Below is the best-supported wording in each, judged only '
            'on people who took a side, and only where enough of them did.</p>')
        ready = representatives[representatives['representative_tid'].notna()]
        undecided = representatives[representatives['representative_tid'].isna()]
        if not ready.empty:
            table = ready[['representative_tid', 'n_variants', 'n_decided',
                           'agree_pct', 'is_rewrite', 'status', 'text']].rename(columns={
                'representative_tid': 'statement', 'n_variants': 'versions written',
                'n_decided': 'people', 'agree_pct': 'agreed %',
                'is_rewrite': 'is a rewrite', 'status': 'note'})
            parts.append(f'<div class="tablewrap">{_table(table, max_rows=40)}</div>')
        if not undecided.empty:
            parts.append(
                f'<p><b>{len(undecided)} families still need a decision.</b> No version '
                f'in them was seen by enough people to choose between the wordings — '
                f'these are the ones to put in front of participants again, not to '
                f'resolve from this data.</p>')
            parts.append(f'<div class="tablewrap">'
                         f'{_table(undecided[["best_seen_tid", "n_variants", "n_decided", "text"]].rename(columns={"best_seen_tid": "statement", "n_variants": "versions written", "n_decided": "people"}), max_rows=40)}</div>')

        # The two tables above only cover statements that sit in a declared rewrite
        # family. Statements nobody rewrote were therefore absent from the whole
        # section — including the most-voted statement in the consultation — which made
        # "what to put in the next round" quietly incomplete rather than merely
        # family-scoped.
        if not divergence.empty:
            in_families = set()
            for family in (families or []):
                in_families.update(int(t) for t in family['members']['tid'])
            alone = divergence[(~divergence['tid'].isin(in_families))
                               & divergence['agree_pct'].notna()]
            alone = alone.sort_values(['agree_pct', 'n_decided'], ascending=False)
            if not alone.empty:
                parts.append(
                    f'<p><b>{len(alone)} statements carry opinions and were never '
                    f'rewritten</b>, so no wording choice arises — they either go '
                    f'forward as written or they do not. They belong on the same '
                    f'slate as the picks above.</p>')
                table = alone[['tid', 'agree_pct', 'n_decided', 'statement']].rename(
                    columns={'tid': 'statement id', 'agree_pct': 'agreed %',
                             'n_decided': 'people who took a side',
                             'statement': 'text'})
                parts.append(f'<div class="tablewrap">{_table(table, max_rows=40)}</div>')

    if 'shortlist' in show and not divergence.empty:
        parts.append('<h3>The most divisive statements</h3>')
        parts.append(
            '<p>These split the groups most sharply. They are not necessarily the ones '
            'to drop — a consultation exists to find them — but they are the ones that '
            'will need argument rather than a count.</p>')
        cols = [c for c in divergence.columns if c.startswith('agree_group')]
        # Interleave each group's rate with how many in that group actually took a
        # side. Without it the visible denominator is n_voters (12, 22…), while the
        # 100-point gaps are one or two people in the small group.
        interleaved = []
        for c in cols:
            interleaved.append(c)
            n_col = c.replace('agree_group', 'decided_group')
            if n_col in divergence.columns:
                interleaved.append(n_col)
        top = divergence.dropna(subset=['gap']).head(8)[
            ['tid'] + interleaved + ['gap', 'statement']]
        parts.append(f'<div class="tablewrap">{_table(top)}</div>')
        parts.append(weak_note)

    # Lift the whole recommendations block to the anchor set just after the intro.
    # Built here because it depends on everything above; read there because that is
    # where the organiser looks first.
    if len(parts) > shortlist_start:
        moved = parts[shortlist_start:]
        del parts[shortlist_start:]
        parts[shortlist_anchor:shortlist_anchor] = moved

    # ── caveats ──────────────────────────────────────────────────────────────
    if 'caveats' in show:
        items = ['<li><b>This was not a poll.</b> Everyone here chose to take part, so '
                 'none of it generalises to the wider community, however clean a '
                 'split looks.</li>',
                 '<li><b>Different people saw different statements.</b> Later statements '
                 'were seen by fewer people, so percentages are not directly comparable '
                 'between statements.</li>',
                 f'<li><b>The numbers are small.</b> With {n_real} participants, a '
                 f'handful of opinions moves any percentage here substantially.</li>']
        if audience == 'participant':
            items.append('<li><b>A group label is not an identity.</b> It describes the '
                         'opinions you gave on these statements, in this consultation, '
                         'and nothing else.</li>')
        else:
            items.append('<li><b>Support is not endorsement.</b> A statement can draw '
                         'agreement because it is uncontroversial rather than because '
                         'it is worth adopting.</li>')
        parts.append('<div class="caveats"><h2>How to read this</h2><ul>'
                     + ''.join(items) + '</ul></div>')

    # ── meta ─────────────────────────────────────────────────────────────────
    if 'meta' in show:
        ok = sum(1 for c in checks if c.passed)
        parts.append(
            f'<p class="meta">Generated from an export taken '
            f'{esc(b.manifest_polis["exported_at"])}; {ok} of {len(checks)} data checks '
            f'passed. The grouping shown is the tool\'s own, reproduced independently to '
            f'confirm it. No usernames, and no record of who wrote which statement, were '
            f'included in the data this was built from.</p>')

    parts.append('</main></body></html>')
    path = Path(out)
    path.write_text(_with_contents('\n'.join(parts)), encoding='utf-8')
    return path


def plot_method_comparison(b, conv_key: str, polis_labels: dict, leiden_labels: dict,
                           sweep: pd.DataFrame, matrix, eligible: list[int]):
    """The same agreement matrix, sorted two ways, beside how modularity behaves.

    The point is to let the reader check the grouping rather than trust it. Sorting
    people by their assigned group is the fairest possible test of a clustering: if
    the groups capture something real, the blocks on the diagonal must be visibly
    darker than everything off them. Showing both methods' orderings side by side
    makes it obvious when neither produces blocks — which no summary statistic
    conveys as directly.

    The third panel is why: modularity measures how much more densely a community
    is connected internally than chance would predict. At or below zero there is no
    community structure to find, whatever number of groups gets reported.
    """
    import methods as _m

    pids, weights, _ = _m.agreement_graph(matrix, restrict_pids=eligible)
    fig, axes = plt.subplots(1, 3, figsize=(12.4, 4.3),
                             gridspec_kw={'width_ratios': [1, 1, 0.95]})

    # Both panels are ordered by groupings computed *here*, on the analysed subset —
    # not by the tool's published labels. Titling the first one "the groups Polis
    # reported" invited the reader to check 3/21 against boundary boxes that split
    # 5/17.
    for ax, labels, title in ((axes[0], polis_labels,
                               "Sorted by the tool's method, rerun here"),
                              (axes[1], leiden_labels, 'Sorted by Leiden communities')):
        order = sorted(range(len(pids)), key=lambda i: (labels.get(pids[i], 99), pids[i]))
        shown = weights[np.ix_(order, order)].copy()
        np.fill_diagonal(shown, 1.0)
        im = ax.imshow(shown, cmap=SEQUENTIAL, vmin=0, vmax=1, interpolation='nearest')
        previous = labels.get(pids[order[0]], 99)
        for position, i in enumerate(order):
            current = labels.get(pids[i], 99)
            if current != previous:
                ax.axhline(position - 0.5, color=INK, lw=1.1)
                ax.axvline(position - 0.5, color=INK, lw=1.1)
                previous = current
        ax.set_xticks([]); ax.set_yticks([]); ax.grid(False)
        ax.set_title(title, loc='left', fontsize=10, color=INK)

    cbar = fig.colorbar(im, ax=axes[1], fraction=0.045, pad=0.03)
    cbar.set_label('how often the two agreed', fontsize=8.5, color=INK_SOFT)
    cbar.outline.set_visible(False)

    ax = axes[2]
    ax.axhline(0, color=INK_SOFT, lw=1.2, zorder=2)
    ax.plot(sweep['resolution'], sweep['modularity'], color=SERIES[1], lw=2,
            marker='o', markersize=5, markeredgecolor=SURFACE, markeredgewidth=1.5,
            zorder=3)
    ax.set_xlabel('Leiden resolution setting')
    ax.set_ylabel('modularity')
    ax.yaxis.grid(True, zorder=1)
    # A single community scores exactly 0 by definition, so the flat left-hand
    # stretch is Leiden declining to split at all — not evidence of structure.
    single = sweep[sweep.get('K_leiden', pd.Series([2] * len(sweep))) <= 1]
    if len(single):
        ax.axvspan(sweep['resolution'].min(), single['resolution'].max(),
                   color=GRID, alpha=0.55, zorder=0)
        ax.text(single['resolution'].max(), ax.get_ylim()[0],
                ' everyone in one\n community here', fontsize=8, color=INK_SOFT,
                va='bottom', ha='left')
    ax.text(0.97, 0.93, 'above 0 = real communities', transform=ax.transAxes,
            fontsize=8.5, color=INK_SOFT, va='top', ha='right')
    ax.text(0.97, 0.06, 'below 0 = none to find', transform=ax.transAxes,
            fontsize=8.5, color=INK_SOFT, va='bottom', ha='right')
    ax.set_title('Is there community structure at all?', loc='left', fontsize=10,
                 color=INK)
    fig.tight_layout()
    return fig

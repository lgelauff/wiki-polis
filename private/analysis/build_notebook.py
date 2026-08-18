#!/usr/bin/env python3
"""Regenerate wiki_polis_analysis.ipynb.

The notebook is the deliverable; this builds it. Kept because the notebook is long
and mostly prose — editing it as JSON by hand invites broken cells, and the prose is
easier to review here.

    ./.venv/bin/python build_notebook.py
"""
from __future__ import annotations

import json
from pathlib import Path

NOTEBOOK = Path(__file__).with_name('wiki_polis_analysis.ipynb')
PROVENANCE = Path(__file__).with_name('data_provenance.ipynb')


def md(text: str) -> dict:
    return {'cell_type': 'markdown', 'metadata': {},
            'source': text.strip('\n').splitlines(keepends=True)}


def code(text: str) -> dict:
    return {'cell_type': 'code', 'metadata': {}, 'execution_count': None, 'outputs': [],
            'source': text.strip('\n').splitlines(keepends=True)}


PROVENANCE_CELLS = [
    md('''
# Where the data came from, and what was left out

Companion to `wiki_polis_analysis.ipynb`. Nothing here is needed to read the
findings — this is the audit trail: which queries pulled the data, what was
deliberately excluded, and the checks that ran before any of it was analysed.
'''),

    md('''
## Two databases

wiki-polis splits its data by concern:

| | Database | Holds |
|---|---|---|
| **App** | MariaDB on Toolforge | conversations, who joined, pseudonyms, and **statement provenance** — which statement was submitted as an improvement on which other |
| **Polis** | PostgreSQL on the VPS | statements, every vote, and `math_main` — the clustering the Polis maths service computed |

Neither is read directly. Two exporters run *on the servers* and write a
de-identified bundle; only that bundle travels. The halves join on `person_key`, an
HMAC of the participant's internal id under a salt that never leaves the server.

The queries below are printed from the exporter modules, not copied, so what appears
here is necessarily what ran.
'''),

    code('''
import sys, textwrap
sys.path.insert(0, '.')
import export_polis_bundle as polis_export
import export_app_bundle as app_export

for name in ('Q_CONVERSATION', 'Q_COMMENTS', 'Q_VOTES_LATEST', 'Q_VOTES_HISTORY',
             'Q_PARTICIPANTS', 'Q_IDENTITY', 'Q_MATH_MAIN'):
    print(f'── {name} ' + '─' * (66 - len(name)))
    print(textwrap.dedent(getattr(polis_export, name)).strip())
    print()
'''),

    md('''
Two notes.

**`Q_VOTES_LATEST` reads `votes_latest_unique`, not `votes`.** Polis keeps `votes` as
an append-only log — changing your mind inserts another row — and maintains
`votes_latest_unique` as current state. Counting the log would count people twice.

**`Q_IDENTITY` never reaches the bundle.** It maps each participant to the subject
Particiapi knows them by; the exporter uses it in memory to derive `person_key` and
discards it. Participants shown as `anon-…` have no such record and are deliberately
*not* joinable rather than guessed at.

`Q_COMMENTS` selects the author's `pid`, but the exporter drops it before writing. An
author column is harmless alone; combined with the pseudonym table it would
reconstruct who wrote what.
'''),

    code('''
print('app-side columns written to the bundle:\\n')
for name in ('CONVERSATION_COLUMNS', 'FEATURED_COLUMNS', 'PROVENANCE_COLUMNS',
             'SIMILARITY_COLUMNS', 'PEOPLE_COLUMNS'):
    print(f'  {name:<22} {", ".join(getattr(app_export, name))}')

import bundle
print('\\nnever exported in any mode:\\n')
print(textwrap.fill(', '.join(sorted(bundle.DENIED_COLUMNS)), 78,
                    initial_indent='  ', subsequent_indent='  '))
'''),

    md('''
## Checks that ran before analysis

These run identically on a synthetic test bundle, a local test conversation and real
server data. A check that passes locally and fails here indicates a problem in the
*data*, not in the analysis.

The last one rebuilds "latest vote per person per statement" from the append-only log
and compares it with the table Polis maintains for that purpose. Those can drift —
the Polis schema ships a repair query for exactly this — and every vote count depends
on them agreeing.
'''),

    code('''
import warnings; warnings.filterwarnings('ignore')
import pipeline as P

b = P.load_bundles('2026-nlwiki-arbcom_bundle')
for check in P.integrity_checks(b):
    print(check)
'''),

    md('''
## Personal information

Audited independently of the exporter's own self-check — that check passed on an
earlier bundle which reconstructed statement authorship through a join, so re-running
it would only re-confirm the same blind spot.
'''),

    code('''
!./.venv/bin/python audit_bundle.py 2026-nlwiki-arbcom_bundle effeietsanders ciell
'''),
]


CELLS = [
    md('''
# nl.wikipedia arbitragecommissie — consultation analysis

This notebook takes the raw votes and statements from a wiki-polis consultation and
asks three questions:

1. **Who actually took part?** The results page reports a single participant number.
   That number is more ambiguous than it looks, and the groups shown alongside it are
   drawn over a smaller set of people.
2. **How much clustering is really there?** Polis always reports between two and five
   opinion groups. It never reports "there are no groups". So a second, independent
   method is needed to tell a real division from a tidy partition of noise.
3. **Does phrasing change the answer?** Consultations accumulate near-duplicate
   statements — one proposition in three wordings. For anyone choosing which phrasing
   to put to a vote, the comparison between those variants *is* the decision.

**How to read this.** Every section starts with plain prose saying what is being done
and why. The code cells are thin: the work lives in `pipeline.py` and `methods.py`
next to this file. Where a result is uncertain, the notebook says so rather than
rounding it into a conclusion.

No usernames were exported, and nothing here records who wrote which statement. For
the export queries, the exclusions and the data checks, see the companion notebook
`data_provenance.ipynb`.
'''),

    code('''
import warnings; warnings.filterwarnings('ignore')
import pandas as pd, numpy as np
import pipeline as P, methods as M, report as R

pd.set_option('display.width', 160)
pd.set_option('display.max_colwidth', 70)

BUNDLE = '2026-nlwiki-arbcom_bundle'   # ← the directory copied back from Toolforge
CONV    = None                          # set below from the bundle itself

b = P.load_bundles(BUNDLE)
CONV = b.conversations[0]

print(f'conversation : {CONV}')
print(f'exported     : {b.manifest_polis["exported_at"]}  (env={b.manifest_polis["env"]})')
print(f'salt id      : {b.manifest_polis["salt_id"]}  — matches across both halves')
print(f'statement text included: {b.manifest_polis["with_text"]}')
print(f'pseudonyms included    : {b.manifest_app.get("with_pseudonyms", False)}')
for conv in b.manifest_polis['conversations']:
    print(f'\\n  phase {conv["phase"]}: {conv["n_participants"]} participants, '
          f'{conv["n_statements"]} statements, {conv["n_votes_latest"]:,} current votes, '
          f'math_main={"yes" if conv["has_math_main"] else "MISSING"}')
'''),

    code('''
checks = P.integrity_checks(b)
failed = [c for c in checks if not c.passed]
print(f'data checks: {len(checks) - len(failed)}/{len(checks)} passed'
      + ('' if not failed else '  — see data_provenance.ipynb'))
for check in failed:
    print(' ', check)
'''),

    md('''
## Who actually took part?

The results page shows one number. It counts everyone with **at least one vote,
passes included** — not everyone who joined, and not the people the clustering
actually used.

Polis only clusters participants who voted on at least `min(7, number of statements)`
statements (topping up to 15 if too few qualify). Everyone below that line is present
in the consultation but absent from the opinion groups. The funnel makes each step
explicit.

One step is missing and cannot be recovered: **how many people opened the page**.
wiki-polis deliberately does not log passive page views, so "joined" is the earliest
honest number.
'''),

    code('''
funnel = P.participation_funnel(b, CONV)
display(funnel)
fig = R.plot_funnel(funnel)
'''),

    md('''
## The opinion groups Polis found

The headline result is **the server's own**, read straight out of `math_main` — the
table the Polis math service writes. This notebook does not recompute it and does not
substitute its own clustering for it.

The map below is Polis's own geometry: the two-dimensional projection it computed,
with each participant placed where Polis placed them.
'''),

    code('''
server = P.server_labels(b, CONV, 2)
if server['available']:
    sizes = pd.Series(list(server['labels'].values())).value_counts().sort_index()
    print(f'K = {server["K"]} opinion groups over {server["n_labelled"]} clustered participants')
    for gid, n in sizes.items():
        print(f'  group {gid + 1}: {n} participants')
    print(f'\\nin-conv (met the vote threshold): {len(server["in_conv"])}')
else:
    print('no clustering available:', server['reason'])
'''),

    code('''
fig = R.plot_opinion_map(b, CONV, server)
'''),

    md('''
## Can we reproduce it?

Before drawing any conclusion about *alternatives* to the server's clustering, we have
to show we can reproduce the clustering itself. `polis_replica` is a line-by-line port
of the Polis math service's own PCA and k-means code, pinned to a specific upstream
commit. Running it on the same votes should return the same groups.

If it does, the counterfactuals further down mean something. If it does not, this
notebook reports the server's answer and stops — a model we cannot reproduce is not a
model we can ask "what if" of.
'''),

    code('''
gate = P.reproduction_gate(b, CONV, 2)
print(f'reproduced : {"yes" if gate["passed"] else "NO — " + gate["reason"]}')
print(f'  K         : server {gate["K_server"]}   replica {gate["K_replica"]}')
print(f'  agreement : ARI {gate["ari"]:.3f} over {gate["n_common"]} participants '
      f'(1.0 = identical grouping)')
print(f'  matrix    : {gate["n_participants"]} people × {gate["n_statements"]} statements, '
      f'{gate["density"]:.0%} filled')
print(f'  in-conv   : {gate["n_in_conv"]}  →  the engine could have returned up to '
      f'K={gate["max_k_allowed"]}')
'''),

    md('''
That last line matters for reading K. The engine caps the number of groups at
`min(5, 2 + in-conv ÷ 12)`. With very few participants that cap is 2 — and then
"we found two groups" is a fact about the cap, not about the participants. The line
above says which situation this consultation is in.
'''),

    md('''
## How much clustering is really there?

Polis partitions people into groups because that is what it is for. It does not report
a confidence, and it has no way to say "these people don't really divide". So we ask a
different method, built on a different principle, and see whether it recovers the same
division.

**Leiden community detection** works on a graph rather than a projection. Each
participant is a node; two participants are linked when they voted the same way on the
statements they both voted on. Passes are excluded — a pass is not an opinion — and
pairs with too little overlap are not linked at all, because agreeing on two votes is
not evidence of anything.

Leiden's *resolution* parameter, not the data, decides how many communities come back.
So a single run proves nothing. What is informative is the shape of the sweep: if the
division is real, the number of communities should hold steady across a broad band of
resolutions and agreement with Polis should be high across that band.
'''),

    code('''
sweep = M.leiden_sweep(b, gate)
print(f'graph: {sweep.attrs["n_nodes"]} people, {sweep.attrs["n_edges"]} links, '
      f'median overlap {sweep.attrs["median_overlap"]:.0f} shared votes per pair\\n')
display(sweep)
'''),

    md('''
**Watch the median overlap.** In a consultation with many statements and modest
turnout, two people may have voted on very few of the same statements, and then this
whole graph rests on thin evidence. If that number is small, treat the Leiden result
as a weak second opinion rather than a verdict, and lean on the reproduction gate
above instead.
'''),

    code('''
stability = M.cluster_stability(b, gate)
if stability['available']:
    print(f'{stability["n_runs"]} runs across resolutions and random seeds, '
          f'{stability["n_people"]} people')
    print(f'  pairs that land together (or apart) every single time: '
          f'{stability["pairs_decided"]:.0%}')
    print(f'  people sitting on a boundary between groups: {stability["n_on_boundary"]}')
else:
    print(stability['reason'])
'''),

    md('''
The heatmap below is the visual form of that number. Every clustered participant
appears on both axes; a cell is dark when those two people ended up in the same
community in nearly every run, pale when they nearly never did.

**Two solid dark blocks means the division is real** — the same people keep finding
each other regardless of how the method is tuned. A washed-out or speckled square
means the grouping is an artefact of the settings, and the two "opinion groups" should
not be described as two camps.
'''),

    code('''
fig = R.plot_stability_heatmap(stability, server)
'''),

    md('''
## Where do people agree, and where do they split?

Two different things get called "consensus", and they are worth separating:

- **Broad agreement** — most people agree, and the opinion groups agree *with each
  other*. These are the statements a proposal can safely build on.
- **Division** — the groups disagree with each other. These are the real fault lines,
  and they are what the consultation exists to surface.

Each statement below is drawn once, showing how much each group agreed with it. The
further apart the two marks, the more that statement divides the room.
'''),

    code('''
divergence = R.statement_divergence(b, CONV, server)
display(divergence.head(12))
fig = R.plot_divergence(divergence)
'''),

    md('''
## Near-duplicate statements — the head-to-head

Participants can propose a rewording of an existing statement, and this consultation
accumulated a good number of them. That creates sets of statements saying almost the
same thing with one qualifier changed.

This matters twice over:

- **For the clustering**, near-duplicates are strongly correlated columns. A
  proposition stated three ways carries three times the weight of one stated once, and
  the axis it sits on gets pulled accordingly. That is a property of the wording, not
  of what people think.
- **For whoever writes the final text**, these are the actual decision. If one
  phrasing draws noticeably more support than its near-twin, that is the phrasing to
  put forward — and it is invisible on a results page that lists statements separately.

Groups are formed two ways at once: statements a participant *declared* as an
improvement on another (recorded at submission time), and statements the embedding
model judges near-identical. Declared links are trusted outright; the model catches
rewordings nobody flagged.
'''),

    code('''
groups, pairs = M.similar_statement_groups(b, CONV, threshold=0.85)
print(f'{len(groups)} near-duplicate group(s) found\\n')
for g in groups:
    print(f'group {g.group_id}: {len(g)} variants, {g.n_declared if hasattr(g, "n_declared") else len(g.declared_links)} declared as improvements')
    for tid in g.tids:
        print(f'   [{tid}] {g.texts[tid][:96]}')
    print()
'''),

    md('''
The similarity distribution is worth a look before trusting the threshold — it should
show a clear gap between "same proposition, reworded" and "different proposition on a
related topic". If there is no gap, the threshold is doing arbitrary work.
'''),

    code('''
display(pairs.head(12)[['tid_a', 'tid_b', 'similarity', 'text_a', 'text_b']])
fig = R.plot_similarity_distribution(pairs, threshold=0.85)
'''),

    code('''
head_to_heads = [M.head_to_head(b, CONV, g) for g in groups]
for h in head_to_heads:
    print(f'══ group {h["group_id"]} ' + '═' * 60)
    display(h['variants'])
    if not h['comparisons'].empty:
        display(h['comparisons'])
'''),

    md('''
Read the **common voters** columns, not the raw agreement percentages. Different
variants were submitted at different times, so they were seen by different numbers of
people — comparing their overall agreement compares different populations. Restricting
to people who voted on both makes each person their own control, and that comparison
can carry a claim.
'''),

    code('''
effect = M.wording_effect(head_to_heads)
if effect['available']:
    print(f'{effect["n_pairs_compared"]} variant pairs, '
          f'{effect["n_discordant_votes"]} people voted differently on two wordings '
          f'of the same proposition')
    print(f'  median shift: {effect["median_abs_shift_pct_points"]} percentage points')
    print(f'  largest shift: {effect["max_abs_shift_pct_points"]} percentage points')
    print(f'  p = {effect["p_value"]}\\n')
    print(effect['reading'])
else:
    print(effect['reason'])
'''),

    md('''
## Which group did each pseudonym land in?

Included so participants can find themselves. Pseudonyms only — no usernames are
exported, and nothing here says who wrote which statement.

Everyone who joined appears exactly once, including people the clustering did not
place. Being unplaced is a normal outcome — it means fewer votes than the engine's
threshold — not an omission.
'''),

    code('''
roster = P.cluster_roster(b, CONV)
if roster is None:
    print('no pseudonyms in this bundle (exported without --with-pseudonyms)')
else:
    for placement, rows in roster.groupby('placement'):
        print(f'{placement} — {len(rows)}')
        print(textwrap.fill(', '.join(sorted(rows['pseudonym'])), 96,
                            initial_indent='    ', subsequent_indent='    '))
        print()
'''),

    md('''
## What this analysis cannot tell you

Stated plainly, because a report that only lists findings invites more weight than the
data can carry.

- **A consultation is not a poll.** Participants chose to take part. Nothing here
  generalises to the wider community, no matter how clear a group split looks.
- **Different people saw different statements.** Statements submitted later were seen
  by fewer people. Agreement percentages across statements are therefore not directly
  comparable, which is why the head-to-heads restrict to common voters.
- **Group labels are not identities.** "Group 1" is a position on a set of statements
  in this consultation, nothing more. The stability figure above says how firm even
  that is.
- **An inconclusive wording effect is not evidence that wording does not matter.** At
  this number of participants, only a large effect would be detectable.
'''),

    md('''
## Write the report

Renders everything above as a single self-contained HTML file — no external files, no
network — suitable for sharing with people who will not run this notebook.
'''),

    code('''
path = R.write_report(
    bundle=b, conv_key=CONV, checks=checks, funnel=funnel, server=server, gate=gate,
    sweep=sweep, stability=stability, divergence=divergence, groups=groups,
    pairs=pairs, head_to_heads=head_to_heads, effect=effect, roster=roster,
    out='report_2026-nlwiki-arbcom.html')
print(f'written: {path}')
'''),
]


def main() -> int:
    for path, cells in ((NOTEBOOK, CELLS), (PROVENANCE, PROVENANCE_CELLS)):
        notebook = {
            'cells': cells,
            'metadata': {
                'kernelspec': {'display_name': 'wiki-polis analysis',
                               'language': 'python', 'name': 'wiki-polis-analysis'},
                'language_info': {'name': 'python', 'pygments_lexer': 'ipython3'},
            },
            'nbformat': 4,
            'nbformat_minor': 5,
        }
        path.write_text(json.dumps(notebook, indent=1) + '\n', encoding='utf-8')
        n_md = sum(1 for c in cells if c['cell_type'] == 'markdown')
        print(f'wrote {path.name}: {len(cells)} cells '
              f'({n_md} markdown, {len(cells) - n_md} code)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

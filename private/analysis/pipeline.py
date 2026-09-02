"""Analysis pipeline over a pair of wiki-polis export bundles.

The logic behind `wiki_polis_analysis.ipynb`, kept in a module so it can be tested
and re-run without a kernel. Nothing here touches a database — it reads only the
de-identified bundles produced by the two exporters.

Governing principle: **stay as close to the server as possible.**

  * The headline clustering is the server's own (`math_main.data`, written by the
    stock polis-math Clojure service). We read it; we never recompute it.
  * `polis_replica.run_replica` — the pinned Python port of `pca.clj` /
    `clusters.clj` / `conversation.clj` in the polis-study repo — is used only to
    (a) demonstrate we can reproduce the server's answer on this data, and
    (b) run counterfactuals the server cannot run.
  * Every counterfactual is gated on (a). A conversation whose server result we
    cannot reproduce reports server labels only.

Matrix policy follows polis-study's `matrix_policy.CLOJURE_FAITHFUL`:
owner included, `mod = -1` columns zeroed whole-column, raw Polis signs kept
(-1 agree / +1 disagree / 0 pass).
"""
from __future__ import annotations

import json
import os
import sys
import warnings
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

# polis-study holds the faithful replica. Overridable for a checkout elsewhere.
POLIS_STUDY = Path(os.environ.get(
    'POLIS_STUDY_DIR',
    Path.home() / 'Documents' / 'GitHub' / 'polis-study'))
if str(POLIS_STUDY) not in sys.path:
    sys.path.insert(0, str(POLIS_STUDY))

RAW_AGREE, RAW_DISAGREE, RAW_PASS = -1, 1, 0
EXPECTED_SCHEMA_VERSION = 1

# ─────────────────────────────────────────────────────────────────────────────
# Thresholds. Every cutoff the analysis applies is declared here, so that what
# counts as a participant is a stated decision rather than a number buried in a
# function. The engine-derived ones are marked: changing those makes the analysis
# describe something other than what Polis did.
# ─────────────────────────────────────────────────────────────────────────────

# --- from the Polis engine (conversation.clj) — do not change to taste ---------

#: Votes needed to be clustered. The engine uses min(this, number of statements),
#: so in a short conversation the effective cutoff is lower. This is also the
#: cutoff the analysis uses to decide who counts as a participant, so that the two
#: agree by construction.
POLIS_VOTE_THRESHOLD = 7

#: If fewer than this many people clear the threshold, the engine tops the set up
#: with the next-highest voters regardless. This is why people with 2–6 votes can
#: appear in a clustering, and — because the engine's in-conv set is cumulative
#: and never shrinks — why they stay there for the rest of the conversation.
POLIS_GREEDY_N = 15

#: Upper bound on the number of opinion groups: min(this, 2 + in_conv // 12).
POLIS_MAX_K = 5

# --- our own choices ----------------------------------------------------------

#: A vote landing within this many milliseconds of its statement being created was
#: not cast by a person. Observed machine lags are 5–51 ms; the nearest human vote
#: is orders of magnitude slower, so the gap is wide and the exact value is not
#: delicate.
MACHINE_LAG_MS = 2000

#: Steps reported in the attrition table. Presentation only — no analysis depends
#: on these, and POLIS_VOTE_THRESHOLD is what actually filters.
FUNNEL_THRESHOLDS = (1, 5, POLIS_VOTE_THRESHOLD, 10, 20)

#: Agreement with the server's own clustering required before any counterfactual
#: is reported. Below this we report the server's result and stop.
REPRODUCTION_ARI = 0.95

#: Cosine similarity above which two statements are treated as the same
#: proposition reworded. Check it against the actual similarity distribution
#: before trusting it — it should be cutting a visible gap, not an arbitrary point.
SIMILARITY_THRESHOLD = 0.85

#: Statements two people must both have voted on before their agreement is used as
#: a graph edge. Below this, agreement is noise.
MIN_PAIR_OVERLAP = 5

#: People who voted decisively on both wordings before a head-to-head is tested at
#: all. Thin pairs are still listed, but excluded from the headline.
MIN_DECIDED_FOR_HEAD_TO_HEAD = 8


# ── loading ──────────────────────────────────────────────────────────────────

@dataclass
class Bundles:
    """A loaded (polis, app) bundle pair."""
    root: Path
    manifest_polis: dict
    manifest_app: dict
    polis: dict[str, pd.DataFrame]
    app: dict[str, pd.DataFrame]
    math: dict[tuple[str, int], dict]

    @property
    def conversations(self) -> list[str]:
        return sorted(self.app['conversations']['conv_key'].tolist())

    # Populated by load_bundles: {(conv_key, phase): {pid: reason}}. Machine-made
    # participants are filtered out of every `phase()` read by default, so no
    # analysis has to remember to exclude them. Set `include_machine=True` to get
    # them back — needed only to reproduce what the server's own maths did, since
    # the server counted them.
    machine: dict = field(default_factory=dict)
    include_machine: bool = False

    def phase(self, name: str, conv_key: str, phase: int,
              include_machine: bool | None = None) -> pd.DataFrame:
        df = self.polis[name]
        out = df[(df['conv_key'] == conv_key) & (df['phase'] == phase)].copy()
        keep_machine = self.include_machine if include_machine is None else include_machine
        if keep_machine or 'pid' not in out.columns:
            return out
        drop = set(self.machine.get((conv_key, phase), {}))
        return out[~out['pid'].isin(drop)] if drop else out

    def has_phase6(self, conv_key: str) -> bool:
        return (conv_key, 6) in self.math or not self.phase('votes_latest', conv_key, 6).empty


def load_bundles(root) -> Bundles:
    root = Path(root)
    manifest_polis = json.loads((root / 'manifest_polis.json').read_text())
    manifest_app = json.loads((root / 'manifest_app.json').read_text())

    for name, manifest in (('polis', manifest_polis), ('app', manifest_app)):
        if manifest['schema_version'] != EXPECTED_SCHEMA_VERSION:
            raise ValueError(
                f'{name} bundle is schema v{manifest["schema_version"]}, '
                f'this pipeline expects v{EXPECTED_SCHEMA_VERSION}')

    if manifest_polis['salt_id'] != manifest_app['salt_id']:
        raise ValueError(
            f'salt mismatch: polis bundle salt_id={manifest_polis["salt_id"]}, '
            f'app bundle salt_id={manifest_app["salt_id"]} — the two hosts used '
            'different salts, so person_keys cannot be joined. Re-export with the '
            'same salt file.')
    if manifest_polis['env'] != manifest_app['env']:
        raise ValueError(f'env mismatch: {manifest_polis["env"]} vs {manifest_app["env"]}')

    polis = {name: pd.read_csv(root / 'polis' / f'{name}.csv')
             for name in ('conversations', 'participants', 'statements',
                          'votes_latest', 'votes_history')}
    app = {}
    for name in ('conversations', 'featured_statements', 'statement_provenance',
                 'statement_similarity', 'arguments', 'argument_votes', 'people'):
        path = root / 'app' / f'{name}.csv'
        app[name] = pd.read_csv(path) if path.exists() else pd.DataFrame()

    # The salt check above passes whenever both halves used the same salt file — but
    # they can still hash *different values* under it, which is exactly what happened
    # when the app side hashed the raw xid and the Polis side the conversation-scoped
    # subject. The keys looked well-formed on both sides and joined to nothing, and
    # every pseudonym-linked result silently became empty rather than wrong. Assert the
    # join actually exists, once, at load.
    if not app['people'].empty:
        linked = {k for k in polis['participants']['person_key'].dropna()
                  if not str(k).startswith('anon-')}
        overlap = set(app['people']['person_key'].dropna()) & linked
        if linked and not overlap:
            message = (
                f'person_key join is empty: {len(app["people"])} people in the app '
                f'bundle, {len(linked)} identity-linked participants in the polis '
                f'bundle, 0 in common. The two halves hashed different values under '
                f'the same salt — the app side must hash the conversation-scoped '
                f'subject (see bundle.conversation_subject), not the raw xid. '
                f'Re-export the app half; the polis half is unaffected.')
            # Bundles predating the fix cannot join and never will, so refusing to load
            # them would strand every report built from data already exported. They
            # warn. A bundle whose manifest carries `sub_secret_id` was built by the
            # fixed exporter and has no excuse — that one is an error.
            if manifest_app.get('sub_secret_id'):
                raise ValueError(message)
            warnings.warn(f'{message} (bundle predates the fix — pseudonym-linked '
                          f'results will be empty)', stacklevel=2)

    math = {}
    math_dir = root / 'polis' / 'math_main'
    if math_dir.exists():
        for path in sorted(math_dir.glob('*.json')):
            payload = json.loads(path.read_text())
            math[(payload['conv_key'], int(payload['phase']))] = payload

    bundles = Bundles(root=root, manifest_polis=manifest_polis,
                      manifest_app=manifest_app, polis=polis, app=app, math=math)

    # Identify machine-made participants once, at load, so nothing downstream has to
    # remember. Detection needs a fully built Bundles, hence the second pass with
    # filtering switched off.
    bundles.include_machine = True
    for conv_key in sorted(set(polis['conversations']['conv_key'])):
        for phase in sorted(set(polis['conversations']['phase'])):
            found = machine_participants(bundles, conv_key, int(phase))
            if found:
                bundles.machine[(conv_key, int(phase))] = found
    bundles.include_machine = False
    return bundles


# ── integrity gate ───────────────────────────────────────────────────────────

@dataclass
class Check:
    name: str
    passed: bool
    detail: str = ''

    def __str__(self) -> str:
        return f'[{"PASS" if self.passed else "FAIL"}] {self.name}' + (
            f' — {self.detail}' if self.detail else '')


def integrity_checks(b: Bundles) -> list[Check]:
    """Assertions run identically on a local test export and a production one.

    A failure here on server data that passed locally is a *data* finding, not a
    pipeline bug — which is the whole point of running both through one harness.
    """
    checks: list[Check] = []

    votes = pd.concat([b.phase('votes_latest', c, p)
                       for c in b.conversations for p in (2, 6)], ignore_index=True)
    bad = sorted(set(votes['vote'].unique()) - {RAW_AGREE, RAW_DISAGREE, RAW_PASS})
    checks.append(Check('vote values are raw Polis signs {-1,0,1}', not bad,
                        f'unexpected values: {bad}' if bad else
                        f'{len(votes):,} current votes'))

    stmt_keys = set(map(tuple, b.polis['statements'][['conv_key', 'phase', 'tid']].values))
    vote_keys = set(map(tuple, votes[['conv_key', 'phase', 'tid']].values))
    orphan_votes = vote_keys - stmt_keys
    checks.append(Check('every vote targets a known statement', not orphan_votes,
                        f'{len(orphan_votes)} orphan (conv, phase, tid) combinations'
                        if orphan_votes else ''))

    part_keys = set(map(tuple, b.polis['participants'][['conv_key', 'phase', 'pid']].values))
    vote_pids = set(map(tuple, votes[['conv_key', 'phase', 'pid']].values))
    orphan_pids = vote_pids - part_keys
    checks.append(Check('every vote has a participant row', not orphan_pids,
                        f'{len(orphan_pids)} pids voting without a participants row'
                        if orphan_pids else ''))

    # The votes RULE that maintains votes_latest_unique is known to drift; the
    # Polis schema even ships a repair query for it. Rebuild and compare.
    history = pd.concat([b.phase('votes_history', c, p)
                         for c in b.conversations for p in (2, 6)], ignore_index=True)
    if history.empty:
        checks.append(Check('votes_latest_unique matches the vote history', True,
                            'no history exported — skipped'))
    else:
        rebuilt = (history.sort_values('created_ms')
                          .groupby(['conv_key', 'phase', 'pid', 'tid'], as_index=False)
                          .last()[['conv_key', 'phase', 'pid', 'tid', 'vote']])
        merged = rebuilt.merge(votes[['conv_key', 'phase', 'pid', 'tid', 'vote']],
                               on=['conv_key', 'phase', 'pid', 'tid'],
                               how='outer', suffixes=('_rebuilt', '_stored'),
                               indicator=True)
        drift = merged[(merged['_merge'] != 'both') |
                       (merged['vote_rebuilt'] != merged['vote_stored'])]
        checks.append(Check('votes_latest_unique matches the vote history', drift.empty,
                            f'{len(drift)} row(s) differ — the on_vote_insert RULE has '
                            'drifted; see the repair query in the Polis schema'
                            if not drift.empty else f'{len(rebuilt):,} rows agree'))

    # Provenance: parents must exist as Phase 2 statements in the same conversation.
    prov = b.app['statement_provenance']
    if prov.empty:
        checks.append(Check('every derived_from_tid resolves to a statement', True,
                            'no provenance rows in this export — skipped'))
    else:
        phase2 = {(r.conv_key, r.tid) for r in
                  b.polis['statements'][b.polis['statements']['phase'] == 2].itertuples()}
        missing = [(r.conv_key, r.derived_from_tid) for r in prov.itertuples()
                   if (r.conv_key, r.derived_from_tid) not in phase2]
        checks.append(Check('every derived_from_tid resolves to a statement', not missing,
                            f'unresolved parents: {missing[:5]}' if missing
                            else f'{len(prov)} provenance link(s)'))
        self_links = prov[prov['polis_statement_id'] == prov['derived_from_tid']]
        checks.append(Check('no statement is its own parent', self_links.empty,
                            f'{len(self_links)} self-link(s)' if not self_links.empty else ''))

    # The Phase 2 ↔ Phase 6 statement bridge.
    featured = b.app['featured_statements']
    for conv_key in b.conversations:
        if not b.has_phase6(conv_key):
            continue
        conf = featured[(featured['conv_key'] == conv_key) & featured['confirmed_by_admin']]
        # tid 0 is a real tid: test for null, never for truthiness.
        bridged = conf['phase6_polis_statement_id'].notna().sum()
        checks.append(Check(f'{conv_key}: confirmed featured statements bridged to Phase 6',
                            bridged == len(conf),
                            f'{bridged}/{len(conf)} bridged'))

    for conv_key in b.conversations:
        for phase in (2, 6):
            if (conv_key, phase) not in b.math and not b.phase('votes_latest', conv_key, phase).empty:
                checks.append(Check(f'{conv_key} phase {phase}: math_main present', False,
                                    'no math_main row — the math service has not run, or '
                                    'the conversation was exported before it did'))
    return checks


# ── machine-generated participants ───────────────────────────────────────────

def machine_participants(b: Bundles, conv_key: str, phase: int = 2,
                         max_lag_ms: int = MACHINE_LAG_MS) -> dict[int, str]:
    """Participants that are not people. Returns {pid: reason}.

    Submitting a statement through wiki-polis opens a Particiapi session without
    asserting the author's identity, so Particiapi's "agree with your own statement"
    lands on a fresh unbound uid. Polis then holds a participant row with votes and
    no way to tell it apart from a person — its own maths counts it.

    Detection is behavioural, not identity-based: a participant qualifies only if
    *every* vote it cast landed within `max_lag_ms` of that statement being created.
    Observed lags here are 5–51 ms; no human votes that fast, and no human votes only
    that fast. Using `identity_linked` alone would be wrong — a real person can lack
    an identity record for unrelated reasons, and would then be silently deleted.
    """
    votes = b.phase('votes_latest', conv_key, phase)
    statements = b.phase('statements', conv_key, phase)
    if votes.empty or statements.empty:
        return {}

    created = dict(zip(statements['tid'], statements['created_ms']))
    seeds = set(statements.loc[statements['is_seed'].astype(bool), 'tid'])

    flagged: dict[int, str] = {}
    for pid, block in votes.groupby('pid'):
        lags = [row.modified_ms - created.get(row.tid, row.modified_ms)
                for row in block.itertuples()]
        if not lags or max(lags) > max_lag_ms or min(lags) < 0:
            continue
        on_seeds = sum(1 for row in block.itertuples() if row.tid in seeds)
        flagged[int(pid)] = ('seeding account — passes on seed statements only'
                             if on_seeds == len(block)
                             else 'statement-author auto-agree')
    return flagged


def auto_agree_votes(b: Bundles, conv_key: str, phase: int = 2,
                     max_lag_ms: int = MACHINE_LAG_MS) -> dict:
    """The automatic agreement the tool records when a statement is submitted.

    Submitting a statement — new, or a reworded version of another — registers an
    agree vote on it on the submitter's behalf. Those votes are indistinguishable
    from considered ones in the vote table, so they are identified the same way
    machine accounts are: by landing within `max_lag_ms` of the statement being
    created. Nobody reads and votes that fast.

    Where they land decides whether they count. An auto-agree on an unbound session
    lands on a machine pid and is dropped with it; one on a properly bound account
    lands on the author and is counted as an ordinary agree vote, inflating that
    statement's support by one. The reports say which happened rather than assuming,
    because it depends on a bug whose fix would change the answer.

    Authorship is not in the export, so this cannot say who submitted what — only
    how many of these votes exist and whether they survive into the analysis.
    """
    votes = b.phase('votes_latest', conv_key, phase, include_machine=True)
    statements = b.phase('statements', conv_key, phase, include_machine=True)
    if votes.empty or statements.empty:
        return {'total': 0, 'on_machine': 0, 'on_real': 0, 'statements': 0}

    created = dict(zip(statements['tid'], statements['created_ms']))
    lag = votes['modified_ms'] - votes['tid'].map(created)
    auto = votes[(lag >= 0) & (lag <= max_lag_ms)]
    machine = set(b.machine.get((conv_key, phase), {}))
    on_machine = int(auto['pid'].isin(machine).sum())
    return {'total': len(auto), 'on_machine': on_machine,
            'on_real': len(auto) - on_machine,
            'statements': int(auto['tid'].nunique())}


# ── matrix build (matrix_policy.CLOJURE_FAITHFUL) ────────────────────────────

@dataclass
class Matrix:
    conv_key: str
    phase: int
    values: np.ndarray                 # (n_ptpt, n_cmt), NaN = did not vote
    pids: list[int]
    tids: list[int]
    person_keys: list[str]
    notes: dict = field(default_factory=dict)

    @property
    def density(self) -> float:
        return float(np.mean(~np.isnan(self.values)))


def build_matrix(b: Bundles, conv_key: str, phase: int, *,
                 mod_out: str = 'zero', include_owner: bool = True,
                 restrict_tids: list[int] | None = None,
                 include_machine: bool = False, drop_unvoted: bool = True) -> Matrix:
    """Participant × statement matrix under the Clojure-faithful policy.

    mod_out: 'zero'  — whole column of a `mod = -1` statement set to 0, including
                       non-voters (named_matrix/zero-out-columns). The default and
                       the only engine-faithful option.
             'keep'  — leave the real votes in place.
             'drop'  — remove the column entirely.
    """
    if mod_out not in ('zero', 'keep', 'drop'):
        raise ValueError(f'mod_out must be zero|keep|drop, got {mod_out!r}')

    votes = b.phase('votes_latest', conv_key, phase, include_machine=include_machine)
    statements = b.phase('statements', conv_key, phase)
    participants = b.phase('participants', conv_key, phase,
                           include_machine=include_machine)
    if votes.empty:
        raise LookupError(f'{conv_key} phase {phase}: no votes in this bundle')

    tids = sorted(statements['tid'].tolist())
    if restrict_tids is not None:
        keep = set(restrict_tids)
        tids = [t for t in tids if t in keep]
    moderated_out = set(statements.loc[statements['mod'] == -1, 'tid'])
    if mod_out == 'drop':
        tids = [t for t in tids if t not in moderated_out]

    pids = sorted(participants['pid'].tolist())
    if not include_owner and pids:
        pids = [p for p in pids if p != 0]

    pid_row = {pid: i for i, pid in enumerate(pids)}
    tid_col = {tid: j for j, tid in enumerate(tids)}
    values = np.full((len(pids), len(tids)), np.nan)
    for row in votes.itertuples():
        i, j = pid_row.get(row.pid), tid_col.get(row.tid)
        if i is not None and j is not None:
            values[i, j] = row.vote

    # Statements nobody voted on carry no information: they are an empty column that
    # the engine fills with zeros. Dropping them does not change the grouping, but it
    # stops the statement count overstating what was actually deliberated. They are
    # still reported to the organiser — an unvoted proposal is a finding about
    # exposure, not something to hide.
    dropped_unvoted = 0
    if drop_unvoted:
        voted = set(votes['tid'])
        keep = [j for j, tid in enumerate(tids) if tid in voted]
        dropped_unvoted = len(tids) - len(keep)
        if dropped_unvoted:
            values = values[:, keep]
            tids = [tids[j] for j in keep]
            tid_col = {tid: j for j, tid in enumerate(tids)}

    zeroed = 0
    if mod_out == 'zero':
        for tid in moderated_out & set(tid_col):
            values[:, tid_col[tid]] = 0.0     # whole column, non-voters included
            zeroed += 1

    key_by_pid = dict(zip(participants['pid'], participants['person_key']))
    return Matrix(
        conv_key=conv_key, phase=phase, values=values, pids=pids, tids=tids,
        person_keys=[key_by_pid.get(p, '') for p in pids],
        notes={'mod_out': mod_out, 'include_owner': include_owner,
               'n_moderated_out': len(moderated_out), 'n_columns_zeroed': zeroed,
               'n_unvoted_dropped': dropped_unvoted,
               'restricted': restrict_tids is not None},
    )


# ── the server's own clustering ──────────────────────────────────────────────

def _get(node, *names):
    """math_main JSON uses Clojure-ish keys; accept a few spellings."""
    if not isinstance(node, dict):
        return None
    for name in names:
        if name in node:
            return node[name]
    return None


def server_labels(b: Bundles, conv_key: str, phase: int) -> dict:
    """Per-pid group label straight out of `math_main.data`.

    Polis stores base clusters (k=100 buckets of participants) and group clusters
    (the 2–5 opinion groups, whose members are *base cluster ids*). A participant's
    group is therefore found by walking group → base-cluster → member pids.
    """
    payload = b.math.get((conv_key, phase))
    if payload is None:
        return {'available': False, 'reason': 'no math_main in the bundle'}

    data = payload['data']
    base = _get(data, 'base-clusters', 'base_clusters')
    groups = _get(data, 'group-clusters', 'group_clusters')
    if base is None or groups is None:
        return {'available': False, 'reason': 'math_main has no cluster keys',
                'keys': sorted(data.keys()) if isinstance(data, dict) else None}

    # base-clusters is a struct-of-arrays: {id: [...], members: [[pid,...], ...]}
    base_members: dict[int, list[int]] = {}
    if isinstance(base, dict):
        ids = _get(base, 'id', 'ids') or []
        members = _get(base, 'members') or []
        for bid, mem in zip(ids, members):
            base_members[int(bid)] = [int(m) for m in mem]
    else:                                    # list-of-maps fallback
        for entry in base:
            base_members[int(_get(entry, 'id'))] = [int(m) for m in (_get(entry, 'members') or [])]

    labels: dict[int, int] = {}
    for gi, group in enumerate(groups):
        gid = _get(group, 'id')
        gid = gi if gid is None else int(gid)
        for bid in (_get(group, 'members') or []):
            for pid in base_members.get(int(bid), []):
                labels[pid] = gid

    in_conv = _get(data, 'in-conv', 'in_conv') or []
    return {
        'available': True,
        'labels': labels,
        'K': len(groups),
        'n_labelled': len(labels),
        'in_conv': [int(p) for p in in_conv],
        'math_tick': payload.get('math_tick'),
        'last_vote_timestamp': payload.get('last_vote_timestamp'),
        'math_env': payload.get('math_env'),
    }


# ── participation funnel ─────────────────────────────────────────────────────

def participation_funnel(b: Bundles, conv_key: str, phase: int = 2) -> pd.DataFrame:
    """How many people reached each level of participation.

    The results page reports a single "N participants", which is the number of
    people with **at least one vote row, passes included** — not the number who
    joined, and not the number the clustering actually used. Those are three
    different populations and the gap between them is often large:

      joined            — accepted the conversation (app DB `participations`)
      voted ≥1          — the number the results page currently shows
      voted ≥7          — Polis's own clustering threshold, min(7, n_statements)
      in-conv           — who the math actually clustered, after the threshold
                          and its greedy top-up to 15
      clustered         — who ended up with a group label

    "Opened the conversation" is deliberately not tracked (passive page views are
    not logged), so `joined` is the earliest step we can honestly report.
    """
    votes = b.phase('votes_latest', conv_key, phase)
    statements = b.phase('statements', conv_key, phase)
    server = server_labels(b, conv_key, phase)

    per_person = votes.groupby('person_key').size()
    n_statements = len(statements)

    rows = []
    app_conv = b.app['conversations']
    joined = app_conv.loc[app_conv['conv_key'] == conv_key, 'n_participations'] \
        if 'n_participations' in app_conv.columns else None
    # Machine-made accounts are excluded upstream and deliberately do not appear as
    # a row here. They are not a step people fall out of — they were never people,
    # and giving them a line in a table about participation implies otherwise. The
    # discrepancy with the live results page is explained once, in prose.
    machine = b.machine.get((conv_key, phase), {})
    if joined is not None and len(joined):
        rows.append({'step': 'people who joined the conversation',
                     'n_people': int(joined.iloc[0]),
                     'note': 'app database'})

    for threshold in FUNNEL_THRESHOLDS:
        if threshold > 1 and threshold > n_statements:
            continue
        rows.append({'step': f'gave an opinion on ≥{threshold} statement(s)',
                     'n_people': int((per_person >= threshold).sum()),
                     'note': 'the number the results page shows' if threshold == 1 else ''})

    threshold = min(POLIS_VOTE_THRESHOLD, n_statements)
    rows.append({'step': f'ANALYSED HERE: ≥{threshold} opinions',
                 'n_people': int((per_person >= threshold).sum()),
                 'note': "Polis's own clustering cutoff, min(7, statements)"})

    if server['available']:
        # Report only the real people the tool placed. The count it published also
        # includes machine-made accounts, but that is a defect to fix rather than a
        # number to explain to readers.
        real_clustered = len(set(server['labels']) - set(machine))
        rows.append({'step': 'placed into an opinion group',
                     'n_people': real_clustered,
                     'note': f'K={server["K"]}'})

    out = pd.DataFrame(rows)
    out['pct_of_voters'] = (out['n_people'] /
                            max(int((per_person >= 1).sum()), 1) * 100).round(1)
    return out


def cluster_roster(b: Bundles, conv_key: str, phase: int = 2) -> pd.DataFrame | None:
    """Which pseudonyms ended up in which opinion group.

    Needs a bundle exported with `--with-pseudonyms`; returns None otherwise.

    Everyone who voted appears exactly once, including people the clustering did
    not place — a participant looking for their own pseudonym should always find
    it, and "not placed" is a real, explainable outcome (too few votes to be
    clustered), not an omission.
    """
    people = b.app['people']
    if people.empty:
        return None
    people = people[people['conv_key'] == conv_key]
    if people.empty:
        return None

    votes = b.phase('votes_latest', conv_key, phase)
    participants = b.phase('participants', conv_key, phase)
    server = server_labels(b, conv_key, phase)

    key_by_pid = dict(zip(participants['pid'], participants['person_key']))
    group_by_key = {}
    if server['available']:
        group_by_key = {key_by_pid[pid]: lab for pid, lab in server['labels'].items()
                        if pid in key_by_pid}

    vote_counts = votes.groupby('person_key').size()
    rows = []
    for person in people.itertuples():
        n_votes = int(vote_counts.get(person.person_key, 0))
        if n_votes == 0:
            placement = 'joined, did not vote'
        elif person.person_key in group_by_key:
            placement = f'group {group_by_key[person.person_key] + 1}'
        else:
            placement = 'not placed (too few votes to cluster)'
        rows.append({'pseudonym': person.pseudonym, 'n_votes': n_votes,
                     'placement': placement})
    out = pd.DataFrame(rows).sort_values(['placement', 'pseudonym'])
    return out.reset_index(drop=True)


# ── the reproduction gate ────────────────────────────────────────────────────

def replica_labels(matrix: Matrix, *, vote_counts: dict[int, int] | None = None,
                   **kwargs) -> dict:
    """Run the pinned replica, correcting who counts as "in conversation".

    `run_replica` derives in-conv by counting non-NaN cells in the matrix it is
    given. That is right for a plain vote matrix and wrong for ours: the
    Clojure-faithful `mod_out='zero'` policy sets the *whole* column of a
    moderated-out statement to 0, including for people who never voted on it, so
    those filled cells would count as votes and everyone would clear the threshold.

    The engine does not work that way. `conversation.clj` computes `:in-conv` from
    `user-vote-counts` — a separate tally of actual votes — while the zeroing applies
    only to `:rating-mat`. Passing real vote counts here restores that separation.

    The correction is applied after clustering rather than inside it, because
    `run_replica` takes no in-conv argument and it lives in another repository. The
    residual difference: base k-means sees the extra rows before they are dropped.
    Where the reproduction gate passes, that difference is demonstrably immaterial.
    """
    from analysis.polis_replica import run_replica
    result = run_replica(matrix.values, **kwargs)
    labels = {pid: int(lab) for pid, lab in zip(matrix.pids, result['labels']) if lab != -1}
    in_conv = [matrix.pids[i] for i in result['in_conv']]

    if vote_counts is not None:
        threshold = min(POLIS_VOTE_THRESHOLD, len(matrix.tids))
        qualified = {pid for pid, n in vote_counts.items() if n >= threshold}
        if len(qualified) < POLIS_GREEDY_N:      # the engine's greedy top-up
            for pid, _ in sorted(vote_counts.items(), key=lambda kv: -kv[1]):
                if len(qualified) >= POLIS_GREEDY_N:
                    break
                qualified.add(pid)
        labels = {pid: lab for pid, lab in labels.items() if pid in qualified}
        in_conv = [pid for pid in in_conv if pid in qualified]

    return {'labels': labels, 'K': int(result['K']),
            'silhouettes': result.get('silhouettes', {}), 'in_conv': in_conv}


def real_vote_counts(b: Bundles, conv_key: str, phase: int,
                     include_machine: bool = False) -> dict[int, int]:
    """Votes actually cast per participant — the engine's `user-vote-counts`."""
    votes = b.phase('votes_latest', conv_key, phase, include_machine=include_machine)
    return votes.groupby('pid').size().to_dict()


def compare_labels(a: dict[int, int], bb: dict[int, int]) -> tuple[float, int]:
    """Adjusted Rand Index over the pids labelled by both."""
    from sklearn.metrics import adjusted_rand_score
    common = sorted(set(a) & set(bb))
    if len(common) < 2:
        return float('nan'), len(common)
    return float(adjusted_rand_score([a[p] for p in common], [bb[p] for p in common])), len(common)


def reproduction_gate(b: Bundles, conv_key: str, phase: int) -> dict:
    """Can the pinned replica reproduce this conversation's server clustering?

    Passing licenses the counterfactuals below. Failing does not invalidate the
    server's own result — it means we may not reason about *alternatives* to it.
    """
    server = server_labels(b, conv_key, phase)
    # The server clustered whatever was in its database, machine-made accounts and
    # all. Reproducing it therefore means feeding the replica the same population;
    # filtering here would compare two different things and fail for the wrong reason.
    matrix = build_matrix(b, conv_key, phase, include_machine=True)
    if not server['available']:
        return {'conv_key': conv_key, 'phase': phase, 'passed': False,
                'reason': server['reason'], 'matrix': matrix, 'server': server}

    replica = replica_labels(
        matrix, vote_counts=real_vote_counts(b, conv_key, phase, include_machine=True))
    ari, n_common = compare_labels(server['labels'], replica['labels'])
    passed = bool(server['K'] == replica['K'] and ari >= REPRODUCTION_ARI)
    return {
        'conv_key': conv_key, 'phase': phase, 'passed': passed,
        'K_server': server['K'], 'K_replica': replica['K'],
        'ari': ari, 'n_common': n_common,
        'n_participants': len(matrix.pids), 'n_statements': len(matrix.tids),
        'density': matrix.density,
        'n_in_conv': len(replica['in_conv']),
        'max_k_allowed': max_k_allowed(len(replica['in_conv'])),
        'server': server, 'replica': replica, 'matrix': matrix,
        'reason': '' if passed else
                  f'K {server["K"]}≠{replica["K"]}' if server['K'] != replica['K']
                  else f'ARI {ari:.3f} < {REPRODUCTION_ARI}',
    }


def max_k_allowed(n_in_conv: int, max_max_k: int = POLIS_MAX_K) -> int:
    """conversation.clj max-k-fn. Below 12 in-conversation participants the engine
    can only ever return K=2, so "we found two groups" is a threshold artefact."""
    return min(max_max_k, 2 + n_in_conv // 12)


# ── counterfactuals (gated) ──────────────────────────────────────────────────

def lineage_root(prov: pd.DataFrame, conv_key: str, tid: int) -> int:
    """Walk derived_from_tid up to the root of the lineage. Cycle-safe, mirroring
    `_lineage_group` in the app."""
    by_tid = dict(zip(prov.loc[prov['conv_key'] == conv_key, 'polis_statement_id'],
                      prov.loc[prov['conv_key'] == conv_key, 'derived_from_tid']))
    seen = {tid}
    cur = tid
    while cur in by_tid:
        parent = int(by_tid[cur])
        if parent in seen:
            break
        seen.add(parent)
        cur = parent
    return cur


def collapse_lineages(b: Bundles, matrix: Matrix) -> Matrix:
    """Merge each lineage of derivative statements into its root column.

    A near-duplicate statement and its rewording are two highly correlated columns,
    which PCA reads as extra evidence for whatever axis they sit on. Collapsing them
    asks: how much of the group structure is carried by the duplication itself?
    A participant who voted on several members of one lineage contributes the mean
    of those votes; sign is preserved because all members restate one proposition.
    """
    prov = b.app['statement_provenance']
    if prov.empty:
        return matrix

    roots = {tid: lineage_root(prov, matrix.conv_key, tid) for tid in matrix.tids}
    groups: dict[int, list[int]] = {}
    for tid, root in roots.items():
        groups.setdefault(root, []).append(tid)

    new_tids = sorted(groups)
    col = {tid: j for j, tid in enumerate(matrix.tids)}
    values = np.full((len(matrix.pids), len(new_tids)), np.nan)
    for j, root in enumerate(new_tids):
        members = [col[t] for t in groups[root]]
        block = matrix.values[:, members]
        # A participant who voted on no member of this lineage stays NaN; nanmean
        # warns on that all-NaN slice, which is the expected case, not a problem.
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', RuntimeWarning)
            merged = np.nanmean(block, axis=1)
        values[:, j] = merged

    notes = dict(matrix.notes)
    notes.update({'lineage_collapsed': True,
                  'n_columns_before': len(matrix.tids),
                  'n_columns_after': len(new_tids),
                  'n_lineages_merged': sum(1 for g in groups.values() if len(g) > 1)})
    return Matrix(conv_key=matrix.conv_key, phase=matrix.phase, values=values,
                  pids=matrix.pids, tids=new_tids, person_keys=matrix.person_keys,
                  notes=notes)


def counterfactuals(b: Bundles, gate: dict) -> pd.DataFrame:
    """Re-cluster under alternative policies and report the drift from the faithful
    baseline. Only meaningful for a conversation that passed the reproduction gate."""
    if not gate['passed']:
        raise ValueError(f'{gate["conv_key"]} phase {gate["phase"]} did not pass the '
                         f'reproduction gate ({gate["reason"]}) — no counterfactuals')

    conv_key, phase = gate['conv_key'], gate['phase']
    baseline = gate['replica']['labels']
    rows = [{'variant': 'faithful baseline', 'K': gate['K_replica'],
             'ari_vs_baseline': 1.0, 'n_common': len(baseline), 'detail': ''}]

    collapsed = collapse_lineages(b, gate['matrix'])
    if collapsed.notes.get('lineage_collapsed'):
        result = replica_labels(collapsed)
        ari, n = compare_labels(baseline, result['labels'])
        rows.append({'variant': 'lineages collapsed', 'K': result['K'],
                     'ari_vs_baseline': ari, 'n_common': n,
                     'detail': f'{collapsed.notes["n_columns_before"]}→'
                               f'{collapsed.notes["n_columns_after"]} columns, '
                               f'{collapsed.notes["n_lineages_merged"]} lineage(s) merged'})

    for mod_out in ('keep', 'drop'):
        matrix = build_matrix(b, conv_key, phase, mod_out=mod_out)
        if matrix.notes['n_moderated_out'] == 0:
            rows.append({'variant': f'moderated-out: {mod_out}', 'K': gate['K_replica'],
                         'ari_vs_baseline': 1.0, 'n_common': len(baseline),
                         'detail': 'no moderated-out statements — identical to baseline'})
            continue
        result = replica_labels(matrix)
        ari, n = compare_labels(baseline, result['labels'])
        rows.append({'variant': f'moderated-out: {mod_out}', 'K': result['K'],
                     'ari_vs_baseline': ari, 'n_common': n,
                     'detail': f'{matrix.notes["n_moderated_out"]} statement(s) affected'})

    for base_k in ('50', '200'):
        previous = os.environ.get('POLIS_BASE_K')
        os.environ['POLIS_BASE_K'] = base_k
        try:
            result = replica_labels(gate['matrix'])
        finally:
            if previous is None:
                os.environ.pop('POLIS_BASE_K', None)
            else:
                os.environ['POLIS_BASE_K'] = previous
        ari, n = compare_labels(baseline, result['labels'])
        rows.append({'variant': f'base-K = {base_k}', 'K': result['K'],
                     'ari_vs_baseline': ari, 'n_common': n,
                     'detail': 'engine default is 100'})

    return pd.DataFrame(rows)


# ── Phase 2 → Phase 6 ────────────────────────────────────────────────────────

def phase_bridge(b: Bundles, conv_key: str) -> pd.DataFrame:
    """Confirmed featured statements with both tids. The only legitimate way to
    line up statements across the two Polis conversations."""
    featured = b.app['featured_statements']
    conf = featured[(featured['conv_key'] == conv_key) &
                    featured['confirmed_by_admin'] &
                    featured['phase6_polis_statement_id'].notna()].copy()
    conf['phase6_polis_statement_id'] = conf['phase6_polis_statement_id'].astype(int)
    return conf[['polis_statement_id', 'phase6_polis_statement_id', 'statement_text']]


def compare_phases(b: Bundles, conv_key: str) -> dict:
    """Did the informed round move people, and did it move them together?

    Both rounds are restricted to the bridged featured statements so the comparison
    is over one statement set — otherwise K and geometry differ merely because
    Phase 6 has fewer statements.
    """
    bridge = phase_bridge(b, conv_key)
    if bridge.empty:
        return {'available': False, 'reason': 'no bridged featured statements'}

    p2 = b.phase('votes_latest', conv_key, 2)
    p6 = b.phase('votes_latest', conv_key, 6)
    if p2.empty or p6.empty:
        return {'available': False, 'reason': 'one of the two rounds has no votes'}

    tid6_by_tid2 = dict(zip(bridge['polis_statement_id'],
                            bridge['phase6_polis_statement_id']))
    p2 = p2[p2['tid'].isin(tid6_by_tid2)].copy()
    p2['stmt'] = p2['tid'].map(tid6_by_tid2)
    p6 = p6[p6['tid'].isin(set(tid6_by_tid2.values()))].copy()
    p6['stmt'] = p6['tid']

    paired = p2.merge(p6, on=['person_key', 'stmt'], suffixes=('_p2', '_p6'))
    people_p2 = set(p2['person_key'])
    people_p6 = set(p6['person_key'])
    linked = people_p2 & people_p6
    anon = {k for k in people_p2 | people_p6 if str(k).startswith('anon-')}

    per_statement = None
    if not paired.empty:
        per_statement = (paired.groupby('stmt')
                         .apply(lambda g: pd.Series({
                             'n_common_voters': len(g),
                             'agree_p2': float((g['vote_p2'] == RAW_AGREE).mean()),
                             'agree_p6': float((g['vote_p6'] == RAW_AGREE).mean()),
                             'n_changed': int((g['vote_p2'] != g['vote_p6']).sum()),
                         }), include_groups=False)
                         .reset_index())
        per_statement['agree_shift'] = per_statement['agree_p6'] - per_statement['agree_p2']
        text_by_tid6 = dict(zip(bridge['phase6_polis_statement_id'], bridge['statement_text']))
        per_statement['statement'] = per_statement['stmt'].map(text_by_tid6)

    return {
        'available': True,
        'n_bridged_statements': len(bridge),
        'n_people_phase2': len(people_p2),
        'n_people_phase6': len(people_p6),
        'n_people_linked': len(linked),
        'n_people_anonymous': len(anon),
        'n_paired_votes': len(paired),
        'paired': paired,
        'per_statement': per_statement,
        'linkage_note': (
            'no person voted in both rounds — either the rounds had different '
            'participants, or trusted-sub identity was off and each session got its '
            'own uid (see ref_cross-device-identity.md)') if not linked else '',
    }


def cluster_migration(b: Bundles, conv_key: str) -> pd.DataFrame | None:
    """Where did each Phase 2 opinion group end up in the informed round?"""
    server2 = server_labels(b, conv_key, 2)
    server6 = server_labels(b, conv_key, 6)
    if not (server2['available'] and server6['available']):
        return None

    key2 = dict(zip(b.phase('participants', conv_key, 2)['pid'],
                    b.phase('participants', conv_key, 2)['person_key']))
    key6 = dict(zip(b.phase('participants', conv_key, 6)['pid'],
                    b.phase('participants', conv_key, 6)['person_key']))
    g2 = {key2[pid]: lab for pid, lab in server2['labels'].items() if pid in key2}
    g6 = {key6[pid]: lab for pid, lab in server6['labels'].items() if pid in key6}
    common = sorted(set(g2) & set(g6) - {k for k in g2 if str(k).startswith('anon-')})
    if not common:
        return None
    return (pd.crosstab(pd.Series([g2[k] for k in common], name='phase 2 group'),
                        pd.Series([g6[k] for k in common], name='phase 6 group')))


# ── derivative statements ────────────────────────────────────────────────────

def derivative_analysis(b: Bundles, conv_key: str) -> pd.DataFrame | None:
    """Parent vs derivative, judged only on the people who voted on both.

    Reports the agreement rate on each, the shift, and how many voters switched
    side between a statement and its rewording — with the similarity score the app
    recorded at submission time, so "how different was the wording" can be set
    against "how differently did people vote".
    """
    prov = b.app['statement_provenance']
    if prov.empty:
        return None
    prov = prov[prov['conv_key'] == conv_key]
    if prov.empty:
        return None

    votes = b.phase('votes_latest', conv_key, 2)
    statements = b.phase('statements', conv_key, 2).set_index('tid')
    similarity = b.app['statement_similarity']
    sim = similarity[similarity['conv_key'] == conv_key] if not similarity.empty else pd.DataFrame()

    rows = []
    for link in prov.itertuples():
        child, parent = int(link.polis_statement_id), int(link.derived_from_tid)
        vc = votes[votes['tid'] == child][['person_key', 'vote']]
        vp = votes[votes['tid'] == parent][['person_key', 'vote']]
        both = vc.merge(vp, on='person_key', suffixes=('_child', '_parent'))
        scores = {}
        if not sim.empty:
            scores = dict(zip(sim.loc[sim['polis_statement_id'] == child, 'model'],
                              sim.loc[sim['polis_statement_id'] == child, 'value']))
        rows.append({
            'parent_tid': parent, 'child_tid': child,
            'parent_text': statements['txt'].get(parent, ''),
            'child_text': statements['txt'].get(child, ''),
            'similarity_semantic': scores.get('semantic-v1', scores.get('semantic')),
            'similarity_char': scores.get('char'),
            'n_voters_parent': len(vp), 'n_voters_child': len(vc),
            'n_voters_both': len(both),
            'agree_parent': float((vp['vote'] == RAW_AGREE).mean()) if len(vp) else np.nan,
            'agree_child': float((vc['vote'] == RAW_AGREE).mean()) if len(vc) else np.nan,
            'agree_parent_common': float((both['vote_parent'] == RAW_AGREE).mean()) if len(both) else np.nan,
            'agree_child_common': float((both['vote_child'] == RAW_AGREE).mean()) if len(both) else np.nan,
            'n_switched_side': int(((both['vote_parent'] * both['vote_child']) < 0).sum()) if len(both) else 0,
            'link_method': link.link_method,
        })
    out = pd.DataFrame(rows)
    out['agree_shift_common'] = out['agree_child_common'] - out['agree_parent_common']
    return out


# ── one-call summary ─────────────────────────────────────────────────────────

def run_all(root) -> dict:
    """Everything the notebook does, in order, as plain data. Handy for a smoke run
    without a kernel."""
    b = load_bundles(root)
    out = {'bundles': b, 'checks': integrity_checks(b), 'gates': {},
           'counterfactuals': {}, 'phases': {}, 'derivatives': {}}
    for conv_key in b.conversations:
        for phase in (2, 6):
            if b.phase('votes_latest', conv_key, phase).empty:
                continue
            gate = reproduction_gate(b, conv_key, phase)
            out['gates'][(conv_key, phase)] = gate
            if gate['passed']:
                out['counterfactuals'][(conv_key, phase)] = counterfactuals(b, gate)
        out['phases'][conv_key] = compare_phases(b, conv_key)
        out['derivatives'][conv_key] = derivative_analysis(b, conv_key)
    return out

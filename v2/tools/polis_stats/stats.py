"""Basic statistics over a checked export. Every threshold is a parameter and is printed in the report.

The labels describe the overall vote on one statement. They are deliberately NOT called
"consensus" or "divisive": in Polis those words mean group-aware measures (group-informed
consensus, representativeness), which this module does not compute.
"""

from __future__ import annotations

import math
from datetime import timedelta
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from .export import AGREE, DISAGREE, PASS, Export


@dataclass
class Thresholds:
    min_votes: int = 10              # agree + disagree votes needed before a statement is labelled
    majority_share: float = 0.70     # agree (or disagree) share of agree + disagree for majority-*
    split_min_share: float = 0.35    # both sides at least this share of agree + disagree for split
    max_pass_share: float = 0.50     # above this share of passes (of all votes): mostly-pass


@dataclass
class StatementStats:
    id: int
    text: str
    moderated: int
    is_seed: bool | None
    is_meta: bool
    agree: int
    disagree: int
    passes: int

    @property
    def votes(self) -> int:
        return self.agree + self.disagree + self.passes

    @property
    def decided(self) -> int:
        return self.agree + self.disagree

    def share(self, n: int) -> float | None:
        return n / self.votes if self.votes else None

    def agree_of_decided(self) -> float | None:
        return self.agree / self.decided if self.decided else None


@dataclass
class Report:
    summary: dict
    statements: list[StatementStats]
    majority_agree: list[int]
    majority_disagree: list[int]
    split: list[int]
    mostly_pass: list[int]
    too_few_votes: list[int]
    votes_per_participant: list[int]
    votes_per_day: list[tuple[str, int]]
    thresholds: Thresholds = field(default_factory=Thresholds)
    groups: dict[str, dict] = field(default_factory=dict)
    # meta statement id -> {'answers': {'agree': n, 'disagree': n, 'pass': n},
    #                       'statements': {opinion id: {'agree': {...}, 'disagree': {...}, 'pass': {...}}}}
    meta: dict[int, dict] = field(default_factory=dict)

    def opinions(self) -> list[StatementStats]:
        """Statements analysed as opinions: not rejected, and not meta (meta statements ask about
        the participant, not the topic; Polis leaves them out of its maths too)."""
        return [s for s in self.statements if s.moderated != -1 and not s.is_meta]

    def label(self, sid: int) -> str:
        for name, ids in (('majority-agree', self.majority_agree), ('majority-disagree', self.majority_disagree),
                          ('split', self.split), ('mostly-pass', self.mostly_pass),
                          ('too-few-votes', self.too_few_votes)):
            if sid in ids:
                return name
        return 'meta' if any(s.id == sid and s.is_meta for s in self.statements) else ''


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    """95% Wilson score interval for k successes out of n (None when n == 0)."""
    if n == 0:
        return None
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def median(values: list[int]) -> float | None:
    if not values:
        return None
    s = sorted(values)
    mid = len(s) // 2
    return float(s[mid]) if len(s) % 2 else (s[mid - 1] + s[mid]) / 2


def compute(export: Export, thresholds: Thresholds | None = None) -> Report:
    t = thresholds or Thresholds()
    counts: dict[int, Counter] = defaultdict(Counter)
    for vote in export.votes.values():
        counts[vote.statement][vote.value] += 1

    rows = [
        StatementStats(
            id=s.id, text=s.text, moderated=s.moderated, is_seed=s.is_seed, is_meta=bool(s.is_meta),
            agree=counts[s.id][AGREE], disagree=counts[s.id][DISAGREE], passes=counts[s.id][PASS],
        )
        for s in sorted(export.statements.values(), key=lambda s: s.id)
    ]
    # Rejected statements are counted, not analysed; meta statements are not opinions.
    shown = [r for r in rows if r.moderated != -1 and not r.is_meta]
    opinion_ids = {r.id for r in shown}

    majority_agree, majority_disagree, split, mostly_pass, too_few = [], [], [], [], []
    for r in shown:
        if r.decided < t.min_votes:
            too_few.append(r.id)
            continue
        if r.passes / r.votes > t.max_pass_share:
            mostly_pass.append(r.id)
            continue
        a = r.agree / r.decided
        if a >= t.majority_share:
            majority_agree.append(r.id)
        elif 1 - a >= t.majority_share:
            majority_disagree.append(r.id)
        elif min(a, 1 - a) >= t.split_min_share:
            split.append(r.id)

    per_participant = Counter(voter for voter, _ in export.votes)
    per_day_counter = Counter(v.at.date() for v in export.votes_all)
    per_day: dict[str, int] = {}
    if per_day_counter:                                    # every day in the range, empty ones too
        day, last = min(per_day_counter), max(per_day_counter)
        while day <= last:
            per_day[day.isoformat()] = per_day_counter.get(day, 0)
            day += timedelta(days=1)

    participants = {voter for voter, _ in export.votes}
    authors = {s.author for s in export.statements.values() if s.author is not None}
    summary = {
        'title': export.summary.get('topic', ''),
        'url': export.summary.get('url', ''),
        'vote_sign': export.vote_sign,
        'statements_total': len(rows),
        'statements_accepted': sum(1 for r in rows if r.moderated == 1),
        'statements_unmoderated': sum(1 for r in rows if r.moderated == 0),
        'statements_rejected': sum(1 for r in rows if r.moderated == -1),
        'statements_seed': sum(1 for r in rows if r.is_seed),
        'statements_meta': sum(1 for r in rows if r.is_meta),
        'participants_voting': len(participants),      # on any statement, rejected and meta included
        'authors': len(authors),
        'votes_current': len(export.votes),             # all statements; 'opinion_votes' excludes rejected and meta
        'vote_rows_including_history': len(export.votes_all),
        'opinion_votes': sum(r.votes for r in shown),
        'agree': sum(r.agree for r in shown),
        'disagree': sum(r.disagree for r in shown),
        'pass': sum(r.passes for r in shown),
        'votes_per_participant_median': median(list(per_participant.values())),
        'first_vote': min((v.at for v in export.votes_all), default=None),
        'last_vote': max((v.at for v in export.votes_all), default=None),
    }

    groups: dict[str, dict] = {}
    clustered = {pid: g for pid, g in export.groups.items() if g is not None}
    if clustered:
        by_group: dict[int, dict[int, Counter]] = defaultdict(lambda: defaultdict(Counter))
        for (voter, sid), vote in export.votes.items():
            g = clustered.get(voter)
            if g is not None:
                by_group[g][sid][vote.value] += 1
        for g in sorted(by_group):
            members = sum(1 for x in clustered.values() if x == g)
            groups[str(g)] = {
                'members': members,
                'statements': {
                    sid: {'agree': c[AGREE], 'disagree': c[DISAGREE], 'pass': c[PASS]}
                    for sid, c in sorted(by_group[g].items())
                },
            }
    meta: dict[int, dict] = {}
    for m in (r for r in rows if r.is_meta and r.moderated != -1):
        answer = {voter: v.value for (voter, sid), v in export.votes.items() if sid == m.id}
        table: dict[int, dict] = {}
        for (voter, sid), v in export.votes.items():
            if sid in opinion_ids and voter in answer:
                key = {AGREE: 'agree', DISAGREE: 'disagree', PASS: 'pass'}[answer[voter]]
                cell = table.setdefault(sid, {k: {'agree': 0, 'disagree': 0, 'pass': 0} for k in ('agree', 'disagree', 'pass')})
                cell[key][{AGREE: 'agree', DISAGREE: 'disagree', PASS: 'pass'}[v.value]] += 1
        meta[m.id] = {
            'answers': {'agree': m.agree, 'disagree': m.disagree, 'pass': m.passes},
            'statements': dict(sorted(table.items())),
        }
    summary['groups'] = len(groups)
    summary['participants_in_groups'] = len(clustered)

    return Report(
        summary=summary, statements=rows, majority_agree=majority_agree,
        majority_disagree=majority_disagree, split=split, mostly_pass=mostly_pass, too_few_votes=too_few,
        votes_per_participant=sorted(per_participant.values()),
        votes_per_day=sorted(per_day.items()), thresholds=t, groups=groups, meta=meta,
    )

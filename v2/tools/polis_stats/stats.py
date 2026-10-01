"""Basic statistics over a checked export. Every threshold is a parameter and is printed in the report."""

from __future__ import annotations

import math
from datetime import timedelta
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from .export import AGREE, DISAGREE, PASS, Export


@dataclass
class Thresholds:
    min_votes: int = 10            # below this, a statement is listed but not called consensus/divisive
    consensus_share: float = 0.70  # agree (or disagree) share of agree+disagree votes
    divisive_min_share: float = 0.35  # both agree and disagree at least this share of agree+disagree


@dataclass
class StatementStats:
    id: int
    text: str
    moderated: int
    is_seed: bool | None
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
    consensus_agree: list[int]
    consensus_disagree: list[int]
    divisive: list[int]
    too_few_votes: list[int]
    votes_per_participant: list[int]
    votes_per_day: list[tuple[str, int]]
    thresholds: Thresholds = field(default_factory=Thresholds)

    def opinions(self) -> list[StatementStats]:
        """Statements analysed as opinions: not rejected."""
        return [s for s in self.statements if s.moderated != -1]


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
            id=s.id, text=s.text, moderated=s.moderated, is_seed=s.is_seed,
            agree=counts[s.id][AGREE], disagree=counts[s.id][DISAGREE], passes=counts[s.id][PASS],
        )
        for s in sorted(export.statements.values(), key=lambda s: s.id)
    ]
    shown = [r for r in rows if r.moderated != -1]   # rejected statements are counted, not analysed

    consensus_agree, consensus_disagree, divisive, too_few = [], [], [], []
    for r in shown:
        if r.decided < t.min_votes:
            too_few.append(r.id)
            continue
        a = r.agree / r.decided
        if a >= t.consensus_share:
            consensus_agree.append(r.id)
        elif 1 - a >= t.consensus_share:
            consensus_disagree.append(r.id)
        elif min(a, 1 - a) >= t.divisive_min_share:
            divisive.append(r.id)

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
        'participants_voting': len(participants),
        'authors': len(authors),
        'votes_current': len(export.votes),
        'vote_rows_including_history': len(export.votes_all),
        'opinion_votes': sum(r.votes for r in shown),
        'agree': sum(r.agree for r in shown),
        'disagree': sum(r.disagree for r in shown),
        'pass': sum(r.passes for r in shown),
        'votes_per_participant_median': median(list(per_participant.values())),
        'first_vote': min((v.at for v in export.votes_all), default=None),
        'last_vote': max((v.at for v in export.votes_all), default=None),
    }

    return Report(
        summary=summary, statements=rows, consensus_agree=consensus_agree,
        consensus_disagree=consensus_disagree, divisive=divisive, too_few_votes=too_few,
        votes_per_participant=sorted(per_participant.values()),
        votes_per_day=sorted(per_day.items()), thresholds=t,
    )

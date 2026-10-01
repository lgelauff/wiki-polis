"""Read a Polis conversation export into one canonical, checked model.

The canonical format is Polis's own CSV export (a folder or a .zip holding ``summary.csv``,
``comments.csv``, ``votes.csv``, ``participants-votes.csv``; ``stats-history.csv`` is ignored).
wiki-polis is meant to write the same files, so one reader serves both.

Two properties of the Polis export decide how it must be read (``math/src/polismath/darwin/export.clj``):

* ``votes.csv`` comes from Polis's append-only ``votes`` table: it holds **every** vote ever cast,
  re-votes included. The current vote of a participant on a statement is the latest row for that
  pair. ``participants-votes.csv`` is that latest-vote matrix, and ``comments.csv``'s
  ``agrees``/``disagrees`` count **all** rows of ``votes.csv``. Both are cross-checked here.
* Polis negates the stored vote on export, so in the export **agree = +1, disagree = -1, pass = 0**.
  In Polis's database and in wiki-polis's vote API agree is -1. A self-consistent export cannot
  reveal which convention it uses, so the caller declares it (``vote_sign``); the default is the
  Polis export convention.

Nothing is dropped silently: every row that is excluded or inconsistent becomes an ``Issue``.
"""

from __future__ import annotations

import csv
import io
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

AGREE, PASS, DISAGREE = 1, 0, -1
FILES = ('summary.csv', 'comments.csv', 'votes.csv', 'participants-votes.csv')

# Polis writes lower-case hyphenated headers in its CSV export and title-case ones in its Excel
# export; accept both, case-insensitively.
_ALIASES = {
    'timestamp': 'timestamp', 'datetime': 'datetime',
    'comment-id': 'comment-id', 'comment id': 'comment-id',
    'author-id': 'author-id', 'author id': 'author-id',
    'voter-id': 'voter-id', 'voter id': 'voter-id',
    'agrees': 'agrees', 'disagrees': 'disagrees', 'moderated': 'moderated',
    'is-meta': 'is-meta', 'is-seed': 'is-seed',
    'group-informed-consensus': 'group-informed-consensus',
    'comment-body': 'comment-body', 'comment body': 'comment-body', 'vote': 'vote',
    'participant': 'participant', 'group-id': 'group-id', 'group id': 'group-id',
    'n-comments': 'n-comments', 'comments': 'n-comments', 'n-votes': 'n-votes', 'votes': 'n-votes',
    'n-agree': 'n-agree', 'agree': 'n-agree', 'n-disagree': 'n-disagree', 'disagree': 'n-disagree',
}


class ExportError(ValueError):
    """The export cannot be read at all (a file or a required column is missing)."""


@dataclass
class Issue:
    level: str        # 'error' | 'warning' | 'note'
    code: str
    message: str
    count: int = 1


@dataclass
class Statement:
    id: int
    author: int | None
    created: datetime | None
    moderated: int            # 1 accepted, 0 not yet moderated, -1 rejected
    is_seed: bool | None
    is_meta: bool | None
    text: str
    reported_agrees: int | None
    reported_disagrees: int | None


@dataclass
class Vote:
    at: datetime
    statement: int
    voter: int
    value: int                # AGREE / PASS / DISAGREE, always in the canonical sign


@dataclass
class Export:
    summary: dict[str, str]
    statements: dict[int, Statement]
    votes_all: list[Vote]                         # every row of votes.csv, history included
    votes: dict[tuple[int, int], Vote]            # (voter, statement) -> latest vote
    groups: dict[int, int | None]                 # participant -> group id (None = not clustered)
    issues: list[Issue] = field(default_factory=list)
    source: str = ''
    vote_sign: str = 'polis-export'


# ── reading ─────────────────────────────────────────────────────────────────────────────

def _classify(base: str) -> str | None:
    """Map a file name to the export file it is: exact, or with a prefix such as 'abc123-'.

    The longest match wins, so 'participants-votes.csv' is never taken for 'votes.csv'.
    """
    hits = [n for n in FILES if base == n or base.endswith('-' + n)]
    return max(hits, key=len) if hits else None


def _open_source(path: Path) -> dict[str, str]:
    """Return {canonical file name: text} from a folder or a .zip (entries may sit in a subfolder)."""
    found: dict[str, str] = {}
    if path.is_dir():
        for f in sorted(path.rglob('*.csv')):
            name = _classify(f.name)
            if name and name not in found:
                found[name] = f.read_text(encoding='utf-8-sig')
    elif zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            for entry in sorted(z.namelist()):
                name = _classify(entry.rsplit('/', 1)[-1])
                if name and name not in found:
                    found[name] = z.read(entry).decode('utf-8-sig')
    else:
        raise ExportError(f'{path} is neither a folder nor a zip file')
    missing = [n for n in ('comments.csv', 'votes.csv') if n not in found]
    if missing:
        raise ExportError(f'export at {path} lacks {", ".join(missing)}')
    return found


def _rows(text: str, required: tuple[str, ...], name: str) -> list[dict[str, str]]:
    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration:
        raise ExportError(f'{name} is empty') from None
    keys = [_ALIASES.get(h.strip().lower(), h.strip()) for h in header]
    missing = [r for r in required if r not in keys]
    if missing:
        raise ExportError(f'{name} lacks column(s) {", ".join(missing)} (has: {", ".join(header)})')
    return [dict(zip(keys, row)) for row in reader if any(cell.strip() for cell in row)]


def _int(value: str | None) -> int | None:
    value = (value or '').strip()
    if value == '':
        return None
    return int(float(value))


def _bool(value: str | None) -> bool | None:
    value = (value or '').strip().lower()
    if value in ('', 'null', 'none'):
        return None
    return value in ('true', 't', '1', 'yes')


def _time(value: str | None) -> datetime | None:
    """Polis timestamps are epoch milliseconds (sometimes seconds); fall back to ISO text."""
    value = (value or '').strip()
    if not value:
        return None
    try:
        number = float(value)
    except ValueError:
        try:
            parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    seconds = number / 1000.0 if number > 1e11 else number
    return datetime.fromtimestamp(seconds, tz=timezone.utc)


def read_export(path: str | Path, *, vote_sign: str = 'polis-export') -> Export:
    """Read and check an export. ``vote_sign`` is 'polis-export' (agree=+1) or 'raw' (agree=-1)."""
    if vote_sign not in ('polis-export', 'raw'):
        raise ValueError("vote_sign must be 'polis-export' or 'raw'")
    flip = -1 if vote_sign == 'raw' else 1
    path = Path(path)
    files = _open_source(path)
    issues: list[Issue] = []

    summary: dict[str, str] = {}
    if 'summary.csv' in files:
        for row in csv.reader(io.StringIO(files['summary.csv'])):
            if len(row) >= 2 and row[0].strip():
                summary[row[0].strip()] = row[1].strip()
    else:
        issues.append(Issue('note', 'no-summary', 'summary.csv is absent; title and URL unknown'))

    statements: dict[int, Statement] = {}
    comment_rows = _rows(files['comments.csv'], ('comment-id', 'comment-body'), 'comments.csv')
    for row in comment_rows:
        sid = _int(row['comment-id'])
        if sid is None:
            issues.append(Issue('error', 'statement-without-id', 'a comments.csv row has no comment-id'))
            continue
        if sid in statements:
            issues.append(Issue('error', 'duplicate-statement', f'statement {sid} appears twice in comments.csv'))
            continue
        statements[sid] = Statement(
            id=sid, author=_int(row.get('author-id')), created=_time(row.get('timestamp')),
            moderated=_int(row.get('moderated')) or 0,
            is_seed=_bool(row.get('is-seed')), is_meta=_bool(row.get('is-meta')),
            text=row.get('comment-body', ''),
            reported_agrees=_int(row.get('agrees')), reported_disagrees=_int(row.get('disagrees')),
        )

    votes_all: list[Vote] = []
    unknown_statement = bad_value = no_time = 0
    for row in _rows(files['votes.csv'], ('comment-id', 'voter-id', 'vote'), 'votes.csv'):
        sid, voter, raw = _int(row['comment-id']), _int(row['voter-id']), _int(row['vote'])
        if raw not in (-1, 0, 1) or sid is None or voter is None:
            bad_value += 1
            continue
        if sid not in statements:
            unknown_statement += 1
            continue
        at = _time(row.get('timestamp')) or _time(row.get('datetime'))
        if at is None:
            no_time += 1
            at = datetime.fromtimestamp(0, tz=timezone.utc)
        votes_all.append(Vote(at=at, statement=sid, voter=voter, value=raw * flip))
    if bad_value:
        issues.append(Issue('error', 'bad-vote-row', 'votes.csv rows with a missing id or a vote other than -1/0/1 (excluded)', bad_value))
    if unknown_statement:
        issues.append(Issue('error', 'vote-for-unknown-statement', 'votes.csv rows for a statement absent from comments.csv (excluded)', unknown_statement))
    if no_time:
        issues.append(Issue('warning', 'vote-without-time', 'votes.csv rows without a timestamp; their order among re-votes is undefined', no_time))

    latest: dict[tuple[int, int], Vote] = {}
    for vote in sorted(votes_all, key=lambda v: v.at):        # stable: file order breaks ties
        latest[(vote.voter, vote.statement)] = vote
    revotes = len(votes_all) - len(latest)
    if revotes:
        issues.append(Issue('note', 'revotes', 'votes.csv rows superseded by a later vote of the same participant on the same statement (history, not counted)', revotes))

    groups: dict[int, int | None] = {}
    if 'participants-votes.csv' in files:
        groups = _check_matrix(files['participants-votes.csv'], latest, flip, issues)
    else:
        issues.append(Issue('note', 'no-participant-matrix', 'participants-votes.csv is absent; no opinion groups, no latest-vote cross-check'))

    _check_reported_counts(statements, votes_all, issues)

    return Export(summary=summary, statements=statements, votes_all=votes_all, votes=latest,
                  groups=groups, issues=issues, source=str(path), vote_sign=vote_sign)


def _check_matrix(text: str, latest: dict, flip: int, issues: list[Issue]) -> dict[int, int | None]:
    """participants-votes.csv must agree, cell by cell, with the latest votes from votes.csv."""
    reader = csv.reader(io.StringIO(text))
    header = next(reader, [])
    keys = [_ALIASES.get(h.strip().lower(), h.strip()) for h in header]
    if 'participant' not in keys:
        issues.append(Issue('error', 'matrix-unreadable', 'participants-votes.csv has no participant column; skipped'))
        return {}
    statement_cols = [(i, int(k)) for i, k in enumerate(keys) if k.strip().lstrip('-').isdigit()]
    gi = keys.index('group-id') if 'group-id' in keys else None
    groups: dict[int, int | None] = {}
    mismatched = 0
    seen: set[tuple[int, int]] = set()
    for row in reader:
        if not any(c.strip() for c in row):
            continue
        pid = _int(row[keys.index('participant')])
        if pid is None:
            continue
        groups[pid] = _int(row[gi]) if gi is not None and gi < len(row) else None
        for i, sid in statement_cols:
            cell = _int(row[i]) if i < len(row) else None
            if cell is None:
                continue
            seen.add((pid, sid))
            vote = latest.get((pid, sid))
            if vote is None or vote.value != cell * flip:
                mismatched += 1
    missing = sum(1 for key in latest if key not in seen and key[0] in groups)
    if mismatched:
        issues.append(Issue('error', 'matrix-mismatch', 'participants-votes.csv cells that differ from the latest vote in votes.csv', mismatched))
    if missing:
        issues.append(Issue('warning', 'matrix-missing-votes', 'latest votes absent from participants-votes.csv (e.g. moderated-out statements dropped from the matrix)', missing))
    return groups


def _check_reported_counts(statements: dict[int, Statement], votes_all: list[Vote], issues: list[Issue]) -> None:
    """comments.csv agrees/disagrees count every row of votes.csv (history included)."""
    agrees: dict[int, int] = {}
    disagrees: dict[int, int] = {}
    for v in votes_all:
        if v.value == AGREE:
            agrees[v.statement] = agrees.get(v.statement, 0) + 1
        elif v.value == DISAGREE:
            disagrees[v.statement] = disagrees.get(v.statement, 0) + 1
    off = swapped = 0
    for s in statements.values():
        if s.reported_agrees is None or s.reported_disagrees is None:
            continue
        a, d = agrees.get(s.id, 0), disagrees.get(s.id, 0)
        if (s.reported_agrees, s.reported_disagrees) != (a, d):
            off += 1
            if (s.reported_agrees, s.reported_disagrees) == (d, a) and a != d:
                swapped += 1
    if swapped and swapped == off:
        issues.append(Issue('error', 'vote-sign-inverted', 'comments.csv counts match votes.csv only with agree and disagree swapped: the declared vote_sign is probably wrong', swapped))
    elif off:
        issues.append(Issue('error', 'reported-counts-mismatch', 'statements whose comments.csv agrees/disagrees differ from votes.csv', off))

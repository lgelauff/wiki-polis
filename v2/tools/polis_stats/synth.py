"""A synthetic Polis export with known answers, in the exact CSV layout of Polis's export.

Used by the tests, and handy for trying the tool without real data:

    python -m tools.polis_stats.synth OUT_DIR && python -m tools.polis_stats OUT_DIR -o OUT_DIR/report

Layout follows math/src/polismath/darwin/export.clj (csv-format): comments.csv carries
agrees/disagrees counted over ALL vote rows (history included); votes.csv holds every vote row;
participants-votes.csv holds each participant's latest vote per statement.
"""

from __future__ import annotations

import csv
import random
import sys
from pathlib import Path

T0 = 1_788_000_000_000        # epoch millis, 2026-08-28

# id: (text, moderated, is_seed, {group: (p_agree, p_disagree)} ; the rest is pass)
STATEMENTS = {
    0: ('Everyone agrees with this.', 1, True, {0: (0.95, 0.0), 1: (0.9, 0.05), 2: (0.95, 0.0)}),
    1: ('Nearly everyone rejects this.', 1, True, {0: (0.05, 0.9), 1: (0.0, 0.95), 2: (0.05, 0.9)}),
    2: ('Groups split on this.', 1, False, {0: (0.95, 0.05), 1: (0.05, 0.95), 2: (0.5, 0.5)}),
    3: ('Hardly anyone saw this.', 1, False, None),
    4: ('A statement moderated out.', -1, False, {0: (0.5, 0.5), 1: (0.5, 0.5), 2: (0.5, 0.5)}),
    5: ('Still waiting for moderation.', 0, False, {0: (0.4, 0.2), 1: (0.4, 0.2), 2: (0.4, 0.2)}),
}
META: set[int] = set()


def build(seed: int = 7, participants: int = 60, raw_sign: bool = False) -> dict:
    """Return the export as {file name: rows} plus the expected answers under 'truth'."""
    rng = random.Random(seed)
    group = {pid: pid % 3 for pid in range(participants)}
    rows, t = [], T0
    for pid in range(participants):
        for sid, (_, _, _, probs) in STATEMENTS.items():
            if probs is None:
                if pid >= 4:                      # statement 3: only 4 voters
                    continue
                vote = 1
            else:
                pa, pd = probs[group[pid]]
                r = rng.random()
                vote = 1 if r < pa else (-1 if r < pa + pd else 0)
            t += 60_000
            rows.append([t, pid, sid, vote])
    # re-votes: 5 participants change their mind on statement 2 later (latest must win) ...
    for pid in range(5):
        t += 3_600_000
        rows.append([t, pid, 2, -1])
    # ... and participant 5 votes twice on statement 0 in the same millisecond: file order decides
    t += 3_600_000
    rows += [[t, 5, 0, 1], [t, 5, 0, -1]]
    # Polis writes votes ordered by statement, participant, time (export.clj get-conversation-votes*)
    rows.sort(key=lambda r: (r[2], r[1], r[0]))
    latest = {}
    for ts, pid, sid, vote in rows:                 # in that order, the last row of a pair wins
        latest[(pid, sid)] = vote
    truth = {sid: {'agree': 0, 'disagree': 0, 'pass': 0} for sid in STATEMENTS}
    for (pid, sid), vote in latest.items():
        truth[sid][{1: 'agree', -1: 'disagree', 0: 'pass'}[vote]] += 1
    history_agrees = {sid: sum(1 for r in rows if r[2] == sid and r[3] == 1) for sid in STATEMENTS}
    history_disagrees = {sid: sum(1 for r in rows if r[2] == sid and r[3] == -1) for sid in STATEMENTS}

    flip = -1 if raw_sign else 1
    from datetime import datetime, timezone
    votes_csv = [['timestamp', 'datetime', 'comment-id', 'voter-id', 'vote']] + [
        [ts, datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime('%a %b %d %H:%M:%S UTC %Y'), sid, pid, vote * flip]
        for ts, pid, sid, vote in rows]
    comments_csv = [['timestamp', 'comment-id', 'author-id', 'agrees', 'disagrees', 'moderated',
                     'is-meta', 'is-seed', 'group-informed-consensus', 'comment-body']] + [
        [T0 - 1000 * (10 - sid), sid, sid % 3, history_agrees[sid], history_disagrees[sid], mod,
         str(sid in META).lower(), str(seed_flag).lower(), '', text]
        for sid, (text, mod, seed_flag, _) in STATEMENTS.items()]
    sids = sorted(STATEMENTS)
    matrix = [['participant', 'group-id', 'n-comments', 'n-votes', 'n-agree', 'n-disagree'] + [str(s) for s in sids]]
    for pid in range(participants):
        cells = [latest.get((pid, sid)) for sid in sids]
        authored = sum(1 for sid in STATEMENTS if sid % 3 == pid)
        matrix.append([pid, group[pid], authored, sum(c is not None for c in cells), cells.count(1), cells.count(-1)]
                      + ['' if c is None else c * flip for c in cells])
    summary_csv = [['topic', 'Synthetic test conversation'], ['url', 'https://example.invalid/synthetic'],
                   ['views', participants], ['voters', participants], ['comments', len(STATEMENTS)], ['groups', 3]]
    return {'summary.csv': summary_csv, 'comments.csv': comments_csv, 'votes.csv': votes_csv,
            'participants-votes.csv': matrix, 'truth': truth, 'revotes': len(rows) - len(latest)}


def write(out: str | Path, **kwargs) -> dict:
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    data = build(**kwargs)
    for name in ('summary.csv', 'comments.csv', 'votes.csv', 'participants-votes.csv'):
        with open(out / name, 'w', newline='', encoding='utf-8') as fh:
            csv.writer(fh).writerows(data[name])
    return data


if __name__ == '__main__':
    write(sys.argv[1] if len(sys.argv) > 1 else 'synthetic-export')

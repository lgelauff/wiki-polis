"""Guard: admin per-statement vote counts must be deduplicated (#269).

Repro of the bug this guards against — one participant, one statement:
    (passed)          A 0  P 1  D 0
    vote agree     -> A 1  P 1  D 0   (pass still counted!)
    change disagree-> A 1  P 1  D 1   (agree still counted!)
    change agree   -> A 2  P 1  D 1   (every event counted)

Root cause: counting the raw append-only `votes` table with COUNT(*) counts every
vote *event* (including changes). The fix counts DISTINCT participants at their
CURRENT vote via `votes_latest_unique`.

The query runs against a Polis Postgres view, so we can't execute it in the SQLite
unit env (a true behavioural test needs the Polis PG — local-e2e / integration tier).
Instead we assert the query SHAPE so a regression to the raw form fails CI.
"""
from polis_admin import _FEATURED_CANDIDATES_SQL, _STATEMENTS_SQL

# Every admin SQL that reports per-statement vote counts to a human.
ADMIN_COUNT_SQL = {
    '_STATEMENTS_SQL': _STATEMENTS_SQL,
    '_FEATURED_CANDIDATES_SQL': _FEATURED_CANDIDATES_SQL,
}


def test_admin_counts_use_deduplicated_source():
    for name, sql in ADMIN_COUNT_SQL.items():
        assert 'votes_latest_unique' in sql, \
            f'{name} must count from votes_latest_unique, not raw votes (#269)'
        assert 'FROM votes v,' not in sql, \
            f'{name} must NOT count the raw append-only `votes` table (#269)'


def test_admin_counts_count_distinct_participants():
    for name, sql in ADMIN_COUNT_SQL.items():
        assert 'COUNT(DISTINCT v.pid)' in sql, \
            f'{name} must COUNT(DISTINCT v.pid) — one count per participant (#269)'
        assert 'COUNT(*)' not in sql, \
            f'{name} must not COUNT(*) vote rows (inflates on vote changes) (#269)'

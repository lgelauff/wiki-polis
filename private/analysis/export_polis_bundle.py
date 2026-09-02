#!/usr/bin/env python3
"""Export the de-identified Polis half of an analysis bundle.

RUNS ON THE HOST THAT HOLDS THE POLIS DATABASE (the VPS, or the local dev stack).
Read-only: every statement is a SELECT.

What leaves: votes, statements, per-conversation pids, and the server's own
clustering output (`math_main.data`), keyed by a salted `person_key`.
What never leaves: `uid`, `particiapi_users.subject` (= the xid), the Polis
`users` table, anything from `participants_extended`.

Two ways to reach the database, in order of preference:

  --db-url postgresql://user:pass@host/db     (needs psycopg2 on the host)
  --psql-cmd 'docker exec -i <container> psql -U polis polis'
                                              (needs nothing but docker)

Usage
-----
    python3 export_polis_bundle.py \
        --conversations conversations.tsv \
        --salt-file ~/.wiki-polis-export-salt \
        --env prod --out ./prod_2026-08-14 \
        --db-url "$POLIS_DATABASE_URL"

`conversations.tsv` is written by export_app_bundle.py and holds one row per
conversation:  slug <TAB> phase2_zinvite <TAB> phase6_zinvite_or_blank
Run the app exporter first, or pass --conversation slug:phase2[:phase6] instead.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bundle import BundleWriter, SelfCheckError, anon_key, load_salt, person_key  # noqa: E402

SAFE_ZINVITE = re.compile(r'^[a-zA-Z0-9]{1,50}$')


# ── database access ──────────────────────────────────────────────────────────

class PsqlClient:
    """Runs queries through a `psql` command line. No Python driver needed, which
    is what makes this usable on a VPS that only has docker."""

    def __init__(self, cmd: str):
        self.cmd = cmd

    def query(self, sql: str, params: tuple = ()) -> list[dict]:
        # \copy is a psql meta-command and must sit on a single line, so the
        # statement's own newlines are collapsed first.
        statement = ' '.join(_inline_params(sql, params).split()).rstrip(';')
        proc = subprocess.run(
            self.cmd, shell=True,
            input=f'\\copy ({statement}) TO STDOUT WITH CSV HEADER\n',
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            raise RuntimeError(f'psql failed: {proc.stderr.strip()[:500]}')
        reader = csv.DictReader(io.StringIO(proc.stdout))
        return [dict(row) for row in reader]


class Psycopg2Client:
    def __init__(self, db_url: str):
        import psycopg2
        import psycopg2.extras
        self._conn = psycopg2.connect(db_url)
        self._conn.set_session(readonly=True, autocommit=True)
        self._extras = psycopg2.extras

    def query(self, sql: str, params: tuple = ()) -> list[dict]:
        with self._conn.cursor(cursor_factory=self._extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return [dict(row) for row in cur.fetchall()]


def _inline_params(sql: str, params: tuple) -> str:
    """Substitute %s placeholders for the psql path.

    Only ever called with values this script controls — zinvites already matched
    against SAFE_ZINVITE, and integers. Anything else is refused rather than quoted,
    because a half-safe quoting routine is worse than none.
    """
    out = sql
    for value in params:
        if isinstance(value, int):
            literal = str(value)
        elif isinstance(value, str) and SAFE_ZINVITE.match(value):
            literal = f"'{value}'"
        else:
            raise ValueError(f'refusing to inline unsafe parameter {value!r}')
        out = out.replace('%s', literal, 1)
    return out


# ── SQL ──────────────────────────────────────────────────────────────────────

Q_CONVERSATION = """
    SELECT c.zid, c.is_active, c.is_public, c.strict_moderation, c.vis_type, c.created
    FROM conversations c
    WHERE c.zid = (SELECT zid FROM zinvites WHERE zinvite = %s)
"""

Q_COMMENTS = """
    SELECT c.tid, c.pid, c.txt, c.mod, c.active, c.is_seed, c.lang, c.created
    FROM comments c
    WHERE c.zid = (SELECT zid FROM zinvites WHERE zinvite = %s)
    ORDER BY c.tid
"""

Q_VOTES_LATEST = """
    SELECT v.pid, v.tid, v.vote, v.modified
    FROM votes_latest_unique v
    WHERE v.zid = (SELECT zid FROM zinvites WHERE zinvite = %s)
    ORDER BY v.pid, v.tid
"""

Q_VOTES_HISTORY = """
    SELECT v.pid, v.tid, v.vote, v.created
    FROM votes v
    WHERE v.zid = (SELECT zid FROM zinvites WHERE zinvite = %s)
    ORDER BY v.created, v.pid, v.tid
"""

Q_PARTICIPANTS = """
    SELECT p.pid, p.uid, p.vote_count, p.last_interaction
    FROM participants p
    WHERE p.zid = (SELECT zid FROM zinvites WHERE zinvite = %s)
    ORDER BY p.pid
"""

# Identity map. Consumed in memory to build person_keys and then dropped —
# neither uid nor subject is ever staged into the bundle.
Q_IDENTITY = """
    SELECT p.pid, pu.subject
    FROM participants p
    JOIN particiapi_users pu ON pu.uid = p.uid
    WHERE p.zid = (SELECT zid FROM zinvites WHERE zinvite = %s)
"""

Q_MATH_MAIN = """
    SELECT m.math_env, m.data, m.last_vote_timestamp, m.math_tick, m.modified
    FROM math_main m
    WHERE m.zid = (SELECT zid FROM zinvites WHERE zinvite = %s)
"""


# ── export ───────────────────────────────────────────────────────────────────

def _as_int(value):
    return None if value in (None, '') else int(value)


def _as_bool(value):
    if isinstance(value, bool) or value is None:
        return value
    return str(value).lower() in ('t', 'true', '1', 'y')


def export_conversation(client, writer_rows, salt, conv_key, phase, zinvite,
                        with_text: bool) -> dict:
    """Pull one Polis conversation into the staged row lists. Returns a stats dict."""
    if not SAFE_ZINVITE.match(zinvite or ''):
        raise ValueError(f'unsafe zinvite {zinvite!r}')

    conv_rows = client.query(Q_CONVERSATION, (zinvite,))
    if not conv_rows:
        raise LookupError(f'no Polis conversation for zinvite {zinvite}')
    conv = conv_rows[0]

    identity = {int(r['pid']): r['subject']
                for r in client.query(Q_IDENTITY, (zinvite,)) if r.get('subject')}
    participants = client.query(Q_PARTICIPANTS, (zinvite,))

    keys: dict[int, str] = {}
    for row in participants:
        pid = int(row['pid'])
        subject = identity.get(pid)
        keys[pid] = person_key(salt, subject) if subject else anon_key(salt, row['uid'])
    linked = sum(1 for pid in keys if pid in identity)

    writer_rows['conversations'].append([
        conv_key, phase, zinvite,
        _as_bool(conv['is_active']), _as_bool(conv['is_public']),
        _as_bool(conv['strict_moderation']), _as_int(conv['vis_type']),
        _as_int(conv['created']),
    ])

    for row in participants:
        pid = int(row['pid'])
        writer_rows['participants'].append([
            conv_key, phase, keys[pid], pid,
            _as_int(row['vote_count']), _as_int(row['last_interaction']),
            pid in identity,
        ])

    comments = client.query(Q_COMMENTS, (zinvite,))
    for row in comments:
        # `pid` is read but deliberately dropped: statement authorship is not exported.
        writer_rows['statements'].append([
            conv_key, phase, _as_int(row['tid']),
            _as_bool(row['is_seed']),
            _as_int(row['mod']), _as_bool(row['active']),
            _as_int(row['created']), row['lang'] or '',
            (row['txt'] or '') if with_text else '',
        ])

    votes = client.query(Q_VOTES_LATEST, (zinvite,))
    for row in votes:
        pid = int(row['pid'])
        writer_rows['votes_latest'].append([
            conv_key, phase, keys.get(pid, anon_key(salt, f'orphan-{pid}')), pid,
            _as_int(row['tid']), _as_int(row['vote']), _as_int(row['modified']),
        ])

    history = client.query(Q_VOTES_HISTORY, (zinvite,))
    for row in history:
        pid = int(row['pid'])
        writer_rows['votes_history'].append([
            conv_key, phase, keys.get(pid, anon_key(salt, f'orphan-{pid}')), pid,
            _as_int(row['tid']), _as_int(row['vote']), _as_int(row['created']),
        ])

    math_rows = client.query(Q_MATH_MAIN, (zinvite,))
    math_payload = None
    for row in math_rows:
        data = row['data']
        if isinstance(data, str):
            data = json.loads(data)
        math_payload = {
            'conv_key': conv_key, 'phase': phase, 'zinvite': zinvite,
            'math_env': row['math_env'],
            'last_vote_timestamp': _as_int(row['last_vote_timestamp']),
            'math_tick': _as_int(row['math_tick']),
            'modified': _as_int(row['modified']),
            'data': data,
        }
        writer_rows['math'][f'math_main/{conv_key}_phase{phase}.json'] = math_payload

    return {
        'conv_key': conv_key, 'phase': phase, 'zinvite': zinvite,
        'n_participants': len(participants), 'n_identity_linked': linked,
        'n_statements': len(comments), 'n_votes_latest': len(votes),
        'n_votes_history': len(history), 'has_math_main': math_payload is not None,
    }


COLUMNS = {
    'conversations': ['conv_key', 'phase', 'zinvite', 'is_active', 'is_public',
                      'strict_moderation', 'vis_type', 'created_ms'],
    'participants': ['conv_key', 'phase', 'person_key', 'pid', 'vote_count',
                     'last_interaction_ms', 'identity_linked'],
    # No author column, by design. A per-statement author key plus people.csv would
    # reconstruct who wrote what; `is_seed` (moderator-seeded vs participant-submitted)
    # is the only authorship fact the analysis needs.
    'statements': ['conv_key', 'phase', 'tid', 'is_seed', 'mod',
                   'active', 'created_ms', 'lang', 'txt'],
    'votes_latest': ['conv_key', 'phase', 'person_key', 'pid', 'tid', 'vote',
                     'modified_ms'],
    'votes_history': ['conv_key', 'phase', 'person_key', 'pid', 'tid', 'vote',
                      'created_ms'],
}


def read_conversations_tsv(path) -> list[tuple[str, str, str | None]]:
    out = []
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        parts = line.split('\t')
        slug, phase2 = parts[0], parts[1]
        phase6 = parts[2] if len(parts) > 2 and parts[2] else None
        out.append((slug, phase2, phase6))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--out', required=True, help='bundle directory to create')
    ap.add_argument('--salt-file', required=True)
    ap.add_argument('--env', required=True, choices=('local', 'staging', 'prod'))
    ap.add_argument('--db-url', help='postgres URL (needs psycopg2)')
    ap.add_argument('--psql-cmd',
                    help="e.g. 'docker exec -i particiapp-docker-postgres-1 psql -U polis polis'")
    ap.add_argument('--conversations', help='TSV from export_app_bundle.py')
    ap.add_argument('--conversation', action='append', default=[],
                    metavar='SLUG:PHASE2[:PHASE6]',
                    help='inline conversation spec; repeatable')
    ap.add_argument('--no-text', dest='with_text', action='store_false',
                    help='omit statement text from the bundle')
    ap.set_defaults(with_text=True)
    args = ap.parse_args()

    if not args.db_url and not args.psql_cmd:
        ap.error('one of --db-url or --psql-cmd is required')

    convs: list[tuple[str, str, str | None]] = []
    if args.conversations:
        convs += read_conversations_tsv(args.conversations)
    for spec in args.conversation:
        parts = spec.split(':')
        convs.append((parts[0], parts[1], parts[2] if len(parts) > 2 and parts[2] else None))
    if not convs:
        ap.error('no conversations given (--conversations or --conversation)')

    salt = load_salt(args.salt_file)
    client = Psycopg2Client(args.db_url) if args.db_url else PsqlClient(args.psql_cmd)

    rows = {name: [] for name in COLUMNS}
    rows['math'] = {}
    stats = []
    for slug, phase2, phase6 in convs:
        stats.append(export_conversation(client, rows, salt, slug, 2, phase2, args.with_text))
        if phase6:
            stats.append(export_conversation(client, rows, salt, slug, 6, phase6, args.with_text))

    writer = BundleWriter(args.out, kind='polis', env=args.env, salt=salt,
                          with_text=args.with_text,
                          extra_manifest={'conversations': stats})
    for name, columns in COLUMNS.items():
        writer.add_csv(f'{name}.csv', columns, rows[name])
    for name, payload in rows['math'].items():
        writer.add_json(name, payload)

    try:
        writer.close()
    except SelfCheckError as exc:
        print(f'\nABORTED: {exc}', file=sys.stderr)
        return 2

    for s in stats:
        unlinked = s['n_participants'] - s['n_identity_linked']
        note = f", {unlinked} without a particiapi_users row" if unlinked else ''
        print(f"  {s['conv_key']} phase {s['phase']}: {s['n_participants']} participants{note}, "
              f"{s['n_statements']} statements, {s['n_votes_latest']} current votes, "
              f"math_main={'yes' if s['has_math_main'] else 'MISSING'}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

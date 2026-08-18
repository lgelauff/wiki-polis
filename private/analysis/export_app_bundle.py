#!/usr/bin/env python3
"""Export the de-identified wiki-polis app-database half of an analysis bundle.

RUNS ON THE HOST THAT HOLDS THE APP DATABASE (Toolforge for prod/staging, or the
local SQLite file in dev). Read-only: every statement is a SELECT.

What leaves: conversation settings and phase flags, the featured-statement bridge
between the Phase 2 and Phase 6 Polis conversations, **statement provenance**
(which statement was submitted as an improvement to which other statement) and its
similarity scores, and optionally arguments — all keyed by a salted `person_key`.

What never leaves: `mw_user_id`, `mw_username`, `xid`, `pseudonym`,
`public_username`, `revealed_at`, invites, content flags, audit events,
eligibility detail, notification preferences.

Also writes `conversations.tsv` (slug / phase-2 zinvite / phase-6 zinvite), which
is the input to export_polis_bundle.py — so run this exporter FIRST.

Usage
-----
    python3 export_app_bundle.py \
        --db-url "$DATABASE_URL" \
        --slug cats-vs-dogs-ab12cd \
        --salt-file ~/.wiki-polis-export-salt \
        --env prod --out ./prod_2026-08-14
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bundle import (BundleWriter, SelfCheckError, conversation_subject,  # noqa: E402
                    load_salt, person_key, secret_id)


# ── database access ──────────────────────────────────────────────────────────

class SqliteClient:
    paramstyle = '?'

    def __init__(self, path: str):
        self._conn = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
        self._conn.row_factory = sqlite3.Row

    def query(self, sql: str, params: tuple = ()) -> list[dict]:
        cur = self._conn.execute(sql, params)
        return [dict(row) for row in cur.fetchall()]


class MySQLClient:
    paramstyle = '%s'

    def __init__(self, url: str):
        import pymysql
        parsed = urlparse(url)
        self._conn = pymysql.connect(
            host=parsed.hostname, port=parsed.port or 3306,
            user=unquote(parsed.username or ''),
            password=unquote(parsed.password or ''),
            database=(parsed.path or '/').lstrip('/'),
            cursorclass=pymysql.cursors.DictCursor,
        )

    def query(self, sql: str, params: tuple = ()) -> list[dict]:
        with self._conn.cursor() as cur:
            cur.execute(sql, params)
            return [dict(row) for row in cur.fetchall()]


def open_client(db_url: str):
    """SQLAlchemy-style URL in, minimal driver out."""
    if db_url.startswith('sqlite'):
        path = db_url.split('///', 1)[1] if '///' in db_url else db_url
        return SqliteClient(path)
    if db_url.startswith(('mysql', 'mariadb')):
        return MySQLClient(db_url)
    raise ValueError(f'unsupported database URL: {db_url.split("://")[0]}://…')


def placeholders(client, n: int) -> str:
    return ', '.join([client.paramstyle] * n)


# ── export ───────────────────────────────────────────────────────────────────

CONVERSATION_COLUMNS = [
    'conv_key', 'slug', 'polis_id', 'phase6_polis_conversation_id', 'title',
    'language', 'access_policy', 'phase_route', 'active', 'paused',
    'phase_submission', 'phase_personal_results', 'phase_argument_mapping',
    'phase_cleanup', 'phase_public_results', 'phase_informed_voting',
    'argument_vote_method', 'created_at', 'closed_at', 'n_participations',
]

FEATURED_COLUMNS = [
    'conv_key', 'polis_statement_id', 'phase6_polis_statement_id',
    'suggested_by_system', 'confirmed_by_admin', 'created_at', 'statement_text',
]

PROVENANCE_COLUMNS = [
    'conv_key', 'polis_statement_id', 'derived_from_tid', 'provenance_type',
    'link_method', 'created_at',
]

SIMILARITY_COLUMNS = ['conv_key', 'polis_statement_id', 'model', 'value', 'scored_at']

# No proposer column, for the same reason statements carry no author: it would
# reconstruct who wrote which argument. `is_seeded` distinguishes an admin-seeded
# argument from a participant-written one, which is all the analysis needs.
ARGUMENT_COLUMNS = [
    'conv_key', 'argument_id', 'polis_statement_id', 'side', 'hidden',
    'is_seeded', 'created_at', 'body',
]

ARGUMENT_VOTE_COLUMNS = ['conv_key', 'argument_id', 'person_key', 'value', 'created_at']

# Only written with --with-pseudonyms. Lets a report say which opinion group a
# pseudonym landed in, so a participant can find themselves in it.
#
# The pseudonym is already visible inside the app (it labels arguments), and this
# file carries no username: `public_username` and `revealed_at` are never exported,
# so the bundle cannot link a pseudonym to a Wikimedia account on its own. But a
# participant who has *voluntarily revealed* their username in the app is linkable
# by anyone who saw that reveal — for them, publishing pseudonym → opinion group
# publishes account → opinion group. That is the organiser's call, not a default.
PEOPLE_COLUMNS = ['conv_key', 'person_key', 'pseudonym']


DEFAULT_SUB_SECRET_PATH = '/run/secrets/wiki-polis/particiapi-sub-secret'


def load_sub_secret(path: str | None) -> bytes:
    """The secret wiki-polis uses to derive each conversation-scoped subject.

    Hard-fails rather than falling back to hashing the raw xid. That fallback is what
    produced a bundle whose `people.csv` could not be joined to any vote at all — an
    empty intersection that no self-check caught and that only surfaced when a report
    tried to name which pseudonym sat in which group. An exporter that cannot key its
    output correctly should stop, not emit rows that look fine and join to nothing.
    """
    import os

    for candidate in (path, DEFAULT_SUB_SECRET_PATH):
        if candidate and Path(candidate).exists():
            raw = Path(candidate).read_text(encoding='utf-8').strip()
            if raw:
                return raw.encode('utf-8')
            raise ValueError(f'sub-secret file {candidate} is empty')
    env = os.environ.get('PARTICIAPI_SUB_SECRET', '').strip()
    if env:
        return env.encode('utf-8')
    raise SystemExit(
        'no PARTICIAPI_SUB_SECRET available.\n'
        f'  Pass --sub-secret-file, place it at {DEFAULT_SUB_SECRET_PATH}, or set '
        '$PARTICIAPI_SUB_SECRET.\n'
        '  This must be the same secret the running app uses: person_key is derived '
        'from HMAC(secret, "<xid>:<conversation_id>"), which is what Particiapi stores '
        'as the subject. A different secret produces keys that join to nothing.')


def _bool(value):
    return None if value is None else bool(value)


def export(client, salt, slugs, *, sub_secret: bytes, with_text: bool,
           with_arguments: bool, with_pseudonyms: bool = False):
    rows = {'conversations': [], 'featured_statements': [], 'statement_provenance': [],
            'statement_similarity': [], 'arguments': [], 'argument_votes': [],
            'people': []}
    stats = []
    tsv_lines = []

    ph = placeholders(client, len(slugs))
    convs = client.query(
        f'SELECT * FROM conversations WHERE slug IN ({ph}) ORDER BY id', tuple(slugs))
    found = {c['slug'] for c in convs}
    missing = [s for s in slugs if s not in found]
    if missing:
        raise LookupError(f'no such conversation slug(s): {", ".join(missing)}')

    # xid → person_key for everyone with a participation in these conversations.
    # The xid is read only to derive the key and is never staged into the bundle.
    conv_ids = [c['id'] for c in convs]
    ph_ids = placeholders(client, len(conv_ids))
    people = client.query(
        f'''SELECT pt.id AS participant_id, pt.xid, pn.pseudonym, pn.conversation_id
            FROM participations pn
            JOIN participants pt ON pt.id = pn.participant_id
            WHERE pn.conversation_id IN ({ph_ids})''', tuple(conv_ids))
    # Keyed by (participant, conversation), not participant alone: the subject Polis
    # stores is conversation-scoped, so one person in two conversations has two keys.
    # The old participant-only dict also collapsed those two rows into one.
    key_by_participant = {
        (p['participant_id'], p['conversation_id']):
            person_key(salt, conversation_subject(sub_secret, p['xid'],
                                                  p['conversation_id']))
        for p in people}

    for conv in convs:
        conv_key = conv['slug']
        rows['conversations'].append([
            conv_key, conv['slug'], conv['polis_id'],
            conv['phase6_polis_conversation_id'], conv['title'], conv['language'],
            conv['access_policy'], conv['phase_route'],
            _bool(conv['active']), _bool(conv['paused']),
            _bool(conv['phase_submission']), _bool(conv['phase_personal_results']),
            _bool(conv['phase_argument_mapping']), _bool(conv['phase_cleanup']),
            _bool(conv['phase_public_results']), _bool(conv['phase_informed_voting']),
            conv['argument_vote_method'], conv['created_at'], conv['closed_at'],
            # How many people joined — the first step of the participation funnel,
            # and a different number from "people who voted at least once".
            sum(1 for p in people if p['conversation_id'] == conv['id']),
        ])
        tsv_lines.append(
            f"{conv['slug']}\t{conv['polis_id']}\t{conv['phase6_polis_conversation_id'] or ''}")

        if with_pseudonyms:
            for person in people:
                if person['conversation_id'] == conv['id']:
                    rows['people'].append([
                        conv_key,
                        key_by_participant[(person['participant_id'], conv['id'])],
                        person['pseudonym'],
                    ])

        featured = client.query(
            f'SELECT * FROM featured_statements WHERE conversation_id = {client.paramstyle} '
            'ORDER BY polis_statement_id', (conv['id'],))
        for fs in featured:
            rows['featured_statements'].append([
                conv_key, fs['polis_statement_id'], fs['phase6_polis_statement_id'],
                _bool(fs['suggested_by_system']), _bool(fs['confirmed_by_admin']),
                fs['created_at'], (fs['statement_text'] or '') if with_text else '',
            ])

        provenance = client.query(
            f'SELECT * FROM statement_provenance WHERE conversation_id = {client.paramstyle} '
            'ORDER BY polis_statement_id', (conv['id'],))
        for pv in provenance:
            rows['statement_provenance'].append([
                conv_key, pv['polis_statement_id'], pv['derived_from_tid'],
                pv['provenance_type'], pv['link_method'], pv['created_at'],
            ])

        if provenance:
            prov_ids = [pv['id'] for pv in provenance]
            tid_by_prov = {pv['id']: pv['polis_statement_id'] for pv in provenance}
            ph_prov = placeholders(client, len(prov_ids))
            scores = client.query(
                f'SELECT * FROM statement_similarity_scores WHERE provenance_id IN ({ph_prov})',
                tuple(prov_ids))
            for sc in scores:
                rows['statement_similarity'].append([
                    conv_key, tid_by_prov[sc['provenance_id']], sc['model'],
                    sc['value'], sc['scored_at'],
                ])

        n_arguments = 0
        if with_arguments and featured:
            fs_ids = [fs['id'] for fs in featured]
            tid_by_fs = {fs['id']: fs['polis_statement_id'] for fs in featured}
            ph_fs = placeholders(client, len(fs_ids))
            arguments = client.query(
                f'SELECT * FROM arguments WHERE featured_statement_id IN ({ph_fs}) ORDER BY id',
                tuple(fs_ids))
            n_arguments = len(arguments)
            for arg in arguments:
                # proposer_pseudonym is read only to tell seeded from participant-
                # written; the identity itself is not exported.
                rows['arguments'].append([
                    conv_key, arg['id'], tid_by_fs[arg['featured_statement_id']],
                    arg['side'], _bool(arg['hidden']),
                    arg['proposer_pseudonym'] is None,
                    arg['created_at'], (arg['body'] or '') if with_text else '',
                ])
            if arguments:
                arg_ids = [a['id'] for a in arguments]
                ph_args = placeholders(client, len(arg_ids))
                votes = client.query(
                    f'SELECT * FROM argument_votes WHERE argument_id IN ({ph_args})',
                    tuple(arg_ids))
                for av in votes:
                    rows['argument_votes'].append([
                        conv_key, av['argument_id'],
                        key_by_participant.get((av['participant_id'], conv['id']), ''),
                        av['value'], av['created_at'],
                    ])

        stats.append({
            'conv_key': conv_key,
            'phase2_zinvite': conv['polis_id'],
            'phase6_zinvite': conv['phase6_polis_conversation_id'],
            'n_participations': sum(1 for p in people if p['conversation_id'] == conv['id']),
            'n_featured': len(featured),
            'n_featured_confirmed': sum(1 for fs in featured if fs['confirmed_by_admin']),
            'n_featured_bridged': sum(1 for fs in featured
                                      if fs['phase6_polis_statement_id'] is not None),
            'n_provenance': len(provenance),
            'n_arguments': n_arguments,
        })

    return rows, stats, tsv_lines


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--out', required=True)
    ap.add_argument('--salt-file', required=True)
    ap.add_argument('--sub-secret-file',
                    help='file holding PARTICIAPI_SUB_SECRET. Defaults to '
                         '/run/secrets/wiki-polis/particiapi-sub-secret, then '
                         '$PARTICIAPI_SUB_SECRET. Required: without it the '
                         'person_key cannot be made to join the Polis half.')
    ap.add_argument('--env', required=True, choices=('local', 'staging', 'prod'))
    ap.add_argument('--db-url', required=True,
                    help='sqlite:///path/to.db or mysql://user:pass@host/db')
    ap.add_argument('--slug', action='append', default=[], help='repeatable')
    ap.add_argument('--all', action='store_true', help='every conversation in the database')
    ap.add_argument('--all-closed', action='store_true', help='every closed conversation')
    ap.add_argument('--with-arguments', action='store_true',
                    help='also export arguments and argument votes')
    ap.add_argument('--with-pseudonyms', action='store_true',
                    help='export the pseudonym for each person, so a report can show '
                         'which opinion group a pseudonym landed in and participants '
                         'can find themselves. Off by default: for anyone who has '
                         'voluntarily revealed their username in the app, this makes '
                         'their opinion group publicly attributable.')
    ap.add_argument('--no-text', dest='with_text', action='store_false',
                    help='omit statement text and argument bodies')
    ap.set_defaults(with_text=True)
    args = ap.parse_args()

    client = open_client(args.db_url)
    slugs = list(args.slug)
    if args.all or args.all_closed:
        where = 'WHERE closed_at IS NOT NULL' if args.all_closed else ''
        slugs += [r['slug'] for r in client.query(f'SELECT slug FROM conversations {where}')]
    slugs = sorted(set(slugs))
    if not slugs:
        ap.error('no conversations selected (--slug / --all / --all-closed)')

    salt = load_salt(args.salt_file)
    sub_secret = load_sub_secret(args.sub_secret_file)
    rows, stats, tsv_lines = export(client, salt, slugs, sub_secret=sub_secret,
                                    with_text=args.with_text,
                                    with_arguments=args.with_arguments,
                                    with_pseudonyms=args.with_pseudonyms)

    writer = BundleWriter(args.out, kind='app', env=args.env, salt=salt,
                          with_text=args.with_text,
                          allow_columns={'pseudonym'} if args.with_pseudonyms else None,
                          extra_manifest={'conversations': stats,
                                          'with_arguments': args.with_arguments,
                                          'with_pseudonyms': args.with_pseudonyms,
                                          # So a rotated secret is visible rather
                                          # than silently unjoinable.
                                          'sub_secret_id': secret_id(sub_secret)})
    writer.add_csv('conversations.csv', CONVERSATION_COLUMNS, rows['conversations'])
    writer.add_csv('featured_statements.csv', FEATURED_COLUMNS, rows['featured_statements'])
    writer.add_csv('statement_provenance.csv', PROVENANCE_COLUMNS, rows['statement_provenance'])
    writer.add_csv('statement_similarity.csv', SIMILARITY_COLUMNS, rows['statement_similarity'])
    if args.with_arguments:
        writer.add_csv('arguments.csv', ARGUMENT_COLUMNS, rows['arguments'])
        writer.add_csv('argument_votes.csv', ARGUMENT_VOTE_COLUMNS, rows['argument_votes'])
    if args.with_pseudonyms:
        writer.add_csv('people.csv', PEOPLE_COLUMNS, rows['people'])

    try:
        writer.close()
    except SelfCheckError as exc:
        print(f'\nABORTED: {exc}', file=sys.stderr)
        return 2

    tsv_path = Path(args.out) / 'conversations.tsv'
    tsv_path.write_text('\n'.join(tsv_lines) + '\n', encoding='utf-8')
    print(f'\n  wrote {tsv_path} — pass it to export_polis_bundle.py --conversations')

    for s in stats:
        phase6 = s['phase6_zinvite'] or 'none'
        print(f"  {s['conv_key']}: phase2={s['phase2_zinvite']} phase6={phase6}, "
              f"{s['n_featured_confirmed']}/{s['n_featured']} featured confirmed, "
              f"{s['n_featured_bridged']} bridged to phase 6, "
              f"{s['n_provenance']} provenance link(s)")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

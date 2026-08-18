#!/usr/bin/env python3
"""Prove both databases are reachable and readable before exporting anything.

Worth its own step because the two most likely failures are silent-ish and happen
late:

  * **Empty connection string.** Toolforge injects envvars into jobs and the
    webservice, not into an interactive bastion shell. Typed on the bastion,
    `$DATABASE_URL` expands to nothing and the driver reports something unhelpful.
  * **A missing grant.** The Polis connection uses the read-only `wiki_polis_ro`
    role, set up with `GRANT SELECT ON ALL TABLES IN SCHEMA public`. Any table
    created *after* that grant ran is not covered — and `particiapi_users` (the
    identity join) and `math_main` (the server's own clustering) are exactly the
    kind of table that could be missing without anything else looking wrong.

Every probe is a bounded SELECT. Nothing is written and nothing is exported.

    python3 preflight.py --app-db-url "$DATABASE_URL" \
                         --polis-db-url "$POLIS_DATABASE_URL" \
                         --slug 2026-nlwiki-arbcom
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from export_app_bundle import open_client  # noqa: E402
from export_polis_bundle import Psycopg2Client  # noqa: E402

APP_TABLES = ['conversations', 'participants', 'participations', 'featured_statements',
              'statement_provenance', 'statement_similarity_scores', 'arguments',
              'argument_votes']
POLIS_TABLES = ['zinvites', 'conversations', 'comments', 'participants', 'votes',
                'votes_latest_unique', 'particiapi_users', 'math_main']

OK, BAD = '  ok  ', ' FAIL '


def probe(client, table: str) -> tuple[bool, str]:
    try:
        rows = client.query(f'SELECT COUNT(*) AS n FROM {table}')
        return True, f'{int(list(rows[0].values())[0]):,} rows'
    except Exception as exc:
        return False, str(exc).strip().splitlines()[0][:90]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--app-db-url')
    ap.add_argument('--polis-db-url')
    ap.add_argument('--slug', action='append', default=[])
    args = ap.parse_args()

    failures = 0

    if args.app_db_url:
        print('app database (ToolsDB)')
        try:
            client = open_client(args.app_db_url)
        except Exception as exc:
            print(f'{BAD} could not connect: {exc}')
            return 2
        for table in APP_TABLES:
            good, detail = probe(client, table)
            failures += not good
            print(f'{OK if good else BAD} {table:<30} {detail}')

        for slug in args.slug:
            rows = client.query(
                f'SELECT slug, polis_id, phase6_polis_conversation_id '
                f'FROM conversations WHERE slug = {client.paramstyle}', (slug,))
            if not rows:
                print(f'{BAD} slug {slug!r} not found')
                failures += 1
            else:
                row = rows[0]
                print(f'{OK} slug {slug!r}: phase2={row["polis_id"]} '
                      f'phase6={row["phase6_polis_conversation_id"] or "none"}')
        print()
    else:
        print('app database: skipped (no --app-db-url)\n')

    if args.polis_db_url:
        print('Polis database (VPS)')
        try:
            polis = Psycopg2Client(args.polis_db_url)
        except Exception as exc:
            print(f'{BAD} could not connect: {str(exc).strip().splitlines()[0]}')
            return 2
        for table in POLIS_TABLES:
            good, detail = probe(polis, table)
            failures += not good
            print(f'{OK if good else BAD} {table:<30} {detail}')

        # The zinvites named by the app database must actually resolve here.
        if args.app_db_url and args.slug:
            for slug in args.slug:
                rows = client.query(
                    f'SELECT polis_id, phase6_polis_conversation_id FROM conversations '
                    f'WHERE slug = {client.paramstyle}', (slug,))
                for row in rows:
                    for phase, zinvite in ((2, row['polis_id']),
                                           (6, row['phase6_polis_conversation_id'])):
                        if not zinvite:
                            continue
                        found = polis.query(
                            'SELECT z.zid, '
                            '  (SELECT COUNT(*) FROM votes v WHERE v.zid = z.zid) AS n_votes, '
                            '  (SELECT COUNT(*) FROM comments c WHERE c.zid = z.zid) AS n_stmts, '
                            '  (SELECT COUNT(*) FROM math_main m WHERE m.zid = z.zid) AS n_math '
                            'FROM zinvites z WHERE z.zinvite = %s', (zinvite,))
                        if not found:
                            print(f'{BAD} phase {phase} zinvite {zinvite!r} not in zinvites')
                            failures += 1
                            continue
                        r = found[0]
                        note = '' if r['n_math'] else '  ← no math_main: the clustering ' \
                                                      'has not run for this conversation'
                        print(f'{OK} phase {phase} {zinvite}: {r["n_votes"]:,} votes, '
                              f'{r["n_stmts"]} statements, math_main={r["n_math"]}{note}')
                        if not r['n_math']:
                            failures += 1
        print()
    else:
        print('Polis database: skipped (no --polis-db-url)\n')

    if not (args.app_db_url or args.polis_db_url):
        print('nothing was checked — pass --app-db-url and/or --polis-db-url.')
        print('(On Toolforge these are empty unless you are inside a job or the '
              'webservice shell.)')
        return 2
    if failures:
        print(f'{failures} problem(s) found — fix these before exporting.')
        return 1
    print('all checks passed — safe to export.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

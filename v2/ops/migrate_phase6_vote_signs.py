#!/usr/bin/env python3
"""One-off remediation: negate the sign of existing Phase 6 (informed voting) votes
in the Polis database so they match the corrected Polis-native convention.

Background
----------
Before the phase6 vote fix, `phase6_vote` forwarded the app's button sign (1=agree)
to Polis verbatim, but Polis stores the opposite (-1=agree, +1=disagree, 0=pass).
So every Phase 6 vote cast before the fix is sign-inverted relative to Phase 2 and
to the vote-count SQL, making informed-vote counts swap agree/disagree. This script
flips the sign of those pre-fix votes (pass, 0, is left unchanged).

CRITICAL — run EXACTLY ONCE, during a voting freeze
---------------------------------------------------
Negation is its own inverse: running it twice re-inverts and silently corrupts the
data. There is no way to tell a pre-fix (inverted) vote from a post-fix (correct)
one by value alone, so:

  * Phase 6 voting MUST be paused/closed while this runs, so that NO post-fix
    (already-correct) votes exist to be wrongly re-inverted. Every remaining Phase 6
    vote must be pre-fix.
  * A local run-log (``--log-file``) records applied zids and refuses to re-apply
    them without ``--force``. Keep that log; do not run on a second machine.

Recommended operational sequence
--------------------------------
  1. Pause / close all Phase 6 rounds (no voting during the window).
  2. Take a Polis database backup.
  3. Dry-run this script and eyeball the affected conversations + counts.
  4. Deploy the phase6 vote fix (so new votes store the correct sign).
  5. Run with --apply.
  6. Re-open the rounds.
  (Steps 4 and 5 may swap: with voting frozen, all existing votes are pre-fix either
  way. What must not happen is new votes being cast between steps 1 and 5.)

Note: this does not, and cannot, repair the *identity* of pre-fix votes — those were
recorded under throwaway anonymous Polis uids and are not linkable to a participant.
This only corrects their sign.

Usage
-----
  # dry run (default) — reports affected conversations + vote counts, changes nothing
  uv run python ops/migrate_phase6_vote_signs.py --polis-db "$POLIS_DATABASE_URL"

  # apply
  uv run python ops/migrate_phase6_vote_signs.py --polis-db "$POLIS_DATABASE_URL" --apply

  # restrict to explicit zinvites instead of auto-discovering from the wiki-polis DB
  uv run python ops/migrate_phase6_vote_signs.py --polis-db "$POLIS_DATABASE_URL" \
      --zinvites 7yhhfecxzy,abcd123456
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

import psycopg2


def _discover_phase6_zinvites() -> tuple[list[str], dict[str, str]]:
    """Phase 6 conversation zinvites + a {zinvite: slug} label map, from the wiki-polis
    DB (the only source that knows which Polis conversations are Phase 6). Uses the
    module-level app so create_app runs once (a second call collides on 'sessions')."""
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from app import app                          # noqa: E402  (module-level app)
    from db import Conversation                  # noqa: E402
    with app.app_context():
        rows = (Conversation.query
                .filter(Conversation.phase6_polis_conversation_id.isnot(None))
                .with_entities(Conversation.slug,
                               Conversation.phase6_polis_conversation_id)
                .all())
    return [z for _slug, z in rows], {z: slug for slug, z in rows}


def _relkind(cur, relname: str) -> str | None:
    cur.execute("SELECT relkind FROM pg_class WHERE relname = %s", (relname,))
    row = cur.fetchone()
    return row[0] if row else None


def _load_log(path: str) -> set[str]:
    if not path or not os.path.exists(path):
        return set()
    with open(path) as f:
        return {rec['zinvite'] for rec in (json.loads(l) for l in f if l.strip())}


def _append_log(path: str, zinvite: str, n: int) -> None:
    if not path:
        return
    with open(path, 'a') as f:
        f.write(json.dumps({
            'zinvite': zinvite, 'flipped': n,
            'at': datetime.now(timezone.utc).isoformat(),
        }) + '\n')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--polis-db', default=os.environ.get('POLIS_DATABASE_URL', ''),
                        help='Polis Postgres connection URL (or POLIS_DATABASE_URL).')
    parser.add_argument('--zinvites', default='',
                        help='Comma-separated zinvites to limit to; default: '
                             'auto-discover all Phase 6 conversations from wiki-polis.')
    parser.add_argument('--apply', action='store_true',
                        help='Actually negate signs. Without this, dry-run only.')
    parser.add_argument('--force', action='store_true',
                        help='Re-apply even to zinvites already in the run-log. '
                             'DANGEROUS — re-inverts. Only with a fresh backup.')
    parser.add_argument('--log-file',
                        default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                             'phase6_sign_fix.applied.log'),
                        help='Run-log guarding against double-application.')
    args = parser.parse_args()

    if not args.polis_db:
        print('ERROR: --polis-db (or POLIS_DATABASE_URL) is required.', file=sys.stderr)
        return 2

    slug_by_zinvite: dict[str, str] = {}
    if args.zinvites:
        zinvites = [z.strip() for z in args.zinvites.split(',') if z.strip()]
    else:
        zinvites, slug_by_zinvite = _discover_phase6_zinvites()
    if not zinvites:
        print('No Phase 6 conversations found — nothing to do.')
        return 0

    already = _load_log(args.log_file)
    print(f'Mode: {"APPLY" if args.apply else "DRY-RUN"}   '
          f'Phase 6 conversations: {len(zinvites)}')

    conn = psycopg2.connect(args.polis_db)
    conn.autocommit = False
    total_flipped = 0
    try:
        with conn.cursor() as cur:
            vlu_kind = _relkind(cur, 'votes_latest_unique')
            # In this Polis build votes_latest_unique is an ordinary TABLE ('r'), NOT a
            # view — the counts SQL and the readback both read it, so it must be negated
            # alongside the append-only `votes` log or the correction won't be visible.
            # ('v' view → reflects `votes` automatically; 'm' matview → refresh.)
            _kinds = {'r': 'table (will be updated directly)',
                      'v': 'view (reflects source automatically)',
                      'm': 'materialized view (will be refreshed)'}
            print(f'votes_latest_unique relkind: {vlu_kind!r} — '
                  f'{_kinds.get(vlu_kind, "unknown — verify manually")}')

            applied: list[tuple[str, int]] = []  # (zinvite, flipped) to log after commit
            for z in zinvites:
                label = slug_by_zinvite.get(z, z)
                cur.execute('SELECT zid FROM zinvites WHERE zinvite = %s', (z,))
                row = cur.fetchone()
                if not row:
                    print(f'  [skip] {label} ({z}): no such zinvite in Polis')
                    continue
                zid = row[0]
                cur.execute('SELECT COUNT(*) FROM votes WHERE zid = %s AND vote <> 0', (zid,))
                n = cur.fetchone()[0]

                if z in already and not args.force:
                    print(f'  [skip] {label} ({z}): already in run-log '
                          f'({n} sign-bearing votes) — use --force to override')
                    continue

                print(f'  {label} ({z}, zid={zid}): {n} sign-bearing votes to flip')
                if args.apply:
                    # Negate the append-only log...
                    cur.execute('UPDATE votes SET vote = -vote WHERE zid = %s AND vote <> 0',
                                (zid,))
                    total_flipped += cur.rowcount
                    # ...and the read path. votes_latest_unique is a real table here, so
                    # it must be negated directly (a view would follow `votes`; a matview
                    # is refreshed instead).
                    if vlu_kind == 'r':
                        cur.execute('UPDATE votes_latest_unique SET vote = -vote '
                                    'WHERE zid = %s AND vote <> 0', (zid,))
                    elif vlu_kind == 'm':
                        cur.execute('REFRESH MATERIALIZED VIEW votes_latest_unique')
                    applied.append((z, n))

            if args.apply:
                conn.commit()
                # Log only after a successful commit, only the zinvites actually flipped.
                for z, n in applied:
                    _append_log(args.log_file, z, n)
                print(f'\nAPPLIED — flipped {total_flipped} vote rows across '
                      f'{len(applied)} conversation(s). Run-log: {args.log_file}')
                if vlu_kind not in ('v', 'm', 'r'):
                    print('WARNING: votes_latest_unique has an unexpected kind; verify it '
                          'reflects the update (a Polis math recompute may be needed).')
            else:
                print('\nDRY-RUN — no changes made. Re-run with --apply to execute.')
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

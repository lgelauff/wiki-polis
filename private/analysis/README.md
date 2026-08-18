# wiki-polis analysis — runbook

Two exporters run **on the servers** and produce a de-identified bundle; the notebook
runs **locally** and never touches a database. That split is what lets real data be
analysed without any personal information leaving the host.

```
Toolforge (app DB)  ──export_app_bundle.py──▶  app/     ─┐
                                                         ├─▶  wiki_polis_analysis.ipynb
VPS (Polis Postgres) ─export_polis_bundle.py─▶  polis/  ─┘
```

## Step 0 — the shared salt (once)

Both bundles derive `person_key = HMAC(salt, xid)`. They only join if both hosts use
the **same salt**, so generate it once and copy it to both:

```bash
openssl rand -hex 32 > ~/.wiki-polis-export-salt && chmod 600 ~/.wiki-polis-export-salt
```

Never commit it, never put it in a bundle. Each manifest records
`salt_id = sha256(salt)[:8]`; the notebook refuses to run if the two disagree, so a
mismatch fails loudly instead of silently producing an empty join.

## Both steps run on Toolforge

The tool already holds `POLIS_DATABASE_URL` — the VPS Polis Postgres, reached over the
private network as the read-only `wiki_polis_ro` role, which has `SELECT` on every table
in the public schema. So both halves can be exported from one host, and no VPS shell is
needed. `psycopg2` is already installed there, because the admin stats panel uses it.

Copy `bundle.py`, `export_app_bundle.py` and `export_polis_bundle.py` to the tool, then:

## Step 1 — app database. Run this first.

It also writes `conversations.tsv`, which step 2 needs.

```bash
python3 export_app_bundle.py \
    --db-url "$DATABASE_URL" \
    --slug 2026-nlwiki-arbcom \
    --salt-file ~/.wiki-polis-export-salt \
    --with-pseudonyms \
    --env prod --out ./arbcom_export
```

Gives: conversation settings and phase flags, the featured-statement bridge, and
**statement provenance** — which statement was submitted as an improvement on which
other statement, plus the similarity score recorded at submission. This half exists
nowhere else: no Polis export can produce it.

Add `--with-arguments` for arguments and argument votes.

## Step 2 — Polis database (still on Toolforge)

```bash
python3 export_polis_bundle.py \
    --db-url "$POLIS_DATABASE_URL" \
    --conversations ./arbcom_export/conversations.tsv \
    --salt-file ~/.wiki-polis-export-salt \
    --env prod --out ./arbcom_export
```

Then `scp` the `arbcom_export/` directory back.

If you ever need to run this on the VPS itself instead (no psycopg2 there), swap the
first flag for a psql pipe — it needs nothing but docker:

```bash
--psql-cmd 'docker compose exec -T postgres psql -U polis polis'
```

Gives: every current vote and the full vote history, statements with their moderation
state, per-conversation pids, and `math_main` — **the server's own clustering output**,
which the analysis treats as the headline result rather than recomputing it.

Both exporters are read-only (SELECT only) and refuse to write anything if their PII
self-check fails.

## Step 3 — analyse (locally)

```bash
./.venv/bin/python -c "import pipeline; r = pipeline.run_all('arbcom_export'); \
    [print(c) for c in r['checks']]"
```

or open `wiki_polis_analysis.ipynb` with the `.venv` kernel.

## What is and is not in a bundle

**In:** `person_key` (salted, per-export), per-conversation `pid`, `tid`, votes and
timestamps, statement text (unless `--no-text`), moderation state, seed flags,
provenance links, similarity scores, conversation settings, `math_main.data`.

**Never:** `mw_user_id`, `mw_username`, `public_username`, `revealed_at`, `xid`,
`particiapi_users.subject`, the Polis `users` table, invites, content flags, audit
events, eligibility detail, notification preferences.

**Never: statement and argument authorship.** `statements.csv` carries no author
column and `arguments.csv` carries only `is_seeded`. The author `pid` is read from
Polis and dropped before anything is staged. This is a *join* rule, not a column rule:
an author key is harmless alone, but combined with `people.csv` it reconstructs who
wrote what. See [`.claude/todo-pii-export-guard.md`](../../.claude/todo-pii-export-guard.md).

**Pseudonyms: only with `--with-pseudonyms`.** Off by default. Writes `people.csv`
(`person_key`, `pseudonym`) so a report can show which opinion group a pseudonym
landed in and participants can find themselves. No username is exported in any mode,
so the bundle cannot tie a pseudonym to a Wikimedia account on its own — but note that
`people.csv` and `votes_latest.csv` share `person_key`, so a bundle exported this way
does link a pseudonym to that person's individual votes.

Statement text is included by default because the derivative analysis needs to compare
a statement with its rewording. A bundle with text is participant-authored content:
treat it as confidential and keep it out of anything public. `--no-text` on both
exporters gives a purely structural bundle.

# Polis Data Model (reference)

> **Source:** [compdemocracy/polis PR #2556](https://github.com/compdemocracy/polis/pull/2556)
> by @lgelauff — pending upstream merge. This copy is temporary; remove once the PR lands
> and link to the upstream doc instead.

This document is an orientation to the core PostgreSQL data model — the tables a
developer touches when working on conversations, comments, votes, and participants. It
is not an exhaustive column-by-column reference; the **source of truth is always the SQL
in `server/postgres/migrations/`** (the `000000_initial.sql` file plus the numbered
migrations applied on top of it). The goal here is to make the schema *legible*: how
the pieces relate, and the handful of conventions that surprise people.

---

## ⚠️ wiki-polis integration notes

These notes document where wiki-polis's assumptions need to agree with the Polis schema.

### Vote sign convention

The Polis `votes` table stores:

```
vote SMALLINT   -- -1 = Agree, 1 = Disagree, 0 = Pass/Unsure
```

This is **opposite to the intuitive sign**. The CSV export negates every vote so that
Agree = +1 in exports, but the raw table and the vote API use -1 = Agree.

wiki-polis sends `value: 1` for Agree and `value: -1` for Disagree via Particiapi's
`PUT /api/conversations/{id}/votes/{tid}`. Particiapi translates these before writing to
Polis. Verify Particiapi's translation if vote data looks inverted.

### tid and pid start at 0

`tid` (statement ID) and `pid` (participant ID) are **per-conversation** and assigned by
database triggers (`tid_auto`, `pid_auto`). **The first statement in a conversation gets
`tid = 0`.** Any code that treats `tid` or `pid` as truthy will incorrectly exclude the
first statement or participant.

wiki-polis fix: template guards use `{% if item.phase6_stmt_id is not none %}` not
`{% if item.phase6_stmt_id %}`. The same care applies anywhere a Polis integer ID is
checked for presence.

### Submitting a statement casts a vote

Submitting a statement writes a `votes` row for the author: an **agree (`-1`)** on their
own `tid`, from the author's own `pid`. No client asks for it, and nothing in wiki-polis
casts it — Polis records it as part of accepting the statement.

So a conversation's vote count is *participant votes + one per statement*, and every
statement starts with one agree it did not earn. Any count, tally or turnout figure
derived from `votes` has to decide whether to exclude author votes; a per-participant
average silently includes them.

Reproduced on the local stack (2026-09-02): a fresh conversation with 0 votes, one
statement submitted through `POST /api/conversations/{id}/statements/` and no vote call
made, leaves exactly one row — `pid=0, tid=0, vote=-1` — whose `pid` equals the author's
in `comments`. This is also why a simulated Phase 6 round of 30 voters over 5 statements
lands 155 rows in `votes`, not 150.

### zinvite vs zid

wiki-polis stores and uses the `zinvite` (the opaque string like `6tpsckec8u`), not the
internal `zid`. The `zinvites` table maps between them. Particiapi accepts the `zinvite`
in its API paths, translating to `zid` internally.

### vis_type gates results

`vis_type = 0` (the default) means the results endpoint returns nothing even when votes
exist. wiki-polis sets `vis_type = 1` via the admin API when `phase_public_results` or
`phase_personal_results` is enabled. This is the most common cause of an empty Results tab.

---

## Keys and conventions

- **`zid`** — conversation id. `SERIAL`, globally unique. Internal; never shown to users.
- **`tid`** — comment (statement) id. **Per-conversation**, starts at 0 in every conversation. Real key is `(zid, tid)`.
- **`pid`** — participant id. **Per-conversation**, starts at 0 per conversation. Real key is `(zid, pid)`.
- **`uid`** — user (account) id. `SERIAL`, globally unique.
- **`zinvite`** — public opaque conversation identifier (string in URLs). Maps to `zid` via `zinvites` table.
- **Timestamps are `BIGINT` epoch-milliseconds** (`created`, `modified`, …). Use `to_timestamp(created / 1000.0)` to read.
- **`-1` is not "no"** — several columns use `-1` as a specific enum state (vote = Agree, mod = rejected). Read column comments before assuming.

---

## Core tables

### `conversations` (keyed by `zid`)

One row per conversation. Key operational columns:

- `is_active`, `is_public`, `is_draft` — lifecycle/visibility.
- `strict_moderation` — new comments must be approved before voting.
- `vis_type` — **0 = results off (default), 1 = on.** Empty results tab = check this first.

### `comments` (keyed by `(zid, tid)`)

One row per statement. `txt` is the statement text.

- `mod` — `-1` rejected, `0` unmoderated, `1` accepted.
- `is_seed` — seeded by moderator vs submitted by participant.
- `active` — false hides regardless of `mod`.

### `votes` and `votes_latest_unique` (keyed by `(zid, pid, tid)`)

- `votes` is **append-only** (vote changes insert new rows).
- `votes_latest_unique` is the **authoritative current vote** — a `RULE` upserts it on every `votes` insert. Query this for current state.
- `vote` value: **-1 = Agree, 1 = Disagree, 0 = Pass/Unsure** (opposite of the data export sign).

**Phase 6 vote queries use `votes_latest_unique`, not `votes`.** The Phase 6 informed
voting round lives in a separate Polis conversation (`phase6_polis_conversation_id`). All
wiki-polis result queries (`get_phase6_vote_counts`, `get_phase6_participant_count`,
`get_personal_votes`) query `votes_latest_unique` to get one-vote-per-participant-per-statement,
consistent with what Polis math uses. Filtering to confirmed featured statement tids and
optionally excluding banned pids happens in the SQL `WHERE` clause — never post-hoc in Python.

### `participants` (keyed by `(zid, pid)`)

One row per (user, conversation). Tracks `vote_count`, `last_interaction`.

### `users` (keyed by `uid`)

Accounts. Both registered owners and ephemeral participants are users.

### `xids`

Maps an external identifier (`xid`, from an embedding site) to a `uid`, scoped to an `owner`. This is how wiki-polis attaches Wikimedia user identity to Polis participants. `UNIQUE (owner, xid)`.

### `math_main`

The headline clustering/PCA result. `data jsonb` holds opinion groups and comment stats. Written by the math service; the server only reads it. Empty = math hasn't run yet, or `vis_type = 0`.

---

## Full upstream document

The complete document (including the "everything else at a glance" table of all 61 tables, legacy social login notes, and references to other docs) is in [compdemocracy/polis PR #2556](https://github.com/compdemocracy/polis/pull/2556). Once merged it will live at `server/docs/data-model.md` in the Polis repo.

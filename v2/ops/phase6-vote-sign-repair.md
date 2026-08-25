# Phase 6 vote-sign: verify, then repair

Two parts. **Verification runs first and proves the bug on your own data** — repair nothing
until step 2 shows the mismatch.

Polis Postgres lives on the **Cloud VPS**. ToolsDB — which knows *which* Polis conversations
are phase 6 — lives on the **Toolforge bastion**. You need both. All shell access is yours to
initiate; nothing here should be run by an agent.

---

## 1. Bastion — which conversations have a phase 6?

Log into the bastion and `become wiki-polis`, then `sql tools`:

```sql
USE `s57499__wiki-polis`; SELECT id, slug, polis_id AS phase2_zinvite, phase6_polis_conversation_id AS phase6_zinvite FROM conversations WHERE phase6_polis_conversation_id IS NOT NULL;
```

Note **both** zinvites per row. `polis_id` is the phase-2 conversation; `phase6_polis_conversation_id`
is a separate Polis conversation. The pair is the whole point — the verification compares them.

---

## 2. Cloud VPS — prove the mismatch

⚠️ **Pin the container name.** Production and staging Polis run side by side on that host —
`particiapp-docker_postgres_1` (port 5432, production) and `wiki-polis-staging_postgres_1`
(port 5442). A grepped name matches both and will silently pick one, or fail confusingly by
passing the second name as a command. Confirm which you are on before any write: query
`zinvites` for the phase-6 zinvite in the container you intend to use — a `zid` back means
production, empty means staging.

On the VPS, open psql in that pinned container. Substituting the zinvites from step 1:

```sql
SELECT 'phase2' AS phase, v.vote, count(*) FROM votes v WHERE v.zid = (SELECT zid FROM zinvites WHERE zinvite='<PHASE2_ZINVITE>') GROUP BY v.vote UNION ALL SELECT 'phase6', v.vote, count(*) FROM votes v WHERE v.zid = (SELECT zid FROM zinvites WHERE zinvite='<PHASE6_ZINVITE>') GROUP BY v.vote ORDER BY phase, vote;
```

This does **not** prove direction on its own — both phases legitimately hold a mix. It gives
you the row counts the repair must match in step 5.

### The decisive check: cast one vote whose intent you know

1. Open the phase 6 round on https://wiki-polis.toolforge.org as yourself.
2. Deliberately click **Agree** on one card; note the statement.
3. Re-run, newest first:

```sql
SELECT v.pid, v.tid, v.vote, to_timestamp(v.created/1000) AS at FROM votes v WHERE v.zid=(SELECT zid FROM zinvites WHERE zinvite='<PHASE6_ZINVITE>') ORDER BY v.created DESC LIMIT 5;
```

**Your Agree should be `vote = -1`.** If it is `+1`, the bug is confirmed on production.
Polis convention is `-1 = agree` — `v2/polis_admin.py:153` counts on it and `:211` states it.

For contrast, cast an Agree in phase 2 of any open consultation and confirm `-1` there.
Two Agrees, opposite signs, is the finding.

*Reference — the same test on a local stack running `a32d61c` (production code):*

| phase | action | row | stored |
|---|---|---|---|
| 2 | Agree | `zid=5, pid=76, tid=10` | **−1** |
| 6 | Agree, unfixed | `zid=6, pid=31, tid=3` | **+1** |
| 6 | Agree, fixed | `zid=6, pid=32, tid=4` | **−1** |

---

## 3. Deploy the code fix BEFORE repairing

Repair first and new inverted votes keep arriving into repaired data, with nothing marking
which rows are which. Deploy `fix/phase6-vote-sign`, confirm with a fresh Agree that new votes
store `-1`, and only then touch the old ones.

---

## 4. Snapshot before you overwrite

**Test votes are evidence.** They are the only record of what the buggy path actually wrote,
and they may matter later in ways that are not obvious now — reconstructing whether a result
shown to someone was affected, validating the repair itself, or as a fixture for a regression
test against real data rather than mocks. `UPDATE ... SET vote = -vote` destroys that record.

Copy the affected rows first. A plain table in the same database, so it travels with any dump:

```sql
CREATE TABLE IF NOT EXISTS votes_phase6_presign_backup (LIKE votes INCLUDING ALL);
```

```sql
INSERT INTO votes_phase6_presign_backup SELECT * FROM votes WHERE zid = (SELECT zid FROM zinvites WHERE zinvite='<PHASE6_ZINVITE>');
```

Confirm the copy matches before going further:

```sql
SELECT (SELECT count(*) FROM votes_phase6_presign_backup) AS backed_up, (SELECT count(*) FROM votes WHERE zid=(SELECT zid FROM zinvites WHERE zinvite='<PHASE6_ZINVITE>')) AS live;
```

The two numbers must be equal. This also gives you a genuine rollback: the pre-repair state is
recoverable even after `COMMIT`, which the transaction alone does not give you.

---

## 5. Repair — one statement, scoped, counted

⚠️ **Not idempotent.** Running it twice returns the data to broken. Record step 2's counts,
run once, verify, do not re-run.

```sql
BEGIN;
```

```sql
UPDATE votes SET vote = -vote WHERE zid = (SELECT zid FROM zinvites WHERE zinvite='<PHASE6_ZINVITE>') AND vote <> 0;
```

The reported row count **must equal the non-zero total from step 2**. Passes (`vote = 0`) are
excluded deliberately — negating zero is a no-op that would pad the count and mask a mistake.

Verify before committing; the distribution should mirror, `-1` and `+1` swapped, `0` unchanged:

```sql
SELECT vote, count(*) FROM votes WHERE zid=(SELECT zid FROM zinvites WHERE zinvite='<PHASE6_ZINVITE>') GROUP BY vote ORDER BY vote;
```

Then `COMMIT;` — or `ROLLBACK;` if anything is off.

Repeat **one conversation at a time**, verifying each. A wrong row count is recoverable when
it is the only conversation in the transaction.

---

## 6. Confirm end to end

Re-run the step-2 vote test: a fresh Agree stores `-1`, and previously-cast votes now read the
direction the participant intended. Spot-check one participant whose intent you know against
the phase 6 results view.

Keep `votes_phase6_presign_backup`. It is small, and it is the only copy of what the bug wrote.

---

## Why not #285's script

`v2/ops/migrate_phase6_vote_signs.py` (208 lines) does this with discovery, dry-run and a
run-log. Good work, but its idempotency guard is a **local JSON file** — its own docstring says
*"Keep that log; do not run on a second machine."* With a handful of phase-6 rows on
production, a counted `UPDATE` in a transaction is smaller, holds no hidden state, and is
verified by numbers in front of you rather than by a file that can go missing.

Keep the script for the day a real consultation finishes phase 6 with the bug present. Not today.

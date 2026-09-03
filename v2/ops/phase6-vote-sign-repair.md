# Phase 6 vote-sign: verify, then repair

Phase 6 informed votes were written to Polis with the **opposite sign** to every other vote — an
Agree stored as a disagree. This covers verifying that on your own data, then repairing it.

**The frontend comes down for the whole operation.** That is what makes this simple: with nothing
able to write, every stored phase-6 vote is uniformly inverted, so the repair is one plain
statement per table with no time boundary to reason about, and no window in which participants
see a mix of both conventions.

Two databases, two hosts. Polis Postgres lives on the **Cloud VPS**; ToolsDB, which knows *which*
Polis conversations are phase 6, lives on the **Toolforge bastion**. All shell access is yours to
initiate.

---

## 1. Bastion — which conversations have a phase 6?

Log in, `become wiki-polis`, then `sql tools`:

```sql
USE `s57499__wiki-polis`; SELECT id, slug, polis_id AS phase2_zinvite, phase6_polis_conversation_id AS phase6_zinvite FROM conversations WHERE phase6_polis_conversation_id IS NOT NULL;
```

Note **both** zinvites per row. `polis_id` is the phase-2 conversation; `phase6_polis_conversation_id`
is a separate Polis conversation. Every phase-6 zinvite in this list needs repairing.

---

## 2. Cloud VPS — prove the bug on your own data

⚠️ **Pin the container name.** Production and staging Polis run side by side on that host:
`particiapp-docker_postgres_1` (port 5432, **production**) and `wiki-polis-staging_postgres_1`
(port 5442). A grepped name matches both. Confirm which you are on before any write — query
`zinvites` for your phase-6 zinvite; a `zid` back means production, empty means staging.

Every SQL block below runs inside that container:

```bash
docker exec -it particiapp-docker_postgres_1 psql -U polis -d polis   # production
docker exec -it wiki-polis-staging_postgres_1 psql -U polis -d polis  # staging
```

### The decisive check: cast one vote whose intent you know

> ⚠️ **The round must not be paused, and the consultation must be active.** Both write
> paths refuse otherwise — the API returns `409 Informed voting is not open.`, the legacy
> route `403` — and a paused round is the state this runbook otherwise wants the tool in.
> Record `active` and `paused` in step 1, unpause for this check and for step 7, and
> restore the recorded state afterwards.
>
> This deliberately writes one genuinely inverted row, so do it **before** the repair,
> never after. A vote cast between the repair and the deploy breaks step 5's uniformity
> premise and leaves both conventions in one table.

1. Open the phase 6 round as yourself and deliberately click **Agree** on one card.
2. Read it back, newest first:

```sql
SELECT pid, tid, vote, to_timestamp(created/1000) AS at FROM votes WHERE zid = (SELECT zid FROM zinvites WHERE zinvite='<PHASE6_ZINVITE>') ORDER BY created DESC LIMIT 5;
```

**Your Agree should be `vote = -1`.** If it is `+1`, the bug is confirmed. Polis convention is
`-1 = agree` — `polis_admin.py:153` counts on it and `:211` states it.

*Reference — the same test on a local stack running production's commit:*

| phase | action | stored |
|---|---|---|
| 2 | Agree | **−1** |
| 6 | Agree, before fix | **+1** |
| 6 | Agree, after fix | **−1** |

---

## 3. Stop the frontend

```bash
cd ~ && toolforge webservice stop
```

Confirm it is actually down before going further — a repair that races live voting is the one
thing this procedure exists to avoid:

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://wiki-polis.toolforge.org/
```

Anything other than a normal page (503, connection refused) is what you want. Then confirm no
votes are still arriving — run this twice, a minute apart, and the count must not move:

```sql
SELECT count(*) FROM votes WHERE zid = (SELECT zid FROM zinvites WHERE zinvite='<PHASE6_ZINVITE>');
```

Everything from here happens with the tool offline.

---

## 4. Snapshot both tables

**These votes are evidence.** They are the only record of what the buggy path wrote, and may
matter later — reconstructing whether a result shown to someone was affected, validating the
repair, or as a fixture for a regression test against real data. Negating them destroys that.

### Two tables, not one

⚠️ **This is the part that makes or breaks the repair.**

- `votes(zid, pid, tid, vote, created)` — append-only history. Has `created`, **no `modified`**.
- `votes_latest_unique(zid, pid, tid, vote, modified)` — **the authoritative current vote**, and
  **what every phase-6 read path queries** (`polis_admin.py:156, 182, 220, 232, 265, 305, 327`).
  Has `modified`, **no `created`**.

`votes_latest_unique` is maintained by an **INSERT rule** on `votes` (`ref_polis-data-model.md:93`,
`guide_runbook.md:154-157`). A row rewrite fires no INSERT rule, so **repairing `votes` alone
changes nothing that anyone sees.**

> **Rehearsed 2026-08-25** on a local Polis stack, in a rolled-back transaction. Repairing
> `votes` alone reported `UPDATE 6` and mirrored all six rows — while `votes_latest_unique`
> came back **byte-for-byte unchanged**. Repairing both produced identical mirrored data in
> each. The single-table version fails silently *and reports success*.

```sql
CREATE TABLE IF NOT EXISTS votes_phase6_presign_backup (LIKE votes INCLUDING ALL);
CREATE TABLE IF NOT EXISTS vlu_phase6_presign_backup (LIKE votes_latest_unique INCLUDING ALL);
```

Copy this conversation's rows, guarded so a re-run cannot double-insert:

```sql
INSERT INTO votes_phase6_presign_backup SELECT v.* FROM votes v WHERE v.zid = (SELECT zid FROM zinvites WHERE zinvite='<PHASE6_ZINVITE>') AND NOT EXISTS (SELECT 1 FROM votes_phase6_presign_backup b WHERE b.zid = v.zid);
INSERT INTO vlu_phase6_presign_backup SELECT u.* FROM votes_latest_unique u WHERE u.zid = (SELECT zid FROM zinvites WHERE zinvite='<PHASE6_ZINVITE>') AND NOT EXISTS (SELECT 1 FROM vlu_phase6_presign_backup b WHERE b.zid = u.zid);
```

Confirm both copies — **scoped to this conversation on both sides.** The backup tables accumulate
across conversations by design, so an unscoped count compares A+B against B and fails falsely on
the second conversation:

```sql
SELECT (SELECT count(*) FROM votes_phase6_presign_backup WHERE zid=(SELECT zid FROM zinvites WHERE zinvite='<PHASE6_ZINVITE>')) AS votes_backed_up, (SELECT count(*) FROM votes WHERE zid=(SELECT zid FROM zinvites WHERE zinvite='<PHASE6_ZINVITE>')) AS votes_live, (SELECT count(*) FROM vlu_phase6_presign_backup WHERE zid=(SELECT zid FROM zinvites WHERE zinvite='<PHASE6_ZINVITE>')) AS vlu_backed_up, (SELECT count(*) FROM votes_latest_unique WHERE zid=(SELECT zid FROM zinvites WHERE zinvite='<PHASE6_ZINVITE>')) AS vlu_live;
```

Each pair must match. This is also your real rollback: the pre-repair state survives even after
`COMMIT`, which the transaction alone does not give you.

---

## 5. Repair — both tables, one transaction, counted

> **Production was repaired on 2026-09-02.** Running this again on the same conversation
> re-inverts it. The negation is an involution over this predicate — odd runs leave the
> data repaired, even runs leave it broken — so if you are unsure whether it has already
> run, do **not** re-run "to be safe". Check first with the known-intent vote from step 2.

⚠️ **Not idempotent.** Running it twice returns the data to broken. Run once, verify, do not
re-run. The `NOT EXISTS` guard protects the *backup*, not this.

Because the frontend is down, every stored phase-6 vote is uniformly inverted — no time bound is
needed, and none should be added. Count what you expect to touch first; the two numbers will
normally **differ**, since `votes` keeps every re-vote while `votes_latest_unique` holds one row
per (pid, tid):

```sql
SELECT (SELECT count(*) FROM votes v WHERE v.zid=(SELECT zid FROM zinvites WHERE zinvite='<PHASE6_ZINVITE>') AND v.vote <> 0 AND NOT EXISTS (SELECT 1 FROM comments c WHERE c.zid = v.zid AND c.tid = v.tid AND c.pid = v.pid)) AS votes_expected, (SELECT count(*) FROM votes_latest_unique v WHERE v.zid=(SELECT zid FROM zinvites WHERE zinvite='<PHASE6_ZINVITE>') AND v.vote <> 0 AND NOT EXISTS (SELECT 1 FROM comments c WHERE c.zid = v.zid AND c.tid = v.tid AND c.pid = v.pid)) AS vlu_expected;
```

```sql
BEGIN;
```

```sql
UPDATE votes v SET vote = -v.vote WHERE v.zid = (SELECT zid FROM zinvites WHERE zinvite='<PHASE6_ZINVITE>') AND v.vote <> 0 AND NOT EXISTS (SELECT 1 FROM comments c WHERE c.zid = v.zid AND c.tid = v.tid AND c.pid = v.pid);
UPDATE votes_latest_unique v SET vote = -v.vote WHERE v.zid = (SELECT zid FROM zinvites WHERE zinvite='<PHASE6_ZINVITE>') AND v.vote <> 0 AND NOT EXISTS (SELECT 1 FROM comments c WHERE c.zid = v.zid AND c.tid = v.tid AND c.pid = v.pid);
```

Each must report exactly its own expected number. Passes (`vote = 0`) are excluded deliberately —
negating zero is a no-op that would pad the counts and mask a mistake.

**Author rows are excluded by identity, not by value.** Polis writes one vote from the
statement's own author, and *that* row was never inverted — the app never sent it. On
production it happens to be a `0` (the moderator seed path sends an explicit zero), so
`vote <> 0` would exclude it by luck. It is `-1` when a round was seeded through the
participant endpoint — which is what the local simulator does, i.e. exactly the stack this
runbook tells you to rehearse on. The `NOT EXISTS` join against `comments` is what actually
excludes them; keep `vote <> 0` only as the pass optimisation it claims to be.

Verify before committing. Both distributions should mirror (`-1` and `+1` swapped, `0`
unchanged), and this reads **both** tables so a divergence is visible *before* you commit:

```sql
SELECT 'votes' AS t, vote, count(*) FROM votes WHERE zid=(SELECT zid FROM zinvites WHERE zinvite='<PHASE6_ZINVITE>') GROUP BY vote UNION ALL SELECT 'votes_latest_unique', vote, count(*) FROM votes_latest_unique WHERE zid=(SELECT zid FROM zinvites WHERE zinvite='<PHASE6_ZINVITE>') GROUP BY vote ORDER BY t, vote;
```

⚠️ Verifying against `votes` alone is the trap this runbook previously walked into: it shows a
perfectly mirrored distribution while every participant-facing number stays inverted.

Then `COMMIT;` — or `ROLLBACK;` if anything is off.

### 5b. Recompute the clusters — the repair is not finished without this

The vote tables are now right and **every rendered opinion group is still wrong.** Polis
serves clustering from `math_main`, computed from the old signs. A plain row rewrite adds
no row, fires no rule and moves no timestamp, so nothing tells the math worker that
anything changed. Step 7's tallies come straight from Postgres and will look correct while
the groups beside them stay backwards — the one silent mis-display this repair does not fix
by itself.

⚠️ **Queueing a task does not work on our deployment, and this is not a transient
fault.** `queue_math_recompute` writes a `worker_tasks` row, but only polismath's `tasks`
run mode consumes that table, and our container runs `full`. In `system.clj`,
`full-system` merges `poller-system` alone — the vote and moderation pollers — while the
`TaskPoller` lives in `task-system`; upstream carries the merge of the two as
commented-out code. Verified 2026-09-02 by reading `system.clj` inside the running image.
Two orphaned rows sit on production as evidence, the older from 2026-08-05.

So use one of these instead:

1. **Give the vote poller something to see.** It polls votes by `:created`, so a real vote
   in the conversation triggers a recompute of that conversation. Least invasive if a
   throwaway vote is acceptable; note it becomes a real row you may then want to remove.
2. **Run the task poller.** Start a math process in `tasks` mode alongside the existing
   one (`clojure -M:run tasks` in the math container), which instantiates the `TaskPoller`
   and drains `worker_tasks`. This is the only route that makes `queue_math_recompute`
   behave as its name implies.
3. **Accept stale clustering and say so.** Report the repair as vote-data-only, and record
   that the groups still derive from pre-repair signs.

**Whichever you choose, verify — do not assume.** Record `math_tick` before, and read it
back after:

```sql
SELECT zid, math_tick, to_timestamp(last_vote_timestamp/1000) AS last_vote FROM math_main WHERE zid = (SELECT zid FROM zinvites WHERE zinvite='<PHASE6_ZINVITE>');
```

`math_tick` must advance. **No movement is a failure, not a pass.** Note that `math_tick`
is a counter, not a timestamp — do not wrap it in `to_timestamp()`, which yields a
meaningless 1970 date. `last_vote_timestamp` is the newest vote math has incorporated;
if it already matches the conversation's newest vote, math is current with respect to
vote *arrivals* and simply cannot see an in-place repair.

Repeat **one conversation at a time** through steps 4 and 5, verifying each. A wrong row count is
recoverable when it is the only conversation in the transaction.

---

## 6. Deploy the fix, which brings the tool back up

Only now, with every conversation repaired:

```bash
bash ~/wiki-polis/deploy.sh main --expect <sha of the merge commit that carries the fix>
```

`--expect` fails closed before installing or restarting. Without it a moved ref puts
unfixed code in front of freshly repaired data, and the commit-stamp check below catches
it only once the tool is already serving.

`deploy.sh` ends with `toolforge webservice restart`, so this returns the tool to service. It is
`set -euo pipefail`, so a failed frontend build exits **before** the restart and leaves the tool
down — which is the safe outcome. Do not start the webservice by hand to "fix" that: repaired
data plus unfixed code means new votes arrive inverted into corrected rows, and you are back to a
blend nobody can untangle.

If the deploy fails, leave it down, fix the deploy, and try again.

---

## 7. Confirm end to end

```bash
curl -s https://wiki-polis.toolforge.org/ | grep -oE '<code>[0-9a-f]{7,40}</code>'
```

The stamp must be the commit carrying the fix. Then cast one deliberate **Agree** in a phase 6
round and read it back:

```sql
SELECT pid, tid, vote, to_timestamp(created/1000) AS at FROM votes WHERE zid = (SELECT zid FROM zinvites WHERE zinvite='<PHASE6_ZINVITE>') ORDER BY created DESC LIMIT 3;
```

`vote = -1` means new votes are correct. Spot-check one participant whose intent you know against
the phase 6 results view to confirm the repaired rows read the right way round.

Keep `votes_phase6_presign_backup` and `vlu_phase6_presign_backup`. They are small, and they are
the only copy of what the bug wrote.

---

## Why not #285's script

#285's migration script (`migrate_phase6_vote_signs.py`, on that PR's branch — it is not in this tree) does this with discovery, dry-run and a
run-log. Good work, but its idempotency guard is a **local JSON file** — its own docstring says
*"Keep that log; do not run on a second machine."* It also only ever touched `votes`, so it would
have hit the same silent-no-op described in step 4. With a handful of phase-6 rows and the tool
offline, a counted statement pair in a transaction is smaller, holds no hidden state, and is
verified by numbers in front of you.

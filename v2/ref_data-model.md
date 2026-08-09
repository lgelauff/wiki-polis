# Data model reference

> **Tracks-code reference — derived from `v2/db.py` @ `883b707` (2026-06-23);
> reconciled against `db.py` again on 2026-07-09.**
> Regenerate whenever the schema changes (a new migration or model edit). This is the
> app's own database — the **identity + argument-mapping layer**. Votes, statements, and
> clusters live in Polis/Postgres, *not* here; see
> [`spec_architecture.md`](spec_architecture.md) for the full data-ownership split.

## Conventions

- **Datetimes are naive UTC.** Every `DateTime` stores UTC with no tzinfo
  (`datetime.now(timezone.utc)` on write); SQLite and MySQL both ignore
  `DateTime(timezone=True)`.
- **Enumerations:** `ACCESS_POLICIES = ('public', 'invite_only', 'demo')`;
  `ADMIN_ROLES = ('moderator', 'organizer')` — conversation-scoped only, site-wide admin is
  `Participant.is_global_admin`; `ARGUMENT_SIDES = ('pro', 'con')`.
- **Store:** MariaDB (ToolsDB) in production, SQLite in dev.

## Tables

### `participants` — one row per Wikimedia account
`id` PK · `mw_user_id` int not-null unique · `mw_username` str(255) · `xid` str(64)
not-null unique · `xid_key_version` int=2 · `is_demo` bool=F · `is_global_admin` bool=F ·
`created_at`.
- **`xid` = `HMAC(secret, subject)`, versioned by `xid_key_version`** — the opaque token
  passed to Particiapi. Version 1 was `sha256(mw_user_id)` (legacy, plain and
  enumerable — MW user IDs are sequential); version 2 (current default) is a keyed HMAC
  and is not recomputable without the deployment secret. *(pending — v1 rows predating
  the HMAC scheme still carry the reversible hash; rotating them is tracked at
  [#96](https://github.com/lgelauff/wiki-polis/issues/96).)*
- `is_demo` marks synthetic, session-scoped participants auto-created for `demo`
  access-policy conversations (see `ACCESS_POLICIES`) — no real Wikimedia account behind them.

### `conversations`
`id` PK · `slug` unique · `polis_id` unique (Polis zinvite) · `title` · `language`
str(10)='en' (BCP-47) · `intro_text` / `outro_text` (sanitised HTML, nullable) ·
`active` bool=T · `paused` bool=F · `access_policy` str(20)='public' · `created_at` ·
`closed_at` (nullable).
- Phase toggles, all bool=F: `phase_submission`, `phase_personal_results`,
  `phase_argument_mapping`, `phase_cleanup`, `phase_public_results`, `phase_informed_voting`.
  - `phase_cleanup`: a passive phase between argument mapping and informed voting
    (#163) — participants do nothing; the organizer moderates arguments before the
    second voting round.
  - `phase_informed_voting`: Phase 6, a second independent voting round on featured
    statements only, with arguments shown inline. Enabling this triggers creation of a
    dedicated Polis conversation (see `phase6_polis_conversation_id`).
- `phase_route` str(32)='default_7' · `recommended_quantities` JSON nullable, default `{}`.
- `scheduled_transition_at` (nullable) · `scheduled_transition_target` str(32) nullable ·
  `scheduled_transition_frozen` bool=F.
- `report_filter_snapshot` JSON nullable.
- **Join-time eligibility gate (#146):** `eligibility_event_id` str(80) nullable ·
  `eligibility_label` str(255) nullable. Empty event id = open to any logged-in user
  allowed by `access_policy`.
- **Phase 6 Polis mapping:** `phase6_polis_conversation_id` str(50) nullable — the
  dedicated Phase 6 Polis conversation id, set once Phase 6 is initialised by the admin.
  Unique (`uq_conversations_phase6_polis_conversation_id`) — enforces one Phase 6 Polis
  conversation per wiki-polis conversation (a double-init race raises `IntegrityError`
  instead of silently overwriting).
- `argument_vote_method` str='kApproval' · `argument_vote_data` JSON, default `{'K': 2}`.
- **Constraint:** `closed_at IS NULL OR (active=0 AND paused=0)` — a permanently closed
  conversation can't be active or paused.
- `paused` is reversible and does **not** start the reveal clock; `closed_at` is set on
  permanent close (irreversible) and drives the reveal timeline.

### `participations` — one row per (participant, conversation)
`id` PK · `participant_id` FK→participants (**RESTRICT**) · `conversation_id`
FK→conversations (CASCADE) · `pseudonym` str(80) · `accepted_at` · `notify_email`
bool=F · `notify_talk_page` bool=F · `public_username` (nullable) · `revealed_at`
(nullable) · `new_stmt_ids` JSON=[] · `last_engagement` nullable · `phase6_card_order`
JSON nullable · `eligibility_status` str(16) nullable · `eligibility_checked_at`
nullable · `eligibility_detail` JSON nullable.
- **Constraints:** unique `(participant_id, conversation_id)`; unique `pseudonym`
  (platform-wide, never reused/deleted); check `pseudonym = LOWER(pseudonym)`.
- `public_username` / `revealed_at` record the opt-in reveal. Per D-PRIV, a reveal is
  **permanent** and is not nullified by the app.
- `new_stmt_ids` = Polis statement IDs of new statements this participant submitted;
  quota used = `len(new_stmt_ids)`, slots consumed at submit time and never returned.
- `last_engagement` records recent meaningful actions only; passive page views are not tracked.
- `phase6_card_order` = list of `FeaturedStatement` IDs in the order shown to this
  participant in the informed-voting tab; set once on first visit and stable across
  reloads (same pattern as `ArgumentSideState.argument_order`).
- `eligibility_status` (`eligible`|`not_required`), `eligibility_checked_at`,
  `eligibility_detail` cache the join-time eligibility verdict (#146); only set when the
  conversation has an `eligibility_event_id` — actions do not re-check after joining.

### `conversation_bans`
`id` PK · `conversation_id` FK (CASCADE) · `participant_id` FK (CASCADE) ·
`banned_by_id` FK→participants (**SET NULL**) · `summary` · `created_at` ·
`lifted_at` nullable · `lifted_by_id` FK→participants (**SET NULL**) ·
`lift_summary`.
- Active ban = `lifted_at IS NULL`. Bans are conversation-scoped; existing content
  remains and is handled separately by moderation.

### `content_flags`
`id` PK · `conversation_id` FK (CASCADE) · `participant_id` FK→participants
(**SET NULL**) · `content_type` enum(`statement`, `argument`) · `statement_tid`
nullable · `argument_id` FK→arguments (CASCADE) nullable · `category`
enum(`personal_attack`, `privacy`, `off_topic`, `other`) · `detail` nullable ·
`status` enum(`open`, `resolved`) · `created_at` · `resolved_at` nullable ·
`resolved_by_id` FK→participants (**SET NULL**) · `resolution_note` nullable.
- Target invariant: statement flags store `statement_tid` and no `argument_id`;
  argument flags store `argument_id` and no `statement_tid`.
- The admin queue does not display flagger identity; moderators review the target,
  reason, optional note, and timestamp.

### `conversation_invites`
`id` PK · `conversation_id` FK (CASCADE) · `mw_username` · `created_at`. Unique
`(conversation_id, mw_username)`.

### `admin_roles`
`id` PK · `participant_id` FK (CASCADE) · `conversation_id` FK (CASCADE) · `role`
enum(`moderator`, `organizer`) · `granted_at` · `granted_by` FK→participants (**SET NULL**). Unique
`(participant_id, conversation_id, role)`.

### `featured_statements`
`id` PK · `conversation_id` FK (CASCADE) · `polis_statement_id` int (Phase 2 tid in the
main Polis conversation) · `phase6_polis_statement_id` int nullable (Phase 6 tid in the
dedicated informed-voting Polis conversation; set by `admin_phase6_init`/`_sync_phase6_featured`
and cleared to NULL when the statement is hidden in Phase 6) · `statement_text`
(nullable; cached from Particiapi) · `suggested_by_system` bool=F · `confirmed_by_admin`
bool=F · `created_at`. Unique `(conversation_id, polis_statement_id)`.

**Phase 6 two-conversation architecture.** Each `Conversation` holds two separate Polis
conversation IDs: `polis_id` (Phase 2, all statements) and `phase6_polis_conversation_id`
(Phase 6, only confirmed featured statements as seeds). These are independent Polis
conversations with distinct zinvites and vote sets. Joining them for comparison uses the
`FeaturedStatement` as the bridge: `polis_statement_id` is the Phase 2 tid,
`phase6_polis_statement_id` is the Phase 6 tid for the same logical statement.

**Vote-sign convention (both conversations).** Raw Polis DB: `-1 = Agree, 1 = Disagree,
0 = Pass`. The participant-facing CSV export negates this (agree = +1). wiki-polis always
reads from `votes_latest_unique` using the raw sign. See `ref_polis-data-model.md`.

### `arguments`
`id` PK · `featured_statement_id` FK (CASCADE) · `proposer_pseudonym` str(80) nullable
(no FK) · `body` str(280) · `side` enum(`pro`/`con`) · `hidden` bool=F · `created_at`.
Unique `(featured_statement_id, proposer_pseudonym, side)` — one argument per side per
pseudonym; a **NULL `proposer_pseudonym` (seeded argument) is exempt** (SQL
`NULL != NULL`), so multiple seeds per side are allowed.
- `proposer_pseudonym` stores the proposing participant's pseudonym directly (no
  `participant_id` FK). It replaced a former `proposer_id` FK→`participants` (#113,
  migration `5c7d8e9f0123`), which is why the foreign-key delete-behaviour table below
  no longer lists a `SET NULL` rule for this column.

### `argument_votes`
`id` PK · `argument_id` FK (CASCADE) · `participant_id` FK (CASCADE) · `value` int
(nullable) · `created_at`. Unique `(argument_id, participant_id)`.
- `value` interpretation depends on `conversation.argument_vote_method`: **kApproval →
  `value` is null** (row presence = approval); ranking → rank position. **⚠ `(pending)`:**
  the ranking path is unimplemented — only kApproval is live, so `value` is currently a
  dead column.

### `argument_side_states` — per (participant, featured_statement, side)
`id` PK · `participant_id` FK (CASCADE) · `featured_statement_id` FK (CASCADE) · `side`
enum · `argument_order` JSON=[] · `skipped` bool=F · `created_at`. Unique
`(participant_id, featured_statement_id, side)`.
- `argument_order` is the participant's stable randomised display order (new arguments
  inserted at a random position on first encounter); `skipped` records the
  "nothing to add" contribute-gate choice.

### `audit_events` — append-only accountability log (#135)
`id` PK · `ts` · `actor_participant_id` FK→participants (**SET NULL**, nullable) ·
`conversation_id` FK→conversations (**SET NULL**, nullable) · `operation` str(64) ·
`target_type` str(32) nullable · `target_id` str(64) nullable · `outcome` str(16)='ok' ·
`detail` JSON=`{}`. Indexed on `(conversation_id, ts)` and `(actor_participant_id, ts)`.
- Records who did what when, for admin/moderation write actions. **Never updated.**
- Holds only ids, enums, and counts — **never** statement text, vote content, usernames,
  xid, or any other PII (the writer's contract; see `record_audit` in `app.py`).
- FKs use **SET NULL**, not CASCADE: the trail must outlive a deleted participant or
  conversation (governance durability).

### `statement_provenance` — derivative-statement lineage (#143)
`id` PK · `conversation_id` FK→conversations (CASCADE) · `polis_statement_id` int (the
new/derivative tid) · `derived_from_tid` int (the parent tid it improves on) ·
`provenance_type` str(16)='derivative' (`new`|`derivative`) · `link_method`
str(16)='declared' (`declared`|`detected`) · `created_at`. Unique
`(conversation_id, polis_statement_id)`.
- wiki-polis has no general statement table — statements live in Polis (`comments`),
  keyed by a Polis statement id (`tid`). Provenance is therefore keyed by
  `(conversation_id, polis_statement_id)` of the **new** statement; absence of a row
  means `new` (the default) — a row exists only for derivatives.
- `derived_from_tid` is a parent pointer, so derivatives form a chain/tree that the
  clustering/weighting consumers resolve into lineage groups (see `_lineage_group`).
- The composite unique constraint also serves `conversation_id`-only lookups (leading
  column), so no standalone `conversation_id` index is needed.

### `statement_similarity_scores` — similarity-at-creation scores (#143/#207)
`id` PK · `provenance_id` FK→statement_provenance (CASCADE) · `model` str(64) (scorer
name/version, e.g. `char`, `semantic-v1`) · `value` float (similarity in `[0, 1]`, higher
= more similar) · `scored_at`. Unique `(provenance_id, model)`.
- One row per (provenance link, scoring model), so a link can carry several kinds of
  score without a schema change — e.g. a cheap always-available `char` fallback and a
  `semantic` model score (#207). Re-scoring a metric replaces rather than duplicates the
  row (unique on `(provenance_id, model)`).
- Consumers prefer `semantic` when present and fall back to `char`.

## Foreign-key delete behaviour

- `participations.participant_id` → **RESTRICT** (can't delete a participant who has participations).
- `admin_roles.granted_by`, `audit_events.actor_participant_id`,
  `audit_events.conversation_id` → **SET NULL** (the audit trail must outlive a deleted
  participant or conversation).
- `arguments.proposer_pseudonym` has **no FK** (see `arguments` above).
- Everything else → **CASCADE**.

## Indexes

FK columns are explicitly indexed (MySQL/MariaDB doesn't auto-index FKs): on
`participations(participant_id, conversation_id)`, `arguments(featured_statement_id,
proposer_pseudonym)`, `argument_votes(argument_id, participant_id)`,
`argument_side_states(participant_id, featured_statement_id)`, and
`featured_statements(conversation_id)`. (See also the `audit_events` indexes noted in
its own section above.)

## Known discrepancies

- **`argument_vote_data` comment vs default.** The `db.py` comment shows `{'k': 2}`
  (lowercase) but the column default and all readers use `{'K': 2}`. *(pending — fix the comment.)*
- **`ArgumentVote.value` / ranking.** Documented for a ranking method that isn't built;
  only kApproval (row-presence) is implemented. *(pending — implement or remove.)*
- **Internal-link removal after retention.** Voluntary reveals are permanent; a separate
  workflow is still needed to remove internal account↔pseudonym links for non-revealed
  participations by the retention commitment.

**Phase 6 results moderation.** `Phase6ResultsFilter` (defined in `app.py`) carries two
exclusion sets applied uniformly across all result surfaces:
- `excluded_tids` — Phase 6 Polis tids suppressed post-init (de-featured statements whose
  `phase6_polis_statement_id` was moderated to `mod = -1`).
- `excluded_pids` — Polis participant pids suppressed (banned participants; empty until
  issue #60 ships the admin ban UI). The field exists so results can be recomputed with
  exclusions without a schema change.

**Result surfaces.** Three surfaces are built from the same `_build_phase6_results` helper:
1. **Surface A — preliminary** (results tab in `conversation.html` while round is live).
2. **Surface B — final report** (`/c/<slug>/report`, public after close).
3. **Surface C — self-comparison** (placeholder in the final report; full implementation deferred).

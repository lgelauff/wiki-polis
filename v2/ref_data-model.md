# Data model reference

> **Tracks-code reference — derived from `v2/db.py` @ `f017e5b` (2026-06-01).**
> Regenerate whenever the schema changes (a new migration or model edit). This is the
> app's own database — the **identity + argument-mapping layer**. Votes, statements, and
> clusters live in Polis/Postgres, *not* here; see
> [`spec_architecture.md`](spec_architecture.md) for the full data-ownership split.

## Conventions

- **Datetimes are naive UTC.** Every `DateTime` stores UTC with no tzinfo
  (`datetime.now(timezone.utc)` on write); SQLite and MySQL both ignore
  `DateTime(timezone=True)`.
- **Enumerations:** `ACCESS_POLICIES = ('public', 'invite_only')`;
  `ADMIN_ROLES = ('moderator',)` — conversation-scoped only, site-wide admin is
  `Participant.is_global_admin`; `ARGUMENT_SIDES = ('pro', 'con')`.
- **Store:** MariaDB (ToolsDB) in production, SQLite in dev.

## Tables

### `participants` — one row per Wikimedia account
`id` PK · `mw_user_id` int not-null unique · `mw_username` str(255) · `xid` str(64)
not-null unique · `is_global_admin` bool=F · `created_at`.
- **`xid` = `sha256(mw_user_id)`**, the opaque token passed to Particiapi. **Not a
  privacy guarantee** — MW user IDs are sequential and the hash is brute-forceable; don't
  publish it; salt before any public exposure. *(pending — this reversibility undermines
  anonymisation: removing the internal link at the retention window doesn't help while
  the xid is recomputable. Salt or delete/rotate the xid at anonymisation —
  [#96](https://github.com/lgelauff/wiki-polis/issues/96).)*

### `conversations`
`id` PK · `slug` unique · `polis_id` unique (Polis zinvite) · `title` · `language`
str(10)='en' (BCP-47) · `intro_text` / `outro_text` (sanitised HTML, nullable) ·
`active` bool=T · `paused` bool=F · `access_policy` str(20)='public' · `created_at` ·
`closed_at` (nullable).
- Phase toggles, all bool=F: `phase_submission`, `phase_personal_results`,
  `phase_argument_mapping`, `phase_public_results`.
- `argument_vote_method` str='kApproval' · `argument_vote_data` JSON, default `{'K': 2}`.
- **Constraint:** `closed_at IS NULL OR (active=0 AND paused=0)` — a permanently closed
  conversation can't be active or paused.
- `paused` is reversible and does **not** start the reveal clock; `closed_at` is set on
  permanent close (irreversible) and drives the reveal timeline.

### `participations` — one row per (participant, conversation)
`id` PK · `participant_id` FK→participants (**RESTRICT**) · `conversation_id`
FK→conversations (CASCADE) · `pseudonym` str(80) · `accepted_at` · `notify_email`
bool=F · `notify_talk_page` bool=F · `public_username` (nullable) · `revealed_at`
(nullable) · `new_stmt_ids` JSON=[].
- **Constraints:** unique `(participant_id, conversation_id)`; unique `pseudonym`
  (platform-wide, never reused/deleted); check `pseudonym = LOWER(pseudonym)`.
- `public_username` / `revealed_at` record the opt-in reveal. Per D-PRIV, a reveal is
  **permanent** and is not nullified by the app.
- `new_stmt_ids` = Polis statement IDs of new statements this participant submitted;
  quota used = `len(new_stmt_ids)`, slots consumed at submit time and never returned.

### `conversation_invites`
`id` PK · `conversation_id` FK (CASCADE) · `mw_username` · `created_at`. Unique
`(conversation_id, mw_username)`.

### `admin_roles`
`id` PK · `participant_id` FK (CASCADE) · `conversation_id` FK (CASCADE) · `role`
enum(`moderator`) · `granted_at` · `granted_by` FK→participants (**SET NULL**). Unique
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
`id` PK · `featured_statement_id` FK (CASCADE) · `proposer_id` FK→participants
(**SET NULL**, nullable) · `body` str(280) · `side` enum(`pro`/`con`) · `hidden` bool=F
· `created_at`. Unique `(featured_statement_id, proposer_id, side)` — one argument per
side per participant; a **NULL `proposer_id` (seeded argument) is exempt** (SQL
`NULL != NULL`), so multiple seeds per side are allowed.

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

## Foreign-key delete behaviour

- `participations.participant_id` → **RESTRICT** (can't delete a participant who has participations).
- `admin_roles.granted_by`, `arguments.proposer_id` → **SET NULL**.
- Everything else → **CASCADE**.

## Indexes

FK columns are explicitly indexed (MySQL/MariaDB doesn't auto-index FKs): on
`participations(participant_id, conversation_id)`, `arguments(featured_statement_id,
proposer_id)`, `argument_votes(argument_id, participant_id)`,
`argument_side_states(participant_id, featured_statement_id)`, and
`featured_statements(conversation_id)`.

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

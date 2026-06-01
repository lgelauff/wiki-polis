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
- `public_username` / `revealed_at` record the opt-in reveal. **⚠ `(pending — D-PRIV)`:**
  the code currently nullifies them ~60 days after close; per the clarified D-PRIV
  decision a reveal is **permanent** — this nullification must change.
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
`id` PK · `conversation_id` FK (CASCADE) · `polis_statement_id` int · `statement_text`
(nullable; cached from Particiapi for when the API is down) · `suggested_by_system`
bool=F · `confirmed_by_admin` bool=F · `created_at`. Unique
`(conversation_id, polis_statement_id)`.

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
- **Reveal nullification vs D-PRIV.** See `participations` above. *(pending — D-PRIV.)*

> The proposal's `phase6_*` fields (from [`prop_phase-model.md`](prop_phase-model.md)) are
> **not** in `db.py` — they exist only in the proposal.

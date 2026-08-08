# Wiki-Polis Functional Design

> **Status — current spec.** This specifies how wiki-polis is *meant to work* — the
> agreed design for the current version. Where the implementation diverges, that's a
> tracked bug/gap (flagged inline with a `pending` marker), not a change to this spec.
> Phase 6 (informed voting) was adopted and implemented (PR #115, 2026-06-04) and is
> described in the Results section below. [`prop_phase-model.md`](prop_phase-model.md)
> contains the full six-phase narrative and is now partially current.

A deliberation tool for the Wikimedia community. Participants vote on atomic statements, clusters of opinion emerge, and curated debate layers can be added on top.

---

## User roles

**Visitor** — not logged in. Can view public conversation landing pages. Cannot vote or submit.

**Participant** — logged in via Wikimedia account. Can join conversations, vote, submit statements, and read and vote on arguments.

**Moderator** — a participant with elevated trust for a specific conversation. Can hide statements and arguments.

**Admin** — full control. Can create and manage conversations, assign roles, curate featured statements, and control phase toggles.

---

## Conversations

A conversation is a deliberation space on a specific topic. It has a title, an introductory text explaining the topic and purpose, and an optional closing text shown after a participant has voted on all available statements.

Conversations have three status states:
- **Active** — open for participation
- **Paused** — temporarily suspended; voting is disabled and the conversation is hidden from public listings, but the admin can resume it at any time. The identity reveal clock does not start.
- **Closed** — permanently ended; the conversation is hidden from available listings, voting is disabled, and the identity reveal timeline begins. Closing is irreversible. *(pending — closed conversations should surface the reveal-window end date and what happens next, [#70](https://github.com/lgelauff/wiki-polis/issues/70))*

Each conversation has an access policy:
- **Public** — anyone with a Wikimedia account can join
- **Invite-only** — only explicitly invited Wikimedia usernames can join

Participants must explicitly accept a conversation before entering it. The acceptance screen shows the intro text and asks for confirmation. This is a deliberate friction point — participants should understand what they are joining.

---

## Statements

A statement is an atomic claim: one idea, one sentence. Examples: *"Wikipedia's sourcing policy is too restrictive for recent events"* or *"Administrators should be subject to community re-confirmation every three years."*

Anyone who has joined a conversation can submit a statement. Statements go into a moderation queue before appearing to other participants. Moderators (scoped to their conversation) and admins approve or hide them.

Statement moderation maps to three Polis `mod` values:

| `mod` | State | Visible to participants |
|---|---|---|
| `1` | Approved | Yes — appears in the vote queue |
| `0` | Pending | No — back in the moderation queue (default for new statements) |
| `-1` | Hidden | No — removed from view; effectively rejected |

Moving an approved statement to **pending** (`mod=0`) or **hidden** (`mod=-1`) removes it from participants' vote queues. Both actions are equivalent from the argument mapping perspective — if the statement is the last featured statement and argument mapping is active, both are blocked.

Statements are presented to participants one at a time, in an order chosen to maximise the information gained from each vote and reduce order effects. *(pending — routing not yet implemented)*

---

## Voting

The core loop:

1. A statement appears.
2. The participant selects **Agree**, **Disagree**, or **Pass** — the vote is submitted immediately.
3. A three-option triad appears below: **Suggest different wording**, **Move on**, **Propose a new statement**.
4. The participant picks one, or does nothing (Move on is the default path).
5. The UI resets for the next statement.

There is no discussion on the voting screen. No visible vote counts. No indication of how others voted. The experience is fast and private.

After voting on all available statements, the participant is shown a brief completion screen. The "Propose a new statement" option remains available there if quota permits. If new statements are added by others after the participant finishes, those appear on the next session.

Statements submitted by a participant never appear in their own voting queue. Polis rejects self-votes (403); the app pre-emptively marks submitted statement IDs as voted in the web component so they are silently skipped.

### State machine

The voting interaction is a small state machine: see a statement, vote, then optionally act on it via a post-vote triad before moving to the next.

#### Post-vote triad

After every vote, a three-card triad appears below the statement. The three options are:

1. **Suggest different wording** — open a composer pre-filled with the statement text; submit a rephrased version into the same statement pool. No quota; available after every vote.
2. **Move on** — proceed immediately to the next statement.
3. **Propose a new statement** — open a blank composer to submit an entirely new statement. Subject to unlock condition and per-participant quota (see below). May move to a different location in a future iteration.

#### Propose new statement — unlock and quota rules

"Propose a new statement" is locked until the participant has seen enough of the existing statement pool. The unlock threshold is:

> **min(10, total statements currently available)**

So if there are 6 statements, unlock requires 6 votes (100%). If there are 20, unlock requires 10 votes. The threshold can be configured per conversation (`new_stmt_unlock_at`, default 10).

Once unlocked, each participant may submit at most **3 new statements** per conversation (default; configurable per conversation as `new_stmt_max`). The remaining count is shown on the card (e.g. "2 of 3 remaining"). Once the quota is exhausted, the card is permanently disabled for that participant in that conversation.

Wording suggestions ("Suggest different wording") do not count against this quota.

Quota slots are consumed at submission time and are never returned. If a moderator hides, rejects, or removes a proposed statement, the participant does not get that slot back. Once used, it is used.

#### States

- **Idle** — statement visible, Agree/Pass/Disagree buttons shown, triad dimmed below with label "After you vote, you can…"
- **Voted: below threshold** — vote submitted, statement frozen with badge, vote buttons hidden, triad active with two live cards: "Suggest different wording" and "Move on". "Propose new statement" card is present but locked, showing the unlock condition.
- **Voted: above threshold** — same as above but "Propose new statement" card is also live (if quota > 0) or permanently disabled (if quota = 0). Quota remaining shown on the card.
- **Composing: suggest** — triad hidden, suggest-wording textarea open, pre-filled with the statement text
- **Composing: new** — triad hidden, blank new-statement textarea open
- **Submitted** — confirmation shown ("Proposed — heading to moderation"); **auto-advances to the next statement after a brief pause long enough to read the confirmation**; a Next button is also available to advance immediately
- **All done** — no more statements to vote on; completion message shown. "Propose new statement" becomes available (threshold is met by definition — you've voted on everything). Quota rules still apply.

The threshold for moving from "below" to "above" is `min(new_stmt_unlock_at, total_statements_currently_available)`, where `new_stmt_unlock_at` defaults to 10.

#### Transitions

| From | Trigger | To | Side effect |
|---|---|---|---|
| Idle | Click Agree / Pass / Disagree (threshold not yet met) | Voted: below threshold | Vote → API; vote counter +1; voted badge shown |
| Idle | Click Agree / Pass / Disagree (threshold already met) | Voted: above threshold | Vote → API; vote counter +1; voted badge shown |
| Voted: any | Click "Move on" | Idle | Next statement loads |
| Voted: any | Click "Suggest different wording" | Composing: suggest | — |
| Voted: above threshold | Click "Propose new statement" (quota > 0) | Composing: new | — |
| Voted: any | Click "change" in voted badge | Idle (same statement, re-votable) | Vote buttons re-enabled for this statement; selecting a new option **resubmits the changed vote** to Polis; vote counter unchanged *(pending — [#69](https://github.com/lgelauff/wiki-polis/issues/69))* |
| Composing: suggest | Click Cancel | Voted: (same threshold state) | Returns to triad for the same statement |
| Composing: suggest | Click Submit (success) | Submitted | Statement sent to pool |
| Composing: new | Click Cancel | Voted: above threshold | Returns to triad for the same statement |
| Composing: new | Click Submit (success) | Submitted | Statement sent to pool; participant quota decremented |
| Submitted | Pause elapses, or click "Next statement" | Idle | Next statement loads |
| Any | All statements voted | All done | — |
| Any | Own submitted statement appears in queue | Idle (skipped) | Statement ID added to web component votes Set; no vote submitted |
| All done | Click "Propose new statement" (quota > 0) | Composing: new | — |
| Composing: new (from All done) | Click Cancel | All done | Returns to completion screen |
| Composing: new (from All done) | Click Submit (success) | All done | Statement sent to pool; participant quota decremented |

---

## Results

A conversation has five independent toggles that the admin can switch on or off at any time. They can be active simultaneously or sequenced — the admin decides.

**Toggle 1 — Submission open**
Participants can vote on statements and submit new ones. This is the data collection phase.

**Toggle 2 — Personal results**
Each logged-in participant can see clustering results, but only for statements they have personally voted on. The more a participant votes, the more of the picture they see. This is a deliberate incentive: deeper engagement unlocks a deeper view. Individual vote choices are never shown — results are always aggregate.

**Toggle 3 — Full public results**
Complete clustering results are visible to everyone, including visitors who are not logged in. This is the full transparency view: consensus points, contention points, cluster breakdown across all statements.

When the participant count for a conversation is below a minimum threshold (currently 25), a visible warning is shown above the results: opinion groups detected from small samples can shift substantially as more people participate. Results are still displayed — the warning contextualises them rather than hiding them.

**Toggle 4 — Argument mapping**
The pro/con argument layer becomes visible on featured statements. Participants can read, submit, and vote on short arguments. When this toggle is off, the argument tab is hidden entirely — the voting loop and results are unaffected.

**Toggle 5 — Informed voting**
A second, independent voting round on the featured statements only. Arguments from Toggle 4 are shown inline so participants deliberate before casting a clean Agree / Disagree / Pass vote. The slate is clean — Phase 1 votes have no effect here, and participants who did not take part in Phase 1 can enter. This toggle requires a one-time admin initialisation step (creates a dedicated Polis conversation and seeds the featured statements) before the tab becomes visible to participants. See the organizer guide for the initialisation flow.

The conversation page uses three distinct result surfaces across the deliberation lifecycle:

- **Intermediate results tab** (`phase_personal_results` or `phase_public_results`) — Polis opinion-group results from the initial voting round (Phase 2).
- **Preliminary results tab** (`phase_public_results` + informed-voting initialised + results available) — side-by-side comparison of initial vs. informed vote per statement, with the shift in agree rate. Shown only when public results are enabled; not shown to participants who have not yet cast any informed votes.
- **Final report** (`/c/<slug>/report`, published when `closed_at` is set) — the definitive published findings after the organizer closes the consultation.

All five toggles default to off and are designed to be enabled in order — each phase building on the previous. The default sequence is:

1. Open submission — collect votes and statements
2. Enable personal results — reward participants with a view of how their engagement lands
3. Enable argument mapping — invite deeper engagement on the most significant statements before opening to the public
4. Enable full public results — open the findings to the wider community and visitors
5. Enable informed voting — after argument mapping is substantive, open a second voting round on the featured statements with arguments visible

The admin can deviate from this sequence, but successive activation is the intended default flow.

---

## Featured statements

Featured statements are the statements that appear in the argument mapping tab. They are not surfaced anywhere else in the conversation.

The system suggests which statements to feature based on cluster analysis — for example, statements that most strongly divide clusters, or that are most representative of a specific cluster's position. The admin reviews these suggestions and confirms or dismisses each one. Admins can also manually feature a statement regardless of the system's suggestions.

This keeps curation grounded in the data rather than editorial intuition, while preserving admin control over what enters the argument layer.

---

## Argument layer

The argument layer is a separate tab on the conversation page. It does not appear during the voting loop.

Within the argument mapping tab, participants see the featured statements curated by the admin from system suggestions. For each, they can read short pro and con arguments submitted by other participants, and vote on each argument as **useful** or not.

Participants can submit their own arguments. An argument is:
- Tied to one featured statement
- Either pro or con
- Maximum one or two sentences — short and atomic
- Visible to all participants regardless of which cluster they are in

There are no replies to arguments. No threading. Arguments are sorted by usefulness votes.

Moderators can hide arguments that are off-topic, abusive, or redundant.

### State machine — current implementation

The argument phase has two independent per-side state machines (one for pro, one for con) that gate access to a shared voting layer.

#### Per-side contribute states

Each side (pro, con) tracks the participant's contribution independently.

**States:**

- **idle** — no action taken; contribute affordance visible. No DB record.
- **composing** — textarea open. Client-only; no DB state. Navigating away returns to `idle`.
- **submitted** — participant submitted an argument for this side. `Argument` row exists for this participant + featured statement + side.
- **skipped** — participant declined to contribute. `ArgumentSideState.skipped = True`.

**Transitions:**

| From | Event | To |
|---|---|---|
| `idle` | click affordance | `composing` |
| `composing` | cancel / close | `idle` |
| `composing` | submit (valid body, ≤ 280 chars) | `submitted` |
| `idle` | click "Nothing to add" | `skipped` |
| `composing` | click "Nothing to add" | `skipped` |
| `skipped` | click "change my mind" | `idle` (client-only — see note) |

> **Bug:** "change my mind" resets the UI to `idle` client-side but there is no server route to clear `ArgumentSideState.skipped`. On page reload, the server re-renders the skipped state from the DB, undoing the client reset.

#### Cross-side gate

Voting only opens once the participant has reached a terminal state (`submitted` or `skipped`) on **both** sides.

| Pro state | Con state | Gate |
|---|---|---|
| `idle` or `composing` | any | `one-side-open` — voting locked |
| `submitted` or `skipped` | `idle` or `composing` | `one-side-open` — voting locked |
| `submitted` or `skipped` | `submitted` or `skipped` | `both-gated` — voting unlocks (if enough arguments exist) |

Voting also requires the argument pool on each side to exceed K (the configured importance-vote quota, default 2) before that side's checkboxes activate.

#### Argument voting states

Once `both-gated`, each argument card on each side is in one of three states. The state is driven by the live count of votes the participant has cast on that side relative to K.

**States (per argument card, per side):**

- **vote-eligible** — card can be voted on (not own, not hidden, count < K)
- **vote-picked** — participant has voted for this argument; `ArgumentVote` row exists
- **vote-cap-reached** — participant has cast K votes on this side; card is eligible but blocked

**Transitions:**

| From | Event | To | Side-effect on other cards |
|---|---|---|---|
| `vote-eligible` | vote | `vote-picked` | if this was the K-th vote: all remaining `vote-eligible` → `vote-cap-reached` |
| `vote-picked` | unvote (count was < K) | `vote-eligible` | no change to others |
| `vote-picked` | unvote (count was = K) | `vote-eligible` | all `vote-cap-reached` → `vote-eligible` |
| `vote-cap-reached` | — | — | no direct action; unvoting a `vote-picked` card is required first |

The dial for a given side therefore moves: `vote-eligible ↔ vote-picked ↔ vote-cap-reached`, where the cap boundary shifts every time a vote is cast or retracted.

#### Navigation between featured statements

Participants can move to any featured statement at any time, regardless of their contribute state on the current one. Navigation does not require completing or skipping either side first.

**Intended design:** Each featured statement panel has a **Previous / Next** button pair at the bottom. Previous is disabled on the first statement; Next is disabled on the last. No statement counter is shown between the buttons. The TOC remains available for non-linear jumping but is not the primary navigation affordance.

**Current implementation gap:** The only navigation affordance is the TOC at the top of the panel list. There are no prev/next buttons. Participants have no obvious way to move forward without scrolling back up to the TOC. This needs to be implemented.

**Composing state across navigation:** Navigating away from a panel while in `composing` silently preserves the open composer and its text — the panel is hidden but not reset. On returning, the composer is still open. This behaviour is incidental; no warning or indicator is shown when leaving an unfinished composer.

---

## Admin panel

Admins can:

**Conversations:**
- Create a conversation (title, intro text, outro text, access policy)
- **Pause / Resume** — temporarily suspend a conversation without starting the identity reveal clock; reversible
- **Close permanently** — irreversible; immediately starts the identity reveal timeline. A confirmation dialog and a prominent warning distinguish this from Pause.

**Participants:**
- Assign and revoke moderator or admin roles, either globally or for a specific conversation. Global admin is granted by typing the Wikimedia username — the account must already have logged in at least once.
- Invite specific Wikimedia usernames to an invite-only conversation
- Remove invites

**Statements:**
- Mark statements as featured
- Enable or disable the argument layer on a featured statement

**Statements:**
- Add seed statements individually, or **bulk-import** them from a CSV (a `text` column; max 20 rows / 100 KB; the whole file is rejected if over limit; duplicates are ignored by Polis).

**Phases:** see *Phase control* below.

Admins do not need a separate moderation UI for hiding individual statements or arguments — that is handled in the Polis admin interface directly.

---

## Phase control

A conversation moves through a linear sequence of phases, each backed by a boolean flag on the conversation:

| Order | Phase | Flag | What it enables |
|---|---|---|---|
| 1 | Preparation | *(none)* | setup only; participants can't act yet |
| 2 | Submission | `phase_submission` | participants submit statements and vote |
| 3 | Featured selection | `phase_personal_results` | participants see personal results while the organizer curates featured statements |
| 4 | Argument mapping | `phase_argument_mapping` | pro/con argument layer on featured statements |
| 5 | Informed voting | `phase_informed_voting` (+ `phase6_polis_conversation_id`) | second clean vote round on featured statements; requires a one-time **initialise** |
| — | *Cleanup window* | *(no flag — inferred state)* | organizer reviews results before publishing; participants see preliminary results; see [#163] |
| 6 | Public results | `phase_public_results` | full aggregate map public to everyone |

The **cleanup window** is the period after informed voting ends and before the organizer publishes the final report by closing the conversation (`closed_at` set). No separate flag is needed: the state is inferred from `conv.active AND NOT conv.phase_informed_voting` (or informed voting still on but organizer is reviewing). Participants see a "Preliminary results" banner during this window; the final report at `/c/<slug>/report` is only published once `closed_at` is set. At that moment the `Phase6ResultsFilter` (excluded statements and participants) is snapshotted so the published figures are semi-immutable — see [#163] for implementation.

**Closing is irreversible** and starts the identity-reveal clock. It does not happen automatically — the organizer explicitly publishes the final report as a deliberate action.

Two control surfaces:

- **Simple / guided ("Move on").** Advances one step forward through the sequence. Renders a consequence summary plus a **readiness checklist** (per-phase preconditions); the submit button is gated client-side until every item is confirmed, and the server re-validates on POST. Machine-checked preconditions (currently only "≥1 confirmed featured statement" before argument mapping) show a met / not-met badge.
- **Advanced toggles (global admin only).** Each phase flag as an independent on/off control, including backward moves and non-linear states. Opens automatically when the conversation is already in a non-linear state.

Conversation moderators (non-admins) see phase controls read-only. Pause/Resume and Close are separate conversation-status actions (see above), not phases.

### Phase-control and transition guards

Transitions and phase-critical mutations are protected by **hard guards** (block the action server-side) and **soft guards** (warn but allow). Catalogue as implemented:

**Hard guards** (server-side `flash`-error + redirect, or `abort`):

| Guard | Trigger | Message / effect |
|---|---|---|
| Featured required for argument mapping | Enabling `phase_argument_mapping` with 0 featured statements | "Cannot enable argument mapping — add at least one featured statement first." |
| Readiness checklist | "Move on" POST with any unchecked / unmet precondition | "Confirm every readiness check before moving on." / "A readiness condition is not met yet…" |
| Non-linear state in simple mode | Simple advance while multiple flags are on | "Phases are in a custom state — use Advanced controls to adjust." |
| Already final | Simple advance at public results | "Already at the final phase (public results)." |
| Phase 6 init — status | Initialise on a closed or paused conversation | "Cannot initialise Phase 6 on a closed or paused conversation." |
| Phase 6 init — toggle | Initialise without informed-voting enabled | "Enable the Informed voting toggle first, then initialise." |
| Phase 6 init — once | Re-initialise | "Phase 6 already initialised." |
| Last featured — remove | Remove the last featured statement while argument mapping is active | "Cannot remove the last featured statement while argument mapping is active. Disable the argument mapping phase first." (row-locked) |
| Last featured — hide/pending | Hide or move-to-pending the last featured statement while argument mapping is active | "Cannot hide or move the last featured statement to pending while argument mapping is active. Disable the argument mapping phase first." (not row-locked — best-effort count check) |
| Participant submission | Submit a statement while closed/paused or submission off | HTTP 403 |
| Participant argument | Propose/skip an argument while closed/paused or argument mapping off | HTTP 403 |
| Argument-vote gate | Vote on an argument before contributing-or-skipping both sides | HTTP 403 / `{ok:false, reason:"gate"}` |
| Phase 6 vote | Vote while closed/paused, or informed voting off / not initialised | HTTP 403 / 404 |

**Soft guards** (confirm dialog, disabled control + tooltip, warning banner, inline hint):

- Guided checklist: submit disabled until all boxes ticked and no unmet machine checks.
- Moderators: phase controls disabled — "Only a site admin can change phases."
- Consequence banners in the Move-on box (e.g. public results "permanently closes the consultation and starts the identity-reveal window"; informed voting "you can pause first").
- `confirm()` dialogs on Close permanently and on argument delete.

---

## Home page

The home page (`/`) is an explicit **fork** between two spaces, shown every visit: *Try out the platform* (demo) and *Participate in real consultations* (real). It carries no conversation listing itself — picking a lane routes to it.

The **real lane** (`/consultations`) shows:

- **Your conversations — active** — conversations the participant has joined where there is still something to do: open submission, unread arguments, or results to explore
- **Your conversations — archived** — conversations the participant joined that are now inactive; results remain accessible but no further participation is possible
- **Available conversations** — conversations the participant is eligible to join but has not yet accepted
- **Conversations you moderate** — shown only to participants who are moderator or admin on one or more conversations. Lists those conversations regardless of their active or archived status. Hidden entirely if the participant has no such role.

The real lane never lists demo conversations. Visitors who are not logged in see a brief explanation of the platform and a login prompt.

The **demo lane** (`/demo`) lists only demo conversations and is available logged in or out.

---

## Demo & real spaces (state model)

A **demo** conversation (`access_policy = 'demo'`) is a genuine *demonstration* conversation: it runs the full flow and **records votes as usual**, so a newcomer experiences how the platform actually works. It is not a throwaway sandbox. The point of separating it from real consultations is **safety** — someone who only wants to try things must not accidentally act on a live consultation.

Demo conversations are open to anonymous visitors: a logged-out participant gets a synthetic, per-conversation guest identity so they can try without logging in. Real conversations require Wikimedia login as usual.

### States

`Empty` (no space chosen yet) · `Landing` (the fork at `/`) · `Demo` · `Real` · `Admin`. The chosen space is held in the session; visiting `/demo` sets it to demo, `/consultations` sets it to real.

### Transitions and warnings

- **Expected, silent:** `Empty → Landing ↔ Demo ↔ Landing ↔ Real`. Moving between spaces *through the Landing fork* (or the header switch), and roaming freely **between demo conversations**, never warns.
- **Direct arrival warns once:** landing on a conversation whose space you did **not** explicitly choose — a deep link from `Empty`, or crossing `Demo → Real` (or `Real → Demo`) directly without going through the fork — shows a one-time banner acknowledged with **"I understand"**: *these ballots are live* (real) or *these are demonstration ballots* (demo), with a link to the demo space. Viewing then adopts that conversation's space, so the warning fires once and subsequent navigation within it stays silent. This arrival banner is the **single** live/demo warning — there is no separate per-vote confirmation.
- **Admin is exempt:** users with admin access (global admin, or any organizer/moderator role) are never shown the banner — we expect them to know what they are doing.

Leaving a demo for a real consultation is never forbidden: the demo (synthetic) identity is dropped and the normal login-required flow for the real conversation proceeds, with the direct-arrival banner carrying the *this is live* warning.

---

## Login and identity

Login is via Wikimedia account only — no separate registration. The participant's Wikimedia username is used as their display identity within the platform. No passwords, no email required.

## Participant identity

**Default: per-conversation pseudonym**
At the accept screen, participants are offered 5 pseudonyms to choose from, generated by combining dictionary words (e.g. "wandering-prism", "quiet-delta"). They pick one; it is stored for that conversation only and does not carry over.

Pseudonyms are generated using the `coolname` Python library (random adjective+noun combinations from a curated word list). This ensures names are readable, memorable, and not traceable to any other participant or external identifier.

Pseudonyms are unique across the entire platform — a name chosen in one conversation cannot be chosen by any participant in any other conversation. Once assigned, a pseudonym is permanently retired: the same pseudonym will never appear in any other conversation, for any participant.

In public results, pseudonyms appear at the individual vote level (e.g. which cluster a participant belongs to). The pseudonym is what appears in public cluster results once the admin enables them. Individual vote choices are never shown to others during voting (anti-herding).

**Opt-in identity reveal (post-close)**
After a conversation has closed and a cooldown period has elapsed, participants may choose to publicly associate their Wikimedia username with their pseudonym for that conversation. This is voluntary and irreversible.

When a participant reveals their identity:
- Their Wikimedia username is stored directly in the participation record alongside the pseudonym (not as a replacement — both are retained permanently, ensuring older exports of the data remain valid)
- In results displays, the Wikimedia username appears alongside or in place of the pseudonym
- The pseudonym is never deleted, for backwards compatibility with any snapshot of the data taken before the reveal

Participants must be shown a clear, prominent warning before confirming: this action cannot be undone. Once a username is attached to a participation record it stays there.

Cross-conversation tracking via pseudonym is structurally impossible — each conversation gets a different pseudonym, and old pseudonyms are never reused. Voluntary self-disclosure across conversations (e.g. a participant publicly stating they were a given pseudonym in two different conversations) is always possible and is the participant's own choice.

**Identity reveal & internal-link retention timeline:**

Two separate things run after a conversation closes: a participant's *voluntary, permanent* reveal, and the *removal* of the internal account↔pseudonym link the platform holds.

- **Cooldown** (`REVEAL_COOLDOWN_DAYS`, currently 30) — days after close before the reveal window opens. Gives time for any post-close review before participants attach their name.
- **Internal-link retention** — the internal account↔pseudonym link is removed by at most **180 days** after close (the public commitment; the internal target is sooner). Removal applies to participants who did **not** reveal; once it happens, no further reveals are possible. This internal-link removal is a separate data-minimisation workflow and is not the same as removing a voluntary public reveal.

| Day (current defaults) | Event |
|---|---|
| 0 | Conversation closes |
| 0 – 30 | Cooldown — reveal not yet available |
| 30 → removal | Reveal window open — a participant may *voluntarily and permanently* attach their Wikimedia username to their pseudonym. A reveal is never undone. |
| ≤ 180 (internal target sooner) | The internal account↔pseudonym link is removed for participants who did **not** reveal (data minimisation). Reveals already made remain — they are public by the participant's own choice. |

A reveal is **permanent**: once a username is attached to a pseudonym it stays, and is never nullified. Removal at the retention deadline affects only the *internal* link of participants who did not reveal; the pseudonym itself remains (for export compatibility), but its connection to a Wikimedia account is dropped.

The app no longer nullifies `public_username` / `revealed_at` after the reveal window. A separate internal-link removal workflow is still needed to implement the 180-day data-minimisation commitment for participants who did not reveal.

**Privacy policy commitment:** the public guarantee for removing the internal link is **180 days** after close; the internal target is sooner. Voluntary reveals are permanent and sit outside this clock.

**No individual early disconnection.** Participants cannot request early removal of the internal link. Reason: someone could attempt to influence the process and then erase the evidence, so the platform must retain the ability to investigate for the retention period. The platform-wide removal at the deadline is the only mechanism. (Revealing your name, by contrast, is voluntary and permanent.)

---

## Notifications

At the accept screen, participants are asked whether they want to receive updates about the consultation. Two channels are offered:
- **Email** — only shown if the participant has a confirmed email address on their Wikimedia account.
- **Talk page** — a post to their Wikimedia user talk page.

Both are opt-in checkboxes. Neither is pre-ticked. The platform makes clear that these are best-effort notifications and cannot be guaranteed to be sent.

The preference is stored at join time. The actual sending of notifications is a future feature — the infrastructure for collecting consent is in place, but no notifications are dispatched yet. Planned triggers:
- New statements have been added to a conversation they joined
- A featured statement they voted on has a new argument
- Their cluster assignment has changed

---

## Feature categorisation

### Natively supported
Provided by Polis and Particiapi out of the box — no custom development needed.

- Voting loop (agree / disagree / pass)
- Semi-random statement routing
- Statement submission by participants
- Immediate vote on a newly submitted statement
- Opinion clustering (PCA-based)
- Points of consensus and contention
- Vote changes (Polis default behaviour)
- Statement moderation via Polis admin UI

### Necessary extensions
We must build these. Without them the platform cannot function as designed.

- Inline "propose a better alternative" prompt after every vote — UI only; submits to the standard Polis statement pool
- Wikimedia OAuth as the login provider (Flask handles auth; Particiapi runs with auth disabled on internal network)
- Conversation creation and management (title, intro, outro, access policy)
- Accept flow — deliberate opt-in before a participant enters a conversation
- Access policies — public and invite-only enforcement
- Per-conversation invite management
- Per-conversation moderator roles; global admin roles
- Five independent phase toggles per conversation: submission open, personal results, argument mapping, full public results, informed voting
- Featured statement curation — system suggests candidates from cluster analysis; admin confirms
- Argument layer — submission, voting, display; visibility controlled by conversation-level argument mapping toggle
- Home page with active, archived, available, and moderating conversation sections

### Nice to have
Valuable for long-term engagement but not required for a first community test.

- Notifications to Wikimedia talk page or email on new statements or arguments
- "New since last visit" indicators on conversations and statements
- Results export for external analysis
- Custom clustering visualisation beyond Polis native display
- Multilingual UI

---

## What this platform is not

- Not a discussion forum. There are no threads, no replies, no quote chains.
- Not a voting system for decisions. Results surface opinion structure; they do not produce binding outcomes.
- Not a social network. Participants do not follow each other, see each other's vote histories, or accumulate reputation scores.
- Not a replacement for on-wiki processes. It is a complementary tool for understanding where a community stands before or during a formal process.

# Wiki-Polis Functional Design

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
- **Closed** — permanently ended; the conversation is hidden from available listings, voting is disabled, and the identity reveal timeline begins. Closing is irreversible.

Each conversation has an access policy:
- **Public** — anyone with a Wikimedia account can join
- **Invite-only** — only explicitly invited Wikimedia usernames can join

Participants must explicitly accept a conversation before entering it. The acceptance screen shows the intro text and asks for confirmation. This is a deliberate friction point — participants should understand what they are joining.

---

## Statements

A statement is an atomic claim: one idea, one sentence. Examples: *"Wikipedia's sourcing policy is too restrictive for recent events"* or *"Administrators should be subject to community re-confirmation every three years."*

Anyone who has joined a conversation can submit a statement. Statements go into a moderation queue before appearing to other participants. Moderators (scoped to their conversation) and admins approve or hide them.

Statements are presented to participants one at a time in a semi-random order. The system routes statements to maximise the information gained from each vote and reduce order effects.

---

## Voting

The core loop:

1. A statement appears
2. The participant chooses: **Agree**, **Disagree**, or **Pass**
3. An inline prompt appears: **"Have a better way to put this?"**
4. The participant optionally types a short alternative statement and immediately casts their own vote on it
5. The next statement appears

Step 3 appears after every vote — not only after disagree. It is always optional; the participant can skip straight to the next statement.

The proposed alternative is backend-identical to any other submitted statement: it enters the same statement pool and goes through the same moderation queue before others see it. The distinction is purely in emphasis — the prompt is surfaced inside the voting loop rather than hidden in a separate submission form, making contribution feel like a natural part of participation rather than an extra step.

Whether proposed alternatives require moderation before entering the pool is admin-configurable per conversation.

There is no discussion on the voting screen beyond this. No visible vote counts. No indication of how others voted. The experience is fast and private.

After voting on all available statements, the participant is shown a brief completion screen. If new statements have been added since their last visit, those appear on the next session.

---

## Results

A conversation has three independent toggles that the admin can switch on or off at any time. They can be active simultaneously or sequenced — the admin decides.

**Toggle 1 — Submission open**
Participants can vote on statements and submit new ones. This is the data collection phase.

**Toggle 2 — Personal results**
Each logged-in participant can see clustering results, but only for statements they have personally voted on. The more a participant votes, the more of the picture they see. This is a deliberate incentive: deeper engagement unlocks a deeper view. Individual vote choices are never shown — results are always aggregate.

**Toggle 3 — Full public results**
Complete clustering results are visible to everyone, including visitors who are not logged in. This is the full transparency view: consensus points, contention points, cluster breakdown across all statements.

When the participant count for a conversation is below a minimum threshold (currently 25), a visible warning is shown above the results: opinion groups detected from small samples can shift substantially as more people participate. Results are still displayed — the warning contextualises them rather than hiding them.

**Toggle 4 — Argument mapping**
The pro/con argument layer becomes visible on featured statements. Participants can read, submit, and vote on short arguments. When this toggle is off, the argument tab is hidden entirely — the voting loop and results are unaffected.

All four toggles default to off and are designed to be enabled in order — each phase building on the previous. The default sequence is:

1. Open submission — collect votes and statements
2. Enable personal results — reward participants with a view of how their engagement lands
3. Enable argument mapping — invite deeper engagement on the most significant statements before opening to the public
4. Enable full public results — open the findings to the wider community and visitors

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

---

## Admin panel

Admins can:

**Conversations:**
- Create a conversation (title, intro text, outro text, access policy)
- **Pause / Resume** — temporarily suspend a conversation without starting the identity reveal clock; reversible
- **Close permanently** — irreversible; immediately starts the identity reveal timeline. A confirmation dialog and a prominent warning distinguish this from Pause.

**Participants:**
- Assign and revoke moderator or admin roles, either globally or for a specific conversation
- Invite specific Wikimedia usernames to an invite-only conversation
- Remove invites

**Statements:**
- Mark statements as featured
- Enable or disable the argument layer on a featured statement

**Results phases (four independent toggles per conversation):**
- Toggle 1: open or close statement submission
- Toggle 2: enable or disable personal results (visible to logged-in participants for statements they voted on)
- Toggle 3: show or hide the argument mapping tab
- Toggle 4: enable or disable full public results (visible to everyone including visitors)

Admins do not need a separate moderation UI for hiding individual statements or arguments — that is handled in the Polis admin interface directly.

---

## Home page

The home page shows:

- **Your conversations — active** — conversations the participant has joined where there is still something to do: open submission, unread arguments, or results to explore
- **Your conversations — archived** — conversations the participant joined that are now inactive; results remain accessible but no further participation is possible
- **Available conversations** — conversations the participant is eligible to join but has not yet accepted
- **Conversations you moderate** — shown only to participants who are moderator or admin on one or more conversations. Lists those conversations regardless of their active or archived status. Hidden entirely if the participant has no such role.

Visitors who are not logged in see a brief explanation of the platform and a login prompt.

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

**Identity reveal timeline:**

Two configurable deltas control the timeline (both expressed in days):

- **Cooldown** (`REVEAL_COOLDOWN_DAYS`, currently 30) — days after close before the reveal window opens. Gives time for any post-close investigation before participants can modify their records.
- **Window** (`REVEAL_NULLIFY_DAYS`, currently 30) — duration of the open window, counted from when it opens. Nullification happens at `cooldown + window` days after close. This ensures nullification can never occur before the window has opened.

| Day (with current defaults) | Event |
|-----------------------------|-------|
| 0 | Conversation closes — reveal clock starts |
| 0 – 30 | Cooldown — reveal not yet available |
| 30 | Reveal window opens — participants may attach their Wikimedia username to their pseudonym |
| 60 (= 30 + 30) | Internal target: reveal window closes — `public_username` and `revealed_at` are nullified for all participation records in this conversation (data minimisation) |

After nullification, the pseudonym remains in the database permanently (for export compatibility), but the association with any Wikimedia username is dropped. This applies to all participants regardless of individual reveal choices.

The reveal action is irreversible for the participant during the reveal window — they cannot un-reveal. The platform-level nullification is automatic and runs lazily when any participant views the closed conversation.

**Privacy policy commitment:** the public guarantee will be more conservative than the internal target — likely between 60 and 180 days after conversation close. The internal target gives operational flexibility to act sooner; the public commitment sets the maximum participants can rely on.

**No individual early disconnection.** Participants cannot request early removal of their own identity link. Reason: someone could attempt to influence the deliberation process and then erase the evidence. Admins must retain the ability to investigate such cases for the full retention period. The platform-wide nullification at the end of the retention window is the only mechanism.

---

## Notifications (future)

After the initial release, participants should be able to opt in to notifications when:
- New statements have been added to a conversation they joined
- A featured statement they voted on has a new argument
- Their cluster assignment has changed

Notifications can be delivered to the participant's Wikimedia talk page or by email if they have one set.

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
- Four independent phase toggles per conversation: submission open, personal results, argument mapping, full public results
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

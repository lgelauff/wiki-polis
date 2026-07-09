# Organizer guide

> **⚠️ AI-generated draft — not reviewed.** Drafted by an AI assistant from this repo's
> research synthesis (`docs/research/`) and functional design. It has **not** been
> reviewed by a human. External citations carry confirmed-accessible URLs but the
> *claims* have not been independently re-verified against the primary sources — do that
> before relying on or publishing this guide (decision D-RESEARCH). Points marked
> *unknown — requires literature review* are open questions we have not resolved.

This guide is for **organizers**: you set up and run a consultation on wiki-polis from
start to finish. It describes the platform as it works **today**.

---

## What wiki-polis is

wiki-polis lets a Wikimedia community find out where it actually stands on a topic.
Participants vote Agree / Disagree / Pass on short **statements**, and the system maps
them into **opinion groups** — and, crucially, surfaces **cross-group consensus**:
positions that people across different groups agree on, not just overall majorities or
the views of the loudest contributors [5][6]. It is built on Polis.

It is a **structured listening exercise** — a map of where a community stands that you
can then act on. It is **not**:

- **not a decision-making or voting tool** — it surfaces opinion structure; it does not
  produce binding outcomes;
- **not a discussion forum** — no threads, replies, or quote chains;
- **not a social network** — no followers, no vote histories, no reputation;
- **not a replacement for on-wiki processes** — it complements them.

## How a consultation works (the phases)

A consultation moves through a linear sequence of phases — each builds on the last:

1. **Preparation** — setup only; participants can't do anything yet. You write seed statements, intro text, access and moderation policy, and appoint moderators.
2. **Submission** — participants submit statements and vote on them (the data-collection phase).
3. **Featured selection** — participants can see their personal results while you curate the featured statements that the argument layer will use.
4. **Argument mapping** — opens a pro/con argument layer on the featured statements. Participants read, submit, and vote on short pro/con arguments.
5. **Informed voting** — a second, independent voting round on the featured statements only, with the Phase 4 arguments shown inline so participants deliberate before casting a clean Agree / Disagree / Pass vote. Participants who skipped earlier phases can join here; the statement set is fixed. Must be **initialised** from the admin panel before the tab appears (see [Enabling informed voting](#enabling-informed-voting)).
   *After informed voting ends:* participants see **preliminary results** while the organizer reviews and moderates before publishing. This is the **cleanup window** — no new phase flag, just the active conversation in a review state (see [section 7](#7-review-results-and-clean-up-the-cleanup-window)).
6. **Publish final report** — the organizer explicitly closes the conversation once satisfied with the results. This publishes the final report at `/c/<slug>/report`, freezes the moderation filter (making report figures semi-immutable), and starts the identity-reveal window. Closing is **irreversible**.

### Moving between phases

There are two ways to advance, both in the conversation's admin panel:

- **Move on (guided, the normal path).** A "Move on to *<next phase>* →" box walks you one step forward. It spells out the consequences (what opens, what closes, what's irreversible) and shows a **readiness checklist** you must confirm before the button enables. Some items are machine-checked (e.g. "at least one featured statement selected" shows a met / not-met badge); the rest are judgement calls you tick off. The server re-checks everything on submit, so the checklist is a real gate, not just a reminder.
- **Advanced phase controls (admin only).** An "Advanced phase controls" panel exposes each phase as an independent on/off toggle, including moving **backward**. Use this only when you deliberately need a non-linear state; it opens automatically if the conversation is already in one. Only a site admin (not a conversation moderator) can change phases either way.

**Pause / Resume** is separate from phases: it temporarily disables voting without starting the identity-reveal clock, and is fully reversible. Pausing before informed voting is a good way to buy time to re-invite participants.

The guards that block or warn on these transitions (hard and soft) are catalogued in [`spec_functional-design.md`](../v2/spec_functional-design.md#phase-control-and-transition-guards).

## What a statement is

A **statement** is the atomic unit participants vote on: a single declarative claim, one
idea, that someone can Agree / Disagree / Pass on. Each vote is a data point, so a
statement is really a *measurement instrument* — if it's badly formed, the data it
produces is unreliable and the opinion map is wrong [1].

---

## 1. Choose the topic and scope

Pick a question narrow enough that statements stay on a shared subject, but broad enough
that there's genuine disagreement to map. Decide the scope up front so you can be
consistent later. See [`research/06`](../docs/research/06-scope-and-topic.md).

## 2. Create the conversation

Before writing any statements, create the conversation: give it a **title**, an
**intro** (what the topic is and why you're asking), an optional **outro** (shown after
a participant has voted on everything), and an **access policy** — public (any Wikimedia
account) or invite-only (named usernames), with invites if needed. See
[`spec_functional-design.md`](../v2/spec_functional-design.md).

## 3. Writing good statements

> This section is written to stand on its own — it may be published separately as a
> "how to write statements" guide.

Statements are the primary input to the algorithm, and their quality determines the
quality of everything downstream. The **seed statements** you write before opening have
outsized influence: they appear first, get the most votes, and frame the whole
conversation [1]. About 1 in 10 participants will add their own
statements; the rest only vote [3].

**What makes a statement good:**

- **One claim (atomic).** Never join two claims with "and / but / because." A compound
  statement forces someone who agrees with only part of it to Pass, which deletes their
  signal from the clustering [1]. *Bad:* "Wikipedia should require
  reliable sources and editors should disclose conflicts of interest." → split in two.
- **Neutral, not leading.** Don't load the wording. Framing genuinely changes votes — in
  one real Polis run the same policy drew 56% support under one framing and opposition
  under another [4]. *Bad:* "Shouldn't the Foundation be more
  transparent about grants?" → *"The Wikimedia Foundation should make its grant decisions
  more transparent."*
- **Concrete, not vague.** "Wikimedia should support a healthier community" earns
  near-universal agreement and tells you nothing. Name something specific.
- **Right scope.** Too broad ("Wikipedia should be accurate") and too narrow (one
  obscure template) both add no signal.
- **A claim, not a question or a title.** Questions can't be voted Agree/Disagree.

**How many, and how balanced:**

- Start with about **10–15 seed statements** [3]. Fewer leaves the space
  ill-defined; many more means you're over-determining the landscape.
- **Cover the range of views, not just your own framing** — include positions you
  disagree with. Mix *diagnostic* claims (what's the problem?) and *policy* claims (what
  should be done?), and deliberately include points where you expect **genuine
  disagreement**, not just easy consensus.
- So: **not boring, not one-sided** — a good seed set spans the real spread of opinion on
  the topic while staying on it.
- **What proportion should agree with a good statement?** *Unknown — requires further
  research / literature review.* The sources don't give a target agreement level (the 56%
  figure above is a framing illustration, not a guideline).

### Bulk-importing seed statements (CSV)

Instead of adding seed statements one at a time, you can upload them in bulk from the
conversation admin panel.

- **Format:** a UTF-8 CSV with a header row containing a **`text`** column (other columns
  are ignored). One statement per row.
- **Limits:** up to **20 rows** and **100 KB** per file. A file over either limit is
  **rejected whole** — nothing is imported — so fix and re-upload rather than getting a
  partial import.
- **Validation:** rows with an empty `text` are skipped and reported; the file must be
  valid UTF-8 with no null bytes. Leading spreadsheet formula characters (`= + - @`) are
  stripped to prevent CSV-injection.
- **Result:** after upload you get a summary — how many statements were imported, how many
  rows were skipped, and how many were duplicates. Duplicates are detected by wiki-polis
  itself (case-insensitive, against the statements already in this conversation) and each
  skipped statement is listed, so re-uploading the same file imports 0 and tells you exactly
  which rows already existed.

This seeds statements the same way the manual "add statement" form does; everything in
[*Writing good statements*](#3-writing-good-statements) above still applies — the limits
are deliberately low because a good seed set is ~10–15 statements, not hundreds.

### Recording a correction (statement provenance)

Moderators **cannot edit** an existing statement's text ([#142]); the workflow is to **hide**
the original and **add a corrected version**. When you do, the "Add seed statement" form has an
optional **"Corrects statement # (optional)"** field — enter the `#id` of the statement you're
replacing. This records that the new statement is a *derivative* of the original (#143).

Today this is just captured (and shown as a small `↳ #id` note next to the statement in the admin
list, with a cheap text-similarity score, so you can verify it landed). Future work will use these
links to cluster a statement with its derivatives and avoid over-representing the same idea in the
presented set, and to estimate how *semantically similar* a "correction" is to the original ([#207]).
Leave the field blank for a genuinely new statement.

[#142]: https://github.com/lgelauff/wiki-polis/issues/142
[#143]: https://github.com/lgelauff/wiki-polis/issues/143
[#207]: https://github.com/lgelauff/wiki-polis/issues/207

## 4. Open submission and moderate

Once open, participants vote and propose statements. **How strict should moderation be?**
This is a real judgment call, and the sources pull in two directions:

- Removing statements is common practice — keeping a conversation on-topic, non-abusive,
  and free of near-duplicates [2].
- But the Computational Democracy Project recommends removing **only abusive content** —
  *not* "off-topic," "duplicate," or low-quality statements. Removing non-abusive
  statements risks silencing perspectives that challenge your framing, especially from
  under-represented groups [5][1].

**Recommendation:** lean permissive — remove abuse, and be cautious about removing merely
off-topic or duplicate statements. **Consequences either way:** over-moderating biases
the opinion map toward your own framing and loses real perspectives; under-moderating
lets abuse and noise degrade the data. When in doubt, leave a non-abusive statement in.

## 5. Read the results

The algorithm reduces the (mostly empty) vote matrix with PCA and clusters participants
with k-means into **opinion groups** [1]. Read two things:

- **Consensus** — statements many groups agree on (e.g. 78% of group A *and* 80% of
  group B). These bridging points are the headline output.
- **Division** — statements one group backs and another rejects (e.g. 95% vs 20%). Still
  useful, but not consensus.

**Small samples:** the platform shows a warning below ~25 participants. *The 25 figure is
unverified — requires our own verification / literature review; treat it as provisional.*
Either way, don't over-read groupings from few participants.

## 6. Feature statements and the argument layer

> **Current limitation:** featuring well depends on first seeing **which opinion groups
> exist** — and that cluster view **doesn't work reliably yet**. This needs fixing first;
> it should get easier once the cluster tooling improves. *(pending — cluster
> identification not reliable yet.)*

Once you can see the groups, curate a small set of **featured statements** (group-
representative or strongly dividing ones) from the system's suggestions, or add them
manually. On featured statements participants read, submit, and vote on short pro/con
arguments. Keep the set small (≈8–12) — curation quality drives the argument layer.

## 7. Review results and clean up (the cleanup window)

After informed voting ends there is a **cleanup window** before the final report is
published. This is not a separate phase toggle — the conversation stays active while you
review. Participants see a **Preliminary results** banner during this time.

**What to do in the cleanup window:**
- Review the preliminary results (the Results tab shows the same data the final report will).
- Moderate any remaining flagged statements from the informed voting round.
- Once issue #60 ships: exclude any participants who violated the terms — their votes will
  be filtered from the final report counts.
- When you are satisfied: **publish the final report** by closing the conversation (see
  section 8 below).

> **Don't rush this step.** Once you close, the moderation filter is frozen and the
> aggregate counts in the report become semi-immutable. You can add a narrative and
> context before publishing, but the vote tallies won't change after close.

### What participants see during the cleanup window
The Results tab shows a "Preliminary results" banner. Once you close, it transitions to a
"Read the final report →" link. Participants are not notified automatically — consider
sending a talk-page or email notification when the final report goes live.

### Result surfaces

#### Preliminary results
Available on the **Results tab** as soon as informed voting is open (and continues through
the cleanup window). Shows agree/disagree bars side-by-side (Phase 2 initial vote vs Phase 6
informed vote) and an aggregate shift indicator. Marked **Preliminary** — counts change while
voting is open.

#### Final report (after close)
Published at `/c/<slug>/report` once `closed_at` is set. Shows:
- Participation counts for each round
- Full opinion-shift table, sorted by size of shift
- Opinion groups (clusters) identified in the informed voting round
- Moderation exclusions applied (statements and participants filtered from counts)
- Process timeline and methodology notes

The report is public when **Public results** is on; login-required when only
**Personal results** is on.

#### Self-comparison (coming soon)
A future surface will let participants see where their own votes place them relative to the
opinion groups.

### Two data sources — what the platform checks
The platform queries **two sources** and compares them:
- **Polis Postgres directly** (`votes_latest_unique`) — ground truth for vote counts;
  moderation filters are applied here.
- **Particiapi results API** — provides the cluster/group structure that Polis math computed.

If participant counts diverge by more than 5% (e.g. a moderation sync lag), the app logs a
warning. You'll see this in the server logs if it occurs.

## 8. Publish the final report and identity reveal

**Closing is irreversible.** It publishes the final report, freezes the moderation filter
(so aggregate counts in the report are semi-immutable), and starts the retention clock.

After a cooldown a participant may *voluntarily and permanently* attach their Wikimedia
username to their pseudonym; that reveal is never undone. The internal link between an
account and its pseudonym is removed within 180 days for participants who did **not** reveal.
See the identity model in [`spec_functional-design.md`](../v2/spec_functional-design.md) and the
[privacy statement](../v2/pub_privacy.md).

---

## Choosing your path (later version)

*Placeholder — to be written.* Not every consultation needs every phase. A later version
of this guide will lay out the composable paths — which phases you can skip and what
skipping each *effectively means* (e.g. stop after submission = a pure opinion poll; stop
after argument mapping = deliberation without a final vote). *(pending — later version.)*

## Good-practice checklist

- Scope written down before you open.
- ~10–15 atomic, neutral, concrete seed statements that span the real range of views.
- Phases turned on in order; don't open public results before there's enough data.
- Moderate for abuse; be cautious removing non-abusive statements.
- Don't over-read small samples.
- Be clear with participants: closing is permanent, revealing your name is optional and permanent.

## Enabling informed voting

Informed voting is a two-step admin action after argument mapping is complete.

**Step 1 — Turn on the toggle**

In the conversation admin panel → **Phases**, check **Informed voting** and save. The tab does not yet appear for participants.

> ⚠️ If statement submission or argument mapping is still on, a warning appears. You don't have to disable them, but informed voting is most meaningful once argument mapping is substantively complete.

**Step 2 — Initialise**

A new **Informed voting — setup** section appears. Click **Initialise Phase 6**. The app will:
1. Create a dedicated Polis conversation for the second vote round.
2. Seed each confirmed featured statement into it.

This takes a few seconds. On success you'll see the Polis conversation ID and how many statements were seeded. **Run this once.** Re-initialisation is blocked once it completes.

After initialisation the **Informed voting** tab becomes visible to all participants who have joined the conversation. Participants who never took part in Phase 1 can also join and vote.

**What participants see**

Each featured statement is shown as a card with:
- The statement text.
- Up to 3 pro arguments visible; a "Show more" fold-out reveals up to 10 per side.
- A placeholder if no arguments were submitted for a side.
- Three vote buttons: **Agree**, **Disagree**, **Pass**.

Participants vote independently of Phase 1 — the Phase 1 vote history is not shown, and the second-round votes go into a separate Polis conversation for clean analysis.

## References

> External sources, carried from the repo's research synthesis. URLs were confirmed
> accessible; the *claims* still need checking against the primary sources before
> publication (D-RESEARCH).

1. Small, Bjorkegren, Erkkilä, Shaw, Megill (2021), "Polis: Scaling Deliberation by Mapping High Dimensional Opinion Spaces," *RECERCA* 26(2). <https://gwern.net/doc/sociology/2021-small.pdf>
2. Huang, Siddarth et al. (2023), "Opportunities and Risks of LLMs for Scalable Deliberation with Polis," arXiv:2306.11932. <https://arxiv.org/abs/2306.11932>
3. EA Forum, "Polis: why and how to use it." <https://forum.effectivealtruism.org/posts/9jxBki5YbS7XTnyQy/polis-why-and-how-to-use-it>
4. Open Rights Group & Demos (2020–21), "Democratic Innovations: Polis and the Political Process." <https://www.openrightsgroup.org/publications/democratic-innovations-polis-and-the-political-process/>
5. Computational Democracy Project, "Polis" / "Lottery-Selected Assemblies." <https://compdemocracy.org/polis/>
6. Wikipedia, "Pol.is." <https://en.wikipedia.org/wiki/Pol.is>

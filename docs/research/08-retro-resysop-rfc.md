# Retro: enwiki's 2019 resysop RfC as a Proto-shaped consultation

> **Class: research (verified).** Written 2026-11-18 for the Proto design discussion.
> Every number below is derived from the wiki revision cited in §2 by the script in
> Appendix B; nothing is inferred from memory or taken from a secondary summary.
> **Status:** verified against the revisions cited. **Not a product spec** — it
> describes what one community did in wikitext, not what Proto should do.

## 1. Why this case

In October 2019 the English Wikipedia ran *Requests for comment/2019 Resysop
Criteria (2)*, the second part of a two-part RfC on restoring administrator
tools after a desysop. It matters here because the community **built Proto's
pattern by hand**: the proposer opened it with

> "This RfC will follow the endorsement of statements model, with users being
> able to put forward multiple proposals to be considered by the community."

Each of the 19 proposals carries its own *Users who endorse statement N* and
*Users who oppose statement N* lists. That gives an explicit participant ×
statement matrix — no inference from prose — which is exactly the artefact a
Proto consultation produces.

## 2. Provenance

| Item | Value |
|---|---|
| Page | `Wikipedia:Requests for comment/2019 Resysop Criteria (2)` (enwiki) |
| Opened | 6 October 2019, 00:18 UTC, by TonyBallioni |
| Individual closures | 4 November 2019, 19:42–00:12 UTC, by Cyberpower678 (statements 1–5, 7, 7.5) |
| Outcome markers added | 5 November 2019, 00:02 UTC, by Wugapodes (rev 924624736), edit summary "mark results from closures that cyberpower…" |
| Revision analysed | **924626190** (the revision at close, 328,001 bytes) |
| Current revision at time of writing | 1312940130 |
| Raw wikitext | `https://en.wikipedia.org/w/index.php?oldid=924626190&action=raw` |
| Fetched | 2026-11-18 |

Two independent outcome records exist and they do not cover the same statements:

- **Individual close boxes** (`{{archive-top|status=…}}`) on statements 1–5, 7
  and 7.5 only, each with the closer's rationale.
- **`{{aye}}`/`{{nay}}` markers** in the page's *Summary of Statements*, added
  the next day for all 18 numbered statements (7.5 is absent), plus four marked
  *Withdrawn* and one *Closed*.

Where both exist they agree. The outcome column in §4 uses the summary markers,
because they are the only outcome record for 11 of the statements.

## 3. Method, and what it deliberately does not do

1. Parse the revision's wikitext: statement headings, the proposal text, and the
   endorse/oppose lists under each.
2. Attribute a signature to a person by the first `[[User:…]]` (or
   `[[Special:Contributions/…]]`, or IP) link in each list item.
3. **Deduplicate** per (statement, list). This matters: 26 of the 465 raw
   signatures are repeats by the same person in the same list.
4. Support = unique endorsers ÷ (unique endorsers + unique opposers). It is a
   *ratio of stated positions*, not a vote share: it has no denominator of
   eligible participants.
5. Read outcomes from the close boxes and summary markers — never inferred.
6. **Not done:** no attempt to infer anyone's position from their prose, no
   sampling, no clustering result reported (an attempt at a two-cluster split of
   the 48 most active signers produced no defensible structure and is omitted
   rather than dressed up).

## 4. The 19 statements

Support is unique endorse ÷ (endorse + oppose). "Outcome" is the page's own
record. Wording here is a one-line gist; exact wording is in Appendix A.

| # | proposer | endorse | oppose | support | outcome | gist |
|---|---|---|---|---|---|---|
| 1 | TonyBallioni | 37 | 21 | 64% | **passed** | crat must be convinced the user intends to return to *activity* |
| 2 | Bradv | 26 | 21 | 55% | **not passed** | crat must be convinced the user *retains community trust* |
| 3 | Hasteur | 31 | 16 | 66% | **passed** | doubt about suitability → delay, crat chat, then consensus |
| 4 | Hasteur | 4 | 22 | 15% | not passed | state intended admin actions with the request |
| 5 | Pharaoh of the Wizards | 10 | 12 | 45% | not passed | no resysop after 5 years without a new RfA |
| 6 | GZWDer | 1 | 16 | 6% | *closed (SNOW)* | state intended frequency of admin actions |
| 7 | Amorymeltzer | 29 | 7 | 81% | **passed** | two years with no edits → new RfA; inactivity desysop needs one |
| 7.5 | DESiegel | 0 | 0 | — | *no outcome* | procedural note ("didn't seem to go anywhere") |
| 8 | Kusma | 7 | 14 | 33% | not passed | N months of 50 "non-stupid" edits proportional to absence |
| 9 | DESiegel | 4 | 17 | 19% | not passed | declare intended frequency of admin actions |
| 10 | Valereee | 1 | 2 | 33% | *withdrawn* | 50 edits/month for six months |
| 11 | Wugapodes | 6 | 15 | 29% | *withdrawn* | restore only via RfA unless resigned cleanly |
| 12 | Govindaharihari | 6 | 8 | 43% | not passed | minimal-edit gaming → community removal |
| 13 | Cyp | 4 | 11 | 27% | not passed | focus on recruiting admins, not restricting them |
| 14 | Valereee | 22 | 0 | 100% | **passed** | recognise the RfC result as a real problem to solve |
| 15 | JzG | 7 | 9 | 44% | not passed | no process without demonstrated evidence of the problem |
| 16 | Wugapodes | 17 | 18 | 49% | *spun out* | there should be a binding community desysop procedure |
| 17 | JFG | 1 | 9 | 10% | *withdrawn* | returning admins must demonstrate current need for the tools |
| 18 | Nosebagbear | 4 | 4 | 50% | not passed | net-supported proposals go to a workshop stage |

Totals: **75 unique signers, 465 raw signatures, 26 duplicates, median 5
positions per signer** (of 19 statements), maximum 16, and 49 signers with four
or more positions.

## 5. Findings

**F1. The pattern was invented locally.** Nineteen atomic proposals, each with
its own support list, in one page — the structure Proto would generate, written
by hand in wikitext.

**F2. Participation was thin per statement.** 75 signers between them recorded a
median of five positions out of nineteen. Support percentages here are therefore
ratios over a few dozen self-selected people, not measurements of a community.

**F3. Duplicates are not a rounding error.** Statement 1's oppose list carries
11 repeated signatures, statement 8's lists six. Raw counts overstate
participation by ~6%; any tool that tallies lists must dedupe by identity.

**F4. Eleven people appear on both sides of at least one statement** (four on
statement 1 alone, three on statement 11). In a page-of-lists model, "both
sides" is often one person changing their mind mid-month; the record cannot
distinguish that from error.

**F5. The sharpest finding: the closest call was about wording, not substance.**
Statements 1 and 2 are the same instruction — *a bureaucrat should be reasonably
convinced of X* — differing only in whether X is *intent to return to activity*
or *retains the trust of the community*. 37 people endorsed statement 1, 26
endorsed statement 2, and **24 endorsed both**; only 13 endorsed 1 alone and 2
endorsed 2 alone. Statement 1 passed at 64%, statement 2 failed at 55%. A policy
distinction of substance was produced by a handful of signatures separating two
wordings that most supporters treated as compatible — the closer of statement 1
noted "significant opposition … as being too subjective or too vague", and of
statement 3 "weak, but sufficient, consensus".

**F6. There was no mechanical threshold.** Highest failing support 55% (s2),
lowest passing 64% (s1); a two-thirds rule would have failed statement 1. The
record shows judgement applied to a ratio — never a rule: "weak, but sufficient"
(s3), "significant opposition" (s1). Any Proto feature that outputs a computed
verdict would be inventing a rule this community did not use.

**F7. Nobody could say whose judgement they trusted.** The subject of the RfC is
trust in returning administrators, and its mechanism asks bureaucrats to
exercise judgement — yet the only thing a participant could express was
agreement with *text*. There was no way to record "I trust X to weigh this
close", which is the signal the close actually needed.

## 6. Reception: what Wikipedia did with this consultation

Wikipedia does not evaluate its own processes. What it produces instead is four
downstream signals, all measurable from the link graph (659 inbound links to the
RfC page as of 2026-11-18: 609 from user talk pages carrying the RfC notice, 32
in project space, 18 on user pages):

**(a) Codification.** The outcome entered policy. The administrators' newsletter
for December 2019 recorded it in one sentence:

> "An RfC on the administrator resysop criteria was closed. 18 proposals have
> been summarised with a variety of supported and opposed statements. The
> inactivity grace period within which a new request for adminship is not
> required has been reduced from three years to two. Additionally, Bureaucrats
> are permitted to use their discretion when returning administrator rights."

`WP:ADMIN` now carries statement 7's wording almost verbatim — "**Over two years
with no edits.**" — and the page is reachable by the shortcuts `WP:RESYSOP2019`
and `WP:RESYSOP 2019`, i.e. the consultation itself is a citable policy
reference.

**(b) Citation as precedent.** Later discussions treat it as the record of what
the community decided. A 2021 RfC on sysop activity requirements says: "A year
later, the inactivity requirements were strengthened further in [the 2019
RfC]#Statement 7 by Amorymeltzer. In that same RfC (here) the community also
decided to grant bureaucrats the discretion to refuse resysop to people they
think have not actually returned."

**(c) Contestation in application.** The wording is litigated, not the process.
In March 2025 a bureaucrats' noticeboard dispute turned on exactly what the
"returned to activity" sentence requires, with one editor asserting "the
community consensus regarding a return to activity was to leave it to the
discretion of the bureaucrats", and another that "the established community
consensus is that bureaucrats do not have to be reasonably convinced that the
requestor continues to hold the community's trust" — which is the content of
**statement 2, the one that failed at 55%**. Note that this is one editor's
characterisation in a live dispute, not a ruling; but it shows the rejected
framing being read back into the record as settled.

The first application of the tightened criteria produced the same kind of
argument from the other direction. The *Signpost*'s August 2020 discussion
report: "One resysop request by an admin who was desysopped for inactivity led
to some controversy on the bureaucrats' noticeboard. The user would have been
eligible to be resysopped under the criteria in place when his administrator
rights were removed, but he was deemed to be no longer eligible due to the
resysop criteria being tightened in 2019." A retroactivity problem created by a
consultation that never asked about transitions.

**(d) Supersession.** The half of the problem this RfC could not settle — what
to do about admins who *should* lose the tools — went elsewhere: statement 16
was spun out during the RfC, and the desysop question was eventually answered by
a separate administrator-recall process (petition + re-request for adminship).
`Wikipedia:Administrator recall` does not mention the 2019 RfC at all.

**What is missing from all 659 links:** any discussion of whether nineteen
statements, seventy-five signers, and a 55%-versus-64% boundary was a good way
to decide. The reception is entirely about what the resulting words mean. That
is the honest answer to "how does Wikipedia evaluate these processes": it
evaluates the text, not the process, and the bill arrives as years of
interpretive dispute.

## 7. The same model recurs

The "statement + endorsement list" pattern is not a one-off. Searching enwiki
(namespace 4) for `insource:"Users who endorse statement"` returns five pages,
and for `insource:"Statement #1 by"` fifteen:

| Page | Statements counted | Endorsement sections | Unique users |
|---|---|---|---|
| RfC/2019 Resysop Criteria (2) | 19 | 19 | 99 |
| RfC/Arbitration Committee Elections December 2020 | 65 | 74 | 114 |
| RfC/Arbitration Committee Elections December 2019 | 47 | 53 | 120 |
| RfC/Arbitration Committee Elections December 2018 | 5 | 6 | 68 |
| RfC/Arbitration Committee Elections December 2017 | 5 | 6 | 99 |
| RfC/2010 ArbCom election voting procedure | 4 | 28 | 146 |
| Centralized discussion/Macedonia/main articles | — | 4 | 44 |

So: an annual series of ArbCom-election RfCs (2017–2020) that decompose election
rules into separately endorsable statements, a 2010 precedent on the voting
procedure, and the 2010 Macedonia naming discussions. Counts are of headings, so
multi-part options (`#1a`, `#1b`, `#1c`) inflate the statement figure — the
endorsement-section count is the more honest measure of how many endorsable
units there were. The exact-phrase search also undercounts: pages that use
*Support/Oppose* per proposal, or *Option A/B/C*, are the same idea in other
words.


## 8. Reception, second case: the ArbCom-election family

The annual pre-election RfCs are the same model in its mature form — "a request
for comment … to amend the structure, rules, and procedures of that year's
Arbitration Committee election and to resolve any issues not covered by
existing rules" (noticeboard announcement, 2018). Because they are framed as
amendments, they are also the only member of this family whose reception is
institutionalised rather than interpretive.

**A ledger, not a paragraph.** `Wikipedia:Arbitration Committee Election/Rules`
is titled *"ACERFC decisions to date"*, carries the shortcut `WP:ACERULES`, and
annotates **each rule with the specific RfC section it came from** — e.g. "There
will be 15 arbitrators, seven seats on Tranche Alpha and eight on Tranche
Beta from the 2019 elections.[…/Arbitration Committee Elections December
2019#Number of arbitrators]". `Wikipedia:Arbitration Committee election
requests for comment` (`WP:ALLACERFC`) is the hub that indexes the series.

**Survival is measurable.** Counting the source citations on the current rules
page: 78 citations across the 33 rule lines, distributed by year as 2020: 16,
2012: 12, 2019: 9, 2021: 7, 2014: 6, 2013: 5, 2022: 4, 2024: 4, 2015: 3,
2016: 3, 2017: 2, 2018: 2, 2023: 2, and one each for 2011, 2025 and 2026. The
most-cited year is 2020 — the one with 74 endorsement sections.

**Decisions get reversed, in public.** The hub page records the committee size
as "15 members (was changed from 15 to 13 in WP:ACERFC2018 and back to 15 in
WP:ACERFC2019)". Each flip is a later consultation overriding an earlier one,
with both citations still on the page.

**Even the threshold has been debated.** In September 2020 a proposal was
pending "to require a minimum of 15 supports for a proposal to pass, but there
are several … mutually exclusive proposals that have not had that level of
engagement (i.e. 'Do X' and 'Do not do X' both have fewer than 15 supports)" —
the same competing-framings artefact as §5 F5, recognised explicitly and
mid-flight.

**Why this matters for the contrast with §6.** The resysop outcome became a
paragraph of policy whose wording is now litigated; the election outcome became
a *cited list of amendments*, each traceable to the consultation and statement
that produced it. Same consultation model, same keyhole of 30–100 signers —
different artefact. A ledger survives revision; a paragraph survives argument.

## 9. What this implies for Proto

- **Duplicate/overlap detection before a consultation opens.** The 1/2 pair is
  the case for it: "these two statements say the same thing — do you support the
  idea, or the wording?" would have collapsed an artefact that changed policy.
- **Per-statement result cards, deduplicated by identity**, rather than one
  bundled question whose close has to reconstruct agreement afterwards.
- **Report counts and ratios, not verdicts.** The community's own record shows
  judgement applied to numbers (F6). A tool that prints "passed" borrows
  authority it was not given.
- **Offer a trust signal that is not a vote** — the layer F7 shows missing:
  during discussion, "I'd trust X to weigh this close", revocable, listed
  plainly, never ranked or summed into an outcome. Its jobs: choose who drafts
  the close from people trusted across positions, and let readers find the
  arguments others found worth trusting.
- **Emit a decision ledger, not a summary.** The election family shows the
  difference (§8): each rule carries the consultation and statement that
  produced it, so a later community revises item by item instead of
  re-litigating a paragraph. A Proto consultation should be able to hand over
  "statement, wording, support, close, link to the discussion" as a table the
  receiving process can cite — which is also what makes survival measurable
  years later.


## 10. Comparison: nlwiki's codified vote procedure

Dutch Wikipedia runs the same class of question through a written procedure
rather than a per-close judgement. The rules (my translations; nlwiki
`Wikipedia:Stemprocedure`, rev 71301286):

- **Escalation ladder.** Ordinary discussion first; if it deadlocks, a
  *non-binding* opinion poll on a talk page; only if that fails (no large
  majority, or little response) a vote in the Stemlokaal. A poll has **no
  quorum** and cannot bind anyone (`Wikipedia:Opiniepeiling`, rev 72180385).
- **Adoption rule, in numbers.** A proposal (or an option within one) is
  adopted if it has "the support of at least **20 valid votes** (the minimum is
  announced before the vote starts) and at least **55%** of the total number of
  valid votes" (Art. 5). Neutral declarations do not count.
- **Options are frozen.** The initiator becomes *stemcoördinator* — explicitly
  "a chore without privileges" — and "once the vote has started, no new options
  may be added" (Art. 2). Options should preferably be yes/no.
- **Moderator appointments** use the same machinery with a higher bar: a
  one-week poll, "a qualified majority of at least **75%** of responses", and
  only editors with ≥100 non-vandalism edits in the preceding twelve months may
  vote (`Wikipedia:Aanmelding moderatoren`, rev 71690742).
- **Iteration is normal.** The 2007 moderator-guideline simplification ran a
  first phase in which proponents argued each proposed change and unsupported
  proposals could be withdrawn, followed by a separate short poll per surviving
  proposal. The 2026 revision plan repeats the pattern — "poll on the draft,
  possibly several times" — then a vote, then a **seven-day objection period**
  before the old guidelines are retired.

**Where this beats what enwiki did.** The 2019 resysop consultation had no
participation floor, no threshold, no option freeze and no deduplication;
nlwiki has all four, and its freeze-before-vote rule plus per-proposal polls
address precisely the competing-framings artefact of §5 F5. It is also
protected against the opposite failure: a 20-vote floor stops a 22-signature
100% from carrying a policy.

**Where it is weaker.** Its provenance is thin. The moderator guidelines cite
only two polls or votes in 28 KB of text, so the chain from decision to rule is
not maintained — unlike `WP:ACERULES` (§8), where every rule carries the RfC
section that produced it. The 2026 plan even warns against reusing the old page
titles, because "20 years of discussion links … would then point at the new
policy" — the provenance problem recognised, and routed around rather than
solved.

**What happened when it was used on a contested question.** February 2025: an
amendment to the biographies-of-living-persons guideline on pronouns and former
names — a topic the community had been deadlocked on for years — ran under this
procedure. Result: **54 for, 40 against, 57.4%**, passed on a 55% threshold, with
one vote struck because the account had two edits before the poll opened. Three
votes the other way would have failed it.

It was then challenged. An objection was filed inside the seven-day window
alleging that the coordinator had influenced the vote by deleting a comment on
the discussion page. The coordinator — who was the subject of the objection —
referred it to the Arbitration Committee, noting that `WP:Stemprocedure` "gives
no further direction about how such an objection should be handled, as the
Arbitration Committee itself concluded in 2016". ArbCom accepted, and said
plainly that handling vote disputes "is not explicitly listed as a task of the
Arbitration Committee", and that the procedure "does not say how to act on an
objection"; it took the case as "other" business, called the deletion
"particularly clumsy" but immaterial, and upheld the result.

**The cautionary reading.** A mechanical threshold makes an outcome *decidable*
without making it *accepted*: 57.4% on a question people care about is a
three-vote margin, and the procedure that produced it had no legitimate path for
reviewing a challenge to it. That is the mechanism behind "people are usually
unhappy with the results" — the arithmetic is clean, the legitimacy is not, and
the dispute lands on whoever happened to run the poll.

**The summary that matters for tool design:** nlwiki formalises the *decision*
and loses both the *trace* and the *review path*; the ArbCom-election family
keeps the trace and leaves the decision to judgement; the resysop consultation
did neither. What transfers from nlwiki is narrow and procedural — **freeze and
deduplicate the options before opening, and state any threshold in advance** —
not majority rule as the decision rule, and not a threshold without a named
reviewer.


## 11. Design doctrine: standardised preparation, explicit non-decision

The two reception cases and the nlwiki comparison converge on one product
definition: **a standardised preparation instrument that does not decide.** That
is not a disclaimer to print at the bottom of a page — it has to be true of the
data model, or the instrument inherits the legitimacy problem it was meant to
avoid.

**Four tests of a genuine non-decision.**

1. **No terminal field.** Nothing in the schema or export says *passed*,
   *rejected*, *winner*, or *quorum met*. Support is a ratio with its
   denominator attached; the outcome belongs to a venue that is not this tool.
2. **No de facto threshold.** No ranking of statements by support, no "top
   proposals", no single blended number. The enwiki resysop case shows how
   quickly a de facto ~60% line is inferred from prose (§5 F6); a tool must not
   manufacture one by layout.
3. **The handover demands a second act.** The export is a ledger the receiving
   venue must cite and reason over: statement, wording, deduplicated counts,
   cluster split, arguments, dissent, and a stable ID per statement. A closer
   who uses it has to write their own reasoning; the record cannot stand in for
   the decision.
4. **A fixed statement of what it is not**, identical in every consultation:
   not a vote, not a quorum, not binding, and — the one people forget — *not a
   mandate to skip the decision*.

**What is actually being prepared: the draft, not the decision.** The consumer
of this instrument is primarily an *author* — a drafter, working group or
WikiProject writing the text — and only secondarily the venue that later decides
on it. That distinction changes the artefact. What a drafter needs is not a
ranking of proposals but a **drafting brief**:

1. **The core that can be written as the spine** — statements with broad support
   across clusters, with their exact wording.
2. **The fault lines, one per drafting decision** — where the room split, with
   the strongest argument on each side and the sub-question the text has to
   answer (carve-out, exception, explicit silence).
3. **The rejected framings, marked as deliberately excluded** — so the next
   drafter does not re-litigate what was considered and dropped.
4. **Wording warnings** — where two formulations of one idea split the room,
   that is evidence the wording is doing work the idea is not; the brief says so
   and quotes both.
5. **A dissent register** — who disagreed, with links to their argument, for the
   draft's talk page and for the eventual close.

This is also why the non-decision claim is easy to keep here: at the point Proto
runs, **no text exists yet**, so there is nothing to overturn, no threshold to
litigate and no quorum to meet. The drafting itself stays on-wiki — edits,
diffs, attribution, CC BY-SA — and the consultation's only lasting output is
material the drafter may cite or ignore, in public.

**Lifecycle this implies:** prepare (consultation) → draft (on-wiki authoring,
brief in hand) → optionally consult again on the draft → decide in the existing
venue → codify with the ledger. Proto owns the first and last steps and touches
neither of the middle two.

**What standardisation is for.** Not uniformity of outcome, uniformity of three
artefacts: the statement schema (one claim, attributable proposer, duplicate
check before opening), the phase sequence (respond → argue → informed response),
and the export format (the ledger, with stable IDs). Everything else — question,
eligibility window, participants, licence of the text — varies per consultation.
Standardise the format and let the authority stay absent. A standardised
*procedure* would be a decision system by another name, which is how nlwiki's
threshold arrived and what it now cannot review (§10).

**The success criterion follows from the definition.** If Proto prepares rather
than decides, "did the community accept the result" is the wrong measure — there
is no result to accept. The measurable ones are:

- **Use**: did the deciding venue cite the record, and in what terms?
- **Absorption**: does the next draft answer the fault lines the record
  surfaced — one drafting decision per line — and can each paragraph be traced
  to a statement or an argument?
- **Reasoning**: did the close engage with the fault lines the record surfaced,
  or with the loudest thread (the resysop case gives instances of both)?
- **Survival**: is the resulting policy text traceable, item by item, to the
  statements that produced it — the property `WP:ACERULES` maintains by hand
  (§8) and that a ledger can produce automatically?
- **Preparation quality**: duplicate rate before opening, share of participants
  who answered the comprehension question, opinion change between round one and
  the informed round.

**The failure modes this framing invites**, in order of likelihood: an organiser
presenting the output as a mandate; a venue citing "the consultation" without
reading it; and the consultation being used to close a question rather than open
one. The countermeasures are structural, not rhetorical — publish the decision
as still open, require the venue's own reasoning to be recorded, and instrument
citation rather than agreement.

## 12. Limitations

- Endorsement lists are self-selected and incomplete; several signers endorsed
  competing statements, and 11 appear on both sides of one statement.
- Four statements were withdrawn by their proposers and one closed as SNOW, so
  their support ratios are evidence of activity, not of preference.
- Only 7 of 19 statements have a closers' rationale; for the rest the summary
  marker is the only record, and it does not say why.
- The case shows what a statement consultation looked like in 2019 wikitext. It
  cannot show that Proto would have produced a better decision — only that the
  information needed for a better decision was, in part, already there.

## Appendix A — exact wording

Wording is quoted from each proposal's own `{{tqb|…}}` / `{{quote|…}}` where
present, otherwise from the proposal text, markup stripped. Statement 7's
operative text was written in the summary as an instruction rather than a quote;
it is reproduced from there.

1. *Before restoring the administrator flag a bureaucrat should be reasonably
   convinced that the user has returned to activity or intends to return to
   activity as an editor.*
2. *Before restoring the administrator flag a bureaucrat should be reasonably
   convinced that the user retains the trust of the community to serve as an
   administrator.*
3. *Should there be doubt concerning the suitability for restoration of Admin
   permissions, the restoration shall be delayed until sufficient discussion has
   occurred and a consensus established through a Crat Chat.*
4. *As part of the request for resysop, the returning administrator should
   indicate what actions they intend to do with the permissions. Bureaucrats
   shall be empowered to consider the assertion and any previous assertions.*
5. *Adminship will not be restored after 5 years for those who resigned without
   a new RfA (in addition to the 3 year inactivity rule).*
6. *Users requesting restoration of sysop flag after being desysopped for
   inactivity will be requested to state the frequency of admin actions which
   they intend to take if the tools are restored to them…*
7. *Over two years with no edits.* If an editor has had at least two years of
   uninterrupted inactivity between removal of the tools and the re-request,
   they must instead request through WP:RFA; after an inactivity desysop, one
   year of continued inactivity suffices.
8. *Any former admin who has been inactive for more than two years will be
   re-sysopped on request after a period of normal editing proportional to their
   length of inactivity. If N years have passed since desysopping, the former
   admin should edit for N months, making 50 "non-stupid" edits each month.*
9. *Users requesting restoration … will be requested to state the frequency of
   admin actions which they intend to take … If the stated anticipated level is
   not significant, or if the Bureaucrats do not find the statement credible in
   view of past history, they may decline the request.*
10. *Users requesting restoration … who have had fewer than 50 edits per year
    for each of the past three years will be required to make 50 edits per month
    for six months before resysopping.*
11. *Requests for restoration of administrator privileges should generally be
    made at requests for adminship. If an editor voluntarily resigned adminship,
    they may request restoration at WP:BN unless they resigned "under a cloud"…*
12. *Admins making clearly minimal edits to keep their advanced permissions …
    can be subject to a community discussion and removal of those permissions if
    such a consensus arises.*
13. *Instead of trying to find ways of restricting people from keeping the sysop
    bit, the focus should be on figuring out how to get more (competent) people
    to apply for and pass RfAs.*
14. *Given that non-admin users, including some of the community's most
    respected, voted 39-8 that our resysopping policy needs tightening, we
    recognize the RfC results represent an actual problem the community needs to
    find consensus to address.*
15. *Wikipedia should not be in the business of writing processes to avoid the
    stupid thing Bob did once. Any proposed solution must first require credible
    evidence of both a problem that it would have fixed, and the absence of any
    simpler or more efficient way of fixing that problem.*
16. *There should be a binding community desysop procedure.*
17. *Returning admins should demonstrate a current need for the tools.*
18. *Proposals that receive some form of net support in this RfC should be taken
    to a workshop/dedicated stage … unless they already possess clarity, don't
    contradict other proposals, and have a clear consensus for straight
    implementation.*

## Appendix B — reproduction

The numbers above come from revision 924626190. This reproduces §4 (Python 3,
only the standard library; `curl` or `urllib` for the fetch):

```python
import json, re, urllib.request
URL = ("https://en.wikipedia.org/w/api.php?action=parse&oldid=924626190"
       "&prop=wikitext&format=json&formatversion=2")
req = urllib.request.Request(URL, headers={"User-Agent": "wiki-polis research/1.0"})
w = json.loads(urllib.request.urlopen(req).read())["parse"]["wikitext"]

heads = [(m.start(), len(m.group(1)), m.group(2).strip())
         for m in re.finditer(r'^(={3,5})\s*(.+?)\s*\1\s*$', w, re.M)]

def users(block):
    out = []
    for line in block.splitlines():
        if not line.startswith('#'):
            continue
        m = re.search(r'\[\[(?:User|User talk):([^|\]]+)', line) or \
            re.search(r'\[\[Special:Contributions/([^|\]]+)', line)
        if m:
            out.append(m.group(1).strip())
    return out

for i, (pos, lvl, title) in enumerate(heads):
    m = re.match(r'Statement (\d+(?:\.\d+)?) by (.+)', title)
    if not m or lvl != 4:
        continue
    end = heads[i + 1][0] if i + 1 < len(heads) else len(w)
    seg = w[pos:end]
    def lst(kind):
        h = re.search(r'^=====\s*Users who ' + kind + r' statement '
                      + re.escape(m.group(1)) + r'\s*=====\s*$', w, re.M)
        if not h:
            return []
        nxt = re.search(r'^====', w[h.end():], re.M)
        return users(w[h.end():h.end() + (nxt.start() if nxt else len(w))])
    e, o = set(lst('endorse')), set(lst('oppose'))
    sup = f"{100*len(e)/(len(e)+len(o)):.0f}%" if (e or o) else "—"
    print(f"{m.group(1):>4} {len(e):>4} {len(o):>4} {sup:>5}  {m.group(2)[:30]}")
```

Mismatches between this table and §4 would indicate a parsing difference, not a
different corpus; the revision is fixed, so the numbers should be reproducible
exactly.

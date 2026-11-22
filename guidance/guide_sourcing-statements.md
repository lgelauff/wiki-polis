# Sourcing statements from a document

> **⚠️ AI-generated draft — not reviewed.** Drafted by an AI assistant from this repo's
> research files (`docs/research/`). It has **not** been reviewed by a human. Its claims
> about voting behaviour come from those files and have not been independently
> re-verified against the primary sources — do that before relying on or publishing this
> guide (decision D-RESEARCH).

This guide is for **organizers** whose seed statements come from a document: a white
paper, a strategy draft, a report. It sits between choosing the topic and writing the
statements, and it builds on
[section 3 of the organizer guide](guide_organizer.md#3-writing-good-statements), which
says what a good statement is.

The method was worked out while extracting 110 statements in eight sets from one white
paper [A, C]. The plan, the statement sets, the verification report and the log of what was
left out are all in the repo [B, C, D, E]; this guide pulls out the parts that apply to
any source.

---

## Before you start: read what kind of source it is

- **Advocacy or survey?** A source that argues for a position writes its sentences to
  persuade, so nearly every candidate will fail the neutrality check at first and need
  rewriting. Extraction from such a source is mostly *de-rhetoricising*: taking the
  persuasion out of the wording while keeping the claim [B].
- **Proposals, measurements, or framing?** Proposals ("X should do Y") are what Polis
  measures well. Measured figures are not statements (see
  [rule 1](#1-measured-figures-go-in-the-framing-not-the-statement-pool)). Diagnosis and
  framing passages can be statements, but including them is a scoping decision [B].
- **How many decision areas?** Group candidates into sets, each a coherent area with a
  distinct question people split on. Size each set to the 10–15 research figure in
  [section 3](guide_organizer.md#3-writing-good-statements). Run several sets as several
  conversations, or run a deliberate subset, rather than one large pool: large pools are linked to dropout,
  and the new-statement boost in Polis's routing fades after about 30 votes, so late
  statements may never be seen [B, F].

## The seven steps

1. **Harvest.** Go through the source section by section and pull every sentence that
   asserts a priority, direction, obligation or contested diagnosis. Keep the page number
   and the original sentence next to each candidate.
2. **Decompose.** Split every compound. Test for two or more claim-bearing clauses, not a
   naive split on "and". A list of three commitments is three statements when someone
   could hold one without the others [B, E §6].
3. **De-rhetoricise.** Strip the advocacy register — *must*, *urgent*, *the only way*,
   loaded metaphors. Keep the claim, drop the pressure. Voting on a metaphor measures
   reaction to the metaphor [B, E §4]. Don't overstate either: a statement that overstates
   its own case invites disagreement on the overstatement rather than the claim [D §1].
4. **Concretise.** Reject vague aspirations that would draw near-universal agreement.
   "X should have agency" is not voteable; "X should require Y to display attribution" is
   [B].
5. **Deduplicate.** Sources repeat their core points in the summary, the body and the
   conclusion. Cluster by meaning, keep the sharpest phrasing, note each page it appeared
   on, and check across sets as well as within them [B].
6. **Balance each set.** Each set should contain statements the source's authors would
   disagree with, some where you expect a genuine split, and a mix of diagnostic and
   policy claims. A set everyone will agree with produces no clustering signal [B, D §4].
   Positions the source rejects get their strongest sympathetic form (see
   [rule 3](#3-write-rejected-positions-in-their-strongest-sympathetic-form)).
7. **Verify.** Check every statement for atomicity, neutrality, concreteness, scope and
   form; keep it under 280 characters; and check **fidelity**: does the rewritten
   statement still say something that is in the source, or did rewriting invent a
   position? Cite the source page for each statement [B, D §5].

For each statement, record `Statement | Source p. | Type | Expected split` [B]. *Type* is
diagnostic (how things are), policy (what should be done) or value (what matters).
*Expected split* is your prediction, written down before the conversation runs so it can
be compared with the results: consensus (over 75% agreement), lean (55–75%), divisive, or
unknown [C].

## Three rules the method adds

### 1. Measured figures go in the framing, not the statement pool

Agree/Disagree on a measured quantity produces noise, not opinion structure.
Participants who do not know the figure Pass, and a high pass rate suppresses a
statement's exposure: pass rate enters Polis's comment router as `(1 − p)` inside a
squared term, so an unclear statement is not merely uninformative, it is buried [F §2].

Put the numbers in the conversation's framing material (the intro). Where a figure
carries a contestable *interpretation*, make the interpretation the statement, so
participants vote on it with the numbers in front of them [E §1].

### 2. Decide on purpose whether to show where the statements came from

A visible institutional label on statements biased voting in one documented case
(Klimarat), as reported in the extraction plan [B, C]; the research synthesis [F] does not
cover this finding. Presenting statements as *the document's proposals* will plausibly
pull votes toward deference. Against that, there can be good reasons to disclose the
source, such as the source's own case for participatory legitimacy [B].

This is a decision for the organizer; do not leave it to defaults. The worked example
settled it this way: disclose the source, but frame the statements as "positions drawn
from the paper, including ones it rejects" rather than "the paper's proposals" [C].

### 3. Write rejected positions in their strongest sympathetic form

Where the source argues against a position, write that position as its supporters would
put it, not as the source characterises it [B, step 6]. The worked example applied this
rule "with force" to every position the paper rejects [B]. A statement can split the room and still pass the neutrality check: sharpness is
about the substance of the claim, not the temperature of the wording [B].

## Keep a residue log

Record every claim from the source that you deliberately did **not** turn into a
statement, with the reason: a measured figure, background narrative, too abstract to
concretise, a rhetorical framing, out of scope, or a compound that resisted splitting.
That log is where your framing choices become visible, and it is where a later pass can
rescue what was lost [B, E]. The worked example's log [E] shows each category.

## Checking the result

What the worked example did at step 7 [D]:

- Ran `v2/statement_advisor.py`, a repo script that is not part of the app, over every
  statement. Treat its flags as advice: in the
  worked example 3 of its 5 flags were false positives from its scope word list, and
  those statements were kept with a written reason [D §1].
- Checked length against the 280-character limit [D §2].
- Ran a lexical near-duplicate check across sets [D §3]. Text similarity measures topic,
  not stance, so read each flagged pair rather than dropping it.
- Tabulated each set by predicted split and by type (diagnostic, policy, value) to check
  balance [D §4].
- Flagged the statements where rewriting moved furthest from the source, for review by
  someone who knows it well [D §5].

What it did not do, and you may want to [D §6]: an inter-rater check on predicted
splits, a semantic-similarity pass, and a test with real participants. Treat the first
conversation you run as partly an instrument test.

---

## Sources

In this repo:

- [A] Tarkowski & Valdelli, *Wikimedia, the commons, and the new AI knowledge loop*,
  White Paper v1.0, July 2026 (CC BY), as cited in [B].
- [B] [`docs/research/07-extraction-plan-ai-knowledge-loop.md`](../docs/research/07-extraction-plan-ai-knowledge-loop.md)
  — the seven-step method, the sizing and provenance warnings, and the decisions taken.
- [C] [`docs/research/statement-sets-ai-knowledge-loop/00-index.md`](../docs/research/statement-sets-ai-knowledge-loop/00-index.md)
  — the statement sets and the provenance recommendation.
- [D] [`docs/research/statement-sets-ai-knowledge-loop/98-verification.md`](../docs/research/statement-sets-ai-knowledge-loop/98-verification.md)
  — the verification report.
- [E] [`docs/research/statement-sets-ai-knowledge-loop/99-residue-log.md`](../docs/research/statement-sets-ai-knowledge-loop/99-residue-log.md)
  — what was left out, and why.
- [F] [`docs/research/06-atomic-statements-synthesis.md`](../docs/research/06-atomic-statements-synthesis.md)
  — section 2, the pass-rate mechanism; section 5, pool size and dropout.

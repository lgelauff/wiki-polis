# Reference — Polis statement-routing: insights for wiki-polis design

Handoff from the **polis-study** analysis of how upstream Polis decides which statement to
show a participant next (verified against `compdemocracy/polis` source). Full write-up:
`polis-study/docs/routing_mechanism.md`. This file distils only the parts that should
influence wiki-polis's own statement-assignment, moderation, and minority-protection design.

## How Polis routes (one paragraph)
At each vote, Polis picks one statement from the participant's not-yet-voted, moderation-passed
pool by **weighted-random roulette**. The weight is `priority = [(1−p)(E+1)a · (1+8·2^(−S/5))]²`
— agreeable (`a`) and group-differentiating (`E` = PCA extremity) statements score high,
passed-on (`p`) statements score low, brand-new statements get a large temporary boost (~60× a
mature statement, fading by ~30 votes), and the whole thing is squared to sharpen the bias.
Consensus-protection (GAC) is computed **downstream** for the report and never feeds routing.

## The five things that matter for wiki-polis

1. **Assignment is the highest-leverage hidden design choice.** Whatever rule wiki-polis uses
   to pick the next statement *manufactures* the vote matrix — over-served statements get
   evaluated, under-served ones effectively don't exist. Make it explicit and inspectable, not
   an accident of query order.

2. **The bored-passer minority-fate trap — design around this.** Polis penalises statements
   that get *passed* (`1−p`). But a pass is ambiguous: "this statement is irrelevant" vs "I'm
   tired and skipping." Fatigued participants pass to skip, so a statement unlucky enough to be
   served during a low-engagement window gets **buried at the routing stage — before any
   consensus/minority protection sees it.** A minority-relevant statement the majority skips is
   silently dropped. *Implications:* (a) don't let a pass-penalised priority alone gate
   exposure; (b) if you weight by pass-rate, **discount passes from globally-high-pass (bored)
   voters** vs selective passers; (c) protect minority statements at the *assignment* stage,
   because downstream consensus logic can't rescue what was never shown.

3. **Pre-seeded statements get a built-in ~1.4× exposure edge** — from *availability*
   (pre-approved, present from t=0, catching the new-comment boost in front of the largest early
   audience), not from any seed term in the formula (there is none). If wiki-polis pre-seeds,
   expect seeds to be over-represented in the data purely for being early; account for it in any
   analysis and consider whether that head start is desired.

4. **New statements get a ~60× boost → near-duplicates amplify an opinion.** Because new
   statements are force-fed exposure, a freshly-authored **near-duplicate** of an existing
   statement collects that boost precisely when new — so writing several near-duplicates is an
   exposure-capture / opinion-amplification vector. **This is the direct justification for
   wiki-polis's planned statement dedup ("anticipation approach"):** collapsing near-duplicates
   *before* routing neutralises it. Caveat: linguistic similarity ≠ opinion similarity — don't
   collapse statements that are phrased alike but sit on different opinion fault-lines.

5. **Moderation gating is a real exposure lever.** Under strict moderation a statement isn't
   votable until approved — measured ~63 min median approval latency upstream, vs instant for
   pre-approved seeds. Strict mode is also the designed defence against statement-flooding (the
   flood queues for the moderator). wiki-polis moderation design should weigh the
   approval-delay-vs-exposure tradeoff and treat moderation as part of the assignment system,
   not a separate cleanup step.

## One-line takeaway
Routing is upstream of everything (consensus, clustering, fairness); its biases — new-statement
boost, pass-based suppression, seed first-mover, near-duplicate amplification — become the
data's biases, so wiki-polis should design statement-assignment and dedup deliberately rather
than inherit these by default.

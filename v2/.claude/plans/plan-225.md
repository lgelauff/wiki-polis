# Plan — #225: Portable "statement helper" prompt (feed your own AI material → good statements)

**Verdict: FITS** — a self-contained, vendor-neutral prompt artifact participants paste into their own AI to convert raw material into well-formed Polis statements. Reuses existing principles; no app/runtime changes required for the core deliverable.

## Context

The statement-writing principles already exist and agree across sources:
- `v2/guide_organizer.md` §3 "Writing good statements" (atomic / neutral / concrete / right scope / claim-not-question; 10–15 seed count; cover the range of views).
- `v2/pub_participant-help.md` "Submitting a statement" (participant-facing short form + good/bad examples).
- `v2/spec_design-principles.md` (statements are atomic), `v2/spec_functional-design.md` (atomic claim, one sentence).
- Research backing: `docs/research/02-statement-writing-guide.md`, `04-arguments.md`, `05-website-copy.md` (branch `research/statement-principles`).

This issue is a **different surface** from #56 (in-app advising module) and #57 (in-app help pages): a portable prompt people run in *their own* assistant, before they ever reach the submission form. Distinguishing requirement (#225): it must accept **arbitrary user-supplied material** (a document, background reading, rough notes, a prior chat history) and help **extract + convert** it into statements — not just critique a single typed draft.

## Deliverable

A single standalone artifact: **`v2/pub_statement-helper.md`** (following the `pub_` public-doc convention). It is two things in one file:
1. A short human intro ("what this is / how to use it").
2. A clearly-delimited **copy-paste prompt block** the user pastes into any assistant, followed by their material.

Assistant-agnostic: no Claude/vendor-specific syntax, no tool calls, no system-prompt-only assumptions — must work pasted as a plain user message into ChatGPT / Claude / Gemini / a local model.

## Files to change

- **Create `v2/pub_statement-helper.md`** — the artifact (intro + prompt block + examples).
- **`v2/guide_organizer.md`** — add a one-line pointer in/after §3 ("Share the portable statement helper with participants before opening: `pub_statement-helper.md`").
- **`v2/pub_participant-help.md`** — add a one-line pointer under "Submitting a statement" ("Want help turning your notes into statements? See the statement helper.").
- *(Optional, defer)* serve it as a page / link from the conversation intro — see "Distribution" below; not required for the artifact to be usable.

## Artifact structure (`pub_statement-helper.md`)

1. **Title + one-paragraph intro** — what a Polis statement is, why form matters (atomic claims are the algorithm's input), and that this prompt helps convert their own material into good ones.
2. **How to use** — "Copy the block below into your AI assistant, then paste your material (a document, notes, an article, a past chat — anything that captures what you want to say). The assistant will help you turn it into clean statements you can submit."
3. **The prompt block** (delimited, copy-paste). It instructs the assistant to:
   - **Role:** help the user turn their material into a shortlist of good statements for a Polis-style consultation.
   - **Ingest** whatever the user pastes; ask 1–2 clarifying questions only if the material's intent is unclear.
   - **Extract** the distinct claims/opinions buried in the material.
   - **Atomize:** split any compound claim ("and / but / because") into separate statements — note *why* (a compound forces partial-agreers to Pass, deleting their signal).
   - **Reform non-statements:** rewrite questions and topic titles as claims; drop pure facts (a statement is an opinion people can agree/disagree with).
   - **Neutralise framing:** flag leading wording and offer a neutral rewrite.
   - **Check** concreteness (no vague near-universal-agreement statements) and scope (not too broad / too narrow); standalone readability (no "see above").
   - **Dedupe / coverage:** merge near-duplicates; gently prompt the user to include views they *disagree* with (good sets span the spread, not one side).
   - **Output:** a numbered shortlist of clean, one-sentence statements, each ≤ ~140 chars, with a one-line "why this works / what I changed" note; then ask the user which to keep/edit. Do **not** auto-submit anywhere.
   - **Tone:** coach, don't lecture; keep it short.
4. **Worked example** — a messy paragraph in → 3–4 atomic statements out (reuse the canonical good/bad pairs from `pub_participant-help.md`, e.g. the compound "reliable sources and disclose COI" split, and the "Shouldn't the Foundation be more transparent?" → claim rewrite).
5. **The principles, condensed** — the bullet list from `guide_organizer.md` §3, so the artifact stands alone if separated from the repo.

Keep wording assistant-agnostic and in plain language; mirror the existing copy so guidance stays consistent across surfaces.

## Distribution (lightweight; the artifact works without this)

- Primary: a copy-paste markdown block organizers can share in a consultation's intro/briefing and link from the docs.
- Optional follow-up (own issue if pursued): expose it at a stable public URL / "Statement helper" page linked from the submission form and the conversation intro, so participants find it in-context.

## Scope note

**Statements only** for this artifact. A sibling "argument helper" (arguments are a wiki-polis addition, not standard Polis) is a natural follow-up — file separately rather than overloading this one (the issue flags this open question).

## Tests / verification

- **Dogfood the prompt** in at least two generic assistants (e.g. ChatGPT + Claude) with three inputs: (a) a multi-claim paragraph, (b) a leading question, (c) a short chat-history snippet. Confirm output is atomic, neutral, one-sentence, deduped, and that it asks before finalizing and never claims to submit.
- **Principle parity check:** every principle in `guide_organizer.md` §3 is represented in the prompt block; wording doesn't contradict `pub_participant-help.md`.
- **Standalone check:** the artifact makes sense with zero wiki-polis context (a facilitator could share just this file).
- Markdown lint / link check on the new file and the two pointer edits.

## Related

- #56 (in-app advising module), #57 (in-app help pages) — same principles, different surfaces; keep copy consistent.
- Source principles: `v2/guide_organizer.md` §3, `v2/pub_participant-help.md`, `docs/research/02-statement-writing-guide.md`.

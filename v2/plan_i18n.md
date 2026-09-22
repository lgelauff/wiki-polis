# Interface internationalisation plan

> **Forward plan — active, revised 2026-09-12.** Sequence, freeze criteria, and open
> decisions; not shipped behaviour. For what is wired today see
> [`i18n/README.md`](i18n/README.md) — that file is the status and stays current, this one
> is the plan and changes only when the plan changes.

## Outcome

The Proto participant interface is available in Dutch, and the interface as a whole is
translatable on translatewiki.net by volunteer translators, with a key namespace stable
enough that their work is never invalidated.

## Constraints

1. **Dutch is needed in about a week** (requested 2026-09-12). This is the binding
   constraint and it reorders everything below.
2. **translatewiki onboarding is filed once the labels are settled** — after stages 1, 2
   and 4 rather than in parallel with them. Filing is reversible, so parallel filing was
   defensible, but a reconciled catalogue makes for a simpler request and ensures no
   translator is offered a message that renders nowhere. Dutch does not depend on it
   (rule 1's exception).
3. **The participant interface is the deliverable. The admin console is nice-to-have.**

These change the ordering that applied when there was no deadline. The earlier draft
sequenced wiring by existing key coverage; under a Dutch deadline the participant interface
takes precedence, since a translated admin console does not serve a Dutch-speaking
participant.

## Where this stands — 2026-09-12

Foundation on `main` ([#357](https://github.com/lgelauff/wiki-polis/pull/357),
[#369](https://github.com/lgelauff/wiki-polis/pull/369)): an 872-key English catalogue in
translatewiki "banana" format, 100% `qqq` coverage, a stdlib-only resolver with per-key
English fallback, per-request locale negotiation, `GET /api/v1/i18n/<locale>`, and **four
screens** reading from it. `ENABLED_LOCALES=en`.

**Only those four screens read the catalogue.** The other 26 components hold literal English
and will render English regardless of how complete a translation is. Dutch is therefore a
wiring problem before it is a translation problem.

### Catalogue state

872 keys. 321 referenced by a static call site. The remaining 551 were authored against the
19 Jinja templates deleted in [#351](https://github.com/lgelauff/wiki-polis/pull/351), and
matching each against the English still on screen in unwired components splits them:

| Orphan bucket | Count | Meaning |
|---|---|---|
| Claimed | 298 | an unwired component still shows this text — will be used by stage 2 |
| Near-match | 13 | text has drifted; requires review |
| No match found | ≤240 | deletion **candidates**, pending stage 4 review |

The third bucket is unreliable and must not be actioned as it stands. Spot-checking found
`phase-label-*`, `precond-*`, and `rec-field-*` — keys that look unreachable only because
their consuming surface is unwired, or because the text they replace is currently shipped
from Python (see stage 1). **Reconciliation therefore comes after wiring, not before**: the
wiring is what establishes reachability.

The figure of "551 keys rendering nowhere" is inaccurate and should not be reused: most
of the 551 are pre-authored copy awaiting the component that will use it.

### Component scope

Counts come from a heuristic scan of JSX text nodes, user-visible attributes, and string
literals. It over-collects, so read the string totals as **upper bounds** and the
already-keyed share as a floor.

**Participant — 13 components, ≤279 strings, 152 already keyed.** These carry the
messages offered for translation; the admin console's are held back under rule 8. The
current counts of each are in `i18n/README.md`.

**Participant components:**
`argument-mapping-panel` (56/23 keyed), `conversation-lane-page` (38/19),
`guidance-pages` (35/12), `conversation-read-pages` (34/22),
`participation-entry-page` (33/28), `identity-reveal-page` (25/19),
`informed-voting-panel` (23/16), `public-pages` (13/2), `legacy-shell` (9/3),
`intermediate-results-panel` (5/4), `legacy-content-flag` (5/3), `app.tsx` (2/1),
`main.tsx` (1/0).

**Admin — 11 components, ≤170 strings, 98 already keyed.** Deferred; see stage 5.

## Architectural rules

Settled. Changing one is a plan change, not an implementation detail.

1. **Three kinds of file, three owners.** The earlier wording — "never hand-edit a delivered
   `<code>.json`" — read strictly forbade editing `qqq.json`, which is a locale code by that
   pattern and which we edit constantly. translatewiki's own guidance draws the line
   differently:

   - **`en.json` is ours.** Translators never edit the source. They *propose* changes —
     grammar corrections, a missing `{{PLURAL:}}`, an ambiguous string — on the project talk
     page or our issue tracker, and leave a `FIXME` note on the message's `/qqq` page while it
     is outstanding. Those notes arrive here on the next export, so **a `FIXME` appearing in
     `qqq.json` is a translator reporting a defect in our English**, and worth reading as
     signal rather than noise.
   - **`qqq.json` is shared, and it round-trips.** Edit it directly when adding a message or
     changing an English one; otherwise documentation "should usually be edited in
     translatewiki", and those edits are exported back to this repository along with the
     translations. So this file receives commits from both sides.
   - **`<lang>.json` is translatewiki's.** Never hand-edit one: the next export overwrites it,
     and the edit discards a volunteer's work. `test_a_translation_for_a_deleted_message_is_not_served`
     exists so that deleting a key from `en.json` never requires touching one.

   Cadence, for planning: sync (new source strings going out) is roughly daily and automatic;
   export (translations and `qqq` coming back) is manually initiated, usually about twice a
   week.

   **Bootstrap exception, live now:** `nl.json` is authored in-repo ahead of translatewiki
   onboarding, because a review queue cannot meet a one-week deadline. When the group comes
   online, that file is handed to translatewiki as the seed for Dutch and TWN becomes
   authoritative from that point. This exception covers Dutch only and ends at stage 6.
2. **Every `en.json` message has a `qqq.json` entry.** CI fails otherwise.
3. **Interface copy is keyed; participant-authored content never is.** Statements, arguments,
   titles, and usernames pass through untranslated.
4. **Server-side error copy is not keyed.** 122 distinct strings across 140
   `error_response(...)` / `abort(description=...)` call sites in `v2/*.py`, `v2/api/` and
   `v2/services/` (recounted 2026-09-21) stay developer-facing; the SPA maps `error.code` to
   its own keyed copy. This is the figure's only home; `i18n/README.md` refers here.
5. **One message per concept, not one per surface.** Reuse before minting; when two surfaces
   show the same words for the same thing they share a key, and the `qqq` names every surface
   ([#369](https://github.com/lgelauff/wiki-polis/pull/369)).
6. **A UI label is never shipped from the server as English.** Presentation constants that
   cross the API send a key or stable identifier the SPA maps, never display text.
7. **Key convention:** `surface-subkey`, lowercase-hyphenated, grouped by screen. A key name
   must not contradict its own text.
8. **Only messages that are both participant-facing and settled are offered to translators.**
   Two groups are held back, for different reasons, tracked separately so either can be
   released without the other:

   - **The admin console** — it needs product work before it is worth volunteer time, and it
     is about a third of the catalogue's words while serving a handful of organisers per
     consultation.
   - **The help pages** (`guidance-*`) — their copy is still being worked on and may be
     expanded or dropped. Key names freeze once translators start, so churning the text
     behind a frozen key spends volunteer effort twice. Participant-facing, so they return as
     soon as the content settles.

   Holding either back is a translatewiki configuration choice: every key, call site and
   `qqq` entry stays, so releasing one is deleting its lines from a list. **A message
   reachable from a participant screen is never held back for the admin console's sake** —
   under-translating a participant string is a user-facing defect, over-translating an admin
   one costs a little volunteer time. The split is computed, not hand-listed, in
   `tests/test_i18n_audience.py`, which fails if the config drifts from it.
9. **The product is called Proto.** Settled 2026-09-12, and recorded here because two of its
   consequences are hard to reverse: the translatewiki group id is `proto`, and a group id
   freezes when translators start; and nine catalogue messages carry the name in their
   English text, so a later rename means re-translating them in every language. The
   repository stays `wiki-polis` ([#289](https://github.com/lgelauff/wiki-polis/issues/289))
   — the `FILES` paths in `translatewiki-group.yaml` address a checkout directory, not the
   product, and the divergence is deliberate. `{{msg-proto|…}}` cross-references in
   `qqq.json` embed the group id too, so they move with it.

## Irreversible step: the key-name freeze

**translatewiki freezes key names once translators begin work on the group.** Renaming a key
after that costs translators their work; deleting a translated message wastes work already
done.

Filing the support request does not trigger the freeze. Configuration, licence review, and
sync-bot setup are reversible and change nothing about the namespace. The freeze begins when
the group is opened to translators, at stage 6.

## Work sequence

### 0. translatewiki onboarding — after stage 4

Held until the catalogue has been reconciled. The review queue is real, but filing early
buys nothing: Dutch does not arrive through translatewiki (rule 1's exception), and a
reconciled catalogue makes for a shorter request.

Waiting also removes a question. How translatewiki handles key deletion before launch only
matters while deletions are pending; reconciling first settles it.

When filed:

- Licence requirement is already confirmed: **GPL-3.0, detected by GitHub's licence API** on
  a public repo.
- Reference `i18n/translatewiki-group.yaml`.
- Flag the `proto` group id against the `wiki-polis` repository path
  ([#289](https://github.com/lgelauff/wiki-polis/issues/289)), so TWN does not "correct" one
  to match the other.
- Ask whether the in-repo `nl.json` can seed the Dutch group, so that work is preserved and
  translators continue from it rather than starting over. By then it will be substantial.

**Exit:** the group exists and the sync bot is configured.

### 1. Server-shipped UI labels

Twelve module-level display-text maps cross the API as English, **38 strings**, rendered raw
by components that otherwise read the catalogue. These are untranslatable today even on the
four finished screens, which makes this the first thing Dutch needs.

- `services/conversation_workspace.py` — `TAB_LABELS`, 5 tab names. All five already have
  exact-matching keys (`conv-tab-vote`, `-results`, `-arguments`, `-informed`,
  `-preliminary`), and the SPA already receives `tab.key`.
- `services/conversation_lanes.py:54` — 7 phase display names, rendered at
  `admin-lifecycle-page.tsx:136`. The `phase-label-*` keys are their replacement.
- `app.py` — flag reasons (4), phase-route names and descriptions (6), cleanup/closed
  labels (2), vote-choice labels (3).
- `error_pages.py` — three error pages, 9 strings. Weigh against rule 4: these are pages a
  participant sees, not API error payloads, so they are interface copy and should be keyed.
- Add a test that fails when a new display-text constant crosses the API.

**Exit:** no user-visible English reaches the SPA from a Python constant, and a
reintroduction fails CI.

### 2. Participant interface wiring

> **Done 2026-09-14.** Wired and tested in #357, #371, #385, #386 and #392–#395; the markup check that
> translations must pass landed in #389. The deliberate exceptions (help pages, admin
> console, server error messages, moderation-log fallbacks) are listed in
> [#399](https://github.com/lgelauff/wiki-polis/issues/399). Carried into stage 3: the
> join-screen tests in [#391](https://github.com/lgelauff/wiki-polis/issues/391), which must
> land before Dutch is switched on, and deleting the two components nothing renders
> ([#387](https://github.com/lgelauff/wiki-polis/issues/387)).

Thirteen components, ordered as a participant encounters them, so that partial progress
covers a continuous journey rather than scattered screens:

1. `public-pages`, `legacy-shell`, `app.tsx`, `main.tsx` — the frame and landing.
2. `participation-entry-page` (33 strings, 28 keyed) — join, consent, licence.
3. `conversation-lane-page` (38/19) and `conversation-read-pages` (34/22).
4. `guidance-pages` (35/12) — the explainers before each task.
5. `argument-mapping-panel` (56/23) — the largest single component, and the one with the
   most minting.
6. `informed-voting-panel` (23/16), `intermediate-results-panel` (5/4).
7. `identity-reveal-page` (25/19) — privacy-critical copy; review wording, do not just map.
8. `legacy-content-flag` (5/3).

Reuse before minting (rule 5). Prove each wiring non-vacuously, per
[#357](https://github.com/lgelauff/wiki-polis/pull/357) — a test that passes identically
before and after has not tested the change.

**Exit:** no user-visible literal English in any participant component, and the
key-existence guard resolves call sites in each.

### 3. Dutch translation

- Author `i18n/nl.json` for the participant key set. Per-key English fallback means a partial
  file degrades to English rather than breaking, so this can land incrementally and early.
- `ENABLED_LOCALES=en,nl`.
- Verify with a real locale, not `qqx`: plural forms, `$1` ordering where Dutch word order
  differs from English, and the 30 messages containing inline HTML.
- Walk the participant journey in Dutch end to end before announcing it.

**Exit:** a Dutch-speaking participant can join, vote, argue, and read results without
meeting English.

### 4. Unreferenced-key reconciliation

Only meaningful once stage 2 has established what is reachable.

- Re-run the orphan triage. The ≤240 no-match bucket shrinks as stages 1 and 2 land.
- Go prefix by prefix, not in bulk. Each surviving key is deleted or justified in writing;
  "might be useful later" is not a justification, because translators pay for it in every
  language.
- Resolve the 13 near-matches by hand.
- Add a CI guard reporting keys with no call site, so the count cannot silently grow.

**Exit:** every key is referenced, or listed with a reason it is not.

### 5. Admin console — deferred

Eleven components, ≤170 strings, 98 already keyed. Ordered by existing key coverage, which
is appropriate here because no deadline applies: `admin-invitations` (5/4), `admin-moderation` (10/9),
`admin-participants` (17/14), `admin-catalog` (25/18), `admin-statements` (39/27),
`admin-featured` (19/12), then the authoring-heavy `admin-roles` (10/4),
`admin-settings` (21/6), `admin-termination` (16/2), `admin-routes` (7/2),
`admin-access-boundary` (1/0).

**Exit:** as stage 2, for the admin surface.

### 6. Namespace freeze and translator onboarding

- Freeze the namespace; announce in `i18n/README.md`.
- Hand `nl.json` to translatewiki as the Dutch seed and retire rule 1's exception; TWN is
  authoritative from here.
- Open the group to translators.
- Verify a delivered translation round-trips through the sync bot, and exercise an RTL locale
  for `g.dir`.

**Exit:** a translator completes a message on translatewiki and sees it render in Proto.

## Open decisions

- **Who translates Dutch**, and whether they work in the repo or wait for translatewiki.
  Stage 3 assumes in-repo.
- **Whether `error_pages.py` copy is interface or error copy** — stage 1 argues interface,
  which is a narrowing of rule 4 rather than an exception to it. Confirm before wiring.
- **Whether rule 5 generalises.** Sharing one message across a button and a state label
  removes a translator's ability to split them where a language needs it. Settled for the
  vote labels; revisit when a translator asks.
- **`?uselang=` cookie lifetime** and its interaction with a future account preference.
  Negotiation order is implemented; persistence policy is not decided.

## Out of scope

Content translation of participant-authored statements and arguments; machine translation of
any kind; locale-specific clustering or results interpretation; and any renaming or deletion
of keys after stage 6.

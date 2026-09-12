# Interface internationalisation plan

> **Forward plan — active, 2026-09.** This records sequence, freeze criteria, and open
> decisions, not shipped behaviour. For what is wired today see
> [`i18n/README.md`](i18n/README.md), which is the status document and stays current;
> this file is the plan and changes only when the plan changes.

## Outcome

The ProtoWiki interface can be translated on translatewiki.net by volunteer translators,
with a key namespace stable enough that their work is never invalidated, and without any
translator spending time on a message that renders nowhere.

## Where this stands — 2026-09-12

The foundation is on `main` ([#357](https://github.com/lgelauff/wiki-polis/pull/357),
[#369](https://github.com/lgelauff/wiki-polis/pull/369)): an 872-key English catalogue in
translatewiki "banana" format with 100% `qqq` coverage, a stdlib-only resolver, per-request
locale negotiation, `GET /api/v1/i18n/<locale>`, and four screens reading from it.
`ENABLED_LOCALES=en`, so none of it is user-visible.

Two numbers define the remaining work, and they are not the same number:

| | Count |
|---|---|
| Catalogue keys | 872 |
| …referenced by code | 321 |
| …**referenced by nothing** | **551** |
| Literal English strings still in components | ~370, across 26 components |

The first three rows are exact. The last is a scan of JSX text nodes and the
`aria-label`/`title`/`placeholder`/`alt` attributes, so read the per-component figures in
stage 2 as relative sizes rather than counts to plan against.

The 551 are not a backlog of future keys. They were authored against the 19 Jinja templates
deleted in [#351](https://github.com/lgelauff/wiki-polis/pull/351), so each one is either a
message some remaining SPA surface still needs, or a message nothing will ever render.
Roughly 70% of the remaining literal strings already have a key, so wiring consumes part of
the 551 — but a substantial remainder will have no target and must be deleted rather than
carried.

Deciding which is which is the bulk of this plan. It is cheap now and impossible later.

## Architectural rules

These are settled. Changing one is a plan change, not an implementation detail.

1. **`en.json` is the source; translations arrive only from translatewiki.** Never hand-edit
   a `<code>.json` that is not `en` or `qqq`.
2. **Every `en.json` message has a `qqq.json` entry.** CI fails otherwise.
3. **Interface copy is keyed; participant-authored content never is.** Statements,
   arguments, titles, and usernames pass through untranslated.
4. **Server-side copy is deliberately not keyed.** The 112 distinct user-visible strings
   across 138 `error_response(...)` and `abort(description=...)` call sites stay
   developer-facing; the SPA maps `error.code` to its own keyed copy. (`i18n/README.md`
   says 122; the two should be reconciled once, and one of them deleted so the figure has
   a single home.)
5. **One message per concept, not one per surface.** Reuse an existing key before minting a
   new one; when two surfaces show the same words for the same thing they share the key, and
   the `qqq` names every surface that uses it ([#369](https://github.com/lgelauff/wiki-polis/pull/369)).
6. **A UI label is never shipped from the server as English.** Presentation constants that
   cross the API send a key or a stable identifier the SPA maps, never display text.
7. **Key convention:** `surface-subkey`, lowercase-hyphenated, grouped by the screen it
   belongs to. The name must not contradict its own text.

## The one-way door

**translatewiki freezes key names once translators begin.** Renaming a key after that costs
translators their work on it; deleting a translated message wastes work already done. Every
stage below exists to get the namespace right *before* that point, and no stage after the
freeze may rename or delete a key.

This is the only irreversible step in the plan. Treat reaching it as a decision, not a
milestone that arrives on its own.

## Work sequence

### 1. Close the server-English leak — small, unblocked

- `TAB_LABELS` in `services/conversation_workspace.py` ships five English tab labels to the
  SPA as `tab.label`, rendered raw on an otherwise fully wired page. All five already have
  exact-matching keys (`conv-tab-vote`, `-results`, `-arguments`, `-informed`,
  `-preliminary`); the SPA already receives `tab.key`.
- Audit the API surface for any other display text crossing it, per rule 6.

**Exit:** no user-visible English reaches the SPA from a Python constant, and rule 6 has a
test that fails if one is reintroduced.

### 2. Wire the remaining surfaces, cheapest first

Order by existing key coverage, not by screen importance: components whose strings already
have keys are pure mapping and mint nothing, so they shrink the 551 without touching the
namespace.

- **Near-complete coverage** (mapping only): `participation-entry` (24/24),
  `admin-featured` (21/21), `admin-participants` (15/15), `admin-invitations` (12/12),
  `admin-moderation` (10/10), `admin-catalog` (24/26), `admin-statements` (22/24),
  `conversation-lane` (22/23), `intermediate-results` (2/2).
- **Partial coverage** (mapping plus some minting): `conversation-read-pages` (27/37),
  `identity-reveal` (13/15), `guidance-pages` (13/32), `argument-mapping` (11/15),
  `informed-voting` (10/11), `legacy-content-flag` (7/8), `admin-roles` (6/13).
- **Mostly new copy** (real authoring, do last): `admin-termination` (1/17),
  `admin-settings` (8/23), `content-flag-control` (2/11), `public-pages` (3/9),
  `statement-composer` (2/6), `legacy-shell` (2/7), `admin-routes` (0/6).

Cheapest-first is deliberate and cuts against intuition. Participant-facing screens matter
more to a reader, but wiring them first mints keys against a namespace still full of
unreconciled orphans, which is the expensive ordering.

Batch by surface, in reviewable PRs, following [#357](https://github.com/lgelauff/wiki-polis/pull/357):
prove each wiring non-vacuously — a test that passes identically before and after a change
has not tested it.

**Exit:** `grep` finds no user-visible literal English in `frontend/src`, and the key-existence
guard resolves call sites in every component.

### 3. Reconcile the orphans

- Re-run the unreferenced-key count. Every remaining key is deleted or justified in writing;
  "might be useful later" is not a justification, because the cost of keeping it is paid by
  translators in every language.
- The 20 surviving `flash-*` keys are settled by rule 4 and should go with the rest.
- Add a CI guard reporting keys with no call site, so the count cannot silently grow again.

**Exit:** every key in `en.json` is referenced by code, or listed with a reason it is not.

### 4. Freeze and onboard

- Freeze the namespace. Announce it in `i18n/README.md`.
- Confirm the repo licence satisfies translatewiki (GPL-3.0, satisfied) and file the support
  request using `i18n/translatewiki-group.yaml`. Flag the `protowiki` group id against the
  `wiki-polis` repository path explicitly, so TWN does not "correct" one to match the other.
- Enable the first non-English locale behind `ENABLED_LOCALES` and verify with a real
  translation, not a synthetic one: plural forms, `$1` ordering, and an RTL locale for `g.dir`.

**Exit:** a translator can complete a message on translatewiki and see it render in ProtoWiki.

## Open decisions

- **Which locale goes first, and who translates it.** Nothing downstream is designed until a
  real language with real plural rules and a real RTL question is in hand.
- **Whether rule 5 generalises.** Sharing one message across a button and a state label
  removes a translator's ability to split them where a language genuinely needs it. Settled
  for the vote labels; revisit if a translator asks.
- **The `?uselang=` cookie's lifetime and interaction with a future account preference.**
  Negotiation order is implemented; persistence policy is not decided.
- **Whether server-side error copy stays unkeyed forever.** Rule 4 is right while the SPA is
  the only consumer. A second consumer reopens it.

## Out of scope

Content translation of participant-authored statements and arguments; machine translation of
any kind; locale-specific clustering or results interpretation; and translating the admin
console ahead of the participant interface, which stage 2 orders by cost rather than
audience for the reasons given there.

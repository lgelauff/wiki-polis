# wiki-polis i18n messages

UI strings for wiki-polis, in the **translatewiki.net (TWN) "banana" JSON** format.
`en.json` is the **source** (English); `qqq.json` documents each message for translators;
`<code>.json` files are translations **delivered by TWN** — do not edit those by hand.

## For translators

Translate on **translatewiki.net**, not here. `qqq.json` gives the context for each message.
Placeholders `$1`, `$2`, … must be preserved. `{{PLURAL:$1|singular|plural}}` selects a form
by the number in `$1` — use the plural forms your language needs.

## For maintainers — adding or changing a UI string

1. Add a key to **`en.json`** (English text) and a one-line context note to **`qqq.json`**.
   Never leave a message in `en.json` without a `qqq.json` entry.
2. Use it:
   - **Templates:** `{{ msg('surface-key') }}` (params: `{{ msg('key', var) }}`).
   - **Python:** `flash(_('surface-key', var))` (the `_()` helper in `app.py`).
   - **Inline JS:** `wpI18n.msg('surface-key', var)` (messages are shipped to the browser via
     the island in `base.html`).
3. **Key convention:** `surface-subkey`, lowercase-hyphenated, grouped by page/area — e.g.
   `base-log-out`, `home-open-consultations`, `conversation-vote-agree`,
   `guidance-statement-heading`, `import-n-imported`.
4. **Plurals / counts:** `"import-n-imported": "$1 {{PLURAL:$1|statement|statements}} imported"`.
5. **Never** hardcode user-facing English in a template, `flash()`, or JS again.

## Coverage check

Append **`?uselang=qqx`** to any page: every externalised string renders as its key
(`(base-log-out)`). Any real English still visible = a string that still needs extracting.
A missing key renders loudly as `⧼key⧽`.

## Scope — the interface / content split

wiki-polis has **two language surfaces**, and only one is translated here.

### Interface (translate — this catalogue)

The UI chrome the platform itself renders: the same for every consultation, regardless of the
consultation's topic or language. Buttons, labels, headings, help/onboarding copy, table
headers, status badges, tab names, `aria-label`/`title`/`placeholder` attributes, screen-reader
announcements, and `flash()` notices. This is what TWN volunteers translate.

Where it lives, and how it's externalised:

| Interface source | Mechanism | Status |
|---|---|---|
| Template literal text | `{{ msg('key') }}` | ✅ all 19 templates |
| Template attrs (aria/title/placeholder) | `{{ msg('key') }}` | ✅ |
| Inline JS UI strings | `wpI18n.msg('key')` (island) | ✅ |
| Python `flash()` messages | `flash(_('key'), 'cat')` | ✅ 61 done |
| Python display labels in data structures | per-request localizers (see below) | ✅ done |

**Interpolating content into an interface frame is still interface.** A message like
`"$1 — join consultation"` is translated; the `$1` value passed in (a consultation title, a
pseudonym, a statement) is *content* and is **not** translated — it's substituted verbatim and
autoescaped. So `msg('home-card-join-aria', c.title)` is correct: translatable frame, literal
value.

### Content (never translate — always renders as `{{ data }}`)

Participant- and organizer-authored material, in the consultation's own `Conversation.language`.
Auditied clean — none of these is wrapped in `msg()`:

- `conversation.title`, `conversation.intro_text`, `conversation.outro_text`
- statement text (`item.text`, `s.text`, `stmt.text`, `txt`)
- argument bodies (`arg.body`), `r.statement_text`
- pseudonyms (`participation.pseudonym`, `part.pseudonym`), Wikimedia usernames
- derived-statement provenance data (TIDs, similarity scores)

Also left as data by design: **enum/config identifiers** shown verbatim (`public`,
`invite_only`, `demo`, phase-route keys), env-var names (`POLIS_DATABASE_URL`), and the Polis
web component (`particiapp-web-components.js`, vendored at deploy) which carries its own English
— a separate upstream i18n concern.

### Interface strings defined in Python data structures

A class of genuinely-*interface* strings is defined in **module-level Python data structures**
and reaches templates as `{{ x.label }}` / `{{ x.effect }}` / `{{ output.tooltip }}`. Because
those constants are evaluated once at import, `_()` can't wrap the literals in place — it would
resolve to the source locale forever. Instead they are localised **per request at the context
boundary**, keying off each item's stable `key`/`id`:

- **`PHASE_SEQUENCE`** — `phase-label-<key>` + `phase-effect-<key>`. Localised by `_localize_stage()`,
  applied in the admin_conversation render, `_transition_context()` (which also feeds
  `consequence.opens/closes`), and `_phase_stat_groups()`.
- **Phase routes** (`PHASE_ROUTES`) — `phase-route-<key>`, via `_localized_phase_routes()`.
- **Readiness preconditions** (`PHASE_TRANSITIONS`) — `precond-<id>`, localised in
  `_transition_context()`. (Precondition *notes* stay data — they're runtime counts.)
- **Output items** (`OUTPUT_DEFINITIONS`) — `output-<key>-{label,tooltip,pending,phase,method}` +
  `output-status-<value>`, localised inside `_output_items()` (a per-request builder).
- **Recommendations** — `rec-tier-<key>` + `rec-field-<key>`, via `_localized_recommendation_*()`.
- **Role bar** — `role-{global-admin,organizer,moderator}`, in `_conversation_role_label()`.
- **`_vote_label()`** values (`Agreed/Disagreed/Passed`) → `conv-p6-mine-*` in the p6-results
  "Yours" cell.

The stable `key`/`id`/`flag` fields are preserved through localisation, so all logic that
branches on them is unaffected. Keys were generated by introspecting the live structures.

## Enabling a locale

New locales arrive as `i18n/<code>.json` from TWN. Enable them for users by adding the code to
`ENABLED_LOCALES` (see `.env.example`). Until enabled, a locale is present in the repo but not
offered.

### Before enabling a non-English locale — two tracked follow-ups

1. **CLDR plural rules.** Server-side `{{PLURAL:}}` (and the client mirror in `static/i18n.js`)
   currently use the English rule (`n == 1` → singular, else plural). Languages with more than
   two plural forms (Arabic, Polish, Russian, …) need their CLDR rule wired into
   `i18n._plural_index` before their counts read correctly.
2. **RTL CSS audit.** `<html dir>` is already driven by `i18n.text_direction(locale)`, so RTL
   locales render right-to-left today — but `static/style.css` / `static/redesign.css` still use
   a handful of *physical* properties (`margin-left`, `text-align:left`, `left:`) that should be
   *logical* (`margin-inline-start`, `text-align:start`, `inset-inline-start`). Convert those and
   verify against a pseudo-RTL locale before offering an RTL language.

## Coverage guard (CI)

`tests/test_i18n.py` fails CI if a message in `en.json` has no `qqq.json` doc, if `qqq.json`
documents a key not in `en.json`, or if a `{{PLURAL:}}`/placeholder is malformed. Add both the
`en.json` value **and** the `qqq.json` line in the same change and the guard stays green.

# wiki-polis i18n messages

UI strings for wiki-polis, in the **translatewiki.net (TWN) "banana" JSON** format.
`en.json` is the **source** (English); `qqq.json` documents each message for translators;
`<code>.json` files are translations **delivered by TWN** — do not edit those by hand.

## Status — what is wired up today

The catalogue and the resolver are in place; **no surface reads them yet.**

| Piece | State |
|---|---|
| `en.json` + `qqq.json` (885 keys, 100% documented) | ✅ committed |
| `i18n.py` resolver (fallback, `$1`, `{{PLURAL:}}`, `qqx`, RTL direction) | ✅ committed |
| Per-request locale negotiation (`g.locale`, `g.dir`) | ✅ committed |
| `GET /api/v1/i18n/<locale>` — the catalogue as JSON | ✅ committed |
| React SPA reads it via `banana-i18n` | ⬜ next |
| Jinja templates wrapped in `msg()` | ⬜ after the SPA |
| Locales offered to users (`ENABLED_LOCALES`) | English only |

`ENABLED_LOCALES` defaults to `en`, so nothing here is user-visible yet. The keys are the
durable asset: they were authored against the Jinja UI but ~75% of them match strings the
React SPA renders today, so the same namespace serves both surfaces.

## Who consumes this

**The React SPA in `v2/frontend` is the primary consumer.** It is what users actually reach:
`SPA_DEFAULT_ENABLED` is on and the canonical routes serve the React shell. The SPA fetches
`/api/v1/i18n/<locale>` once and feeds the map to `banana-i18n`, which parses this exact format
and brings real CLDR plural rules.

**The Jinja templates in `v2/templates` are the `?spa_only=0` fallback.** They still render
every page, and are still reachable by appending `?spa_only=0` (or holding the `spa_only=0`
cookie), but they are not the default path for any route the SPA covers. They have their own
`msg()` handle in the Jinja context and no wrapped strings yet; wrapping them is a later phase
and may not happen at all if the legacy deck is retired.

Both surfaces read the same `en.json`. That is the point of freezing the key namespace before
TWN onboarding: renaming keys after translators start costs them their work.

## For translators

Translate on **translatewiki.net**, not here. `qqq.json` gives the context for each message.
Placeholders `$1`, `$2`, … must be preserved. `{{PLURAL:$1|singular|plural}}` selects a form
by the number in `$1` — use the plural forms your language needs.

## For maintainers — adding or changing a UI string

1. **Reuse before you mint.** Search `en.json` for the English text first. A large fraction of
   the SPA's copy already has a key here under a name derived from the Jinja page it came
   from. Reusing it keeps one message for translators instead of two.
2. Add a key to **`en.json`** (English text) and a one-line context note to **`qqq.json`**.
   Never leave a message in `en.json` without a `qqq.json` entry — CI fails on it.
3. Use it:
   - **React (primary):** through the `banana-i18n` store loaded from
     `GET /api/v1/i18n/<locale>`.
   - **Jinja (fallback):** `{{ msg('surface-key') }}` (params: `{{ msg('key', var) }}`).
     The handle is injected by the context processor in `create_app()`.
   - **Python:** there is no `_()` helper on `main` yet. Server-rendered `flash()` copy and
     API error strings are wrapped in a later phase.
4. **Key convention:** `surface-subkey`, lowercase-hyphenated, grouped by page/area — e.g.
   `base-log-out`, `home-open-consultations`, `conversation-vote-agree`,
   `guidance-statement-heading`, `import-n-imported`.
5. **Plurals / counts:** `"import-n-imported": "$1 {{PLURAL:$1|statement|statements}} imported"`.
6. **Never** hardcode user-facing English in a component, template, `flash()`, or API error
   payload once that surface has been converted.

## The endpoint

```
GET /api/v1/i18n/<locale>          -> {"base-log-out": "Log out", ...}
GET /api/v1/i18n/<locale>?v=<sha>  -> same, Cache-Control: public, max-age=604800
```

A flat `{key: text}` map — **not** the `{"data": ...}` envelope the rest of API v1 uses,
because that flat map is what `banana-i18n` takes as a message store. English-filled, so a
partly translated locale is still complete. `@metadata` is excluded. An unknown locale falls
back to English rather than 404ing, mirroring the resolver's `locale -> en -> ⧼key⧽` chain.
`qqx` returns `(key)` for every key.

Pin `?v=<gitVersion>` (the SPA already has `gitVersion` from `GET /api/v1/session`) to get the
cacheable response; the same `?v=<git-sha>` contract the static assets use, so a deploy busts
the cache. Unversioned requests are `no-store` on purpose — a client that did not pin a build
must not be handed a week-old catalogue.

The catalogue is deliberately **not** inlined into HTML responses. Doing so costs ~61 KB on
every page load and cannot be cached.

## Locale negotiation

`create_app()` resolves the UI locale once per request, before route dispatch:

`?uselang=` → `uselang` cookie → `Accept-Language` best match → `DEFAULT_LOCALE`

Only codes in `ENABLED_LOCALES` are eligible. An explicit `?uselang=` choice is persisted as a
one-year `SameSite=Lax` cookie. The result lands on `g.locale` and `g.dir`.

`qqx` bypasses the enabled list so the coverage check below always works.

## Coverage check

Append **`?uselang=qqx`** to any page: every externalised string renders as its key
(`(base-log-out)`). Any real English still visible = a string that still needs extracting.
A missing key renders loudly as `⧼key⧽`. Today every page is entirely un-externalised, so this
is a tool for the conversion phases rather than a passing check.

## Scope — the interface / content split

wiki-polis has **two language surfaces**, and only one is translated here.

### Interface (translate — this catalogue)

The UI chrome the platform itself renders: the same for every consultation, regardless of the
consultation's topic or language. Buttons, labels, headings, help/onboarding copy, table
headers, status badges, tab names, `aria-label`/`title`/`placeholder` attributes, screen-reader
announcements, and `flash()` notices. This is what TWN volunteers translate.

**Interpolating content into an interface frame is still interface.** A message like
`"$1 — join consultation"` is translated; the `$1` value passed in (a consultation title, a
pseudonym, a statement) is *content* and is **not** translated — it's substituted verbatim and
autoescaped. So `msg('home-card-join-aria', c.title)` is correct: translatable frame, literal
value.

### Content (never translate — always renders as `{{ data }}`)

Participant- and organizer-authored material, in the consultation's own `Conversation.language`.
Audited clean — none of these is wrapped in `msg()`:

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
(`PHASE_SEQUENCE`, `PHASE_ROUTES`, `PHASE_TRANSITIONS`, `OUTPUT_DEFINITIONS`, the recommendation
tiers) and reaches the UI as `label` / `effect` / `tooltip` fields. Because those constants are
evaluated once at import, `_()` cannot wrap the literals in place — it would resolve to the
source locale forever. They have to be localised **per request at the context boundary**,
keying off each item's stable `key`/`id`, so that all logic branching on those identifiers is
unaffected.

Keys for this are already in the catalogue — `phase-label-<key>`, `phase-effect-<key>`,
`phase-route-<key>`, `precond-<id>`, `output-<key>-{label,tooltip,pending,phase,method}`,
`output-status-<value>`, `rec-tier-<key>`, `rec-field-<key>`, `role-{global-admin,organizer,
moderator}` — generated by introspecting the live structures. **The localizers themselves are
not written yet.** They belong wherever these structures are consumed, which since the service
extraction is largely `v2/services/`, not `app.py`.

These keys are built by concatenation, so the CI key-existence guard cannot verify them
statically; it skips runtime-assembled keys by design.

## Enabling a locale

New locales arrive as `i18n/<code>.json` from TWN. Enable them for users by adding the code to
`ENABLED_LOCALES` (see `.env.example`). Until enabled, a locale is present in the repo but not
offered.

### Before enabling a non-English locale — two tracked follow-ups

1. **CLDR plural rules.** Server-side `{{PLURAL:}}` currently uses the English rule (`n == 1` →
   singular, else plural). Languages with more than two plural forms (Arabic, Polish, Russian,
   …) need their CLDR rule wired into `i18n._plural_index` before their counts read correctly.
   (The client side gets this for free: `banana-i18n` applies CLDR rules itself.)
2. **RTL CSS audit.** `<html dir>` is already driven by `i18n.text_direction(locale)`, so RTL
   locales render right-to-left today — but `static/style.css` / `static/redesign.css` still use
   a handful of *physical* properties (`margin-left`, `text-align:left`, `left:`) that should be
   *logical* (`margin-inline-start`, `text-align:start`, `inset-inline-start`). Convert those and
   verify against a pseudo-RTL locale before offering an RTL language.

## Coverage guards (CI)

`tests/test_i18n.py` fails CI if:

- a message in `en.json` has no `qqq.json` doc;
- `qqq.json` documents a key not in `en.json`;
- a `{{PLURAL:}}` or placeholder is malformed;
- **a key referenced in code does not exist in `en.json`** — a typo would otherwise ship and
  render as `⧼key⧽` at runtime. The scan reads `msg('key')` and `_('key')` literals across
  `v2/*.py`, `v2/api/`, `v2/services/` and `v2/templates/`; keys assembled at runtime are
  skipped, since a static scan cannot resolve them.

Add both the `en.json` value **and** the `qqq.json` line in the same change and the guards
stay green.

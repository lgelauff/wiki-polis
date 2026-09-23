# Proto i18n messages

UI strings for Proto, in the **translatewiki.net (TWN) "banana" JSON** format.
`en.json` is the **source** (English); `qqq.json` documents each message for translators;
`<code>.json` files are translations **delivered by TWN** — do not edit those by hand. The one
exception is `nl.json`, seeded here before onboarding and handed over at the first TWN export
(see [`../plan_i18n.md`](../plan_i18n.md), stage 3).

## Status — what is wired up today

The catalogue and the resolver are in place, and **the participant interface reads them
throughout** (stage 2 of [`../plan_i18n.md`](../plan_i18n.md), done 2026-09-14): the shared
frame and landing page, the consultation list, the join screen, the conversation workspace,
the arguments tab and flag form, informed voting, intermediate and preliminary results, the
final report, the About page, the public moderation log, the output pages and the
identity-reveal page. The admin lifecycle console is wired too.

Still English, on purpose, and listed with reasons in
[#399](https://github.com/lgelauff/wiki-polis/issues/399): the two help pages
(`guidance-*`, pending an English review), the rest of the admin console (stage 5) and server
error messages ([#397](https://github.com/lgelauff/wiki-polis/issues/397)).

| Piece | State |
|---|---|
| `en.json` + `qqq.json` (950 keys, 100% documented; 572 offered to translators, 378 held back) | ✅ committed |
| `i18n.py` resolver (fallback, `$1`, `{{PLURAL:}}`, `qqx`, RTL direction) | ✅ committed |
| Per-request locale negotiation (`g.locale`, `g.dir`) | ✅ committed |
| `GET /api/v1/i18n/<locale>` — the catalogue as JSON | ✅ committed |
| React SPA reads it via `banana-i18n` | ✅ participant interface; 🟡 help pages and admin console (see above) |
| Locales offered to users (`ENABLED_LOCALES`) | English and Dutch (`nl.json`, 534 keys) |

`ENABLED_LOCALES` defaults to `en,nl` when unset (`app.py`), so the language switcher is visible
and Dutch is live wherever the variable is left alone. The keys are the durable asset: they were authored against the Jinja UI, which has since been deleted, but
**562 of the SPA's 785 distinct strings (72%) already have an equivalent here** — 495 exact
matches plus 67 that JSX splits around inline markup. So wiring the SPA is mostly mapping
existing keys, not authoring a second catalogue.

## Who consumes this

**The React SPA in `v2/frontend` is the only consumer.** The Jinja frontend these messages
were originally written against was deleted in #351 — there is no second surface, no
`?spa_only=0` fallback, and no Jinja `msg()` handle. The SPA fetches `/api/v1/i18n/<locale>`
once and feeds the map to `banana-i18n`, which parses this exact format and brings real CLDR
plural rules.

Freeze the key namespace before TWN onboarding: renaming keys after translators start costs
them their work. The sequence for getting there — and the reconciliation of the 551 keys no
call site references, most of which an unwired component still needs — is in
[`../plan_i18n.md`](../plan_i18n.md). This file is the status; that one is the plan.

**Server-side copy is deliberately not keyed.** 122 user-visible English strings live in
`error_response(...)` and `abort(description=...)`. The SPA maps `error.code` to its own copy
rather than rendering the server's `message`, so those strings stay developer-facing.

## For translators

Translate on **translatewiki.net**, not here. `qqq.json` gives the context for each message.
Placeholders `$1`, `$2`, … must be preserved, and no others added. `{{PLURAL:$1|singular|plural}}`
selects a form by the number in `$1` — use the plural forms your language needs, in CLDR's
category order (zero, one, two, few, many, other), writing only the categories your language
has: Russian is `{{PLURAL:$1|one|few|many|other}}`, Arabic
`{{PLURAL:$1|zero|one|two|few|many|other}}`. If you give fewer forms, the last one is used for
the rest. A form for one exact number, like `0=no votes`, may be added anywhere; it does not
take the place of a category.

A translation that breaks these rules is not shown; English is shown in its place:

- Use only the tags and attributes the English uses. Leaving a tag out, or moving it, is fine —
  except a link: where the English links, the translation links too, to the same place.
- No `<` in text: write it in words.
- In `{{PLURAL:$1|…}}`: no space before `$1`, no empty forms, and at least one form that is not
  an explicit number such as `1=…`. No stray `{`, `}` or `{{…}}` of other kinds.
- In a message that contains markup or `{{…}}`: no `$` except in a placeholder like `$1`, and no
  backslash.

Avoid HTML entities such as `&lt;` as well. They are not refused, but some places show them
exactly as typed.

## For maintainers — adding or changing a UI string

1. **Reuse before you mint.** Search `en.json` for the English text first. A large fraction of
   the SPA's copy already has a key here under a name derived from the page it came
   from. Reusing it keeps one message for translators instead of two.
2. Add a key to **`en.json`** (English text) and a one-line context note to **`qqq.json`**.
   Never leave a message in `en.json` without a `qqq.json` entry — CI fails on it.
3. Use it:
   - **React (primary):** through the `banana-i18n` store loaded from
     `GET /api/v1/i18n/<locale>`.
   - **Python:** there is no `_()` helper yet, and server-side copy is deliberately not
     keyed — the SPA maps `error.code` to its own message rather than rendering the API's
     English `message`.
4. **Key convention:** `surface-subkey`, lowercase-hyphenated, grouped by page/area — e.g.
   `base-log-out`, `home-open-consultations`, `conv-vote-agree`, `guidance-statement-heading`.
   (Every example here is a real key; check before copying one into a new message.)
5. **Plurals / counts:** `"reveal-tl-days": "$1 {{PLURAL:$1|day|days}}"`.
6. **Never** hardcode user-facing English in a component once that surface has been
   converted.
7. **Dates** go through `frontend/src/i18n/dates.ts`, which formats in the language the reader
   chose, not the browser's. `Intl.DateTimeFormat(undefined, …)` and month-name tables are
   the two ways a translated page ends up with English dates.

## The endpoint

```
GET /api/v1/i18n/<locale>          -> {"base-log-out": "Log out", ...}
GET /api/v1/i18n/<locale>?v=<sha>  -> same, Cache-Control: public, max-age=604800
```

A flat `{key: text}` map — **not** the `{"data": ...}` envelope the rest of API v1 uses,
because that flat map is what `banana-i18n` takes as a message store. English-filled, so a
partly translated locale is still complete. `@metadata` is excluded. An unknown locale falls
back to English rather than 404ing, mirroring the resolver's `locale -> en -> ⧼key⧽` chain.
`qqx` returns `(key)` for every key, or `(key: $1, $2)` for a message with parameters.

Pin `?v=<gitVersion>` (the SPA already has `gitVersion` from `GET /api/v1/session`) to get the
cacheable response; the same `?v=<git-sha>` contract the static assets use, so a deploy busts
the cache. Unversioned requests are `no-store` on purpose — a client that did not pin a build
must not be handed a week-old catalogue.

The catalogue is deliberately **not** inlined into HTML responses. Doing so costs ~61 KB on
every page load and cannot be cached.

## Locale negotiation

`create_app()` resolves the UI locale once per request, before route dispatch:

`?uselang=` → `uselang` cookie → `DEFAULT_LOCALE`

`ENABLED_LOCALES` says what the **language switcher offers**, not what `?uselang=` may reach.
Forcing any locale by URL renders the page in that language's direction with English filling
whatever is untranslated — the familiar MediaWiki behaviour, and how a translator or operator
previews a language, or an RTL layout, before switching it on. Only an **enabled** locale is
persisted as a one-year `SameSite=Lax` cookie, so a forced preview is not sticky, and a
remembered locale is dropped once it stops being offered. The result lands on `g.locale` and `g.dir`, and is stamped
onto the `<html>` tag of the SPA shell along with the few messages that render before the
catalogue loads.

**There is deliberately no `Accept-Language` step.** The SPA has to reach the same locale as
the server — it chooses which catalogue to fetch — and it cannot match a browser header
against `ENABLED_LOCALES`, which it does not know. A step only one end can perform produces a
document that says one language while its content is another. Readers choose instead, through
the language switcher in the site header; `session.locales` tells the SPA what to offer and
which locale this request resolved to, and `MessageProvider` clamps the requested locale to
that list.

`qqx` bypasses the enabled list so the coverage check below always works.

## Coverage check

Append **`?uselang=qqx`** to any page: every externalised string renders as its key
(`(base-log-out)`). Any real English still visible = a string that still needs extracting.
A missing key renders loudly as `⧼key⧽`. Only the wired surfaces render as keys throughout
today; everywhere else is still un-externalised, so this remains a tool for the conversion
phases rather than a passing check.

`qqx` shows a message's parameters too, as MediaWiki does: `(key: a, b)`. So English passed
*into* a message — a link label, a phase name — is as visible as English written around one.

The same check runs in the frontend tests. `renderAsQqx()` and `untranslatedCopy()` in
`frontend/src/test/i18n.ts` render a surface under `qqx` and list any text or readable
attribute still carrying a word once message keys and fixture content are removed. A test
that asserts English cannot prove a surface is wired — the test catalogue is the real
`en.json`, so a literal and `msg()` of the same words render identically — and this one can.
It cannot see a *wrong* value in the right place (a swapped parameter, a server label used
instead of its identifier's message): those need an English test whose fixture differs from
the catalogue.

## Scope — the interface / content split

Proto has **two language surfaces**, and only one is translated here.

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
`ENABLED_LOCALES` (see `.env.example`); setting the variable replaces the `en,nl` default, so
list every locale to offer. Until enabled, a locale is present in the repo but not offered.

### Before enabling a non-English locale

1. **CLDR plural rules — done (#436).** `banana-i18n` in the browser takes its rules from
   `Intl.PluralRules`; the server has the same CLDR rules written out in `i18n._PLURAL_RULES`,
   and `tests/test_i18n.py` checks it picks the form banana picks. The table covers
   the languages likely to be enabled (among them fr, ru, uk, pl, ar, cy, ga, he, ja, zh);
   **a language not in it gets the English rule on the server**, so add it there first;
   `test_every_shipped_locale_has_a_plural_rule` fails when a `<code>.json` lands without one.
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
  `v2/*.py`, `v2/api/`, `v2/services/` and `v2/frontend/src/`; keys assembled at runtime are
  skipped, since a static scan cannot resolve them. **This guard is live**: it covers the
  keys the converted screens reference, so a typo'd key fails CI rather than shipping;
- a delivered translation would not be served (see *Markup in messages* below):
  `test_every_delivered_translation_passes_the_markup_check`;
- an English message uses markup outside the allowlist, or cannot be parsed:
  `test_source_messages_use_only_allowlisted_markup`.

`frontend/src/i18n/catalogue-parses.test.ts` fails CI if any message in any catalogue file
makes banana-i18n throw.

Add both the `en.json` value **and** the `qqq.json` line in the same change and the guards
stay green.

## Markup in messages

Messages with inline HTML are rendered as HTML, in the SPA and in the error pages' hint, so
markup is held to two rules.

Both are scanned against a small grammar in `i18n.py` (`_Scanner`), a strict subset of what
banana-i18n parses; the scan is linear in the message's length, so no input is slow.

**English** may use only `<strong>`, `<em>`, `<code>`, and `<a href>` to a same-site path, and
must fit the grammar. The allowlist is `_SOURCE_TAGS` / `_SOURCE_ATTRIBUTES` in
`tests/test_i18n.py`, and widening it widens what every translation may use. In the SPA,
banana-i18n escapes an `<a>` written in plain message text but not inside a `{{PLURAL:}}`
branch; SPA links are passed into the message as a parameter instead.

**A translation** is served only if it fits the grammar and uses only markup its English
already uses: the same tags with the same attributes and values, repeated or reordered as the
language needs, and no placeholder the English lacks. `i18n.load()` does not serve one that
fails — English is used for that message — nor any translation at all if `en.json` did not
load. A translation of a key English no longer has is set aside as stale and does not fail
CI; translatewiki drops it on its next export. The app logs both at startup.

**Changing English markup.** If a change removes or alters a tag or attribute in an existing
message, existing translations that still carry it will fail the check. Give the message a
new key instead: the old translations become stale, which CI accepts, and translators see a
new message. This is the MediaWiki convention for a change that invalidates translations.

### When a translatewiki export fails the check

The failing test names the file, the key, and why: where the text leaves the grammar, the tags
and attributes it added, or a placeholder it added or dropped.

1. Fix the message on translatewiki.net, or ask on its talk page; the next export carries the
   fix. Never hand-edit `<code>.json` — the next export overwrites it. (Dutch is the standing
   exception until onboarding; see the note at the top of this file.)
2. Merging the export in the meantime is safe for readers, because `i18n.load()` serves English
   for that one message. Merging does leave CI red until the fix arrives.

The group config (`translatewiki-group.yaml`) expects exports as pull requests. The check can
only stop a translation before it lands if `main` requires the CI checks to pass; until branch
protection is on, a failing export can still be merged or pushed. Tracked in #390.

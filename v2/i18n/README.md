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

## Scope

TWN translates the **interface chrome only**. Participant-authored **statements and arguments**
are content in the conversation's own language (`Conversation.language`) and are *not*
translated here. The Polis web component (`particiapp-web-components.js`, added at deploy from
the upstream particiapp project) carries its own English — its i18n is a separate upstream
concern.

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

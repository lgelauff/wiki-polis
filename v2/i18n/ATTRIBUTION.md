# Messages copied from other projects

Some of Proto's messages reuse text from MediaWiki and its components rather than new
wording (see "Reuse before you mint" in [README.md](README.md)). This file lists every one of
them, with its source and licence. Each is also marked in `qqq.json`, where its entry cites
the source message with `{{msg-mw|<key>}}` and points here; `tests/test_i18n.py` fails
if the two lists differ, or if a message's English here no longer matches `en.json`.

Proto is licensed under GPL-3.0 (see [`LICENSE`](../../LICENSE)). Every source below is
compatible with it: GPL-2.0-or-later may be used under GPL-3.0, and MIT permits reuse in a
GPL-3.0 work as long as its copyright and permission notice is kept, which is done under
[Licence notices](#licence-notices).

**Copied** says which languages' text is copied: `en` from the source's `en.json`, and `nl`
where `nl.json` holds the source's Dutch. "(lowercased)" means our text is the source's
with its first letter lowercased, because the element is a small inline control.

## Copied on purpose

Chosen from MediaWiki's catalogue to replace wording of our own.

| Our key | English | Source | Source key | Licence | Copied |
|---|---|---|---|---|---|
| `common-err-nologin` | `Please log in to be able to access this page or action.` | MediaWiki core | [`exception-nologin-text`](https://github.com/wikimedia/mediawiki/blob/master/languages/i18n/en.json) | GPL-2.0-or-later | en, nl |
| `errorpage-500-title` | `Something went wrong` | OOUI | [`ooui-dialog-process-error`](https://github.com/wikimedia/oojs-ui/blob/master/i18n/en.json) | MIT | en, nl |
| `base-dismiss` | `Close` | MediaWiki core (Codex messages) | [`cdx-message-dismiss-button-label`](https://github.com/wikimedia/mediawiki/blob/master/languages/i18n/codex/en.json) | GPL-2.0-or-later | en, nl |
| `base-skip-to-content` | `Jump to content` | Vector skin | [`vector-jumptocontent`](https://github.com/wikimedia/mediawiki-skins-Vector/blob/master/i18n/en.json) | GPL-2.0-or-later | en, nl |
| `common-loading` | `Loading…` | MobileFrontend | [`mobile-frontend-loading-message`](https://github.com/wikimedia/mediawiki-extensions-MobileFrontend/blob/master/i18n/en.json) | GPL-2.0-or-later | en, nl |
| `common-opens-in-new-tab` | `(opens in new window)` | MediaWiki core | [`newwindow`](https://github.com/wikimedia/mediawiki/blob/master/languages/i18n/en.json) | GPL-2.0-or-later | en, nl |
| `adminconv-countdown-days` | `$1 d` | MediaWiki core | [`days-abbrev`](https://github.com/wikimedia/mediawiki/blob/master/languages/i18n/datetime/en.json) | GPL-2.0-or-later | en |
| `adminconv-countdown-hours` | `$1 h` | MediaWiki core | [`hours-abbrev`](https://github.com/wikimedia/mediawiki/blob/master/languages/i18n/datetime/en.json) | GPL-2.0-or-later | en |
| `adminconv-countdown-minutes` | `$1 min` | MediaWiki core | [`minutes-abbrev`](https://github.com/wikimedia/mediawiki/blob/master/languages/i18n/datetime/en.json) | GPL-2.0-or-later | en |
| `conv-nav-prev` | `Previous` | MediaWiki core | [`watchlistlabels-onboarding-prev`](https://github.com/wikimedia/mediawiki/blob/master/languages/i18n/en.json) | GPL-2.0-or-later | en, nl |
| `conv-nav-next` | `Next` | MediaWiki core | [`watchlistlabels-onboarding-next`](https://github.com/wikimedia/mediawiki/blob/master/languages/i18n/en.json) | GPL-2.0-or-later | en, nl |

`adminconv-countdown-*` has no Dutch: the admin console is not translated into Dutch yet, and
MediaWiki core has Dutch only for `hours-abbrev` ("$1 u"). `days-abbrev` and
`minutes-abbrev` are `{{optional}}` in core, so most languages keep the English.

## Short labels that already matched

Our English was already the same word as MediaWiki's, in the same sense, so it counts as
copied text and is credited here too. Where MediaWiki has Dutch for the same message, ours
is MediaWiki's (lowercased where the English is), and other Dutch messages use the same words
for the same thing: "samenvouwen"/"uitvouwen", "zichtbaar maken", "Niet toegestaan".

| Our key | English | Source | Source key | Licence | Copied |
|---|---|---|---|---|---|
| `common-cancel` | `Cancel` | MediaWiki core | [`cancel`](https://github.com/wikimedia/mediawiki/blob/master/languages/i18n/en.json) | GPL-2.0-or-later | en, nl |
| `adminconv-edit` | `Edit` | MediaWiki core | [`edit`](https://github.com/wikimedia/mediawiki/blob/master/languages/i18n/en.json) | GPL-2.0-or-later | en |
| `stmts-save` | `Save` | MediaWiki core | [`saveprefs`](https://github.com/wikimedia/mediawiki/blob/master/languages/i18n/preferences/en.json) | GPL-2.0-or-later | en |
| `featured-arg-delete` | `delete` | MediaWiki core | [`delete`](https://github.com/wikimedia/mediawiki/blob/master/languages/i18n/en.json) | GPL-2.0-or-later | en (lowercased) |
| `featured-btn-confirm` | `confirm` | MediaWiki core | [`confirm`](https://github.com/wikimedia/mediawiki/blob/master/languages/i18n/en.json) | GPL-2.0-or-later | en (lowercased) |
| `conv-arg-hide` | `hide` | MediaWiki core | [`hide`](https://github.com/wikimedia/mediawiki/blob/master/languages/i18n/en.json) | GPL-2.0-or-later | en (lowercased), nl |
| `featured-arg-hide` | `hide` | MediaWiki core | [`hide`](https://github.com/wikimedia/mediawiki/blob/master/languages/i18n/en.json) | GPL-2.0-or-later | en (lowercased) |
| `stmts-hide` | `hide` | MediaWiki core | [`hide`](https://github.com/wikimedia/mediawiki/blob/master/languages/i18n/en.json) | GPL-2.0-or-later | en (lowercased) |
| `conv-arg-hidden` | `Hidden` | MediaWiki core | [`revdelete-radio-set`](https://github.com/wikimedia/mediawiki/blob/master/languages/i18n/en.json) | GPL-2.0-or-later | en, nl |
| `featured-arg-hidden` | `hidden` | MediaWiki core | [`revdelete-radio-set`](https://github.com/wikimedia/mediawiki/blob/master/languages/i18n/en.json) | GPL-2.0-or-later | en (lowercased) |
| `stmts-hidden-heading` | `Hidden` | MediaWiki core | [`revdelete-radio-set`](https://github.com/wikimedia/mediawiki/blob/master/languages/i18n/en.json) | GPL-2.0-or-later | en |
| `conv-arg-unhide` | `unhide` | Flow | [`flow-post-action-unhide-post`](https://github.com/wikimedia/mediawiki-extensions-Flow/blob/master/i18n/en.json) | GPL-2.0-or-later | en (lowercased), nl (lowercased) |
| `featured-arg-unhide` | `unhide` | Flow | [`flow-post-action-unhide-post`](https://github.com/wikimedia/mediawiki-extensions-Flow/blob/master/i18n/en.json) | GPL-2.0-or-later | en (lowercased) |
| `base-log-in` | `log in` | MediaWiki core | [`loginreqlink`](https://github.com/wikimedia/mediawiki/blob/master/languages/i18n/en.json) | GPL-2.0-or-later | en, nl |
| `base-log-out` | `log out` | MediaWiki core | [`logout`](https://github.com/wikimedia/mediawiki/blob/master/languages/i18n/en.json) | GPL-2.0-or-later | en (lowercased), nl (lowercased) |
| `conv-crumb-about` | `About` | MediaWiki core | [`about`](https://github.com/wikimedia/mediawiki/blob/master/languages/i18n/en.json) | GPL-2.0-or-later | en, nl |
| `conv-flag-reason-label` | `Reason` | MediaWiki core | [`block-reason`](https://github.com/wikimedia/mediawiki/blob/master/languages/i18n/en.json) | GPL-2.0-or-later | en, nl |
| `flags-th-reason` | `Reason` | MediaWiki core | [`blocklist-reason`](https://github.com/wikimedia/mediawiki/blob/master/languages/i18n/en.json) | GPL-2.0-or-later | en |
| `flags-th-target` | `Target` | MediaWiki core | [`blocklist-target`](https://github.com/wikimedia/mediawiki/blob/master/languages/i18n/en.json) | GPL-2.0-or-later | en |
| `conv-flag-cat-other` | `Other` | MediaWiki core | [`htmlform-selectorother-other`](https://github.com/wikimedia/mediawiki/blob/master/languages/i18n/en.json) | GPL-2.0-or-later | en, nl |
| `conv-flag-details-label` | `Details` | MediaWiki core | [`upload-form-label-infoform-title`](https://github.com/wikimedia/mediawiki/blob/master/languages/i18n/en.json) | GPL-2.0-or-later | en, nl |
| `conv-flag-send` | `Send` | MediaWiki core | [`emailsend`](https://github.com/wikimedia/mediawiki/blob/master/languages/i18n/en.json) | GPL-2.0-or-later | en, nl |
| `conv-vote-change` | `change` | MediaWiki core | [`protect_change`](https://github.com/wikimedia/mediawiki/blob/master/languages/i18n/en.json) | GPL-2.0-or-later | en, nl |
| `conv-results-heading` | `Results` | MediaWiki core | [`apisandbox-results`](https://github.com/wikimedia/mediawiki/blob/master/languages/i18n/en.json) | GPL-2.0-or-later | en, nl |
| `conv-results-quoted` | `"$1"` | MediaWiki core | [`quotation-marks`](https://github.com/wikimedia/mediawiki/blob/master/languages/i18n/en.json) | GPL-2.0-or-later | en, nl |
| `conv-orient-collapse` | `collapse` | MediaWiki core | [`collapsible-collapse`](https://github.com/wikimedia/mediawiki/blob/master/languages/i18n/en.json) | GPL-2.0-or-later | en (lowercased), nl (lowercased) |
| `adminconv-mode-advanced` | `Advanced` | MediaWiki core | [`searchprofile-advanced`](https://github.com/wikimedia/mediawiki/blob/master/languages/i18n/en.json) | GPL-2.0-or-later | en |
| `base-language-label` | `Language` | MediaWiki core | [`pagelang-language`](https://github.com/wikimedia/mediawiki/blob/master/languages/i18n/en.json) | GPL-2.0-or-later | en, nl |
| `errorpage-403-title` | `Not allowed` | MediaWiki core | [`specialpage-securitylevel-not-allowed-title`](https://github.com/wikimedia/mediawiki/blob/master/languages/i18n/en.json) | GPL-2.0-or-later | en, nl |
| `conv-of` | `$1 of $2` | MediaWiki core | [`watchlistlabels-onboarding-progress`](https://github.com/wikimedia/mediawiki/blob/master/languages/i18n/en.json) | GPL-2.0-or-later | en, nl |
| `about-stat-unknown` | `unknown` | MediaWiki core | [`mediastatistics-header-unknown`](https://github.com/wikimedia/mediawiki/blob/master/languages/i18n/en.json) | GPL-2.0-or-later | en (lowercased), nl (lowercased) |
| `accept-not-now` | `Not now` | VisualEditor | [`visualeditor-sourceswitch-popup-dismiss`](https://github.com/wikimedia/mediawiki-extensions-VisualEditor/blob/master/i18n/ve-mw/en.json) | MIT | en |

## Sources

| Source | Messages (English, Dutch) | Licence, as stated by the source |
|---|---|---|
| MediaWiki core | [`en.json`](https://github.com/wikimedia/mediawiki/blob/master/languages/i18n/en.json), [`nl.json`](https://github.com/wikimedia/mediawiki/blob/master/languages/i18n/nl.json); also [`datetime/`](https://github.com/wikimedia/mediawiki/tree/master/languages/i18n/datetime), [`preferences/`](https://github.com/wikimedia/mediawiki/tree/master/languages/i18n/preferences) | GPL-2.0-or-later ([`COPYING`](https://github.com/wikimedia/mediawiki/blob/master/COPYING)) |
| MediaWiki core, Codex messages | [`codex/en.json`](https://github.com/wikimedia/mediawiki/blob/master/languages/i18n/codex/en.json), [`codex/nl.json`](https://github.com/wikimedia/mediawiki/blob/master/languages/i18n/codex/nl.json) | GPL-2.0-or-later, as part of core ([`COPYING`](https://github.com/wikimedia/mediawiki/blob/master/COPYING)). Codex itself is GPL-2.0-or-later too ([`package.json`](https://github.com/wikimedia/codex/blob/main/package.json), [`LICENSE`](https://github.com/wikimedia/codex/blob/main/LICENSE)). |
| OOUI | [`i18n/en.json`](https://github.com/wikimedia/oojs-ui/blob/master/i18n/en.json), [`i18n/nl.json`](https://github.com/wikimedia/oojs-ui/blob/master/i18n/nl.json) | MIT ([`LICENSE-MIT`](https://github.com/wikimedia/oojs-ui/blob/master/LICENSE-MIT)) |
| Vector skin | [`i18n/en.json`](https://github.com/wikimedia/mediawiki-skins-Vector/blob/master/i18n/en.json), [`i18n/nl.json`](https://github.com/wikimedia/mediawiki-skins-Vector/blob/master/i18n/nl.json) | GPL-2.0-or-later ([`skin.json`](https://github.com/wikimedia/mediawiki-skins-Vector/blob/master/skin.json) `license-name`, [`COPYING`](https://github.com/wikimedia/mediawiki-skins-Vector/blob/master/COPYING)) |
| MobileFrontend extension | [`i18n/en.json`](https://github.com/wikimedia/mediawiki-extensions-MobileFrontend/blob/master/i18n/en.json), [`i18n/nl.json`](https://github.com/wikimedia/mediawiki-extensions-MobileFrontend/blob/master/i18n/nl.json) | GPL-2.0-or-later ([`extension.json`](https://github.com/wikimedia/mediawiki-extensions-MobileFrontend/blob/master/extension.json) `license-name`) |
| Flow extension | [`i18n/en.json`](https://github.com/wikimedia/mediawiki-extensions-Flow/blob/master/i18n/en.json), [`i18n/nl.json`](https://github.com/wikimedia/mediawiki-extensions-Flow/blob/master/i18n/nl.json) | GPL-2.0-or-later ([`extension.json`](https://github.com/wikimedia/mediawiki-extensions-Flow/blob/master/extension.json) `license-name`) |
| VisualEditor extension | [`i18n/ve-mw/en.json`](https://github.com/wikimedia/mediawiki-extensions-VisualEditor/blob/master/i18n/ve-mw/en.json) | MIT ([`extension.json`](https://github.com/wikimedia/mediawiki-extensions-VisualEditor/blob/master/extension.json) `license-name`, [`LICENSE.txt`](https://github.com/wikimedia/mediawiki-extensions-VisualEditor/blob/master/LICENSE.txt)) |

## Licence notices

### GPL-2.0-or-later

MediaWiki core (including its Codex messages), the Vector skin, and the MobileFrontend and
Flow extensions are licensed under the GNU General Public License, version 2 or (at your
option) any later version. Proto uses the copied text under version 3, the licence of the
rest of this repository; its full text is in [`LICENSE`](../../LICENSE). Copyright is held by
the contributors to each project, as listed in its history and, for MediaWiki core, its
[`CREDITS`](https://github.com/wikimedia/mediawiki/blob/master/CREDITS) file.

### OOUI (MIT)

Applies to `errorpage-500-title`.

```
Copyright 2011-2025 OOUI Team and other contributors.

Permission is hereby granted, free of charge, to any person obtaining
a copy of this software and associated documentation files (the
"Software"), to deal in the Software without restriction, including
without limitation the rights to use, copy, modify, merge, publish,
distribute, sublicense, and/or sell copies of the Software, and to
permit persons to whom the Software is furnished to do so, subject to
the following conditions:

The above copyright notice and this permission notice shall be
included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
```

### VisualEditor (MIT)

Applies to `accept-not-now`.

```
Copyright (c) 2011-2020 VisualEditor Team and others under the terms
of The MIT License (MIT), as follows:

This software consists of voluntary contributions made by many
individuals (AUTHORS.txt) For exact contribution history, see the
revision history and logs, available at https://gerrit.wikimedia.org

Permission is hereby granted, free of charge, to any person obtaining
a copy of this software and associated documentation files (the
"Software"), to deal in the Software without restriction, including
without limitation the rights to use, copy, modify, merge, publish,
distribute, sublicense, and/or sell copies of the Software, and to
permit persons to whom the Software is furnished to do so, subject to
the following conditions:

The above copyright notice and this permission notice shall be
included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
```

## Translators

The Dutch copied from these projects, and the translations that translatewiki.net's
translation memory will offer for every message above, were written by volunteer translators
on [translatewiki.net](https://translatewiki.net/) and are published under each project's
licence. Their names are in the `@metadata` `authors` list at the top of each source's
`nl.json` (and of every other language's file), linked under [Sources](#sources). Thank you.

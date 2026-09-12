# translatewiki.net support request — draft

Post on <https://translatewiki.net/wiki/Support>. Not read by the application; kept here so
the request and the group config it references stay together. Delete once the group exists.

---

**Subject:** New project request: ProtoWiki (Wikimedia deliberation tool, GPL-3.0)

Hello,

I would like to request a new message group for **ProtoWiki**, a deliberation tool built for
the Wikimedia community and running on Toolforge. It helps editors constructively prepare a
complex decision, building on Polis with its own frontend.

**Repository:** <https://github.com/lgelauff/wiki-polis> (public)
**Licence:** GPL-3.0
**Source language:** English
**Format:** MediaWiki-style JSON ("banana"), which is what the app's resolver already parses
**Messages:** 872 keys, each with a `qqq.json` documentation entry (100% coverage)
— 86 use `$1`-style parameters, 19 use `{{PLURAL:}}`, and 30 contain inline HTML.

A draft group configuration is in the repository at
`v2/i18n/translatewiki-group.yaml`, with source/target patterns, the validators I believe
apply (BraceBalance, MediaWikiPlural, Printf), and a `FlatPluralInsertablesSuggester`. Please
treat it as a starting point rather than a finished config.

**One request about timing.** I would like the group **configured but not yet announced to
translators.** The catalogue is complete and documented, but a final reconciliation pass is
still outstanding: an earlier version of the interface was removed, and some messages no
longer have a rendering surface. I do not want volunteers spending time on messages that
render nowhere, or on keys I may still delete. I will follow up when it is ready to open.

**Three questions.**

1. **Key deletion before launch.** I expect to delete some keys during the reconciliation
   described above, before any translator sees the group. Is that free if it happens before
   the group opens, and is there anything I should do differently to avoid disrupting your
   tooling?

2. **Seeding an existing translation.** I need Dutch on a short deadline — sooner than I can
   reasonably ask this request to be processed — so I am authoring `nl.json` in the
   repository directly, in the same format. Can that file be imported as the starting point
   for Dutch when the group is set up, so the existing work is preserved and translators
   continue from it rather than starting over?

3. **Group id vs repository name.** The group id in the draft config is `protowiki` (the
   product name), while the repository is still called `wiki-polis` and the file paths
   therefore contain `wiki-polis`. This divergence is deliberate — the product was renamed and
   the repository rename is pending — so please do not "correct" one to match the other. I
   understand the group id is effectively frozen once translators start, whereas the
   repository can still be renamed.

Happy to provide anything else that would help, and glad to adjust the config to your
conventions.

Thanks very much,
Lodewijk

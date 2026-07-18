> **⚠️ Not fact-checked by this project. Did not inform wiki-polis / ProtoWiki's design.**
> This document reproduces an external research dossier about **All Our Ideas (AOI)**, an
> earlier and unrelated Wikimedia experiment in community deliberation tooling
> (2011, then piloted again in 2014). It was compiled independently by a third party
> ("Hermes Agent," for Andrew Lih) and is absorbed here **purely as historical context /
> prior art** — a precedent for "Wikimedia tries a third-party deliberation/prioritization
> tool," not as a source that shaped any decision in this repository. wiki-polis was not
> designed with knowledge of this dossier, and no claim below has been independently
> verified against primary sources by this project. Treat it as background reading on how
> a structurally similar effort played out, not as a reference to cite.

---

# Wikimedia's Use of All Our Ideas (AOI) — Comprehensive Research Dossier

> Research compiled July 14, 2026 by Hermes Agent for Andrew Lih

## Executive Summary

**All Our Ideas (AOI)** is an open-source pairwise wiki survey platform developed at Princeton University by **Matthew J. Salganik & Karen E.C. Levy**. Wikimedia used it in two phases:

1. **December 2011** — Fundraiser banner challenge (crowdsourcing new banner ideas)
2. **December 2014** — Pilot product survey of English & Spanish Wikipedia communities to prioritize tools/gadgets for improvement

The platform presents users with random pairs of ideas and asks them to choose one, then uses statistical modeling to produce a ranked list from all pairwise comparisons.

### Why It Was Chosen

The WMF reviewed five candidate systems (AOI, Consider It, Deliberatorium, IdeaScale, Synapp) against criteria including multi-language support, open-source licensing, ability to rank ideas, robustness against gaming, and proven scaling. AOI was selected as a pilot.

### What Happened

The December 2014 survey ran for two weeks on English and Spanish Wikipedias, attracting thousands of responses. The top English result was Citation Bot (score: 81), and top Spanish result was Corrector ortográfico/Spell Checker (score: 69). Between October 2015 and early 2016, the newly-formed Community Tech team worked through the top 10 results from each survey, completing fixes for Citation Bot, HotCat, FlickrFree, RevisionJumper, and others. However, the AOI process was superseded by the Community Wishlist Survey launched in November 2015, which became the permanent community input mechanism.

### Why It Was Dismissed

Five key factors:

1. **Always a pilot** — The AOI survey was explicitly framed as a "pilot" — a bridge until a permanent cross-project process could be established
2. **Community Tech team formation** — The formation of the Community Tech team in mid-2015 created a natural opportunity to design a new, more wiki-native process (the Community Wishlist Survey)
3. **Overwhelmingly negative community feedback** — Users described it as "frankly idiotic," "torture," and a "never-ending series of comparisons"
4. **Technical limitations** — 140-character idea descriptions, no hyperlinks, inability to fix translations once entered, and confusing/possibly incorrect real-time statistics
5. **Cultural mismatch** — The AOI was an external third-party service, which conflicted with community values around on-wiki transparency, discussion, and consensus-building

### Overall Assessment

AOI succeeded as a lightweight data-collection instrument and yielded actionable results that Community Tech delivered on. It failed as a community engagement tool because its design philosophy (statistical robustness through pairwise comparison) clashed with Wikimedian expectations of transparency, deliberation, and a sense of completion. The experience directly informed the design of the Community Wishlist Survey, which addressed these shortcomings by being wiki-native, discussion-rich, and transparently scored.

---

## Survey Results

### English Wikipedia Top 10

| Rank | Tool | Score |
|------|------|-------|
| 1 | Citation Bot | 81 |
| 2 | Reflinks | 75 |
| 3 | CopyVios | 69 |
| 4 | Cite4Wiki | 69 |
| 5 | RevisionJumper | 67 |
| 6 | Checklinks | 65 |
| 7 | Page stats | 65 |
| 8 | Twinkle | 64 |
| 9 | Dab Solver | 63 |
| 10 | Syntax highlighter | 63 |

40 total ideas. 16,862+ votes cast.

### Spanish Wikipedia Top 10

| Rank | Tool | Score |
|------|------|-------|
| 1 | Corrector ortográfico / Spell Checker | 69 |
| 2 | HotCat | 66 |
| 3 | Twinkle | 62 |
| 4 | FlickrFree | 60 |
| 5 | Localizar imágenes | 60 |
| 6 | CopyVios | 60 |
| 7 | RevisionJumper | 57 |
| 8 | Navigation Popups | 56 |
| 9 | QuickIntersection | 54 |
| 10 | Reflinks | 54 |

---

## What Was Actually Delivered

Between October 2015 and March 2016, the Community Tech team delivered on several AOI survey requests:

| Request | Status |
|---------|--------|
| **Citation Bot** | Fixed — had been completely broken for 3 months; fixed gadget code, API, security fixes, simplified code |
| **HotCat** | Fixed on 100+ wikis |
| **FlickrFree** | Improved search results, fixed thumbnail display |
| **RevisionJumper** | Firefox bug resolved |
| **Dab Solver** | Maintainer access restored |
| Turnitin integration | In progress |
| Pageview stats tool | Backlogged |

---

## Constructive vs. Non-Constructive Feedback

### ✅ Constructive (Positive + Improvement-Focused)

| Source | Feedback |
|--------|----------|
| **WMF staff** (Whatamidoing, Rdicerb, Quiddity) | Defended pairwise comparison on voting-theory grounds; resistant to gaming |
| **WMF Analytics** | Results "well received"; could identify and filter gaming attempts |
| **Wikimedia-l** (2 posts + IRC/private) | Positive feedback through informal channels |
| **Erik Moeller** (2011) | "It's good to experiment with new tools instead of locking ourselves into MediaWiki's feature set" |
| **Noyster** | Provided systematic improvement suggestions: limit to 20, fixed list, comparable descriptions |
| **Rdicerb (WMF)** (post-survey) | Acknowledged limitations candidly: 140-char limit, no hyperlinks, translation difficulties. Created comprehensive list of issues for AOI team |

### ❌ Non-Constructive (Negative + Hostile)

| Source | Feedback |
|--------|----------|
| **NeilN** (power editor) | "Who chose this frankly idiotic way of gathering feedback? No way of prioritizing requests. No links to get more info about each tool. No indication of what would be improved for each tool. Just click, click, click." |
| **Fram** (power editor) | Statistical analysis showing data anomalies — early ideas had 1200–1400 completed contests vs 300–400 for later ones. "Yet another excuse-building effort" |
| **Technical 13** | Gaming vulnerability: "makes this type of survey entirely useless" |
| **Ca2james** | "Infinite clicking… not knowing whether an end actually exists" |
| **Ganímedes** (es.wp) | "It is a torture to do this survey" + poor translations |
| **NaBUru38** | "It would have been much easier if the poll was a sortable list" |
| **Noyster** | Criticized that more votes from one user drives their preferred tool's score toward 100%: "A strange way to run a survey!" |
| **Elitre** (2011) | "Will you please remind us why the heck you are using an external site for matters that belong to Meta?" |
| **Rogol Domedonfors** | "Either demonstrate success or admit failure. No more excuses, no more delays, no more vagueness." |
| **Didcot power station** | "This is a sham, and by that I mean that Community Tech is a conscious and deliberate deception, designed and implemented to give the impression that WMF takes community technical input seriously when in fact it has nothing but contempt for the volunteer population." |

---

## Who Was Favorable vs. Unfavorable

| Favorable | Unfavorable |
|-----------|-------------|
| WMF staff (insiders who designed/ran it) | Experienced Wikipedians / power editors |
| Academically-oriented participants | Non-English communities (poor translations) |
| IRC / private email respondents | Users expecting wiki-native features |
| Analytics team (loved the data) | Technically sophisticated skeptics |

**The divide:** WMF staff defended AOI on methodological grounds; volunteers judged it on user experience and cultural fit. The methodology was statistically sound — it just wasn't *wiki*.

---

## Key Text Extracts

> "Who chose this frankly idiotic way of gathering feedback? No way of prioritizing requests. No links to get more info about each tool. No indication of what would be improved for each tool. Just click, click, click."
> — **NeilN**, 4 Dec 2014

> "Technical limitations: Significant technical limitations in the system meant that descriptions were limited to 140 characters, without any external links. This meant that users were sometimes presented with choices that they did not recognize and could not easily get more information about."
> — **Product Surveys page** (WMF's own assessment)

> "We also completed work on long-tail small issues. Example: fixing the citation bot. #1 request from 2014 all our ideas survey; it had actually been completely broken for 3 months… The community was very happy about that."
> — **Kaldari**, Jan 2016 Quarterly Review

> "This is a sham, and by that I mean that Community Tech is a conscious and deliberate deception, designed and implemented to give the impression that WMF takes community technical input seriously when in fact it has nothing but contempt for the volunteer population."
> — **Didcot power station**, 17 Jun 2015

> "While preparations are being made for a cross-project technical request survey, the Community Tech team will begin working on the requests identified by the community as high priority in the All Our Ideas survey."
> — **AOI Process page** (the bridge statement)

> "It is a torture to do this survey."
> — **Ganímedes** (Spanish Wikipedia), 23 Dec 2014

---

## Timeline

| Date | Event |
|------|-------|
| **Dec 2011** | First AOI use: Wikimedia fundraiser banner challenge. Zack Exley announces on Diff blog |
| **Nov 12, 2014** | Product Surveys page created on Meta-Wiki by Rdicerb (WMF), outlining AOI pilot plan |
| **Dec 3–17, 2014** | AOI pilot survey runs on English Wikipedia. 40 ideas, 16,862+ votes |
| **Dec 4–22, 2014** | AOI pilot survey runs on Spanish Wikipedia |
| **Dec 2014 – Aug 2015** | Intense community discussion on Talk:Community Liaisons/Product Surveys. Overwhelmingly critical |
| **Mar 10, 2015** | Whatamidoing (WMF) adds survey update noting top results, technical limitations, methodology criticism |
| **May 20, 2015** | Salganik & Levy publish "Wiki Surveys: Open and Quantifiable Social Data Collection" in PLOS ONE |
| **Jun 3, 2015** | Whatamidoing references AOI survey in Community Tech project ideas discussion |
| **Sep 11, 2015** | Quiddity (WMF) adds final pointer update to Product Surveys page |
| **Oct 20, 2015** | Community Tech/All Our Ideas page created by DannyH (WMF) to track AOI follow-up work |
| **Nov 2015** | First Community Wishlist Survey launches, effectively replacing AOI |
| **Dec 2015 – Mar 2016** | Community Tech completes work on Citation Bot, HotCat (100+ wikis), FlickrFree, RevisionJumper, Dab Solver |
| **Jan 2016** | Quarterly review: Kaldari reports AOI survey follow-up to Lila Tretikov. Community "very happy" about Citation Bot fix |
| **Apr 15, 2016** | Last substantive edit to Community Tech/All Our Ideas page |
| **2023** | Global Data and Insights team still using AOI for Equity Landscape title voting (niche continued use) |
| **Jun 2024** | Minor/vandalism edits — page is historical |

---

## Phabricator Tasks

Phabricator tasks created as a result of the AOI survey:

| Task ID | Description |
|---------|-------------|
| T108412 | Fix or replace Citation Bot |
| T108422 | Add i18n support to Copyvio Detector |
| T108424 | Fix RevisionJumper Firefox bug |
| T108425 | Turn RevisionJumper into an extension |
| T108426 | Make Twinkle localizable to any wiki |
| T108628 | Related to AOI survey outcomes |
| T108630 | Related to AOI survey outcomes |
| T108631 | Improve FlickrFree search results |
| T108633 | Related to AOI survey outcomes |
| T108636 | Related to AOI survey outcomes |
| T108637 | Quick Intersection tool documentation |
| T109370 | Fix thumbnail display in FlickrFree |
| T109796 | Get Hovercards to feature parity with Navigation Pop-ups |
| T101246 | Syntax highlighter |
| T103285 | Fix HotCat/VE bug |
| T110124 | Add i18n support to Copyvio Detector |
| T110144 | Integrate Turnitin into Copyvio Detector |
| T110147 | Add page view statistics to page information pages |
| T110148 | Make Twinkle localizable to any wiki |
| T110149 | Fix HotCat on wikis where it is broken |
| T110156 | Add spell-checking option to LanguageTool WikiCheck |
| T110159 | Fix RevisionJumper Firefox bug |
| T110160 | Turn RevisionJumper into an extension |
| T110162 | Create documentation for Quick Intersection tool |
| T115681 | Related to AOI survey outcomes |
| T149635 | Related to AOI survey outcomes |
| T153063 | Related to AOI survey outcomes |

---

## Key Documentation URLs

### Primary Meta-Wiki Pages

| Page | Description |
|------|-------------|
| [Community Tech/All Our Ideas](https://meta.wikimedia.org/wiki/Community_Tech/All_Our_Ideas) | Work tracking — Completed, In Progress, Backlogged, Declined items |
| [Community Tech/All Our Ideas/Process](https://meta.wikimedia.org/wiki/Community_Tech/All_Our_Ideas/Process) | 4-step workflow: Selection, Investigation, Analysis, Development |
| [Community Liaisons/Product Surveys](https://meta.wikimedia.org/wiki/Community_Liaisons/Product_Surveys) | Methodology, 9 selection criteria, 5 candidate systems, FAQ, Legal |
| [Talk:Community Liaisons/Product Surveys](https://meta.wikimedia.org/wiki/Talk:Community_Liaisons/Product_Surveys) | **The motherlode of feedback (~40 comments)** |
| [Talk:Community Liaisons/Product Surveys/Ideas](https://meta.wikimedia.org/wiki/Talk:Community_Liaisons/Product_Surveys/Ideas) | Specific tool/gadget discussions |
| [Talk:Community Tech/Project ideas](https://meta.wikimedia.org/wiki/Talk:Community_Tech/Project_ideas) | Broad community frustration — includes "This is a sham" |
| [Quarterly Review Jan 2016](https://meta.wikimedia.org/wiki/Wikimedia_monthly_activities_meetings/Quarterly_reviews/Reading_and_Community_Tech,_January_2016) | Kaldari reports AOI follow-up outcomes |
| [Community Liaisons/Process ideas](https://meta.wikimedia.org/wiki/Community_Liaisons/Process_ideas) | Brainstorming: 27 process improvement ideas |
| [Community Tech/Pageview stats tool/Notes](https://meta.wikimedia.org/wiki/Community_Tech/Pageview_stats_tool/Notes) | Meeting notes from AOI-derived request |
| [Community Tech](https://meta.wikimedia.org/wiki/Community_Tech) | Main page — now marked "historical" |
| [Community Wishlist](https://meta.wikimedia.org/wiki/Community_Wishlist) | Current process that replaced AOI |
| [Global Data and Insights/Equity Landscape](https://meta.wikimedia.org/wiki/Global_Data_and_Insights/Movement_Data/Equity_Landscape/Pilot_%26_Consultation/Design_Considerations) | 2023: AOI still in niche use |

### External

| URL | Description |
|-----|-------------|
| [AOI English results](http://www.allourideas.org/wikimediagadgets/results) | Still live — Citation Bot #1 (81) |
| [AOI Spanish results](http://www.allourideas.org/wikimediaaccesorios/results?locale=es) | Still live — Spell Checker #1 (69) |
| [AOI Homepage](http://www.allourideas.org/) | 27,620 wiki surveys, 60.8M votes hosted |
| [Diff Blog (2011)](https://diff.wikimedia.org/2011/12/19/all-our-ideas-in-the-wikimedia-fundraiser/) | Zack Exley announces first AOI use |
| [AOI GitHub](https://github.com/allourideas) | Open-source Ruby on Rails platform |

### Academic

| Reference | Details |
|-----------|---------|
| [Salganik & Levy (2015)](https://doi.org/10.1371/journal.pone.0123483) | "Wiki Surveys: Open and Quantifiable Social Data Collection" — PLOS ONE |

---

## Reasons for Dismissal — Full Analysis

AOI was not abruptly "dismissed" but was designed as a pilot and naturally superseded by the Community Wishlist Survey. The transition happened through several reinforcing factors:

| Factor | Detail |
|--------|--------|
| **Always a pilot** | Explicitly framed as a "pilot" from the start: "Should this prove effective, the Foundation will launch a broad scale to ask all communities." A two-week test on two wikis, not a permanent process |
| **Community Tech team formation** | The Community Tech team was formed in mid-2015 as a direct response to the WMF "Call to Action" for better community input. The team needed its own process and designed the Community Wishlist Survey (launched November 2015), which rendered AOI redundant |
| **Community hostility to the interface** | Overwhelmingly negative feedback made it politically untenable to continue. Terms like "frankly idiotic," "torture," "sham," and "deception" appeared in on-wiki discussions |
| **Technical limitations** | 140-character limit, no hyperlinks, inability to fix translations post-launch, and questions about data reliability (Fram's statistical analysis showing anomalies) |
| **Cultural mismatch with wiki values** | Wikimedians expect transparency (you can see all votes), editability (you can fix mistakes), and discussion (you can talk about the choices). AOI's black-box algorithm and external hosting conflicted with these norms. Elitre's 2011 criticism — "why use an external site for matters that belong to Meta?" — was prescient |
| **Slow follow-through** | Survey closed Dec 2014. WMF didn't begin acting on results until Oct 2015 (~10 months later) due to staffing delays and reorganization. Community trust was eroded |
| **The Wishlist was better** | The Community Wishlist Survey addressed most of AOI's shortcomings: wiki-native, allowed detailed proposals with links, supported discussion on talk pages, used straightforward voting (support/oppose), and produced transparent results. The 2015 survey received 107 proposals with hundreds of participants |

---

## Bottom Line

AOI was a methodologically sound but culturally mismatched experiment. It succeeded as a lightweight data-collection instrument and produced concrete improvements (Citation Bot, HotCat, etc.), but failed as a community engagement tool. The experience directly informed the Community Wishlist Survey, which addressed nearly every AOI shortcoming by being wiki-native, discussion-rich, and transparently scored. The AOI results pages remain accessible online a decade later — a quiet monument to a brief, turbulent chapter in Wikimedia's quest to listen to its communities.

---

*Research completed July 14, 2026, by Hermes Agent for Andrew Lih. Absorbed into this repository as prior-art context — see the disclaimer at the top of this document.*

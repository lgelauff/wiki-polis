# Retro: enwiki's 2019 resysop RfC as a Proto-shaped consultation

> **Class: research (verified).** Written 2026-11-18 for the Proto design discussion.
> Every number below is derived from the wiki revision cited in §2 by the script in
> Appendix B; nothing is inferred from memory or taken from a secondary summary.
> **Status:** verified against the revisions cited. **Not a product spec** — it
> describes what one community did in wikitext, not what Proto should do.

## 1. Why this case

In October 2019 the English Wikipedia ran *Requests for comment/2019 Resysop
Criteria (2)*, the second part of a two-part RfC on restoring administrator
tools after a desysop. It matters here because the community **built Proto's
pattern by hand**: the proposer opened it with

> "This RfC will follow the endorsement of statements model, with users being
> able to put forward multiple proposals to be considered by the community."

Each of the 19 proposals carries its own *Users who endorse statement N* and
*Users who oppose statement N* lists. That gives an explicit participant ×
statement matrix — no inference from prose — which is exactly the artefact a
Proto consultation produces.

## 2. Provenance

| Item | Value |
|---|---|
| Page | `Wikipedia:Requests for comment/2019 Resysop Criteria (2)` (enwiki) |
| Opened | 6 October 2019, 00:18 UTC, by TonyBallioni |
| Individual closures | 4 November 2019, 19:42–00:12 UTC, by Cyberpower678 (statements 1–5, 7, 7.5) |
| Outcome markers added | 5 November 2019, 00:02 UTC, by Wugapodes (rev 924624736), edit summary "mark results from closures that cyberpower…" |
| Revision analysed | **924626190** (the revision at close, 328,001 bytes) |
| Current revision at time of writing | 1312940130 |
| Raw wikitext | `https://en.wikipedia.org/w/index.php?oldid=924626190&action=raw` |
| Fetched | 2026-11-18 |

Two independent outcome records exist and they do not cover the same statements:

- **Individual close boxes** (`{{archive-top|status=…}}`) on statements 1–5, 7
  and 7.5 only, each with the closer's rationale.
- **`{{aye}}`/`{{nay}}` markers** in the page's *Summary of Statements*, added
  the next day for all 18 numbered statements (7.5 is absent), plus four marked
  *Withdrawn* and one *Closed*.

Where both exist they agree. The outcome column in §4 uses the summary markers,
because they are the only outcome record for 11 of the statements.

## 3. Method, and what it deliberately does not do

1. Parse the revision's wikitext: statement headings, the proposal text, and the
   endorse/oppose lists under each.
2. Attribute a signature to a person by the first `[[User:…]]` (or
   `[[Special:Contributions/…]]`, or IP) link in each list item.
3. **Deduplicate** per (statement, list). This matters: 26 of the 465 raw
   signatures are repeats by the same person in the same list.
4. Support = unique endorsers ÷ (unique endorsers + unique opposers). It is a
   *ratio of stated positions*, not a vote share: it has no denominator of
   eligible participants.
5. Read outcomes from the close boxes and summary markers — never inferred.
6. **Not done:** no attempt to infer anyone's position from their prose, no
   sampling, no clustering result reported (an attempt at a two-cluster split of
   the 48 most active signers produced no defensible structure and is omitted
   rather than dressed up).

## 4. The 19 statements

Support is unique endorse ÷ (endorse + oppose). "Outcome" is the page's own
record. Wording here is a one-line gist; exact wording is in Appendix A.

| # | proposer | endorse | oppose | support | outcome | gist |
|---|---|---|---|---|---|---|
| 1 | TonyBallioni | 37 | 21 | 64% | **passed** | crat must be convinced the user intends to return to *activity* |
| 2 | Bradv | 26 | 21 | 55% | **not passed** | crat must be convinced the user *retains community trust* |
| 3 | Hasteur | 31 | 16 | 66% | **passed** | doubt about suitability → delay, crat chat, then consensus |
| 4 | Hasteur | 4 | 22 | 15% | not passed | state intended admin actions with the request |
| 5 | Pharaoh of the Wizards | 10 | 12 | 45% | not passed | no resysop after 5 years without a new RfA |
| 6 | GZWDer | 1 | 16 | 6% | *closed (SNOW)* | state intended frequency of admin actions |
| 7 | Amorymeltzer | 29 | 7 | 81% | **passed** | two years with no edits → new RfA; inactivity desysop needs one |
| 7.5 | DESiegel | 0 | 0 | — | *no outcome* | procedural note ("didn't seem to go anywhere") |
| 8 | Kusma | 7 | 14 | 33% | not passed | N months of 50 "non-stupid" edits proportional to absence |
| 9 | DESiegel | 4 | 17 | 19% | not passed | declare intended frequency of admin actions |
| 10 | Valereee | 1 | 2 | 33% | *withdrawn* | 50 edits/month for six months |
| 11 | Wugapodes | 6 | 15 | 29% | *withdrawn* | restore only via RfA unless resigned cleanly |
| 12 | Govindaharihari | 6 | 8 | 43% | not passed | minimal-edit gaming → community removal |
| 13 | Cyp | 4 | 11 | 27% | not passed | focus on recruiting admins, not restricting them |
| 14 | Valereee | 22 | 0 | 100% | **passed** | recognise the RfC result as a real problem to solve |
| 15 | JzG | 7 | 9 | 44% | not passed | no process without demonstrated evidence of the problem |
| 16 | Wugapodes | 17 | 18 | 49% | *spun out* | there should be a binding community desysop procedure |
| 17 | JFG | 1 | 9 | 10% | *withdrawn* | returning admins must demonstrate current need for the tools |
| 18 | Nosebagbear | 4 | 4 | 50% | not passed | net-supported proposals go to a workshop stage |

Totals: **75 unique signers, 465 raw signatures, 26 duplicates, median 5
positions per signer** (of 19 statements), maximum 16, and 49 signers with four
or more positions.

## 5. Findings

**F1. The pattern was invented locally.** Nineteen atomic proposals, each with
its own support list, in one page — the structure Proto would generate, written
by hand in wikitext.

**F2. Participation was thin per statement.** 75 signers between them recorded a
median of five positions out of nineteen. Support percentages here are therefore
ratios over a few dozen self-selected people, not measurements of a community.

**F3. Duplicates are not a rounding error.** Statement 1's oppose list carries
11 repeated signatures, statement 8's lists six. Raw counts overstate
participation by ~6%; any tool that tallies lists must dedupe by identity.

**F4. Eleven people appear on both sides of at least one statement** (four on
statement 1 alone, three on statement 11). In a page-of-lists model, "both
sides" is often one person changing their mind mid-month; the record cannot
distinguish that from error.

**F5. The sharpest finding: the closest call was about wording, not substance.**
Statements 1 and 2 are the same instruction — *a bureaucrat should be reasonably
convinced of X* — differing only in whether X is *intent to return to activity*
or *retains the trust of the community*. 37 people endorsed statement 1, 26
endorsed statement 2, and **24 endorsed both**; only 13 endorsed 1 alone and 2
endorsed 2 alone. Statement 1 passed at 64%, statement 2 failed at 55%. A policy
distinction of substance was produced by a handful of signatures separating two
wordings that most supporters treated as compatible — the closer of statement 1
noted "significant opposition … as being too subjective or too vague", and of
statement 3 "weak, but sufficient, consensus".

**F6. There was no mechanical threshold.** Highest failing support 55% (s2),
lowest passing 64% (s1); a two-thirds rule would have failed statement 1. The
record shows judgement applied to a ratio — never a rule: "weak, but sufficient"
(s3), "significant opposition" (s1). Any Proto feature that outputs a computed
verdict would be inventing a rule this community did not use.

**F7. Nobody could say whose judgement they trusted.** The subject of the RfC is
trust in returning administrators, and its mechanism asks bureaucrats to
exercise judgement — yet the only thing a participant could express was
agreement with *text*. There was no way to record "I trust X to weigh this
close", which is the signal the close actually needed.

## 6. The same model recurs

The "statement + endorsement list" pattern is not a one-off. Searching enwiki
(namespace 4) for `insource:"Users who endorse statement"` returns five pages,
and for `insource:"Statement #1 by"` fifteen:

| Page | Statements counted | Endorsement sections | Unique users |
|---|---|---|---|
| RfC/2019 Resysop Criteria (2) | 19 | 19 | 99 |
| RfC/Arbitration Committee Elections December 2020 | 65 | 74 | 114 |
| RfC/Arbitration Committee Elections December 2019 | 47 | 53 | 120 |
| RfC/Arbitration Committee Elections December 2018 | 5 | 6 | 68 |
| RfC/Arbitration Committee Elections December 2017 | 5 | 6 | 99 |
| RfC/2010 ArbCom election voting procedure | 4 | 28 | 146 |
| Centralized discussion/Macedonia/main articles | — | 4 | 44 |

So: an annual series of ArbCom-election RfCs (2017–2020) that decompose election
rules into separately endorsable statements, a 2010 precedent on the voting
procedure, and the 2010 Macedonia naming discussions. Counts are of headings, so
multi-part options (`#1a`, `#1b`, `#1c`) inflate the statement figure — the
endorsement-section count is the more honest measure of how many endorsable
units there were. The exact-phrase search also undercounts: pages that use
*Support/Oppose* per proposal, or *Option A/B/C*, are the same idea in other
words.

## 7. What this implies for Proto

- **Duplicate/overlap detection before a consultation opens.** The 1/2 pair is
  the case for it: "these two statements say the same thing — do you support the
  idea, or the wording?" would have collapsed an artefact that changed policy.
- **Per-statement result cards, deduplicated by identity**, rather than one
  bundled question whose close has to reconstruct agreement afterwards.
- **Report counts and ratios, not verdicts.** The community's own record shows
  judgement applied to numbers (F6). A tool that prints "passed" borrows
  authority it was not given.
- **Offer a trust signal that is not a vote** — the layer F7 shows missing:
  during discussion, "I'd trust X to weigh this close", revocable, listed
  plainly, never ranked or summed into an outcome. Its jobs: choose who drafts
  the close from people trusted across positions, and let readers find the
  arguments others found worth trusting.

## 8. Limitations

- Endorsement lists are self-selected and incomplete; several signers endorsed
  competing statements, and 11 appear on both sides of one statement.
- Four statements were withdrawn by their proposers and one closed as SNOW, so
  their support ratios are evidence of activity, not of preference.
- Only 7 of 19 statements have a closers' rationale; for the rest the summary
  marker is the only record, and it does not say why.
- The case shows what a statement consultation looked like in 2019 wikitext. It
  cannot show that Proto would have produced a better decision — only that the
  information needed for a better decision was, in part, already there.

## Appendix A — exact wording

Wording is quoted from each proposal's own `{{tqb|…}}` / `{{quote|…}}` where
present, otherwise from the proposal text, markup stripped. Statement 7's
operative text was written in the summary as an instruction rather than a quote;
it is reproduced from there.

1. *Before restoring the administrator flag a bureaucrat should be reasonably
   convinced that the user has returned to activity or intends to return to
   activity as an editor.*
2. *Before restoring the administrator flag a bureaucrat should be reasonably
   convinced that the user retains the trust of the community to serve as an
   administrator.*
3. *Should there be doubt concerning the suitability for restoration of Admin
   permissions, the restoration shall be delayed until sufficient discussion has
   occurred and a consensus established through a Crat Chat.*
4. *As part of the request for resysop, the returning administrator should
   indicate what actions they intend to do with the permissions. Bureaucrats
   shall be empowered to consider the assertion and any previous assertions.*
5. *Adminship will not be restored after 5 years for those who resigned without
   a new RfA (in addition to the 3 year inactivity rule).*
6. *Users requesting restoration of sysop flag after being desysopped for
   inactivity will be requested to state the frequency of admin actions which
   they intend to take if the tools are restored to them…*
7. *Over two years with no edits.* If an editor has had at least two years of
   uninterrupted inactivity between removal of the tools and the re-request,
   they must instead request through WP:RFA; after an inactivity desysop, one
   year of continued inactivity suffices.
8. *Any former admin who has been inactive for more than two years will be
   re-sysopped on request after a period of normal editing proportional to their
   length of inactivity. If N years have passed since desysopping, the former
   admin should edit for N months, making 50 "non-stupid" edits each month.*
9. *Users requesting restoration … will be requested to state the frequency of
   admin actions which they intend to take … If the stated anticipated level is
   not significant, or if the Bureaucrats do not find the statement credible in
   view of past history, they may decline the request.*
10. *Users requesting restoration … who have had fewer than 50 edits per year
    for each of the past three years will be required to make 50 edits per month
    for six months before resysopping.*
11. *Requests for restoration of administrator privileges should generally be
    made at requests for adminship. If an editor voluntarily resigned adminship,
    they may request restoration at WP:BN unless they resigned "under a cloud"…*
12. *Admins making clearly minimal edits to keep their advanced permissions …
    can be subject to a community discussion and removal of those permissions if
    such a consensus arises.*
13. *Instead of trying to find ways of restricting people from keeping the sysop
    bit, the focus should be on figuring out how to get more (competent) people
    to apply for and pass RfAs.*
14. *Given that non-admin users, including some of the community's most
    respected, voted 39-8 that our resysopping policy needs tightening, we
    recognize the RfC results represent an actual problem the community needs to
    find consensus to address.*
15. *Wikipedia should not be in the business of writing processes to avoid the
    stupid thing Bob did once. Any proposed solution must first require credible
    evidence of both a problem that it would have fixed, and the absence of any
    simpler or more efficient way of fixing that problem.*
16. *There should be a binding community desysop procedure.*
17. *Returning admins should demonstrate a current need for the tools.*
18. *Proposals that receive some form of net support in this RfC should be taken
    to a workshop/dedicated stage … unless they already possess clarity, don't
    contradict other proposals, and have a clear consensus for straight
    implementation.*

## Appendix B — reproduction

The numbers above come from revision 924626190. This reproduces §4 (Python 3,
only the standard library; `curl` or `urllib` for the fetch):

```python
import json, re, urllib.request
URL = ("https://en.wikipedia.org/w/api.php?action=parse&oldid=924626190"
       "&prop=wikitext&format=json&formatversion=2")
req = urllib.request.Request(URL, headers={"User-Agent": "wiki-polis research/1.0"})
w = json.loads(urllib.request.urlopen(req).read())["parse"]["wikitext"]

heads = [(m.start(), len(m.group(1)), m.group(2).strip())
         for m in re.finditer(r'^(={3,5})\s*(.+?)\s*\1\s*$', w, re.M)]

def users(block):
    out = []
    for line in block.splitlines():
        if not line.startswith('#'):
            continue
        m = re.search(r'\[\[(?:User|User talk):([^|\]]+)', line) or \
            re.search(r'\[\[Special:Contributions/([^|\]]+)', line)
        if m:
            out.append(m.group(1).strip())
    return out

for i, (pos, lvl, title) in enumerate(heads):
    m = re.match(r'Statement (\d+(?:\.\d+)?) by (.+)', title)
    if not m or lvl != 4:
        continue
    end = heads[i + 1][0] if i + 1 < len(heads) else len(w)
    seg = w[pos:end]
    def lst(kind):
        h = re.search(r'^=====\s*Users who ' + kind + r' statement '
                      + re.escape(m.group(1)) + r'\s*=====\s*$', w, re.M)
        if not h:
            return []
        nxt = re.search(r'^====', w[h.end():], re.M)
        return users(w[h.end():h.end() + (nxt.start() if nxt else len(w))])
    e, o = set(lst('endorse')), set(lst('oppose'))
    sup = f"{100*len(e)/(len(e)+len(o)):.0f}%" if (e or o) else "—"
    print(f"{m.group(1):>4} {len(e):>4} {len(o):>4} {sup:>5}  {m.group(2)[:30]}")
```

Mismatches between this table and §4 would indicate a parsing difference, not a
different corpus; the revision is fixed, so the numbers should be reproducible
exactly.

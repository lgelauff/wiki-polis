# polis_report: methodology

What the polis_report reports count, how they describe it, and why. It covers two settings with different
requirements (§1). §3 says which parts of a report can be built from which export, and what the report builder
implements today. Planned changes are marked **Planned**.

## 1. Scope: two settings

**External exports.** Analysis of conversations run elsewhere, from the files the platform publishes. Example:
an external partner's Poll A / Poll B pair, from pol.is's public report export plus each conversation's xid file.
- Only the files are known, not the platform's code or configuration, so every rule is stated in terms of what
  is visible in the files. For example, "a response by the statement's author at the second it was created", not
  "the response the platform adds".
- Results describe that export at its export time. The report records the time and the file hashes.

**Production (wiki-polis).** Reports on wiki-polis's own processes, which can inform decisions. On top of
everything that applies to external exports:
- **Reproducible.** The report records the exact code version (git hash), the config and input hashes, and the
  export times. The same inputs and code give byte-identical HTML and CSV.
- **Verified code.** Reports come from code that is tested and reviewed in the repository (pull request with
  tests and a PR check), not from one-off scripts. Where a rule depends on how the platform behaves, the
  methodology cites the code that behaviour was checked against, and production reports name the deployed
  version they were checked against.
- **Runnable from exports where possible.** Reports are built from exports, never from a live database
  connection. Production data reaches the analysis host only as a participant-id-only extract, run by the
  operator. §3 says which parts of a report can be built from which export, and what else the others need.

## 2. Reporting principles (both settings)

1. **Observed values only; no significance.** Reports give what was observed: counts, and rule-based descriptions
   of them. They run no significance tests and mark nothing as significant, and every report says so. These
   reports have too many moving parts for a test to carry a clear meaning yet. How firm a reading is, is given
   in people instead: how many responses would have to change for it to change ("3 responses changing from
   agree to disagree would change this label", §6). **Planned:** significance, designed in §11 so it can be added later.
2. **Never causal, never more certain than the numbers.** Reports say what was observed among these participants.
   They don't say why it happened, and they don't speak for a wider population. Each page and table states
   which participants its figures describe ("among the 34 matched participants") and gives the counts.
3. **Deterministic.** Every sentence is a fixed template filled from the data, chosen by a stated rule.
4. **Self-selected participants.** Counts describe the people who responded. Each page says so.
5. **Counts only, and exact.** The data is cleaned for privacy before it reaches the report. The report writes
   counts only: no xid or participant id is ever written. Every count is exact. The limits in §9 are about how
   much a number can carry, not about hiding anyone.
6. **Main text first, detail in fold-outs.** The main text gives counts and plain readings. Detail (for example how
   close a label is to the line) sits in fold-out sections. Nothing in a report is a claim about a wider
   population.
7. **Every response counts, unless excluded.** Each exclusion has a rule, a reason and a count, and the report
   lists them (§4). **Planned:** changes to the settings that decide what counts are logged with a reason, and
   the log is printed in every report it produced (§4).

**Wording review.** Every sentence a report can contain is a template in the code, so wording can only change in
the pull request that changes a template. That pull request is reviewed for four problems: implied cause, more
certainty than the test supports, speaking for people beyond these participants, and size words ("most", "many",
"strongly") without the counts next to them. A language model may assist that review; it is not part of the
method, and it never changes report text. There is no list of banned words.

## 3. What can be built from which export

Three kinds of input:
- **pol.is public export:** `comments.csv`, `votes.csv`, `participant-votes.csv`, `summary.csv`, from
  `/api/v3/reportExport/<report>/<file>.csv`. It has no `is-seed` and no `is-meta` column.
- **xid file:** `participant,xid`, one per conversation, downloaded by the conversation owner.
- **Production extract (wiki-polis):** participant-id-only CSVs from the Polis database, plus Polis's math
  record (`math_main`), extracted read-only by the operator:
  - statements with author, creation time, moderation, `is_seed` and `is_meta`;
  - the full response history and the current responses, in the database sign convention (agree = −1);
  - Polis's math record, including its groups.

  It contains no xids, by design.

| Report element | pol.is public export | + xid file | Production extract | Implemented in polis_report |
|---|---|---|---|---|
| Statements, moderation, creation time, author | yes | | yes | yes (pol.is format) |
| Responses with time; current response | yes | | yes | yes (pol.is format) |
| Automatic responses (author + creation time) | yes | | yes | excluded, total counted |
| Exclusions listed with rule, reason and count | yes | | yes | not yet (counts only) |
| Settings change log, checked by the builder | yes | | yes | **Planned** (its own pull request) |
| Automatic responses by value (pass / agree) | yes | | yes | not yet |
| Seed vs participant-written statement | no | | yes (`is_seed`) | not yet |
| Role questions | named by text in the config | | yes (`is_meta`) | by config text |
| Labels, PCA map | yes | | yes | yes (pol.is format) |
| Polis groups | yes, snapshot at export time | | yes, from the math record | yes (pol.is format) |
| Leiden groups | computed from responses | | computed from responses | **Planned** |
| Label sensitivity (responses that would change a label) | yes | | yes | in #563 |
| Minimum of 10 for percentages, bars, labels and groups (§9) | yes | | yes | in #563 |
| Detail in fold-outs | yes | | yes | not yet |
| Significance (§11) | yes (shifts need the xid file) | | yes (shifts need the xid file) | **Planned**; #563 still runs tests, to be removed |
| Linking participants across conversations | no | yes | no | yes (with xid files) |
| wiki-polis phases, arguments, featured statements | no | no | no | no |

The report builder reads the pol.is CSV format today. **Planned:** a reader for the production extract, so
production reports run from the same code.

The last row needs data from the wiki-polis side, which none of these exports covers. A production report that
uses it has to name its source and how it was extracted.

## 4. Which responses count: all, unless excluded

Every response counts. A response is left out only by a named exclusion, and each report has an "Excluded
responses" fold-out with one line per exclusion: the rule, the reason and how many responses it removed. Three
kinds exist:
- **Automatic responses:** a fixed rule, always applied (below).
- **Responses before a stated time (`since`):** optional, with a reason, e.g. "test responses before the session
  opened". The time comes from the event, not from the results. The report also says how many participants
  responded only before it. In production, test responses are better kept out at the source, in a separate test
  conversation.
- **A named participant's responses (`exclude_participants`):** optional, with a reason.

**Planned (its own pull request): change log.** The settings that decide what counts (exclusions, role questions,
statement pairs, thresholds and minimums) get a log next to them: date, setting, old → new, reason. Every report
prints the log in a fold-out. The builder fingerprints these settings, and refuses to run when they changed since
the last logged fingerprint without a new entry, or when an exclusion has no reason. For an external partner the
settings and log stay with their data, outside the repository.

- **Automatic responses.**
  - **Rule (both settings):** a response by a statement's author on that statement, at the second the statement
    was created, is treated as automatic and excluded. The rule is procedural: it is about *which response*, not
    *which person*. All other responses count, including those of statement authors and the conversation owner,
    who can also take part as ordinary participants.
  - **Reported as well as excluded.** Excluded responses are counted, so a reader can see what was left out and
    add it back. The line reconciles the report with Polis's own counts, e.g. "Automatic responses: 39 excluded
    (39 passes, 0 agrees). Polis's own counts include them." **Planned:** the split by value, and in production,
    where `is_seed` is available, by seed versus participant-written statement.
  - **What produces them,** as checked in code:
    - **Seed statements** (written by the moderator): the Polis server records a pass from the author, unless the
      author submitted a response (`lgelauff/polis` fork, `server/src/routes/comments.ts:507-513` and `:940-942`).
    - **Statements written by participants:** the Polis server adds nothing itself. The participant-facing layer
      sends an agree: Polis's classic participant interface (`client-participation/js/views/comment-form.js:257-258`)
      and Particiapi (`particiapi/models.py:759-760`, checked at commit `fb2a450`, 2025-10-23). Particiapi also
      blocks authors from responding to their own statements, so the author cannot confirm or change that agree.
    - wiki-polis's own data-model reference (`v2/ref_polis-data-model.md`) records the same two paths.
  - **External setting:** only the observable rule applies. The report does not assume which component produced
    the response. On the external partner's data all 39 statements are seed statements, and the rule removes exactly their
    39 automatic passes; no other responses by the authors exist there.
  - **Production setting:** the report must name the deployed version of the participant-facing code it was
    checked against, because that code decides whether participant-written statements carry an automatic agree.
- **Current response.** The latest row per participant and statement in the response history (`votes.csv`). Rows
  with equal timestamps keep file order, and the report counts them. Polis's participant-by-statement matrix
  (`participant-votes.csv`) is not used for responses: Polis builds it by id order with last-write-wins, so after
  changed responses it can differ from the latest response by time. The report counts those differences.
- **Sign convention.** In the pol.is export, agree = +1. In the Polis database, and so in the production extract,
  agree = −1. A reader for the production extract must convert, and must say so in the report.
- **Participants** are people with at least one counted response to an opinion statement.

## 5. Statements, including statements that change

- **Opinion statements and role questions.** Statements that ask about the participant ("I'm here today as…")
  are left out of opinion totals, labels, groups and the map, and reported separately as self-reported role
  answers.
  - In external exports they are named by text in the config (`meta`), ignoring spacing and quote style. Meta
    texts not found in a poll produce a warning in the report.
  - In production they are marked in the data (`is_meta`).
- **Moderation.** Rejected statements are left out. Unmoderated ones are left out unless `include_unmoderated`
  is set. The report gives both counts.
- **Statements added while the poll was open.** Someone who finished before a statement existed could not
  respond to it. For every opinion statement created after the first counted response, the report gives its
  creation time and how many participants had already given their last response. Every statement is reported
  with its own number of responses, never as a share of all participants.
- **The same statement in two polls.** Statements are matched by text, ignoring spacing and quote style, never by
  number. Conversations number the same texts differently (Poll B #0 = Poll A #2). The second poll is shown with
  the first poll's numbers.
- **Statements edited between polls** count as different statements unless the config pairs the two versions
  (`statement_pairs`). Statements in only one poll appear in that poll's report and are listed as not compared.
- **Display order.** Polis chooses the order in which each participant sees statements, and that order can
  differ between polls. The report states this; it cannot correct for it.

## 6. Labels

- A statement is labelled **≥70% agree**, **≥70% disagree** or **neither ≥70%**, counting agree + disagree only.
  The pass count is shown separately and is not in the denominator. The threshold is `label_share`.
- The label is written as the rule itself, not as "consensus". It is not Polis's group-informed consensus.
- **Pass in a label** counts as a non-answer: the label is about the position people took (§10).
- **Too few to label.** A statement with fewer than `min_total` (10) agree + disagree responses gets no label:
  "too few responses for a label", with its counts (§9).
- **Close to the line.** A fold-out gives how many responses would have to change for the label to change
  (e.g. "6 responses changing from disagree to agree would change this label"). That describes these responses;
  it is not a confidence interval, which would assume a sample from a wider population.
- **Pass count.** Each statement's pass count is shown next to its label, as observed. No test compares pass rates
  between statements (§11).

## 7. Opinion groups

- **Current:** Polis's own groups (its k-means clustering), shown only when at least
  `min_participants_for_groups` people took part. The interim value is **25**. Below it the report says "not
  computed" and gives the count.
  - Groups under `min_total` (10) members are merged into "Other", shown with its size.
  - The groups are a snapshot at export time, computed by Polis over all responses, including the responses this
    report excludes. The report labels them "groups as Polis computed them, including responses this report
    excludes", gives how many excluded responses that is, and names the Polis group of participants with only
    automatic responses.
  - Clustering treats pass as the middle between agree and disagree (§10).
- **Descriptive only.** Testing differences between groups formed from these same responses would be circular, so
  no test is applied. The "largest difference between groups" chart uses this report's own measure: the range
  across groups of (agree − disagree) / all responses, over the groups shown (10 or more members). It is named as such on the page.
- **Planned:** an indication of how confident a grouping is (for example, how stable group assignments stay
  when the analysis is repeated on resampled participants). The method needs research first; until then groups
  are shown without a confidence indicator.
- **Planned:** show k-means and Leiden community detection side by side, so readers see how much the grouping
  depends on the method. Replace the fixed minimum with a robustness measure: re-cluster on resampled
  participants, and show groups only when assignments stay stable above a stated threshold. Leiden needs an
  outside library, so it will be an optional dependency.

## 8. Before and after (two polls)

- **Same people only.** The comparison uses only participants whose xid appears in both conversations' xid
  files and who gave a counted response to an opinion statement in both. Each conversation has its own xid file.
  The production extract has no xids, so this comparison needs the xid files in both settings.
  - Comparing the two rooms' totals mixes change with who turned up. On the external partner's data, the agree share on #4
    among all participants fell from 26% to 15% of responses, but among the 34 matched people the number
    agreeing was 4 in both polls.
  - The report shows how the one-poll-only participants responded, but keeps them out of the comparison.
  - Each single-poll page lists where its labels differ from those of the matched group.
- **Movement in both directions, never only the net.**
  - Per statement: a table of each person's response in A against their response in B (agree / disagree / pass /
    no response).
  - Counts of movers toward agree and toward disagree, on the order agree · pass · disagree: for change, pass is
    the middle (§10). Agree → pass counts as a move toward disagree.
  - Direct agree↔disagree switches, reported separately.
- **Observed values only.** No test is run on the shifts. Each statement gets a reading chosen by rule from its
  counts:
  - no movers: "No observed movement";
  - otherwise: the counts in both directions, e.g. "5 moved toward agree, 3 toward disagree; 2 of them switched
    directly between agree and disagree". The reading never names a direction as the result.
  - Movement counts direction, not distance: agree → pass and agree → disagree each count as one move toward
    disagree. Direct switches are given separately.
- **Movement toward the middle.** The report counts how many statements' net movement went toward the middle. Rows are in statement order, not ranked by change,
  so the top rows don't read as findings.
- **Planned:** significance for shifts (§11, not reviewed), and possibly a paired effect size per statement with a
  confidence interval (suggested, not reviewed: Newcombe).

## 9. What the report leaves out, and why

The data this tool reads is cleaned for privacy before it reaches the report. The limits below are about how much
a number can carry, so the reader looks at what the data supports. They do not hide anyone.

- **Every count is exact,** in every table, chart and CSV, including counts of 1, the per-person transition
  tables and movers.
- **Percentages and bars** need at least `min_total` (default 10) responses behind them. Below that the counts are
  shown on their own ("3 of 9" in place of a percentage, "fewer than 10 responses" in place of a bar).
- **Labels** need at least `min_total` agree + disagree responses (§6).
- **Polis groups** are shown on their own only with at least `min_total` members, and only when at least
  `min_participants_for_groups` (25) people took part (§7). Smaller groups are merged into "Other", shown with its
  size.
- Role answers are not shown for "Other", and are not compared between polls.
- xids are used only to match people; they never appear in an output.
- In production, data reaches the analysis host only as the participant-id-only extract (§1).

## 10. Known limits

- Groups are weak and change between exports while the poll is open: Polis re-clusters on new responses.
- Observed shifts are not tested. With a few dozen people, a few movers either way is ordinary; the report gives
  the counts and does not read a direction into them.
- **Pass.** In a single poll's labels, pass counts as a non-answer: the label uses agree and disagree only, and
  pass is shown separately. For grouping people and for change between polls, pass is the middle of
  agree · pass · disagree. People also pass when they are unsure or uninterested, so a move into pass can mean
  either.
- Matching assumes one xid per person.
- In external exports, platform behaviour (such as automatic responses) is inferred from the files, not checked
  in code.

## 11. Planned: where significance could appear

Reports mark no significance today (§2). This section keeps the places where significance could be added later,
and what would plug in at each. **None of the tests below has been reviewed.** Every test, correction and marker
named here is a suggestion, listed with the questions to answer before it can become method.

**Which places.** A place could carry significance only if a test there makes a claim our principles allow: it is
not a claim about a wider population, and it is not circular (testing groups formed from the same responses).
Whether a place qualifies has been decided; the tests have not.

| Place | Could carry significance | Suggested test (not reviewed) |
|---|---|---|
| Statement labels (≥70% agree / disagree / neither) | never: descriptive | — |
| Agree versus disagree on one statement | never: no defensible noise model for one-off responses | — |
| Differences between Polis groups on a statement | never: the groups were formed from these responses | — |
| Opinion by role answer | never | — |
| Map, participation, timing | never: no claim to test | — |
| Label changes between polls | never: a threshold crossing, not a test | — |
| Participants who responded in one poll only, versus returners | never | — |
| All participants of one poll versus all of the other | never: only participants with the same xid are compared | — |
| Shifts by role answer | not reported | — |
| Statements passed more often than others | yes, first | Cochran's Q, then per statement |
| Direction of shift per statement | yes, first | exact sign test |
| Direct agree↔disagree switches per statement | yes, first | exact McNemar |
| Change in pass rate per statement | yes, first | exact McNemar |
| Polis group membership by role answer | later | Fisher's exact / χ² |
| Overall drift; drift toward pass; movement toward the middle | later | a person-level test, decided in advance |
| Shifts by Polis group in the first poll | later | none yet: to be designed with confidence for groupings (§7), since groups formed from the first poll's responses regress toward the middle |

**How it would plug in.** At each place the report already computes and shows the observed counts a test would
need. Adding significance would add a test on those counts and show its result in a main-text marker and a
fold-out, without changing any count or reading. One setting would switch it on, off by default.

### Questions for every place

- **Level and sides:** 95% or 90%; two-sided?
- **Family:** what one correction covers: the statements of one place in one report, all places in one report, or
  both polls together?
- **Correction:** suggested, not reviewed: Holm over all compared statements. Alternatives: none, Bonferroni,
  Benjamini–Hochberg (false discovery rate), Tarone's method (leaving out statements that cannot reach
  significance; not now).
- **Exact or approximate:** exact tests suit counts this small; is that the rule everywhere?
- **Marker form:** suggested, not reviewed: a `*` next to the observed value, meaning significant after
  correction, with p-values in the fold-out. Alternatives: no marker, only the fold-out; words instead of a symbol.
- **Not tested versus not significant:** how the report shows a place where a test could not reach significance
  with the counts it had.
- **Minimum:** does a test need `min_total` (10) responses behind it, as percentages do (§9)?

### Per place

**Statements passed more often than others** (first)
- Counts already shown: each statement's pass count; per participant, passed or not.
- Suggested, not reviewed: Cochran's Q across statements, then McNemar per statement against the rest.
- Open: which statements enter (all, or only those everyone saw, given statements added during the poll, §5);
  "more often than what": the other statements, or a fixed rate; does a "no response" count?

**Direction of shift per statement** (first)
- Counts already shown: movers toward agree and toward disagree, on agree · pass · disagree.
- Suggested, not reviewed: exact two-sided sign test.
- Open: what counts as a mover (any change, or only across the middle); whether distance counts (agree → pass
  versus agree → disagree; a signed-rank test would weigh it); whether no response in one poll is a move.

**Direct agree↔disagree switches per statement** (first)
- Counts already shown: agree → disagree and disagree → agree, from the transition table.
- Suggested, not reviewed: exact McNemar.
- Open: is this a separate family from the direction of shift, or the same question asked twice?

**Change in pass rate per statement** (first)
- Counts already shown: into pass and out of pass, from the transition table.
- Suggested, not reviewed: exact McNemar.
- Open: does a move from "no response" into pass count?

**Polis group membership by role answer** (later)
- Counts already shown: group × role answer.
- Suggested, not reviewed: Fisher's exact test, χ² for larger tables.
- Open: is this circular? Role questions are left out of clustering, so probably not, but this needs checking. How
  does "Other" enter?

**Overall drift; drift toward pass; movement toward the middle** (later)
- Counts already shown: net movement per statement; the count of statements whose net movement went toward the
  middle.
- Suggested, not reviewed: a person-level test across statements, fixed before looking at the data.
- Open: per person or per statement; how to weigh statements; how to fix it in advance.

**Shifts by Polis group in the first poll** (later)
- Counts already shown: movers per group per statement.
- No test suggested: it needs the confidence-for-groupings work first (§7).

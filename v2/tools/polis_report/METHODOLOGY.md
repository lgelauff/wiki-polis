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

1. **Show significance wherever a valid test exists; otherwise describe in words.** If a test can answer the
   question, the report gives its result. Where it can't, the report describes the pattern by a stated rule.
   Examples: too few people moved; the groups were formed from the same responses. Descriptions come with the
   counts they rest on.
2. **Never causal, never more certain than the numbers.** Reports say what was observed among these participants.
   They don't say why it happened, and they don't speak for a wider population. Each page and table states
   which participants its figures describe ("among the 34 matched participants") and gives the counts.
3. **Deterministic.** Every sentence is a fixed template filled from the data, chosen by a stated rule.
4. **Self-selected participants.** Counts describe the people who responded. Each page says so.
5. **Counts only, and exact.** The data is cleaned for privacy before it reaches the report. The report writes
   counts only: no xid or participant id is ever written. Every count is exact. The limits in §9 are about how
   much a number can carry, not about hiding anyone.
6. **Descriptive first, statistics in fold-outs.** The main text gives counts and plain readings. Test details
   (p-values, corrections, how close a label is to the line) sit in fold-out sections. The statistical claims are the tests listed in §11, each read against a model of
   response noise among these same participants; everything else describes these participants and makes no
   claim about a wider population.
7. **Every response counts, unless excluded.** Each exclusion has a rule, a reason and a count, and the report
   lists them (§4). Changes to the settings that decide what counts are logged with a reason, and the log is
   printed in every report it produced (§4).

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
| Settings change log, checked by the builder | yes | | yes | not yet |
| Automatic responses by value (pass / agree) | yes | | yes | not yet |
| Seed vs participant-written statement | no | | yes (`is_seed`) | not yet |
| Role questions | named by text in the config | | yes (`is_meta`) | by config text |
| Labels, PCA map | yes | | yes | yes (pol.is format) |
| Polis groups | yes, snapshot at export time | | yes, from the math record | yes (pol.is format) |
| Leiden groups | computed from responses | | computed from responses | **Planned** |
| Label sensitivity (responses that would change a label) | yes | | yes | in #563 |
| Minimum of 10 for percentages, bars, labels and groups (§9) | yes | | yes | in #563 |
| Tarone's selection of testable statements (§8) | yes (shifts need the xid file) | | yes (shifts need the xid file) | not yet |
| Statistics in fold-outs | yes | | yes | not yet |
| `*` on significant results (§11) | yes (shifts need the xid file) | | yes (shifts need the xid file) | not yet |
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

**Change log.** The settings that decide what counts (exclusions, role questions, statement pairs, thresholds and
minimums) have a log next to them: date, setting, old → new, reason. Every report prints the log in a fold-out.
**Planned:** the builder fingerprints these settings, and refuses to run when they changed since the last logged
fingerprint without a new entry, or when an exclusion has no reason. For an external partner the settings and log
stay with their data, outside the repository.

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
- **No significance marker.** Labels are descriptive, so they never carry the `*` (§11).
- **Pass rate.** Statements that were passed more often than others get a `*`: one test across all statements
  (Cochran's Q, since the same people respond to every statement), then a per-statement comparison with Holm
  correction. Details are in the fold-out.

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
- **Significance where it can exist.**
  - Test: an exact two-sided sign test per statement on the direction of movement, Holm-corrected. It counts
    direction, not distance: agree → pass and agree → disagree each count as one move. Full switches have their
    own test (below).
  - **Which statements are tested (Tarone's method).** With n movers, the smallest two-sided p a statement can
    reach is 2 × 0.5ⁿ. A statement whose smallest reachable p cannot clear its Holm threshold is left out of the
    correction, and the thresholds are recomputed until every statement left can reach its own. The choice uses
    only the number of movers, never their direction, so it does not bias the test. Statements of interest are
    not named in advance.
  - Each statement gets a reading chosen by rule:
    - no movers: "No observed movement";
    - too few movers to be tested: "Too few people changed their response to tell", with the counts;
    - significant after correction: the direction and both p-values;
    - significant only before correction: said explicitly;
    - otherwise: "No clear direction", with the probability of a split at least as uneven if movers were
      equally likely to go either way.
  - The report also counts how many statements had too few movers to be tested.
  - **Marker:** a result that is significant at 95% (two-sided, after Holm correction within its family, §11)
    gets a `*` in the main text, with a footnote saying so. Three families of per-statement tests carry it: the
    direction of shift (sign test), direct agree↔disagree switches (McNemar on agree and disagree only), and the
    change in pass rate (McNemar on pass versus not pass). Tarone's selection applies within each family.
    Everything else about the test (p-values, the reading, how many movers) is in the fold-out.
    The marker belongs to the test only: descriptive labels (≥70% agree, ≥70% disagree, neither) and other
    counts never carry it.
- **Noise baseline.** The report counts how many statements' net movement went toward the middle. Changes in
  responses to opinion statements can be read against it. Rows are in statement order, not ranked by change,
  so the top rows don't read as findings.
- **Planned:** a paired effect size per statement with a confidence interval (Newcombe), so the size and
  uncertainty of a shift are visible together. A pre-specified person-level test across statements, if a pooled
  question is wanted.

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
- With a few dozen people, most per-statement shifts cannot reach significance. The report says so instead of
  reporting "no change".
- **Pass.** In a single poll's labels, pass counts as a non-answer: the label uses agree and disagree only, and
  pass is shown separately. For grouping people and for change between polls, pass is the middle of
  agree · pass · disagree. People also pass when they are unsure or uninterested, so a move into pass can mean
  either.
- Matching assumes one xid per person.
- In external exports, platform behaviour (such as automatic responses) is inferred from the files, not checked
  in code.

## 11. Where a significance marker can appear

A `*` means: significant at 95%, two-sided, after Holm correction within its family (the per-statement tests
of one kind in one report). A place gets a marker only if a test there makes a claim our principles allow:
- it is not a claim about a wider population;
- it is not circular (testing groups formed from the same responses);

| Place | Test | Marker |
|---|---|---|
| Statement labels (≥70% agree / disagree / neither) | — | never: descriptive |
| Agree versus disagree on one statement | — | never: no defensible noise model for one-off responses |
| Differences between Polis groups on a statement | — | never: the groups were formed from these responses |
| Opinion by role answer | — | never |
| Polis group membership by role answer | Fisher / χ² | later |
| Statements passed more often than others | Cochran's Q, then per statement | **yes** |
| Map, participation, timing | — | never: no claim to test |
| Direction of shift per statement | sign test | **yes** |
| Direct agree↔disagree switches per statement | McNemar | **yes** |
| Change in pass rate per statement | McNemar | **yes** |
| Label changes between polls | — | never: a threshold crossing, not a test |
| Overall drift; drift toward pass; movement toward the middle | per-person or per-statement test, decided in advance | later |
| Shifts by role answer | — | not reported |
| Shifts by Polis group in the first poll | — | later: designed together with confidence for groupings, since groups formed from the first poll's responses regress toward the middle |
| Participants who responded in one poll only, versus returners | — | never |
| All participants of one poll versus all of the other | — | never: only participants with the same xid are compared |

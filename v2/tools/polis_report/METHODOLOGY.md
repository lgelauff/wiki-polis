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
5. **Privacy at a small event.** Counts only; no xid or participant id is ever written. Small cells are
   suppressed where they could identify someone (§9).

**Planned (language review):** a semantic check of the report templates for overclaiming, run when templates
change and before a report goes out. It covers implied causation, more certainty than the test supports,
generalising beyond these participants, and qualitative words without sizes. A language-model reviewer applies
this rubric and records the flagged sentences with reasons. It is a review step, not a word list, and not part
of the deterministic test suite.

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
| Automatic responses (author + creation time) | yes | | yes | removed, total counted |
| Automatic responses by value (pass / agree) | yes | | yes | not yet |
| Seed vs participant-written statement | no | | yes (`is_seed`) | not yet |
| Role questions | named by text in the config | | yes (`is_meta`) | by config text |
| Labels, PCA map | yes | | yes | yes (pol.is format) |
| Polis groups | yes, snapshot at export time | | yes, from the math record | yes (pol.is format) |
| Leiden groups | computed from responses | | computed from responses | **Planned** |
| Linking participants across conversations | no | yes | no | yes (with xid files) |
| wiki-polis phases, arguments, featured statements | no | no | no | no |

The report builder reads the pol.is CSV format today. **Planned:** a reader for the production extract, so
production reports run from the same code.

The last row needs data from the wiki-polis side, which none of these exports covers. A production report that
uses it has to name its source and how it was extracted.

## 4. Which responses count

- **Time window (`since`).** Response rows before the window are dropped, e.g. test responses before a live session.
  The report gives the number of rows removed, and how many participants responded only before the window.
- **Automatic responses.**
  - **Rule (both settings):** a response by a statement's author on that statement, at the second the statement
    was created, is treated as automatic and left out. The rule is procedural: it is about *which response*, not
    *which person*. All other responses count, including those of statement authors and the conversation owner,
    who can also take part as ordinary participants.
  - **Reported as well as removed.** Removed responses are counted, so a reader can see what was left out and
    add it back. **Planned:** the count is split by value (automatic passes, automatic agrees), and in production,
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
  - `exclude_participants` remains as a manual override and must come with a stated reason.
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
- **Close to the line.** When the 95% Wilson interval of the leading share crosses 70%, the report says so and
  gives the interval. That is a description of uncertainty, not a test.

## 7. Opinion groups

- **Current:** Polis's own groups (its k-means clustering), shown only when at least
  `min_participants_for_groups` people took part. The interim value is **25**. Below it the report says "not
  computed" and gives the count.
  - Groups under 5 members are merged into "Other".
  - The groups are a snapshot at export time, computed by Polis over all responses, including responses before
    the window and automatic responses. The report names the Polis group of participants with only automatic
    responses.
- **Descriptive only.** Testing differences between groups formed from these same responses would be circular, so
  no test is applied. The "largest difference between groups" chart uses this report's own measure: the range
  across groups of (agree − disagree) / all responses, over groups of 5 or more. It is named as such on the page.
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
  - Counts of movers toward agree and toward disagree, on the order agree · pass · disagree.
  - Direct agree↔disagree switches, reported separately.
- **Significance where it can exist.**
  - Test: an exact two-sided sign test per statement on the direction of movement, Holm-corrected for the
    number of statements. Each statement gets a reading chosen by rule:
    - no movers: "No observed movement";
    - too few movers for any split to reach p < 0.05: "Too few people changed their response to tell", with the
      counts;
    - significant after correction: the direction and both p-values;
    - significant only before correction: said explicitly;
    - otherwise: "No clear direction", with the probability of a split at least as uneven if movers were
      equally likely to go either way.
  - The report also counts how many statements could not reach significance with the movers they had.
- **Noise baselines.** The report counts how many matched participants answered a factual role question
  differently in the two polls, and how many statements' net movement went toward the middle. Changes in
  responses to opinion statements can be read against these. Rows are in statement order, not ranked by change,
  so the top rows don't read as findings.
- **Planned:** a paired effect size per statement with a confidence interval (Newcombe), so the size and
  uncertainty of a shift are visible together. A pre-specified person-level test across statements, if a pooled
  question is wanted.

## 9. Small cells and privacy

- Counts of 1–2 are shown as "<3" for the merged "Other" group, and wherever role answers are crossed with
  anything.
- Role answers are never crossed with a group under 5.
- Role answers over time are summarised as the number of differing answers, not tabulated per person.
- Per-person opinion transitions are shown exactly. Seeing single agree↔disagree switches is the point of that
  table, and it contains no role answers.
- xids are used only to match people; they never appear in an output.
- In production, data reaches the analysis host only as the participant-id-only extract (§1).

## 10. Known limits

- Groups are weak and change between exports while the poll is open: Polis re-clusters on new responses.
- With a few dozen people, most per-statement shifts cannot reach significance. The report says so instead of
  reporting "no change".
- Pass is treated as the middle of agree · pass · disagree. People also pass when unsure or uninterested.
- Matching assumes one xid per person.
- In external exports, platform behaviour (such as automatic responses) is inferred from the files, not checked
  in code.

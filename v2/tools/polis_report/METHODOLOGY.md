# polis_report: methodology

What the reports count, how they describe it, and why. The rules themselves are in the docstring of
`polis_report.py`. This file explains the reasoning. Planned changes are marked **Planned**.

## 1. Reporting principles

1. **Show significance wherever a valid test exists; otherwise describe in words.** If a test can answer the
   question, the report gives its result. Where it can't, the report describes the pattern in words.
   Examples: too few people moved; the groups were formed from the same votes. The description always comes
   with the counts it rests on.
2. **Never causal, never more certain than the numbers.** Reports say what was observed among these voters.
   They don't say why it happened, and they don't speak for a wider population. Every number names its
   population ("among the 34 matched participants") and its count.
3. **Deterministic.** Every sentence is a fixed template filled from the data, chosen by a stated rule. The
   same inputs and code give byte-identical HTML and CSV. A reproducibility block on every page lists the
   script's git hash, the config and input hashes, the export times and the Python version.
4. **Self-selected participants.** Counts describe the people who voted. Each page says so.
5. **Privacy at a small event.** Counts only; no xid or participant id is ever written. Small cells are
   suppressed where they could identify someone (§7).

**Planned (language review):** a semantic check of the report templates for overclaiming, run when templates
change and before a report goes out. It covers implied causation, more certainty than the test supports,
generalising beyond these voters, and qualitative words without sizes. A language-model reviewer applies this
rubric and records the flagged sentences with reasons. It is a review step, not a word list, and not part of
the deterministic test suite.

## 2. Which votes count

- **Time window (`since`).** Vote rows before the window are dropped, e.g. test votes before a live session.
  The report gives the number of rows removed, and how many participants voted only before the window.
- **Automatic votes.** When a statement is created, Polis records a vote by its author at that exact second.
  That vote is the platform's, not an opinion, so it is not counted. The rule is procedural: it is about
  *which vote*, not *which person*. All other votes count, including those of statement authors and the
  conversation owner, who can also take part as ordinary participants.
  `exclude_participants` remains as a manual override and must come with a stated reason.
  - On the Europeana data this rule removes exactly the 20 (Poll A) and 19 (Poll B) passes recorded at
    statement creation. No other votes by the author exist there.
- **Current vote.** The latest row per participant and statement in `votes.csv`. Rows with equal timestamps keep
  file order, and the report counts them. `participant-votes.csv` is not used for votes: Polis builds it by id
  order with last-write-wins, so after re-votes it can differ from the latest vote by time. The report counts
  those differences.
- **Participants** are people with at least one counted opinion vote.

## 3. Statements, including statements that change

- **Opinion statements and role questions.** Statements that ask about the participant ("I'm here today as…")
  are named by exact text in the config (`meta`). They are left out of opinion totals, labels, groups and the
  map, and reported separately as self-reported role answers. Meta texts not found in a poll produce a warning
  in the report.
- **Moderation.** Rejected statements are left out. Unmoderated ones are left out unless `include_unmoderated`
  is set. The report gives both counts.
- **Statements added while voting was under way.** Someone who finished before a statement existed could not
  vote on it. For every statement created after the first counted vote, the report gives its creation time and
  how many participants had already cast their last vote. Every statement is reported with its own number of
  votes, never as a share of all participants.
- **The same statement in two polls.** Statements are matched by text, ignoring spacing and apostrophe style,
  never by number. Conversations number the same texts differently (Poll B #0 = Poll A #2). The second poll is
  shown with the first poll's numbers.
- **Statements edited between polls** count as different statements unless the config pairs the two versions
  (`statement_pairs`). Statements in only one poll appear in that poll's report and are listed as not compared.
- **Display order.** Polis chooses the order in which each participant sees statements, and that order can
  differ between polls. The report states this; it cannot correct for it.

## 4. Labels

- A statement is labelled **≥70% agree**, **≥70% disagree** or **neither ≥70%**, counting agree + disagree only.
  The pass share is shown separately and is not in the denominator. The threshold is `label_share`.
- The label is written as the rule itself, not as "consensus". It is not Polis's group-informed consensus.
- **Close to the line.** When the 95% Wilson interval of the leading share crosses 70%, the report says so and
  gives the interval. That is a description of uncertainty, not a test.

## 5. Opinion groups

- **Current:** Polis's own groups (its k-means clustering, `group-id` in the export), shown only when at least
  `min_participants_for_groups` people took part. The interim value is **25**. Below it the report says "not
  computed" and gives the count.
  - Groups under 5 members are merged into "Other".
  - The groups are a snapshot at export time, computed by Polis over all votes, including votes before the
    window and automatic votes. The report names the Polis group of participants who cast only automatic votes.
- **Descriptive only.** Testing differences between groups formed from these same votes would be circular, so
  no test is applied. The "largest difference between groups" chart uses this report's own measure: the range
  across groups of (agree − disagree) / all votes, over groups of 5 or more. It is named as such on the page.
- **Planned:** show k-means and Leiden community detection side by side, so readers see how much the grouping
  depends on the method. Replace the fixed minimum with a robustness measure: re-cluster on resampled
  participants, and show groups only when assignments stay stable above a stated threshold. Leiden needs an
  outside library, so it will be an optional dependency.

## 6. Before and after (two polls)

- **Same people only.** The comparison uses only participants whose xid appears in both conversations' xid
  files and who cast a counted opinion vote in both. Each conversation has its own xid file.
  - Comparing the two rooms' totals mixes change with who turned up. On the Europeana data, #4 looked like a
    22-point drop in agreement, but among the 34 matched people the number agreeing was 4 in both polls.
  - The report shows how the one-poll-only voters voted, but keeps them out of the comparison.
  - Each single-poll page lists where its labels differ from those of the matched group.
- **Movement in both directions, never only the net.**
  - Per statement: a table of each person's vote in A against their vote in B (agree / disagree / pass /
    no vote).
  - Counts of movers toward agree and toward disagree, on the order agree · pass · disagree.
  - Direct agree↔disagree switches, reported separately.
- **Significance where it can exist.**
  - Test: an exact two-sided sign test per statement on the direction of movement, Holm-corrected for the
    number of statements. Each statement gets a reading chosen by rule:
    - no movers: "No observed movement";
    - too few movers for any split to reach p < 0.05: "Too few people changed their vote to tell", with the
      counts;
    - significant after correction: the direction and both p-values;
    - significant only before correction: said explicitly;
    - otherwise: "No clear direction", with the probability of a split at least as uneven if movers were
      equally likely to go either way.
  - The report also counts how many statements could not reach significance with the movers they had.
- **Noise baselines.** The report counts how many matched participants answered a factual role question
  differently in the two polls, and how many statements' net movement went toward the middle. Changes in
  opinion votes can be read against these. Rows are in statement order, not ranked by change, so the top rows
  don't read as findings.
- **Planned:** a paired effect size per statement with a confidence interval (Newcombe), so the size and
  uncertainty of a shift are visible together. A pre-specified person-level test across statements, if a pooled
  question is wanted.

## 7. Small cells and privacy

- Counts of 1–2 are shown as "<3" for the merged "Other" group, and wherever role answers are crossed with
  anything.
- Role answers are never crossed with a group under 5.
- Role answers over time are summarised as the number of differing answers, not tabulated per person.
- Per-person opinion transitions are shown exactly. Seeing single agree↔disagree switches is the point of that
  table, and it contains no role answers.
- xids are used only to match people; they never appear in an output.

## 8. Known limits

- Groups are weak and change between exports while voting is open: Polis re-clusters on new votes.
- With a few dozen people, most per-statement shifts cannot reach significance. The report says so instead of
  reporting "no change".
- Pass is treated as the middle of agree · pass · disagree. People also pass when unsure or uninterested.
- Matching assumes one xid per person.

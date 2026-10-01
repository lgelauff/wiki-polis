# polis_stats

Basic statistics and charts from a Polis conversation export, with the export cross-checked
before anything is counted. Standard library only; no plotting dependency.

```bash
cd v2
python -m tools.polis_stats path/to/export-folder-or.zip -o out/
python -m tools.polis_stats.synth /tmp/synthetic && python -m tools.polis_stats /tmp/synthetic -o /tmp/report   # try it
```

Output in `out/`: `report.html` (summary, checks, charts, the full statement table; light and dark),
`stats.json` (summary, labels, checks), `statements.csv` (every statement: counts, shares, 95% Wilson
interval, label, per-group numbers), `groups.csv`, `meta_crosstab.csv`, `issues.csv` (every check
result), `charts/*.svg`.
Exit code 0 = written; 1 = a cross-check failed (nothing written unless `--allow-errors`);
2 = unreadable export.

## The standard format (Polis's CSV export)

wiki-polis's own export should write exactly these files, so this tool reads both.
Source of truth: `math/src/polismath/darwin/export.clj` (`csv-format`).

| file | columns | notes |
|---|---|---|
| `summary.csv` | no header; `key,value` rows: `topic`, `url`, `views`, `voters`, `voters-in-conv`, `commenters`, `comments`, `groups`, `conversation-description` | optional |
| `comments.csv` | `timestamp, comment-id, author-id, agrees, disagrees, moderated, is-meta, is-seed, group-informed-consensus, comment-body` | `moderated`: 1 accepted, 0 pending, -1 rejected. `agrees`/`disagrees` count **every** row of votes.csv, re-votes included |
| `votes.csv` | `timestamp, datetime, comment-id, voter-id, vote` | **every vote ever cast** (append-only history); the current vote is the latest row per voter and statement |
| `participants-votes.csv` | `participant, group-id, n-comments, n-votes, n-agree, n-disagree, <one column per comment-id>` | the latest-vote matrix; `group-id` empty = not clustered |

Timestamps are epoch milliseconds. **Vote sign: agree = +1, disagree = -1, pass = 0.** Polis
negates its stored votes on export (in its database and in wiki-polis's vote API agree is -1).
An export cannot reveal its own sign, so pass `--vote-sign raw` for data in the database
convention; a mismatch between files is reported as `vote-sign-inverted`.

## Checks (all reported in the HTML, stats.json and issues.csv; nothing is dropped silently)

- votes for statements missing from comments.csv; malformed vote rows; votes without time
- participants-votes.csv differs from the latest votes in votes.csv (cell by cell)
- comments.csv agrees/disagrees differ from votes.csv (with a specific error when swapped)
- re-votes (a note: history, not counted)

## Definitions (all thresholds are options)

- current vote: latest row per (voter, statement) in votes.csv; equal timestamps keep file order,
  the same tie-break Polis uses for participants-votes.csv
- rejected statements (moderated = -1) are counted but not charted or classified; pending ones (0) are
  classified like accepted ones, so check the `moderated` column if strict moderation was on
- meta statements (`is-meta`) ask about the participant, not the topic: no opinion label
- labels describe the overall vote on one statement, among statements with at least `--min-votes`
  (10) agree + disagree votes: `mostly-pass` if passes are over `--max-pass` (0.50) of all votes;
  otherwise `majority-agree` / `majority-disagree` if one side has at least `--majority` (0.70) of
  agree + disagree; `split` if both sides have at least `--split` (0.35). They are **not** Polis's
  group-informed consensus or representativeness, which are group-aware.
- the 95% Wilson interval describes these votes; participants chose to take part, so it is not an
  estimate for any wider population

## Opinion groups

Groups are an input, not a finding. By default they are Polis's own clusters (`group-id` in
participants-votes.csv); `--groups FILE` (a CSV with `participant,group`) uses any other assignment.
The report shows a heatmap of agree share per statement and group (rows with the largest difference
between groups first) and a participant map: our own two-component PCA of the vote matrix, not
Polis's map, coloured by group, so one can see whether the groups really separate. Participants
need at least 7 opinion votes to be placed (half the opinion statements, for small conversations),
and, as in Polis, those with few votes are scaled so that they are not pulled to the centre. Polis
decides whom to cluster by its own rule, so the map says how many grouped participants it placed.
The group spread (largest gap in agree share between groups with at least 10 decided votes) is a
descriptive number, not a significance test.

## Meta statements

Statements with `is-meta = true` ask about the participant, not the topic, so they are treated as
demographics: they are left out of the opinion totals, the statement labels, the statement chart, the group
heatmap and spread, and the participant map (Polis also leaves them out of its clustering, though
they still count towards which participants it includes). The
report gives each meta statement its own section: how many answered each way, and how every
opinion statement was voted by those who agreed versus disagreed with it (`meta_crosstab.csv`).
An export without an `is-meta` column is reported, not guessed at.

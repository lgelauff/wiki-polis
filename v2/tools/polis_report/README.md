# polis_report

Deterministic HTML/PDF reports for one or two Polis conversations from their public CSV exports. The two-conversation
case is a before/after pair with the same statements, linked per participant by xid. Standard library only.

```bash
python3 v2/tools/polis_report/polis_report.py my-study/config.json           # build from the exports named in the config
python3 v2/tools/polis_report/polis_report.py my-study/config.json --fetch   # download fresh exports from pol.is first
cd v2 && python -m tools.polis_report ../my-study/config.json --no-pdf
```

The reasoning behind every rule is in [METHODOLOGY.md](METHODOLOGY.md). Start from `config.example.json`. All paths in the config are relative to the config file. Keep study data outside
this repository.

| config key | meaning |
|---|---|
| `since` | UTC time; vote rows before it are dropped before taking each participant's latest vote |
| `meta` | role/demographic statements, by exact text; left out of opinion totals, labels and the map |
| `timezone` | IANA zone for local times in the reports (default UTC) |
| `polls[].exclude_participants` | optional manual override: participant ids left out entirely, with `exclude_reason` (automatic votes are already removed by rule) |
| `statement_pairs` | optional `[[text in first poll, text in second poll], ...]` for statements edited between polls |
| `min_participants_for_groups` | groups are shown only with at least this many participants (default 25) |
| `min_cell` | counts from 1 to `min_cell` − 1 are shown as "<3" (default 3); if that hides one count of a row, the row's next-smallest is shown as "≥3" |
| `min_total` | a column or breakdown with fewer people is not shown (default 10); Polis groups under it are merged into "Other" |
| `include_unmoderated` | also count statements Polis has not moderated yet (default: accepted only) |
| `polls[].dir` | folder with `comments.csv`, `votes.csv`, `participant-votes.csv` (pol.is's name) or `participants-votes.csv` |
| `polls[].xid` | the conversation's `participant,xid` file (owner view); both polls need one for the comparison reports |
| `polls[].report` | pol.is report id, used by `--fetch` |
| `label_share` | 0.7: broadly agreed / rejected when that share of agree + disagree goes one way, otherwise divided |
| `chrome` | optional path to Chrome/Chromium for the PDFs (also `$CHROME`; common locations are tried) |

Outputs in `out/`:

- `poll-<key>-report`: statement bars, the statements where Polis's groups differ most, a full agree/disagree/pass
  table per group, a PCA map, and role questions.
- `poll-ab-compared`: the two polls side by side, for participants with the same xid in both only.
- `poll-ab-transitions`: for those participants, 4×4 vote transition tables (both directions, never only net change),
  movers per statement, an exact sign test with Holm correction, and how those who voted in one poll only voted.
- CSVs of every table. Counts only: no xid or participant id is written. Small counts follow `min_cell` and `min_total`
  everywhere except the per-person transition tables and movers, which are shown exactly.

Linking the two polls: Polis records, for each participant, the xid the organizer passed in (for example through the
embed URL). The organizer decides what it is, so use the same xid for a person in both polls. The tool reads it from
the `participant,xid` file named in `polls[].xid`. A participant with the same xid in both polls is counted as the same
person; participants whose xid appears in one poll only are reported separately, as responding in one poll only. The
xids are read only to make this link. No xid or participant id is written to any output.

Rules (see METHODOLOGY.md for the reasons):
- A vote by a statement's author on that statement at the second it was created is Polis's automatic vote and is not counted; all other votes count.
- Current vote = the latest row per participant and statement; equal timestamps keep file order.
- The second poll's statements are matched to the first by exact text, and shown with the first poll's numbers.
- Every sentence is a template filled from the data, and the PCA is seeded, so the same input gives byte-identical HTML and CSV.

How this differs from `tools/polis_stats`: polis_stats cross-checks a single export and reports on it. polis_report adds
the time window, exclusions, meta-by-text, matching across two conversations and the per-participant transition reports.
It reads pol.is's own file names directly.

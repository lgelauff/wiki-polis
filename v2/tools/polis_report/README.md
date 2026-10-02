# polis_report

Deterministic HTML/PDF reports for one or two Polis conversations from their public CSV exports. The two-conversation
case is a before/after pair with the same statements, linked per participant by xid. Standard library only.

```bash
python3 v2/tools/polis_report/polis_report.py my-study/config.json           # build from the exports named in the config
python3 v2/tools/polis_report/polis_report.py my-study/config.json --fetch   # download fresh exports from pol.is first
cd v2 && python -m tools.polis_report ../my-study/config.json --no-pdf
```

Start from `config.example.json`. All paths in the config are relative to the config file. Keep study data outside
this repository.

| config key | meaning |
|---|---|
| `since` | UTC time; vote rows before it are dropped before taking each participant's latest vote |
| `meta` | role/demographic statements, by exact text; left out of opinion totals, labels and the map |
| `polls[].exclude_participants` | participant ids to leave out, e.g. the moderator, whose automatic passes are not opinions |
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
- CSVs of every table. Counts only: no xid or participant id is written.

Rules:
- Current vote = the latest row per participant and statement; equal timestamps keep file order.
- The second poll's statements are matched to the first by exact text, and shown with the first poll's numbers.
- Every sentence is a template filled from the data, and the PCA is seeded, so the same input gives byte-identical HTML and CSV.

How this differs from `tools/polis_stats`: polis_stats cross-checks a single export and reports on it. polis_report adds
the time window, exclusions, meta-by-text, matching across two conversations and the per-participant transition reports.
It reads pol.is's own file names directly.

# Issue #162: Add more detail / guidance to the statements admin page

**Verdict: FITS**

## Context

`v2/templates/admin_statements.html` has three functional sections:
1. "Add seed statement" — adds a single statement via Particiapi.
2. "Import seed statements from CSV" — bulk import.
3. A statements table showing existing statements with approve/hide/pending controls.

The current guidance is minimal: a one-line note that seed statements "appear as regular
participant statements (not seed-marked)". There is no explanation of what approve/hide/pending
do, no statement provenance info, no phase-dependency warnings.

The issue scope (confirmed in the note) is the admin statements management page. No route or
DB changes are required — this is primarily a template change, though the route may need to pass
additional context (provenance: seed vs participant-submitted).

The `admin_conversation_statements` route in `app.py` already fetches statement data from
Particiapi (via the proxy) and passes it to the template. The `new_stmt_ids` JSON column on
`Participation` records participant-submitted statement IDs — this can be used to identify
provenance.

## Files to change

- `v2/templates/admin_statements.html` — add guidance text to each section; add provenance
  column to the statements table; add phase-dependency note.
- `v2/app.py` — in `admin_conversation_statements` route, enrich the statement rows with
  provenance info (seed vs participant-submitted) using `new_stmt_ids` from participations.

## Implementation steps

### 1. `admin_statements.html` — guidance for the seed/import sections

**Add seed statement section** — replace the current muted note with:
```jinja
<p class="muted" style="margin-bottom:.75rem;font-size:13px">
  Seed statements bootstrap the voting loop. They appear immediately in the vote view for all
  participants, attributed the same way as participant-submitted statements (no "seed" label is
  shown to participants). Add seeds <em>before</em> opening submission so participants have
  something to react to from their first visit.
  {% if recommended_seeds %}
  Aim for at least {{ recommended_seeds }} before opening.
  {% endif %}
</p>
```

**CSV import section** — after the existing description, add:
```jinja
<p class="muted" style="font-size:12px;margin-top:.5rem">
  Each row becomes a separate seed statement. Duplicate texts (already present in this
  conversation) are skipped automatically. The import is one-way — there is no bulk-delete.
</p>
```

### 2. `admin_statements.html` — guidance panel for moderation controls

Before the statements table, add a collapsible or inline explanation:
```jinja
<div class="guidance-block" style="margin-bottom:1rem;font-size:13px">
  <p style="margin-bottom:.5rem">
    <strong>Moderation states</strong> (these map to Polis statement moderation):
  </p>
  <ul style="margin:0 0 .5rem 1.25rem;line-height:1.7">
    <li><strong>Approved</strong> — visible in the vote view; participants can vote on it.</li>
    <li><strong>Hidden</strong> — removed from the vote view; existing votes are preserved in Polis
        but the statement no longer appears to participants.</li>
    <li><strong>Pending</strong> — awaiting moderation; not shown to participants until approved.
        Participant-submitted statements start here if moderation is enabled.</li>
  </ul>
  <p style="font-size:12px;color:var(--muted)">
    Moderation actions are applied via Particiapi and take effect immediately in Polis.
  </p>
</div>
```

### 3. `app.py` — enrich statement rows with provenance

In the `admin_conversation_statements` route, after fetching statements from Particiapi:

```python
# Build a set of participant-submitted statement IDs for this conversation.
from itertools import chain
participations = Participation.query.filter_by(conversation_id=conv_id).all()
participant_stmt_ids = set(chain.from_iterable(
    p.new_stmt_ids or [] for p in participations
))
# Attach provenance flag to each statement dict.
for stmt in statements:
    stmt['provenance'] = 'participant' if stmt.get('tid') in participant_stmt_ids else 'seed'
```

Pass `statements` (enriched) to the template as before.

### 4. `admin_statements.html` — add provenance + vote count columns to the table

In the statements table, add a "Source" column:
```jinja
<th>Source</th>
```
And in the row:
```jinja
<td>
  {% if stmt.provenance == 'participant' %}
    <span style="font-size:11px;color:var(--muted)">participant</span>
  {% else %}
    <span style="font-size:11px;color:var(--muted)">seed</span>
  {% endif %}
</td>
```

If the Particiapi statement data includes vote counts (`agrees`, `disagrees`), surface them:
```jinja
<td style="font-size:12px;white-space:nowrap">
  {{ stmt.agrees | default(0) }}A / {{ stmt.disagrees | default(0) }}D
</td>
```
Add a "Votes" column header to match.

### 5. `admin_statements.html` — phase-dependency note

Near the top of the page (below the title/back-link, before the seed section):
```jinja
{% if not conversation.active %}
<div class="notice notice--warning" style="margin-bottom:1.5rem;font-size:13px">
  This conversation is closed. Seed import and statement moderation are still available for
  archival purposes, but will not affect what participants see.
</div>
{% endif %}
```

## Tests

- `v2/tests/test_admin_statements_guidance.py`:
  - GET `/admin/conversation/<id>/statements` for a moderator returns 200.
  - Response HTML contains "Moderation states" guidance text.
  - Response HTML contains "Approved" / "Hidden" / "Pending" explanations.
  - Response HTML contains "seed" provenance label for a known seed statement.
  - Closed conversation response contains the "closed" warning notice.

## Verification

1. Run `pytest v2/tests/test_admin_statements_guidance.py -v`.
2. Log in as admin, navigate to Statements for a conversation.
3. Verify the moderation-states guidance panel renders.
4. Verify seed vs participant provenance labels appear in the table.
5. For a closed conversation, verify the warning notice appears at the top.

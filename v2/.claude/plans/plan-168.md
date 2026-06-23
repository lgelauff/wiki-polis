# Issue #168: Design pass on the admin phase-management UI

**Verdict: FITS**

## Context

The admin phase-management block in `v2/templates/admin_conversation.html` has grown organically
through multiple PRs (#140, #156). The issue explicitly says "this is a polish/design pass, not
new functionality". The roadmap cites #47 (admin/participant split) and #119 (informed-voting
polish) as sibling design work; #168 is the corresponding pass for the phase block itself.

The phase block in `admin_conversation.html` contains (in order):
- Phase stepper (simple mode) — CSS class `.phase-stepper` (style.css ~line 1927)
- Pause/Resume row — form with `.pause-btn`
- Guided "Move on" box — `.guided-transition` area with consequence list, checklist, machine-check
  readouts, and submit button
- Custom-state notice — shown when phases are manually set
- Advanced controls disclosure — `<details>` with direct phase toggles and phase 6 init
- Phase 6 init fallback

The issue asks for:
1. Visual hierarchy & grouping — clearer spacing/separation between sub-areas.
2. Guided "Move on" box — layout of consequences, checklist, machine readouts, submit affordance,
   irreversibility warning prominence.
3. Consistency with rest of admin UI.
4. Stepper styling — done/current/upcoming, responsiveness.
5. Copy tone pass.
6. Mobile/narrow-viewport behaviour.

No route or DB changes needed. This is template + CSS only.

## Files to change

- `v2/templates/admin_conversation.html` — restructure the phase block markup for better
  visual grouping; improve copy on consequence text, checklist labels, warning text.
- `v2/static/style.css` — refine `.phase-stepper`, `.guided-transition`, and related
  classes; add spacing tokens; add narrow-viewport overrides.

## Implementation steps

### Preparation: read the current markup

Before implementing, read the full phase block in `admin_conversation.html`. The block spans
roughly lines 190–400. Key sections to identify:
- The stepper loop (iterates `phases` list with done/current/upcoming states).
- The pause form.
- The `{% if guided_transition %}` block containing consequence list + checklist + machine readouts.
- The `{% if custom_state %}` notice.
- The `<details>` advanced block.

### 1. Visual hierarchy & spacing

Wrap the entire phase-management section in a single `<section class="phase-mgmt-panel">` to
give it a distinct container. Add:

```css
.phase-mgmt-panel {
  background: var(--surface2);
  border: 1px solid var(--hairline);
  border-radius: 8px;
  padding: 1.5rem;
  margin-bottom: 2rem;
}
```

Sub-sections (stepper, pause row, guided-transition, advanced) should be separated by
`<hr class="phase-divider">` with:
```css
.phase-divider {
  border: none;
  border-top: 1px solid var(--hairline);
  margin: 1.25rem 0;
}
```

### 2. Stepper styling pass

Current stepper classes (from style.css ~line 1927): audit them and ensure:
- **Done** state: checkmark icon, muted colour, no circle emphasis.
- **Current** state: highlighted (accent colour background or bold ring), clearly prominent.
- **Upcoming** state: muted, lighter weight.

Add responsive wrapping for long phase labels at narrow widths:
```css
@media (max-width: 600px) {
  .phase-stepper {
    flex-wrap: wrap;
    gap: .5rem;
  }
  .phase-step-label {
    font-size: 11px;
  }
}
```

### 3. Guided "Move on" box

The guided-transition box should have a distinct visual treatment:

```css
.guided-transition {
  background: var(--surface);
  border: 1px solid var(--hairline);
  border-radius: 6px;
  padding: 1.25rem;
}
.guided-transition__heading {
  font-size: 15px;
  font-weight: 600;
  margin-bottom: 1rem;
}
```

**Consequence list** — use a visually distinct tag/badge for each consequence (the
`.consequence-tag` class already exists per line 251 in admin_conversation.html):
- Ensure tags have adequate padding and font-size.
- Group consequences under a clear "What will change:" heading.

**Checklist** — the precondition checklist items (admin to-do items) should have a checkbox
aesthetic. If currently plain list items, add a visual checkbox indicator:
```css
.checklist-item::before {
  content: '☐';
  margin-right: .4rem;
  color: var(--muted);
}
.checklist-item--done::before {
  content: '☑';
  color: var(--success, #16a34a);
}
```

**Machine-check readouts** (e.g. "N selected, 15 recommended") — these are the automated
status lines from `_featured_note()`. They should be visually distinct from the admin-todo
checklist:
```css
.machine-check {
  font-size: 12px;
  color: var(--muted);
  padding-left: 1.5rem;
  display: flex;
  align-items: center;
  gap: .5rem;
}
.machine-check--warn {
  color: var(--warning, #b45309);
}
.machine-check--ok {
  color: var(--success, #16a34a);
}
```

**Submit button** — the "Move on" submit button should be disabled until preconditions pass.
This is already implemented — verify the disabled→enabled affordance is clear by adding a
tooltip or muted text like "Complete the checklist above to enable" when disabled.

**Irreversibility warning** — the warning text (e.g. "This cannot be undone") should use the
existing `.consequence-callout` pattern or a `.warning-callout` with amber left-border:
```css
.warning-callout {
  border-left: 3px solid var(--warning, #f59e0b);
  padding-left: .75rem;
  font-size: 13px;
  color: var(--body);
  margin-top: .75rem;
}
```

### 4. Copy tone pass

While editing the template, do a light copy pass:
- Change "Move on" (generic) to "Advance to [Phase Name]" where the target phase name is
  available in context — more specific and action-oriented.
- Replace "This cannot be undone" with "This step is permanent — [specific consequence]."
- Checklist labels: use sentence case consistently; remove redundant "Please" prefixes.
- Pause/Resume button copy: "Pause voting" / "Resume voting" — make the object explicit.

### 5. Advanced controls disclosure

The `<details>` element for advanced controls should have a clear label and be visually
de-emphasised (it's an escape hatch, not the primary path):
```jinja
<details class="advanced-disclosure">
  <summary class="advanced-disclosure__trigger">Advanced controls (direct phase overrides)</summary>
  ...
</details>
```
```css
.advanced-disclosure__trigger {
  font-size: 13px;
  color: var(--muted);
  cursor: pointer;
}
.advanced-disclosure__trigger:hover {
  color: var(--body);
}
```

### 6. Mobile / narrow-viewport

Add or verify at `max-width: 640px`:
- `.guided-transition` padding reduces to `.75rem`.
- `.phase-mgmt-panel` padding reduces to `1rem`.
- Consequence tags wrap naturally (they should already be `flex-wrap:wrap`).

## Tests

- `v2/tests/test_admin_phase_ui.py`:
  - GET `/admin/conversation/<id>` returns 200.
  - Response HTML contains `phase-mgmt-panel` class.
  - Response HTML contains `guided-transition` class.
  - Response HTML contains `warning-callout` or `consequence-callout` for irreversibility text.
  (These are smoke tests — the design pass is primarily visual and requires manual review.)

## Verification

1. Run `pytest v2/tests/test_admin_phase_ui.py -v`.
2. Log in as admin, navigate to a conversation with a pending phase transition.
3. Verify:
   - Phase stepper clearly shows done/current/upcoming states.
   - Guided "Move on" box has distinct visual container, clear heading, and grouped sections.
   - Irreversibility warning has amber left-border styling.
   - Machine-check readouts are visually distinct from admin checklist items.
   - Submit button shows "Complete the checklist above to enable" when disabled.
4. Resize browser to 375px width — verify stepper wraps gracefully, guided box remains readable.
5. Optional: screenshot before/after for the PR.

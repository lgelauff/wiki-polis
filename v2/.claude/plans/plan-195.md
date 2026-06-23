# Plan: #195 — Design: replace phase-rail dots with progressive input/output badges

**Verdict: FITS** — The 4-dot `.conv-phase-rail` macro exists in `home.html` (lines 4–18) and is rendered on every conversation card (lines 208, 241, 282). The issue's badge concept is coherent with the phase model and the design principles (curiosity-driven, shows progress, low-friction). It references #190 and #194 as predecessors; both exist. This plan covers the HTML/CSS redesign of the per-card phase rail from dots to a compact badge strip. The issue explicitly calls for static mockups first; this plan covers phase 1 (replace the rail) with the full progressive-state model.

---

## Context

Current state: `{{ phase_rail(sig.phases) }}` macro in `home.html` renders four dots and three connector lines via `.conv-phase-dot` / `.conv-phase-rail-line` classes. The macro takes `sig.phases` — a set of active Polis phase strings like `{'submission', 'argument_mapping'}`.

Phase mapping (from the macro, lines 6–9):
- pos 0: not yet started
- pos 1: `submission` (Explore)
- pos 2: `argument_mapping` or `featured_selection` (Arguments)
- pos 3: `cleanup_window`, `informed_voting`, or `cleanup` (Informed vote)
- pos 4: `closed` or `public_results` (Report)

The issue proposes replacing the dot rail with **6 progressive badges** split into two rows:

| Group | Badge | Unlocks at pos |
|-------|-------|----------------|
| Input | Vote on statements | pos ≥ 1 |
| Input | Submit / rate arguments | pos ≥ 2 |
| Input | Informed vote | pos ≥ 3 |
| Output | Opinion clusters | pos ≥ 4 (results) |
| Output | Argument map | pos ≥ 2 (after arg phase) |
| Output | Final report | pos ≥ 4 |

The "done" treatment is the current scope limit — a done badge shows a muted filled check; the open issue is whether done state is tracked (Polis doesn't expose per-user completion on the card level). For this plan, **done state is deferred**: badges show `locked` or `unlocked` only, with a comment noting where done-state could be added later.

---

## Files to change

| File | Change |
|------|--------|
| `v2/templates/home.html` | Replace `phase_rail` macro (lines 4–18) with a new `phase_badges` macro; replace all three `{{ phase_rail(...) }}` call-sites (lines 208, 241, 282) with `{{ phase_badges(...) }}` |
| `v2/static/style.css` | Remove `.conv-phase-rail` / `.conv-phase-dot` / `.conv-phase-rail-line` block (lines 3797–3840); add `.conv-phase-badges` block |

---

## Implementation steps

### 1. New macro in `home.html` (replace lines 4–18)

```jinja2
{# ── Phase badges macro: two rows of progressive input/output badges ──────── #}
{% macro phase_badges(phases) %}
{%- set pos = 4 if ('closed' in phases or 'public_results' in phases) else
              (3 if ('cleanup_window' in phases or 'informed_voting' in phases or 'cleanup' in phases) else
               (2 if ('argument_mapping' in phases or 'featured_selection' in phases) else
                (1 if 'submission' in phases else 0))) -%}
<div class="conv-phase-badges" aria-hidden="true">
  <div class="conv-phase-badges-row conv-phase-badges-row--input">
    <span class="conv-phase-badge{% if pos >= 1 %} conv-phase-badge--unlocked{% endif %}" title="Vote on statements">
      <span class="conv-phase-badge-dot"></span>
      <span class="conv-phase-badge-label">Vote</span>
    </span>
    <span class="conv-phase-badge{% if pos >= 2 %} conv-phase-badge--unlocked{% endif %}" title="Submit &amp; rate arguments">
      <span class="conv-phase-badge-dot"></span>
      <span class="conv-phase-badge-label">Arguments</span>
    </span>
    <span class="conv-phase-badge{% if pos >= 3 %} conv-phase-badge--unlocked{% endif %}" title="Informed vote">
      <span class="conv-phase-badge-dot"></span>
      <span class="conv-phase-badge-label">Re-vote</span>
    </span>
  </div>
  <div class="conv-phase-badges-row conv-phase-badges-row--output">
    <span class="conv-phase-badge{% if pos >= 2 %} conv-phase-badge--unlocked{% endif %}" title="Argument map">
      <span class="conv-phase-badge-dot"></span>
      <span class="conv-phase-badge-label">Arg map</span>
    </span>
    <span class="conv-phase-badge{% if pos >= 4 %} conv-phase-badge--unlocked{% endif %}" title="Opinion clusters">
      <span class="conv-phase-badge-dot"></span>
      <span class="conv-phase-badge-label">Clusters</span>
    </span>
    <span class="conv-phase-badge{% if pos >= 4 %} conv-phase-badge--unlocked{% endif %}" title="Final report">
      <span class="conv-phase-badge-dot"></span>
      <span class="conv-phase-badge-label">Report</span>
    </span>
  </div>
</div>
{% endmacro %}
```

Then replace the three call-sites:
- Line 208: `{{ phase_rail(sig.phases if sig.phases is defined else set()) }}` → `{{ phase_badges(sig.phases if sig.phases is defined else set()) }}`
- Line 241: same replacement
- Line 282: same replacement

### 2. New CSS block in `style.css` (replace the `.conv-phase-rail` block at ~line 3797)

Remove the old block (`.conv-phase-rail`, `.conv-phase-dot`, `.conv-phase-dot--past`, `.conv-phase-dot--active`, `.conv-phase-rail-line`, `.conv-phase-rail-line--done`) and add:

```css
/* ── Conv card: phase badges ────────────────────────────────────────────── */

.conv-phase-badges {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 6px 0 2px;
}

.conv-phase-badges-row {
  display: flex;
  gap: 4px;
  align-items: center;
}

/* Row label (screen-reader only; sighted users see the badge labels) */
.conv-phase-badges-row--input::before {
  content: '';
  display: block;
  width: 3px;
  height: 10px;
  border-radius: 2px;
  background: var(--accent, #3366cc);
  opacity: 0.35;
  flex-shrink: 0;
  margin-right: 2px;
}

.conv-phase-badges-row--output::before {
  content: '';
  display: block;
  width: 3px;
  height: 10px;
  border-radius: 2px;
  background: var(--muted-fg, #72777d);
  opacity: 0.35;
  flex-shrink: 0;
  margin-right: 2px;
}

.conv-phase-badge {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 2px 6px 2px 4px;
  border-radius: 10px;
  border: 1px solid var(--hairline);
  background: var(--surface2);
  font-size: 10px;
  font-weight: 500;
  color: var(--muted);
  opacity: 0.45;
  transition: opacity 0.15s, background 0.15s, color 0.15s;
  white-space: nowrap;
}

.conv-phase-badge--unlocked {
  opacity: 1;
  color: var(--body);
  background: var(--surface);
  border-color: var(--accent-muted, #c8d8f5);
}

.conv-phase-badges-row--input .conv-phase-badge--unlocked {
  color: var(--accent, #3366cc);
  border-color: var(--accent-muted, #c8d8f5);
  background: var(--accent-subtle, #f0f4ff);
}

.conv-phase-badge-dot {
  display: inline-block;
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: currentColor;
  flex-shrink: 0;
}

.conv-phase-badge-label {
  line-height: 1;
}

/* mobile: shrink gap when card is narrow */
@media (max-width: 360px) {
  .conv-phase-badge {
    font-size: 9px;
    padding: 2px 4px 2px 3px;
  }
  .conv-phase-badge-dot {
    width: 4px;
    height: 4px;
  }
}
```

### CSS variable references

The new CSS uses these variables already defined in `style.css`:
- `--hairline`, `--surface`, `--surface2`, `--body`, `--muted` — confirmed present
- `--accent` — may be `#3366cc` (Wikimedia blue); check `style.css` for the exact variable name; substitute hard-coded fallback if not yet defined
- `--accent-muted`, `--accent-subtle` — add to the `:root` block if not present:
  ```css
  --accent-muted: #c8d8f5;
  --accent-subtle: #f0f4ff;
  ```

---

## Tests

No automated JS/Python tests needed for this purely visual change. Manual verification:

1. Check all three card sections on the authenticated homepage render badge rows (active conversations, browse, completed).
2. Verify a pos=0 conversation shows all six badges locked (greyed, low opacity).
3. Verify a pos=1 (submission only) conversation shows "Vote" unlocked, all others locked.
4. Verify a pos=4 (closed) conversation shows all six badges unlocked.
5. Check narrow viewport (375 px): badges should not overflow the card; the `@media` rule kicks in.
6. Check dark mode (add `prefers-color-scheme: dark` or toggle the dark theme): locked badges must remain readable; unlocked badges should not clash.

---

## Verification

1. Run dev server: `cd v2 && flask run` (or Docker compose).
2. Navigate to the authenticated homepage with at least one conversation in each phase (or use test fixtures).
3. Screenshot the conversation card grid at:
   - Desktop (1200 px)
   - Narrow (375 px)
   - Dark mode (if theme toggle is available)
4. Confirm the old dot rail is gone and the badge rows render as expected.
5. Confirm the phase-journey legend strip (`.phase-legend`) at the top of the page is unaffected (it is separate from the per-card rail).

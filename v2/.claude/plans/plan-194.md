# Plan: #194 — Design: replace inline SVG icons in phase legend with polished image assets

**Verdict: FITS** — The phase-legend strip exists in `home.html` and is actively maintained. Replacing hand-drawn inline SVGs with polished, consistent SVG files is a pure visual improvement that aligns with the design-principles goal of low-friction, high-quality UI.

---

## Context

The phase journey legend in `v2/templates/home.html` (lines 111–178) renders four inline SVGs inside `.phase-legend-icon` spans. They are 18×18 px paths drawn by hand. The CSS puts them in a 36×36 px circular badge with `currentColor` stroke. The issue asks to produce four polished SVG files, delivered to `v2/static/img/phases/`, with wiring into the template as a follow-up dev ticket.

This plan covers **asset creation only** (the four SVG files). Template wiring is a natural follow-on once assets are approved.

---

## Files to change

| Action | Path |
|--------|------|
| Create directory | `v2/static/img/phases/` |
| Create asset | `v2/static/img/phases/explore.svg` |
| Create asset | `v2/static/img/phases/arguments.svg` |
| Create asset | `v2/static/img/phases/informed-vote.svg` |
| Create asset | `v2/static/img/phases/report.svg` |

No template or CSS changes in this ticket. The existing inline SVGs remain in place until a follow-up dev ticket replaces them.

---

## Implementation steps

### Design constraints (apply to all four icons)

- ViewBox: `0 0 24 24` (standard 24 px grid)
- No hard-coded fill/stroke colors — use `stroke="currentColor"` and `fill="none"` so the icon inherits CSS `color` (works in both light and dark themes via `.phase-legend-icon { color: var(--body) }`)
- `stroke-width="1.75"`, `stroke-linecap="round"`, `stroke-linejoin="round"` — consistent stroke language
- Optical weight should be similar across all four icons
- Each icon should be legible at 18 px (the size used in the legend) and look good at 24 px (used on a potential conversation landing page strip)

### Icon designs

**`explore.svg`** — voting on statements, forming an opinion  
Concept: a ballot / checklist — two horizontal lines (statement rows) with a tick on the right.  
Paths:
```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
     stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
  <!-- two statement rows -->
  <line x1="3" y1="9"  x2="14" y2="9"/>
  <line x1="3" y1="15" x2="14" y2="15"/>
  <!-- checkmark -->
  <polyline points="16,11 18.5,15.5 22,7"/>
</svg>
```

**`arguments.svg`** — weighing pros and cons  
Concept: a balance / scales with a vertical stem and two hanging pans.  
Paths:
```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
     stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
  <!-- stem -->
  <line x1="12" y1="3" x2="12" y2="21"/>
  <!-- base -->
  <line x1="5"  y1="21" x2="19" y2="21"/>
  <!-- beam -->
  <line x1="5"  y1="8"  x2="19" y2="8"/>
  <!-- left pan arc -->
  <path d="M5,8 L3,13 Q5,17 7,13 Z"/>
  <!-- right pan arc -->
  <path d="M19,8 L17,13 Q19,17 21,13 Z"/>
</svg>
```

**`informed-vote.svg`** — re-voting after seeing arguments (combo of vote + scale)  
Concept: a small ballot on the left with a compact scales glyph on the right, unified in a single viewbox.
```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
     stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
  <!-- ballot rows (left half) -->
  <line x1="2"  y1="9"  x2="11" y2="9"/>
  <line x1="2"  y1="14" x2="11" y2="14"/>
  <!-- mini scales (right half): stem -->
  <line x1="17" y1="4"  x2="17" y2="20"/>
  <line x1="13" y1="20" x2="21" y2="20"/>
  <!-- mini scales: beam -->
  <line x1="14" y1="8"  x2="20" y2="8"/>
  <!-- mini scales: left pan -->
  <path d="M14,8 L13,10.5 Q14,13 15,10.5 Z"/>
  <!-- mini scales: right pan -->
  <path d="M20,8 L19,10.5 Q20,13 21,10.5 Z"/>
</svg>
```

**`report.svg`** — final published results document  
Concept: a document/page with three lines of text (lines progressively shorter to suggest content).
```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
     stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
  <!-- page outline with folded corner -->
  <path d="M6,2 H15 L20,7 V22 H6 Z"/>
  <polyline points="15,2 15,7 20,7"/>
  <!-- text lines -->
  <line x1="9"  y1="11" x2="17" y2="11"/>
  <line x1="9"  y1="14" x2="17" y2="14"/>
  <line x1="9"  y1="17" x2="14" y2="17"/>
</svg>
```

---

## Tests

No automated tests. This is a pure visual asset delivery.

Manual check after asset creation:
1. Open each SVG file directly in a browser and confirm it renders cleanly at 18 px and 24 px.
2. Temporarily embed one icon into `home.html` (replace one `.phase-legend-icon` inline SVG with `<img src="{{ url_for('static', filename='img/phases/explore.svg') }}" width="18" height="18" alt="">`) and check in both light and dark mode that `currentColor` renders correctly.
   - Note: `<img>` does NOT inherit `currentColor`; for theming to work the icon must be inlined or served via a CSS `mask-image`. Preferred approach: keep them as inline SVG `<use>` references or replace the `<img>` with the raw SVG markup. Document the chosen wiring approach in the follow-up dev ticket.

---

## Verification

1. Run the Flask dev server: `cd v2 && flask run` (or via Docker compose).
2. Navigate to the authenticated homepage.
3. Confirm the four legend icons render — they will still be the old inline SVGs until the dev follow-up. The new asset files can be spot-checked at `/static/img/phases/explore.svg` etc. in the browser.
4. Screenshot the legend strip at full width and at a narrow (375 px) viewport to confirm no overflow.

**Known follow-up:** A dev ticket should replace the four inline SVG blocks in `home.html` lines 115–174 with `<img>` tags pointing at the new assets (or with Jinja `include` of the SVG source for `currentColor` support). That wiring is out of scope for this design-asset ticket.

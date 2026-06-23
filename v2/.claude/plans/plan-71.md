# Issue #71 — Mobile cards: no tap affordance when action labels are hidden

**Verdict:** FITS

## Context

On screens ≤600px, `.conv-card-action` is hidden (`display: none` at line ~338 of `v2/static/style.css`). This leaves "Open to you" cards with only a title and a blue dot — no visual cue that the card is tappable.

The project uses a card-based home layout (`home.html` + `.conv-card` in `style.css`). Adding a right-aligned chevron visible only on mobile is the lowest-risk approach: it requires no template logic change and no new JS.

Key existing styles in `v2/static/style.css`:
- `.conv-card` defined around line 384
- `.conv-card-action { display: none; }` inside the `@media (max-width:600px)` block around line 337–338
- `.conv-card-left`, `.conv-card-title-row`, `.conv-card-action` are the layout elements

## Files to change

1. `v2/templates/home.html` — add a `<span class="conv-card-chevron" aria-hidden="true">›</span>` inside `.conv-card-left` (or directly inside the `<a class="conv-card">` at the end of the card), for every non-split card.
2. `v2/static/style.css` — add `.conv-card-chevron` styles: hidden by default, displayed only in the ≤600px breakpoint, positioned right-aligned.

## Implementation steps

### 1. Identify the card markup in `home.html`

Find every `<a class="conv-card …"` block that is NOT a split card (`conv-card--split`). These represent "Open to you", active, and closed cards for the participant. Add a chevron span just before the closing `</a>`:

```html
<span class="conv-card-chevron" aria-hidden="true">›</span>
```

Place it as the last child of the `<a>` element so it can be absolutely positioned to the right.

### 2. Add CSS for `.conv-card-chevron` in `style.css`

Add after the `.conv-card-action` block (around line 488):

```css
/* ── Mobile tap chevron — visible only when action label is hidden ── */
.conv-card-chevron {
  display: none;          /* hidden on desktop — action label does the job */
  color: var(--muted);
  font-size: 20px;
  line-height: 1;
  flex-shrink: 0;
  align-self: center;
  margin-left: auto;
  padding-left: 8px;
}

@media (max-width: 600px) {
  .conv-card-chevron {
    display: block;
  }
  /* Hide chevron on split cards (they are not single-click targets) */
  .conv-card--split .conv-card-chevron {
    display: none;
  }
}
```

Because `.conv-card` uses `display: flex` and `.conv-card-left` is a flex child, the chevron needs to either be a sibling of `.conv-card-left` or be placed inside it with `margin-left: auto`. The simpler approach: add it as a direct child of `.conv-card` (after `.conv-card-left`), giving it `flex-shrink:0; align-self:center; margin-left:auto`.

### 3. Verify existing `conv-card--split` handling

Split cards already have `cursor: default` and are not single click targets — the chevron must not appear on them. The CSS rule `.conv-card--split .conv-card-chevron { display: none; }` above handles this.

### 4. Accessibility check

The `aria-hidden="true"` attribute on the span ensures screen readers ignore the decorative character. No additional ARIA changes needed.

## Tests

- `v2/tests/` — no existing mobile/CSS test suite; verify visually.
- Manual verification: resize browser to ≤600px on the home page; confirm chevron appears on tappable cards but not on split cards.
- At >600px: confirm chevron is not visible (action label shows instead).

## Verification

1. Run `flask run` from `v2/` (or the existing dev stack).
2. Open the home page at ≤600px viewport width.
3. Confirm each "Open to you" and active card shows a `›` aligned to the right.
4. Confirm split-card rows (admin-facing, if visible) do not show the chevron.
5. Confirm at 601px+ the chevron is absent and the action label is visible.

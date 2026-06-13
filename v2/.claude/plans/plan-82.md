# Issue #82 — Simplify pseudonym selection screen — too much text, participants getting lost

**Verdict:** FITS

## Context

The current `v2/templates/accept.html` join screen contains:
1. A breadcrumb / header with conversation title
2. A teaser line ("Quick setup before you start — pick a pseudonym…") at line 36
3. The pseudonym card with a sub-line ("This name appears next to your opinions…") at line 59
4. A "Stay informed" notification section (email + talk page checkboxes)
5. A "Privacy summary" section with two paragraphs (lines 110–122)
6. A `<details>` "Privacy & data handling" disclosure (lines 126–148) with three more paragraphs
7. A checkbox consent line ("I understand…") at line 159
8. The submit button

User feedback is that this is overwhelming. The goal is: pick a name → continue. Privacy detail should be minimal and scannable, moved behind a disclosure.

The functional design (`v2/spec_functional-design.md`) and `v2/pub_participant-help.md` should remain authoritative for what content must be present; nothing may be removed that is legally or ethically necessary — only reorganised.

## Files to change

1. `v2/templates/accept.html` — restructure copy and layout
2. `v2/static/style.css` — minor CSS adjustments if new layout elements need it (e.g. a "why?" inline link style)

## Implementation steps

### 1. Strip the teaser line

Remove the `<p>` at line 36 ("Quick setup before you start…"). The page title + breadcrumb already orient the user.

### 2. Shorten the pseudonym sub-line

Current (line 59):
> "This name appears next to your opinions in this consultation. It is separate from your Wikimedia username."

Replace with:
> "Your name in this consultation — separate from your Wikimedia username."

Add a small inline "why?" link that scrolls to / expands the privacy details:
```html
<a href="#privacy-details-body" class="pseudonym-why-link">why?</a>
```

### 3. Collapse the Privacy summary section into a single sentence

Replace the two-paragraph "Privacy summary" `<div>` (lines 110–122) with a single sentence inside the existing `<details>` block, merged into the foldable disclosure. Move the two paragraphs inside `<details>`. Remove the separate `<h3>Privacy summary</h3>` and its wrapper `<div class="accept-section">`.

The `<details>` summary label changes from "Privacy & data handling" to "Privacy summary & data handling" to remain self-explanatory. The body then contains all three existing paragraphs (the two moved ones + the existing three).

Result: the page shows zero privacy text by default. Users who want it open the `<details>`.

### 4. Keep the consent checkbox

The "I understand…" checkbox must remain — it is a design/trust requirement (pseudonym appears in public results). Do not remove it.

### 5. Keep the notification section

The notification section is functional and not the source of overwhelm. Keep it, but consider moving it below the pseudonym card and above the consent checkbox to group the decision flow: (a) pick name → (b) notification prefs → (c) consent → (d) submit.

Current order is already: pseudonym → notification → privacy → consent → submit. No reorder needed; just removing/collapsing the privacy text reduces the total length significantly.

### 6. CSS: style the "why?" inline link

Add in `style.css` near the `.pseudonym-card-sub` block:

```css
.pseudonym-why-link {
  font-size: inherit;
  color: var(--muted);
  text-decoration: underline dotted;
  margin-left: 4px;
}
.pseudonym-why-link:hover { color: var(--ink); }
```

## Tests

- `v2/tests/test_participant.py` (or equivalent) — check that the accept page still renders without 500 for a valid slug and unauthenticated/authenticated user.
- Visual: load `/c/<slug>/accept` and confirm the page fits on a single mobile viewport without scrolling before the pseudonym options appear.
- Accessibility: confirm `<details>` summary is keyboard accessible; `<a href="#privacy-details-body">` lands on the disclosure.
- Confirm the `aria-describedby="accept-privacy-summary-copy"` on the `<form>` element (line 43) is updated to point to the new collapsed element or removed if the element is gone.

## Verification

1. Start the dev stack.
2. Navigate to a conversation accept page as a non-joined participant.
3. Confirm: pseudonym options visible above the fold on mobile (375px viewport).
4. Confirm: privacy text is hidden by default, expandable via the `<details>`.
5. Confirm: form submits successfully and lands in the conversation.
6. Confirm: "why?" link opens/scrolls to the privacy disclosure.

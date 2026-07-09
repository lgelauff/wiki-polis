# Accessibility conventions

The accessibility patterns we encourage in wiki-polis code. Grounded in Wikimedia's own
developer guidance so a Wikimedia-ecosystem tool stays idiomatic, and aligned with our stated
**WCAG 2.1/2.2 AA** target.

**Primary source:** MediaWiki — [Accessibility guide for developers](https://www.mediawiki.org/wiki/Accessibility_guide_for_developers).
It is opinionated where WCAG is neutral and has already resolved several controversies (notably
rejecting off-screen-text hiding and favouring progressive enhancement); we follow it.

Enforcement arm: rendered-markup regression guards in `tests/test_a11y_markup.py`.

---

## Principles

1. **Progressive enhancement over graceful degradation.** Semantic HTML that works without JS first; JS only enhances. Never make JS the only path to a control.
2. **Accessibility is broader than screen readers** — keyboard, magnification, contrast, TTS, custom CSS, RTL, language, low bandwidth all count.
3. **ARIA is a last resort, not a substitute for HTML** — "keyboard navigation is simply achieved by logical DOM order." Reach for a real element before a role.
4. **Avoid workarounds that create technical debt.** Prefer future-proof code; when an interim a11y hack is unavoidable, annotate it with a "remove when #N lands" note.

## Conventions

### Semantic HTML
- Use the right element: `<button>` for actions (never `<div>/<span>` + click, never `<a href="#">` + onclick), `<ul>/<li>` for lists, real `<h1>…<h3>` for structure. *(WCAG 4.1.2 / 1.3.1)*
- Never nest interactive inside interactive (no button/link inside a link).

### Headings
- Logical, **no gaps** (never `<h1>`→`<h3>`), descriptive, unique within a level. Headings are a primary screen-reader navigation tool. *(WCAG 2.4.6)*

### Hiding things
- **Never** push content off-screen with `left:-9999px` / `text-indent:-9999px` — it breaks RTL, breaks positional mobile VoiceOver, and costs render performance.
- **Name icon-only controls with `aria-label`**, not visually-hidden label text.
- **To remove a control from assistive tech**, use `display:none` (or `tabindex="-1"` + `aria-hidden` if it must stay visible). Do not create hidden duplicate controls for API proxying; call the API from the visible control's handler.
- The clipped `.sr-only` pattern is **only** for text that must be announced but has no visual equivalent (e.g. live-region content, "(opens in a new tab)" cues) — not for hiding controls.

### Focus & keyboard
- Everything doable with a mouse must work with the keyboard. Non-native interactive elements need `tabindex="0"` **and** an Enter/Space keydown handler.
- **Always define a `:focus-visible` style wherever you define `:hover` or `:active`.** Never `outline:0` without a replacement. *(WCAG 2.4.7)*
- Avoid `tabindex > 0`; rely on DOM order.

### Names, descriptions, repetition
- Accessible **name = the concise action**; secondary/helper text goes in `aria-describedby`, not baked into the name. *(WCAG 2.4.6 "descriptive *and concise*")*
- Don't repeat the same label many times — explain once, e.g. via `aria-live="polite"`.

### Symbols, language, contrast, images
- **Avoid bare Unicode symbols** (`→ ↑ ↔`) as meaningful content. If decorative, mark the element `aria-hidden`; if meaningful, wrap in a `<span>` carrying a label/`title`.
- Set `lang` (and `dir` where relevant) so screen readers pick the right voice.
- Sufficient contrast; small text needs *more* than the bare WCAG minimum. *(WCAG 1.4.3)*
- Images: meaningful `alt`; decorative images get empty `alt` or become CSS backgrounds.

### ARIA roles
- Don't override implicit roles (`<th>`=columnheader, `<li>`=listitem); nest a child element instead.
- `role="button"`/`"dialog"`/`"alert"` only when a real element won't do; `aria-haspopup` on controls that open dialogs/menus.

### Dialogs
`aria-haspopup` on opener; `role="dialog"`; move focus in on open and **trap** it; Esc + focusable close button; rest of page `aria-hidden`/inert; return focus to opener on close.

## wiki-polis resolutions
| Situation | Convention |
|---|---|
| Icon/arrow-only affordance ("JOIN →", "↻", "↔") | decorative → `aria-hidden`; never the accessible name |
| API-only control | Do not render a hidden duplicate control; call the API from the visible control's handler |
| SR-only announcement with no visual twin | `.sr-only` clip + `aria-live` (`status`=polite / `alert`=assertive) |
| Card with title + helper text | name = title (heading); helper via `aria-describedby` |
| Listing of entities | real `<ul>/<li>` + a heading per item |
| New `:hover`/`:active` style | add a matching `:focus-visible` style in the same change |

## PR review checklist
- [ ] Real elements (`button`/`ul`/`h*`); no `div`+click, no `a href="#"`; no interactive nested in interactive.
- [ ] Heading order has no gaps; titles heading-navigable.
- [ ] Every interactive element keyboard-operable; visible `:focus-visible`.
- [ ] Accessible names concise; helper text via `aria-describedby`; no duplicated announcements.
- [ ] Decorative glyphs/arrows `aria-hidden`; meaningful symbols wrapped/labelled.
- [ ] Nothing hidden with `-9999px`; AT-removed controls use `display:none`/`tabindex=-1`.
- [ ] Contrast checked (incl. small text); images have correct `alt`.
- [ ] Interim a11y hacks carry a "remove when #N lands" note.

## Testing
- Keyboard-only sweep (Tab / Shift-Tab / Enter / Space / Esc / arrows).
- VoiceOver (⌘F5) + rotor (headings, landmarks, links); remember iOS VoiceOver is *positional*.
- axe / Lighthouse for automated catches; `tests/test_a11y_markup.py` for CI regression guards.
- Contrast checker for new colours; toggle `prefers-reduced-motion` and RTL where layout is non-trivial.

## See also
- MediaWiki [Accessibility guide for developers](https://www.mediawiki.org/wiki/Accessibility_guide_for_developers) · [Accessibility](https://www.mediawiki.org/wiki/Accessibility)
- Wikipedia [Manual of Style/Accessibility](https://en.wikipedia.org/wiki/Wikipedia:Manual_of_Style/Accessibility)
- [`spec_design-principles.md`](spec_design-principles.md)

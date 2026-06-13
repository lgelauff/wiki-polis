# Issue #202 — Arguments screen: skip argument without opening it

**Verdict:** FITS

## Context

The arguments tab shows one `arg-block` panel at a time (subsequent panels have `arg-block--hidden`). Each panel contains two `contribute-wrapper` divs (pro and con). To skip a side currently, the participant must click the "Add one for-argument, or skip" button to open the contribute affordance, then click "Nothing to add" inside it.

Issue #202 asks for a way to skip a featured statement's contribution entirely from the panel header, without having to open each side's composer.

The backend `argument_skip` route (`/c/<slug>/arguments/<int:fs_id>/<side>/skip`, POST, line 2506 in `app.py`) already exists and handles both sides independently. The frontend JS (`checkBothGated`, `setState`) already handles transitioning a panel to done when both sides are gated.

The simplest implementation: add a "Skip this statement" button in the `at-head` of each panel that fires both pro and con skip API calls in sequence, then triggers the same "both gated" transition the existing per-side skip uses.

## Files to change

1. `v2/templates/conversation.html` — add a "Skip statement" button in the `at-head` block of each `arg-block` panel, and wire its click handler in the existing arguments JS section.
2. `v2/static/style.css` — add styles for the new skip button.

## Implementation steps

### 1. Add the skip button to the panel header in the template

Inside the `<div class="at-head">` block (around line 488 in `conversation.html`), after the `<div class="at-head-main">` and `at-steps` divs, add:

```html
{# Quick-skip button — only shown when neither side is gated yet #}
{% if not both_gate %}
<button type="button"
        class="at-head-skip-btn"
        data-fs="{{ fs.id }}"
        data-skip-pro-url="{{ url_for('participant.argument_skip', slug=conversation.slug, fs_id=fs.id, side='pro') }}"
        data-skip-con-url="{{ url_for('participant.argument_skip', slug=conversation.slug, fs_id=fs.id, side='con') }}"
        data-csrf="{{ csrf_token() }}"
        aria-label="Skip this statement">
  Skip statement
</button>
{% endif %}
```

Place it at the end of `.at-head`, before the collapse chevron span.

The button is server-rendered as hidden when `both_gate` is already true (participant already completed both sides). JS will also hide it once both sides become gated during the session.

### 2. Add CSS for `.at-head-skip-btn` in `style.css`

Add near the `.at-head` styles:

```css
.at-head-skip-btn {
  font-size: 12px;
  color: var(--muted);
  background: none;
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 3px 8px;
  cursor: pointer;
  white-space: nowrap;
  flex-shrink: 0;
  align-self: flex-start;
  margin-top: 4px;
}
.at-head-skip-btn:hover {
  color: var(--ink);
  border-color: var(--muted);
}
.at-head-skip-btn:focus-visible {
  outline: 2px solid var(--focus-ring, #2563eb);
  outline-offset: 2px;
}
```

### 3. Wire the click handler in the arguments JS section

In the JS section that handles contribute/skip (around lines 2037–2140 in `conversation.html`), add a delegated event listener on `.arg-panels` for clicks on `.at-head-skip-btn`:

```js
tab.addEventListener('click', function (e) {
  var skipBtn = e.target.closest('.at-head-skip-btn');
  if (!skipBtn) return;

  var fsId    = skipBtn.dataset.fs;
  var proUrl  = skipBtn.dataset.skipProUrl;
  var conUrl  = skipBtn.dataset.skipConUrl;
  var csrf    = skipBtn.dataset.csrf;

  skipBtn.disabled = true;
  skipBtn.textContent = 'Skipping…';

  // Fire both skips; on both succeeding, trigger the gated transition.
  Promise.all([
    fetch(proUrl, { method: 'POST', headers: { 'X-Requested-With': 'fetch', 'X-CSRFToken': csrf } }),
    fetch(conUrl, { method: 'POST', headers: { 'X-Requested-With': 'fetch', 'X-CSRFToken': csrf } }),
  ]).then(function (responses) {
    if (responses.every(function (r) { return r.ok; })) {
      // Update both contribute-wrapper states to 'skipped' so existing gating logic fires
      var panel = document.getElementById('fs-' + fsId);
      panel.querySelectorAll('.contribute-wrapper').forEach(function (w) {
        // Reuse the existing setState helper scoped to this wrapper
        // Find its skip button and simulate the skip (or call setState directly)
        setState(w, 'skipped');
      });
      // checkBothGated will be called by setState; hide the skip button
      skipBtn.remove();
    } else {
      skipBtn.disabled = false;
      skipBtn.textContent = 'Skip statement';
    }
  }).catch(function () {
    skipBtn.disabled = false;
    skipBtn.textContent = 'Skip statement';
  });
});
```

**Note on `setState`**: The existing `setState(wrapper, state)` function is defined inside a `forEach` over `.contribute-wrapper` elements (a closure per wrapper, not a named outer function). To call it from outside that closure, refactor `setState` out of the per-wrapper `forEach` into a named function that accepts `(wrapper, state)` as arguments. This is a small refactor of the existing forEach block (lines ~2037–2080).

Refactor sketch — currently:
```js
tab.querySelectorAll('.contribute-wrapper').forEach(function (wrapper) {
  function setState(s) { ... }
  ...
});
```

Refactor to:
```js
function setContributeState(wrapper, s) { ... }
tab.querySelectorAll('.contribute-wrapper').forEach(function (wrapper) {
  function setState(s) { setContributeState(wrapper, s); }
  ...
});
```

Then the delegated handler can call `setContributeState(w, 'skipped')` directly.

### 4. Hide skip button after both sides are gated (dynamic case)

At the end of `checkBothGated(panelEl)` (around line 2121), add:

```js
var headSkip = panelEl.querySelector('.at-head-skip-btn');
if (headSkip) headSkip.remove();
```

This covers the case where the user skips sides one at a time (not via the bulk skip button) and the button should disappear once both are done.

### 5. Handle already-gated panels (server-rendered)

The Jinja `{% if not both_gate %}` guard in step 1 means the button is not rendered for panels where both sides are already done on page load. No further JS needed for that case.

## Tests

- `v2/tests/test_participant.py` — add a test that POSTs to both `argument_skip` endpoints for a given `fs_id`; assert 200 and `{'ok': True}`.
- Manual: open the arguments tab with at least one featured statement. Confirm "Skip statement" button is visible in the panel header. Click it; confirm both sides transition to "skipped" state and the panel collapses/advances. Confirm the skip button disappears.
- Edge case: already skipped one side manually → click "Skip statement" → confirm only the un-skipped side fires a skip request (both endpoints are idempotent on the backend, so double-skipping is safe).

## Verification

1. Join a conversation in the arguments phase.
2. Open the Arguments tab.
3. Confirm "Skip statement" button appears in the panel header.
4. Click it; confirm both "for" and "against" columns transition to skipped state.
5. Confirm the panel collapses and advances to the next featured statement.
6. Confirm the skip button is absent on panels where both sides are already gated.

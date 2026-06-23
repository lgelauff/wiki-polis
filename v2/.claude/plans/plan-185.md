# Issue #185 — Possible bug in progress bar (shows N-1 instead of N)

**Verdict:** FITS

## Context

The reporter says: "I'm on question 3 and the meter shows 2/14 — it lags one behind."

Reading `updateProgress` in `v2/templates/conversation.html` (lines 1601–1624):

```js
function updateProgress(statements) {
  var done = 0;
  statements.forEach(function (stmt, id) { if (votedIds.has(id)) done++; });
  votesDone.textContent = done;
  ...
}
```

This is called on `particiappvotesubmitsuccess` — i.e., after a vote is cast. So when the user is "on question 3" (viewing the 3rd statement), they have voted on questions 1 and 2 → `done = 2`. The display `2/14` is technically correct as "statements voted so far".

However, from the user's perspective "I'm on question 3" naturally implies the counter should show `3/14` (the current question counts as in-progress). This is a framing mismatch, not a code bug.

**The fix:** Change the label/framing so users understand what the counter means, OR change the counter to show the current statement as in-progress (N-of-total rather than N-completed).

The lower-friction fix is a label change — rename "X / Y" to "X voted · Y total" or add a "currently on N" label — so it reads "2 voted / 14" rather than implying position.

Alternatively, change `done` to `done + 1` (capped at `total`) when a current statement exists, matching the user's mental model of "I'm on #3".

The second approach (show current position) is more intuitive and aligns with how Polis-style tools typically frame progress. It requires a one-line change plus updating the aria label.

## Files to change

1. `v2/templates/conversation.html` — `updateProgress` function (lines 1601–1624) and the progress row HTML (lines 139–149).

## Implementation steps

### Option chosen: show current position (N of total)

When the user is viewing statement N (1-indexed), show `N / total` rather than `completed / total`.

#### Step 1: Compute display count

In `updateProgress`, after computing `done`, add:

```js
// Show position (done + 1 if currently viewing a statement) rather than
// completed count, so "on question 3" reads 3/14, not 2/14.
var current = conv.statement;
var displayDone = (current !== null) ? Math.min(done + 1, total) : done;
```

#### Step 2: Update DOM

Replace:
```js
votesDone.textContent = done;
```
With:
```js
votesDone.textContent = displayDone;
```

Keep `progressBar.setAttribute('aria-valuenow', done)` using the real `done` count for accurate assistive-technology feedback, but update `aria-valuetext`:
```js
progressBar.setAttribute('aria-valuetext',
  done + ' of ' + total + ' statements voted' +
  (current !== null ? ' — viewing statement ' + displayDone : ''));
```

#### Step 3: Update the progress bar segments

The segment loop uses `i < done` for "done" segments. When viewing a new statement, segment `done` is styled as `vote-seg--current`. This already correctly highlights the current statement. No change needed here.

#### Step 4: Update label copy (optional but recommended)

In the HTML progress row (line 140–143), add a visually-hidden annotation or change the separator label:

Current:
```html
<span class="vote-progress-count">
  <span id="votes-done" class="vote-progress-voted">0</span>
  <span class="vote-progress-sep"> / </span>
  ...
```

Change the separator to something that implies position:
```html
<span class="vote-progress-sep"> of </span>
```

So it reads "3 of 14" rather than "2 / 14". "3 of 14" aligns with the user's mental model of being on statement 3.

## Tests

- `v2/tests/` — add or update any JS behaviour test if a test framework for in-template JS exists.
- Manual: start a conversation with several statements, vote on 2, observe the counter shows `3 of N` (the current statement number) before voting the 3rd, then `4 of N` after.
- Edge case: when all statements are voted (`current === null`), display should show `total of total` or `done of total` (both equal). Verify the cap `Math.min(done + 1, total)` handles this correctly when `current === null` (the `(current !== null)` guard returns `done` directly).

## Verification

1. Join a conversation with ≥5 statements.
2. Vote on statement 1. Confirm counter reads "2 of N".
3. Vote on statement 2. Confirm counter reads "3 of N".
4. Vote on all remaining statements. Confirm counter reads "N of N" (not N+1).
5. Refresh page; confirm counter initialises correctly from existing vote state.

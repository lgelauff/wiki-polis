# Plan: #129 — Cross-browser test of same-origin hardening (#106)

**Verdict: FITS — framed as a concrete test-matrix spike with a clear deliverable.**

## Context

PR #106 tightened `_validate_same_origin()` to reject requests carrying neither
`Sec-Fetch-Site` nor `Origin`. Safari never implemented `Sec-Fetch-Site` (Fetch Metadata),
but appears to send `Origin` on same-origin fetches. However, this has only been verified
manually on Safari 16+ on macOS; the full browser matrix is untested.

**Risk:** any browser/OS combination that sends neither header on a same-origin fetch will
get a silent 403 on `POST /c/<slug>/statements/new`.

**This plan delivers:**
1. A manual test checklist document (`v2/.claude/browser-matrix-test-129.md`) for human
   testers to work through.
2. A fallback patch in `v2/app.py` `_validate_same_origin()` if a gap is found.
3. Guidance on using BrowserStack / Sauce Labs for matrix testing if a local device is unavailable.

**Note:** this is primarily a human-driven test matrix (no automated browser driver covers
real Safari on iOS). The agent can prepare the test protocol, the fallback patch, and a
lightweight automated regression for the testable subset.

## Files to change

| File | Action |
|---|---|
| `v2/.claude/browser-matrix-test-129.md` | Create — test protocol + results log |
| `v2/app.py` | Edit — conditional fallback in `_validate_same_origin()` if gap confirmed |
| `v2/tests/test_same_origin.py` | Edit (or create) — unit tests for the header-absent fallback |

## Implementation steps

### Step 1 — write test protocol (`v2/.claude/browser-matrix-test-129.md`)

Document the test checklist from the issue body, plus:

```markdown
## Test setup
1. Log in to https://wiki-polis-dev.toolforge.org (Wikimedia OAuth).
2. Join or create a public conversation (slug: `test`).
3. Open browser DevTools → Network tab.

## For each browser/OS combination:
1. Navigate to the conversation page.
2. Submit a new statement.
3. In Network, find the POST to `/c/test/statements/new`.
4. Check request headers for:
   - `Sec-Fetch-Site: same-origin` — present? (Chrome/Firefox only)
   - `Origin: https://wiki-polis-dev.toolforge.org` — present?
5. Check response status: 201 (created) or 403 (blocked)?

## Expected result
At least one of `Sec-Fetch-Site` or `Origin` must be present.
A 403 response with no network error = the failure signature.

## Results table
| Browser | Version | OS | Sec-Fetch-Site | Origin | Status | Tester | Date |
|---|---|---|---|---|---|---|---|
| Safari | 16+ | macOS | absent | present | 201 ✅ | (confirmed per issue) | |
| Safari | latest | iOS 17 | ? | ? | ? | | |
...
```

### Step 2 — verify the logic in `_validate_same_origin()` (app.py ~line 880)

Read the current implementation:
```bash
grep -n -A 20 "def _validate_same_origin" v2/app.py
```

Current logic (per issue description): if neither `Sec-Fetch-Site` nor `Origin` is present,
abort 403.

**The fallback patch** (apply only if a gap is confirmed in testing):

In `_validate_same_origin()`, add a fallback before `abort(403)`: if both headers are
absent **and** the route is `conversation_statement_new`, rely on the CSRF token (already
validated before `_validate_same_origin` is called) and return without aborting.

```python
def _validate_same_origin():
    sec_fetch_site = request.headers.get('Sec-Fetch-Site')
    origin = request.headers.get('Origin')

    if sec_fetch_site:
        if sec_fetch_site != 'same-origin':
            abort(403)
        return

    if origin:
        expected = f"{request.scheme}://{request.host}"
        if origin != expected:
            abort(403)
        return

    # Neither header present. For the statement-submit route, the CSRF token
    # (validated upstream by _validate_fetch_csrf) is the compensating control.
    # This handles Safari on older iOS/macOS that omit both headers on same-origin fetches.
    if request.endpoint == 'participant.conversation_statement_new':
        return   # CSRF already validated

    abort(403)
```

**Only apply this patch if testing confirms a real gap.** If all tested browsers send at
least `Origin`, the existing code is correct and no patch is needed.

### Step 3 — add unit tests for the fallback (if patch applied)

In `v2/tests/test_same_origin.py` (or add to the existing CSRF test file), add:

```python
def test_statement_new_no_sec_fetch_no_origin_with_csrf(client, ...):
    """Browsers that send neither Sec-Fetch-Site nor Origin must still be able to
    submit a statement if the CSRF token is valid (e.g. Safari on older iOS)."""
    # POST without either header, but with a valid CSRF token
    # Expected: 201 or 403 quota, not 403 origin-blocked

def test_statement_new_no_headers_no_csrf(client, ...):
    """Without either same-origin header AND without CSRF, the request is still rejected."""
    # Expected: 400 (CSRF) or 403 (origin)
```

### Step 4 — automated check for the testable subset

Add a CI-runnable test that verifies `_validate_same_origin` behaviour for each header
combination using Flask's test client:

```python
@pytest.mark.parametrize("headers,expected_allowed", [
    ({"Sec-Fetch-Site": "same-origin"}, True),
    ({"Origin": "http://localhost"}, True),
    ({"Sec-Fetch-Site": "cross-site"}, False),
    ({"Origin": "https://evil.example.com"}, False),
    ({}, False),  # no headers, no CSRF → 403/400
])
def test_same_origin_combinations(client, headers, expected_allowed, ...):
    ...
```

## Tests

```bash
cd v2 && python -m pytest tests/test_same_origin.py -v
```

All parametrised cases should pass before and after the (conditional) patch.

## Verification

- Test matrix doc filled in with real browser results by a human tester.
- If gap found: patch applied, unit tests pass, matrix row updated with "fixed" status.
- If no gap: no code change; matrix doc filed as evidence; issue closed.
- The unit test for the "no headers + valid CSRF → allowed on statement_new" case passes
  (if patch applied).

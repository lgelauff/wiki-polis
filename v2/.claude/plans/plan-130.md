# Plan: #130 — Fix synthetic_traffic.py act_submit after CSRF validation in #106

**Verdict: FITS — explicitly called out in plan_roadmap.md § Code health ("Soak harness follow-up").**

## Context

`act_submit` sends a POST to `/c/<slug>/statements/new` with only `Origin`/`Referer` headers
and no CSRF token. After #106 landed `_validate_fetch_csrf()`, the route requires
`X-CSRFToken` or `X-CSRF-Token` or `csrf_token` form field, validated by Flask-WTF
`validate_csrf(token)`. Without it the route returns 400. The soak harness then records a
failure (400 is not in `allow_status=(401, 403, 404)`).

Additionally, the roadmap notes the `accept` step doesn't establish a Participation properly,
so `statements/new` returns 401 rather than reaching the CSRF/same-origin gate. Both issues
need fixing.

**Root cause audit (v2/synthetic_traffic.py):**

1. `act_submit` (line 265–273): sends JSON body with `Origin`/`Referer` but no `X-CSRFToken`.
2. `accept()` (lines 201–221): already fetches the Flask CSRF token from the `/accept/<slug>`
   form page and submits a pseudonym — this should establish a Participation. The `accept`
   step is likely working. The route returns 401 when the Participation exists but `phase` is
   wrong (e.g. not in Statements phase). This is also acceptable (401 is in allow_status).

The real fix needed: extract a Flask CSRF token before `act_submit` and attach it as
`X-CSRFToken`.

**How to get the Flask CSRF token in a worker:**
The `/accept/<slug>` page already contains `<input name="csrf_token" value="…">`. The
`accept()` step already captures it via `CSRF_RE`. The simplest fix: store the CSRF token
from `accept()` on `self.flask_csrf` and attach it in `act_submit`. If `accept` is skipped
(worker idx without submit action), also fetch it from `GET /c/<slug>`.

## Files to change

| File | Action |
|---|---|
| `v2/synthetic_traffic.py` | Edit — store Flask CSRF token; attach it in act_submit |

## Implementation steps

### Step 1 — store Flask CSRF token on Worker

In `Worker.__init__`, add:
```python
self.flask_csrf = None
```

### Step 2 — capture token in `accept()`

After `m = CSRF_RE.search(r.text)` (currently line 209), add:
```python
self.flask_csrf = m.group(1)
```

The CSRF_RE is already defined at module level:
```python
CSRF_RE = re.compile(r'name="csrf_token"[^>]*value="([^"]+)"')
```

### Step 3 — ensure `flask_csrf` is available even when accept skips the form

In `accept()`, when the GET `/accept/<slug>` returns 302 (already participating), the token
is not fetched from the form. Add a fallback fetch in `discover()` or a new helper:

Add a `_fetch_csrf()` helper:
```python
def _fetch_csrf(self):
    """Fetch a fresh Flask CSRF token from the conversation page."""
    r = self._req("csrf", "GET", f"/c/{self.args.slug}",
                  health={"allow_status": (302,), "expect_2xx": False})
    m = CSRF_RE.search(r.text or "")
    if m:
        self.flask_csrf = m.group(1)
```

Call this in `run()` after `self.accept()` but only when `self.flask_csrf` is still `None`
and `"submit"` is in `self.args.actions`:

```python
self.accept()
if "submit" in self.args.actions and not self.flask_csrf:
    self._fetch_csrf()
```

### Step 4 — attach CSRF token in `act_submit`

Replace the current `act_submit` call's headers:

```python
def act_submit(self):
    self.n_submit += 1
    text = f"{self.args.submit_text_prefix} w{self.idx} #{self.n_submit} — synthetic statement"
    headers = {"Origin": self.origin,
               "Referer": f"{self.args.base_url}/c/{self.args.slug}"}
    if self.flask_csrf:
        headers["X-CSRFToken"] = self.flask_csrf
    self._req("submit", "POST", f"/c/{self.args.slug}/statements/new",
              json={"text": text}, headers=headers,
              health={"allow_status": (401, 403, 404)})
```

### Step 5 — verify the Content-Type for the submit route

`act_submit` sends `json={"text": text}` (requests sets `Content-Type: application/json`).
Check `v2/app.py conversation_statement_new` to confirm it reads from `request.json`, not
`request.form`. If the route reads `request.form`, switch to `data={"text": text}` and move
the CSRF token to a form field instead of a header.

Look up in app.py:
```bash
grep -n "statement_new\|request\.json\|request\.form\|request\.get_json" v2/app.py | head -20
```

Adjust if needed.

## Tests

Run locally with `DEV_FAKE_LOGIN=1` and a `test` conversation slug:

```bash
# Baseline — confirm submit was broken (400):
python v2/synthetic_traffic.py --dry-run --slug test
# After fix — all actions should show no HEALTH VIOLATIONs:
python v2/synthetic_traffic.py --dry-run --slug test
```

Expected output: `OK — no health invariant violated.`

Also check the `submit` action row in the summary shows `201×N` or `403×N` (quota), not
`400×N`.

## Verification

- `--dry-run` exits 0.
- Summary table for `submit` shows `201` or `403` status codes only (not `400`).
- A 60-second soak (`--duration 60 --actions vote:5,results:2,submit:1`) completes without
  health failures.

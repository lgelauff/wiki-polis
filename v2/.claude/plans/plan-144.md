# Plan — #144: Admin: disable seed statement and CSV import for permanently closed conversations

**Issue:** #144 — Admin: disable seed statement and CSV import features for permanently closed conversations
**Verdict:** FITS — adds a server-side guard and UI feedback for out-of-phase seed controls; not yet implemented.

## Context

The two seed routes (`admin_statement_seed`, `admin_statement_seed_import` in `v2/app.py` lines 2003–2170)
currently have no phase-gate. `_require_mod_for_conv` checks moderator auth but not conversation
state. The template `v2/templates/admin_statements.html` shows the seed + CSV import forms
unconditionally.

The phase model (#140, now shipped) defines:
- **Preparation** = no phase flags on yet (preparation phase; seed ok)
- **Submission** = `phase_submission == True` (statements open; seed ok)
- **Past submission** = `phase_submission == False` AND at least one other phase flag set (blocked)
- **Closed** = `conv.active == False` (blocked regardless)

A helper `_seed_allowed(conv)` can encode this cleanly: `conv.active and (conv.phase_submission
or not any([conv.phase_personal_results, conv.phase_argument_mapping]))`.

The template already receives `conversation` — add a `seed_locked` boolean from the view
function and gate the forms on it.

## Files to change

- `v2/app.py` — two places:
  1. Add `_seed_allowed(conv)` helper (~5 lines).
  2. `admin_statement_seed` (line ~2005): guard with `_seed_allowed`; flash + redirect on fail.
  3. `admin_statement_seed_import` (line ~2023): same guard.
  4. `admin_conversation_statements` (line ~1958): pass `seed_locked=not _seed_allowed(conv)` to template.
- `v2/templates/admin_statements.html` — wrap the "Add seed statement" section (lines 20–38)
  and "Import seed statements from CSV" section (lines 40–77) with `{% if not seed_locked %}…{% else %}<locked notice>{% endif %}`.

## Implementation steps

### 1. Add helper in `app.py` (near other `_require*` helpers, around line 740)

```python
def _seed_allowed(conv: Conversation) -> bool:
    """Seed statements are only allowed in Preparation or Submission phase.

    Preparation = active, no phase flags set.
    Submission  = active, phase_submission is True.
    """
    if not conv.active:
        return False
    if conv.phase_submission:
        return True
    # In preparation: none of the downstream phase flags are on yet.
    return not any([
        conv.phase_personal_results,
        conv.phase_argument_mapping,
    ])
```

> Check `db.py` for the full list of phase flag columns (currently: `phase_submission`,
> `phase_personal_results`, `phase_argument_mapping`; also check for any informed-vote
> or public-results flag added by recent PRs) and include all downstream flags in `any([...])`.

### 2. Guard `admin_statement_seed` (around line 2006, after `conv = _require_mod_for_conv(...)`)

```python
if not _seed_allowed(conv):
    flash('Seed statements can only be added during Preparation or Submission phase.', 'error')
    return redirect(url_for('admin.admin_conversation_statements', conv_id=conv_id))
```

### 3. Guard `admin_statement_seed_import` (around line 2024, after `conv = _require_mod_for_conv(...)`)

Same flash + redirect pattern as step 2.

### 4. Pass `seed_locked` to template in `admin_conversation_statements` (around line 1958)

Add `seed_locked=not _seed_allowed(conv)` to the `render_template(...)` call.

### 5. Template: gate seed section

Replace the unconditional "Add seed statement" and "Import seed statements from CSV" sections
with a conditional block:

```jinja
{% if not seed_locked %}
  <!-- ── Add seed statement ───────────────────── -->
  … existing form …

  <!-- ── Bulk CSV import ──────────────────────── -->
  … existing form …
{% else %}
  <div class="edit-form" style="background:#fef9c3;border:1px solid #fde68a;padding:.75rem 1rem;border-radius:6px;font-size:13px;margin-bottom:1.5rem">
    <strong>Seed statements are locked.</strong>
    Seeds can only be added during Preparation or Submission phase.
    {% if not conversation.active %}
    This conversation is closed.
    {% else %}
    Statement collection has ended.
    {% endif %}
  </div>
{% endif %}
```

Use inline styles consistent with the existing flash-message style in the template
(no new CSS class needed).

## Tests

File: `v2/tests/test_admin_seed_guard.py` (new) or add to an existing admin test file.

Test cases (use Flask test client + `login_required` fixture pattern from existing tests):

1. **Preparation phase (no flags set)** — POST to seed route → 302 redirect to statements page
   (allowed; no error flash).
2. **Submission phase (`phase_submission=True`)** — POST → allowed.
3. **Past submission (`phase_submission=False`, `phase_personal_results=True`)** — POST → 302
   with flash "can only be added during Preparation or Submission phase".
4. **Closed conversation (`active=False`)** — POST to seed and seed_import → both return 302
   with the locked flash.
5. **Template: `seed_locked=True`** — render `admin_statements.html` with `seed_locked=True`
   and assert the locked notice text is present and both forms are absent.
6. **Template: `seed_locked=False`** — assert both forms are present.

## Verification

1. `pytest v2/tests/` — all pass.
2. `ruff check v2/` — clean.
3. Manually (or via `staging-chrome-test`): advance a test conversation past Submission, open
   the admin statements page — locked notice appears, no seed forms. Confirm a direct POST is
   also rejected (302 + flash, not a silent success).

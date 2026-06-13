# Issue #160: Define the logic for recommended quantities across a conversation

**Verdict: FITS** (design/implementation issue — the current `_RECOMMENDED_FEATURED = 15`
hard-coded constant is in app.py lines 475/484/601 and the issue asks to define a proper
approach; the roadmap does not mark this as deferred)

## Context

The current code has a single module-level constant `_RECOMMENDED_FEATURED = 15` in `app.py`
(line 475). It is used in two places:
- `_featured_note()` function (line 481–484): generates the advisory string
  `"N selected, 15 recommended"` for the guided transition precondition box.
- A direct f-string at line 601: `'{} recommended'.format(_RECOMMENDED_FEATURED)`.

The issue asks to:
1. Define ALL places where recommended quantities are useful.
2. Decide how each is derived (fixed default vs complexity tiers vs per-conversation).
3. Decide whether advisory only or soft-warn/gate.
4. Where the value is stored.

**Decision (to implement):**
- Keep recommendations **purely advisory** (current behaviour) — no gating.
- Use a single `RECOMMENDED` config dict in `app.py` with named keys, replacing the
  single constant. No DB column needed for the prototype.
- Surface areas: seed statements (before opening submission), featured statements
  (currently covered), arguments per featured statement (new).
- Per-conversation override is **out of scope** for this issue (no new DB column).

## Files to change

- `v2/app.py` — replace `_RECOMMENDED_FEATURED = 15` with a `_RECOMMENDED` dict; update
  all callsites; add recommended seed count display on the admin statements page context;
  add recommended arguments-per-featured count display on the featured page context.
- `v2/templates/admin_statements.html` — surface the seed-statement recommended count.
- `v2/templates/admin_featured.html` — surface the recommended arguments count (if used).
- `v2/templates/admin_conversation.html` — update any hardcoded "15 recommended" references
  to use the context variable.

## Implementation steps

### 1. `app.py` — replace constant with dict

Remove `_RECOMMENDED_FEATURED = 15` (line 475). Add:

```python
# Advisory recommended quantities — purely informational, never gate transitions.
_RECOMMENDED = {
    'seed_statements':              10,   # statements before opening submission
    'featured_statements':          15,   # for argument mapping and Phase 6
    'arguments_per_featured':        2,   # pro + con per featured statement
}
```

Update `_featured_note()` (line 481) to use `_RECOMMENDED['featured_statements']`.
Update line 601 to use `_RECOMMENDED['featured_statements']`.

### 2. `app.py` — pass recommended counts to admin templates

In `admin_conversation_statements` route, add to the template context:
```python
recommended_seeds=_RECOMMENDED['seed_statements'],
```

In `admin_conversation_featured` route, add to context:
```python
recommended_featured=_RECOMMENDED['featured_statements'],
recommended_args_per_featured=_RECOMMENDED['arguments_per_featured'],
```

### 3. `admin_statements.html` — show seed recommendation

In the "Add seed statement" section, add a note near the section heading or intro paragraph:
```jinja
<p class="muted" style="font-size:12px;margin-bottom:.5rem">
  Aim for at least {{ recommended_seeds }} seed statements before opening submission, to give
  participants a variety of positions to react to from their first visit.
</p>
```

### 4. `admin_featured.html` — show featured + argument recommendations

Near the top of the page (after the existing intro paragraph, before the Confirmed section):
```jinja
<p class="muted" style="font-size:12px;margin-bottom:.5rem">
  Aim for {{ recommended_featured }} featured statements covering the main axes of disagreement.
  Each featured statement should have at least one pro and one con argument
  ({{ recommended_args_per_featured }} total) before advancing to informed voting.
</p>
```

The confirmed count display already shows "N selected, 15 recommended" via the flash/note
mechanism — verify this is now driven by the context variable rather than the hardcoded constant
so it stays in sync.

### 5. (No DB migration needed)

All recommended values stay as Python constants for the prototype. A future issue can add a
per-conversation override column if complexity-tier or organizer-set values are needed.

## Tests

- `v2/tests/test_recommended_quantities.py`:
  - Import `_RECOMMENDED` from `app` and assert all expected keys exist with positive int values.
  - Test that the admin statements route response contains the seed recommendation text.
  - Test that the admin featured route response contains the featured recommendation count.
  - Test that the guided-transition note for featured statements uses `_RECOMMENDED['featured_statements']`
    (not a hardcoded 15) by temporarily monkeypatching the value.

## Verification

1. Run `pytest v2/tests/test_recommended_quantities.py -v`.
2. Navigate to Admin > Conversation > Statements — verify seed recommendation text appears.
3. Navigate to Admin > Conversation > Featured — verify featured/argument recommendation text appears.
4. Change `_RECOMMENDED['featured_statements']` to 20 temporarily, reload — verify both the
   guided-transition note and the featured page reflect the new value.

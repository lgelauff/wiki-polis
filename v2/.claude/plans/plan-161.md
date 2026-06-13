# Issue #161: Add explanatory guidance to the featured statements admin page

**Verdict: FITS**

## Context

`v2/templates/admin_featured.html` currently has a single short intro paragraph (~lines 13–16):
> "Featured statements appear in the argument mapping tab. Participants submit a pro and con
> argument for each, then vote on the most important arguments submitted by others."

This is accurate but minimal. The issue asks for inline guidance covering: what "featured" means,
how to choose a representative set, how many to select, consequences/irreversibility (Phase 6
seeding, effectively locked once argument mapping begins), and the difference between
system-suggested candidates and manually added (by TID) statements.

The page already distinguishes between "Confirmed" and "Suggested" sections — the Suggested
section shows system-recommended candidates that the admin confirms.

No route or DB changes required — this is a template-only change.

## Files to change

- `v2/templates/admin_featured.html` — expand the intro guidance section; add a note on
  the system-suggested vs manual distinction; add irreversibility callout.

## Implementation steps

### 1. Replace the existing intro paragraph

Current (lines 13–16):
```html
<p class="muted" style="font-size:13px;margin-bottom:1.5rem">
  Featured statements appear in the argument mapping tab. Participants submit a pro and con
  argument for each, then vote on the most important arguments submitted by others.
</p>
```

Replace with a richer guidance block:

```jinja
<div class="guidance-block" style="margin-bottom:2rem">
  <p style="margin-bottom:.75rem">
    <strong>What are featured statements?</strong> Featured statements are the curated set used
    in two phases: <em>argument mapping</em> (participants submit pro/con arguments and vote on
    them) and <em>informed voting</em> (Phase 6, participants re-vote on statements with arguments
    shown inline). Only featured statements appear in these phases — choose them carefully.
  </p>
  <p style="margin-bottom:.75rem">
    <strong>Choosing a representative set.</strong> Aim to cover the main axes of disagreement,
    not just the most-voted or most-obvious statements. Include statements that represent minority
    views and edge cases, so argument mapping captures the full spectrum. A set of around
    {{ recommended_featured }} statements is a reasonable target for most consultations.
  </p>
  <p style="margin-bottom:.75rem">
    <strong>System-suggested vs manually added.</strong> The <em>Suggested</em> section below
    shows statements the system has flagged as candidates (based on vote engagement). Confirming
    a suggestion moves it to <em>Confirmed</em>. You can also add any statement directly by its
    statement ID (TID) using the form below — useful for statements that are important but may
    not surface automatically.
  </p>
  <p class="consequence-callout" style="font-size:13px;border-left:3px solid var(--warning,#f59e0b);padding-left:.75rem;color:var(--body)">
    <strong>Irreversible once argument mapping begins.</strong> When you open the Argument
    Mapping phase, participants start submitting arguments against this set. Featured statements
    that already have arguments cannot safely be removed. Finalise your selection <em>before</em>
    opening Argument Mapping.
  </p>
</div>
```

Note: `recommended_featured` must be passed to this template from the route. Verify the
`admin_conversation_featured` route passes it (this overlaps with #160; if #160 is implemented
first, `recommended_featured` will already be in context; otherwise add it here).

If #160 is not yet done, add a temporary fallback: `{{ recommended_featured | default(15) }}`.

### 2. Confirm the Suggested section has a brief explanation

The Suggested section heading should have a one-line sub-note:
```jinja
<p class="muted" style="font-size:12px;margin-top:.25rem;margin-bottom:.75rem">
  System-suggested candidates based on vote engagement. Confirm to add to the featured set.
</p>
```
Add this after the `<h3 class="section-heading">Suggested</h3>` heading.

### 3. Confirm the manual-add form has a brief explanation

The "Add by statement ID" form (or however the TID-add form is labelled) should include:
```jinja
<p class="muted" style="margin-bottom:.5rem;font-size:13px">
  Add any statement by its Polis statement ID (TID). Use this for important statements that
  were not automatically suggested.
</p>
```

## Tests

- `v2/tests/test_admin_featured_guidance.py`:
  - GET `/admin/conversation/<id>/featured` for a moderator returns 200.
  - Response HTML contains "representative set" guidance text.
  - Response HTML contains "Irreversible" warning text.
  - Response HTML contains "System-suggested" explanation.

## Verification

1. Run `pytest v2/tests/test_admin_featured_guidance.py -v`.
2. Log in as admin, navigate to a conversation's Featured statements page.
3. Verify the guidance block renders with all four paragraphs.
4. Verify the irreversibility callout has visible left-border styling.
5. Verify the Suggested section and manual-add form have their sub-notes.

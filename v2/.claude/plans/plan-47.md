# Issue #47: Cleaner admin / participant UI split with visual mode indicator

**Verdict: FITS**

## Context

The admin and participant interfaces share identical header chrome. Admin templates have ad-hoc
inline back-links (e.g. `← admin panel` in `admin_conversation.html` line 27, `← admin` in
`admin_featured.html` line 8, `← back to admin` in `admin_statements.html` line 12) instead of
using the `{% block header_crumb %}` slot that already exists in `base.html` (line 27).
`conversation.html` already uses `header_crumb` (lines 4–9) for the participant view.
`style.css` has `.header-admin-link` (line 213) but no admin-mode colour modifier on `<header>`.
The roadmap (section 4, Arguments tab) explicitly lists #47 as remaining work.

## Files to change

- `v2/templates/base.html` — add `{% block admin_mode %}{% endblock %}` on `<header>`; add
  "Admin" badge markup inside it.
- `v2/templates/admin.html` — add `{% block header_crumb %}` with "Admin" crumb; add
  `{% block admin_mode %}admin{% endblock %}`.
- `v2/templates/admin_conversation.html` — add `{% block header_crumb %}` with
  "Admin › *title*" crumb; remove inline `← admin panel` back-link (line 27); add
  `{% block admin_mode %}admin{% endblock %}`; add "View as participant →" shortcut link.
- `v2/templates/admin_featured.html` — add `{% block header_crumb %}` with
  "Admin › *title* › Featured" crumb; remove inline `← admin` back-link (line 8); add
  `{% block admin_mode %}admin{% endblock %}`.
- `v2/templates/admin_statements.html` — add `{% block header_crumb %}` with
  "Admin › *title* › Statements" crumb; remove inline `← admin` back-link (line 12); add
  `{% block admin_mode %}admin{% endblock %}`.
- `v2/templates/admin_invites.html` — add `{% block header_crumb %}` with
  "Admin › *title* › Invites" crumb; add `{% block admin_mode %}admin{% endblock %}`.
- `v2/templates/conversation.html` — add "← Manage" link in `header_crumb` block when
  `can_moderate` is true (already has the crumb block at lines 4–9; already passes
  `can_moderate` to the template at lines 633, 759).
- `v2/static/style.css` — add `.header--admin` styles for the admin mode header tint and
  "Admin" badge.

## Implementation steps

### 1. `base.html` — admin-mode class on `<header>`

Replace:
```html
<header>
```
with:
```html
<header class="{% block header_mode %}{% endblock %}">
```

### 2. `base.html` — "Admin" badge slot

Inside `<div class="header-inner">`, after the logo+crumb block, add a conditional badge:
```html
{% if self.header_mode() == 'admin' %}
  <span class="header-admin-badge" aria-label="Admin mode">Admin</span>
{% endif %}
```

### 3. `style.css` — admin header tint + badge

Add after the existing `.header-admin-link` block (~line 223):

```css
/* ── Admin-mode header tint ── */
.header--admin {
  background: var(--admin-header-bg, #f0f4f8);  /* subtle blue-grey */
  border-bottom-color: #b8c8d8;
}

.header-admin-badge {
  display: inline-block;
  padding: 1px 7px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  background: var(--admin-badge-bg, #dbeafe);
  color: var(--admin-badge-color, #1e40af);
  border-radius: 3px;
}
```

Also add to `:root` or the existing CSS variable block:
```css
--admin-header-bg: #f0f4f8;
--admin-badge-bg: #dbeafe;
--admin-badge-color: #1e40af;
```

### 4. All admin templates — `header_mode` + `header_crumb` blocks

For each admin template, add at the top (after `{% extends "base.html" %}`):

```jinja
{% block header_mode %}header--admin{% endblock %}
```

And replace the inline back-link with a proper `header_crumb` block:

**`admin.html`** (no conversation context):
```jinja
{% block header_crumb %}
<span class="header-crumb">
  <span class="header-crumb-sep">/</span>
  <a href="{{ url_for('admin.admin') }}">Admin</a>
</span>
{% endblock %}
```
Remove any existing inline admin back-link from the body.

**`admin_conversation.html`** (has `conversation` in context):
```jinja
{% block header_crumb %}
<span class="header-crumb">
  <span class="header-crumb-sep">/</span>
  <a href="{{ url_for('admin.admin') }}">Admin</a>
  <span class="header-crumb-sep">/</span>
  <span>{{ conversation.title | truncate(30, True, '…') }}</span>
</span>
{% endblock %}
```
Remove line 27 (`<a href="{{ url_for('admin.admin') }}">← admin panel</a>`) from body.
Add "View as participant →" link near the top of the page (after the title, before the
phase block):
```jinja
<a class="view-as-btn" href="{{ url_for('participant.conversation', slug=conversation.slug) }}">View as participant →</a>
```
Note: `view-as-btn` style already exists in style.css (used in admin_conversation.html line 17).

**`admin_featured.html`** (has `conversation` in context):
```jinja
{% block header_crumb %}
<span class="header-crumb">
  <span class="header-crumb-sep">/</span>
  <a href="{{ url_for('admin.admin') }}">Admin</a>
  <span class="header-crumb-sep">/</span>
  <a href="{{ url_for('admin.admin_conversation_detail', conv_id=conversation.id) }}">{{ conversation.title | truncate(20, True, '…') }}</a>
  <span class="header-crumb-sep">/</span>
  <span>Featured</span>
</span>
{% endblock %}
```
Remove line 8 (`← admin` back-link) from body.

**`admin_statements.html`** (has `conversation` in context):
Same pattern as featured, with "Statements" as the leaf crumb.
Remove line 12 (`← back to admin` back-link) from body.

**`admin_invites.html`** (has `conversation` in context):
Same pattern, with "Invites" as the leaf crumb.
Check current back-link and remove it.

### 5. `conversation.html` — "← Manage" link for moderators

The existing `header_crumb` block (lines 4–9):
```jinja
{% block header_crumb %}
<span class="header-crumb">
  <span class="header-crumb-sep">/</span>
  <span>{{ conversation.title | truncate(40, True, '…') }}</span>
</span>
{% endblock %}
```
Replace with:
```jinja
{% block header_crumb %}
<span class="header-crumb">
  <span class="header-crumb-sep">/</span>
  <span>{{ conversation.title | truncate(40, True, '…') }}</span>
  {% if can_moderate %}
    <a class="header-manage-link" href="{{ url_for('admin.admin_conversation_detail', conv_id=conversation.id) }}" aria-label="Manage conversation">← Manage</a>
  {% endif %}
</span>
{% endblock %}
```

Add `.header-manage-link` style in style.css (small, muted, same feel as `.header-admin-link`).

## Tests

- `v2/tests/` — add `test_admin_ui_split.py`:
  - Test that each admin route response contains `header--admin` in the HTML.
  - Test that `conversation.html` response for a moderator contains `← Manage`.
  - Test that `conversation.html` response for a non-moderator does NOT contain `← Manage`.
  - Test that admin pages do NOT contain the old inline `← admin panel` / `← admin` text
    as plain anchor links in the page body (i.e. they moved to header_crumb).

## Verification

1. Run `pytest v2/tests/test_admin_ui_split.py -v`.
2. Start the dev server (`flask run` from v2/), log in as admin.
3. Navigate to the admin panel — verify blue-grey header tint and "Admin" badge.
4. Navigate to a conversation detail page in admin — verify crumb shows "Admin / Title".
5. Navigate to Featured statements — verify "Admin / Title / Featured" crumb.
6. Switch to participant view via "View as participant →" — verify header returns to normal.
7. As a moderator on `conversation.html`, verify "← Manage" link appears in header crumb.
8. As a regular participant, verify "← Manage" does not appear.

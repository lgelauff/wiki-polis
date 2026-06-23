# Plan — #57: Docs: instruction pages for writing good statements and arguments

**Issue:** #57 — Docs: instruction pages for writing good statements and arguments
**Verdict:** FITS — two static in-app pages not yet implemented; source material exists and is ready.

## Context

No help/guide routes exist in `v2/app.py` (confirmed by grep). Source copy is in
`docs/research/05-website-copy.md` (branch `research/statement-principles`; the relevant
sections are already on `main`). The two pages required:

1. `/help/statements` — writing good statements
2. `/help/arguments` — writing good arguments (wiki-polis-specific feature)

These need to be linkable standalone URLs (for facilitators to share) and also linked from:
- The statement submission form (in `v2/templates/conversation.html`)
- The argument submission form (in `v2/templates/conversation.html`)

## Files to change

- `v2/app.py` — add a `help_bp` Blueprint (or add routes to the existing `main_bp`) with two
  `@bp.get` routes.
- `v2/templates/help_statements.html` — new template (statement guidance page).
- `v2/templates/help_arguments.html` — new template (arguments guidance page).
- `v2/templates/conversation.html` — add "Writing tips" links near the statement and argument
  submission forms.

## Implementation steps

### 1. Routes in `app.py`

Add near the bottom of the main-blueprint routes (after the home/conversation routes):

```python
@main_bp.get('/help/statements')
def help_statements():
    return render_template('help_statements.html')

@main_bp.get('/help/arguments')
def help_arguments():
    return render_template('help_arguments.html')
```

No `@login_required` — these pages must be publicly accessible so facilitators can share the
URL before a conversation starts.

### 2. Template: `help_statements.html`

Extend `base.html`. Content drawn verbatim from `docs/research/05-website-copy.md` section
"How to submit a statement" plus the four principles table from `docs/research/02-statement-writing-guide.md`.

Structure:
```
{% extends "base.html" %}
{% block content %}
<div class="container" style="max-width:680px">
  <h1>Writing good statements</h1>
  <p class="muted"><a href="{{ url_for('main.home') }}">← home</a></p>

  <p>A statement is a short claim that participants vote on. How it is written affects
  whether the votes produce useful signal.</p>

  <h2>The core rules</h2>
  <dl>
    <dt>One claim per statement</dt>
    <dd>If you want to say two things, submit two statements. A compound statement forces
    participants to split their vote and produces ambiguous results.</dd>

    <dt>Neutral phrasing</dt>
    <dd>Describe the situation rather than argue for a conclusion. Other participants make up
    their own minds.</dd>

    <dt>Be specific</dt>
    <dd>Vague statements ("things should be better") produce near-universal agreement that
    tells us nothing useful.</dd>

    <dt>Statement form, not a question</dt>
    <dd>Write a claim ("The Foundation should publish X"), not a question ("Shouldn't the
    Foundation publish X?").</dd>
  </dl>

  <h2>Examples</h2>
  <table>
    <thead><tr><th>Statement</th><th>Problem</th></tr></thead>
    <tbody>
      <tr>
        <td>"Wikipedia should require reliable sources and editors should disclose conflicts of interest."</td>
        <td>Two separate claims. Split them.</td>
      </tr>
      <tr>
        <td>"Shouldn't the Wikimedia Foundation be more transparent?"</td>
        <td>A question, not a statement.</td>
      </tr>
      <tr>
        <td>"The Wikimedia Foundation should publish a detailed annual report on how discretionary grants are allocated."</td>
        <td style="color:#166534">Good — one specific, falsifiable claim.</td>
      </tr>
    </tbody>
  </table>
</div>
{% endblock %}
```

Use the existing table/base styles; no new CSS.

### 3. Template: `help_arguments.html`

Same structure. Content from `docs/research/05-website-copy.md` section "How to write a good
argument" and `docs/research/04-arguments.md`.

Structure:
```
{% extends "base.html" %}
{% block content %}
<div class="container" style="max-width:680px">
  <h1>Writing good arguments</h1>
  <p class="muted"><a href="{{ url_for('main.home') }}">← home</a></p>

  <p><strong>Arguments are a wiki-polis feature.</strong> They are not part of standard Polis.
  After voting on a statement, you can add an argument explaining your reasoning. Arguments
  are read by other participants and facilitators — they are <em>not</em> used by the
  voting algorithm.</p>

  <h2>What makes a good argument</h2>
  <dl>
    <dt>State your direction</dt>
    <dd>Make clear whether you are arguing for or against the statement.</dd>

    <dt>Add a reason, not just your vote</dt>
    <dd>"I agree because this is important" adds no information. State a mechanism, consequence,
    or precedent.</dd>

    <dt>One point per argument</dt>
    <dd>If you have multiple reasons, write multiple arguments.</dd>

    <dt>Be specific</dt>
    <dd>Name the mechanism or consequence you have in mind.</dd>

    <dt>Engage with the claim, not with other participants</dt>
    <dd>Arguments are not a reply thread.</dd>
  </dl>

  <h2>Examples</h2>
  <table>
    <thead><tr><th>Argument</th><th>Problem</th></tr></thead>
    <tbody>
      <tr>
        <td>"I disagree because this would be bad for the project."</td>
        <td>Restates the vote; adds nothing.</td>
      </tr>
      <tr>
        <td>"<strong>Against:</strong> This would disproportionately affect new editors, who are
        less likely to know sourcing conventions and more likely to be discouraged by rejection."</td>
        <td style="color:#166534">Good — direction stated, specific mechanism named.</td>
      </tr>
    </tbody>
  </table>
</div>
{% endblock %}
```

### 4. Link from `conversation.html`

Find the statement submission form and argument submission form in `v2/templates/conversation.html`.
Add a small "Writing tips" link next to or below each submit button:

For statements:
```html
<a href="{{ url_for('main.help_statements') }}" target="_blank" rel="noopener"
   class="muted" style="font-size:12px">Writing tips ↗</a>
```

For arguments:
```html
<a href="{{ url_for('main.help_arguments') }}" target="_blank" rel="noopener"
   class="muted" style="font-size:12px">Writing tips ↗</a>
```

`target="_blank"` keeps the participant in the conversation flow. Check whether the current
form uses a modal or inline form (read `conversation.html` before editing) to place the link
correctly without breaking layout.

## Tests

Add to `v2/tests/test_routes.py` (or a new `test_help.py`):

1. `GET /help/statements` → 200, response body contains "Writing good statements".
2. `GET /help/arguments` → 200, response body contains "wiki-polis feature".
3. Both routes accessible without login (test with unauthenticated client).

## Verification

1. `pytest v2/tests/` — all pass.
2. `ruff check v2/` — clean.
3. Visit `/help/statements` and `/help/arguments` in browser; confirm readable standalone pages.
4. Open a conversation in the voting view and confirm "Writing tips" links appear near both
   the statement and argument submission forms.

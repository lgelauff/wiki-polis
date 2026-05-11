# Particiapp Web Components

Source: subprojects/particiapp-web-components/particiapp-web-components.js + doc/, read 2026-05-11.

All components must be descendants of `<pa-conversation>`. That element fetches conversation data from Particiapi and propagates state to children.

---

## Components

### `<pa-conversation>`

Root element. Required attributes:

| Attribute | Description |
|---|---|
| `base` | Particiapi base URL |
| `conversation-id` | Polis zinvite code |
| `disabled` | Disables all interactions |

Polls Particiapi for new statements and results automatically once loaded.

**CSS custom states** (use as `pa-conversation:state(loaded) { ... }`):

| State | Meaning |
|---|---|
| `loading` | Fetching conversation data |
| `loaded` | Data loaded successfully |
| `error` | Failed to load |
| `inactive` | Conversation is closed |
| `unauthenticated` | Auth required but user not logged in |

---

### `<pa-statement>`

Displays the current statement injected by `<pa-conversation>`. Content inside is shown only when there are no more statements (`no-statements` state) — use for a completion message.

**CSS custom states:** `no-statements`

---

### `<pa-vote-button>`

| Attribute | Description |
|---|---|
| `type` | Vote type (`agree` / `disagree` / `pass`) |
| `disabled` | Disables the button |

**CSS part:** `pa-vote-button::part(button)` — styles the inner `<button>`.

**CSS custom states:** `inactive`

Dispatches `particiappvotesubmit` event (bubbles) with:
- `event.statementID` — the statement ID
- `event.value` — vote value (-1=agree, 0=neutral, 1=disagree)

`<pa-conversation>` then dispatches `particiappvotesubmitsuccess` or `particiappvotesubmiterror`.

---

### `<pa-submit-button>`

| Attribute | Description |
|---|---|
| `submitfor` | `id` of associated `<input>` or `<textarea>` |
| `disabled` | Disables the button |

**CSS part:** `pa-submit-button::part(button)`

`<pa-conversation>` dispatches `particiappstatementsubmitsuccess` or `particiappstatementsubmiterror` after submission.

---

### Other components

| Component | Purpose |
|---|---|
| `<pa-topic>` | Displays conversation topic |
| `<pa-description>` | Displays conversation description |
| `<pa-login-button>` | Login trigger; hidden when auth disabled |
| `<pa-notifications-checkbox>` | Notification opt-in |

---

## Integration pattern for wiki-polis

Flask templates own the full page; web components handle only the voting loop.

```html
<script type="module" src="/static/particiapp-web-components.js"></script>

<pa-conversation
  base="/proxy/particiapi"
  conversation-id="{{ conversation.polis_id }}">

  <pa-statement>
    <p>You've voted on all available statements. Check back later for new ones.</p>
  </pa-statement>

  <pa-vote-button type="agree">Agree</pa-vote-button>
  <pa-vote-button type="disagree">Disagree</pa-vote-button>
  <pa-vote-button type="pass">Pass</pa-vote-button>

  <div id="propose-prompt" hidden>
    <p>Have a better way to put this?</p>
    <textarea id="propose-input" maxlength="1000"></textarea>
    <pa-submit-button submitfor="propose-input">Submit alternative</pa-submit-button>
    <button id="propose-skip">Skip</button>
  </div>

</pa-conversation>

<script>
  const conv = document.querySelector('pa-conversation');
  const prompt = document.getElementById('propose-prompt');

  conv.addEventListener('particiappvotesubmitsuccess', () => {
    prompt.hidden = false;
  });
  document.getElementById('propose-skip').addEventListener('click', () => {
    prompt.hidden = true;
  });
  conv.addEventListener('particiappstatementsubmitsuccess', () => {
    prompt.hidden = true;
    document.getElementById('propose-input').value = '';
  });
</script>
```

`base` points to a Flask proxy route — the browser never talks to the VPS directly.

---

## Styling

```css
pa-vote-button::part(button) {
  background: #fff;
  border: 2px solid currentColor;
  border-radius: 4px;
  padding: 0.5rem 1.5rem;
  cursor: pointer;
}

pa-conversation:state(loading) { opacity: 0.5; }

pa-statement:state(no-statements) pa-vote-button { display: none; }
```

# wiki-polis — Implementation Plan

## Overview

A lightweight Flask wrapper hosted on Toolforge that gates access to a Polis conversation via MediaWiki OAuth. The Polis embed handles proposal submission, voting, assignment algorithm, and consensus math. The wrapper handles identity, stability, and framing.

---

## Stack

| Layer | Choice | Reason |
|---|---|---|
| Backend | Python / Flask | Fits Toolforge, same as wall-of-faces |
| Database | MariaDB | Stable xid storage, free on Toolforge |
| Auth | MediaWiki OAuth 2.0 | Native Wikimedia identity |
| Frontend | Vanilla JS + minimal CSS | No build step |
| Proposals/voting/math | Polis (pol.is hosted) | No custom backend needed |

---

## Database schema

Small table — only needed for stable xid across potential account renames:

```sql
CREATE TABLE participants (
  id           INT AUTO_INCREMENT PRIMARY KEY,
  mw_user_id   INT          NOT NULL UNIQUE,  -- numeric MW user ID, stable across renames
  mw_username  VARCHAR(255) NOT NULL,          -- display name, updated on rename
  xid          VARCHAR(64)  NOT NULL UNIQUE,   -- sha256 hash, set on first login, never changes
  created_at   DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

**On first login:** generate xid (sha256 of mw_user_id), store row.
**On subsequent logins:** look up by mw_user_id, retrieve stable xid. Update mw_username if it changed (rename case).

---

## Application structure

```
wiki-polis/
  app.py               # Flask app, routes, ADMIN_USERS, INTRO_TEXT, OUTRO_TEXT
  auth.py              # MediaWiki OAuth flow (based on wall-of-faces)
  db.py                # MariaDB connection, participant upsert
  templates/
    base.html
    index.html         # Intro text + Polis embed + outro text
  static/
    style.css          # Polis-inspired styling
  requirements.txt
  README.md
```

---

## Participant flow

1. User arrives → redirected to MediaWiki OAuth if not logged in
2. After auth → xid looked up or created in MariaDB
3. Page renders with:
   - Custom intro text (configurable in app.py)
   - Stripped-down Polis embed (see embed config)
   - Custom outro text (configurable in app.py)
4. Polis handles everything inside the embed: proposal submission, voting, assignment, math

---

## Page layout

Styled to echo Polis's visual language (clean sans-serif, white cards, `#3498db` blue) but with custom framing above and below the embed. Intro and outro text are configurable strings in `app.py`.

```
┌─────────────────────────────────────────────┐
│  [Logo / event name]              [username] │  ← header, Polis blue
├─────────────────────────────────────────────┤
│                                             │
│  INTRO TEXT                                 │  ← configurable, supports HTML
│  (context, purpose, what is expected)       │
│                                             │
├─────────────────────────────────────────────┤
│                                             │
│  ┌─────────────────────────────────────┐   │
│  │  [voting card]                      │   │  ← Polis embed (stripped)
│  │  agree / pass / disagree            │   │
│  │                                     │   │
│  │  [proposal write box]               │   │
│  └─────────────────────────────────────┘   │
│                                             │
├─────────────────────────────────────────────┤
│                                             │
│  OUTRO TEXT                                 │  ← configurable, supports HTML
│  (next steps, links, thank you)             │
│                                             │
└─────────────────────────────────────────────┘
```

Configurable in `app.py`:
```python
CONVERSATION_ID = "9r7fkvxyjb"
EVENT_NAME      = "My Consultation"
INTRO_TEXT      = """
    <p>We are collecting proposals for ...</p>
    <p>Please <strong>submit your own proposal</strong> first,
       then vote on others.</p>
"""
OUTRO_TEXT      = """
    <p>Thank you for participating. Results will be shared at ...</p>
"""
```

---

## Polis embed configuration

```html
<div class="polis"
  data-conversation_id="{{ conversation_id }}"
  data-xid="{{ participant.xid }}"
  data-x_name="{{ participant.mw_username }}"
  data-ucst="false"
  data-ucsd="false"
  data-ucsh="false"
  data-ucsf="false"
  data-ucsv="false">
</div>
<script async src="https://pol.is/embed.js"></script>
```

Strips out: topic header, description, help text, footer, visualization.
Leaves: voting cards + proposal submission write box.

---

## Admin interface

Access controlled by a plain list of MediaWiki usernames in `app.py` (same pattern as wall-of-faces):

```python
ADMIN_USERS = []  # add usernames here
```

Protected via `@admin_required` decorator checking `session['username']` against the list.

Admin functions:
- Moderation of proposals happens directly in the Polis moderator UI at `pol.is/m/<conversation_id>`
- Local admin page (if needed) shows participant count and xid table

---

## MediaWiki OAuth flow

Same pattern as wall-of-faces. Key difference: MediaWiki OAuth returns a stable numeric `user_id` — use this (not the username) as the basis for xid generation, so xid survives account renames.

```python
mw_user_id   = token['user_id']      # stable numeric ID
mw_username  = token['username']     # may change on rename
xid          = hashlib.sha256(str(mw_user_id).encode()).hexdigest()
```

**Note:** Requires registering a new OAuth consumer at:
https://meta.wikimedia.org/wiki/Special:OAuthConsumerRegistration

Separate consumer from wall-of-faces (different tool, different callback URL).
Can reuse the same OAuth flow code.

---

## Toolforge deployment

- Register tool at https://toolsadmin.wikimedia.org
- Deploy as a Kubernetes webservice (Python container)
- MariaDB provisioned via Toolforge database service
- Secrets (OAuth consumer key/secret) stored in Toolforge's secret management
- Docs: https://wikitech.wikimedia.org/wiki/Portal:Toolforge

---

## Analysis

Polis handles clustering and consensus math internally. Researcher access:
- Export conversation data from pol.is (votes.csv, comments.csv, participants-votes.csv)
- Join xid in export with local MariaDB to recover MediaWiki usernames
- Further analysis in Python as needed

---

## Phases

### Phase 1 — Core (MVP)
- [ ] Register OAuth consumer on Meta-Wiki
- [ ] Flask app with MediaWiki OAuth (based on wall-of-faces)
- [ ] MariaDB participants table + xid logic
- [ ] Index page with framing text + stripped Polis embed
- [ ] Deploy to Toolforge

### Phase 2 — Polis
- [ ] Admin page showing participant count
- [ ] Styling — make framing text prominent, embed well-integrated
- [ ] Test rename edge case

### Phase 3 — Notifications
- [ ] Register a bot account on Meta-Wiki for sending notifications
- [ ] Configure bot credentials as Toolforge secrets
- [ ] Implement `action=emailuser` sending for participants with `notify_email=True`
- [ ] Implement talk page posting for participants with `notify_talk_page=True`

### Phase 4 — Analysis
- [ ] Export script: join Polis CSV xid with local participants table
- [ ] Recover mw_usernames for full analysis dataset

---

## Open questions (future)

- Should participants see a simple progress indicator (e.g. "you've voted on X proposals")?
- Do we need the conversation_id configurable at runtime, or hardcoded is fine?
- Multi-language support needed?

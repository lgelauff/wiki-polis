# Particiapi API Reference

Source: read from subprojects/particiapi/particiapi/api.py, 2026-05-11.

All routes are under the `/api` prefix. Base URL locally: `http://127.0.0.1:8000`.

---

## Authentication

With `PARTICIAPI_AUTHENTICATION_DISABLED=True`, auth checks are relaxed.
Routes marked `@session_required` need a session (created via `POST /api/session`).
Routes marked `@auth_required` work without a session when auth is disabled.

### Create session

```
POST /api/session?create=true
```

Returns `{"csrf_token": "...", "authenticated": false}`. Store the session cookie and use the token for all subsequent POST/PUT requests.

---

## Conversations

### Get conversation

```
GET /api/conversations/<conversation_id>
```

No auth required. `conversation_id` is the Polis zinvite (e.g. `3rf5ssn9ns`).

Example response:
```json
{
  "topic": "Test conversation",
  "description": "Testing wiki-polis",
  "description_html": "<div>Testing wiki-polis</div>",
  "is_active": true,
  "statements_allowed": true,
  "notifications_available": true,
  "results_available": false,
  "seed_statements": {}
}
```

`results_available` is `vis_type <> 0` in Polis — false by default.

### Get results

```
GET /api/conversations/<conversation_id>/results/
```

No auth required.

---

## Statements

### Get statements

```
GET /api/conversations/<conversation_id>/statements/
```

Requires `@auth_required`.

### Post statement

```
POST /api/conversations/<conversation_id>/statements/
Content-Type: application/json
X-CSRF-Token: <token>

{"text": "Statement text here"}
```

Requires `@session_required`. Field is `text`, not `txt`.

---

## Participant

### Get participant info

```
GET /api/conversations/<conversation_id>/participant
```

Returns dummy value when auth disabled and no session exists.

### Get / set notifications

```
GET  /api/conversations/<conversation_id>/participant/notifications
PUT  /api/conversations/<conversation_id>/participant/notifications
```

---

## Votes

### Cast vote

```
PUT /api/conversations/<conversation_id>/votes/<tid>
Content-Type: application/json
X-CSRF-Token: <token>

{"value": -1}
```

`tid` is the statement ID (integer). Vote values:

```
AGREE    = -1
NEUTRAL  =  0
DISAGREE =  1
```

A user cannot vote on their own statement — returns 403.

---

## CSRF

All `POST`/`PUT` routes require an `X-CSRF-Token` header. Get the token from `POST /api/session?create=true`.

---

## Local setup notes

- Polis API (port 8001) requires `X-Forwarded-Proto: https` on all POST requests (normally set by Traefik)
- Create conversations via Polis API: `POST http://127.0.0.1:8001/api/v3/conversations` with session cookies
- Polis cookies are scoped to `.polis.particiapp.internal` — must be passed manually with curl against `127.0.0.1`
- Polis login: `POST /api/v3/auth/login` sets `token2`, `uid2`, `e` cookies (domain-scoped)
- Full setup: `v2/cache/local-setup.md`

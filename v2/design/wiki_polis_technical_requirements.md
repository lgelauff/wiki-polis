# Technical Requirements & Stack

# Core Technology Stack

## Frontend

### Recommended

- React
- TypeScript
- Vite
- TailwindCSS

### Additional Packages

```bash
react-router-dom
zustand
axios
react-query
clsx
```

---

## Backend

### Recommended

- Node.js
- TypeScript
- Express or Fastify

### Additional Packages

```bash
express
passport
passport-mediawiki-oauth
express-session
connect-pg-simple
helmet
cors
zod
pino
```

---

# Database

## Primary Database

PostgreSQL

## Recommended Extensions

```sql
pg_trgm
uuid-ossp
```

---

# Deployment Environment

## Toolforge

### Required Components

- Kubernetes webservice
- PostgreSQL access
- OAuth consumer registration
- ingress configuration

---

# Infrastructure Components

## Reverse Proxy

Recommended:
- nginx ingress

---

## HTTPS

Use Toolforge-managed TLS.

---

# Authentication

## Wikimedia OAuth

Recommended Flow:

```text
User
  → MediaWiki OAuth
  → wiki-polis auth layer
  → Polis session
```

---

# Session Management

## Recommended

PostgreSQL-backed sessions.

### Packages

```bash
express-session
connect-pg-simple
```

---

# Frontend State Management

## Recommended

Use Zustand.

Avoid:
- legacy Redux complexity

---

# Styling

## Recommended

TailwindCSS.

Goals:
- fast iteration
- responsive UI
- simplified design system

---

# API Layer

## Recommended Structure

```text
/api
  /auth
  /statements
  /arguments
  /votes
  /moderation
```

---

# Moderation Infrastructure

## Required Features

- audit logs
- abuse reports
- rate limiting
- admin controls

### Packages

```bash
rate-limiter-flexible
```

---

# Logging

## Recommended

```bash
pino
```

Structured logging simplifies Toolforge debugging.

---

# Analytics Export Pipeline

## Export Formats

- CSV
- JSONL

## Export Targets

- external analytics service
- research tooling
- ML experimentation

---

# Recommended Analytics Stack (External)

NOT on Toolforge initially.

## Suggested

Python ecosystem:

```bash
pandas
numpy
scikit-learn
sentence-transformers
umap-learn
```

---

# CI/CD

## Recommended

GitHub Actions.

### Tasks

- linting
- tests
- deployment packaging

---

# Testing Stack

## Frontend

```bash
vitest
playwright
```

## Backend

```bash
jest
supertest
```

---

# Security Requirements

## Required

- CSP headers
- CSRF protection
- secure cookies
- OAuth state validation
- rate limiting

### Packages

```bash
helmet
csurf
```

---

# Performance Goals

## Voting Actions

Target:
- under 150ms perceived latency

## Statement Loading

Target:
- infinite-scroll friendly
- lightweight payloads

---

# Accessibility Goals

## Required

- keyboard navigation
- screen reader compatibility
- mobile usability

---

# Recommended Repository Structure

```text
wiki-polis/
  frontend/
  backend/
  analytics/
  infrastructure/
  docs/
```

---

# Suggested Initial Team Roles

## Needed

- frontend engineer
- backend engineer
- Toolforge deployment engineer
- UX/product designer
- moderation/community lead

---

# Initial Non-Goals

Do NOT initially build:

- AI moderation
- threaded discussions
- nested comments
- semantic ranking
- real-time chat
- reputation systems

Focus on:
- stability
- engagement
- clustering integrity

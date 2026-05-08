# Required Polis Changes

## Overview

This document lists the required modifications to Polis to support Wiki-Polis functionality.

The goal is to preserve:
- voting matrix architecture
- clustering engine
- lightweight interaction

while extending:
- identity handling
- frontend interaction
- deliberation depth
- return engagement

---

# 1. Authentication Changes

## Required

Replace Polis-native auth assumptions with Wikimedia OAuth integration.

## Tasks

- Disable anonymous participation
- Add Wikimedia OAuth login flow
- Integrate existing wiki-polis session logic
- Map Wikimedia usernames
- Add rights/permissions system
- Add admin/mod roles

## Technical Areas

Likely affected:
- authentication middleware
- session handling
- frontend auth state
- user models

---

# 2. Frontend Modernization

## Required

Modernize Polis UI without changing core voting loop.

## Tasks

- update styling
- improve mobile responsiveness
- improve accessibility
- simplify navigation
- improve conversation browsing
- improve onboarding

## Important

Do NOT slow:
- statement loading
- vote submission
- navigation speed

---

# 3. Featured Statement System

## Required

Introduce curated “central statements”.

## New Features

- statement_featured boolean
- admin selection interface
- featured statement ranking
- featured statement feeds

## Purpose

Only featured statements gain deeper deliberation layers.

---

# 4. Pro/Con Argument System

## Required

Introduce second-order argument objects.

## New Database Objects

### statement_arguments

```sql
id
statement_id
type ENUM('pro','con')
text
created_by
created_at
deleted_at
```

### argument_votes

```sql
id
argument_id
user_id
vote
created_at
```

---

# 5. New API Endpoints

## Required Endpoints

### Statements

- GET featured statements
- PATCH feature statement
- GET statement arguments

### Arguments

- POST argument
- DELETE argument
- VOTE argument
- LIST arguments

---

# 6. Moderation Systems

## Required

Introduce moderation tooling for:
- statements
- arguments
- abuse

## Features

- hide argument
- feature statement
- rate limit
- moderation logs
- report abuse

---

# 7. Discovery & Return Systems

## Required

Encourage repeat visits.

## Features

- “new since last visit”
- trending statements
- featured debates
- recently active debates
- personalized rediscovery

---

# 8. Analytics Export Layer

## Required

Support external analytics experimentation.

## Export Types

- votes
- statements
- argument graphs
- timestamps
- anonymized user ids

---

# 9. Toolforge Compatibility Changes

## Required

Adapt Polis deployment assumptions.

## Tasks

- Kubernetes deployment configs
- Toolforge ingress configuration
- environment variable management
- PostgreSQL connectivity adaptation
- OAuth callback configuration

---

# 10. Iframe & Session Handling

## Required

Support embedded deployment safely.

## Challenges

- third-party cookies
- CSP headers
- session persistence
- redirect handling

## Required Testing

- mobile browsers
- Firefox
- Safari
- Wikimedia embedding contexts

---

# Stable Testing Points

# Stable Point 0

Vanilla Polis deployment works.

---

# Stable Point 1

OAuth authentication works reliably.

---

# Stable Point 2

Modernized frontend usable on desktop/mobile.

---

# Stable Point 3

Featured statement workflow operational.

---

# Stable Point 4

Pro/con system operational.

---

# Stable Point 5

Recurring engagement systems operational.

---

# Stable Point 6

Analytics exports operational.

---

# Areas That Should NOT Be Changed Initially

Avoid changing:
- core clustering math
- vote matrix generation
- agree/disagree/pass model
- core analytics pipeline

Preserve these until substantial real-world usage data exists.

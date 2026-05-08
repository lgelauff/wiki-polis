# Wiki-Polis Design Plan

## Vision

Wiki-Polis is a Wikimedia-integrated deliberation and opinion-clustering platform inspired by Polis.

The system is designed to:
- encourage repeated participation
- surface meaningful disagreement
- cluster participants by voting behavior
- encourage idea discovery
- preserve low-friction interaction
- avoid traditional social media threading dynamics

This project intentionally preserves Polis' core strengths:
- lightweight interaction
- opinion clustering
- emergent consensus discovery

while extending it with:
- pro/con argument layers
- recurring engagement mechanics
- Wikimedia OAuth integration
- moderation and curation workflows

---

# Core Product Principles

## Preserve Atomicity

Statements remain short and atomic.

Avoid:
- long essays
- threaded discussions
- nested replies

---

## Preserve Fast Interaction

The core loop remains:

1. See statement
2. Agree / Disagree / Pass
3. Continue

Every additional feature must preserve speed.

---

## Encourage Return Visits

Users should return because:
- new statements exist
- new arguments exist
- their clusters evolved
- featured statements changed
- new debates emerged

---

## Avoid Reddit Dynamics

Do NOT introduce:
- nested threads
- direct argument battles
- infinite replies
- quote wars

The system should remain:
- exploratory
- curiosity-driven
- lightweight

---

# Product Architecture

## Core Objects

### Conversation

A deliberation space.

### Statement

An atomic claim users can vote on.

### Vote

Agree / Disagree / Pass.

### Argument

Optional pro/con explanation attached to a featured statement.

### Argument Vote

Simple endorsement vote on usefulness.

---

# System Overview

## High-Level Architecture

```text
MediaWiki OAuth
        ↓
wiki-polis auth/session layer
        ↓
Modified Polis frontend/backend
        ↓
PostgreSQL
        ↓
(optional export)
External analytics
```

---

# Stable Development Phases

# Phase 0 — Infrastructure Validation

## Goal

Deploy unmodified Polis on Toolforge with Wikimedia OAuth.

## Tasks

- Deploy Polis on Toolforge Kubernetes
- Connect PostgreSQL
- Configure ingress
- Configure HTTPS
- Integrate MediaWiki OAuth
- Validate iframe/session behavior
- Validate persistent login

## Deliverable

A functioning Wikimedia-authenticated Polis deployment.

## Stable Point 0

Community can:
- log in
- create conversations
- vote on statements

No custom features yet.

---

# Phase 1 — Authentication & Permissions Layer

## Goal

Integrate existing wiki-polis authentication stack.

## Tasks

- Integrate session handling
- Map Wikimedia identities
- Add admin/moderator roles
- Add conversation permissions
- Add anti-abuse protections

## Deliverable

Wikimedia-native authentication and moderation.

## Stable Point 1

Community can:
- authenticate through Wikimedia
- moderate discussions
- manage permissions

---

# Phase 2 — Frontend Modernization

## Goal

Improve UX while preserving Polis interaction model.

## Tasks

- Re-theme frontend
- Improve mobile UX
- Improve navigation
- Improve statement discovery
- Improve responsiveness
- Add “continue exploring” flows

## Deliverable

Modernized, community-testable frontend.

## Stable Point 2

Community can:
- browse comfortably
- repeatedly interact
- test engagement flows

---

# Phase 3 — Featured Statements

## Goal

Introduce curated “central statements”.

## Tasks

- Add featured statement flag
- Add admin curation UI
- Add featured-statement surfacing
- Add analytics indicators

## Deliverable

Statements can become focal points for deeper interaction.

## Stable Point 3

Community can:
- identify important statements
- experience curated debates

---

# Phase 4 — Pro/Con Layer

## Goal

Add lightweight argument ecology.

## Tasks

- Add pro/con arguments
- Add argument voting
- Add moderation tools
- Add character limits
- Add ranking/sorting

## Rules

Arguments are:
- atomic
- short
- non-threaded

## Deliverable

A richer deliberation layer.

## Stable Point 4

Community can:
- add pro arguments
- add con arguments
- vote on arguments

---

# Phase 5 — Return Engagement Systems

## Goal

Increase recurring participation.

## Tasks

- Add “new since last visit”
- Add notifications
- Add evolving featured statements
- Add resurfacing logic
- Add discovery feeds

## Deliverable

A sustainable recurring interaction system.

## Stable Point 5

Community can:
- revisit evolving debates
- discover new material
- build long-term participation habits

---

# Phase 6 — Analytics Export Pipeline

## Goal

Support advanced external analytics.

## Tasks

- Add structured exports
- Add anonymization options
- Add clustering exports
- Add scheduled export jobs

## Deliverable

Analytics-ready data pipeline.

## Stable Point 6

External researchers can:
- analyze clusters
- experiment with embeddings
- build visualizations

---

# Moderation Design

## Moderation Goals

Prevent:
- spam
- abuse
- brigading
- argument flooding

while preserving:
- openness
- curiosity
- dissent

---

## Recommended Controls

- rate limiting
- admin statement featuring
- admin argument moderation
- abuse reporting
- soft deletion
- audit logs

---

# UX Principles

## Core Screen

The voting interface must remain visually dominant.

Arguments should feel:
- optional
- secondary
- enriching

not mandatory.

---

## Keep Cognitive Load Low

Every screen should optimize for:
- quick understanding
- fast decisions
- curiosity continuation

---

# Future Extensions

Potential future additions:

- AI-generated summaries
- semantic clustering
- argument synthesis
- proposal merging
- multilingual translation
- recommendation systems

These should NOT be part of initial MVP.

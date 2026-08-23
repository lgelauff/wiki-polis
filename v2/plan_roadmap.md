# Roadmap

> **Forward-looking plan** — what's next, ordered roughly by dependency. Reflects
> intent and priorities, not commitments, and changes often. For what's already been
> built, see [`log_changelog.md`](log_changelog.md); for how the app is meant to work,
> see [`spec_functional-design.md`](spec_functional-design.md). Items link their GitHub issues.

The launch bar (decision **D-GA**) is **feature-complete + hardened**: the agreed
feature set shipped, the blueprint refactor done, CI/tests in place, monitoring set up,
and the launch-blocking privacy statement published.

---

## 1. Production hardening

Production is **live** at `wiki-polis.toolforge.org` (Toolforge Flask app + VPS backend
up). Provisioning, OAuth, secrets, and the Flask↔VPS wiring are done. Remaining
operational hardening:

- **Backups — top priority, not confirmed running**
  ([#139](https://github.com/lgelauff/wiki-polis/issues/139)). Production is live without
  verified backups; the plan (daily `pg_dump` → Backblaze B2 via `rclone`, 14-day
  retention, dead-man's-switch alert, restore drill in the runbook) is scoped on #139 but
  not yet running. Address before other hardening.
- Monitoring / alerting — deferred (D-MON,
  [#49](https://github.com/lgelauff/wiki-polis/issues/49)).

(Stack how-to: [`guide_deployment.md`](guide_deployment.md). The pre-launch deployment
plan has been retired to the local-only `archive/`.)

## 2. Documentation

This documentation effort is largely complete; the original wave plan has been retired
to the local-only `archive/`.
Launch-blocking item: the **privacy statement (N2)**, drafted toward the 180-day
retention commitment (decision D-PRIV), pending legal/comms review.

## 3. Code health

- **SPA/API foundation** — active. Establish a versioned same-origin browser API,
  application-service boundaries, generated TypeScript contracts, and a strangler
  migration to React. Dependency order and issue map: [`plan_spa-foundation.md`](plan_spa-foundation.md).

- **Blueprint refactor** — ✅ **done.** `app.py` decomposed into `proxy_bp` / `admin_bp` /
  `participant_bp`; `_register_routes` complexity 177→33. Steps 1–4 (PR #88), 5–6 (#97),
  7 (#98), 8 (#99), 9 (#100); issues #89–93 closed. See
  [`log_changelog.md`](log_changelog.md).
- **Soak harness follow-up**
  ([#130](https://github.com/lgelauff/wiki-polis/issues/130)) — `synthetic_traffic.py`
  soaks the proxy/vote path, but its `act_submit` step broke after the same-origin CSRF
  validation landed (#106) and the accept step doesn't establish a Participation, so
  `statements/new` returns 401 and is not exercised. Fix the accept step so
  statement-submit gets soak coverage too.
- **Testing strategy / CI** — decision pending (D-TEST); recommendation in
  `.claude/testing-strategy-recommendations.md`. Leaning toward a CI gate on PRs plus
  coverage for the untested risky paths (proxy, reveal-window timing, Polis-Postgres
  SQL, statement-quota race).
- **Pre-launch hardening review** (from the archived `plan.md`) — confirm whether these
  are still open and fix if so: `argument_unvote` cross-conversation join, restricting
  proxy `DELETE` to mods/admins, and backup-cron error handling. (Other pre-launch items
  — the `_is_emailable` login timeout, argument moderation — are already done.)

## 4. Product / UX

- **Voting** — ✅ "change vote" reopens + resubmits to Polis
  ([#69](https://github.com/lgelauff/wiki-polis/issues/69)), the three-action footer
  ([#64](https://github.com/lgelauff/wiki-polis/issues/64)), and the slug-format hint on
  validation ([#68](https://github.com/lgelauff/wiki-polis/issues/68)) all shipped.
  Remaining: mobile tap affordance on listing cards
  ([#71](https://github.com/lgelauff/wiki-polis/issues/71)).
- **Arguments tab** — ✅ the visual + interaction overhaul to the design handoff (Screen 2)
  shipped (PR #174): status strip, dashed contribute affordance, reserved checkbox slot,
  importance-vote gating, the top-of-tab explanation
  ([#80](https://github.com/lgelauff/wiki-polis/issues/80)), the clarified
  importance-vote unlock state ([#11](https://github.com/lgelauff/wiki-polis/issues/11)),
  and the Arguments-phase toggle gated on ≥1 featured proposal
  ([#12](https://github.com/lgelauff/wiki-polis/issues/12)). Remaining: resolve the
  concurrent-active-phases tab navigation
  ([#79](https://github.com/lgelauff/wiki-polis/issues/79)) and the cleaner
  admin/participant UI split with a visual mode indicator
  ([#47](https://github.com/lgelauff/wiki-polis/issues/47)). _(The detailed visual spec
  lives in the design-handoff doc; the pre-rename build-log history has the full
  checklist.)_
- **Results / identity** — ✅ participant results tab fixed
  ([#81](https://github.com/lgelauff/wiki-polis/issues/81)) and the reveal-window end date
  + "what happens next" now shown on closed conversations
  ([#70](https://github.com/lgelauff/wiki-polis/issues/70)). Remaining: simplify the
  pseudonym selection screen ([#82](https://github.com/lgelauff/wiki-polis/issues/82)).
- **Internal-link removal still needed.** Per D-PRIV (clarified), a voluntary reveal is
  permanent and is no longer nullified by the app. The remaining work is a separate
  data-minimisation mechanism that removes the *internal* account↔pseudonym link for
  non-revealed participations by the 180-day commitment.
- **xid anonymisation — salting done, mapping-rotation still open.** The old
  `sha256(mw_user_id)` form was brute-forceable from sequential MW user IDs. The **salt**
  half of the fix has shipped: xid is now `HMAC(secret, subject)`, versioned by
  `xid_key_version`, and forwarded conversation-scoped (#96). Still open: **delete/rotate**
  the xid↔uid mapping at the retention window so removing the internal link actually
  anonymises the Polis vote data — non-trivial because xid is the live participant identity
  in Polis (re-keying orphans existing votes). Relates to the security model (N11).
  *(partially done — salting shipped; rotation pending —
  [#96](https://github.com/lgelauff/wiki-polis/issues/96))*

## 5. Deferred / later

- ~~**Phase 6 — informed voting**~~ ✅ Implemented (PR #115, 2026-06-04); standalone
  phase6-init hardened (PR #179). Data model, admin init, participant UI, vote route. See
  `log_changelog.md` for detail. Follow-up: informed-voting card layout polish
  ([#119](https://github.com/lgelauff/wiki-polis/issues/119)), a Phase-2-vs-informed
  results report ([#122](https://github.com/lgelauff/wiki-polis/issues/122)), and the
  "Done" completion screen after all cards are voted/skipped
  ([#128](https://github.com/lgelauff/wiki-polis/issues/128)).
- **Return engagement** — notifications (talk page / email), "new since last visit".
- **Analytics export** — structured export of votes / clusters / arguments.
- **Admin & ops** — ban participant
  ([#60](https://github.com/lgelauff/wiki-polis/issues/60)), per-conversation
  participants tab ([#42](https://github.com/lgelauff/wiki-polis/issues/42)), statement
  advising module ([#56](https://github.com/lgelauff/wiki-polis/issues/56)), centralised
  log aggregation ([#49](https://github.com/lgelauff/wiki-polis/issues/49)),
  buildservice migration ([#55](https://github.com/lgelauff/wiki-polis/issues/55)).

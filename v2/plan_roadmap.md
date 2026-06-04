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

- **Backups — top priority, not confirmed running.** Production is live without
  verified backups; set up / confirm the nightly `pg_dump` → offsite, then rehearse a
  restore. Address before other hardening.
- Monitoring / alerting — deferred (D-MON,
  [#49](https://github.com/lgelauff/wiki-polis/issues/49)).

(Stack how-to: [`guide_deployment.md`](guide_deployment.md). The pre-launch deployment
plan has been retired to the local-only `archive/`.)

## 2. Documentation

This documentation effort — see
[`docs/plan_doc-improvement.md`](docs/plan_doc-improvement.md) for the wave plan.
Launch-blocking item: the **privacy statement (N2)**, drafted toward the 180-day
retention commitment (decision D-PRIV), pending legal/comms review.

## 3. Code health

- **Blueprint refactor** — ✅ **done.** `app.py` decomposed into `proxy_bp` / `admin_bp` /
  `participant_bp`; `_register_routes` complexity 177→33. Steps 1–4 (PR #88), 5–6 (#97),
  7 (#98), 8 (#99), 9 (#100); issues #89–93 closed. See
  [`log_changelog.md`](log_changelog.md).
- **Soak harness follow-up** — `synthetic_traffic.py` soaks the proxy/vote path; its
  accept step doesn't yet establish a Participation, so `statements/new` returns 401 and is
  not exercised. Fix the accept step so statement-submit gets soak coverage too.
- **Testing strategy / CI** — decision pending (D-TEST); recommendation in
  `.claude/testing-strategy-recommendations.md`. Leaning toward a CI gate on PRs plus
  coverage for the untested risky paths (proxy, reveal nullification, Polis-Postgres
  SQL, statement-quota race).
- **Pre-launch hardening review** (from the archived `plan.md`) — confirm whether these
  are still open and fix if so: `argument_unvote` cross-conversation join, restricting
  proxy `DELETE` to mods/admins, and backup-cron error handling. (Other pre-launch items
  — the `_is_emailable` login timeout, argument moderation — are already done.)

## 4. Product / UX

- **Voting** — "change vote" reopens + resubmits to Polis
  ([#69](https://github.com/lgelauff/wiki-polis/issues/69)); three-action footer polish
  ([#64](https://github.com/lgelauff/wiki-polis/issues/64)); slug-format hint on
  validation ([#68](https://github.com/lgelauff/wiki-polis/issues/68)); mobile tap
  affordance ([#71](https://github.com/lgelauff/wiki-polis/issues/71)).
- **Arguments tab** — visual + interaction overhaul to the design handoff (Screen 2):
  status strip, dashed contribute affordance, reserved checkbox slot, importance-vote
  gating ([#79](https://github.com/lgelauff/wiki-polis/issues/79),
  [#80](https://github.com/lgelauff/wiki-polis/issues/80),
  [#47](https://github.com/lgelauff/wiki-polis/issues/47)); clarify when importance
  voting unlocks ([#11](https://github.com/lgelauff/wiki-polis/issues/11)) and gate the
  Arguments phase toggle on ≥1 featured proposal
  ([#12](https://github.com/lgelauff/wiki-polis/issues/12)). _(The detailed visual spec
  lives in the design-handoff doc; the pre-rename build-log history has the full
  checklist.)_
- **Results / identity** — fix the participant results tab
  ([#81](https://github.com/lgelauff/wiki-polis/issues/81)); simplify the pseudonym
  selection screen ([#82](https://github.com/lgelauff/wiki-polis/issues/82)); show the
  reveal-window end date on closed conversations
  ([#70](https://github.com/lgelauff/wiki-polis/issues/70)).
- **Identity reveal must be permanent (not nullified).** Per D-PRIV (clarified), a
  voluntary reveal is permanent; only the *internal* account↔pseudonym link is removed
  (≤180 days). The current code nullifies revealed links at the retention window —
  change `_nullify_expired_reveals` to stop touching reveals. *(pending — reconcile
  `spec_functional-design.md` to the model first)*
- **xid is reversible — weak anonymisation.** `xid = sha256(mw_user_id)` and MW user IDs
  are sequential, so the xid can be brute-forced back to an account. Removing the
  internal link at the retention window does **not** anonymise the Polis vote data,
  because the xid is recomputable from a user ID. Fix: **salt** the hash with a
  per-deployment secret, and/or **delete/rotate** the xid mapping at anonymisation —
  non-trivial because xid is the live participant identity in Polis (re-keying orphans
  existing votes). Needs design; relates to the security model (N11). *(pending —
  [#96](https://github.com/lgelauff/wiki-polis/issues/96))*

## 5. Deferred / later

- ~~**Phase 6 — informed voting**~~ ✅ Implemented (PR #115, 2026-06-04). Data model,
  admin init, participant UI, vote route. See `log_changelog.md` for detail.
  Follow-up: dedup table for repeat votes, 409 UX, tab on closed convs, admin
  warning for un-seeded confirmed statements.
- **Return engagement** — notifications (talk page / email), "new since last visit".
- **Analytics export** — structured export of votes / clusters / arguments.
- **Admin & ops** — seed CSV import
  ([#61](https://github.com/lgelauff/wiki-polis/issues/61)), ban participant
  ([#60](https://github.com/lgelauff/wiki-polis/issues/60)), per-conversation
  participants tab ([#42](https://github.com/lgelauff/wiki-polis/issues/42)), statement
  advising module ([#56](https://github.com/lgelauff/wiki-polis/issues/56)), centralised
  log aggregation ([#49](https://github.com/lgelauff/wiki-polis/issues/49)),
  buildservice migration ([#55](https://github.com/lgelauff/wiki-polis/issues/55)).

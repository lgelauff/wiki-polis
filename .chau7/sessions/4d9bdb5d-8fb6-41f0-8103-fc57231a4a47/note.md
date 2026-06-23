 Accessibility Audit — wiki-polis participant front-end

  Scope: the participant-facing front (base.html, home.html, conversation.html, accept.html, reveal.html, forbidden_invite_only.html,
  static/style.css, and the two vendored Particiapp web-component bundles). Standard: WCAG 2.1/2.2 AA. Code audited at: main @ b5b22a3
  (repo updated from 80 commits behind). Admin templates (admin*.html) were out of scope — say the word and I'll run them next.

  Bottom line: this is a above-average front-end for a11y — lang, zoomable viewport, a global :focus-visible outline,
  [hidden]{display:none!important}, genuine keyboard handling (arrow-key tabs, focus management on the vote loop, triadGuard that
  correctly gates aria-disabled buttons), and an exemplary accept.html (radiogroup + sr-only live status + aria-busy + role="alert").
  The gaps cluster around screen-reader announcements in the dynamic voting loop, toggle-button state, a few contrast tokens, and form
  labelling.

  ★ Insight ─────────────────────────────────────
  The recurring theme isn't missing markup — it's the gap between
  *visual* state and *programmatic* state. This app does a lot of
  optimistic, JS-driven DOM mutation (vote → next statement, pick →
  checkmark, error → text swap). Sighted users see each change; the
  accessibility tree never hears about most of them. accept.html (a
  static form) is nearly perfect; conversation.html (a live app) is
  where the announcements leak. That's the classic SPA a11y failure
  mode, and it's very fixable.
  ─────────────────────────────────────────────────

  ---
  Moderate

 

 
  
  
  ---
  Minor / polish

  
  Worth acknowledging (done right)

  lang="en" + zoomable viewport; [hidden]{display:none!important}; global :focus-visible (5.13:1); accept.html's radiogroup + sr-only
  role="status" + aria-busy + role="alert"; non-color-redundant card status on home.html (status is in the aria-label, dots are
  aria-hidden); arrow/Home/End tab nav; triadGuard correctly blocking activation of aria-disabled cards; disciplined focus moves
  through the vote→triad→composer flow; CSRF + escapeHtml on injected argument text.

  ---
  Priority order to fix

  1. S1 (statement announcement) and S2 (toggle state) — these block the core experience non-visually.
  2. M1, M2 (labels + alerts) — small, high-leverage diffs.
  3. M3, M4 (contrast tokens + textarea focus) — mostly CSS.
  4. M5, M6 + minors.

  One genuine design decision is worth your call before I touch S1: how should a new statement be announced? The two idioms trade off
  differently —

  - aria-live region (statement is spoken automatically, focus stays on the vote buttons so the rhythm is "hear statement → vote"
  without a tab) — smoother, but live regions can be missed if the user is navigating, and verbose statements interrupt.
  - Move focus to the statement (tabindex="-1" + .focus(); the user lands on the text, reads, then tabs to vote) — more robust and
  predictable, but adds a tab per cycle and changes the keyboard rhythm you've carefully built around focusing the vote button.

  Given your loop already does deliberate focus management, I lean toward the live-region approach so I don't disturb the existing
  focus flow — but it's your UX. Want me to implement the fixes (I'd start with S1/S2/M1/M2 and can do the CSS token changes as a
  second pass), and/or save this report to v2/audit/ alongside the existing security_best_practices_report.md convention?
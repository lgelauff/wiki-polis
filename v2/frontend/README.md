# Wiki Polis frontend

React/TypeScript SPA developed against the versioned Flask browser API. It is the only
browser surface: the Jinja frontend it replaced was deleted in #351, so there are no
compatibility adapters left. Every route has a canonical path at the site root
(`/c/<slug>`, `/admin/conversations/<id>/settings`, …); the `/app/*` forms are the
temporary names the migration used, they still resolve, and `src/client-routes.ts` maps
them onto the canonical ones for links.

## Commands

```sh
npm install
npm run dev
npm run typecheck
npm test
npm run build
```

Run Flask on `127.0.0.1:5000` while using Vite. The Vite proxy keeps `/api`, auth,
conversation, and admin requests on the browser's Vite origin, so existing session and
CSRF behavior is preserved without CORS.

`src/api/schema.ts` is generated from `../openapi.json`. Do not edit it manually; run
`npm run api:generate` after changing the API contract. Production output is written to
`../static/spa` and is intentionally ignored by Git. Flask serves that shell for every
`/app/*` path; `deploy.sh` runs the locked production build before restarting the service.

Feature code must use the typed adapters in `src/api/queries.ts`. Direct `fetch` calls,
legacy `/admin` form actions, and browser calls to Polis or Particiapi are contract
violations. API links between screens must point at the canonical paths, which
`canonicalClientPath()` in `src/client-routes.ts` resolves for you.

## State ownership

- TanStack Query owns server state and request lifecycle.
- React owns temporary presentation state only.
- Flask owns authorization, validation, transactions, and durable state.
- Browser code consumes capabilities and never derives permissions from roles or raw
  persistence fields.

## When a surface counts as translated

Decided on [#388](https://github.com/lgelauff/wiki-polis/issues/388). A test that asserts
English text proves nothing about wiring: the test catalogue is the real `v2/i18n/en.json`
(`testMessages` in `src/test/handlers.ts`), so `msg('home-mode-browse')` and a hardcoded
`"Browse"` render the same string. The bar below is structural: it checks that copy comes
from the catalogue, never what the English says.

- **One `qqx` test per component, for each wired surface.** Render with `renderAsQqx()`
  and assert `untranslatedCopy([root], content)` is `[]` (both in `src/test/i18n.ts`).
  It checks text nodes and readable attributes (`aria-label`, `title`, `alt`,
  `placeholder`, `aria-valuetext`), hidden elements included. Cover each state a
  participant can reach, not only the default one. Only the roots you pass are checked:
  pass a dialog or portal that renders outside the component as a root of its own. A
  surface that is already wired but has no such test gets one the next time a PR
  touches it; there is no separate roll-out PR.
- **Per component, not one sweep.** There is no suite-wide `qqx` crawl over every route.
- **Derive `content` from the fixture.** `content` is participant data the fixture
  supplied (titles, pseudonyms, statement text); whatever it lists is exempt from the
  check. Build it from the fixture's own values (the constants or objects the test
  renders), not from hand-typed strings, so interface copy cannot slip into the
  allow-list.
- **`qqx`, as the server serves it.** Under `?uselang=qqx` the catalogue entry is `(key)`,
  or `(key: $1, $2)` for a message with parameters, and on screen the values replace the
  `$n`. The server and the test catalogue must agree. `untranslatedCopy` strips only the
  `(key` opening of keys the catalogue has, so parameter values stay in the text and are
  checked: English passed in as a parameter is caught.
- **Dates use a fixed locale.** Compute expected dates with an explicit locale, for
  example `formatDate('en', …)` from `src/i18n/dates.ts`, never
  `Intl.DateTimeFormat(undefined, …)`, which agrees with itself on every machine.
- **Mutation check, by hand.** After writing a test, break the code once and see it go
  red: restore a literal, echo the server's English, swap two states, or drop a `$1`.
  Each PR that adds a qqx test carries this checklist line in its description:

  ```md
  - [ ] Each new qqx test went red when I broke the wiring (restored a literal, echoed server English, swapped states, or dropped a `$1`).
  ```

- **One Dutch walk before stage 3 exits.** `qqx` cannot catch plural rules, word order or
  messages with inline HTML. Before stage 3 of [`../plan_i18n.md`](../plan_i18n.md)
  exits, walk through the site once in Dutch against the full local stack (Docker
  Particiapi, Polis and Postgres plus the Flask app; the `local-e2e` agent skill drives it).

Examples to copy:
[`informed-voting-panel.test.tsx`](src/features/legacy/informed-voting-panel.test.tsx)
(`content` built mostly from fixture constants) and
[`participation-entry-page.test.tsx`](src/features/legacy/participation-entry-page.test.tsx);
[`conversation-lane-page.test.tsx`](src/features/legacy/conversation-lane-page.test.tsx)
for a dialog passed as a second root. Older tests still hand-type some `content` entries;
follow the rule above rather than them. For dates,
[`dates.test.ts`](src/i18n/dates.test.ts) and
[`final-report-page.test.tsx`](src/features/legacy/final-report-page.test.tsx).

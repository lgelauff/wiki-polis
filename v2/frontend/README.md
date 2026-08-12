# Wiki Polis frontend

React/TypeScript SPA developed against the versioned Flask browser API. This is an
additive strangler application: Jinja routes remain available until an SPA route has
behavior, accessibility, and end-to-end parity.

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

## State ownership

- TanStack Query owns server state and request lifecycle.
- React owns temporary presentation state only.
- Flask owns authorization, validation, transactions, and durable state.
- Browser code consumes capabilities and never derives permissions from roles or raw
  persistence fields.

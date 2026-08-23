# Jinja-to-React parity program

`routes.json` is the executable source of truth for the frontend migration. The target is
100% parity: route ownership, authorization states, features, behavior, accessibility,
and deterministic screenshots must all match before a page can be marked `parity`.

The manifest deliberately separates page reads from feature commands. A React screen can
exist while its feature remains unverified, and a typed command can exist while the React
screen still has no visual parity. `tests/test_frontend_parity_manifest.py` prevents new
legacy endpoints, templates, or invented API operation names from bypassing the program.

Status meanings:

- `missing`: no React implementation exists.
- `partial`: some React/API coverage exists, but route, behavior, or visual parity is absent.
- `implemented-unverified`: the replacement exists but has not passed the complete parity gate.
- `parity`: all scenarios pass and golden evidence is current.

The existing public URL is the final React URL. `/app/...` entries are temporary strangler
routes and are removed after their corresponding legacy URL is cut over.

## Visual baselines

`visual-scenarios.json` defines deterministic browser scenarios. Capture current Jinja
goldens and compare available React routes with:

```sh
cd v2
.venv/bin/python parity/visual.py capture
.venv/bin/python parity/visual.py compare
```

React is the default on canonical URLs. The runner explicitly renders Jinja with
`spa_only=0` at each canonical path, then renders React at that same path in a
fresh browser context:

```sh
.venv/bin/python parity/visual.py compare --spa-only --require-parity
```

The `/app/...` routes remain temporary compatibility entry points. Application
links and API page-link contracts use canonical `/`, `/c/...`, and `/admin/...`
paths. OAuth login, logout, downloads, API requests, static assets, and external
sites remain intentional full-document boundaries.

The browser navigation gate proves an internal click emits no document request
and that a canonical hard refresh remains in React while SPA-only mode is active:

```sh
.venv/bin/python parity/navigation.py --base-url http://127.0.0.1:5002
```

The runner fixes Chromium, locale, timezone, color scheme, reduced motion, device scale,
and viewport; waits for the network and fonts; disables residual animation; and masks the
changing commit fingerprint. Each scenario gets a fresh browser process. Comparison first verifies
the committed golden against a live Jinja render, then compares React in the same process. Exact
PNG equality is preferred; Chromium-only anti-alias noise is accepted only under either a 0.1%
edge/20-channel cap or a 0.5% glyph-edge/0.25-total-error cap. During the
migration, missing/different screens are reported but only scenarios marked `parityGate`
fail. `--require-parity` turns every missing or different scenario into a failure for the
final cutover audit. Browser artifacts live under `output/playwright/`.

Scenarios tagged `serverFixture: "isolated"` use a disposable SQLite corpus for mutually
exclusive lifecycle states. Start it separately, then gate that corpus explicitly:

```sh
PARITY_FIXTURE_DATABASE=/tmp/wiki-polis-parity-fixture.db \
  PARITY_FIXTURE_PORT=5002 \
  .venv/bin/python parity/fixture_app.py

.venv/bin/python parity/visual.py compare \
  --base-url http://127.0.0.1:5002 \
  --fixture isolated \
  --spa-only \
  --require-parity
```

The fixture app refuses database paths outside a temporary directory. With no `--fixture`
or `--scenario` filter, the runner operates only on the normal `dev` corpus.

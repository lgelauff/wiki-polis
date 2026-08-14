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

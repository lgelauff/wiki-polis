"""http_pool.py — one process-wide, connection-pooled HTTP client for the Polis stack.

Every request-path call to Particiapi / Polis (votes, statement fetches, submits,
results, admin ops) goes through a single module-level ``requests.Session`` so
TCP+TLS connections are reused across requests instead of a fresh handshake per
vote. Under a participation spike this turns per-vote connection setup into cheap
pool checkouts — the single highest-value, lowest-risk change for concurrency.

Thread-safety: the Session is shared across uWSGI threads. This is safe **only**
because callers pass ``cookies=`` / ``headers=`` / ``params=`` per request and never
mutate the Session's own state (``session.headers`` / ``session.cookies``).
urllib3's connection pool is thread-safe; do not set attributes on ``session`` at
request time.

Pool sizing: ``pool_maxsize`` should track the uWSGI threads-per-process (see
``v2/ops/uwsgi.ini`` / ``guide_deployment.md``) so threads don't queue on a
too-small pool. Override with ``POLIS_HTTP_POOL_MAXSIZE``.
"""

import os

import requests
from requests.adapters import HTTPAdapter

try:  # urllib3 ships with requests, but guard the import path defensively.
    from urllib3.util.retry import Retry
except ImportError:  # pragma: no cover
    Retry = None

# Default tracks the uWSGI threads-per-process default in v2/ops/uwsgi.ini.
POOL_MAXSIZE = int(os.environ.get('POLIS_HTTP_POOL_MAXSIZE', '20'))

# Retry ONLY idempotent methods, and ONLY on connection setup: a pooled keep-alive
# connection the server has already closed raises on first reuse, and one connect
# retry absorbs that without a user-visible 502. GET (reads) and PUT (a vote re-PUT
# is idempotent) are safe; POST is never retried (session-create and statement-submit
# are not idempotent — a retry could double-create). No read/status retries — a
# mid-flight failure must surface, not silently replay.
_RETRY = (
    Retry(total=1, connect=1, read=0, redirect=0, status=0,
          allowed_methods=frozenset({'GET', 'PUT'}), backoff_factor=0.1)
    if Retry is not None else 0
)


def _build_session() -> requests.Session:
    sess = requests.Session()
    adapter = HTTPAdapter(
        pool_connections=POOL_MAXSIZE,
        pool_maxsize=POOL_MAXSIZE,
        max_retries=_RETRY,
    )
    sess.mount('http://', adapter)
    sess.mount('https://', adapter)
    return sess


# Process-wide shared client. Import this; do not build your own per-call Session.
session = _build_session()

"""http_pool.py — one process-wide, connection-pooled HTTP client for the Polis stack.

Every request-path call to Particiapi / Polis (votes, statement fetches, submits,
results, admin ops) goes through a single module-level ``requests.Session`` so
TCP+TLS connections are reused across requests instead of a fresh handshake per
vote. Under a participation spike this turns per-vote connection setup into cheap
pool checkouts — the single highest-value, lowest-risk change for concurrency.

Thread-safety & cookies: the Session is shared across all uWSGI threads. Callers
pass ``cookies=`` / ``headers=`` / ``params=`` per request. Crucially the Session
uses a **no-store cookie policy** (``_NoStoreCookiePolicy``): ``requests`` otherwise
extracts every response ``Set-Cookie`` into ``session.cookies``, and because the
Session is process-wide that jar would leak one participant's Particiapi ``session``
cookie onto another participant's request (host-only cookies match every request to
that host). Blocking storage keeps the jar empty, so identity is carried ONLY by the
explicit per-request ``cookies=`` — no cross-participant contamination, and no shared
mutable jar for threads to race on. urllib3's connection pool is thread-safe.

Pool sizing: ``pool_maxsize`` should track the uWSGI threads-per-process (see
``v2/ops/uwsgi.ini`` / ``guide_deployment.md``) so threads don't queue on a
too-small pool. Override with ``POLIS_HTTP_POOL_MAXSIZE``.
"""

import os
from http.cookiejar import DefaultCookiePolicy

import requests
from requests.adapters import HTTPAdapter

try:  # urllib3 ships with requests, but guard the import path defensively.
    from urllib3.util.retry import Retry
except ImportError:  # pragma: no cover
    Retry = None

# Default tracks the uWSGI threads-per-process default in v2/ops/uwsgi.ini.
POOL_MAXSIZE = int(os.environ.get('POLIS_HTTP_POOL_MAXSIZE', '20'))

# Retry ONLY idempotent methods (GET reads; PUT — a vote re-PUT is idempotent). POST
# is never retried (session-create and statement-submit are not idempotent — a retry
# could double-create). Both connect AND read errors are retried once for those safe
# methods: reusing a pooled keep-alive socket the server has already closed surfaces
# as a ProtocolError that urllib3 classifies as a *read* error, so read=1 is required
# to actually absorb stale-connection reuse without a user-visible 502 (a connect-only
# retry would not). status errors are never retried.
_RETRY = (
    Retry(total=2, connect=1, read=1, redirect=0, status=0,
          allowed_methods=frozenset({'GET', 'PUT'}), backoff_factor=0.1)
    if Retry is not None else 0
)


class _NoStoreCookiePolicy(DefaultCookiePolicy):
    """Reject storing any response cookie in the shared Session's jar.

    The Session is process-wide; a persisted host-only ``session=`` cookie would be
    re-attached to other participants' requests, leaking Polis identity. All cookies
    are supplied explicitly per request, so the jar must stay empty.
    """

    def set_ok(self, cookie, request):  # noqa: ARG002 — signature fixed by CookiePolicy
        return False


def _build_session() -> requests.Session:
    sess = requests.Session()
    # Never persist response cookies into the shared jar (see class docstring).
    sess.cookies.set_policy(_NoStoreCookiePolicy())
    adapter = HTTPAdapter(
        pool_connections=POOL_MAXSIZE,
        pool_maxsize=POOL_MAXSIZE,
        max_retries=_RETRY,
    )
    sess.mount('http://', adapter)
    sess.mount('https://', adapter)
    return sess


# Process-wide shared client. Import this; do not build your own per-call Session.
#
# Built at import, which is pre-fork when uWSGI loads the app in the master (the
# default, without lazy-apps). That is safe ONLY because urllib3 opens sockets
# lazily on first request — post-fork — so no file descriptors are shared across
# workers. INVARIANT: never issue an upstream HTTP call at import / master scope.
# (We keep master-preloading rather than lazy-apps so workers share the app via
# copy-on-write and stay within the pod's memory budget.)
session = _build_session()

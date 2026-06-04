"""
polis_admin.py — Server-side Particiapi and Polis admin operations.

Participant-facing calls (PolisParticipantClient): use PARTICIAPI_BASE_URL (port 8000).
Auth disabled on Particiapi — no session cookie needed for these calls.
Only participant-scoped reads: statements, settings, results.

Admin calls (PolisServerClient): use POLIS_SERVER_URL (port 8001).
Requires a Polis system account (POLIS_ADMIN_EMAIL / POLIS_ADMIN_PASSWORD).
Handles all privileged operations: conversation creation, statement moderation,
strict-moderation toggle, seed statements, and conversation settings.

Direct Postgres reads (also via PolisServerClient): use POLIS_DATABASE_URL.
Used for featured candidates and stats — data not exposed by the Polis API.
"""

import logging
import re

import requests

logger = logging.getLogger(__name__)

_SAFE_ZINVITE = re.compile(r'^[A-Za-z0-9]{6,20}$')

# Returns all active statements with vote counts, seeds first then by agree rate.
# The agree-rate ordering is a heuristic proxy for group-representativeness when
# cluster data (math_main) is not yet available or computed.
_STATEMENTS_SQL = """
    WITH z AS (SELECT zid FROM zinvites WHERE zinvite = %s),
    vote_stats AS (
      SELECT
        v.tid,
        COUNT(*) FILTER (WHERE v.vote = -1)::int AS agree_count,
        COUNT(*) FILTER (WHERE v.vote =  1)::int AS disagree_count,
        COUNT(*) FILTER (WHERE v.vote =  0)::int AS pass_count
      FROM votes v, z WHERE v.zid = z.zid GROUP BY v.tid
    )
    SELECT
      c.tid,
      c.txt,
      c.mod,
      c.is_seed,
      COALESCE(vs.agree_count,    0) AS agree_count,
      COALESCE(vs.disagree_count, 0) AS disagree_count,
      COALESCE(vs.pass_count,     0) AS pass_count
    FROM comments c
    JOIN z ON c.zid = z.zid
    LEFT JOIN vote_stats vs ON c.tid = vs.tid
    WHERE c.active = TRUE
    ORDER BY c.tid
"""

_FEATURED_CANDIDATES_SQL = """
    WITH z AS (SELECT zid FROM zinvites WHERE zinvite = %s),
    vote_stats AS (
      SELECT
        v.tid,
        COUNT(*) FILTER (WHERE v.vote = -1)::int  AS n_agree,
        COUNT(*) FILTER (WHERE v.vote =  1)::int  AS n_disagree,
        COUNT(*) FILTER (WHERE v.vote != 0)::int  AS n_votes
      FROM votes v, z WHERE v.zid = z.zid GROUP BY v.tid
    )
    SELECT
      c.tid,
      c.txt,
      c.is_seed,
      COALESCE(vs.n_agree,    0) AS n_agree,
      COALESCE(vs.n_disagree, 0) AS n_disagree,
      COALESCE(vs.n_votes,    0) AS n_votes
    FROM comments c
    JOIN z ON c.zid = z.zid
    LEFT JOIN vote_stats vs ON c.tid = vs.tid
    WHERE c.active = TRUE AND c.mod >= 0
    ORDER BY
      c.is_seed DESC,
      (COALESCE(vs.n_votes, 0) >= 3) DESC,
      COALESCE(vs.n_agree, 0)::float / NULLIF(vs.n_votes, 0) DESC NULLS LAST
    LIMIT %s
"""

_POLIS_STATS_SQL = """
    WITH z AS (SELECT zid FROM zinvites WHERE zinvite = %s),
    vd AS (
      SELECT pid, COUNT(*) FILTER (WHERE vote != 0) AS n
      FROM votes WHERE zid = (SELECT zid FROM z) GROUP BY pid
    ),
    vs AS (
      SELECT
        COUNT(pid)::int AS n_participants,
        COALESCE(SUM(n),0)::int AS n_votes,
        COALESCE(ROUND(AVG(n)::numeric,1),0)::float AS avg_votes,
        COALESCE(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY n::float),0) AS median_votes
      FROM vd
    ),
    ss AS (
      SELECT COUNT(*)::int AS n_statements,
             COUNT(*) FILTER (WHERE is_seed = TRUE)::int AS n_seed
      FROM comments c, z WHERE c.zid = z.zid AND active = TRUE AND mod >= 0
    )
    SELECT n_participants, n_votes, avg_votes, median_votes, n_statements, n_seed
    FROM vs, ss
"""


# ── Participant client ────────────────────────────────────────────────────────

class PolisParticipantError(Exception):
    pass


class PolisParticipantClient:
    """Particiapi client — participant-facing reads only (port 8000)."""

    def __init__(self, particiapi_base: str):
        self._base = particiapi_base.rstrip('/')

    def _req(self, method: str, path: str, **kwargs):
        url = f"{self._base}/{path.lstrip('/')}"
        try:
            resp = requests.request(method, url, timeout=10, **kwargs)
        except requests.RequestException as exc:
            raise PolisParticipantError(str(exc)) from exc
        if not resp.ok:
            raise PolisParticipantError(f"HTTP {resp.status_code}: {resp.text[:300]}")
        return resp.json() if resp.content else {}

    def get_statements(self, conversation_id: str) -> tuple[list, list, list]:
        """Return (pending, approved, hidden).

        Particiapi has no moderation concept — all statements are returned as
        approved. pending and hidden are always empty.
        """
        data = self._req('GET', f'api/conversations/{conversation_id}/statements/')
        if not isinstance(data, dict):
            return [], [], []
        approved = [
            {'tid': int(tid), 'txt': s.get('text', ''), **s}
            for tid, s in data.items()
        ]
        return [], approved, []

    def get_settings(self, conversation_id: str) -> dict:
        try:
            return self._req('GET', f'api/conversations/{conversation_id}')
        except PolisParticipantError:
            return {}

    def get_results(self, conversation_id: str) -> dict | None:
        try:
            return self._req('GET', f'api/conversations/{conversation_id}/results/')
        except PolisParticipantError:
            return None


# ── Polis server admin client ─────────────────────────────────────────────────

class PolisServerError(Exception):
    pass


class PolisServerClient:
    """Direct Polis server API client (port 8001 on VPS).

    Handles all privileged operations: conversation creation, statement moderation,
    strict-moderation toggle, seed statements, and conversation settings.
    Also queries Polis Postgres directly (db_url) for stats and featured candidates.
    """

    def __init__(self, polis_server_url: str, email: str, password: str,
                 db_url: str = ''):
        self._base     = polis_server_url.rstrip('/')
        self._email    = email
        self._password = password
        self._db_url   = db_url

    # Polis rejects plain HTTP form submissions unless the request appears to
    # come via HTTPS (checked via X-Forwarded-Proto). Since we call it over the
    # internal private network this header is safe to add.
    _HEADERS = {'X-Forwarded-Proto': 'https'}

    def _login(self) -> tuple[requests.Session, dict]:
        """Return (session, extra_headers) where extra_headers carries the auth token.

        Polis sets the token cookie with domain=POLIS_SERVER_NAME (e.g. polis.internal).
        That domain never matches our internal VPS hostname, so requests won't send the
        cookie automatically.  We extract the raw token from the response and return it
        as an explicit Cookie header for callers to merge into their requests.
        """
        sess = requests.Session()
        try:
            resp = sess.post(
                f'{self._base}/api/v3/auth/login',
                json={'email': self._email, 'password': self._password},
                headers=self._HEADERS,
                timeout=10,
            )
        except requests.RequestException as exc:
            raise PolisServerError(str(exc)) from exc
        if not resp.ok:
            raise PolisServerError(
                f'Polis login failed (HTTP {resp.status_code}). '
                'Check POLIS_ADMIN_EMAIL / POLIS_ADMIN_PASSWORD env vars.'
            )
        token = resp.json().get('token')
        extra = {'x-polis': token} if token else {}
        return sess, extra

    # ── Conversations ─────────────────────────────────────────────────────────

    def create_conversation(self, title: str, strict_moderation: bool = False) -> str:
        """Create a Polis conversation and return its zinvite."""
        sess, auth_headers = self._login()
        headers = {**self._HEADERS, **auth_headers}
        try:
            resp = sess.post(
                f'{self._base}/api/v3/conversations',
                json={
                    'topic':             title,
                    'description':       '',
                    'is_active':         True,
                    'is_draft':          False,
                    'is_anon':           False,
                    'profanity_filter':  False,
                    'spam_filter':       False,
                    'strict_moderation': strict_moderation,
                },
                headers=headers,
                timeout=10,
            )
        except requests.RequestException as exc:
            raise PolisServerError(str(exc)) from exc
        if not resp.ok:
            raise PolisServerError(
                f'Polis conversation creation failed (HTTP {resp.status_code}): '
                f'{resp.text[:300]}'
            )
        # Response: {url: "...", zid: N}  — zinvite is the last path segment of url
        data = resp.json()
        url  = data.get('url', '')
        if url:
            slug = url.rstrip('/').rsplit('/', 1)[-1]
            if re.match(r'^[A-Za-z0-9]{6,20}$', slug):
                return slug
        raise PolisServerError('Polis returned no usable zinvite in response.')

    def set_strict_moderation(self, conversation_id: str, enabled: bool) -> None:
        sess, auth_headers = self._login()
        headers = {**self._HEADERS, **auth_headers}
        try:
            resp = sess.put(
                f'{self._base}/api/v3/conversations',
                json={'conversation_id': conversation_id, 'strict_moderation': enabled},
                headers=headers,
                timeout=10,
            )
        except requests.RequestException as exc:
            raise PolisServerError(str(exc)) from exc
        if not resp.ok:
            raise PolisServerError(
                f'Polis conversation settings update failed (HTTP {resp.status_code}): '
                f'{resp.text[:300]}'
            )

    def set_vis_type(self, conversation_id: str, vis_type: int) -> None:
        """Set the conversation's `vis_type` in Polis.

        Polis gates `GET /api/conversations/<id>/results/` on `vis_type <> 0`
        (surfaced as `results_available`), and defaults it to 0 — so results are
        hidden until this is set. We mirror it onto the results-phase toggle: a
        non-zero value makes the results visualisation available, 0 hides it.
        """
        sess, auth_headers = self._login()
        headers = {**self._HEADERS, **auth_headers}
        try:
            resp = sess.put(
                f'{self._base}/api/v3/conversations',
                json={'conversation_id': conversation_id, 'vis_type': vis_type},
                headers=headers,
                timeout=10,
            )
        except requests.RequestException as exc:
            raise PolisServerError(str(exc)) from exc
        if not resp.ok:
            raise PolisServerError(
                f'Polis vis_type update failed (HTTP {resp.status_code}): '
                f'{resp.text[:300]}'
            )

    # ── Statements ────────────────────────────────────────────────────────────

    def moderate(self, conversation_id: str, tid: int, mod: int) -> None:
        """Set mod value on a statement (1=approved, 0=pending, -1=hidden)."""
        sess, auth_headers = self._login()
        headers = {**self._HEADERS, **auth_headers}
        try:
            resp = sess.put(
                f'{self._base}/api/v3/comments',
                json={
                    'conversation_id': conversation_id,
                    'tid':             tid,
                    'mod':             mod,
                    'active':          True,
                    'is_meta':         False,
                    'velocity':        0.5,
                },
                headers=headers,
                timeout=10,
            )
        except requests.RequestException as exc:
            raise PolisServerError(str(exc)) from exc
        if not resp.ok:
            raise PolisServerError(
                f'Polis moderation failed (HTTP {resp.status_code}): {resp.text[:300]}'
            )

    def add_seed(self, conversation_id: str, text: str) -> None:
        """Add a seed statement via the Polis admin API, marked is_seed=True."""
        self.add_seed_return_id(conversation_id, text)

    def add_seed_return_id(self, conversation_id: str, text: str) -> int:
        """Add a seed statement and return the Polis statement ID (tid)."""
        sess, auth_headers = self._login()
        headers = {**self._HEADERS, **auth_headers}
        try:
            resp = sess.post(
                f'{self._base}/api/v3/comments',
                json={
                    'conversation_id': conversation_id,
                    'txt':             text,
                    'is_seed':         True,
                    'vote':            0,
                },
                headers=headers,
                timeout=10,
            )
        except requests.RequestException as exc:
            raise PolisServerError(str(exc)) from exc
        if not resp.ok:
            raise PolisServerError(
                f'Polis seed statement creation failed (HTTP {resp.status_code}): '
                f'{resp.text[:300]}'
            )
        tid = resp.json().get('tid')
        if tid is None:
            raise PolisServerError('Polis returned no tid for seed statement.')
        return int(tid)

    # ── Direct Postgres reads ─────────────────────────────────────────────────

    def _pg_query(self, sql: str, params: tuple, label: str) -> list[tuple] | None:
        """Run a parameterised Postgres query and return all rows, or None on failure.

        Returns None when db_url is absent, psycopg2 is unavailable, or the
        query raises. Callers are responsible for their own zinvite guard.
        """
        try:
            import psycopg2
        except ImportError:
            logger.exception('psycopg2 not available — %s unavailable', label)
            return None
        try:
            conn = psycopg2.connect(self._db_url)
            try:
                with conn.cursor() as cur:
                    cur.execute(sql, params)
                    rows = cur.fetchall()
            finally:
                conn.close()
        except Exception:
            logger.exception('Postgres %s failed', label)
            return None
        return rows

    def get_statements(self, zinvite: str) -> tuple[list, list, list] | None:
        """Return (pending, approved, hidden) from Postgres, or None if unavailable.

        mod=0 → pending, mod=1 → approved, mod=-1 → hidden.
        Returns None when db_url is absent so caller can fall back to Particiapi.
        """
        if not self._db_url or not _SAFE_ZINVITE.match(zinvite or ''):
            return None
        rows = self._pg_query(_STATEMENTS_SQL, (zinvite,),
                              'get_statements — falling back to Particiapi')
        if rows is None:
            return None
        pending, approved, hidden = [], [], []
        for r in rows:
            s = {
                'tid':          r[0],
                'txt':          r[1],
                'mod':          r[2],
                'is_seed':      r[3],
                'agree_count':    r[4],
                'disagree_count': r[5],
                'pass_count':     r[6],
            }
            if r[2] == 1:
                approved.append(s)
            elif r[2] == -1:
                hidden.append(s)
            else:
                pending.append(s)
        return pending, approved, hidden

    def get_featured_candidates(self, zinvite: str,
                                max_statements: int = 20) -> list[dict] | None:
        """Return candidate statements for featuring, or None if unavailable.

        Each item: {tid, text, is_seed, n_agree, n_disagree, n_votes}.
        Seeds always appear first; remainder ranked by agree rate.
        Returns None when db_url is absent or the query fails.
        """
        if not self._db_url or not _SAFE_ZINVITE.match(zinvite or ''):
            return None
        rows = self._pg_query(_FEATURED_CANDIDATES_SQL, (zinvite, max_statements),
                              'get_featured_candidates')
        if rows is None:
            return None
        return [
            {'tid': r[0], 'text': r[1], 'is_seed': r[2],
             'n_agree': r[3], 'n_disagree': r[4], 'n_votes': r[5]}
            for r in rows
        ]

    def get_polis_stats(self, zinvite: str) -> dict | None:
        """Return conversation stats from Polis Postgres, or None if unavailable."""
        if not self._db_url or not _SAFE_ZINVITE.match(zinvite or ''):
            return None
        rows = self._pg_query(_POLIS_STATS_SQL, (zinvite,), 'get_polis_stats')
        if rows is None:
            return None
        row = rows[0] if rows else None
        if not row or len(row) < 6:
            return None
        try:
            return {
                'n_participants': int(row[0]),
                'n_votes':        int(row[1]),
                'avg_votes':      float(row[2]),
                'median_votes':   float(row[3]),
                'n_statements':   int(row[4]),
                'n_seed':         int(row[5]),
            }
        except (ValueError, IndexError):
            return None

    def queue_math_recompute(self, zinvite: str) -> bool:
        """Insert a worker_tasks row to trigger a polismath recompute for one conversation.

        Polismath polls worker_tasks continuously (1 s interval) and processes the task
        within seconds. Returns True if the task was queued, False if unavailable or failed.
        No-op when db_url is absent.
        """
        if not self._db_url or not _SAFE_ZINVITE.match(zinvite or ''):
            return False
        sql = """
            INSERT INTO worker_tasks (task_type, task_data, task_bucket, math_env)
            SELECT 'update_math',
                   jsonb_build_object('zid', zid),
                   zid,
                   'prod'
            FROM zinvites WHERE zinvite = %s
        """
        try:
            import psycopg2
        except ImportError:
            logger.exception('psycopg2 not available — queue_math_recompute unavailable')
            return False
        try:
            conn = psycopg2.connect(self._db_url)
            try:
                with conn.cursor() as cur:
                    cur.execute(sql, (zinvite,))
                conn.commit()
            finally:
                conn.close()
        except Exception:
            logger.exception('queue_math_recompute failed for %s', zinvite)
            return False
        return True

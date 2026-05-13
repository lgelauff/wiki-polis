"""
polis_admin.py — Server-side Particiapi admin operations.

All calls go to Particiapi (not directly to Polis). Because the stack runs
with PARTICIAPI_AUTHENTICATION_DISABLED=True, no session cookie is needed
for server-to-server calls from Flask.

Note on feature parity:
  Particiapi exposes a minimal API — conversation metadata, statements (read),
  voting, and results. It does not expose moderation, seed-statement creation,
  or strict-moderation settings; those remain Polis-only. Methods that cannot
  be fulfilled raise PolisAdminError so callers can surface a clear message.
"""

import re

import requests

_SAFE_ZINVITE = re.compile(r'^[A-Za-z0-9]{6,20}$')

# Returns all active statements with vote counts, seeds first then by agree rate.
# The agree-rate ordering is a heuristic proxy for group-representativeness when
# cluster data (math_main) is not yet available or computed.
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
    FROM comments c, z
    LEFT JOIN vote_stats vs ON c.tid = vs.tid
    WHERE c.zid = z.zid AND c.active = TRUE AND c.mod >= 0
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


def get_featured_candidates(zinvite: str, db_url: str = '',
                            max_statements: int = 20) -> list[dict] | None:
    """Return candidate statements for featuring, or None if unavailable.

    Each item: {tid, text, is_seed, n_agree, n_disagree, n_votes}.
    Seeds always appear first; remainder ranked by agree rate.
    Returns None when POLIS_DATABASE_URL is absent or the query fails.
    """
    if not db_url or not _SAFE_ZINVITE.match(zinvite or ''):
        return None
    try:
        import psycopg2
    except ImportError:
        return None
    try:
        conn = psycopg2.connect(db_url)
        try:
            with conn.cursor() as cur:
                cur.execute(_FEATURED_CANDIDATES_SQL, (zinvite, max_statements))
                rows = cur.fetchall()
        finally:
            conn.close()
    except Exception:
        return None
    return [
        {'tid': r[0], 'text': r[1], 'is_seed': r[2],
         'n_agree': r[3], 'n_disagree': r[4], 'n_votes': r[5]}
        for r in rows
    ]


def get_polis_stats(zinvite: str, db_url: str = '') -> dict | None:
    """Query Polis PostgreSQL directly for conversation stats.

    Returns a dict with n_participants, n_votes, avg_votes, median_votes,
    n_statements, n_seed — or None if unavailable (no db_url, connection error, etc.).
    """
    if not db_url or not _SAFE_ZINVITE.match(zinvite or ''):
        return None

    try:
        import psycopg2
    except ImportError:
        return None

    try:
        conn = psycopg2.connect(db_url)
        try:
            with conn.cursor() as cur:
                cur.execute(_POLIS_STATS_SQL, (zinvite,))
                row = cur.fetchone()
        finally:
            conn.close()
    except Exception:
        return None

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


class PolisAdminError(Exception):
    pass


class PolisAdminClient:

    def __init__(self, particiapi_base: str):
        self._base = particiapi_base.rstrip('/')

    def _req(self, method: str, path: str, **kwargs):
        url = f"{self._base}/{path.lstrip('/')}"
        try:
            resp = requests.request(method, url, timeout=10, **kwargs)
        except requests.RequestException as exc:
            raise PolisAdminError(str(exc)) from exc
        if not resp.ok:
            raise PolisAdminError(f"HTTP {resp.status_code}: {resp.text[:300]}")
        return resp.json() if resp.content else {}

    # ── Statements ────────────────────────────────────────────────────────────

    def get_statements(self, conversation_id: str) -> tuple[list, list, list]:
        """Return (pending, approved, hidden).

        Particiapi has no moderation concept — all statements are returned as
        approved. pending and hidden are always empty.
        """
        data = self._req('GET', f'api/conversations/{conversation_id}/statements/')
        if not isinstance(data, dict):
            return [], [], []
        # Normalise to the {tid, txt, ...} shape the admin template expects.
        approved = [
            {'tid': int(tid), 'txt': s.get('text', ''), **s}
            for tid, s in data.items()
        ]
        return [], approved, []

    def moderate(self, conversation_id: str, tid: int, mod: int) -> None:
        """Not available — Particiapi has no moderation endpoint."""
        raise PolisAdminError(
            'Statement moderation is not available through Particiapi.'
        )

    def add_seed(self, conversation_id: str, text: str) -> None:
        """Not available server-side — Particiapi seed creation requires a browser session."""
        raise PolisAdminError(
            'Seed statement creation is not available server-side through Particiapi.'
        )

    # ── Conversation settings ─────────────────────────────────────────────────

    def get_settings(self, conversation_id: str) -> dict:
        try:
            return self._req('GET', f'api/conversations/{conversation_id}')
        except PolisAdminError:
            return {}

    def set_strict_moderation(self, conversation_id: str, enabled: bool) -> None:
        """Not available — Particiapi has no strict-moderation setting."""
        raise PolisAdminError(
            'Strict moderation is not available through Particiapi.'
        )

    def get_results(self, conversation_id: str) -> dict | None:
        """Return results dict, or None if not yet available."""
        try:
            return self._req('GET', f'api/conversations/{conversation_id}/results/')
        except PolisAdminError:
            return None

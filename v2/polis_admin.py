"""
polis_admin.py — Server-side Particiapi admin operations.

All calls go to Particiapi (not directly to Polis). Because the stack runs
with PARTICIAPI_AUTHENTICATION_DISABLED=True, no session cookie is needed
for server-to-server calls from Flask.
"""

import re

import requests

_SAFE_ZINVITE = re.compile(r'^[A-Za-z0-9]{6,20}$')

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
        """Return (pending, approved, hidden) lists for a conversation."""
        visible = self._req('GET', 'api/v3/comments',
                            params={'conversation_id': conversation_id})
        if not isinstance(visible, list):
            visible = []

        pending  = [s for s in visible if s.get('mod') == 0]
        approved = [s for s in visible if s.get('mod') == 1]

        try:
            hidden = self._req('GET', 'api/v3/comments',
                               params={'conversation_id': conversation_id, 'mod': -1})
            if not isinstance(hidden, list):
                hidden = []
        except PolisAdminError:
            hidden = []

        return pending, approved, hidden

    def moderate(self, conversation_id: str, tid: int, mod: int) -> None:
        """Set moderation status: -1=hidden, 0=pending, 1=approved."""
        self._req('PUT', 'api/v3/comments', json={
            'conversation_id': conversation_id,
            'tid': tid,
            'active': mod >= 0,
            'mod': mod,
            'is_meta': False,
            'velocity': 1.0,
        })

    def add_seed(self, conversation_id: str, text: str) -> None:
        """Create a seed statement (pre-approved, shown to all participants)."""
        self._req('POST', 'api/v3/comments', json={
            'conversation_id': conversation_id,
            'txt': text,
            'is_seed': True,
            'vote': 0,
        })

    # ── Conversation settings ─────────────────────────────────────────────────

    def get_settings(self, conversation_id: str) -> dict:
        try:
            result = self._req('GET', 'api/v3/conversations',
                               params={'conversation_id': conversation_id})
            if isinstance(result, list):
                return result[0] if result else {}
            return result if isinstance(result, dict) else {}
        except PolisAdminError:
            return {}

    def set_strict_moderation(self, conversation_id: str, enabled: bool) -> None:
        self._req('PUT', 'api/v3/conversations', json={
            'conversation_id': conversation_id,
            'strict_moderation': enabled,
        })

    def get_results(self, conversation_id: str) -> dict | None:
        """Return results dict, or None if not yet available."""
        try:
            return self._req('GET', f'api/conversations/{conversation_id}/results/')
        except PolisAdminError:
            return None

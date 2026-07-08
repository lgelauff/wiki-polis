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

from http_pool import session as _http

logger = logging.getLogger(__name__)

_SAFE_ZINVITE = re.compile(r'^[A-Za-z0-9]{6,20}$')

# Returns all active statements with vote counts, seeds first then by agree rate.
# The agree-rate ordering is a heuristic proxy for group-representativeness when
# cluster data (math_main) is not yet available or computed.
# Counts use votes_latest_unique + COUNT(DISTINCT pid) so a participant is counted
# once at their CURRENT vote — raw `votes` + COUNT(*) would inflate every count by
# vote changes (see #269).
_STATEMENTS_SQL = """
    WITH z AS (SELECT zid FROM zinvites WHERE zinvite = %s),
    vote_stats AS (
      SELECT
        v.tid,
        COUNT(DISTINCT v.pid) FILTER (WHERE v.vote = -1)::int AS agree_count,
        COUNT(DISTINCT v.pid) FILTER (WHERE v.vote =  1)::int AS disagree_count,
        COUNT(DISTINCT v.pid) FILTER (WHERE v.vote =  0)::int AS pass_count
      FROM votes_latest_unique v, z WHERE v.zid = z.zid GROUP BY v.tid
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
        COUNT(DISTINCT v.pid) FILTER (WHERE v.vote = -1)::int  AS n_agree,
        COUNT(DISTINCT v.pid) FILTER (WHERE v.vote =  1)::int  AS n_disagree,
        COUNT(DISTINCT v.pid) FILTER (WHERE v.vote != 0)::int  AS n_votes
      FROM votes_latest_unique v, z WHERE v.zid = z.zid GROUP BY v.tid
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

# Per-statement vote counts for a Phase 6 (informed voting) conversation.
# Uses votes_latest_unique (one vote per participant per statement) — the same
# table Polis math uses — so counts are deduplicated and authoritative.
# allowed_tids filters to confirmed featured statements; hidden/moderated tids
# are excluded by passing only the non-moderated set from the caller.
# excluded_pids is an array of Polis participant IDs (ints) to exclude from counts
# (banned participants); pass an empty array when no bans are in effect.
# Raw vote sign: -1 = agree, +1 = disagree, 0 = pass (Polis convention).
_PHASE6_VOTE_COUNTS_SQL = """
    WITH z AS (SELECT zid FROM zinvites WHERE zinvite = %s)
    SELECT
      v.tid,
      COUNT(DISTINCT v.pid) FILTER (WHERE v.vote = -1) AS n_agree,
      COUNT(DISTINCT v.pid) FILTER (WHERE v.vote =  1) AS n_disagree,
      COUNT(DISTINCT v.pid) FILTER (WHERE v.vote =  0) AS n_pass,
      COUNT(DISTINCT v.pid)                             AS n_voters
    FROM votes_latest_unique v, z
    WHERE v.zid = z.zid
      AND v.tid = ANY(%s)
      AND NOT (v.pid = ANY(%s))
    GROUP BY v.tid
"""

# Total distinct participant count for a Phase 6 conversation, optionally
# excluding banned pids. Used as the denominator for participation rate.
_PHASE6_PARTICIPANT_COUNT_SQL = """
    WITH z AS (SELECT zid FROM zinvites WHERE zinvite = %s)
    SELECT COUNT(DISTINCT v.pid)
    FROM votes_latest_unique v, z
    WHERE v.zid = z.zid
      AND NOT (v.pid = ANY(%s))
"""

# Statements remaining to vote on, across multiple conversations, for one participant.
# Identified by xid (our SHA-256 of mw_user_id — stored in xids.xid).
# Returns one row per zinvite: total approved statements and how many the participant
# has already cast a non-pass vote on (pass counts as "voted" for progress purposes).
# zinvites is an ARRAY of text; only zinvites present in the xids table for this xid
# are counted (i.e. conversations the participant has actually joined in Polis).
_STATEMENTS_REMAINING_BULK_SQL = """
    WITH zmap AS (
        SELECT zi.zinvite, zi.zid
        FROM zinvites zi
        WHERE zi.zinvite = ANY(%s)
    ),
    pid_map AS (
        SELECT p.zid, p.pid
        FROM participants p
        JOIN xids x ON x.uid = p.uid AND x.zid = p.zid
        WHERE x.xid = %s
          AND p.zid IN (SELECT zid FROM zmap)
    ),
    total_stmts AS (
        SELECT zmap.zinvite, COUNT(c.tid)::int AS n_total
        FROM comments c
        JOIN zmap ON c.zid = zmap.zid
        WHERE c.active = TRUE AND c.mod = 1
        GROUP BY zmap.zinvite
    ),
    voted_stmts AS (
        SELECT zmap.zinvite, COUNT(DISTINCT v.tid)::int AS n_voted
        FROM votes_latest_unique v
        JOIN zmap ON v.zid = zmap.zid
        JOIN pid_map pm ON pm.zid = v.zid AND pm.pid = v.pid
        JOIN comments c ON c.zid = zmap.zid AND c.tid = v.tid
          AND c.active = TRUE AND c.mod = 1
        GROUP BY zmap.zinvite
    )
    SELECT
        ts.zinvite,
        ts.n_total,
        COALESCE(vs.n_voted, 0) AS n_voted,
        GREATEST(0, ts.n_total - COALESCE(vs.n_voted, 0)) AS n_remaining
    FROM total_stmts ts
    LEFT JOIN voted_stmts vs USING (zinvite)
"""

# Personal votes: the logged-in participant's own votes in a given conversation,
# keyed by statement tid. Used to show "You: Agreed / Disagreed / Passed" on
# the results surfaces. Requires the participant's Polis pid.
_PERSONAL_VOTES_SQL = """
    WITH z AS (SELECT zid FROM zinvites WHERE zinvite = %s)
    SELECT v.tid, v.vote
    FROM votes_latest_unique v, z
    WHERE v.zid = z.zid AND v.pid = %s
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

_VALID_VOTE_COUNT_SQL = """
    WITH z AS (SELECT zid FROM zinvites WHERE zinvite = %s)
    SELECT COUNT(*)::int
    FROM votes_latest_unique v, z
    WHERE v.zid = z.zid
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
            resp = _http.request(method, url, timeout=10, **kwargs)
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

        Uses the shared connection-pooled session (http_pool). Safe because the auth
        token is returned as an explicit header, never relied on via session cookies,
        and no session state is mutated here.
        """
        sess = _http
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

    def close_and_hide_conversation(self, conversation_id: str) -> None:
        """Deactivate a Polis conversation and hide results before local deletion."""
        sess, auth_headers = self._login()
        headers = {**self._HEADERS, **auth_headers}
        try:
            resp = sess.put(
                f'{self._base}/api/v3/conversations',
                json={
                    'conversation_id': conversation_id,
                    'is_active': False,
                    'vis_type': 0,
                },
                headers=headers,
                timeout=10,
            )
        except requests.RequestException as exc:
            raise PolisServerError(str(exc)) from exc
        if not resp.ok:
            raise PolisServerError(
                f'Polis conversation close/hide failed (HTTP {resp.status_code}): '
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

    def _post_seed(self, sess, headers: dict, conversation_id: str, text: str) -> requests.Response:
        """POST a single seed statement to Polis. Raises PolisServerError on failure."""
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
        return resp

    def add_seed(self, conversation_id: str, text: str) -> None:
        """Add a seed statement via the Polis admin API, marked is_seed=True.
        Raises PolisServerError on non-2xx response or network failure.
        Does not require a tid in the response (fire-and-record semantics)."""
        sess, auth_headers = self._login()
        self._post_seed(sess, {**self._HEADERS, **auth_headers}, conversation_id, text)

    def bulk_add_seeds(
        self, conversation_id: str, texts: list[str]
    ) -> tuple[int, list[tuple[str, PolisServerError]]]:
        """Add multiple seed statements with a single login.

        Returns (successes, failures) where failures is a list of (text, exc)
        pairs. Raises PolisServerError only if login itself fails.
        """
        sess, auth_headers = self._login()
        headers = {**self._HEADERS, **auth_headers}
        successes = 0
        failures: list[tuple[str, PolisServerError]] = []
        for text in texts:
            try:
                self._post_seed(sess, headers, conversation_id, text)
                successes += 1
            except (requests.RequestException, PolisServerError) as exc:
                failures.append((text, PolisServerError(str(exc)) if not isinstance(exc, PolisServerError) else exc))
        return successes, failures

    def add_seed_return_id(self, conversation_id: str, text: str) -> int:
        """Add a seed statement and return the Polis statement ID (tid).
        Raises PolisServerError if the response is not JSON or does not include a tid."""
        sess, auth_headers = self._login()
        resp = self._post_seed(sess, {**self._HEADERS, **auth_headers}, conversation_id, text)
        try:
            tid = resp.json().get('tid')
        except ValueError:
            raise PolisServerError(
                f'Polis returned non-JSON response: {resp.text[:100]}'
            )
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

    def get_valid_vote_count(self, zinvite: str) -> int | None:
        """Return latest valid Polis vote rows for one conversation.

        Uses votes_latest_unique so one participant contributes at most one current
        vote per statement. Returns None if Postgres is unavailable.
        """
        if not self._db_url or not _SAFE_ZINVITE.match(zinvite or ''):
            return None
        rows = self._pg_query(_VALID_VOTE_COUNT_SQL, (zinvite,),
                              'get_valid_vote_count')
        if rows is None:
            return None
        return int(rows[0][0]) if rows else 0

    def get_phase6_vote_counts(
        self,
        zinvite: str,
        allowed_tids: list[int],
        excluded_pids: list[int] | None = None,
    ) -> dict[int, dict] | None:
        """Return per-statement vote counts for a Phase 6 conversation.

        Queries votes_latest_unique (one vote per participant per statement).
        Only counts votes for tids in allowed_tids — caller passes the
        confirmed, non-moderated set so hidden statements are automatically
        excluded from aggregates.

        excluded_pids is an optional list of Polis participant IDs to suppress
        (e.g. banned participants). Pass None or [] when no bans are in effect.

        Returns dict[tid → {n_agree, n_disagree, n_pass, n_voters}], or None
        if the Postgres connection is unavailable.

        Raw Polis vote sign: -1 = agree, +1 = disagree, 0 = pass.
        """
        if not self._db_url or not _SAFE_ZINVITE.match(zinvite or ''):
            return None
        if not allowed_tids:
            return {}
        pids = list(excluded_pids or [])
        rows = self._pg_query(
            _PHASE6_VOTE_COUNTS_SQL,
            (zinvite, allowed_tids, pids),
            'get_phase6_vote_counts',
        )
        if rows is None:
            return None
        return {
            int(r[0]): {
                'n_agree':    int(r[1]),
                'n_disagree': int(r[2]),
                'n_pass':     int(r[3]),
                'n_voters':   int(r[4]),
            }
            for r in rows
        }

    def get_phase6_participant_count(
        self,
        zinvite: str,
        excluded_pids: list[int] | None = None,
    ) -> int | None:
        """Return the number of distinct participants in a Phase 6 conversation.

        Excludes any pids in excluded_pids (banned participants).
        Returns None if Postgres is unavailable.
        """
        if not self._db_url or not _SAFE_ZINVITE.match(zinvite or ''):
            return None
        pids = list(excluded_pids or [])
        rows = self._pg_query(
            _PHASE6_PARTICIPANT_COUNT_SQL,
            (zinvite, pids),
            'get_phase6_participant_count',
        )
        if rows is None:
            return None
        return int(rows[0][0]) if rows else 0

    def get_statements_remaining_bulk(
        self,
        zinvites: list[str],
        xid: str,
    ) -> dict[str, int] | None:
        """Return statements remaining to vote on per conversation for one participant.

        zinvites: list of Polis zinvites (conv.polis_id values).
        xid: the participant's xid (sha256 of mw_user_id) — used to look up their
             Polis pid via the xids table without storing pid separately.

        Returns dict[zinvite → n_remaining], or None if Postgres is unavailable.
        Conversations where the participant has no Polis record are absent from the dict.
        """
        progress = self.get_statement_progress_bulk(zinvites, xid)
        if progress is None:
            return None
        return {zinvite: row['remaining'] for zinvite, row in progress.items()}

    def get_statement_progress_bulk(
        self,
        zinvites: list[str],
        xid: str,
    ) -> dict[str, dict] | None:
        """Return statement vote progress per conversation for one participant."""
        if not self._db_url or not zinvites or not xid:
            return None
        safe = [z for z in zinvites if _SAFE_ZINVITE.match(z or '')]
        if not safe:
            return {}
        rows = self._pg_query(
            _STATEMENTS_REMAINING_BULK_SQL,
            (safe, xid),
            'get_statement_progress_bulk',
        )
        if rows is None:
            return None
        return {
            r[0]: {
                'total': int(r[1]),
                'voted': int(r[2]),
                'remaining': int(r[3]),
            }
            for r in rows
        }

    def get_personal_votes(
        self,
        zinvite: str,
        polis_pid: int,
    ) -> dict[int, int] | None:
        """Return the participant's own votes in a conversation keyed by tid.

        Returns dict[tid → vote] where vote is -1 (agree), +1 (disagree), or
        0 (pass). Returns None if Postgres is unavailable.
        """
        if not self._db_url or not _SAFE_ZINVITE.match(zinvite or ''):
            return None
        rows = self._pg_query(
            _PERSONAL_VOTES_SQL,
            (zinvite, polis_pid),
            'get_personal_votes',
        )
        if rows is None:
            return None
        return {int(r[0]): int(r[1]) for r in rows}

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
        except psycopg2.errors.InsufficientPrivilege:
            logger.exception(
                'queue_math_recompute lacks worker_tasks privileges for %s; '
                'grant INSERT on worker_tasks and USAGE on its sequence to the '
                'POLIS_DATABASE_URL role',
                zinvite,
            )
            return False
        except Exception:
            logger.exception('queue_math_recompute failed for %s', zinvite)
            return False
        return True

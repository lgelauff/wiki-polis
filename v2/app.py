"""
app.py — Flask application for wiki-polis v2.
"""

import base64
import click
import dataclasses
import functools
import hashlib
import hmac
import ipaddress
import os
import random
import re
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode, urlparse, urljoin

import coolname
import nh3
import requests
from dotenv import load_dotenv
from flask import (Blueprint, Flask, abort, current_app, flash, g, jsonify,
                   has_request_context, make_response, redirect, render_template,
                   request, session, url_for)
from flask_migrate import Migrate
from flask_session import Session
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect, validate_csrf
from sqlalchemy import text as _sa_text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import joinedload
from wtforms.validators import ValidationError

from db import (ACCESS_POLICIES, ADMIN_ROLES, FLAG_CATEGORIES, AdminRole, Argument,
                ArgumentSideState, ArgumentVote, AuditEvent, ContentFlag, Conversation,
                ConversationBan, ConversationInvite, FeaturedStatement, Participant,
                Participation, StatementProvenance, StatementSimilarityScore, db)
from polis_admin import (PolisParticipantClient, PolisParticipantError,
                         PolisServerClient, PolisServerError,
                         polis_server_config_error)
from http_pool import session as polis_http
from seed_csv import (MAX_FILE_BYTES, MAX_ROWS, MAX_TEXT_CHARS, ParseResult,
                      RowError, strip_formula_prefixes)
from logging_setup import configure_logging
from api.v1 import create_api_v1_blueprint, register_api_error_handlers
from services.identity import reconcile_participant_login
from services.invites import InviteBatchSaveError, add_conversation_invites

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))

_MW_USER_AGENT   = 'wiki-polis/2.0 (Toolforge tool; https://wiki-polis.toolforge.org)'
_TEXT_ALLOWED_TAGS  = {'p', 'strong', 'em', 'a', 'ul', 'ol', 'li', 'br'}
_TEXT_ALLOWED_ATTRS = {'a': {'href', 'title'}}
_POLIS_ID_RE     = re.compile(r'^[A-Za-z0-9]{6,20}$')
_SLUG_RE         = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')
_PSEUDONYM_RE    = re.compile(r'^[a-z]{2,20}-[a-z]{2,20}$')
_REDIS_RATELIMIT_SCHEMES = ('redis://', 'rediss://')
_MIN_RATELIMIT_IDENTITY_SECRET_LEN = 32
_XID_HMAC_VERSION = 2
_MIN_STAGING_DEV_TOKEN_LEN = 32


def _read_secret(name: str) -> str:
    """Read from /run/secrets/wiki-polis/<name> (Kubernetes) or fall back to env var."""
    file_path = f'/run/secrets/wiki-polis/{name}'
    if os.path.exists(file_path):
        with open(file_path) as f:
            return f.read().strip()
    return os.environ.get(name.upper().replace('-', '_'), '')


def _split_csv(value: str) -> list[str]:
    return [v.strip() for v in (value or '').split(',') if v.strip()]


def _truthy(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or '').strip().lower() in ('1', 'true', 'yes', 'on')


def _derive_xid(subject: str) -> str:
    """Keyed participant xid derivation (#96).

    Version 1 used plain sha256(mw_user_id), which is enumerable because Wikimedia
    user ids are sequential. HMAC keeps the live Particiapi identifier stable within
    one deployment without making it recomputable from public user ids.
    """
    secret = current_app.config.get('XID_HASH_SECRET') or current_app.config['SECRET_KEY']
    return hmac.new(str(secret).encode(), str(subject).encode(), hashlib.sha256).hexdigest()


def _is_staging_toolforge_app(app: Flask) -> bool:
    tool_name = (
        os.environ.get('TOOL_NAME')
        or os.environ.get('TOOLFORGE_TOOL_NAME')
        or ''
    ).strip()
    if tool_name == 'wiki-polis-dev':
        return True
    if os.environ.get('WIKI_POLIS_ENV', '').strip().lower() == 'staging':
        return True
    hosts = app.config.get('TRUSTED_HOSTS') or []
    if isinstance(hosts, str):
        hosts = _split_csv(hosts)
    return 'wiki-polis-dev.toolforge.org' in hosts


def _staging_dev_login_token(username: str, secret: str) -> str:
    return hmac.new(secret.encode('utf-8'), username.encode('utf-8'), hashlib.sha256).hexdigest()


ADMIN_USERS = [u.strip() for u in _read_secret('admin-users').split(',') if u.strip()]

_REVEAL_COOLDOWN_DAYS = 30   # days after close before reveal window opens
_REVEAL_WINDOW_DAYS   = 30   # days participants may opt in once the window opens
_MATH_RECOMPUTE_COOLDOWN = 600  # seconds between auto-triggered recomputes per conversation
_DEMO_MW_ID_MIN = -2_000_000_000
_DEMO_MW_ID_MAX = -1_000_000_000
_LAST_ENGAGEMENT_THROTTLE = timedelta(minutes=5)

# ── Phase 6 results ───────────────────────────────────────────────────────────

@dataclasses.dataclass(frozen=True)
class Phase6ResultsFilter:
    """Moderation exclusions applied uniformly across all Phase 6 result surfaces.

    excluded_tids: Phase 6 Polis statement tids to suppress (statements hidden via
      admin moderation after Phase 6 init, e.g. de-featured mid-round). Populated
      from FeaturedStatement rows whose phase6_polis_statement_id has mod=-1 in the
      Phase 6 Polis conversation.

    excluded_pids: Polis participant pids to suppress (banned participants). Empty
      until issue #60 (ban participant) ships the admin UI; the field exists so
      results can be recomputed with exclusions without a schema change.
    """
    excluded_tids: frozenset  # frozenset[int]
    excluded_pids: frozenset  # frozenset[int]

    @classmethod
    def empty(cls) -> 'Phase6ResultsFilter':
        return cls(excluded_tids=frozenset(), excluded_pids=frozenset())

    def to_snapshot(self) -> dict:
        return {
            'excluded_tids': sorted(int(tid) for tid in self.excluded_tids),
            'excluded_pids': sorted(int(pid) for pid in self.excluded_pids),
        }

    @classmethod
    def from_snapshot(cls, data) -> 'Phase6ResultsFilter':
        if not isinstance(data, dict):
            return cls.empty()
        return cls(
            excluded_tids=frozenset(int(tid) for tid in data.get('excluded_tids', [])),
            excluded_pids=frozenset(int(pid) for pid in data.get('excluded_pids', [])),
        )


def _vote_label(vote: int | None) -> str | None:
    """Human-readable label for a raw Polis vote value."""
    if vote is None:
        return None
    return {-1: 'Agreed', 1: 'Disagreed', 0: 'Passed'}.get(vote)


def _pct(n: int, total: int) -> float:
    return round(n / total * 100, 1) if total else 0.0


# ── Phase 6 results aggregate cache ───────────────────────────────────────────
# The results / report surfaces recompute ~5 Postgres + Particiapi round trips per
# view, and the aggregate is identical for every viewer. Memoise the fetched
# aggregate (NOT the assembled result — the per-participant overlay stays
# per-request) for a short TTL so a Results-tab spike collapses to ~one fetch per
# TTL per conversation. In-process only (no Redis); a few duplicate fetches per pod
# per TTL are fine. Set PHASE6_RESULTS_CACHE_TTL=0 to disable (tests do this).
_PHASE6_AGG_TTL = float(os.environ.get('PHASE6_RESULTS_CACHE_TTL', '30'))
_phase6_agg_cache: dict = {}
_phase6_agg_lock = threading.Lock()

# Phase-6 vote-session bootstrap coordination (#275 thread-safety). Under threaded
# workers, two concurrent first-time Phase-6 votes from the SAME participant could
# each POST create=true and mint two different Polis uids — which the aggregate's
# COUNT(DISTINCT pid) would then count as two voters. We serialize the first bootstrap
# per (xid, conversation) within a worker and share the resulting session token via a
# process-local cache (each request holds its own Flask-session copy, so re-reading the
# session under the lock is not enough). Cross-process double-bootstrap predates the
# threading change (multi-process workers already allowed it); the complete cross-worker
# fix is to bind the Phase-6 session to the trusted-sub subject (idempotent uid).
_p6_bootstrap_locks: dict = {}
_p6_bootstrap_locks_guard = threading.Lock()
_p6_session_cache: dict = {}  # (xid, conv_id) -> (pa_cookie, csrf_token)


def _p6_bootstrap_lock(key):
    with _p6_bootstrap_locks_guard:
        lock = _p6_bootstrap_locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _p6_bootstrap_locks[key] = lock
        return lock


def _phase6_agg_cached(key, producer, cacheable=None):
    """Return producer()'s value, memoised per key for _PHASE6_AGG_TTL seconds.

    TTL <= 0 disables caching. The producer runs outside the lock, so a burst may
    recompute a few times before the entry is warm — acceptable, and it keeps one
    slow fetch from blocking every other viewer.

    `cacheable`, if given, is called with the produced value; the value is cached
    only when it returns truthy. Used to avoid memoising a transient/degraded fetch
    (e.g. a momentary Postgres failure) for the full TTL.
    """
    ttl = _PHASE6_AGG_TTL
    if ttl <= 0:
        return producer()
    now = time.monotonic()
    with _phase6_agg_lock:
        hit = _phase6_agg_cache.get(key)
        if hit is not None and hit[0] > now:
            return hit[1]
    value = producer()
    if cacheable is None or cacheable(value):
        with _phase6_agg_lock:
            _phase6_agg_cache[key] = (now + ttl, value)
    return value


def _invalidate_phase6_results_cache(conv=None) -> None:
    """Drop cached Phase 6 aggregates — all, or just one conversation's.

    Called on transitions that change what results should show (phase toggles,
    close). The short TTL bounds staleness even without an explicit call; keys are
    (p6_zinvite, ...), so a per-conversation drop matches on the first element.
    """
    with _phase6_agg_lock:
        if conv is None:
            _phase6_agg_cache.clear()
            return
        z = conv.phase6_polis_conversation_id
        if z:
            for k in [k for k in _phase6_agg_cache if k and k[0] == z]:
                _phase6_agg_cache.pop(k, None)


def _build_phase6_results(
    conv,
    participation,
    results_filter: 'Phase6ResultsFilter | None' = None,
) -> dict | None:
    """Build the unified Phase 6 results object used by all result surfaces.

    Returns None if Phase 6 is not initialised or has no confirmed statements.

    The returned dict has shape:
      {
        'statements': [{
          'text', 'fs_id',
          'p2': {n_agree, n_disagree, n_pass, n_voters, pct_agree, pct_disagree, pct_pass},
          'p6': {n_agree, n_disagree, n_pass, n_voters, pct_agree, pct_disagree, pct_pass},
          'shift': float | None,     # aggregate: p6_pct_agree - p2_pct_agree (population comparison,
                                     #   NOT individual-level delta — see 'matched_participants')
          'my_p2_vote': int | None,  # raw Polis vote; None if participation absent or PG unavail
          'my_p6_vote': int | None,
          'my_p2_label': str | None,
          'my_p6_label': str | None,
        }],
        'p6_participants': int | None,
        'p2_participants': int | None,
        'matched_participants': None,  # int | None — participants who voted in BOTH rounds;
                                       # requires xid→pid mapping (not yet stored, see TODO below).
                                       # Individual-level delta + CI extrapolation depend on this.
        'p2_consensus': list,   # top-3 statements by Phase 2 agree rate (population consensus)
        'p2_divisive':  list,   # top-3 statements by balanced agree/disagree split (most divisive)
        'filter': Phase6ResultsFilter,
        'source_divergence': float | None,  # abs diff between PG count and Particiapi count
        'is_preliminary': bool,   # True while conversation is still active
        'clusters': list | None,  # from Particiapi get_results on the Phase 6 zinvite
        'pg_available': bool,
      }

    Data sources:
      - Primary: PolisServerClient Postgres queries (votes_latest_unique).
      - Comparison/clusters: ParticiAPIClient.get_results(phase6_zinvite).
    Moderation is applied via results_filter before any aggregation.
    If Postgres is unavailable, vote counts fall back to None (surfaces degrade
    gracefully) but cluster data from Particiapi is still returned.
    """
    if not conv.phase6_polis_conversation_id:
        return None

    filt = results_filter or Phase6ResultsFilter.empty()

    # Confirmed featured statements, excluding any whose Phase 6 tid is suppressed.
    confirmed = [
        fs for fs in FeaturedStatement.query.filter_by(
            conversation_id=conv.id, confirmed_by_admin=True
        ).all()
        if fs.phase6_polis_statement_id is not None
        and fs.phase6_polis_statement_id not in filt.excluded_tids
        and fs.statement_text
    ]
    if not confirmed:
        return None

    p6_zinvite = conv.phase6_polis_conversation_id
    p2_zinvite = conv.polis_id
    excluded_pids = list(filt.excluded_pids)
    allowed_p6_tids = [fs.phase6_polis_statement_id for fs in confirmed]

    client = _polis_server_client()

    # Phase 2 counts keyed by polis_statement_id (Phase 2 tid).
    p2_tids = [fs.polis_statement_id for fs in confirmed if fs.polis_statement_id]

    # ── Aggregate fetches (cached) ────────────────────────────────────────────
    # ~5 Postgres/Particiapi round trips, identical for every viewer. Memoise them
    # for a short TTL (see _phase6_agg_cached). The per-participant overlay below
    # stays per-request, outside the cache.
    def _fetch_phase6_aggregate():
        p6c = client.get_phase6_vote_counts(p6_zinvite, allowed_p6_tids, excluded_pids)
        p6t = client.get_phase6_participant_count(p6_zinvite, excluded_pids)
        pg_ok = p6c is not None
        p2c = p2t = None
        if p2_tids and pg_ok:
            # Reuse get_phase6_vote_counts against the Phase 2 zinvite — same SQL works.
            p2c = client.get_phase6_vote_counts(p2_zinvite, p2_tids, excluded_pids)
            p2t = client.get_phase6_participant_count(p2_zinvite, excluded_pids)
        pa = None
        try:
            pa = PolisParticipantClient(
                current_app.config['PARTICIAPI_BASE']).get_results(p6_zinvite)
        except Exception:
            current_app.logger.exception(
                'Particiapi get_results failed for Phase 6 zinvite %s', p6_zinvite)
        return {'p6_counts': p6c, 'p6_total': p6t, 'pg_available': pg_ok,
                'p2_counts_raw': p2c, 'p2_total': p2t, 'pa_results': pa}

    _agg = _phase6_agg_cached(
        (p6_zinvite, p2_zinvite, tuple(sorted(allowed_p6_tids)),
         tuple(sorted(p2_tids)), tuple(sorted(excluded_pids))),
        _fetch_phase6_aggregate,
        # Don't memoise a degraded fetch (transient Postgres failure) for the full TTL.
        cacheable=lambda v: v['pg_available'],
    )
    p6_counts             = _agg['p6_counts']
    p6_total_participants = _agg['p6_total']
    pg_available          = _agg['pg_available']
    p2_counts_raw         = _agg['p2_counts_raw']
    p2_total_participants = _agg['p2_total']
    pa_results            = _agg['pa_results']

    # ── Personal votes (per-request; only when participation is present) ───────
    my_p2_votes: dict[int, int] = {}
    my_p6_votes: dict[int, int] = {}
    if participation and pg_available:
        # We need the Polis pid for the participant. Polis pids are not stored in
        # our DB — we use xid (hashed mw_user_id). The personal-votes query
        # therefore cannot run until we have a xid→pid mapping.
        # For now this is left as empty dicts (personal votes show as None).
        # TODO: store or derive Polis pid to enable per-participant vote display.
        pass

    clusters = None
    source_divergence = None
    if pa_results:
        clusters = pa_results.get('groups') or None
        # Sanity-check: compare Particiapi participant count vs Postgres count.
        pa_n = None
        if pa_results.get('majority'):
            # Particiapi doesn't expose a participant count directly in majority.
            # Use groups n_members sum as a proxy when available.
            groups = pa_results.get('groups') or []
            if groups:
                pa_n = sum(g.get('n_members', 0) for g in groups)
        if pa_n and p6_total_participants:
            source_divergence = abs(pa_n - p6_total_participants) / max(p6_total_participants, 1)
            if source_divergence > 0.05:
                current_app.logger.warning(
                    'Phase 6 source divergence %.1f%% for conv %s '
                    '(PG=%d, Particiapi=%d) — may indicate moderation sync lag',
                    source_divergence * 100, conv.slug, p6_total_participants, pa_n,
                )

    # ── Build per-statement rows ──────────────────────────────────────────────
    statements = []
    for fs in confirmed:
        p6_tid = fs.phase6_polis_statement_id
        p2_tid = fs.polis_statement_id

        p6_row = (p6_counts or {}).get(p6_tid, {'n_agree': 0, 'n_disagree': 0, 'n_pass': 0, 'n_voters': 0})
        p2_row = (p2_counts_raw or {}).get(p2_tid, None) if p2_tid else None

        p6_n = p6_row['n_voters']
        p6_pct_agree    = _pct(p6_row['n_agree'],    p6_n)
        p6_pct_disagree = _pct(p6_row['n_disagree'], p6_n)
        p6_pct_pass     = _pct(p6_row['n_pass'],     p6_n)

        p2_pct_agree = p2_pct_disagree = p2_pct_pass = None
        if p2_row:
            p2_n = p2_row['n_voters']
            p2_pct_agree    = _pct(p2_row['n_agree'],    p2_n)
            p2_pct_disagree = _pct(p2_row['n_disagree'], p2_n)
            p2_pct_pass     = _pct(p2_row['n_pass'],     p2_n)

        shift = round(p6_pct_agree - p2_pct_agree, 1) if p2_pct_agree is not None else None

        statements.append({
            'text':        fs.statement_text,
            'fs_id':       fs.id,
            'p6': {**p6_row, 'pct_agree': p6_pct_agree,
                   'pct_disagree': p6_pct_disagree, 'pct_pass': p6_pct_pass},
            'p2': ({**p2_row, 'pct_agree': p2_pct_agree,
                    'pct_disagree': p2_pct_disagree, 'pct_pass': p2_pct_pass}
                   if p2_row else None),
            'shift':       shift,
            'my_p2_vote':  my_p2_votes.get(p2_tid),
            'my_p6_vote':  my_p6_votes.get(p6_tid),
            'my_p2_label': _vote_label(my_p2_votes.get(p2_tid)),
            'my_p6_label': _vote_label(my_p6_votes.get(p6_tid)),
        })

    # Sort by largest absolute shift first; statements with no shift data go last.
    statements.sort(key=lambda s: abs(s['shift']) if s['shift'] is not None else -1, reverse=True)

    # Phase 2 consensus / divisiveness derived from the same data.
    p2_with_data = [s for s in statements if s['p2'] is not None and s['p2']['n_voters'] > 0]
    p2_consensus = sorted(p2_with_data,
                          key=lambda s: s['p2']['pct_agree'] or 0, reverse=True)[:3]
    # Most divisive = smallest gap between agree and disagree (most 50/50 split).
    p2_divisive  = sorted(p2_with_data,
                          key=lambda s: abs((s['p2']['pct_agree'] or 0) - (s['p2']['pct_disagree'] or 0)))[:3]

    return {
        'statements':            statements,
        'p6_participants':       p6_total_participants,
        'p2_participants':       p2_total_participants,
        # TODO: compute once xid→pid mapping is available (see personal-votes TODO above).
        'matched_participants':  None,
        'p2_consensus':          p2_consensus,
        'p2_divisive':           p2_divisive,
        'filter':                filt,
        'source_divergence':     source_divergence,
        'is_preliminary':        bool(conv.active),
        'clusters':              clusters,
        'pg_available':          pg_available,
    }


def _current_phase6_results_filter(conv) -> Phase6ResultsFilter:
    """Build the current moderation filter for Phase 6 report surfaces.

    Hidden Phase 6 statements are sourced from the Polis stats DB when available.
    Participant exclusions are reserved for #60; the field is intentionally present
    in snapshots now so final reports do not need another schema change later.
    """
    excluded_tids: set[int] = set()
    if conv.phase6_polis_conversation_id:
        try:
            rows = _polis_server_client().get_statements(conv.phase6_polis_conversation_id)
        except Exception:
            current_app.logger.exception(
                'Could not build Phase 6 report filter for %s', conv.slug)
            rows = None
        if rows:
            _, _, hidden = rows
            excluded_tids = {
                int(row['tid']) for row in hidden
                if row.get('tid') is not None
            }
    return Phase6ResultsFilter(excluded_tids=frozenset(excluded_tids),
                               excluded_pids=frozenset())


def _snapshot_report_filter(conv) -> Phase6ResultsFilter:
    filt = _current_phase6_results_filter(conv)
    conv.report_filter_snapshot = filt.to_snapshot()
    return filt


_math_recompute_last: dict[int, float] = {}  # conv.id → epoch of last trigger


def _reveal_context(conv, participation):
    """Identity-reveal timeline for a closed conversation (#70): when it closed, when
    the opt-in window opens (after the cooldown) and closes, the current state, and the
    days left while the window is open. Returns None when the conversation is not closed.
    """
    if not conv.closed_at:
        return None
    # Normalize ONCE to a tz-aware UTC instant, then derive everything from it — so the
    # displayed dates and the countdown target are the same correct UTC moments the
    # state math uses. (DB may hand back a naive datetime; deriving window dates off a
    # naive value would make the live countdown tick to the wrong instant.)
    closed = (conv.closed_at if conv.closed_at.tzinfo
              else conv.closed_at.replace(tzinfo=timezone.utc))
    opens_at  = closed + timedelta(days=_REVEAL_COOLDOWN_DAYS)
    closes_at = closed + timedelta(days=_REVEAL_COOLDOWN_DAYS + _REVEAL_WINDOW_DAYS)
    now = datetime.now(timezone.utc)
    age = now - closed
    if participation and participation.public_username:
        state = 'revealed'
    elif age >= timedelta(days=_REVEAL_COOLDOWN_DAYS + _REVEAL_WINDOW_DAYS):
        state = 'expired'
    elif age >= timedelta(days=_REVEAL_COOLDOWN_DAYS):
        state = 'open'
    else:
        state = 'pending'
    # The window's next boundary, as a UTC instant the client ticks a live countdown
    # against (per the design): opens_at while in cooldown, closes_at while open.
    target = opens_at if state == 'pending' else closes_at if state == 'open' else None
    # No-JS fallback: whole days to that boundary, partial day rounded UP so the final
    # open day never reads "0 days left" while the reveal POST is still accepted.
    days_left = 0
    if target is not None:
        _d = target - now
        days_left = max(0, _d.days + (1 if (_d.seconds or _d.microseconds) else 0))
    return {'closed_at': closed, 'opens_at': opens_at, 'closes_at': closes_at,
            'state': state, 'days_left': days_left,
            'countdown_target_iso': target.isoformat() if target else None,
            'cooldown_days': _REVEAL_COOLDOWN_DAYS, 'window_days': _REVEAL_WINDOW_DAYS}

# Canonical consultation phase sequence. One flag per stage; preparation = all off.
# Simple mode advances through this list (forward-only, exclusive). The existing
# independent toggles remain available in advanced mode.
PHASE_SEQUENCE = [
    {'key': 'preparation',        'label': 'Preparation',        'flag': None,
     'effect': 'setup only — participants cannot do anything yet'},
    {'key': 'submission',         'label': 'Explore',            'flag': 'phase_submission',
     'effect': 'participants can submit statements and vote on them'},
    {'key': 'featured_selection', 'label': 'Featured selection', 'flag': 'phase_personal_results',
     'effect': 'participants can see their personal results while you curate featured statements'},
    {'key': 'argument_mapping',   'label': 'Arguments',          'flag': 'phase_argument_mapping',
     'effect': 'participants can add and rate arguments on featured statements'},
    {'key': 'cleanup',            'label': 'Cleanup',            'flag': 'phase_cleanup',
     'effect': 'a quiet pause — participants are idle while you moderate the arguments before the informed vote'},
    {'key': 'informed_voting',    'label': 'Informed vote',      'flag': 'phase_informed_voting',
     'effect': 'participants vote again on featured statements (requires initialising Phase 6)'},
    {'key': 'public_results',     'label': 'Report',             'flag': 'phase_public_results',
     'effect': 'everyone can see the full aggregate results'},
]
_PHASE_BY_KEY = {stage['key']: stage for stage in PHASE_SEQUENCE}

PHASE_ROUTES = {
    'default_7': {
        'label': 'Default 7-step path',
        'description': 'Explore, featured selection, arguments, cleanup, informed vote, report.',
        'keys': [
            'preparation', 'submission', 'featured_selection', 'argument_mapping',
            'cleanup', 'informed_voting', 'public_results',
        ],
    },
    'no_informed_vote': {
        'label': 'Arguments, no informed vote',
        'description': 'Explore, feature statements, map arguments, then publish a report.',
        'keys': [
            'preparation', 'submission', 'featured_selection', 'argument_mapping',
            'cleanup', 'public_results',
        ],
    },
    'short_results': {
        'label': 'Short path to report',
        'description': 'Explore, curate featured statements, then publish results.',
        'keys': ['preparation', 'submission', 'featured_selection', 'public_results'],
    },
}
_DEFAULT_PHASE_ROUTE = 'default_7'
_PHASE_FLAGS = [s['flag'] for s in PHASE_SEQUENCE if s['flag']]
_ACTIVE_PHASE_KEYS = {'submission', 'argument_mapping', 'informed_voting'}


def _valid_phase_route(value: str | None) -> str:
    value = (value or _DEFAULT_PHASE_ROUTE).strip()
    return value if value in PHASE_ROUTES else _DEFAULT_PHASE_ROUTE


def _phase_sequence_for(conv) -> list[dict]:
    route = _valid_phase_route(getattr(conv, 'phase_route', _DEFAULT_PHASE_ROUTE))
    return [_PHASE_BY_KEY[key] for key in PHASE_ROUTES[route]['keys']]


def _phase_flags_for(conv) -> list[str]:
    return [s['flag'] for s in _phase_sequence_for(conv) if s['flag']]


def _route_has_phase(conv, key: str) -> bool:
    return any(stage['key'] == key for stage in _phase_sequence_for(conv))


def _in_cleanup_window(conv) -> bool:
    return (
        bool(conv.active)
        and not bool(conv.phase_informed_voting)
        and bool(conv.phase_public_results)
        and conv.closed_at is None
    )


def _current_stage_index(conv) -> int:
    """Furthest-along stage whose flag is on; 0 (preparation) if none on."""
    idx = 0
    for i, stage in enumerate(_phase_sequence_for(conv)):
        if stage['flag'] and getattr(conv, stage['flag']):
            idx = i
    return idx


def _active_phases(conv) -> set:
    """Return the set of currently-active phase keys for a conversation.

    Uses route flag names as keys. Also adds 'cleanup_window' (inferred:
    final report pending after participant activity ends) and 'closed'. Multiple keys are possible
    when the conversation is in advanced/non-linear mode.
    """
    phases = {s['key'] for s in _phase_sequence_for(conv) if s['flag'] and getattr(conv, s['flag'])}
    if not phases and not conv.closed_at:
        phases.add('preparation')
    if _in_cleanup_window(conv):
        phases.add('cleanup_window')
    if conv.closed_at:
        phases.add('closed')
    return phases


def _is_linear_phase_state(conv) -> bool:
    """True if at most one phase flag is on — the simple-mode invariant."""
    return sum(1 for f in _phase_flags_for(conv) if getattr(conv, f)) <= 1


def _advance_target_index(conv) -> int | None:
    """Index simple-mode advance would move to, or None if no forward move.

    Active conversation: one step forward. Closed conversation: jump straight
    to the final stage (public results) — closed consultations skip the
    intermediate steps. Returns None when already at/after the target.
    """
    sequence = _phase_sequence_for(conv)
    i = _current_stage_index(conv)
    last = len(sequence) - 1
    target = last if not conv.active else i + 1
    return target if target > i and target <= last else None


def _advance_confirm_message(conv) -> str:
    """Plain-language confirmation describing what the next forward move does
    to participants in this specific conversation."""
    i = _current_stage_index(conv)
    target = _advance_target_index(conv)
    if target is None:
        return ''
    sequence = _phase_sequence_for(conv)
    nxt = sequence[target]
    cur = sequence[i]
    parts = [f'Move to “{nxt["label"]}”? Participants: {nxt["effect"]}.']
    if cur['flag']:
        parts.append(f'This closes the current phase ({cur["effect"]}).')
    parts.append('This cannot be undone here — only a site admin can change it back.')
    return ' '.join(parts)


# Guided phase transitions (#156). Keyed by the TARGET stage. Each transition lists
# the preconditions the organizer must affirm (one checkbox each) before the "Move on"
# button enables. `check` (optional) names a machine-verifiable predicate, shown met/
# unmet and enforced server-side. Behavioural flags: runs_phase6_init, show_pause.
PHASE_TRANSITIONS = {
    'submission': {'preconditions': [
        {'id': 'seeds',       'label': 'Enough seed statements added (the voting loop isn’t empty)',
         'recommendation': 'seed_statements'},
        {'id': 'intro',       'label': 'Intro text / topic framing finalized'},
        {'id': 'access',      'label': 'Access policy (public / invite-only) set correctly'},
        {'id': 'modpolicy',   'label': 'Moderation policy decided and configured'},
        {'id': 'mods',        'label': 'Moderators appointed for this conversation'},
        {'id': 'live',        'label': 'I understand participants can submit and vote immediately'},
    ]},
    'featured_selection': {'preconditions': [
        {'id': 'no_submit',   'label': 'Participants no longer expect to submit new statements'},
        {'id': 'no_agree',    'label': 'Participants no longer expect to express agreement (voting closes)'},
        {'id': 'spectrum',    'label': 'The current statements cover the full spectrum of my theme'},
        {'id': 'ready_curate', 'label': 'I’m ready to select featured statements as a representative set'},
    ]},
    'argument_mapping': {'preconditions': [
        {'id': 'all_featured', 'label': 'I have selected all featured statements as a representative set',
         'check': 'has_confirmed_featured'},
        {'id': 'no_more_feat', 'label': 'I understand no further featured statements can be added later'},
        {'id': 'no_more_stmt', 'label': 'I understand participants cannot add further statements later'},
        {'id': 'args_visible', 'label': 'I understand featured statements become visible and participants add/rate arguments'},
    ]},
    'cleanup': {'preconditions': [
        {'id': 'args_collected', 'label': 'Argument mapping has run long enough — enough pro/con reasoning has been gathered'},
        {'id': 'args_close',     'label': 'I understand participants can no longer add or rate arguments after this'},
        {'id': 'ready_moderate', 'label': 'I’m ready to review and moderate the arguments before the informed vote'},
    ]},
    'informed_voting': {'runs_phase6_init': True, 'show_pause': True, 'preconditions': [
        {'id': 'args_modded', 'label': 'I’ve reviewed all arguments and removed those against moderation expectations',
         'recommendation': 'arguments_per_featured'},
        {'id': 'reinvite',    'label': 'I’m ready to invite participants back for the informed voting phase'},
        {'id': 'newcomers',   'label': 'I understand participants who didn’t take part earlier can join this round'},
    ]},
    'public_results': {'preconditions': [
        {'id': 'ran_long',    'label': 'The informed voting round has run long enough / had enough participation'},
        {'id': 'public',      'label': 'I understand participant activity ends and preliminary results remain visible'},
        {'id': 'no_identity', 'label': 'I understand results won’t expose individual identities (aggregate only)'},
        {'id': 'disclosure',  'label': 'I understand identity disclosure does not start until final publication'},
        {'id': 'inform',      'label': 'I’m ready to enter the organizer cleanup window'},
        {'id': 'final',       'label': 'I understand publishing the final report is a separate irreversible action'},
    ]},
}

# Recommended quantities are advisory unless a transition has a separate machine
# check. Organizers can choose a tier and override individual values per conversation.
_RECOMMENDATION_TIERS = {
    'simple': {
        'label': 'Simple topic',
        'seed_statements': 5,
        'featured_statements': 8,
        'arguments_per_featured': 2,
        'votes_per_statement': 25,
    },
    'medium': {
        'label': 'Medium topic',
        'seed_statements': 8,
        'featured_statements': 15,
        'arguments_per_featured': 3,
        'votes_per_statement': 50,
    },
    'complex': {
        'label': 'Complex topic',
        'seed_statements': 12,
        'featured_statements': 24,
        'arguments_per_featured': 4,
        'votes_per_statement': 75,
    },
}
_DEFAULT_RECOMMENDATION_TIER = 'medium'
_RECOMMENDATION_LABELS = {
    'seed_statements': 'seed statements before Explore opens',
    'featured_statements': 'featured statements for argument mapping',
    'arguments_per_featured': 'arguments per featured statement',
    'votes_per_statement': 'votes per statement before advancing',
}
_RECOMMENDED_FEATURED = _RECOMMENDATION_TIERS[_DEFAULT_RECOMMENDATION_TIER]['featured_statements']


def _recommendation_profile(conv) -> dict:
    raw = getattr(conv, 'recommended_quantities', None) or {}
    tier = raw.get('tier', _DEFAULT_RECOMMENDATION_TIER)
    if tier not in _RECOMMENDATION_TIERS:
        tier = _DEFAULT_RECOMMENDATION_TIER
    profile = dict(_RECOMMENDATION_TIERS[tier])
    profile['tier'] = tier
    for key in _RECOMMENDATION_LABELS:
        value = raw.get(key)
        if isinstance(value, int) and value > 0:
            profile[key] = value
    return profile


def _recommended_quantity(conv, key: str) -> int:
    return int(_recommendation_profile(conv).get(key, 0))


def _recommendation_note(conv, key: str) -> str | None:
    value = _recommended_quantity(conv, key)
    label = _RECOMMENDATION_LABELS.get(key)
    return f'{value} recommended {label}' if value and label else None


def _check_confirmed_featured(conv):
    """Machine check for the featured-statement precondition. Returns (met, note):
    met is True when at least one is confirmed (the hard requirement); note shows the
    selected count against the recommended target so the organizer can judge coverage."""
    n = (FeaturedStatement.query
         .filter_by(conversation_id=conv.id, confirmed_by_admin=True).count())
    recommended = _recommended_quantity(conv, 'featured_statements')
    note = f'{n} selected, {recommended} recommended' if n > 0 else None
    return n > 0, note


# Machine-verifiable preconditions: name → check(conv) -> (met: bool, note: str|None).
_PRECONDITION_CHECKS = {
    'has_confirmed_featured': _check_confirmed_featured,
}


def _transition_context(conv):
    """Context for the guided 'Move on' box and the route. Returns None when there is
    no forward move (non-linear state or already final). Otherwise a dict with the
    target stage, the source stage, the consequence text, and the preconditions with
    each machine `check` evaluated (met/unmet)."""
    if not _is_linear_phase_state(conv):
        return None
    target = _advance_target_index(conv)
    if target is None:
        return None
    sequence = _phase_sequence_for(conv)
    cur = sequence[_current_stage_index(conv)]
    nxt = sequence[target]
    cfg = PHASE_TRANSITIONS.get(nxt['key'], {})
    preconds = []
    for p in cfg.get('preconditions', []):
        met, note = None, None
        if p.get('check'):
            met, note = _PRECONDITION_CHECKS[p['check']](conv)
        elif p.get('recommendation'):
            note = _recommendation_note(conv, p['recommendation'])
        preconds.append({**p, 'met': met, 'note': note})
    # Consequence text — what opens, what closes, irreversibility.
    consequence = {
        'opens':  nxt['effect'],
        'closes': cur['effect'] if cur['flag'] else None,
    }
    return {
        'target': nxt,
        'source': cur,
        'preconditions': preconds,
        'consequence': consequence,
        'runs_phase6_init': bool(cfg.get('runs_phase6_init')),
        'show_pause': bool(cfg.get('show_pause')),
    }


def _is_schedulable_transition(ctx: dict | None) -> bool:
    if not ctx:
        return False
    source = ctx['source']['key']
    target = ctx['target']['key']
    return source in _ACTIVE_PHASE_KEYS and target not in _ACTIVE_PHASE_KEYS


def _clear_scheduled_transition(conv) -> None:
    conv.scheduled_transition_at = None
    conv.scheduled_transition_target = None
    conv.scheduled_transition_frozen = False


def _normalise_utc(value: datetime | None) -> datetime | None:
    if not value:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _parse_utc_timestamp(value: str) -> datetime | None:
    raw = (value or '').strip()
    if not raw:
        return None
    if raw.endswith('Z'):
        raw = raw[:-1] + '+00:00'
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format_countdown(target: datetime | None) -> str | None:
    target = _normalise_utc(target)
    if target is None:
        return None
    delta = target - datetime.now(timezone.utc)
    if delta.total_seconds() <= 0:
        return 'due now'
    days = delta.days
    hours, rem = divmod(delta.seconds, 3600)
    minutes = rem // 60
    if days:
        return f'{days}d {hours}h'
    if hours:
        return f'{hours}h {minutes}m'
    return f'{minutes}m'


def _schedule_context(conv) -> dict:
    ctx = _transition_context(conv)
    scheduled_at = _normalise_utc(conv.scheduled_transition_at)
    return {
        'transition': ctx,
        'can_schedule': _is_schedulable_transition(ctx),
        'scheduled_at': scheduled_at,
        'scheduled_target': conv.scheduled_transition_target,
        'scheduled_label': next(
            (stage['label'] for stage in _phase_sequence_for(conv)
             if stage['key'] == conv.scheduled_transition_target),
            conv.scheduled_transition_target,
        ),
        'frozen': bool(conv.scheduled_transition_frozen),
        'countdown': _format_countdown(scheduled_at),
    }


def _apply_phase_transition(conv, ctx: dict) -> tuple[str, str]:
    cur, nxt = ctx['source'], ctx['target']
    if cur['flag']:
        setattr(conv, cur['flag'], False)
    setattr(conv, nxt['flag'], True)
    _clear_scheduled_transition(conv)
    return cur['key'], nxt['key']


def _publish_final_report(conv) -> Phase6ResultsFilter:
    conv.phase_public_results = True
    conv.active = False
    conv.paused = False
    conv.closed_at = datetime.now(timezone.utc)
    _clear_scheduled_transition(conv)
    return _snapshot_report_filter(conv)


def _process_due_scheduled_transitions(now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    due = Conversation.query.filter(
        Conversation.active.is_(True),
        Conversation.scheduled_transition_at.isnot(None),
        Conversation.scheduled_transition_frozen.is_(False),
    ).all()
    fired = aborted = skipped = 0
    for conv in due:
        scheduled_at = _normalise_utc(conv.scheduled_transition_at)
        if scheduled_at is None or scheduled_at > now:
            skipped += 1
            continue
        ctx = _transition_context(conv)
        if (
            not _is_schedulable_transition(ctx)
            or conv.scheduled_transition_target != ctx['target']['key']
            or any(p.get('met') is False for p in ctx['preconditions'])
        ):
            conv.scheduled_transition_frozen = True
            db.session.commit()
            record_audit('phase.schedule.abort', conv_id=conv.id,
                         target_type='phase',
                         target_id=conv.scheduled_transition_target,
                         outcome='blocked')
            aborted += 1
            continue
        source, target = _apply_phase_transition(conv, ctx)
        db.session.commit()
        record_audit('phase.schedule.fire', conv_id=conv.id,
                     target_type='phase', target_id=target,
                     from_phase=source)
        if not _sync_vis_type(conv):
            current_app.logger.warning(
                'Scheduled phase transition fired for %s but vis_type sync failed',
                conv.slug)
        fired += 1
    return {'fired': fired, 'aborted': aborted, 'skipped': skipped}


OUTPUT_DEFINITIONS = [
    {
        'key': 'initial-clustering',
        'label': 'Initial clustering',
        'short_label': 'Clusters',
        'phase': 'Explore',
        'tooltip': 'After Explore phase: topic and participant clustering',
        'method': (
            'Votes from the Explore phase are grouped with Polis clustering. '
            'The page focuses first on consensus statements and breaking points; '
            'cluster details are shown only when the data is stable enough.'
        ),
        'status': 'provisional',
        'symbol': 'initial-clustering',
        'pending': (
            'Initial clustering becomes available after Explore closes. It will show '
            'which statements mostly united participants and which statements split them.'
        ),
    },
    {
        'key': 'argument-map',
        'label': 'Argument map',
        'short_label': 'Arguments',
        'phase': 'Arguments',
        'tooltip': 'After Arguments phase: argument mapping',
        'method': (
            'Featured statements are paired with pro and con arguments submitted by '
            'participants, then ordered by participant argument votes.'
        ),
        'status': 'provisional',
        'symbol': 'argument-map',
        'pending': (
            'The argument map opens when featured statements are visible for argument '
            'mapping. It will collect the strongest pro and con reasoning for each featured statement.'
        ),
    },
    {
        'key': 'preliminary-results',
        'label': 'Preliminary results',
        'short_label': 'Prelim',
        'phase': 'Informed vote',
        'tooltip': 'After Informed Vote and closing: preliminary results',
        'method': (
            'Informed-voting tallies are computed from the Phase 6 Polis round and '
            'shown as a live, lighter-weight preview before the final report is published.'
        ),
        'status': 'provisional',
        'symbol': 'preliminary-results',
        'pending': (
            'Preliminary results become available once informed voting is running. '
            'They are useful for orientation but can still change before publication.'
        ),
    },
    {
        'key': 'report',
        'label': 'Report',
        'short_label': 'Report',
        'phase': 'Publish',
        'tooltip': 'After closing and organizer confirmation: report',
        'method': (
            'The report uses the informed-voting tallies frozen at publication time, '
            'with moderation exclusions snapshotted so later cleanup cannot silently alter it.'
        ),
        'status': 'final',
        'symbol': 'report',
        'pending': (
            'The final report is published after the organizer completes cleanup. '
            'Publication freezes the report filter and starts the identity-reveal window.'
        ),
    },
    {
        'key': 'dataset',
        'label': 'Dataset',
        'short_label': 'Dataset',
        'phase': 'Opt-in identity window',
        'tooltip': 'After the opt-in identity window: download of the raw pseudonymous dataset',
        'method': (
            'The dataset is the raw pseudonymous results export for external analysis. '
            'It never exposes xid or Wikimedia user IDs.'
        ),
        'status': 'provisional',
        'symbol': 'dataset',
        'pending': (
            'The dataset finalizes after the opt-in identity window and post-close processing settle. '
            'Until then, re-exports may differ.'
        ),
    },
]


def _output_ready(conv, key: str) -> bool:
    phases = _active_phases(conv)
    if key == 'initial-clustering':
        return bool(phases & {
            'featured_selection', 'argument_mapping', 'cleanup', 'informed_voting',
            'public_results', 'cleanup_window', 'closed',
        })
    if key == 'argument-map':
        return bool(phases & {'argument_mapping', 'cleanup', 'informed_voting',
                              'public_results', 'cleanup_window', 'closed'})
    if key == 'preliminary-results':
        return bool(phases & {'informed_voting', 'public_results',
                              'cleanup_window', 'closed'})
    if key == 'report':
        return bool(conv.closed_at)
    if key == 'dataset':
        reveal = _reveal_context(conv, participation=None)
        return bool(reveal and reveal['state'] == 'expired')
    return False


def _output_href(conv, key: str) -> str:
    if key == 'report':
        return url_for('participant.conversation_report', slug=conv.slug)
    return url_for('participant.conversation_output', slug=conv.slug, output_key=key)


def _output_items(conv) -> list[dict]:
    items = []
    for definition in OUTPUT_DEFINITIONS:
        ready = _output_ready(conv, definition['key'])
        status = definition['status']
        if definition['key'] == 'dataset' and ready:
            status = 'final'
        item = {
            **definition,
            'ready': ready,
            'status': status,
            'state': 'ready' if ready else 'pending',
            'href': _output_href(conv, definition['key']),
        }
        items.append(item)
    return items


def _output_definition(output_key: str) -> dict | None:
    return next((item for item in OUTPUT_DEFINITIONS if item['key'] == output_key), None)


def _featured_counts(conv):
    """(confirmed, total) featured statements for one conversation."""
    base = FeaturedStatement.query.filter_by(conversation_id=conv.id)
    return (base.filter_by(confirmed_by_admin=True).count(), base.count())


def _argument_stats(conv):
    """Argument-phase aggregates for one conversation (Flask DB only).

    Counts human-authored, visible arguments — seeds (NULL proposer_pseudonym) and
    hidden/moderated arguments are excluded — plus the distinct participants
    who contributed or rated arguments.
    """
    visible = (db.session.query(Argument)
               .join(FeaturedStatement, Argument.featured_statement_id == FeaturedStatement.id)
               .filter(FeaturedStatement.conversation_id == conv.id,
                       Argument.hidden.is_(False),
                       Argument.proposer_pseudonym.isnot(None)))
    by_side = dict(visible.with_entities(Argument.side, db.func.count(Argument.id))
                          .group_by(Argument.side).all())
    n_contributors = (visible.with_entities(db.func.count(db.distinct(Argument.proposer_pseudonym)))
                             .scalar() or 0)
    n_raters = (db.session.query(db.func.count(db.distinct(ArgumentVote.participant_id)))
                .join(Argument, ArgumentVote.argument_id == Argument.id)
                .join(FeaturedStatement, Argument.featured_statement_id == FeaturedStatement.id)
                .filter(FeaturedStatement.conversation_id == conv.id,
                        Argument.hidden.is_(False)).scalar() or 0)
    return {
        'n_pro':          int(by_side.get('pro', 0)),
        'n_con':          int(by_side.get('con', 0)),
        'n_contributors': int(n_contributors),
        'n_raters':       int(n_raters),
    }


def _phase_tiles(conv, key, polis_stats, phase6_stats=None,
                 get_featured_counts=None, get_argument_stats=None):
    """Stat tiles for a single phase `key` (#165). Each tile is {value, label, unit?, note?}.

    Polis-derived tiles (vote/participant counts) are omitted when polis_stats is
    None — the template shows a loud warning instead. Flask-derived tiles (featured
    statements, arguments) always render, since they don't depend on Polis PG.

    `get_featured_counts` / `get_argument_stats` are optional accessors so a multi-phase
    caller can memoize those DB aggregates across phases (several active phases reuse the
    same featured/argument counts); they default to a fresh per-call query.
    """
    get_featured_counts = get_featured_counts or (lambda: _featured_counts(conv))
    get_argument_stats  = get_argument_stats  or (lambda: _argument_stats(conv))

    def polis_basic():
        if not polis_stats:
            return []
        return [
            {'value': polis_stats['n_participants'], 'label': 'participants'},
            {'value': polis_stats['n_votes'],        'label': 'votes cast'},
            {'value': polis_stats['n_statements'],
             'label': 'statements ({} seed)'.format(polis_stats['n_seed'])},
        ]

    tiles = []

    if key == 'submission':
        tiles = polis_basic()
        if polis_stats:
            tiles.append({'value': polis_stats['avg_votes'],    'label': 'avg votes / person'})
            tiles.append({'value': polis_stats['median_votes'], 'label': 'median votes / person'})

    elif key == 'featured_selection':
        confirmed, _ = get_featured_counts()
        tiles.append({'value': confirmed, 'label': 'featured selected',
                      'note': '{} recommended'.format(
                          _recommended_quantity(conv, 'featured_statements'))})
        if polis_stats:
            tiles.append({'value': polis_stats['n_statements'],   'label': 'candidate statements'})
            tiles.append({'value': polis_stats['n_participants'], 'label': 'participants'})

    elif key in ('argument_mapping', 'cleanup'):
        confirmed, _ = get_featured_counts()
        a = get_argument_stats()
        tiles.append({'value': confirmed,          'label': 'featured statements'})
        tiles.append({'value': a['n_pro'],         'label': 'pro arguments'})
        tiles.append({'value': a['n_con'],         'label': 'con arguments'})
        tiles.append({'value': a['n_contributors'], 'label': 'contributors'})
        if key == 'argument_mapping':
            tiles.append({'value': a['n_raters'],  'label': 'rating arguments'})

    elif key == 'informed_voting':
        confirmed, _ = get_featured_counts()
        seeded = (FeaturedStatement.query
                  .filter(FeaturedStatement.conversation_id == conv.id,
                          FeaturedStatement.confirmed_by_admin.is_(True),
                          FeaturedStatement.phase6_polis_statement_id.isnot(None))
                  .count())
        tiles.append({'value': '{}/{}'.format(seeded, confirmed), 'label': 'statements seeded'})
        if phase6_stats:
            tiles.append({'value': phase6_stats['n_participants'], 'label': 'voted this round'})
            tiles.append({'value': phase6_stats['n_votes'],        'label': 'informed votes'})
        if polis_stats:
            tiles.append({'value': polis_stats['n_participants'], 'label': 'round 1 participants'})

    else:  # preparation, public_results — show the headline totals
        tiles = polis_basic()

    return tiles


def _phase_stat_groups(conv, polis_stats, phase6_stats=None):
    """One stat group per *active* phase, in sequence order; each is
    {key, label, tiles}. In simple/linear mode this is a single group (the template
    renders it flat). In advanced mode several phases can be on at once, so the
    control box shows a group per phase — its name plus the tiles relevant to it —
    rather than only the furthest-along phase. Groups with no tiles are kept here and
    skipped by the template.

    The featured/argument DB aggregates are memoized across phases here: in advanced
    mode several active phases (e.g. argument_mapping + cleanup + informed_voting) each
    want the featured count, and they'd otherwise re-run the same COUNT/aggregate query
    per phase on every admin page load.
    """
    cache = {}

    def featured_counts():
        if 'featured' not in cache:
            cache['featured'] = _featured_counts(conv)
        return cache['featured']

    def argument_stats():
        if 'arguments' not in cache:
            cache['arguments'] = _argument_stats(conv)
        return cache['arguments']

    return [
        {'key':   _phase_sequence_for(conv)[i]['key'],
         'label': _phase_sequence_for(conv)[i]['label'],
         'tiles': _phase_tiles(conv, _phase_sequence_for(conv)[i]['key'], polis_stats, phase6_stats,
                               featured_counts, argument_stats)}
        for i in [j for j, s in enumerate(_phase_sequence_for(conv)) if s['key'] in _active_phases(conv)]
    ]


csrf    = CSRFProtect()
# No global default — limits applied per endpoint only.
# Toolforge provides TOOL_REDIS_URI; production startup validates Redis isolation.
def _ratelimit_identity_key() -> str:
    """Return a stable, non-reversible client identity for Flask-Limiter."""
    trust_proxy_headers = (
        _truthy(current_app.config.get('TRUST_PROXY_HEADERS'))
        or bool(os.environ.get('TOOL_TOOLFORGE_API_URL'))
    )
    if trust_proxy_headers:
        access_route = [addr.strip() for addr in request.access_route if addr.strip()]
        client_identity = access_route[0] if access_route else get_remote_address()
    else:
        client_identity = get_remote_address()
    identity_secret = current_app.config.get('RATELIMIT_IDENTITY_SECRET', '')
    if not identity_secret:
        return client_identity
    digest = hmac.new(str(identity_secret).encode('utf-8'),
                      client_identity.encode('utf-8'),
                      hashlib.sha256).hexdigest()
    return f'ip:{digest}'


limiter = Limiter(key_func=_ratelimit_identity_key, default_limits=[])


def _short_title(text: str, max_len: int = 80) -> str:
    if len(text) <= max_len:
        return text
    truncated = text[:max_len]
    last_space = truncated.rfind(' ')
    return (truncated[:last_space] if last_space > 0 else truncated) + '…'


def _safe_redirect(target: str, fallback: str) -> str:
    """Return target if it is a same-host relative URL, otherwise fallback."""
    if not target:
        return fallback
    ref  = urlparse(request.host_url)
    test = urlparse(urljoin(request.host_url, target))
    if test.scheme in ('http', 'https') and test.netloc == ref.netloc:
        return target
    return fallback


def _touch_last_engagement(participation: 'Participation | None', *, commit: bool = False) -> bool:
    """Update meaningful-action recency, throttled and best-effort."""
    if participation is None:
        return False
    now = datetime.now(timezone.utc)
    last = participation.last_engagement
    if last is not None and last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    if last is not None and now - last < _LAST_ENGAGEMENT_THROTTLE:
        return False
    participation.last_engagement = now
    if commit:
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            current_app.logger.exception('last_engagement update failed')
            return False
    return True


def _sanitise_text(html: str) -> str:
    return nh3.clean(html or '', tags=_TEXT_ALLOWED_TAGS,
                     attributes=_TEXT_ALLOWED_ATTRS, strip_comments=True)


def _valid_polis_id(v: str) -> bool:
    return bool(_POLIS_ID_RE.match(v or ''))


def _valid_slug(v: str) -> bool:
    return bool(_SLUG_RE.match(v or ''))


def _parse_conversation_form() -> dict:
    raw_policy = request.form.get('access_policy', 'public').strip()
    eligibility_event_id = request.form.get('eligibility_event_id', '').strip()
    eligibility_label = request.form.get('eligibility_label', '').strip()
    return {
        'title':         request.form.get('title', '').strip(),
        'intro_text':    _sanitise_text(request.form.get('intro_text', '')),
        'outro_text':    _sanitise_text(request.form.get('outro_text', '')),
        'access_policy': raw_policy if raw_policy in ACCESS_POLICIES else 'public',
        'eligibility_event_id': eligibility_event_id[:80] or None,
        'eligibility_label': eligibility_label[:255] or None,
    }


def _current_participant() -> 'Participant | None':
    if 'participant' in g:
        return g.participant
    xid = session.get('xid')
    if xid:
        g.participant = Participant.query.filter_by(xid=xid).first()
        return g.participant
    username = session.get('username')
    if not username:
        g.participant = None
        return None
    # Temporary compatibility for old server-side sessions created before xid
    # was stored. New sessions resolve by the stable Wikimedia user-id hash.
    g.participant = Participant.query.filter_by(mw_username=username).first()
    return g.participant


def _is_demo_session() -> bool:
    return bool(session.get('demo_conversation_id') and session.get('xid'))


def _demo_bound_conversation_id() -> int | None:
    value = session.get('demo_conversation_id')
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _exit_demo_session() -> None:
    """Drop the demo binding so the session can enter a real consultation (#293).

    Demo is a try-it-out space, not a cage: leaving it for a real conversation
    shouldn't 403. Clears the synthetic identity; the caller then follows the
    normal (login-required) flow for the real conversation.
    """
    session.pop('demo_conversation_id', None)
    session.pop('xid', None)
    session.pop('emailable', None)


def _demo_pseudonym() -> str:
    for _ in range(50):
        name = f"demo-{secrets.token_hex(4)}"
        if Participation.query.filter_by(pseudonym=name).first() is None:
            return name
    return f"demo-{secrets.token_hex(8)}"


def _ensure_demo_participation(conversation) -> 'Participation':
    """Return a participation for a demo conversation.

    A demo is a genuine demonstration conversation that records as usual (#293),
    so a **logged-in** user participates as themselves and stays logged in — only
    a **logged-out** visitor gets an anonymous, session-scoped synthetic guest.
    """
    if conversation.access_policy != 'demo':
        abort(404)

    # Logged-in real user: don't log them out — participate under their real
    # identity, auto-joining (no accept/pseudonym gate) so "try it" stays frictionless.
    participant = _current_participant()
    if 'username' in session and participant and not participant.is_demo:
        part = Participation.query.filter_by(
            participant_id=participant.id,
            conversation_id=conversation.id,
        ).first()
        if part is None:
            part = Participation(
                participant_id=participant.id,
                conversation_id=conversation.id,
                pseudonym=_demo_pseudonym(),
                eligibility_status='not_required',
            )
            db.session.add(part)
            db.session.commit()
        return part

    # A demo session may move freely between demo conversations (#293): reuse the
    # SAME synthetic guest and rebind the session to this demo rather than forbidding
    # it or minting a fresh guest per hop. The conversation-scoped proxy (#246) stays
    # safe because this rebinds `demo_conversation_id` to `conversation` before any
    # proxied call for it is made.
    if participant and participant.is_demo:
        part = Participation.query.filter_by(
            participant_id=participant.id,
            conversation_id=conversation.id,
        ).first()
        if part is None:
            part = Participation(
                participant_id=participant.id,
                conversation_id=conversation.id,
                pseudonym=_demo_pseudonym(),
                eligibility_status='not_required',
            )
            db.session.add(part)
            db.session.commit()
        session['demo_conversation_id'] = conversation.id   # rebind; same guest xid
        session.pop('username', None)
        return part

    # Brand-new visitor with no identity yet: mint the synthetic guest.
    for _ in range(20):
        token = secrets.token_hex(4)
        participant = Participant(
            mw_user_id=random.randint(_DEMO_MW_ID_MIN, _DEMO_MW_ID_MAX),
            mw_username=f'Demo-guest-{token}',
            xid=secrets.token_hex(32),
            xid_key_version=_XID_HMAC_VERSION,
            is_demo=True,
        )
        db.session.add(participant)
        try:
            db.session.flush()
        except IntegrityError:
            db.session.rollback()
            continue
        part = Participation(
            participant_id=participant.id,
            conversation_id=conversation.id,
            pseudonym=_demo_pseudonym(),
            eligibility_status='not_required',
        )
        db.session.add(part)
        db.session.commit()
        session['xid'] = participant.xid
        session['demo_conversation_id'] = conversation.id
        session.pop('username', None)
        session['emailable'] = False
        return part
    abort(503)


def _is_emailable(username: str) -> bool:
    try:
        resp = requests.get(
            'https://meta.wikimedia.org/w/api.php',
            params={'action': 'query', 'list': 'users', 'ususers': username,
                    'usprop': 'emailable', 'format': 'json'},
            headers={'User-Agent': _MW_USER_AGENT},
            timeout=2,
        )
        resp.raise_for_status()
        user = resp.json()['query']['users'][0]
        return 'emailable' in user
    except Exception:
        return False


def _eligibility_detail(payload: dict, *, reason: str | None = None) -> dict:
    """Small non-PII detail blob for cached AccountEligibility verdicts (#146)."""
    detail = {}
    if reason:
        detail['reason'] = reason
    for key in ('reason', 'message', 'event', 'criteria', 'failed', 'rules'):
        value = payload.get(key)
        if value not in (None, ''):
            detail[key] = value
    return detail


def _check_join_eligibility(conversation, participant) -> tuple[bool, str, dict]:
    """Return (allowed, status, detail) for the optional join-time gate (#146).

    The expected sidecar/tool contract is AccountEligibility-style JSON:
    GET <ACCOUNT_ELIGIBILITY_URL>?user=<mw_username>&event=<event_id>&format=json
    returning at least {"eligible": true|false}. Extra non-PII fields such as
    reason/criteria/rules are cached for admin/debug display.
    """
    event_id = (conversation.eligibility_event_id or '').strip()
    if not event_id:
        return True, 'not_required', {}
    endpoint = current_app.config.get('ACCOUNT_ELIGIBILITY_URL', '').strip()
    if not endpoint:
        return False, 'unavailable', {'reason': 'eligibility checker is not configured'}
    try:
        resp = requests.get(
            endpoint,
            params={'user': participant.mw_username, 'event': event_id, 'format': 'json'},
            headers={'User-Agent': _MW_USER_AGENT},
            timeout=5,
        )
        resp.raise_for_status()
        payload = resp.json()
    except Exception:
        current_app.logger.exception('eligibility check failed for event %s', event_id)
        return False, 'unavailable', {'reason': 'eligibility checker is unavailable'}
    allowed = bool(payload.get('eligible'))
    return allowed, 'eligible' if allowed else 'ineligible', _eligibility_detail(payload)


def _generate_pseudonyms(count: int = 5) -> list[str]:
    """Generate unique coolname pseudonyms not yet used in any Participation."""
    candidates: list[str] = []
    attempts = 0
    while len(candidates) < count and attempts < 200:
        attempts += 1
        name = coolname.generate_slug(2)
        if name in candidates:
            continue
        if Participation.query.filter_by(pseudonym=name).first() is None:
            candidates.append(name)
    return candidates


# ── Auth helpers ──────────────────────────────────────────────────────────────

def login_required(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        if 'username' not in session:
            if not request.path.startswith('/proxy/'):
                session['next'] = request.path
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return wrapper


def login_or_demo_required(f):
    """Like login_required, but also admits an active demo session.

    Demo conversations are genuine demonstration conversations (#293): an
    anonymous visitor plays through the full flow — vote, suggest statements,
    arguments — on a synthetic participant, and it records as usual. The demo
    session is bound to a single conversation (demo_conversation_id), and each
    route still runs its own access check (_check_conversation_access / the
    demo participation lookup), so this only widens *who may reach* the route,
    not *which conversation* they may act on.
    """
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        if 'username' not in session and not _is_demo_session():
            if not request.path.startswith('/proxy/'):
                session['next'] = request.path
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return wrapper


def _is_global_admin(participant: 'Participant | None' = None) -> bool:
    if session.get('username') in ADMIN_USERS:
        return True
    if participant is None:
        participant = _current_participant()
    if participant is None:
        return False
    return bool(participant.is_global_admin)


def _can_moderate(conversation, participant: 'Participant | None' = None) -> bool:
    if _is_global_admin(participant):
        return True
    if participant is None:
        participant = _current_participant()
    if participant is None:
        return False
    return AdminRole.query.filter(
        AdminRole.participant_id == participant.id,
        AdminRole.conversation_id == conversation.id,
    ).first() is not None


def _can_organize(conversation, participant: 'Participant | None' = None) -> bool:
    if _is_global_admin(participant):
        return True
    if participant is None:
        participant = _current_participant()
    if participant is None:
        return False
    return AdminRole.query.filter_by(
        participant_id=participant.id,
        conversation_id=conversation.id,
        role='organizer',
    ).first() is not None


def _conversation_role_label(conversation, participant: 'Participant | None' = None) -> str:
    if _is_global_admin(participant):
        return 'Global admin'
    if _can_organize(conversation, participant):
        return 'Organizer'
    return 'Moderator'


def admin_required(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        if not _is_global_admin():
            abort(403)
        return f(*args, **kwargs)
    return wrapper


def _polis_server_client() -> PolisServerClient:
    """Return a PolisServerClient from config.

    Always returns a client — DB-only methods (get_polis_stats,
    get_featured_candidates) work with db_url alone.  HTTP admin methods
    (moderate, add_seed, etc.) will raise PolisServerError at login if
    POLIS_SERVER_URL / POLIS_ADMIN_EMAIL / POLIS_ADMIN_PASSWORD are absent.
    """
    return PolisServerClient(
        current_app.config.get('POLIS_SERVER_URL', ''),
        current_app.config.get('POLIS_ADMIN_EMAIL', ''),
        current_app.config.get('POLIS_ADMIN_PASSWORD', ''),
        db_url=current_app.config.get('POLIS_DATABASE_URL', ''),
    )


def _require_mod_for_conv(conv_id: int) -> 'Conversation':
    """Return conversation or abort 403 if the current user can't moderate it."""
    conv = Conversation.query.get_or_404(conv_id)
    if not _can_moderate(conv):
        abort(403)
    return conv


def _require_organizer_for_conv(conv_id: int) -> 'Conversation':
    """Return conversation or abort 403 if the current user can't organize it."""
    conv = Conversation.query.get_or_404(conv_id)
    if not _can_organize(conv):
        abort(403)
    return conv


def _active_conversation_ban(conversation, participant: 'Participant | None'):
    if participant is None:
        return None
    return ConversationBan.query.filter_by(
        conversation_id=conversation.id,
        participant_id=participant.id,
        lifted_at=None,
    ).first()


def _abort_if_banned(conversation, participant: 'Participant | None') -> None:
    if _active_conversation_ban(conversation, participant):
        abort(403)


def _check_conversation_access(conversation, participant) -> None:
    # NOTE (#293): for a demo session this expects the session to be ALREADY bound
    # to `conversation` — the conversation view calls _ensure_demo_participation
    # (which rebinds) before this. Don't reorder those calls, or demo roaming
    # (visiting a demo the session isn't yet bound to) would 403 here.
    if _is_demo_session():
        if conversation.access_policy == 'demo' and _demo_bound_conversation_id() == conversation.id:
            return
        abort(403)
    if conversation.access_policy == 'demo':
        return
    if conversation.access_policy != 'invite_only':
        return
    if participant:
        existing = Participation.query.filter_by(
            participant_id=participant.id,
            conversation_id=conversation.id,
        ).first()
        if existing:
            return
    username = session.get('username')
    invited = ConversationInvite.query.filter_by(
        conversation_id=conversation.id,
        mw_username=username,
    ).first()
    if not invited:
        can_mod = _can_moderate(conversation, participant)
        abort(make_response(render_template(
            'forbidden_invite_only.html',
            conversation=conversation,
            can_moderate=can_mod,
        ), 403))


# ── Particiapi proxy ──────────────────────────────────────────────────────────

def _validate_same_origin(*, allow_missing_provenance: bool = False):
    """Abort 403 if the request does not appear to be same-origin.
    Used as a compensating control on CSRF-exempt endpoints."""
    sec_fetch = request.headers.get('Sec-Fetch-Site')
    if sec_fetch:
        if sec_fetch != 'same-origin':
            abort(403)
        return
    origin = request.headers.get('Origin')
    if origin:
        if urlparse(origin).netloc != urlparse(request.host_url).netloc:
            abort(403)
        return
    if allow_missing_provenance:
        return
    abort(403)


def _validate_fetch_csrf():
    """Validate Flask-WTF CSRF for JSON/fetch routes on the exempt proxy blueprint."""
    if not current_app.config.get('WTF_CSRF_ENABLED', True):
        return False
    token = (request.headers.get('X-CSRFToken')
             or request.headers.get('X-CSRF-Token')
             or request.form.get('csrf_token'))
    try:
        validate_csrf(token)
    except ValidationError:
        abort(400)
    return True


def _demo_proxy_allowed(pa_path: str, method: str) -> bool:
    conv_id = _demo_bound_conversation_id()
    if conv_id is None:
        return False
    conv = db.session.get(Conversation, conv_id)
    if conv is None or conv.access_policy != 'demo':
        return False
    if pa_path == 'api/session' and method in ('GET', 'POST'):
        return True
    prefix = f'api/conversations/{conv.polis_id}/'
    if method == 'GET' and pa_path.startswith(prefix):
        return True
    if method == 'PUT' and pa_path.startswith(prefix + 'votes/'):
        return True
    # Demo conversations run the full flow (#293), so a demo session may also
    # create statements — scoped to its own bound conversation.
    if method == 'POST' and pa_path.startswith(prefix + 'statements'):
        return True
    return False


def _proxy_auth_response(pa_path: str):
    if 'username' in session:
        return None
    if _is_demo_session():
        if _demo_proxy_allowed(pa_path, request.method):
            return None
        abort(403)
    if not request.path.startswith('/proxy/'):
        session['next'] = request.path
    return redirect(url_for('login'))


def _is_secure_pa_transport(base_url: str) -> bool:
    """True if the sub-secret can be sent safely: HTTPS, or HTTP to loopback only.

    X-Particiapi-Sub-Secret is a long-lived master credential; combined with an
    enumerable xid, a wire-capture of it lets an attacker forge any user's identity.
    Used only to emit a loud warning when it would traverse a cleartext non-loopback
    link (#245 review) — the actual fix is encrypting that hop.
    """
    u = urlparse(base_url)
    if u.scheme == 'https':
        return True
    host = (u.hostname or '').strip('[]')
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host == 'localhost'


def _conversation_subject(xid: str, conv) -> str:
    """Conversation-scoped participant subject for Particiapi's trusted-sub binding.

    Keyed by the **wiki-polis conversation id** so the same person resolves to the same
    Polis uid across devices *within* one conversation, but to a **different** uid in a
    different conversation — no cross-conversation linkage chain (#246). Using ``conv.id``
    (not the Polis zinvite) keeps it stable across the conversation's Phase-2 and Phase-6
    rounds, so an individual's initial and informed votes share one uid.
    """
    secret = current_app.config.get('PARTICIAPI_SUB_SECRET') or current_app.config['SECRET_KEY']
    return hmac.new(str(secret).encode(), f'{xid}:{conv.id}'.encode(), hashlib.sha256).hexdigest()


def _proxy_to_particiapi(pa_path: str, conv=None):
    """
    Proxy a browser request to Particiapi and return the response.

    When ``conv`` is given (the per-conversation proxy route), the asserted identity is
    **conversation-scoped** and the ``pa_session`` cookie is **path-scoped to that
    conversation**, so each conversation gets its own session/uid (no cross-conversation
    chain). The legacy unscoped route passes ``conv=None`` (bare-xid subject, root cookie).

    Browser ↔ Flask proxy ↔ Particiapi:
    - The browser stores a 'pa_session' cookie (Particiapi's session, renamed to
      avoid colliding with Flask's own 'session' cookie).
    - On each request we map pa_session → session when forwarding to Particiapi.
    - When Particiapi sets a new session cookie we rename it pa_session before
      sending it back to the browser.
    - CSRF tokens pass through unchanged via the X-CSRF-Token header.
    - This route is CSRF-exempt (the web component uses its own token scheme);
      Sec-Fetch-Site / Origin validation is the compensating control.
    """
    # Origin validation as compensating control for CSRF exemption.
    if request.method not in ('GET', 'HEAD'):
        _validate_same_origin()

    # CRIT-1: Reject path traversal and non-API paths.
    if '..' in pa_path.split('/') or not pa_path.startswith('api/'):
        abort(404)

    url = f"{current_app.config['PARTICIAPI_BASE']}/{pa_path}"

    forwarded_cookies = {}
    pa_cookie = request.cookies.get('pa_session')

    # Identity binding: on the session-create call, if the user is logged in and the
    # shared secret is configured, assert their stable identity (xid) to Particiapi so
    # they keep the same Polis uid across devices instead of a new anonymous uid each
    # session. Scoped to POST /api/session only — Particiapi consults the headers
    # nowhere else, so sending the secret on other requests is pure exposure surplus.
    _xid = session.get('xid')
    _sub_secret = current_app.config.get('PARTICIAPI_SUB_SECRET')
    # Conversation-scope the subject when we know the conversation, so the participant gets
    # a different uid per conversation (no chain) while staying stable across devices in it.
    _sub = _conversation_subject(_xid, conv) if (_xid and conv is not None) else _xid
    _bind_identity = (
        # Privacy invariant (#246): only ever bind on the conversation-scoped route.
        # With conv=None (legacy unscoped route) `_sub` is the bare xid, which would
        # re-link the participant across conversations — never assert that as identity.
        conv is not None
        and pa_path == 'api/session' and request.method == 'POST'
        and bool(_sub) and bool(_sub_secret)
    )

    # Loud warning (#245 review): the sub-secret is a master credential. If the transport
    # to Particiapi is cleartext non-loopback, a wire-capture forges any user's identity.
    # We still bind (the link is firewalled-private in prod) but surface it on every bind
    # so an unencrypted hop can't stay invisible. The real fix is encrypting the hop.
    if _bind_identity and not _is_secure_pa_transport(current_app.config['PARTICIAPI_BASE']):
        current_app.logger.warning(
            'PARTICIAPI_SUB_SECRET is being sent over a cleartext non-loopback transport '
            '(%s); encrypt the Toolforge<->VPS hop (WireGuard/TLS)',
            current_app.config['PARTICIAPI_BASE'])

    # On a bind we deliberately do NOT forward any existing pa_session cookie: a stale
    # (possibly anonymous) session would make Particiapi skip the bind path and pin the
    # user to a throwaway uid forever. Dropping it forces a clean re-bind to the xid.
    if pa_cookie and not _bind_identity:
        forwarded_cookies['session'] = pa_cookie

    # HIGH-5: Only forward known safe query parameters to Particiapi.
    _ALLOWED_PARAMS = frozenset({'create', 'zinvite', 'conversation_id', 'tid'})
    params = {k: v for k, v in request.args.items() if k in _ALLOWED_PARAMS}
    # If the web component calls POST /api/session with no existing session (and we're
    # not binding a stable identity), Particiapi 403s unless we add ?create=true.
    if (pa_path == 'api/session' and request.method == 'POST'
            and not pa_cookie and not _bind_identity):
        params['create'] = 'true'

    interaction_match = re.match(r'^api/conversations/([^/]+)/(votes(?:/\d+)?|statements/?)(?:/)?$', pa_path)
    if request.method in ('POST', 'PUT') and interaction_match:
        participant = _current_participant()
        conv = Conversation.query.filter_by(polis_id=interaction_match.group(1)).first()
        if conv:
            _abort_if_banned(conv, participant)

    headers = {}
    if request.method in ('POST', 'PUT'):
        csrf = request.headers.get('X-CSRF-Token')
        if csrf:
            headers['X-CSRF-Token'] = csrf
        if request.content_type:
            headers['Content-Type'] = request.content_type

    if _bind_identity:
        headers['X-Particiapi-Sub'] = _sub
        headers['X-Particiapi-Sub-Secret'] = _sub_secret

    try:
        upstream = polis_http.request(
            method=request.method,
            url=url,
            params=params,
            headers=headers,
            cookies=forwarded_cookies,
            json=request.get_json(silent=True),
            data=request.form if not request.is_json else None,
            timeout=10,
            # A proxy must hand 3xx back to the browser, never follow them itself:
            # `requests` preserves custom headers across cross-host redirects (it only
            # strips Authorization/Cookie), so following one could replay
            # X-Particiapi-Sub-Secret to a redirect-chosen host.
            allow_redirects=False,
        )
    except requests.RequestException:
        current_app.logger.exception('Particiapi proxy error')
        abort(502)

    # Particiapi returns 403 on /results/ when math hasn't run yet (no clusters).
    # The web component treats any 403 as a fatal error and clears the UI.
    # Convert to 200 with empty body so the component stays in a usable state.
    if upstream.status_code == 403 and pa_path.endswith('/results/'):
        flask_resp = make_response('{}', 200)
        flask_resp.headers['Content-Type'] = 'application/json'
        return flask_resp

    vote_match = re.match(r'^api/conversations/([^/]+)/votes(?:/\d+)?/?$', pa_path)
    # `upstream.ok` (status < 400) also covers 3xx; with allow_redirects=False a
    # redirect is a reachable terminal response here, so require an actual 2xx
    # before crediting engagement for a vote that was never confirmed applied.
    if upstream.status_code < 300 and request.method in ('POST', 'PUT') and vote_match:
        participant = _current_participant()
        if participant:
            conv = Conversation.query.filter_by(polis_id=vote_match.group(1)).first()
            if conv:
                part = Participation.query.filter_by(
                    participant_id=participant.id,
                    conversation_id=conv.id,
                ).first()
                _touch_last_engagement(part, commit=True)

    flask_resp = make_response(upstream.content, upstream.status_code)
    flask_resp.headers['Content-Type'] = upstream.headers.get(
        'Content-Type', 'application/json')
    if 'Location' in upstream.headers:
        # allow_redirects=False means a 3xx reaches here verbatim; forward Location
        # too or the browser gets a redirect status with nowhere to go (#245 follow-up).
        flask_resp.headers['Location'] = upstream.headers['Location']

    if 'session' in upstream.cookies:
        # Path-scope the session cookie to this conversation's proxy base, so the browser
        # only returns it on that conversation's calls — each conversation keeps its own
        # session/uid (#246). The legacy unscoped route keeps the root path.
        _cookie_path = f'/c/{conv.slug}/proxy/particiapi' if conv is not None else '/'
        flask_resp.set_cookie(
            'pa_session',
            upstream.cookies['session'],
            path=_cookie_path,
            httponly=True,
            samesite='Lax',
            secure=not current_app.debug,
        )

    return flask_resp


# ── App factory ───────────────────────────────────────────────────────────────

def _git_version() -> str:
    try:
        import subprocess
        return subprocess.check_output(
            ['git', 'rev-parse', '--short', 'HEAD'],
            cwd=os.path.dirname(os.path.abspath(__file__)),
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        return 'unknown'

_GIT_VERSION = _git_version()


# ── Route helpers (lifted from _register_routes; issue #90) ─────────────────

def _get_or_create_side_state(participant_id, fs_id, side, current_args):
    """Return ArgumentSideState, creating it on first view.

    On creation: randomise argument_order from current_args.
    On subsequent views: append any new arguments at a random position.
    Commits to DB if any change is made.
    """
    state = ArgumentSideState.query.filter_by(
        participant_id=participant_id,
        featured_statement_id=fs_id,
        side=side,
    ).first()
    changed = False
    if state is None:
        order = [a.id for a in current_args]
        random.shuffle(order)
        state = ArgumentSideState(
            participant_id=participant_id,
            featured_statement_id=fs_id,
            side=side,
            argument_order=order,
        )
        db.session.add(state)
        changed = True
    else:
        known = set(state.argument_order)
        new_ids = [a.id for a in current_args if a.id not in known]
        if new_ids:
            order = list(state.argument_order)
            for aid in new_ids:
                pos = random.randint(0, len(order))
                order.insert(pos, aid)
            state.argument_order = order
            changed = True
    if changed:
        db.session.commit()
    return state

def _statement_text_map(conv_polis_id: str) -> dict[int, str]:
    """Map Polis tid -> approved-statement text for a conversation.

    Single source for the three call sites that fetch statement text. Unified key
    rule: prefer the 'text' field, fall back to 'txt'. Does not catch fetch errors —
    callers decide how to degrade (PolisParticipantError propagates).

    Note on the key rule: PolisParticipantClient.get_statements returns both 'text'
    and 'txt' set to the same value, so the choice is a no-op there. The 'txt'
    fallback is load-bearing only for admin-client-shaped payloads (PolisAdminClient
    emits 'txt' without 'text') — keep it if this helper is ever pointed at that path.
    """
    client = PolisParticipantClient(current_app.config['PARTICIAPI_BASE'])
    _, approved, _ = client.get_statements(conv_polis_id)
    return {s['tid']: (s.get('text') or s.get('txt', '')) for s in approved}

def _build_featured_data(conv, participation, can_mod=False):
    """Return list of dicts for the argument tab, one per confirmed FS.

    Each dict: {fs, text, short_title, pro_args, con_args, pro_state,
                con_state, voted_ids, pro_gate, con_gate}
    Creates/updates ArgumentSideState records as a side effect.
    Moderators see hidden arguments (marked); participants never see them.
    Order is deterministically randomised per participant.
    """
    fss = (FeaturedStatement.query
           .filter_by(conversation_id=conv.id, confirmed_by_admin=True)
           .options(joinedload(FeaturedStatement.arguments))
           .order_by(FeaturedStatement.created_at)
           .all())
    if not fss:
        return []

    stmt_texts = {}
    try:
        stmt_texts = _statement_text_map(conv.polis_id)
    except Exception:
        pass

    pid = participation.participant_id
    voted_ids = {av.argument_id for av in
                 ArgumentVote.query.filter_by(participant_id=pid).all()}

    result = []
    for fs in fss:
        pro_args = [a for a in fs.arguments if a.side == 'pro' and (can_mod or not a.hidden)]
        con_args = [a for a in fs.arguments if a.side == 'con' and (can_mod or not a.hidden)]

        pro_state = _get_or_create_side_state(pid, fs.id, 'pro', pro_args)
        con_state = _get_or_create_side_state(pid, fs.id, 'con', con_args)

        def _ordered(args, state):
            arg_map = {a.id: a for a in args}
            return [arg_map[aid] for aid in state.argument_order if aid in arg_map]

        pro_proposed = Argument.query.filter_by(
            proposer_pseudonym=participation.pseudonym,
            featured_statement_id=fs.id, side='pro').first()
        con_proposed = Argument.query.filter_by(
            proposer_pseudonym=participation.pseudonym,
            featured_statement_id=fs.id, side='con').first()

        ordered_pro = _ordered(pro_args, pro_state)
        ordered_con = _ordered(con_args, con_state)
        pro_voted_count = sum(1 for a in ordered_pro if a.id in voted_ids)
        con_voted_count = sum(1 for a in ordered_con if a.id in voted_ids)

        text_value = (stmt_texts.get(fs.polis_statement_id)
                      or fs.statement_text
                      or f'Statement #{fs.polis_statement_id}')
        result.append({
            'fs':          fs,
            'text':        text_value,
            'short_title': _short_title(text_value),
            'pro_args':  ordered_pro,
            'con_args':  ordered_con,
            'pro_state': pro_state,
            'con_state': con_state,
            'voted_ids': voted_ids,
            'pro_gate':  bool(pro_proposed or pro_state.skipped),
            'con_gate':  bool(con_proposed or con_state.skipped),
            'pro_proposed': pro_proposed,
            'con_proposed': con_proposed,
            'k': int((conv.argument_vote_data or {}).get('K', 2)),
            'pro_voted_count': pro_voted_count,
            'con_voted_count': con_voted_count,
        })

    random.Random(pid).shuffle(result)
    return result

def _require_arg_participation(slug):
    """Return (conv, participation) or abort. Checks active + argument phase."""
    conv = Conversation.query.filter_by(slug=slug).first_or_404()
    if not conv.active or conv.paused or not conv.phase_argument_mapping:
        abort(403)
    participant = _current_participant()
    if not participant:
        abort(403)
    part = Participation.query.filter_by(
        participant_id=participant.id,
        conversation_id=conv.id,
    ).first_or_404()
    _abort_if_banned(conv, participant)
    return conv, part

def _backfill_statement_texts(conv, confirmed: list) -> bool:
    """Fetch and store statement_text for any confirmed FS that is missing it."""
    missing = [fs for fs in confirmed if not fs.statement_text]
    if not missing:
        return False
    try:
        text_by_tid = _statement_text_map(conv.polis_id)
    except PolisParticipantError:
        return False
    changed = False
    for fs in missing:
        text = text_by_tid.get(fs.polis_statement_id, '')
        if text:
            fs.statement_text = text
            changed = True
    if changed:
        db.session.commit()
    return changed

def _fetch_statement_text(conv_polis_id: str, tid: int) -> str:
    try:
        return _statement_text_map(conv_polis_id).get(tid, '')
    except PolisParticipantError:
        return ''


# ── Particiapi proxy + participant statement submit ──────────────────────────
# The generic Particiapi proxy is CSRF-exempt with _validate_same_origin() as the
# compensating control and bridges the browser's renamed 'pa_session' cookie to
# Particiapi's 'session'. First-party statement submission lives on
# participant_bp so Flask-WTF validates CSRF normally, while the same-origin
# provenance check remains as an extra browser-request guard.
proxy_bp = Blueprint('proxy', __name__)
admin_bp = Blueprint('admin', __name__)
participant_bp = Blueprint('participant', __name__)

@participant_bp.post('/c/<slug>/statements/new')
@login_or_demo_required
@limiter.limit('20 per minute')
def conversation_statement_new(slug):
    """Submit an entirely new statement; enforces per-participant quota and
    records the Polis statement ID for novelty tracking."""
    # Statement submit is on participant_bp, so Flask-WTF validates CSRF; we also
    # re-check the token here so the same-origin guard can relax the provenance
    # requirement when a valid CSRF token is present (#129).
    csrf_validated = _validate_fetch_csrf()
    _validate_same_origin(allow_missing_provenance=csrf_validated)

    conv = Conversation.query.filter_by(slug=slug).first_or_404()
    if not conv.active or conv.paused or not conv.phase_submission:
        abort(403)
    participant = _current_participant()
    if not participant:
        abort(401)

    _abort_if_banned(conv, participant)

    body = request.get_json(silent=True) or {}
    text = (body.get('text') or '').strip()
    derived_from = body.get('derived_from')
    if derived_from in ('', None):
        derived_from = None

    if not text or len(text) > 280:
        abort(400)
    if derived_from is not None and not isinstance(derived_from, int):
        abort(400)

    new_stmt_max = conv.argument_vote_data.get('new_stmt_max', 3) if conv.argument_vote_data else 3

    # Optimistic quota fast-fail (unlocked read): reject an over-quota submit before the
    # upstream statement fetch + similarity work. The authoritative check runs under the
    # lock below, right before the submit, so the quota stays race-safe. Wording
    # suggestions (derived_from set) are exempt — only genuinely new statements count
    # against the quota (#296 / spec_functional-design.md).
    part = Participation.query.filter_by(
        participant_id=participant.id, conversation_id=conv.id,
    ).first_or_404()
    if derived_from is None and len(part.new_stmt_ids or []) >= new_stmt_max:
        return jsonify({'error': 'quota_exceeded'}), 403

    # Derivative gate — statement fetch + similarity + threshold. Read-only w.r.t. the
    # participation row, and a rejection here means we never submit, so it runs OFF the
    # quota lock (keeping the lock's held time off the statement fetch and the similarity
    # sidecar). `scores` is reused for provenance below — computed once, not twice.
    parent_text = None
    scores = None
    if derived_from is not None:
        try:
            text_map = _statement_text_map(conv.polis_id)
        except PolisParticipantError:
            current_app.logger.exception('could not load statements for derivative parent')
            abort(502)
        parent_text = text_map.get(derived_from)
        if parent_text is None:
            return jsonify({'error': 'unknown_parent_statement'}), 400
        scores = _statement_similarity_scores(text, parent_text)
        model, score = _preferred_similarity_score(scores)
        threshold = _derivative_similarity_threshold()
        if threshold and score is not None and score < threshold:
            return jsonify({
                'error': 'derivative_similarity_too_low',
                'message': 'This looks like a different claim. Revise it closer to the original, or submit it as a new statement instead.',
                'model': model,
                'similarity': score,
                'threshold': threshold,
            }), 409

    # Establish the Particiapi session + CSRF token BEFORE taking the row lock, so the
    # ~5s session-create round-trip does not run while holding the FOR UPDATE lock (#275
    # M3) — that keeps the lock's held time down to just the submit + append. Only the
    # submit must stay atomic with the quota recheck (so a rejected submit never orphans
    # a Polis statement); the session bootstrap does not.
    pa_cookie = request.cookies.get('pa_session')
    forwarded = {'session': pa_cookie} if pa_cookie else {}
    base = current_app.config['PARTICIAPI_BASE']
    try:
        sess_resp = polis_http.post(
            f'{base}/api/session',
            cookies=forwarded,
            params={'create': 'true'},
            timeout=5,
        )
        if not sess_resp.ok:
            current_app.logger.error('Particiapi session error: %s', sess_resp.status_code)
            abort(502)
        csrf_token = sess_resp.json().get('csrf_token', '')
        new_pa_cookie = sess_resp.cookies.get('session')
        submit_cookies = {'session': new_pa_cookie or pa_cookie} if (new_pa_cookie or pa_cookie) else {}
    except requests.RequestException:
        current_app.logger.exception('Particiapi error in conversation_statement_new')
        abort(502)

    # Authoritative quota check under a row lock, held through the submit + append so two
    # concurrent submits from the same participant can't both pass. (Per-participation
    # lock — only serialises one participant's own concurrent submits, not the
    # conversation.) The submit stays inside the lock so a quota-rejected request never
    # creates an orphaned Polis statement.
    #
    # populate_existing() is REQUIRED: the optimistic read above already loaded this row
    # into the session identity map, so without it the locking SELECT returns the stale
    # cached instance (SQLAlchemy does not refresh an already-loaded object on
    # with_for_update) and the recheck below would run on pre-lock data — defeating the
    # lock entirely.
    part = Participation.query.filter_by(
        participant_id=participant.id, conversation_id=conv.id,
    ).populate_existing().with_for_update().first_or_404()
    if derived_from is None and len(part.new_stmt_ids or []) >= new_stmt_max:
        return jsonify({'error': 'quota_exceeded'}), 403

    try:
        stmt_resp = polis_http.post(
            f'{base}/api/conversations/{conv.polis_id}/statements/',
            json={'text': text},
            cookies=submit_cookies,
            headers={'X-CSRF-Token': csrf_token},
            timeout=10,
        )
    except requests.RequestException:
        current_app.logger.exception('Particiapi error in conversation_statement_new')
        abort(502)

    if stmt_resp.status_code == 201:
        stmt_id = stmt_resp.json().get('id')
        if stmt_id is not None:
            if derived_from is None:
                ids = list(part.new_stmt_ids or [])
                ids.append(stmt_id)
                part.new_stmt_ids = ids
            else:
                record_statement_provenance(conv.id, stmt_id, derived_from,
                                            parent_text=parent_text, new_text=text,
                                            scores=scores)
        _touch_last_engagement(part)
        db.session.commit()
        flask_resp = make_response(stmt_resp.content, 201)
        flask_resp.headers['Content-Type'] = 'application/json'
    else:
        current_app.logger.error('Particiapi statement error: %s', stmt_resp.status_code)
        flask_resp = make_response(jsonify({'error': 'upstream_error'}), 502)

    if new_pa_cookie:
        flask_resp.set_cookie('pa_session', new_pa_cookie, httponly=True,
                              samesite='Lax', secure=not current_app.debug)
    return flask_resp

@proxy_bp.route('/proxy/particiapi/<path:pa_path>',
                methods=['GET', 'POST', 'PUT'])
@limiter.limit('180 per minute')
def proxy_particiapi(pa_path):
    auth_resp = _proxy_auth_response(pa_path)
    if auth_resp is not None:
        return auth_resp
    return _proxy_to_particiapi(pa_path)


@proxy_bp.route('/c/<slug>/proxy/particiapi/<path:pa_path>',
                methods=['GET', 'POST', 'PUT'])
@limiter.limit('180 per minute')
def proxy_particiapi_scoped(slug, pa_path):
    """Per-conversation proxy: conversation-scoped identity + path-scoped session cookie,
    so a participant gets a different Polis uid per conversation (#246). Uses the global
    proxy's demo-aware auth (_proxy_auth_response) rather than @login_required so demo
    sessions work through the scoped proxy too. (admin_bp is defined above on this branch.)"""
    auth_resp = _proxy_auth_response(pa_path)
    if auth_resp is not None:
        return auth_resp
    conv = Conversation.query.filter_by(slug=slug).first_or_404()
    return _proxy_to_particiapi(pa_path, conv=conv)
# nh3 tag allowlist for CSV import sanitisation — no HTML tags permitted.
_NH3_NO_TAGS: frozenset[str] = frozenset()


@participant_bp.get('/help/statements')
def statement_guidance():
    return render_template('guidance_statement.html')


@participant_bp.get('/help/arguments')
def argument_guidance():
    return render_template('guidance_argument.html')


_FLAG_CATEGORY_LABELS = {
    'personal_attack': 'Personal attack',
    'privacy': 'Privacy violation',
    'off_topic': 'Off-topic',
    'other': 'Other',
}


def _parse_seed_text_lines(raw_text: str) -> ParseResult:
    """Parse textarea seed import: one non-empty line per candidate statement."""
    result = ParseResult()
    seen: set[str] = set()
    non_empty_rows: list[tuple[int, str]] = [
        (idx, line.strip())
        for idx, line in enumerate((raw_text or '').splitlines(), start=1)
        if line.strip()
    ]
    if len(non_empty_rows) > MAX_ROWS:
        for idx, _line in non_empty_rows[MAX_ROWS:]:
            result.errors.append(RowError(
                idx,
                f'skipped — import limit of {MAX_ROWS} rows reached',
                limit_skipped=True,
            ))
        non_empty_rows = non_empty_rows[:MAX_ROWS]

    for idx, text in non_empty_rows:
        if len(text) > MAX_TEXT_CHARS:
            result.errors.append(RowError(
                idx,
                f'text is too long ({len(text)} characters; max {MAX_TEXT_CHARS})',
            ))
            continue
        if text in seen:
            result.errors.append(RowError(idx, 'duplicate — already added from an earlier row'))
            continue
        seen.add(text)
        result.texts.append(text)
    return result


def _reject_seed_import_parse_errors(result: ParseResult, source_label: str) -> bool:
    """Flash parse errors and return True when an import should stop before Polis I/O."""
    limit_skipped = [e for e in result.errors if e.limit_skipped]
    if limit_skipped:
        total_rows = len(result.texts) + len(result.errors)
        current_app.logger.warning(
            '%s import rejected — row limit exceeded: %d rows, max %d',
            source_label,
            total_rows,
            MAX_ROWS,
        )
        flash(
            f'✗ Import rejected — nothing was imported. {source_label} contains '
            f'{total_rows} lines, maximum is {MAX_ROWS}. Reduce it and try again. '
            f'(Parse errors may also be present — fix everything before retrying.)',
            'import_result',
        )
        return True

    parse_errors = [e for e in result.errors if not e.limit_skipped]
    if parse_errors:
        for err in parse_errors:
            flash(f'Row {err.row}: {err.reason}.', 'import_row_error')
        # All-or-nothing: a single invalid line rejects the whole import so the admin
        # never ends up with a silently partial paste.
        flash('✗ Import rejected — nothing was added. One invalid line rejects the '
              'whole import; fix the lines listed above and try again.', 'import_result')
        return True
    return False


def _import_seed_statement_texts(conv: Conversation, texts: list[str]) -> dict:
    """Shared post-parse seed import pipeline: sanitize, dedup, bulk-add, report."""
    seen_sanitised: set[str] = set()
    sanitised_texts: list[str] = []
    for raw_text in texts:
        san = nh3.clean(raw_text, tags=_NH3_NO_TAGS)
        # Re-apply formula-prefix stripping: nh3 decodes HTML entities (e.g.
        # &equals; -> =) which can reintroduce leading formula chars.
        san = strip_formula_prefixes(san).strip()
        san_key = san.casefold()
        if not san or san_key in seen_sanitised:
            continue  # drop empty-after-nh3 and nh3-induced within-batch dupes
        seen_sanitised.add(san_key)
        sanitised_texts.append(san)

    existing_texts: set[str] = set()
    dedup_check_failed = False
    try:
        rows = _polis_server_client().get_statements(conv.polis_id)
        if rows is not None:
            pending, approved, hidden = rows
            for stmt in pending + approved + hidden:
                existing_texts.add(stmt['txt'].strip().casefold())
    except Exception:
        current_app.logger.exception('Could not fetch existing statements for dedup check')
        dedup_check_failed = True

    dedup_errors = []
    clean_texts = []
    for sanitised in sanitised_texts:
        if sanitised.casefold() in existing_texts:
            dedup_errors.append(
                f'"{sanitised[:60]}{"…" if len(sanitised) > 60 else ""}" — already exists in this conversation'
            )
        else:
            clean_texts.append(sanitised)

    successes = 0
    polis_skipped = []  # Polis rejected these — likely already exist
    polis_errors = []  # Polis login or unexpected failure
    if clean_texts:
        try:
            successes, failures = _polis_server_client().bulk_add_seeds(conv.polis_id, clean_texts)
            for text, exc in failures:
                current_app.logger.warning('Polis rejected imported row (%s, may already exist): %s',
                                           type(exc).__name__, exc)
                polis_skipped.append(f'"{text[:60]}{"…" if len(text) > 60 else ""}"')
        except PolisServerError as exc:
            current_app.logger.exception('Polis login failed during bulk import')
            polis_errors = [f'"{t[:60]}{"…" if len(t) > 60 else ""}"' for t in clean_texts]
            polis_failure_message = exc.admin_message
        else:
            polis_failure_message = None
    else:
        polis_failure_message = None

    if dedup_check_failed:
        flash('Could not check for existing statements — some may be duplicates. Check server logs.', 'warning')

    for msg in dedup_errors:
        flash(f'Skipped — {msg}.', 'warning')
    for msg in polis_skipped:
        flash(f'Already in Polis, skipped: {msg}.', 'warning')
    for msg in polis_errors:
        flash(f'Could not send to Polis: {msg}.', 'error')
    if not successes and not dedup_errors and not polis_skipped and not polis_errors:
        flash('No statements were imported — there were no valid rows.', 'warning')

    n_skipped = len(dedup_errors) + len(polis_skipped)
    n_errors = len(polis_errors)
    if successes and not n_skipped:
        flash(f'✓ {successes} statement{"s" if successes != 1 else ""} imported', 'import_result')
    elif successes:
        flash(f'✓ {successes} imported — ⚠ {n_skipped} skipped', 'import_result')
    elif n_errors:
        flash(f'✗ Import failed — {polis_failure_message}', 'import_result')
    elif n_skipped:
        flash(f'⚠ 0 imported — {n_skipped} already existed in Polis', 'import_result')
    else:
        flash('⚠ 0 imported — Polis returned no result', 'import_result')

    return {'successes': successes, 'skipped': n_skipped, 'errors': n_errors}


def _seed_statement_lock_reason(conv: Conversation) -> str | None:
    """Why seed-statement controls are locked, or None when seeding is allowed."""
    if not conv.active:
        return 'Seed statements are locked because this conversation is permanently closed.'
    if conv.phase_submission:
        return None
    if not any(getattr(conv, flag) for flag in _PHASE_FLAGS):
        return None
    return 'Seed statements are locked because statement submission has ended.'


def _delete_local_conversation(conv: Conversation) -> None:
    """Delete local rows owned by a conversation after external deletion guards pass."""
    conv_id = conv.id
    ContentFlag.query.filter_by(conversation_id=conv_id).delete(synchronize_session=False)
    featured_ids = [
        row[0] for row in db.session.query(FeaturedStatement.id)
        .filter_by(conversation_id=conv_id)
        .all()
    ]
    if featured_ids:
        arg_ids = [
            row[0] for row in db.session.query(Argument.id)
            .filter(Argument.featured_statement_id.in_(featured_ids))
            .all()
        ]
        if arg_ids:
            ArgumentVote.query.filter(
                ArgumentVote.argument_id.in_(arg_ids)
            ).delete(synchronize_session=False)
            Argument.query.filter(
                Argument.id.in_(arg_ids)
            ).delete(synchronize_session=False)
        ArgumentSideState.query.filter(
            ArgumentSideState.featured_statement_id.in_(featured_ids)
        ).delete(synchronize_session=False)
        FeaturedStatement.query.filter(
            FeaturedStatement.id.in_(featured_ids)
        ).delete(synchronize_session=False)

    provenance_ids = [
        row[0] for row in db.session.query(StatementProvenance.id)
        .filter_by(conversation_id=conv_id)
        .all()
    ]
    if provenance_ids:
        StatementSimilarityScore.query.filter(
            StatementSimilarityScore.provenance_id.in_(provenance_ids)
        ).delete(synchronize_session=False)
        StatementProvenance.query.filter(
            StatementProvenance.id.in_(provenance_ids)
        ).delete(synchronize_session=False)

    ConversationBan.query.filter_by(conversation_id=conv_id).delete(synchronize_session=False)
    ConversationInvite.query.filter_by(conversation_id=conv_id).delete(synchronize_session=False)
    AdminRole.query.filter_by(conversation_id=conv_id).delete(synchronize_session=False)
    Participation.query.filter_by(conversation_id=conv_id).delete(synchronize_session=False)
    AuditEvent.query.filter_by(conversation_id=conv_id).update(
        {'conversation_id': None},
        synchronize_session=False,
    )
    db.session.delete(conv)


def _parse_content_flag_form() -> tuple[str, str | None]:
    category = (request.form.get('category') or '').strip()
    if category not in FLAG_CATEGORIES:
        abort(400, description='Choose a valid reason for the flag.')
    detail = nh3.clean((request.form.get('detail') or '').strip(),
                       tags=_NH3_NO_TAGS)[:1000]
    if category == 'other' and not detail:
        abort(400, description='Explain the reason when choosing Other.')
    return category, detail or None


def _existing_open_flag(
    conv_id: int,
    participant_id: int,
    content_type: str,
    category: str,
    *,
    statement_tid: int | None = None,
    argument_id: int | None = None,
) -> ContentFlag | None:
    query = ContentFlag.query.filter_by(
        conversation_id=conv_id,
        participant_id=participant_id,
        content_type=content_type,
        category=category,
        status='open',
    )
    if content_type == 'statement':
        query = query.filter_by(statement_tid=statement_tid)
    else:
        query = query.filter_by(argument_id=argument_id)
    return query.first()


def _flag_rows_for_admin(conv: Conversation) -> list[dict]:
    flags = (ContentFlag.query
             .filter_by(conversation_id=conv.id)
             .options(joinedload(ContentFlag.argument))
             .order_by(ContentFlag.status, ContentFlag.created_at.desc())
             .all())
    statement_tids = [f.statement_tid for f in flags if f.content_type == 'statement']
    statement_texts = {}
    if statement_tids:
        try:
            statement_texts = _statement_text_map(conv.polis_id)
        except PolisParticipantError:
            statement_texts = {}
    rows = []
    for flag in flags:
        if flag.content_type == 'argument':
            target_text = flag.argument.body if flag.argument else 'Argument removed'
            target_label = f'Argument #{flag.argument_id}'
        else:
            target_text = statement_texts.get(flag.statement_tid, 'Statement text unavailable')
            target_label = f'Statement #{flag.statement_tid}'
        rows.append({
            'flag': flag,
            'category_label': _FLAG_CATEGORY_LABELS.get(flag.category, flag.category),
            'target_label': target_label,
            'target_text': target_text,
        })
    return rows


def _conversation_ban_log_rows(conv: Conversation) -> list[dict]:
    events = (AuditEvent.query
              .filter(AuditEvent.conversation_id == conv.id,
                      AuditEvent.operation.in_(('participant.ban', 'participant.unban')))
              .order_by(AuditEvent.ts.desc())
              .all())
    target_ids = []
    actor_ids = []
    for event in events:
        try:
            target_ids.append(int(event.target_id))
        except (TypeError, ValueError):
            pass
        if event.actor_participant_id:
            actor_ids.append(event.actor_participant_id)

    pseudonyms = {
        p.participant_id: p.pseudonym
        for p in Participation.query.filter(
            Participation.conversation_id == conv.id,
            Participation.participant_id.in_(target_ids or [-1]),
        ).all()
    }
    actors = {
        p.id: p.mw_username
        for p in Participant.query.filter(
            Participant.id.in_(actor_ids or [-1]),
        ).all()
    }

    rows = []
    for event in events:
        try:
            target_id = int(event.target_id)
        except (TypeError, ValueError):
            target_id = None
        rows.append({
            'action': 'Unbanned' if event.operation == 'participant.unban' else 'Banned',
            'ts': event.ts,
            'pseudonym': pseudonyms.get(target_id, 'participant'),
            'actor': actors.get(event.actor_participant_id, 'administrator'),
            'scope': 'conversation',
        })
    return rows

# ── Admin ─────────────────────────────────────────────────────────────────

@admin_bp.get('/admin')
@login_required
@admin_required
def admin():
    conversations  = (Conversation.query
                      .order_by(Conversation.created_at.desc()).all())
    participants   = (Participant.query
                      .order_by(Participant.mw_username).all())
    global_admins  = (Participant.query
                      .filter_by(is_global_admin=True)
                      .order_by(Participant.mw_username).all())
    return render_template('admin.html',
                           conversations=conversations,
                           participants=participants,
                           global_admins=global_admins,
                           phase_routes=PHASE_ROUTES,
                           )

@admin_bp.get('/admin/conversations/<int:conv_id>')
@login_required
def admin_conversation_detail(conv_id):
    conv       = _require_mod_for_conv(conv_id)
    phase_sequence = _phase_sequence_for(conv)
    conv_roles = (AdminRole.query
                   .filter_by(conversation_id=conv_id)
                   .all())
    can_manage_roles  = _is_global_admin()
    participants      = (
        Participant.query.order_by(Participant.mw_username).all()
        if can_manage_roles else []
    )
    invite_count      = ConversationInvite.query.filter_by(conversation_id=conv_id).count()
    participant_count = Participation.query.filter_by(conversation_id=conv_id).count()
    open_flag_count   = ContentFlag.query.filter_by(
        conversation_id=conv_id,
        status='open',
    ).count()
    can_organize      = _can_organize(conv)
    client            = _polis_server_client()
    polis_stats       = client.get_polis_stats(conv.polis_id)
    delete_vote_count = client.get_valid_vote_count(conv.polis_id) if _is_global_admin() else None
    # Informed-voting round-2 tiles render whenever that phase is active (its flag is
    # on) — including alongside other phases in advanced mode — so fetch the phase-6
    # stats and gate the warning on the flag itself.
    phase6_stats      = (client.get_polis_stats(conv.phase6_polis_conversation_id)
                         if (conv.phase_informed_voting or _in_cleanup_window(conv))
                         and conv.phase6_polis_conversation_id
                         else None)
    # Loud warning only when Polis PG is configured but unreachable — never when it is
    # deliberately not wired (local/dev), where None is expected. Unavailable if the
    # round-1 fetch failed, or — when informed voting is active — the round-2 (phase-6)
    # fetch failed (without that a phase-6 outage would drop the round-2 tiles silently).
    polis_pg_configured     = bool(current_app.config.get('POLIS_DATABASE_URL'))
    polis_stats_unavailable = polis_pg_configured and (
        polis_stats is None
        or ((conv.phase_informed_voting or _in_cleanup_window(conv))
            and conv.phase6_polis_conversation_id
            and phase6_stats is None))
    phase6_results    = (_build_phase6_results(conv, participation=None)
                         if (conv.phase_informed_voting or _in_cleanup_window(conv))
                         and conv.phase6_polis_conversation_id
                         else None)
    reveal            = _reveal_context(conv, participation=None)
    return render_template('admin_conversation.html',
                           conversation=conv,
                           conv_roles=conv_roles,
                           participants=participants,
                           invite_count=invite_count,
                           participant_count=participant_count,
                           open_flag_count=open_flag_count,
                           polis_stats=polis_stats,
                           phase_stat_groups=_phase_stat_groups(conv, polis_stats, phase6_stats),
                           polis_stats_unavailable=polis_stats_unavailable,
                           phase6_results=phase6_results,
                           reveal=reveal,
                           delete_vote_count=delete_vote_count,
                           admin_roles=ADMIN_ROLES,
                           can_manage_roles=can_manage_roles,
                           can_organize=can_organize,
                           role_label=_conversation_role_label(conv),
                           phase_sequence=phase_sequence,
                           current_stage_index=_current_stage_index(conv),
                           active_stage_indices=[i for i, s in enumerate(phase_sequence)
                                                  if s['key'] in _active_phases(conv)],
                           linear_phase_state=_is_linear_phase_state(conv),
                           advance_target_index=_advance_target_index(conv),
                           transition=_transition_context(conv),
                           phase_routes=PHASE_ROUTES,
                           recommendation_tiers=_RECOMMENDATION_TIERS,
                           recommendation_labels=_RECOMMENDATION_LABELS,
                           recommendation_profile=_recommendation_profile(conv),
                           schedule=_schedule_context(conv),
                           cleanup_window=_in_cleanup_window(conv))


@admin_bp.get('/admin/conversations/<int:conv_id>/participants')
@login_required
def admin_conversation_participants(conv_id):
    conv = _require_mod_for_conv(conv_id)
    participations = (Participation.query
                      .join(Participant)
                      .filter(Participation.conversation_id == conv_id)
                      .options(joinedload(Participation.participant))
                      .order_by(Participant.mw_username)
                      .all())

    # Arguments store the proposer's pseudonym (not a participant FK) for privacy (#113),
    # so attribute submitted-argument counts by pseudonym within this conversation.
    submitted_counts = dict(
        db.session.query(Argument.proposer_pseudonym, db.func.count(Argument.id))
        .join(FeaturedStatement, Argument.featured_statement_id == FeaturedStatement.id)
        .filter(FeaturedStatement.conversation_id == conv_id,
                Argument.proposer_pseudonym.isnot(None))
        .group_by(Argument.proposer_pseudonym)
        .all()
    )
    voted_counts = dict(
        db.session.query(ArgumentVote.participant_id, db.func.count(ArgumentVote.id))
        .join(Argument, ArgumentVote.argument_id == Argument.id)
        .join(FeaturedStatement, Argument.featured_statement_id == FeaturedStatement.id)
        .filter(FeaturedStatement.conversation_id == conv_id)
        .group_by(ArgumentVote.participant_id)
        .all()
    )

    client = _polis_server_client()
    pg_configured = bool(current_app.config.get('POLIS_DATABASE_URL'))
    statement_progress_unavailable = pg_configured
    # One batched query for every participant's progress — previously this issued a
    # fresh Postgres connection per participant (O(N) connects on this page, which
    # stalled at 1000 participants).
    progress_by_xid = None
    if pg_configured:
        progress_by_xid = client.get_statement_progress_for_participants(
            conv.polis_id, [p.participant.xid for p in participations])
        if progress_by_xid is not None:
            statement_progress_unavailable = False
    active_bans = {
        ban.participant_id: ban
        for ban in ConversationBan.query.filter_by(
            conversation_id=conv_id,
            lifted_at=None,
        ).all()
    }
    rows = []
    for part in participations:
        progress_row = (
            progress_by_xid.get(part.participant.xid)
            if progress_by_xid is not None else None
        )
        rows.append({
            'participation': part,
            'participant': part.participant,
            'statement_progress': progress_row,
            'arguments_submitted': int(submitted_counts.get(part.pseudonym, 0)),
            'arguments_voted': int(voted_counts.get(part.participant_id, 0)),
            'active_ban': active_bans.get(part.participant_id),
        })

    return render_template(
        'admin_participants.html',
        conversation=conv,
        rows=rows,
        statement_progress_unavailable=statement_progress_unavailable,
    )


@admin_bp.get('/admin/conversations/<int:conv_id>/flags')
@login_required
def admin_conversation_flags(conv_id):
    conv = _require_mod_for_conv(conv_id)
    rows = _flag_rows_for_admin(conv)
    open_count = sum(1 for row in rows if row['flag'].status == 'open')
    return render_template(
        'admin_flags.html',
        conversation=conv,
        rows=rows,
        open_count=open_count,
    )


@admin_bp.post('/admin/conversations/<int:conv_id>/flags/<int:flag_id>/resolve')
@login_required
def admin_flag_resolve(conv_id, flag_id):
    conv = _require_mod_for_conv(conv_id)
    flag = ContentFlag.query.filter_by(
        id=flag_id,
        conversation_id=conv.id,
    ).first_or_404()
    note = nh3.clean((request.form.get('resolution_note') or '').strip(),
                     tags=_NH3_NO_TAGS)[:1000]
    actor = _current_participant()
    flag.status = 'resolved'
    flag.resolved_at = datetime.now(timezone.utc)
    flag.resolved_by_id = actor.id if actor else None
    flag.resolution_note = note or None
    db.session.commit()
    record_audit('content_flag.resolve', conv_id=conv.id, target_type='content_flag',
                 target_id=flag.id, content_type=flag.content_type)
    flash('Flag marked resolved.', 'success')
    return redirect(url_for('admin.admin_conversation_flags', conv_id=conv.id))


@admin_bp.post('/admin/conversations/<int:conv_id>/participants/<int:participant_id>/ban')
@login_required
def admin_participant_ban(conv_id, participant_id):
    conv = _require_mod_for_conv(conv_id)
    Participation.query.filter_by(
        conversation_id=conv_id,
        participant_id=participant_id,
    ).first_or_404()
    existing = ConversationBan.query.filter_by(
        conversation_id=conv_id,
        participant_id=participant_id,
        lifted_at=None,
    ).first()
    if existing:
        flash('Participant is already banned from this conversation.', 'warning')
        return redirect(url_for('admin.admin_conversation_participants', conv_id=conv_id))

    summary = nh3.clean((request.form.get('summary') or '').strip(), tags=_NH3_NO_TAGS)[:1000]
    actor = _current_participant()
    ban = ConversationBan(
        conversation_id=conv_id,
        participant_id=participant_id,
        banned_by_id=actor.id if actor else None,
        summary=summary or None,
    )
    db.session.add(ban)
    db.session.commit()
    record_audit('participant.ban', conv_id=conv.id, target_type='participant',
                 target_id=participant_id, scope='conversation',
                 summary_present=bool(summary))
    flash('Participant banned from this conversation.', 'success')
    return redirect(url_for('admin.admin_conversation_participants', conv_id=conv_id))


@admin_bp.post('/admin/conversations/<int:conv_id>/participants/<int:participant_id>/unban')
@login_required
def admin_participant_unban(conv_id, participant_id):
    conv = _require_mod_for_conv(conv_id)
    ban = ConversationBan.query.filter_by(
        conversation_id=conv_id,
        participant_id=participant_id,
        lifted_at=None,
    ).first_or_404()
    summary = nh3.clean((request.form.get('summary') or '').strip(), tags=_NH3_NO_TAGS)[:1000]
    actor = _current_participant()
    ban.lifted_at = datetime.now(timezone.utc)
    ban.lifted_by_id = actor.id if actor else None
    ban.lift_summary = summary or None
    db.session.commit()
    record_audit('participant.unban', conv_id=conv.id, target_type='participant',
                 target_id=participant_id, scope='conversation',
                 summary_present=bool(summary))
    flash('Participant unbanned from this conversation.', 'success')
    return redirect(url_for('admin.admin_conversation_participants', conv_id=conv_id))

@admin_bp.post('/admin/conversations/new')
@login_required
@admin_required
def admin_conversation_new():
    slug   = request.form.get('slug', '').strip().lower()
    fields = _parse_conversation_form()
    phase_route = _valid_phase_route(request.form.get('phase_route'))

    if not fields['title']:
        flash('Title is required.', 'error')
        return redirect(url_for('admin.admin'))
    if not _valid_slug(slug):
        flash(
            'Invalid slug — use lowercase letters, numbers, and hyphens only, '
            'no spaces or special characters (e.g. climate-2026).',
            'error',
        )
        return redirect(url_for('admin.admin'))

    polis_configured = all(current_app.config.get(k) for k in (
        'POLIS_SERVER_URL', 'POLIS_ADMIN_EMAIL', 'POLIS_ADMIN_PASSWORD'))
    if polis_configured:
        try:
            polis_id = _polis_server_client().create_conversation(fields['title'], strict_moderation=True)
        except PolisServerError:
            current_app.logger.exception('Polis conversation creation failed')
            flash('Could not create the Polis conversation. Check server logs for details.', 'error')
            return redirect(url_for('admin.admin'))
    else:
        # Fallback: accept manually supplied polis_id (local dev / misconfigured prod)
        polis_id = request.form.get('polis_id', '').strip()
        if not _valid_polis_id(polis_id):
            return redirect(url_for('admin.admin', error=(
                'POLIS_SERVER_URL / POLIS_ADMIN_EMAIL / POLIS_ADMIN_PASSWORD not configured. '
                'Pass a polis_id manually or set the env vars.'
            )))

    conv = Conversation(slug=slug, active=True, polis_id=polis_id,
                        phase_route=phase_route, **fields)
    db.session.add(conv)
    db.session.commit()
    record_audit('conversation.create', conv_id=conv.id, slug=slug)
    return redirect(url_for('admin.admin'))

@admin_bp.post('/admin/conversations/<int:conv_id>/edit')
@login_required
def admin_conversation_edit(conv_id):
    conv   = _require_organizer_for_conv(conv_id)
    fields = _parse_conversation_form()

    if not fields['title']:
        flash('Title is required.', 'error')
        return redirect(url_for('admin.admin_conversation_detail', conv_id=conv_id))

    conv.title         = fields['title']
    conv.intro_text    = fields['intro_text']
    conv.outro_text    = fields['outro_text']
    # Access policy is freely switchable, including to/from demo (#293): demo
    # conversations are genuine demonstration conversations that record as usual,
    # so designating an existing conversation as a demo (or back) is allowed.
    # Existing participations are untouched; new visitors follow the new policy.
    # (_parse_conversation_form clamps this to ACCESS_POLICIES.)
    conv.access_policy = fields['access_policy']
    db.session.commit()
    record_audit('conversation.edit', conv_id=conv.id)
    return redirect(url_for('admin.admin_conversation_detail', conv_id=conv_id))

@admin_bp.post('/admin/conversations/<int:conv_id>/pause')
@login_required
@admin_required
def admin_conversation_pause(conv_id):
    conv = Conversation.query.get_or_404(conv_id)
    if not conv.active:
        abort(400)
    conv.paused = not conv.paused
    db.session.commit()
    record_audit('conversation.pause', conv_id=conv.id, paused=conv.paused)
    return redirect(url_for('admin.admin_conversation_detail', conv_id=conv_id))

@admin_bp.post('/admin/conversations/<int:conv_id>/close')
@login_required
@admin_required
def admin_conversation_close(conv_id):
    conv = Conversation.query.get_or_404(conv_id)
    if not conv.active:
        abort(400)
    if _in_cleanup_window(conv):
        required = {
            'cleanup_reviewed_results',
            'cleanup_moderated_flagged',
            'cleanup_reviewed_exclusions',
            'cleanup_report_intro',
        }
        if any(request.form.get(field) != 'on' for field in required):
            flash('Complete every cleanup checklist item before publishing the final report.', 'error')
            return redirect(url_for('admin.admin_conversation_detail', conv_id=conv_id))
        if _route_has_phase(conv, 'informed_voting') and not conv.phase6_polis_conversation_id:
            flash('Phase 6 must be initialised before publishing the final report.', 'error')
            return redirect(url_for('admin.admin_conversation_detail', conv_id=conv_id))
    filt = _publish_final_report(conv)
    db.session.commit()
    _invalidate_phase6_results_cache(conv)  # report view must reflect the close immediately
    record_audit('conversation.close', conv_id=conv.id,
                 excluded_tids=len(filt.excluded_tids),
                 excluded_pids=len(filt.excluded_pids))
    return redirect(url_for('admin.admin_conversation_detail', conv_id=conv_id))


@admin_bp.post('/admin/conversations/<int:conv_id>/recommendations')
@login_required
@admin_required
def admin_conversation_recommendations(conv_id):
    conv = Conversation.query.get_or_404(conv_id)
    tier = request.form.get('tier', _DEFAULT_RECOMMENDATION_TIER)
    if tier not in _RECOMMENDATION_TIERS:
        tier = _DEFAULT_RECOMMENDATION_TIER
    config = {'tier': tier}
    for key in _RECOMMENDATION_LABELS:
        value = request.form.get(key, type=int)
        if value is not None and value > 0:
            config[key] = min(value, 999)
    conv.recommended_quantities = config
    db.session.commit()
    record_audit('recommendations.set', conv_id=conv.id, tier=tier)
    return redirect(url_for('admin.admin_conversation_detail', conv_id=conv_id))


@admin_bp.post('/admin/conversations/<int:conv_id>/phase/schedule')
@login_required
@admin_required
def admin_conversation_phase_schedule(conv_id):
    conv = Conversation.query.get_or_404(conv_id)
    action = request.form.get('action', 'set')
    if action == 'cancel':
        _clear_scheduled_transition(conv)
        db.session.commit()
        record_audit('phase.schedule.cancel', conv_id=conv.id)
        return redirect(url_for('admin.admin_conversation_detail', conv_id=conv_id))
    if action in ('freeze', 'unfreeze') and conv.scheduled_transition_at:
        conv.scheduled_transition_frozen = action == 'freeze'
        db.session.commit()
        record_audit(f'phase.schedule.{action}', conv_id=conv.id,
                     target_type='phase',
                     target_id=conv.scheduled_transition_target)
        return redirect(url_for('admin.admin_conversation_detail', conv_id=conv_id))

    ctx = _transition_context(conv)
    if not _is_schedulable_transition(ctx):
        flash('Only active-to-passive wind-down transitions can be scheduled.', 'error')
        return redirect(url_for('admin.admin_conversation_detail', conv_id=conv_id))
    scheduled_at = _parse_utc_timestamp(request.form.get('scheduled_at', ''))
    if scheduled_at is None:
        flash('Enter a valid UTC timestamp.', 'error')
        return redirect(url_for('admin.admin_conversation_detail', conv_id=conv_id))
    if scheduled_at <= datetime.now(timezone.utc):
        flash('Scheduled transition time must be in the future.', 'error')
        return redirect(url_for('admin.admin_conversation_detail', conv_id=conv_id))
    conv.scheduled_transition_at = scheduled_at
    conv.scheduled_transition_target = ctx['target']['key']
    conv.scheduled_transition_frozen = False
    db.session.commit()
    record_audit('phase.schedule.set', conv_id=conv.id,
                 target_type='phase', target_id=ctx['target']['key'])
    return redirect(url_for('admin.admin_conversation_detail', conv_id=conv_id))

@admin_bp.post('/admin/conversations/<int:conv_id>/delete')
@login_required
@admin_required
def admin_conversation_delete(conv_id):
    conv = Conversation.query.get_or_404(conv_id)
    client = _polis_server_client()
    valid_vote_count = client.get_valid_vote_count(conv.polis_id)
    if valid_vote_count is None:
        flash('Cannot delete this conversation because Polis vote data could not be verified.', 'error')
        return redirect(url_for('admin.admin_conversation_detail', conv_id=conv_id))
    if valid_vote_count != 0:
        flash(
            f'Cannot delete this conversation because it has {valid_vote_count} valid vote'
            f'{"s" if valid_vote_count != 1 else ""}.',
            'error',
        )
        return redirect(url_for('admin.admin_conversation_detail', conv_id=conv_id))

    try:
        client.close_and_hide_conversation(conv.polis_id)
    except PolisServerError:
        current_app.logger.exception('Polis conversation close/hide failed')
        flash('Could not hide the Polis conversation. Nothing was deleted.', 'error')
        return redirect(url_for('admin.admin_conversation_detail', conv_id=conv_id))

    slug = conv.slug
    polis_id = conv.polis_id
    record_audit('conversation.delete', conv_id=conv.id, target_type='conversation',
                 target_id=conv.id, valid_vote_count=valid_vote_count)
    _delete_local_conversation(conv)
    db.session.commit()
    current_app.logger.info('deleted empty conversation slug=%s polis_id=%s', slug, polis_id)
    flash('Conversation deleted.', 'success')
    return redirect(url_for('admin.admin'))

def _sync_vis_type(conv) -> bool:
    """Mirror the results phases onto Polis's vis_type, which gates GET /results/
    (off by default — otherwise the Results tab stays empty no matter how many votes
    are cast). Returns False on a Polis failure (best-effort; never raises).

    CAVEAT: vis_type is a single all-or-nothing Polis flag — it cannot distinguish
    public vs personal results. Enabling it for *personal* results makes the full
    aggregate /results/ fetchable by any logged-in participant through the proxy.
    Withholding/scoping the aggregate for personal results (the anti-anchoring intent)
    must be enforced app-side — tracked as #81 Part 2 — not via vis_type.
    """
    if not conv.polis_id:
        return True
    results_on = conv.phase_public_results or conv.phase_personal_results
    try:
        _polis_server_client().set_vis_type(conv.polis_id, 1 if results_on else 0)
        return True
    except PolisServerError as exc:
        current_app.logger.warning('vis_type update failed for %s: %s', conv.slug, exc)
        return False


@admin_bp.post('/admin/conversations/<int:conv_id>/phases')
@login_required
@admin_required
def admin_conversation_phases(conv_id):
    # Advanced mode: independent toggles, out of order, NO readiness checks — the admin
    # is responsible for the resulting state (the guided flow enforces preconditions like
    # ≥1 featured statement before argument mapping; this route deliberately does not, so
    # a single rejected toggle never silently discards the whole save).
    conv = Conversation.query.get_or_404(conv_id)
    conv.phase_submission       = bool(request.form.get('phase_submission'))
    conv.phase_personal_results = bool(request.form.get('phase_personal_results'))
    conv.phase_argument_mapping = bool(request.form.get('phase_argument_mapping'))
    conv.phase_cleanup          = bool(request.form.get('phase_cleanup'))
    conv.phase_public_results   = bool(request.form.get('phase_public_results'))
    conv.phase_informed_voting  = bool(request.form.get('phase_informed_voting'))
    db.session.commit()
    record_audit('phase.set', conv_id=conv.id, phases={
        'submission': conv.phase_submission, 'personal_results': conv.phase_personal_results,
        'argument_mapping': conv.phase_argument_mapping, 'cleanup': conv.phase_cleanup,
        'public_results': conv.phase_public_results, 'informed_voting': conv.phase_informed_voting})

    if not _sync_vis_type(conv):
        flash('Phases saved, but updating results visibility in Polis failed — '
              'results may not appear until you save phases again.', 'error')
    # A vis_type change alters what /results/ returns — drop any cached aggregate.
    _invalidate_phase6_results_cache(conv)
    return redirect(url_for('admin.admin_conversation_detail', conv_id=conv_id))


@admin_bp.post('/admin/conversations/<int:conv_id>/phase/advance')
@login_required
def admin_conversation_advance(conv_id):
    """Guided 'Move on' phase transition (#156). The organizer must affirm every
    precondition (one checkbox each) before this is accepted; the route re-enforces
    that server-side and re-runs machine-checkable preconditions.

    Exclusive: the target stage's flag is set and the current stage's flag cleared.
    Active conversation → one step forward; closed → jump to public results. Backward
    / custom-state repair is an advanced-mode action, so a non-linear state is refused.
    The Informed-voting transition runs Phase 6 init atomically; the Public-results
    transition to Report ends participant activity and enters the cleanup window;
    the separate publish action stamps closed_at and starts the identity-reveal window.
    """
    conv = _require_organizer_for_conv(conv_id)
    redirect_to = redirect(url_for('admin.admin_conversation_detail', conv_id=conv_id))

    ctx = _transition_context(conv)
    if ctx is None:
        if not _is_linear_phase_state(conv):
            flash('Phases are in a custom state — use Advanced controls to adjust.', 'error')
        else:
            flash('Already at the final phase (public results).', 'error')
        return redirect_to

    # Server-side enforcement of the readiness checklist (the UI disables the button
    # until all are ticked; a stale page or direct POST must not bypass it).
    for p in ctx['preconditions']:
        if request.form.get(p['id']) != 'on':
            flash('Confirm every readiness check before moving on.', 'error')
            return redirect_to
        if p.get('met') is False:                 # machine-checkable and currently unmet
            flash('A readiness condition is not met yet — fix it before moving on.', 'error')
            return redirect_to

    # Run the Phase 6 Polis I/O FIRST, before mutating conv. This keeps the network
    # round-trips out of the open write transaction: the only DB write happens at the
    # commit below, so a slow Polis backend never holds a row lock on the conversation.
    # First entry → initialise the round. Re-entry (the featured set may have changed
    # in between) → re-sync round 6 to the current featured set, preserving votes (#175).
    created_p6 = None
    sync_msg = None
    if ctx['runs_phase6_init']:
        if not conv.phase6_polis_conversation_id:
            ok, msg = _init_phase6(conv)          # assigns ids onto conv/featured; no commit
            if not ok:
                db.session.rollback()
                flash(msg, 'error')
                return redirect_to
            created_p6 = conv.phase6_polis_conversation_id
        else:
            ok, sync_msg = _sync_phase6_featured(conv)
            if not ok:
                db.session.rollback()
                flash(sync_msg, 'error')
                return redirect_to

    source_key, target_key = _apply_phase_transition(conv, ctx)

    slug = conv.slug                              # capture before any rollback expires it
    try:
        db.session.commit()                       # flag flip (+ phase6 ids / close) atomic
    except IntegrityError:
        db.session.rollback()
        # A concurrent transition won the UNIQUE race. The winner committed cleanly, so
        # reload-and-retry resolves it. If we created a Phase 6 Polis conversation in this
        # request it is now orphaned — log it for manual cleanup.
        if created_p6:
            current_app.logger.error(
                'Phase advance lost a concurrent race after Phase 6 init — '
                'orphaned Polis conversation %s (conv %s)', created_p6, slug)
        flash('Could not move on — the conversation changed at the same time. '
              'Reload and try again.', 'error')
        return redirect_to
    except SQLAlchemyError:
        # Any other DB failure (deadlock, timeout, lost connection). Scoped to
        # SQLAlchemyError so genuine programming errors still surface. If Phase 6 init
        # already created a remote conversation it is orphaned — a blind retry would
        # create a SECOND one, so warn the organizer rather than inviting a re-submit.
        db.session.rollback()
        if created_p6:
            current_app.logger.error(
                'Phase advance commit failed after Phase 6 init — '
                'orphaned Polis conversation %s (conv %s)', created_p6, slug)
            flash('Could not complete the move — a database error occurred, and a '
                  'linked Polis conversation may already have been created. Do not '
                  'simply retry; check with a site admin first.', 'error')
        else:
            flash('Could not move on — a database error occurred. Please try again.', 'error')
        return redirect_to

    record_audit('phase.advance', conv_id=conv.id, target_type='phase', target_id=target_key,
                 from_phase=source_key, phase6_created=bool(created_p6))

    if not _sync_vis_type(conv):
        flash('Phase moved, but updating results visibility in Polis failed.', 'error')
    if sync_msg:                                  # re-entry re-synced round 6 (#175)
        flash(sync_msg, 'warning' if 'check manually' in sync_msg else 'success')
    flash(f'Moved to: {ctx["target"]["label"]}.', 'success')
    return redirect_to


@admin_bp.post('/admin/conversations/<int:conv_id>/phase6/init')
@login_required
def admin_phase6_init(conv_id):
    """Initialise Phase 6: create a dedicated Polis conversation, seed all confirmed
    featured statements into it, and store the resulting IDs atomically.

    All-or-nothing: phase6_polis_conversation_id is only committed once every seed
    succeeds. If any seed fails the Polis conversation is abandoned (logged for manual
    cleanup) and the admin can retry from scratch.

    The DB-level UNIQUE constraint on phase6_polis_conversation_id converts a
    concurrent double-submit into a loud IntegrityError rather than a silent overwrite.
    """
    # Allows conversation moderators (not just global admins) to initialise Phase 6.
    conv = _require_mod_for_conv(conv_id)

    if not conv.active or conv.paused:
        flash('Cannot initialise Phase 6 on a closed or paused conversation.', 'error')
        return redirect(url_for('admin.admin_conversation_detail', conv_id=conv_id))

    if not conv.phase_informed_voting:
        flash('Enable the Informed voting toggle first, then initialise.', 'error')
        return redirect(url_for('admin.admin_conversation_detail', conv_id=conv_id))

    if conv.phase6_polis_conversation_id:
        flash('Phase 6 already initialised.', 'error')
        return redirect(url_for('admin.admin_conversation_detail', conv_id=conv_id))

    ok, msg = _init_phase6(conv)
    if not ok:
        flash(msg, 'error')
        return redirect(url_for('admin.admin_conversation_detail', conv_id=conv_id))
    orphan_id = conv.phase6_polis_conversation_id  # capture before any rollback expires it
    slug = conv.slug
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash('Phase 6 was already initialised by a concurrent request.', 'error')
        return redirect(url_for('admin.admin_conversation_detail', conv_id=conv_id))
    except SQLAlchemyError:
        db.session.rollback()
        # Logged unconditionally (unlike the guided route's `if created_p6:`
        # guard): this route early-returns when an id already exists and has no
        # re-sync path, so reaching the commit means _init_phase6 just created a
        # fresh Polis conversation, now orphaned by the rollback.
        current_app.logger.error(
            'Phase 6 standalone init: DB error after Polis I/O — '
            'orphaned Polis conversation %s (conv %s)', orphan_id, slug)
        flash('Phase 6 initialisation failed due to a database error. '
              'Contact a site admin — the Polis conversation id has been logged.', 'error')
        return redirect(url_for('admin.admin_conversation_detail', conv_id=conv_id))
    record_audit('phase6.init', conv_id=conv.id)
    flash(msg, 'success')
    return redirect(url_for('admin.admin_conversation_detail', conv_id=conv_id))


def _init_phase6(conv) -> tuple[bool, str]:
    """Create the Phase 6 Polis conversation and seed all confirmed featured statements,
    assigning the resulting ids onto the conversation and featured rows.

    Does NOT commit — the caller commits so a flag flip plus this init are one
    transaction. All-or-nothing: on any Polis failure no model fields are changed and
    the orphaned remote conversation id is logged for manual cleanup. Returns
    (ok, message).
    """
    statements = (FeaturedStatement.query
                  .filter_by(conversation_id=conv.id, confirmed_by_admin=True)
                  .all())
    if not statements:
        return False, 'No confirmed featured statements — confirm at least one before initialising Phase 6.'

    client = _polis_server_client()
    try:
        p6_conv_id = client.create_conversation(
            f'{conv.title} — Informed Voting', strict_moderation=True)
    except PolisServerError as exc:
        current_app.logger.error('Phase 6 conversation creation failed: %s', exc)
        return False, f'Could not create Phase 6 Polis conversation: {exc}'

    seeded: list[tuple[FeaturedStatement, int]] = []
    for fs in statements:
        text = fs.statement_text or ''
        if not text:
            current_app.logger.error(
                'Phase 6 init: fs %s has no cached text — abandoning Polis conversation %s',
                fs.id, p6_conv_id)
            return False, (f'Phase 6 init failed: statement {fs.id} has no cached text. '
                           'The orphaned Polis conversation id has been logged.')
        try:
            seeded.append((fs, client.add_seed_return_id(p6_conv_id, text)))
        except PolisServerError as exc:
            current_app.logger.error(
                'Phase 6 init: seed failed for fs %s: %s; abandoning Polis conversation %s',
                fs.id, exc, p6_conv_id)
            return False, (f'Phase 6 init failed while seeding statement {fs.id}. '
                           'The orphaned Polis conversation id has been logged.')

    for fs, tid in seeded:
        fs.phase6_polis_statement_id = tid
    conv.phase6_polis_conversation_id = p6_conv_id
    return True, f'Phase 6 initialised — {len(seeded)} statement(s) seeded.'


def _norm(text) -> str:
    """Case/space-insensitive key for matching statement text across systems."""
    return (text or '').strip().casefold()


def _resync_phase6_if_live(conv) -> bool:
    """Keep an already-running Informed Vote round in sync with the featured set:
    call after staging (not committing) a confirm/add/remove of a FeaturedStatement.
    On failure this rolls back the staged change and flashes the error, so a broken
    Polis sync never leaves a featured-set edit half-applied. Returns whether the
    caller should proceed to commit."""
    if not (conv.phase_informed_voting and conv.phase6_polis_conversation_id):
        return True
    ok, msg = _sync_phase6_featured(conv)
    if not ok:
        db.session.rollback()
        flash(msg, 'error')
    return ok


def _sync_phase6_featured(conv) -> tuple[bool, str]:
    """Reconcile an ALREADY-initialised Phase 6 round with the CURRENT confirmed
    featured set, preserving votes (#175). Statements are matched by text:

    - featured but missing from round 6        → add_seed_return_id (new)
    - featured but hidden in round 6           → moderate(+1) to restore
    - featured and live                        → adopt its tid
    - live in round 6 but no longer featured   → moderate(-1) to hide (votes kept)

    Does NOT commit — the caller commits so the reconciliation and the flag flip are
    one transaction. On any Polis failure returns (False, msg) so the caller rolls back
    the DB; note that remote moderation calls already applied are non-transactional and
    persist — re-running the sync is idempotent and reconciles them.

    Hiding requires reading round 6's actual moderation state from the Polis stats DB:
    - stats DB read succeeds → full reconcile (add / restore / adopt / hide);
    - stats DB not configured → add-side only (seed unmapped featured statements) and
      warn that removed statements could not be hidden;
    - stats DB configured but the read FAILS → return failure (caller rolls back) rather
      than risk double-seeding a live statement we momentarily couldn't see.
    """
    round6 = conv.phase6_polis_conversation_id
    client = _polis_server_client()
    featured = (FeaturedStatement.query
                .filter_by(conversation_id=conv.id, confirmed_by_admin=True).all())
    featured_by_text = {_norm(fs.statement_text): fs
                        for fs in featured if _norm(fs.statement_text)}
    n_texts = sum(1 for fs in featured if _norm(fs.statement_text))
    if len(featured_by_text) < n_texts:                # last-write-wins collapsed duplicates
        current_app.logger.warning(
            'Round 6 re-sync: %d featured statements collapsed to %d distinct texts '
            '(duplicates) for conv %s — some may be skipped.', n_texts,
            len(featured_by_text), conv.slug)

    rows = client.get_statements(round6)   # None if stats DB unconfigured OR the read failed

    added = restored = removed = 0
    try:
        if rows is not None:
            pending, approved, hidden = rows
            live_tid   = {_norm(s['txt']): s['tid'] for s in approved + pending}
            hidden_tid = {_norm(s['txt']): s['tid'] for s in hidden}

            for key, fs in featured_by_text.items():
                if key in live_tid:
                    fs.phase6_polis_statement_id = live_tid[key]          # already live
                elif key in hidden_tid:
                    client.moderate(round6, hidden_tid[key], 1)           # restore
                    fs.phase6_polis_statement_id = hidden_tid[key]
                    restored += 1
                else:
                    # New statement. Owner-authored seeds are auto-approved even under
                    # strict_moderation (same path as _init_phase6), so it's visible.
                    fs.phase6_polis_statement_id = client.add_seed_return_id(
                        round6, fs.statement_text)
                    added += 1

            for key, tid in live_tid.items():                            # de-featured → hide
                if key not in featured_by_text:
                    client.moderate(round6, tid, -1)
                    removed += 1

            return True, (f'Round 6 re-synced to the current featured set — '
                          f'{added} added, {restored} restored, {removed} hidden.')

        if not client._db_url:
            # Stats DB genuinely not configured — add side only (cannot read round 6 to
            # hide removed statements). Only seed featured statements with no local
            # mapping (i.e. genuinely new ones); warn about the limitation.
            for fs in featured:
                if fs.phase6_polis_statement_id is None and _norm(fs.statement_text):
                    fs.phase6_polis_statement_id = client.add_seed_return_id(
                        round6, fs.statement_text)
                    added += 1
            return True, (f'Round 6: added {added} new statement(s). The stats DB is not '
                          'configured, so de-featured statements could not be hidden — '
                          'check manually.')

        # Stats DB IS configured but the read failed — do not guess (seeding here could
        # double-seed a live statement we couldn't see). Fail so the caller rolls back.
        current_app.logger.error('Round 6 re-sync: stats DB read failed for %s', round6)
        return False, ('Could not read round 6 from the stats DB to re-sync — nothing was '
                       'changed; reload and try again.')
    except PolisServerError as exc:
        current_app.logger.error('Round 6 re-sync failed: %s', exc)
        return False, f'Could not re-sync round 6 with the featured set: {exc}'


@admin_bp.post('/admin/global-admins/add')
@login_required
@admin_required
def admin_global_admin_add():
    mw_username = (request.form.get('mw_username') or '').strip()
    if not mw_username:
        flash('Enter a Wikimedia username.', 'error')
        return redirect(url_for('admin.admin'))
    p = Participant.query.filter_by(mw_username=mw_username).first()
    if not p:
        flash(f'No account found for "{mw_username}". They must log in at least once first.', 'error')
        return redirect(url_for('admin.admin'))
    p.is_global_admin = True
    db.session.commit()
    record_audit('global_admin.grant', target_type='participant', target_id=p.id)
    return redirect(url_for('admin.admin'))

@admin_bp.post('/admin/global-admins/<int:participant_id>/remove')
@login_required
@admin_required
def admin_global_admin_remove(participant_id):
    p = Participant.query.get_or_404(participant_id)
    p.is_global_admin = False
    db.session.commit()
    record_audit('global_admin.revoke', target_type='participant', target_id=p.id)
    return redirect(url_for('admin.admin'))

@admin_bp.post('/admin/roles/add')
@login_required
@admin_required
def admin_role_add():
    participant_id  = request.form.get('participant_id', type=int)
    conversation_id = request.form.get('conversation_id', type=int)
    role            = request.form.get('role', '').strip()

    if role not in ADMIN_ROLES or not conversation_id:
        abort(400)
    Participant.query.get_or_404(participant_id)
    Conversation.query.get_or_404(conversation_id)

    existing = AdminRole.query.filter_by(
        participant_id=participant_id,
        conversation_id=conversation_id,
        role=role,
    ).first()
    if not existing:
        grantor = _current_participant()
        db.session.add(AdminRole(
            participant_id=participant_id,
            conversation_id=conversation_id,
            role=role,
            granted_by=grantor.id if grantor else None,
        ))
        db.session.commit()
        record_audit('role.grant', conv_id=conversation_id, target_type='participant',
                     target_id=participant_id, role=role)
    return redirect(_safe_redirect(request.form.get('redirect_to', ''), url_for('admin.admin')))

@admin_bp.post('/admin/roles/<int:role_id>/remove')
@login_required
@admin_required
def admin_role_remove(role_id):
    role = AdminRole.query.get_or_404(role_id)
    conv_id, pid, role_name = role.conversation_id, role.participant_id, role.role
    db.session.delete(role)
    db.session.commit()
    record_audit('role.revoke', conv_id=conv_id, target_type='participant',
                 target_id=pid, role=role_name)
    return redirect(_safe_redirect(request.form.get('redirect_to', ''), url_for('admin.admin')))

@admin_bp.get('/admin/conversations/<int:conv_id>/invites')
@login_required
def admin_conversation_invites(conv_id):
    conv    = _require_mod_for_conv(conv_id)
    invites = (ConversationInvite.query
               .filter_by(conversation_id=conv_id)
               .order_by(ConversationInvite.mw_username)
               .all())
    return render_template('admin_invites.html',
                           conversation=conv, invites=invites)

@admin_bp.post('/admin/conversations/<int:conv_id>/invites/add')
@login_required
def admin_invite_add(conv_id):
    _require_mod_for_conv(conv_id)
    raw = [line.strip() for line in
           request.form.get('mw_usernames', '').splitlines() if line.strip()]
    usernames = [u for u in raw if 1 <= len(u) <= 255]
    if not usernames:
        return redirect(url_for('admin.admin_conversation_invites', conv_id=conv_id))
    try:
        result = add_conversation_invites(
            db.session,
            conversation_id=conv_id,
            usernames=usernames,
        )
    except InviteBatchSaveError:
        current_app.logger.exception('invite batch save failed for conversation %s', conv_id)
        flash("Couldn't save invites — please review the list and retry.", 'error')
        return redirect(url_for('admin.admin_conversation_invites', conv_id=conv_id))

    if result.added:
        record_audit('invite.add', conv_id=conv_id,
                     count=result.added)  # counts only — no usernames (PII)

    summary = [f'{result.added} added']
    if result.already_present:
        summary.append(f'{result.already_present} already present')
    if result.duplicate_inputs:
        summary.append(f'{result.duplicate_inputs} duplicate input')
    if result.concurrent_conflicts:
        summary.append(f'{result.concurrent_conflicts} added concurrently by another moderator')
    flash('Invites: ' + '; '.join(summary) + '.',
          'info' if result.concurrent_conflicts else 'success')
    return redirect(url_for('admin.admin_conversation_invites', conv_id=conv_id))

@admin_bp.post('/admin/conversations/<int:conv_id>/invites/<int:invite_id>/remove')
@login_required
def admin_invite_remove(conv_id, invite_id):
    _require_mod_for_conv(conv_id)
    invite = ConversationInvite.query.filter_by(
        id=invite_id, conversation_id=conv_id).first_or_404()
    db.session.delete(invite)
    db.session.commit()
    record_audit('invite.remove', conv_id=conv_id, target_type='invite', target_id=invite_id)
    return redirect(url_for('admin.admin_conversation_invites', conv_id=conv_id))

# ── Admin: Polis statement moderation ─────────────────────────────────────

@admin_bp.get('/admin/conversations/<int:conv_id>/statements')
@login_required
def admin_conversation_statements(conv_id):
    conv     = _require_mod_for_conv(conv_id)
    pending = approved = hidden = []
    settings = {}
    # Prefer Postgres for accurate mod state; fall back to Particiapi when unavailable.
    result = _polis_server_client().get_statements(conv.polis_id)
    if result is not None:
        pending, approved, hidden = result
    else:
        try:
            pending, approved, hidden = PolisParticipantClient(
                current_app.config['PARTICIAPI_BASE']
            ).get_statements(conv.polis_id)
        except PolisParticipantError:
            current_app.logger.exception('get_statements failed')
            flash('Could not load statements. Check server logs.', 'error')
    try:
        settings = PolisParticipantClient(
            current_app.config['PARTICIAPI_BASE']
        ).get_settings(conv.polis_id)
    except PolisParticipantError:
        pass
    featured_tids = {
        fs.polis_statement_id
        for fs in FeaturedStatement.query.filter_by(conversation_id=conv_id).all()
    }
    # Provenance (#143): which listed statements are recorded derivatives → {tid: row}.
    all_tids = [s['tid'] for s in (list(pending) + list(approved) + list(hidden))]
    provenance_map = _provenance_map(conv_id, all_tids)
    seed_lock_reason = _seed_statement_lock_reason(conv)
    return render_template('admin_statements.html',
                           conversation=conv,
                           pending=pending,
                           approved=approved,
                           hidden=hidden,
                           settings=settings,
                           featured_tids=featured_tids,
                           provenance_map=provenance_map,
                           phase_active=conv.phase_argument_mapping,
                           seed_import_allowed=seed_lock_reason is None,
                           seed_import_lock_reason=seed_lock_reason,
                           polis_public_url=current_app.config.get('POLIS_PUBLIC_URL') or 'https://pol.is',
                           max_import_rows=MAX_ROWS,
                           max_import_chars=MAX_TEXT_CHARS)

@admin_bp.post('/admin/conversations/<int:conv_id>/statements/<int:tid>/moderate')
@login_required
def admin_statement_moderate(conv_id, tid):
    conv = _require_mod_for_conv(conv_id)
    mod  = request.form.get('mod', type=int)
    if mod not in (-1, 0, 1):
        abort(400)
    if mod in (-1, 0):
        is_featured = FeaturedStatement.query.filter_by(
            conversation_id=conv_id, polis_statement_id=tid).first() is not None
        if is_featured and conv.phase_argument_mapping:
            # Best-effort check: the mutation here is a Polis API call, not a
            # DB write, so FOR UPDATE would be released before the call anyway.
            # The strong DB-level invariant is enforced by admin_featured_remove,
            # which does lock correctly before db.session.commit().
            featured_count = FeaturedStatement.query.filter_by(
                conversation_id=conv_id).count()
            if featured_count <= 1:
                flash(
                    'Cannot hide or move the last featured statement to pending while argument mapping is active. Disable the argument mapping phase first.',
                    'error'
                )
                return redirect(url_for('admin.admin_conversation_statements', conv_id=conv_id))
    try:
        _polis_server_client().moderate(conv.polis_id, tid, mod)
    except PolisServerError:
        current_app.logger.exception('moderate failed')
        flash('Moderation action failed. Check server logs for details.', 'error')
        return redirect(url_for('admin.admin_conversation_statements', conv_id=conv_id))
    record_audit('statement.moderate', conv_id=conv_id, target_type='statement',
                 target_id=tid, decision=mod)
    return redirect(url_for('admin.admin_conversation_statements', conv_id=conv_id))

@admin_bp.post('/admin/conversations/<int:conv_id>/statements/seed')
@login_required
def admin_statement_seed(conv_id):
    conv = _require_mod_for_conv(conv_id)
    lock_reason = _seed_statement_lock_reason(conv)
    if lock_reason:
        flash(lock_reason, 'error')
        return redirect(url_for('admin.admin_conversation_statements', conv_id=conv_id))
    text = request.form.get('txt', '').strip()
    text = nh3.clean(text, tags=frozenset())
    if not text or len(text) > 280:
        abort(400)
    # Optional provenance (#143): the tid this statement corrects/derives from. When set,
    # we need the NEW statement's tid back, so seed via add_seed_return_id and record the link.
    derived_from = request.form.get('derived_from', type=int)
    try:
        if derived_from is not None:
            # Validate the parent is a real statement in THIS conversation before recording a
            # link — a typo'd / cross-conversation tid would otherwise store a bogus link.
            text_map = _statement_text_map(conv.polis_id)
            if derived_from not in text_map:
                flash(f'Statement #{derived_from} was not found in this conversation — '
                      'fix the "corrects" number and try again. Nothing was added.', 'error')
                return redirect(url_for('admin.admin_conversation_statements', conv_id=conv_id))
            new_tid = _polis_server_client().add_seed_return_id(conv.polis_id, text)
            prov = record_statement_provenance(conv_id, new_tid, derived_from,
                                               parent_text=text_map.get(derived_from), new_text=text)
            if prov is None:
                flash('Seed statement added, but the correction link could not be recorded.', 'warning')
            else:
                flash(f'Seed statement added (recorded as a correction of #{derived_from}).', 'success')
            record_audit('statement.seed', conv_id=conv_id, target_type='statement',
                         target_id=new_tid, derived_from=derived_from)
        else:
            _polis_server_client().add_seed(conv.polis_id, text)
            flash('Seed statement added.', 'success')
            record_audit('statement.seed', conv_id=conv_id)   # no text (statement content)
    except PolisServerError as exc:
        current_app.logger.exception('add_seed failed')
        flash(exc.admin_message, 'error')
    return redirect(url_for('admin.admin_conversation_statements', conv_id=conv_id))

@admin_bp.post('/admin/conversations/<int:conv_id>/statements/seed/import-text')
@login_required
@limiter.limit('5 per minute')
def admin_statement_seed_import_text(conv_id):
    conv = _require_mod_for_conv(conv_id)
    redirect_target = url_for('admin.admin_conversation_statements', conv_id=conv_id)
    lock_reason = _seed_statement_lock_reason(conv)
    if lock_reason:
        flash(lock_reason, 'error')
        return redirect(redirect_target)
    raw_text = request.form.get('statement_texts', '')
    # Pre-parse size guard, mirroring the CSV path's MAX_FILE_BYTES cap (#238).
    # The textarea has a client-side maxlength, but that is trivially bypassed by
    # a crafted POST, so bound the raw payload server-side before parsing.
    if len(raw_text.encode('utf-8')) > MAX_FILE_BYTES:
        flash(f'Too much text — maximum is {MAX_FILE_BYTES // 1024} KB.', 'error')
        return redirect(redirect_target)
    result = _parse_seed_text_lines(raw_text)
    if _reject_seed_import_parse_errors(result, 'Text import'):
        return redirect(redirect_target)

    summary = _import_seed_statement_texts(conv, result.texts)
    if summary['successes']:
        record_audit('statement.seed_import_text', conv_id=conv_id,
                     imported=summary['successes'], skipped=summary['skipped'],
                     errors=summary['errors'])
    return redirect(redirect_target)

@admin_bp.post('/admin/conversations/<int:conv_id>/strict-moderation')
@login_required
def admin_conversation_strict_moderation(conv_id):
    conv    = _require_mod_for_conv(conv_id)
    enabled = request.form.get('strict_moderation') == '1'
    try:
        _polis_server_client().set_strict_moderation(conv.polis_id, enabled)
        record_audit('strict_moderation.set', conv_id=conv_id, enabled=enabled)
    except PolisServerError:
        current_app.logger.exception('set_strict_moderation failed')
        flash('Could not update moderation settings. Check server logs for details.', 'error')
    return redirect(url_for('admin.admin_conversation_statements', conv_id=conv_id))

# ── Featured statements ───────────────────────────────────────────────────

@admin_bp.get('/admin/conversations/<int:conv_id>/featured')
@login_required
def admin_conversation_featured(conv_id):
    conv        = _require_mod_for_conv(conv_id)
    confirmed   = (FeaturedStatement.query
                   .filter_by(conversation_id=conv_id)
                   .options(joinedload(FeaturedStatement.arguments))
                   .order_by(FeaturedStatement.created_at).all())
    for fs in confirmed:
        fs.arguments.sort(key=lambda a: a.side if isinstance(a.side, str) else a.side.value or '')
    _backfill_statement_texts(conv, confirmed)
    confirmed_tids = {fs.polis_statement_id for fs in confirmed}
    candidates   = _polis_server_client().get_featured_candidates(conv.polis_id)
    if candidates is not None:
        candidates = [c for c in candidates if c['tid'] not in confirmed_tids]
    candidate_tids = [c['tid'] for c in candidates] if candidates else []
    provenance_map = _provenance_map(conv_id, list(confirmed_tids) + candidate_tids)
    return render_template('admin_featured.html',
                           conversation=conv,
                           confirmed=confirmed,
                           candidates=candidates,
                           provenance_map=provenance_map,
                           phase_active=conv.phase_argument_mapping)

@admin_bp.post('/admin/conversations/<int:conv_id>/featured/confirm')
@login_required
def admin_featured_confirm(conv_id):
    conv = _require_mod_for_conv(conv_id)
    tid  = request.form.get('tid', type=int)
    if tid is None:
        abort(400)
    if not FeaturedStatement.query.filter_by(
            conversation_id=conv_id, polis_statement_id=tid).first():
        db.session.add(FeaturedStatement(
            conversation_id=conv_id,
            polis_statement_id=tid,
            statement_text=_fetch_statement_text(conv.polis_id, tid),
            suggested_by_system=request.form.get('system_suggested') == '1',
            confirmed_by_admin=True,
        ))
        if not _resync_phase6_if_live(conv):
            return redirect(url_for('admin.admin_conversation_featured', conv_id=conv_id))
        db.session.commit()
        record_audit('featured.confirm', conv_id=conv_id, target_type='statement', target_id=tid)
    return redirect(url_for('admin.admin_conversation_featured', conv_id=conv_id))

@admin_bp.post('/admin/conversations/<int:conv_id>/featured/add')
@login_required
def admin_featured_add(conv_id):
    conv = _require_mod_for_conv(conv_id)
    tid  = request.form.get('tid', type=int)
    if tid is None or tid < 0:
        abort(400)
    if not FeaturedStatement.query.filter_by(
            conversation_id=conv_id, polis_statement_id=tid).first():
        db.session.add(FeaturedStatement(
            conversation_id=conv_id,
            polis_statement_id=tid,
            statement_text=_fetch_statement_text(conv.polis_id, tid),
            suggested_by_system=False,
            confirmed_by_admin=True,
        ))
        if not _resync_phase6_if_live(conv):
            return redirect(url_for('admin.admin_conversation_featured', conv_id=conv_id))
        db.session.commit()
        record_audit('featured.add', conv_id=conv_id, target_type='statement', target_id=tid)
    return redirect(url_for('admin.admin_conversation_featured', conv_id=conv_id))

@admin_bp.post('/admin/conversations/<int:conv_id>/featured/<int:fs_id>/remove')
@login_required
def admin_featured_remove(conv_id, fs_id):
    conv = _require_mod_for_conv(conv_id)
    fs = FeaturedStatement.query.filter_by(
        id=fs_id, conversation_id=conv_id).first_or_404()
    if conv.phase_argument_mapping:
        remaining = FeaturedStatement.query.filter_by(conversation_id=conv_id).with_for_update().count()
        if remaining <= 1:
            flash('Cannot remove the last featured statement while argument mapping is active. Disable the argument mapping phase first.', 'error')
            return redirect(url_for('admin.admin_conversation_featured', conv_id=conv_id))
    db.session.delete(fs)
    if not _resync_phase6_if_live(conv):
        return redirect(url_for('admin.admin_conversation_featured', conv_id=conv_id))
    db.session.commit()
    record_audit('featured.remove', conv_id=conv_id, target_type='featured', target_id=fs_id)
    return redirect(url_for('admin.admin_conversation_featured', conv_id=conv_id))

@admin_bp.post('/admin/conversations/<int:conv_id>/arguments/<int:arg_id>/delete')
@login_required
def admin_argument_delete(conv_id, arg_id):
    conv = _require_mod_for_conv(conv_id)
    arg  = Argument.query.filter_by(id=arg_id).first_or_404()
    FeaturedStatement.query.filter_by(
        id=arg.featured_statement_id, conversation_id=conv.id).first_or_404()
    fs_id = arg.featured_statement_id
    db.session.delete(arg)
    db.session.commit()
    record_audit('argument.delete', conv_id=conv_id, target_type='argument', target_id=arg_id,
                 featured_statement_id=fs_id)
    return redirect(url_for('admin.admin_conversation_featured', conv_id=conv_id))

@admin_bp.post('/admin/conversations/<int:conv_id>/arguments/<int:arg_id>/moderate')
@login_required
def admin_argument_moderate(conv_id, arg_id):
    conv = _require_mod_for_conv(conv_id)
    arg  = Argument.query.filter_by(id=arg_id).first_or_404()
    FeaturedStatement.query.filter_by(
        id=arg.featured_statement_id, conversation_id=conv.id).first_or_404()
    hidden = request.form.get('hidden') == '1'
    arg.hidden = hidden
    db.session.commit()
    record_audit('argument.moderate', conv_id=conv_id, target_type='argument',
                 target_id=arg_id, hidden=hidden)
    return redirect(url_for('admin.admin_conversation_featured', conv_id=conv_id))


# ── Accept ───────────────────────────────────────────────────────────────

@participant_bp.get('/accept/<slug>')
@login_required
def accept(slug):
    conv        = Conversation.query.filter_by(slug=slug).first_or_404()
    if conv.access_policy == 'demo':
        return redirect(url_for('participant.conversation', slug=slug))
    participant = _current_participant()
    _check_conversation_access(conv, participant)
    if participant and Participation.query.filter_by(
            participant_id=participant.id,
            conversation_id=conv.id).first():
        return redirect(url_for('participant.conversation', slug=slug))
    pseudonyms = _generate_pseudonyms(5)
    emailable  = session.get('emailable', False)
    return render_template('accept.html', conversation=conv,
                           emailable=emailable, pseudonyms=pseudonyms,
                           reveal_cooldown=_REVEAL_COOLDOWN_DAYS,
                           reveal_window_end=_REVEAL_COOLDOWN_DAYS + _REVEAL_WINDOW_DAYS)

@participant_bp.post('/accept/<slug>')
@login_required
@limiter.limit('10 per minute')
def accept_post(slug):
    conv        = Conversation.query.filter_by(slug=slug).first_or_404()
    if conv.access_policy == 'demo':
        return redirect(url_for('participant.conversation', slug=slug))
    participant = _current_participant()
    if participant is None:
        abort(404)
    _check_conversation_access(conv, participant)

    if Participation.query.filter_by(
            participant_id=participant.id,
            conversation_id=conv.id).first():
        return redirect(url_for('participant.conversation', slug=slug))

    pseudonym = request.form.get('pseudonym', '').strip()
    emailable = session.get('emailable', False)

    if not _PSEUDONYM_RE.match(pseudonym):
        abort(400)

    allowed, eligibility_status, eligibility_detail = _check_join_eligibility(conv, participant)
    if not allowed:
        return make_response(render_template(
            'forbidden_eligibility.html',
            conversation=conv,
            status=eligibility_status,
            detail=eligibility_detail,
        ), 403)

    db.session.add(Participation(
        participant_id=participant.id,
        conversation_id=conv.id,
        pseudonym=pseudonym,
        notify_email=bool(request.form.get('notify_email')) and emailable,
        notify_talk_page=bool(request.form.get('notify_talk_page')),
        eligibility_status=eligibility_status,
        eligibility_checked_at=datetime.now(timezone.utc)
        if eligibility_status != 'not_required' else None,
        eligibility_detail=eligibility_detail or None,
    ))
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        pseudonyms = _generate_pseudonyms(5)
        return render_template('accept.html', conversation=conv,
                               emailable=emailable, pseudonyms=pseudonyms,
                               error='That pseudonym was just taken — please choose another.')
    return redirect(url_for('participant.conversation', slug=slug))

@participant_bp.get('/accept/<slug>/pseudonyms')
@login_required
@limiter.limit('30 per minute')
def accept_pseudonyms(slug):
    Conversation.query.filter_by(slug=slug).first_or_404()
    return jsonify({'pseudonyms': _generate_pseudonyms(5)})

# ── Argument helpers ──────────────────────────────────────────────────────

# ── Conversation ─────────────────────────────────────────────────────────

@participant_bp.get('/c/<slug>')
@limiter.limit('120 per minute')
def conversation(slug):
    conv        = Conversation.query.filter_by(slug=slug).first()
    if conv is None:
        if 'username' not in session and not _is_demo_session():
            session['next'] = request.path
            return redirect(url_for('login'))
        abort(404)
    if conv.access_policy == 'demo':
        participation = _ensure_demo_participation(conv)
        participant = participation.participant
    else:
        if _is_demo_session():
            # Leaving the demo for a real consultation: don't forbid — exit the
            # demo, then follow the normal flow (#293). The space-mismatch banner
            # below carries the "this is live" warning; `space` stays 'demo' so it
            # still fires once we render the real conversation.
            _exit_demo_session()
        if 'username' not in session:
            session['next'] = request.path
            return redirect(url_for('login'))
        participant = _current_participant()
    _check_conversation_access(conv, participant)

    participation = locals().get('participation')
    if participation is None and participant:
        participation = Participation.query.filter_by(
            participant_id=participant.id,
            conversation_id=conv.id,
        ).first()

    if participation is None:
        return redirect(url_for('participant.accept', slug=slug))

    can_mod = _can_moderate(conv, participant)

    # Demo/real space state model (#293): warn once when the viewer lands on a
    # conversation whose space they didn't explicitly choose (e.g. a deep link,
    # or crossing demo->real directly). Admin-access users are exempt — we expect
    # them to know what they're doing. Viewing then adopts the conversation's
    # space, so the warning fires once and normal navigation stays silent.
    conv_space = 'demo' if conv.access_policy == 'demo' else 'real'
    has_admin_access = _is_global_admin(participant) or bool(
        participant and AdminRole.query.filter_by(participant_id=participant.id).first())
    space_warning = conv_space if (
        not has_admin_access and session.get('space') != conv_space) else None
    session['space'] = conv_space

    results     = None
    polis_stats = None
    # Fetch clustering results for either results phase. Personal results (Phase 3,
    # logged-in only) and public results (Phase 4, everyone) currently render the same
    # aggregate data; #81 part 2 will scope personal results to the participant's voted
    # statements (anti-anchoring).
    recomputing = False
    if conv.phase_public_results or conv.phase_personal_results:
        _r = PolisParticipantClient(
            current_app.config['PARTICIAPI_BASE']).get_results(conv.polis_id)
        results = _r if (_r and (_r.get('groups') or _r.get('majority', {}).get('agree') or _r.get('majority', {}).get('disagree'))) else None
        polis_stats = _polis_server_client().get_polis_stats(conv.polis_id)
        if results is None:
            import time
            _now = time.monotonic()
            _last = _math_recompute_last.get(conv.id, 0)
            if _now - _last > _MATH_RECOMPUTE_COOLDOWN:
                if _polis_server_client().queue_math_recompute(conv.polis_id):
                    _math_recompute_last[conv.id] = _now
                    recomputing = True

    # Reveal-window timeline for closed conversations (#70).
    reveal          = _reveal_context(conv, participation)
    reveal_state    = reveal['state'] if reveal else None
    reveal_opens_at = reveal['opens_at'] if reveal else None

    featured_data = []
    if conv.phase_argument_mapping and participation:
        featured_data = _build_featured_data(conv, participation, can_mod=can_mod)

    moderation_log_count = AuditEvent.query.filter(
        AuditEvent.conversation_id == conv.id,
        AuditEvent.operation.in_(('participant.ban', 'participant.unban')),
    ).count()

    # Phase 6 — build card data: each confirmed featured statement with its
    # top-10 visible arguments per side, sorted by usefulness vote count.
    # Eager-load arguments + votes to avoid N+1 queries.
    phase6_data = []
    if conv.phase_informed_voting and conv.phase6_polis_conversation_id and participation:
        p6_stmts = (FeaturedStatement.query
                    .filter_by(conversation_id=conv.id, confirmed_by_admin=True)
                    .options(joinedload(FeaturedStatement.arguments)
                             .joinedload(Argument.votes))
                    .all())

        # Stable per-participant random order — set once on first visit.
        # Same pattern as ArgumentSideState.argument_order.
        fs_by_id = {fs.id: fs for fs in p6_stmts}
        if participation.phase6_card_order is None:
            order = [fs.id for fs in p6_stmts]
            random.shuffle(order)
            participation.phase6_card_order = order
            db.session.commit()
        ordered = [fs_by_id[fid] for fid in participation.phase6_card_order
                   if fid in fs_by_id]
        # Append any confirmed statements added after the order was set
        ordered_ids = set(participation.phase6_card_order)
        ordered += [fs for fs in p6_stmts if fs.id not in ordered_ids]

        for fs in ordered:
            text = fs.statement_text or ''
            if not text:
                continue
            visible_args = [a for a in fs.arguments if not a.hidden]
            pro = sorted(
                [a for a in visible_args if a.side == 'pro'],
                key=lambda a: len(a.votes), reverse=True)[:10]
            con = sorted(
                [a for a in visible_args if a.side == 'con'],
                key=lambda a: len(a.votes), reverse=True)[:10]
            phase6_data.append({
                'fs': fs,
                'text': text,
                'pro': pro,
                'con': con,
                'phase6_stmt_id': fs.phase6_polis_statement_id,
            })

    # Phase 6 results — built when the results tab is visible or Phase 6 is active.
    # Surface A (preliminary) is shown inside the results tab while the round is live.
    phase6_results = None
    if (conv.phase_informed_voting or conv.phase_personal_results or conv.phase_public_results) \
            and conv.phase6_polis_conversation_id:
        phase6_results = _build_phase6_results(conv, participation)

    return render_template('conversation.html',
                           header_mode='conversation',
                           space_warning=space_warning,
                           conversation=conv,
                           participation=participation,
                           can_moderate=can_mod,
                           results=results,
                           recomputing=recomputing,
                           polis_stats=polis_stats,
                           reveal_state=reveal_state,
                           reveal_opens_at=reveal_opens_at,
                           reveal=reveal,
                           demo_mode=conv.access_policy == 'demo',
                           featured_data=featured_data,
                           new_stmt_unlock_at=conv.argument_vote_data.get('new_stmt_unlock_at', 10) if conv.argument_vote_data else 10,
                           new_stmt_max=conv.argument_vote_data.get('new_stmt_max', 3) if conv.argument_vote_data else 3,
                           new_stmt_ids=participation.new_stmt_ids if participation else [],
                           phase6_data=phase6_data,
                           phase6_results=phase6_results,
                           output_items=_output_items(conv),
                           moderation_log_count=moderation_log_count)


@participant_bp.get('/c/<slug>/outputs/<output_key>')
@login_or_demo_required
def conversation_output(slug, output_key):
    conv = Conversation.query.filter_by(slug=slug).first_or_404()
    participant = _current_participant()
    _check_conversation_access(conv, participant)
    participation = Participation.query.filter_by(
        participant_id=participant.id,
        conversation_id=conv.id,
    ).first()
    if participation is None:
        return redirect(url_for('participant.accept', slug=slug))
    definition = _output_definition(output_key)
    if definition is None:
        abort(404)
    items = _output_items(conv)
    output = next(item for item in items if item['key'] == output_key)
    return render_template('output.html',
                           conversation=conv,
                           participation=participation,
                           output=output,
                           output_items=items)


@participant_bp.get('/c/<slug>/moderation-log')
def conversation_moderation_log(slug):
    conv = Conversation.query.filter_by(slug=slug).first_or_404()
    return render_template(
        'moderation_log.html',
        conversation=conv,
        rows=_conversation_ban_log_rows(conv),
    )

# ── Arguments ────────────────────────────────────────────────────────────

@participant_bp.post('/c/<slug>/arguments/<int:fs_id>/submit')
@login_or_demo_required
def argument_submit_legacy(slug, fs_id):
    return redirect(url_for('participant.argument_submit', slug=slug, fs_id=fs_id),
                    code=307)

@participant_bp.post('/c/<slug>/featured-statements/<int:fs_id>/arguments')
@login_or_demo_required
@limiter.limit('20 per minute')
def argument_submit(slug, fs_id):
    conv, part = _require_arg_participation(slug)
    FeaturedStatement.query.filter_by(
        id=fs_id, conversation_id=conv.id).first_or_404()
    side = request.form.get('side', '').strip()
    body = nh3.clean(request.form.get('body', '').strip(), tags=frozenset())
    if side not in ('pro', 'con') or not body or len(body) > 280:
        abort(400)

    existing = Argument.query.filter_by(
        proposer_pseudonym=part.pseudonym,
        featured_statement_id=fs_id,
        side=side,
    ).first()
    if existing:
        if request.headers.get('X-Requested-With') == 'fetch':
            return jsonify({
                'ok': True,
                'id': existing.id,
                'body': existing.body,
                'vote_url': url_for('participant.argument_vote', slug=slug, arg_id=existing.id),
                'unvote_url': url_for('participant.argument_unvote', slug=slug, arg_id=existing.id),
            })
        return redirect(url_for('participant.conversation', slug=slug) + f'#fs-{fs_id}')

    arg = Argument(
        featured_statement_id=fs_id,
        proposer_pseudonym=part.pseudonym,
        body=body,
        side=side,
    )
    db.session.add(arg)
    db.session.flush()   # get arg.id before commit

    # Insert new argument at a random position in this participant's display order.
    # Create ArgumentSideState now if the participant hasn't visited the page yet.
    state = ArgumentSideState.query.filter_by(
        participant_id=part.participant_id,
        featured_statement_id=fs_id,
        side=side,
    ).first()
    if state is None:
        state = ArgumentSideState(
            participant_id=part.participant_id,
            featured_statement_id=fs_id,
            side=side,
            argument_order=[],
        )
        db.session.add(state)
        db.session.flush()
    order = list(state.argument_order)
    order.insert(random.randint(0, len(order)), arg.id)
    state.argument_order = order

    _touch_last_engagement(part)
    db.session.commit()
    if request.headers.get('X-Requested-With') == 'fetch':
        return jsonify({
            'ok': True,
            'id': arg.id,
            'body': body,
            'vote_url': url_for('participant.argument_vote', slug=slug, arg_id=arg.id),
            'unvote_url': url_for('participant.argument_unvote', slug=slug, arg_id=arg.id),
        })
    return redirect(url_for('participant.conversation', slug=slug) + f'#fs-{fs_id}')

@participant_bp.post('/c/<slug>/arguments/<int:fs_id>/<side>/skip')
@login_or_demo_required
def argument_skip_legacy(slug, fs_id, side):
    return redirect(url_for('participant.argument_skip', slug=slug, fs_id=fs_id, side=side),
                    code=307)

@participant_bp.post('/c/<slug>/featured-statements/<int:fs_id>/skip/<side>')
@login_or_demo_required
def argument_skip(slug, fs_id, side):
    conv, part = _require_arg_participation(slug)
    FeaturedStatement.query.filter_by(
        id=fs_id, conversation_id=conv.id).first_or_404()
    if side not in ('pro', 'con'):
        abort(400)

    state = ArgumentSideState.query.filter_by(
        participant_id=part.participant_id,
        featured_statement_id=fs_id,
        side=side,
    ).first()
    if state is None:
        state = ArgumentSideState(
            participant_id=part.participant_id,
            featured_statement_id=fs_id,
            side=side,
            skipped=True,
        )
        db.session.add(state)
        _touch_last_engagement(part)
        db.session.commit()
    elif not state.skipped:
        state.skipped = True
        _touch_last_engagement(part)
        db.session.commit()
    else:
        _touch_last_engagement(part, commit=True)
    if request.headers.get('X-Requested-With') == 'fetch':
        return jsonify({'ok': True})
    return redirect(url_for('participant.conversation', slug=slug) + f'#fs-{fs_id}')

@participant_bp.post('/c/<slug>/arguments/<int:arg_id>/vote')
@login_or_demo_required
def argument_vote(slug, arg_id):
    conv, part = _require_arg_participation(slug)
    arg = Argument.query.filter_by(id=arg_id).first_or_404()
    fs  = FeaturedStatement.query.filter_by(
        id=arg.featured_statement_id, conversation_id=conv.id).first_or_404()

    # Gate: participant must have proposed or skipped both sides.
    pro_state = ArgumentSideState.query.filter_by(
        participant_id=part.participant_id,
        featured_statement_id=fs.id, side='pro').first()
    con_state = ArgumentSideState.query.filter_by(
        participant_id=part.participant_id,
        featured_statement_id=fs.id, side='con').first()
    pro_proposed = Argument.query.filter_by(
        proposer_pseudonym=part.pseudonym,
        featured_statement_id=fs.id, side='pro').first()
    con_proposed = Argument.query.filter_by(
        proposer_pseudonym=part.pseudonym,
        featured_statement_id=fs.id, side='con').first()
    pro_gate = bool(pro_proposed or (pro_state and pro_state.skipped))
    con_gate = bool(con_proposed or (con_state and con_state.skipped))
    is_ajax = request.headers.get('X-Requested-With') == 'fetch'
    if not (pro_gate and con_gate):
        if is_ajax:
            return jsonify({'ok': False, 'reason': 'gate'}), 403
        abort(403)

    # K-approval cap: count existing votes for this side.
    k = int((conv.argument_vote_data or {}).get('K', 2))
    side_arg_ids = [a.id for a in
                    Argument.query.filter_by(
                        featured_statement_id=fs.id, side=arg.side).all()]
    existing_votes = ArgumentVote.query.filter(
        ArgumentVote.participant_id == part.participant_id,
        ArgumentVote.argument_id.in_(side_arg_ids),
    ).count()
    if existing_votes >= k:
        if is_ajax:
            return jsonify({'ok': False, 'reason': 'cap'}), 409
        abort(409)   # cap reached

    # Can't vote on a hidden argument.
    if arg.hidden:
        if is_ajax:
            return jsonify({'ok': False, 'reason': 'hidden'}), 403
        abort(403)
    existing = ArgumentVote.query.filter_by(
        participant_id=part.participant_id, argument_id=arg_id).first()
    if not existing:
        db.session.add(ArgumentVote(
            argument_id=arg_id,
            participant_id=part.participant_id,
        ))
        _touch_last_engagement(part)
        db.session.commit()
    if is_ajax:
        return jsonify({'ok': True})
    return redirect(url_for('participant.conversation', slug=slug) + '#tab-arguments')

@participant_bp.post('/c/<slug>/arguments/<int:arg_id>/unvote')
@login_or_demo_required
def argument_unvote(slug, arg_id):
    conv, part = _require_arg_participation(slug)
    arg = Argument.query.filter_by(id=arg_id).first_or_404()
    FeaturedStatement.query.filter_by(
        id=arg.featured_statement_id, conversation_id=conv.id).first_or_404()
    existing = ArgumentVote.query.filter_by(
        participant_id=part.participant_id, argument_id=arg_id).first()
    if existing:
        db.session.delete(existing)
        _touch_last_engagement(part)
        db.session.commit()
    if request.headers.get('X-Requested-With') == 'fetch':
        return jsonify({'ok': True})
    return redirect(url_for('participant.conversation', slug=slug) + '#tab-arguments')

@participant_bp.post('/c/<slug>/arguments/<int:arg_id>/hide')
@login_required
def argument_hide(slug, arg_id):
    conv = Conversation.query.filter_by(slug=slug).first_or_404()
    if not _can_moderate(conv):
        abort(403)
    arg = Argument.query.filter_by(id=arg_id).first_or_404()
    FeaturedStatement.query.filter_by(
        id=arg.featured_statement_id, conversation_id=conv.id).first_or_404()
    arg.hidden = True
    db.session.commit()
    return redirect(url_for('participant.conversation', slug=slug) + '#tab-arguments')

@participant_bp.post('/c/<slug>/arguments/<int:arg_id>/unhide')
@login_required
def argument_unhide(slug, arg_id):
    conv = Conversation.query.filter_by(slug=slug).first_or_404()
    if not _can_moderate(conv):
        abort(403)
    arg = Argument.query.filter_by(id=arg_id).first_or_404()
    FeaturedStatement.query.filter_by(
        id=arg.featured_statement_id, conversation_id=conv.id).first_or_404()
    arg.hidden = False
    db.session.commit()
    return redirect(url_for('participant.conversation', slug=slug) + '#tab-arguments')


@participant_bp.post('/c/<slug>/arguments/<int:arg_id>/flag')
@login_or_demo_required
@limiter.limit('10 per minute')
def argument_flag(slug, arg_id):
    conv, part = _require_arg_participation(slug)
    arg = Argument.query.filter_by(id=arg_id).first_or_404()
    FeaturedStatement.query.filter_by(
        id=arg.featured_statement_id, conversation_id=conv.id).first_or_404()
    if arg.hidden:
        if request.headers.get('X-Requested-With') == 'fetch':
            return jsonify({'ok': True, 'already_reviewed': True})
        flash('This argument is already under moderator review.', 'info')
        return redirect(url_for('participant.conversation', slug=slug) + '#tab-arguments')
    category, detail = _parse_content_flag_form()
    if not _existing_open_flag(
        conv.id,
        part.participant_id,
        'argument',
        category,
        argument_id=arg.id,
    ):
        db.session.add(ContentFlag(
            conversation_id=conv.id,
            participant_id=part.participant_id,
            content_type='argument',
            argument_id=arg.id,
            category=category,
            detail=detail,
            status='open',
        ))
        db.session.commit()
        record_audit('content_flag.create', conv_id=conv.id, target_type='argument',
                     target_id=arg.id, category=category)
    if request.headers.get('X-Requested-With') == 'fetch':
        return jsonify({'ok': True})
    flash('Thanks - this has been sent to the moderator for review.', 'success')
    return redirect(url_for('participant.conversation', slug=slug) + '#tab-arguments')


@participant_bp.post('/c/<slug>/statements/<int:tid>/flag')
@login_or_demo_required
@limiter.limit('10 per minute')
def statement_flag(slug, tid):
    conv = Conversation.query.filter_by(slug=slug).first_or_404()
    if not conv.active or conv.paused:
        abort(403)
    participant = _current_participant()
    if participant is None:
        abort(403)
    part = Participation.query.filter_by(
        participant_id=participant.id,
        conversation_id=conv.id,
    ).first_or_404()
    _abort_if_banned(conv, participant)

    statements = _polis_server_client().get_statements(conv.polis_id)
    if statements is not None:
        all_statements = [s for group in statements for s in group]
        matching = [s for s in all_statements if s.get('tid') == tid]
        if not matching:
            abort(404)
        # Seed statements (organizer-authored) are just as flaggable as any other —
        # a moderator's own wording can still need review. Previously excluded here
        # with no test coverage and no documented rationale; caused every flag on a
        # featured (often seed-derived) statement to 400.

    category, detail = _parse_content_flag_form()
    if not _existing_open_flag(
        conv.id,
        part.participant_id,
        'statement',
        category,
        statement_tid=tid,
    ):
        db.session.add(ContentFlag(
            conversation_id=conv.id,
            participant_id=part.participant_id,
            content_type='statement',
            statement_tid=tid,
            category=category,
            detail=detail,
            status='open',
        ))
        db.session.commit()
        record_audit('content_flag.create', conv_id=conv.id, target_type='statement',
                     target_id=tid, category=category)
    if request.headers.get('X-Requested-With') == 'fetch':
        return jsonify({'ok': True})
    flash('Thanks - this has been sent to the moderator for review.', 'success')
    return redirect(url_for('participant.conversation', slug=slug) + '#tab-vote')

# ── Identity reveal ───────────────────────────────────────────────────────

@participant_bp.get('/c/<slug>/reveal')
@login_required
def reveal_identity(slug):
    conv        = Conversation.query.filter_by(slug=slug).first_or_404()
    participant = _current_participant()
    if participant is None:
        abort(404)
    participation = Participation.query.filter_by(
        participant_id=participant.id,
        conversation_id=conv.id,
    ).first_or_404()
    if not conv.closed_at:
        abort(404)

    # Single source of truth: the displayed timeline and these gate flags both come
    # from _reveal_context, so the page can never show "open" while the POST rejects.
    reveal = _reveal_context(conv, participation)
    return render_template('reveal.html',
                           conversation=conv,
                           participation=participation,
                           window_open=reveal['state'] in ('open', 'revealed'),
                           window_closed=reveal['state'] == 'expired',
                           opens_at=reveal['opens_at'],
                           reveal=reveal)

@participant_bp.post('/c/<slug>/reveal')
@login_required
@limiter.limit('5 per minute')
def reveal_identity_post(slug):
    conv        = Conversation.query.filter_by(slug=slug).first_or_404()
    participant = _current_participant()
    if participant is None:
        abort(404)
    participation = Participation.query.filter_by(
        participant_id=participant.id,
        conversation_id=conv.id,
    ).first_or_404()

    if not conv.closed_at:
        abort(400)

    # Same source of truth as the GET page / timeline — the window is open iff
    # _reveal_context says so. (Already-revealed → state 'revealed', also rejected.)
    if _reveal_context(conv, participation)['state'] != 'open':
        abort(400)
    if participation.public_username is not None:
        abort(400)
    if request.form.get('confirm') != '1':
        return redirect(url_for('participant.reveal_identity', slug=slug))

    participation.public_username = participant.mw_username
    participation.revealed_at     = datetime.now(timezone.utc)
    db.session.commit()
    return redirect(url_for('participant.conversation', slug=slug))


# ── Phase 6 vote ──────────────────────────────────────────────────────────────

@participant_bp.post('/c/<slug>/phase6/vote')
@limiter.limit('30 per minute')
def phase6_vote(slug):
    """Submit a Phase 6 (informed voting) vote for a featured statement.

    The client sends {fs_id, vote} — never pid/tid. The server resolves the Polis
    conversation ID and statement ID from the DB, verifies the participant is a member
    of this conversation, and forwards the vote to Particiapi via the same cookie-rename
    proxy pattern used by proxy_particiapi.

    This route is on participant_bp (CSRF-enabled) so Flask-WTF validates X-CSRFToken.
    """
    conv = Conversation.query.filter_by(slug=slug).first_or_404()

    # Only accept votes on active, unpaused consultations.
    if not conv.active or conv.paused:
        abort(403)

    if _is_demo_session():
        if _demo_bound_conversation_id() != conv.id or conv.access_policy != 'demo':
            abort(403)
    elif 'username' not in session:
        abort(403)

    participant = _current_participant()
    if participant is None:
        abort(403)

    # Membership check — participant must have joined this conversation.
    participation = Participation.query.filter_by(
        participant_id=participant.id,
        conversation_id=conv.id,
    ).first()
    if not participation:
        abort(403)
    _abort_if_banned(conv, participant)

    if not conv.phase_informed_voting or not conv.phase6_polis_conversation_id:
        abort(404)

    data = request.get_json(silent=True) or {}
    fs_id = data.get('fs_id')
    vote  = data.get('vote')
    # Validate types explicitly — non-integer fs_id causes an unhandled 500 in the DB query.
    # isinstance check on vote prevents False/True (Python bool subclasses int, False==0).
    if not isinstance(fs_id, int) or isinstance(vote, bool) or vote not in (1, -1, 0):
        abort(400)

    fs = FeaturedStatement.query.filter_by(
        id=fs_id, conversation_id=conv.id, confirmed_by_admin=True,
    ).first_or_404()
    if fs.phase6_polis_statement_id is None:
        abort(404)

    # Resolve conversation/statement IDs server-side — never trust the client.
    polis_conv_id = conv.phase6_polis_conversation_id
    tid           = fs.phase6_polis_statement_id

    base = current_app.config['PARTICIAPI_BASE']

    # Manage the Phase 6 Particiapi session entirely server-side, in the Flask
    # session, and reuse its CSRF token across votes — instead of bootstrapping a
    # fresh session (two upstream calls) on every vote. Kept out of the browser's
    # `pa_session` cookie so it never collides with the Phase 2 web component's
    # session. We re-bootstrap only when it is missing or a vote is rejected as a
    # session/CSRF failure (stale token).
    p6_key = (session.get('xid'), conv.id)

    def _bootstrap():
        """(Re)establish the Phase 6 Particiapi session + CSRF token, storing both in
        the Flask session and the process-local share cache. Returns (pa, csrf_token);
        aborts 502 on failure."""
        prior = session.get('_p6_pa')
        try:
            r = polis_http.post(
                f'{base}/api/session',
                cookies={'session': prior} if prior else {},
                params={'create': 'true'},
                timeout=5,
            )
        except requests.RequestException:
            current_app.logger.exception('Particiapi session bootstrap failed in phase6_vote')
            abort(502)
        if not r.ok:
            current_app.logger.error('Particiapi session error in phase6_vote: %s', r.status_code)
            abort(502)
        session['_p6_pa']   = r.cookies.get('session') or prior
        session['_p6_csrf'] = r.json().get('csrf_token', '')
        _p6_session_cache[p6_key] = (session['_p6_pa'], session['_p6_csrf'])
        return session['_p6_pa'], session['_p6_csrf']

    pa = session.get('_p6_pa')
    csrf_token = session.get('_p6_csrf')
    bootstrapped = False
    if not (pa and csrf_token):
        # Serialize the first bootstrap per (participant, conversation) within this
        # worker so concurrent first votes reuse one Polis session instead of minting
        # two uids (#275). See the _p6_session_cache note above.
        with _p6_bootstrap_lock(p6_key):
            shared = _p6_session_cache.get(p6_key)
            if shared:
                session['_p6_pa'], session['_p6_csrf'] = shared
                pa, csrf_token = shared
            else:
                pa, csrf_token = _bootstrap()
                bootstrapped = True

    def _put(cookie_val, token):
        try:
            return polis_http.put(
                f'{base}/api/conversations/{polis_conv_id}/votes/{tid}',
                json={'value': vote},
                cookies={'session': cookie_val} if cookie_val else {},
                headers={'X-CSRF-Token': token},
                timeout=10,
            )
        except requests.RequestException:
            current_app.logger.exception('Particiapi error in phase6_vote')
            abort(502)

    upstream = _put(pa, csrf_token)
    # A reused token can be stale (the session expired). If a vote we did NOT just
    # bootstrap for is rejected, refresh the session once and retry.
    if upstream.status_code in (401, 403) and not bootstrapped:
        pa, csrf_token = _bootstrap()
        upstream = _put(pa, csrf_token)

    resp = make_response('', upstream.status_code)
    if upstream.ok:
        _touch_last_engagement(participation, commit=True)
    return resp


# Accepted shape for a reused inbound X-Request-Id (only honoured behind a trusted proxy).
_REQUEST_ID_RE = re.compile(r'^[A-Za-z0-9_-]{1,64}$')


def record_audit(operation, *, conv_id=None, target_type=None, target_id=None,
                 outcome='ok', **detail):
    """Append an AuditEvent (#135) and emit a correlated structured log line.

    Table-primary, log-as-backstop: the row is the system of record; the log line is the
    redundant correlated copy (carries request_id + participant_id via the Phase-1 factory),
    so the event survives even if the row write fails.

    Call AFTER the audited action has committed — so a rolled-back action leaves no audit row.

    PRIVACY CONTRACT: `detail` and target_* may contain ONLY ids / enums / counts — never
    statement text, vote values, usernames, xid, or any PII. The row is not redaction-filtered;
    this contract is the control (enforced by tests).
    """
    actor = getattr(g.get('participant'), 'id', None)
    if actor is None and has_request_context() and session.get('username'):
        # Authenticated admin with no Participant row (env-listed ADMIN_USERS superadmin).
        # Mark the row so a NULL actor is explained, not ambiguous — without storing the
        # username (PII). See _is_global_admin's ADMIN_USERS branch.
        detail.setdefault('actor_kind', 'env_admin')
    try:
        db.session.add(AuditEvent(
            actor_participant_id=actor, conversation_id=conv_id, operation=operation,
            target_type=target_type,
            target_id=(str(target_id) if target_id is not None else None),
            outcome=outcome, detail=detail))
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception('audit write failed: %s', operation)
    current_app.logger.info(
        'audit %s', operation,
        extra={'audit': True, 'operation': operation, 'conversation_id': conv_id,
               'target_type': target_type, 'target_id': target_id, 'outcome': outcome})


def _char_similarity(new_text, parent_text):
    """Cheap, always-available character-level similarity (stdlib difflib; no dependency,
    language-agnostic). 1.0 = identical, 0.0 = no overlap."""
    import difflib
    return round(difflib.SequenceMatcher(None, parent_text or '', new_text or '').ratio(), 4)


def _semantic_similarity(new_text, parent_text):
    """Semantic scorer (#207) backed by the optional embedding sidecar (#208).

    Contract (matches the embedding sidecar #208): POST STATEMENT_SIMILARITY_URL with
    {"left": parent_text, "right": new_text}; response {"similarity": float}.
    The call is best-effort and short-timeout; absent config or sidecar failure returns
    None so the always-available char score remains the fallback.
    """
    url = current_app.config.get('STATEMENT_SIMILARITY_URL', '').strip()
    if not url:
        return None
    timeout = float(current_app.config.get('STATEMENT_SIMILARITY_TIMEOUT', 1.5))
    try:
        resp = requests.post(
            url,
            json={'left': parent_text or '', 'right': new_text or ''},
            headers={'User-Agent': _MW_USER_AGENT},
            timeout=timeout,
        )
        resp.raise_for_status()
        payload = resp.json()
        raw = payload.get('similarity', payload.get('score'))
        value = float(raw)
    except Exception:
        current_app.logger.exception('semantic similarity sidecar failed')
        return None
    return round(max(0.0, min(1.0, value)), 4)


# Similarity-at-creation scorers (#143/#207). Each: (new_text, parent_text) -> float | None
# in [0, 1], higher = more similar. Best-effort — a scorer returning None or raising is
# skipped. The 'char' fallback ships working now; #207 fills in 'semantic' (cosine).
_SIMILARITY_SCORERS = {'char': _char_similarity, 'semantic': _semantic_similarity}


def _statement_similarity_scores(new_text, parent_text) -> dict[str, float]:
    scores = {}
    for name, fn in _SIMILARITY_SCORERS.items():
        try:
            value = fn(new_text, parent_text)
        except Exception:
            current_app.logger.exception('similarity scorer %s failed', name)
            continue
        if value is not None:
            scores[name] = value
    return scores


def _preferred_similarity_score(scores: dict[str, float]) -> tuple[str | None, float | None]:
    if 'semantic' in scores:
        return 'semantic', scores['semantic']
    if 'char' in scores:
        return 'char', scores['char']
    return None, None


def _derivative_similarity_threshold() -> float:
    raw = current_app.config.get('STATEMENT_DERIVATIVE_MIN_SIMILARITY', 0)
    try:
        return max(0.0, min(1.0, float(raw)))
    except (TypeError, ValueError):
        return 0.0


def record_statement_provenance(conv_id, new_tid, derived_from_tid,
                                parent_text=None, new_text=None, scores=None):
    """Record that `new_tid` is a derivative of `derived_from_tid` (#143), best-effort.

    Writes one StatementProvenance row (declared link) plus a StatementSimilarityScore row
    per scorer that yields a value. A scorer failure never blocks the link; a provenance
    write failure is swallowed (logged). Returns the row, or None on failure.

    Pass `scores` (from an earlier `_statement_similarity_scores` call) to avoid
    recomputing them — the caller already scores the pair for the derivative gate,
    so recomputing here would repeat the similarity sidecar call.
    """
    try:
        row = StatementProvenance(
            conversation_id=conv_id, polis_statement_id=new_tid,
            derived_from_tid=derived_from_tid, provenance_type='derivative',
            link_method='declared')
        db.session.add(row)
        db.session.flush()        # need row.id for the score FKs
        if scores is None and parent_text is not None and new_text is not None:
            scores = _statement_similarity_scores(new_text, parent_text)
        if scores:
            for name, value in scores.items():
                db.session.add(StatementSimilarityScore(
                    provenance_id=row.id, model=name, value=value))
        db.session.commit()
        return row
    except Exception:
        db.session.rollback()
        current_app.logger.exception('provenance write failed for tid %s', new_tid)
        return None


def _provenance_map(conv_id, tids):
    """{tid: StatementProvenance} for the given tids in one query (bulk, like the other maps)."""
    tids = [t for t in tids if t is not None]
    if not tids:
        return {}
    rows = (StatementProvenance.query
            .options(joinedload(StatementProvenance.scores))
            .filter(StatementProvenance.conversation_id == conv_id,
                    StatementProvenance.polis_statement_id.in_(tids))
            .all())
    return {r.polis_statement_id: r for r in rows}


def _lineage_group(conv_id, tid):
    """Walk `derived_from_tid` from `tid` up to its root; return [tid, parent, …, root].

    The primitive the clustering/weighting consumers (#143 follow-ups) build on. Cycle-safe.
    """
    by_tid = {r.polis_statement_id: r.derived_from_tid
              for r in StatementProvenance.query.filter_by(conversation_id=conv_id).all()}
    chain, seen = [tid], {tid}
    cur = tid
    while cur in by_tid:
        parent = by_tid[cur]
        if parent in seen:          # defensive: stop on any cycle
            break
        chain.append(parent)
        seen.add(parent)
        cur = parent
    return chain


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__)

    # ── Dev DB isolation ──────────────────────────────────────────────────────
    # When running locally with DEV_LOGIN_USER set, force a separate SQLite DB
    # regardless of what database-url/DATABASE_URL contains. This prevents a
    # stray prod URL in .env from being touched during local dev.
    # Production (Toolforge) is detected via TOOL_TOOLFORGE_API_URL and bypasses
    # this branch entirely.
    _dev_user     = os.environ.get('DEV_LOGIN_USER', '').strip()
    _on_toolforge = bool(os.environ.get('TOOL_TOOLFORGE_API_URL'))
    _is_dev_mode  = (app.debug or os.environ.get('FLASK_DEBUG') == '1') \
                    and _dev_user and not _on_toolforge

    if _is_dev_mode:
        dev_url = os.environ.get('DEV_DATABASE_URL', '').strip() or 'sqlite:///dev.db'
        if not dev_url.startswith('sqlite:///'):
            raise RuntimeError(
                'DEV_DATABASE_URL must be a sqlite:/// URL when DEV_LOGIN_USER '
                'is set. Refusing to start to prevent accidental prod writes.'
            )
        app.config['SQLALCHEMY_DATABASE_URI'] = dev_url
        app.logger.warning(
            'DEV MODE: SQLALCHEMY_DATABASE_URI forced to %s '
            '(ignoring database-url secret / DATABASE_URL env)', dev_url)
    else:
        _db_url = (test_config or {}).get('SQLALCHEMY_DATABASE_URI') or _read_secret('database-url')
        if not _db_url:
            raise RuntimeError(
                'DATABASE_URL is not set. '
                'Set it via `toolforge envvars create DATABASE_URL <url>` or the '
                'DATABASE_URL environment variable. '
                'Example: mysql+pymysql://s11111:<pw>@tools.db.svc.wikimedia.cloud/s11111__wiki-polis?charset=utf8mb4'
            )
        app.config['SQLALCHEMY_DATABASE_URI'] = _db_url

    _secret_key = (test_config or {}).get('SECRET_KEY') or _read_secret('secret-key')
    if not _secret_key:
        if not app.debug:
            raise RuntimeError(
                'SECRET_KEY is not set. '
                'Generate one with: python -c "import secrets; print(secrets.token_hex(32))" '
                'then set it as the "secret-key" Kubernetes secret or SECRET_KEY env var.'
            )
        _secret_key = 'dev-insecure-key'
    app.config['SECRET_KEY'] = _secret_key
    app.config['XID_HASH_SECRET'] = (
        (test_config or {}).get('XID_HASH_SECRET')
        or _read_secret('xid-hash-secret')
        or os.environ.get('XID_HASH_SECRET', '')
        or _secret_key
    )
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    # On MariaDB/MySQL (prod ToolsDB) size the pool so threaded uWSGI workers don't
    # starve waiting on a connection, and fail fast (pool_timeout) rather than hang
    # under exhaustion. SQLite (dev/tests) keeps the default pool — pool_size /
    # max_overflow are for QueuePool and don't apply to its thread-local connections.
    # Reconcile processes x (pool_size + max_overflow) with ToolsDB max_user_connections.
    _engine_options = {'pool_recycle': 280, 'pool_pre_ping': True}
    if not str(app.config.get('SQLALCHEMY_DATABASE_URI', '')).startswith('sqlite'):
        _engine_options['pool_size']    = int(os.environ.get('TOOLSDB_POOL_SIZE', '10'))
        _engine_options['max_overflow'] = int(os.environ.get('TOOLSDB_MAX_OVERFLOW', '10'))
        _engine_options['pool_timeout'] = int(os.environ.get('TOOLSDB_POOL_TIMEOUT', '10'))
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = _engine_options

    app.config['SESSION_TYPE']               = 'sqlalchemy'
    app.config['SESSION_SQLALCHEMY']         = db
    app.config['SESSION_PERMANENT']          = True
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)
    app.config['SESSION_COOKIE_HTTPONLY']    = True
    app.config['SESSION_COOKIE_SAMESITE']    = 'Lax'
    app.config['SESSION_COOKIE_SECURE']      = not app.debug

    app.config['OAUTH_CLIENT_ID']     = _read_secret('oauth-client-id')
    app.config['OAUTH_CLIENT_SECRET'] = _read_secret('oauth-client-secret')
    app.config['OAUTH_REDIRECT_URI']  = _read_secret('oauth-redirect-uri')
    app.config['PARTICIAPI_BASE']     = (_read_secret('particiapi-base-url')
                                         or os.environ.get('PARTICIAPI_BASE_URL', 'http://localhost:8000'))
    # Shared secret that lets the proxy assert the logged-in user's stable identity
    # (xid) to Particiapi, so a participant keeps the same Polis uid across devices
    # instead of a fresh anonymous one per session. Must match Particiapi's
    # TRUSTED_SUB_SECRET. Unset → falls back to the old anonymous-per-session behaviour.
    app.config['PARTICIAPI_SUB_SECRET'] = (_read_secret('particiapi-sub-secret')
                                           or os.environ.get('PARTICIAPI_SUB_SECRET', ''))
    app.config['POLIS_DATABASE_URL'] = (_read_secret('polis-database-url')
                                        or os.environ.get('POLIS_DATABASE_URL', ''))
    app.config['POLIS_SERVER_URL']   = (_read_secret('polis-server-url')
                                        or os.environ.get('POLIS_SERVER_URL', ''))
    app.config['POLIS_ADMIN_EMAIL']  = (_read_secret('polis-admin-email')
                                        or os.environ.get('POLIS_ADMIN_EMAIL', ''))
    app.config['POLIS_ADMIN_PASSWORD'] = (_read_secret('polis-admin-password')
                                          or os.environ.get('POLIS_ADMIN_PASSWORD', ''))
    app.config['ACCOUNT_ELIGIBILITY_URL'] = (
        _read_secret('account-eligibility-url')
        or os.environ.get('ACCOUNT_ELIGIBILITY_URL', '')
    )
    app.config['STATEMENT_SIMILARITY_URL'] = (
        _read_secret('statement-similarity-url')
        or os.environ.get('STATEMENT_SIMILARITY_URL', '')
    )
    app.config['STATEMENT_SIMILARITY_TIMEOUT'] = (
        os.environ.get('STATEMENT_SIMILARITY_TIMEOUT', '1.5')
    )
    app.config['STATEMENT_DERIVATIVE_MIN_SIMILARITY'] = (
        os.environ.get('STATEMENT_DERIVATIVE_MIN_SIMILARITY', '0')
    )

    # Apply test overrides before extensions are initialised so SESSION_TYPE,
    # SQLALCHEMY_DATABASE_URI, etc. are effective from the first db.init_app call.
    if test_config is not None:
        app.config.update(test_config)

    _polis_config_error = polis_server_config_error(
        app.config.get('POLIS_SERVER_URL', ''),
        app.config.get('POLIS_ADMIN_EMAIL', ''),
        app.config.get('POLIS_ADMIN_PASSWORD', ''),
    )
    if _polis_config_error:
        app.logger.warning('Polis HTTP admin configuration: %s', _polis_config_error)

    # Migration mode: set by deploy.sh --migrate to skip web-server-only
    # startup checks (rate limiting, trusted hosts) that require
    # Kubernetes-injected vars unavailable on the Toolforge bastion.
    # Has no effect on which code runs at request time.
    _migration_mode = bool(os.environ.get('MIGRATION_MODE'))

    _trust_proxy_headers = app.config.get('TRUST_PROXY_HEADERS')
    if _trust_proxy_headers is None:
        _trust_proxy_headers = _read_secret('trust-proxy-headers')
    app.config['TRUST_PROXY_HEADERS'] = (
        _truthy(_trust_proxy_headers) or bool(os.environ.get('TOOL_TOOLFORGE_API_URL'))
    )

    _trusted_hosts = app.config.get('TRUSTED_HOSTS')
    if _trusted_hosts is None:
        _trusted_hosts = _split_csv(_read_secret('trusted-hosts'))
    elif isinstance(_trusted_hosts, str):
        _trusted_hosts = _split_csv(_trusted_hosts)
    if _trusted_hosts:
        app.config['TRUSTED_HOSTS'] = _trusted_hosts
    elif not app.debug and not app.testing and not _migration_mode:
        raise RuntimeError(
            'TRUSTED_HOSTS is not set. Configure comma-separated allowed hostnames '
            'such as wiki-polis.toolforge.org before starting production.'
        )

    _ratelimit_storage_uri = (
        app.config.get('RATELIMIT_STORAGE_URI')
        or _read_secret('ratelimit-storage-uri')
        or os.environ.get('TOOL_REDIS_URI', '').strip()
    )
    if _ratelimit_storage_uri:
        if (not app.debug and not app.testing and not _migration_mode
                and not _ratelimit_storage_uri.startswith(_REDIS_RATELIMIT_SCHEMES)):
            raise RuntimeError(
                'RATELIMIT_STORAGE_URI must use a Redis backend in production '
                '(for example Toolforge TOOL_REDIS_URI or redis://...).'
            )
        app.config['RATELIMIT_STORAGE_URI'] = _ratelimit_storage_uri
    elif not app.debug and not app.testing and not _migration_mode:
        raise RuntimeError(
            'RATELIMIT_STORAGE_URI is not set and Toolforge TOOL_REDIS_URI is unavailable. '
            'Configure Redis-backed Flask-Limiter storage before starting production.'
        )

    _ratelimit_key_prefix = app.config.get('RATELIMIT_KEY_PREFIX')
    if _ratelimit_key_prefix is None:
        _ratelimit_key_prefix = _read_secret('ratelimit-key-prefix')
    _ratelimit_key_prefix = str(_ratelimit_key_prefix).strip() if _ratelimit_key_prefix else ''
    if _ratelimit_key_prefix:
        app.config['RATELIMIT_KEY_PREFIX'] = _ratelimit_key_prefix
    elif not app.debug and not app.testing and not _migration_mode:
        raise RuntimeError(
            'RATELIMIT_KEY_PREFIX is not set. Configure a unique Toolforge Redis key '
            'prefix such as wiki-polis:<random>: before starting production.'
        )

    _ratelimit_identity_secret = app.config.get('RATELIMIT_IDENTITY_SECRET')
    if _ratelimit_identity_secret is None:
        _ratelimit_identity_secret = _read_secret('ratelimit-identity-secret')
    _ratelimit_identity_secret = (
        str(_ratelimit_identity_secret).strip() if _ratelimit_identity_secret else ''
    )
    if _ratelimit_identity_secret:
        if (not app.debug and not app.testing and not _migration_mode
                and len(_ratelimit_identity_secret) < _MIN_RATELIMIT_IDENTITY_SECRET_LEN):
            raise RuntimeError(
                'RATELIMIT_IDENTITY_SECRET must be at least 32 characters in production.'
            )
        app.config['RATELIMIT_IDENTITY_SECRET'] = _ratelimit_identity_secret
    elif not app.debug and not app.testing and not _migration_mode:
        raise RuntimeError(
            'RATELIMIT_IDENTITY_SECRET is not set. Configure a random secret so '
            'rate-limit keys do not expose raw client identities in shared Redis.'
        )

    # Configure logging before extensions init so their startup logs are formatted/correlated.
    configure_logging(app, on_toolforge=_on_toolforge)

    db.init_app(app)
    Migrate(app, db)
    Session(app)
    csrf.init_app(app)
    limiter.init_app(app)

    @app.cli.command('init-db')
    def init_db_cmd():
        """Initialise or migrate the database. Idempotent.

        Fresh DB: creates all tables via SQLAlchemy then stamps Alembic at head
        (the incremental migrations assume a base schema already exists).
        Existing DB: runs any pending Alembic migrations.
        """
        import sqlalchemy as _sa
        from flask_migrate import upgrade as _upgrade
        from alembic import command as _alembic_cmd
        from alembic.runtime.migration import MigrationContext
        from alembic.script import ScriptDirectory
        migrate_ext = app.extensions.get('migrate')
        alembic_cfg = migrate_ext.migrate.get_config()
        inspector = _sa.inspect(db.engine)
        with db.engine.connect() as _conn:
            current_rev = MigrationContext.configure(_conn).get_current_revision()
        head_rev = ScriptDirectory.from_config(alembic_cfg).get_current_head()
        if current_rev == head_rev:
            click.echo('Database already at head revision.')
        elif 'participants' not in inspector.get_table_names():
            db.create_all()
            _alembic_cmd.stamp(alembic_cfg, 'head')
            click.echo('Fresh database created and stamped at head.')
        elif current_rev is None:
            # Tables exist but alembic_version is empty — create_all() ran but
            # stamp() failed (e.g. wrong working directory). Schema is already
            # current; just record the revision.
            _alembic_cmd.stamp(alembic_cfg, 'head')
            click.echo('Existing schema stamped at head.')
        else:
            _upgrade()
            click.echo('Database migrated to head revision.')

    @app.cli.command('process-phase-schedules')
    def process_phase_schedules_cmd():
        """Fire due scheduled active-to-passive phase transitions."""
        result = _process_due_scheduled_transitions()
        click.echo(
            'Scheduled transitions: '
            f'{result["fired"]} fired, {result["aborted"]} aborted, '
            f'{result["skipped"]} not due.'
        )

    @app.before_request
    def _set_csp_nonce():
        g.csp_nonce = secrets.token_urlsafe(16)

    @app.before_request
    def _set_request_id():
        # Mint a fresh id by default. Only honour an inbound X-Request-Id when behind a
        # trusted proxy AND it is well-formed — an unvalidated inbound value is a
        # log-forging / header-injection vector.
        rid = None
        if app.config.get('TRUST_PROXY_HEADERS'):
            inbound = request.headers.get('X-Request-Id', '')
            if _REQUEST_ID_RE.match(inbound):
                rid = inbound
        g.request_id = rid or secrets.token_urlsafe(8)
        g._t0 = time.perf_counter()

    @app.context_processor
    def _inject_globals():
        participant = _current_participant()
        return {
            'is_admin':   _is_global_admin(participant),
            'username':   session.get('username'),
            'csp_nonce':  g.get('csp_nonce', ''),
            'git_version': _GIT_VERSION,
            # Header mode drives the demo/real switch + demo theme (#293).
            # Pages override this via render_template kwargs; default keeps the
            # switch off on pages outside the fork/lanes (e.g. admin).
            'header_mode': None,
        }

    @app.after_request
    def _security_headers(response):
        nonce = g.get('csp_nonce', '')
        csp = (
            "default-src 'self'; "
            f"script-src 'self' 'nonce-{nonce}'; "
            "style-src 'self' 'unsafe-inline'; "
            "font-src 'self'; "
            "connect-src 'self'; "
            "img-src 'self' data:; "
            "frame-ancestors 'none';"
        )
        response.headers['Content-Security-Policy'] = csp
        response.headers['X-Content-Type-Options']  = 'nosniff'
        response.headers['Referrer-Policy']         = 'strict-origin-when-cross-origin'
        # X-Frame-Options superseded by frame-ancestors in CSP above, but kept for old browsers
        response.headers['X-Frame-Options']         = 'DENY'
        response.headers['X-Request-Id']            = g.get('request_id', '-')

        # Diagnostic completion line. request_id + participant_id ride the LogRecord factory
        # (no DB access here). Skip successful static-asset hits to keep the log signal-dense;
        # static errors (>=400) still log.
        if not (request.path.startswith('/static/') and response.status_code < 400):
            _t0 = g.get('_t0')
            _ms = round((time.perf_counter() - _t0) * 1000, 1) if _t0 is not None else None
            app.logger.info(
                '%s %s -> %s (%sms)', request.method, request.path, response.status_code, _ms,
                extra={'http_method': request.method, 'http_path': request.path,
                       'http_status': response.status_code, 'duration_ms': _ms})

        # Cache static assets (fonts, CSS, JS) for 1 week.
        # URLs include ?v=<git-sha> so each deploy busts the cache automatically.
        # 1 week (not 1 year) limits blast radius if a bad asset slips through.
        # Note: .woff2 font files are referenced by relative URL from fonts.css (a static
        # file, not a template) so they cannot carry ?v= — treat them as immutable; rename
        # the files if fonts ever need to change.
        if request.path.startswith('/static/') and response.status_code == 200:
            response.headers['Cache-Control'] = 'public, max-age=604800'
        elif response.content_type.startswith('text/html'):
            # Prevent intermediary proxies from caching HTML pages; stale HTML pointing
            # to old ?v= URLs would cause users to load mismatched assets after a deploy.
            response.headers.setdefault('Cache-Control', 'no-store')

        return response

    _register_routes(app)

    # Generic Particiapi proxy: CSRF-exempt with _validate_same_origin() as the
    # compensating control; first-party statement submission is on participant_bp.
    app.register_blueprint(proxy_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(participant_bp)
    app.register_blueprint(create_api_v1_blueprint(
        resolve_participant=_current_participant,
        resolve_global_admin=_is_global_admin,
    ))
    register_api_error_handlers(app)
    csrf.exempt(proxy_bp)

    # Startup fingerprint — config-only, no secrets, no live probe. Answers
    # "is this environment configured as expected" before chasing a phantom bug.
    try:
        _db_backend = make_url(app.config.get('SQLALCHEMY_DATABASE_URI', '')).drivername
    except Exception:
        _db_backend = 'unknown'
    app.logger.info(
        'startup env=%s db=%s polis=%s polis_pg=%s version=%s',
        'toolforge' if _on_toolforge else 'dev', _db_backend,
        bool(app.config.get('POLIS_SERVER_URL')), bool(app.config.get('POLIS_DATABASE_URL')),
        _GIT_VERSION,
        extra={'env': 'toolforge' if _on_toolforge else 'dev', 'db_backend': _db_backend,
               'polis_configured': bool(app.config.get('POLIS_SERVER_URL')),
               'polis_pg_configured': bool(app.config.get('POLIS_DATABASE_URL')),
               'git_version': _GIT_VERSION})

    return app


# ── Phase 6 final report ──────────────────────────────────────────────────────

@participant_bp.get('/c/<slug>/report')
def conversation_report(slug):
    """Phase 6 final results report — aggregate only, no personal votes.

    Accessible once the conversation is closed (conv.closed_at is set).
    Requires login when phase_personal_results is set; public when
    phase_public_results is set.

    Surface B: post-close, post-organizer-cleanup. Marked 'Final report'.
    For the preliminary in-round view see the Results tab on the conversation page.
    """
    conv = Conversation.query.filter_by(slug=slug).first_or_404()
    participant = _current_participant()
    participation = (
        Participation.query.filter_by(
            conversation_id=conv.id,
            participant_id=participant.id,
        ).first()
        if participant else None
    )
    _check_conversation_access(conv, participant)

    if not conv.closed_at:
        # Conversation still open — redirect to the results tab.
        return redirect(url_for('participant.conversation', slug=slug) + '#tab-results')

    if not (conv.phase_public_results or conv.phase_personal_results):
        return redirect(url_for('participant.conversation', slug=slug))

    if conv.phase_personal_results and not conv.phase_public_results and not participant:
        return redirect(url_for('participant.login') + f'?next={request.path}')

    report_filter = Phase6ResultsFilter.from_snapshot(conv.report_filter_snapshot)
    phase6_results = _build_phase6_results(
        conv, participation=None, results_filter=report_filter)  # aggregate only

    reveal = _reveal_context(conv, participation)
    return render_template(
        'report.html',
        conversation=conv,
        participation=participation,
        phase6_results=phase6_results,
        output_context=next(item for item in _output_items(conv) if item['key'] == 'report'),
        reveal=reveal,
        reveal_state=reveal['state'] if reveal else None,
    )


# ── Routes ────────────────────────────────────────────────────────────────────

def _register_routes(app: Flask) -> None:

    _dev_login_user = os.environ.get('DEV_LOGIN_USER', '').strip()
    _on_toolforge   = bool(os.environ.get('TOOL_TOOLFORGE_API_URL'))
    _staging_dev_token = _read_secret('staging-dev-token')
    _staging_dev_login_enabled = bool(
        _on_toolforge
        and _staging_dev_token
        and len(_staging_dev_token) >= _MIN_STAGING_DEV_TOKEN_LEN
        and _is_staging_toolforge_app(app)
    )
    app.config['STAGING_DEV_LOGIN'] = _staging_dev_login_enabled

    if app.debug and _dev_login_user and not _on_toolforge:
        @app.get('/dev-login')
        @limiter.limit('20 per minute')
        def dev_login():
            username = _dev_login_user
            xid = _derive_xid(f'dev:{username}')
            participant = reconcile_participant_login(
                Participant.query.filter_by(mw_username=username).first(),
                mw_user_id=abs(hash(username)) % 10**9,
                mw_username=username,
                new_xid=xid,
                xid_key_version=_XID_HMAC_VERSION,
            )
            if participant.id is None:
                db.session.add(participant)
            db.session.commit()
            session['username']  = username
            session['xid']       = participant.xid
            session['emailable'] = _is_emailable(username)
            return redirect(url_for('index'))

    # ── Dev test users (DEV_FAKE_LOGIN=1) ────────────────────────────────────
    # Hardcoded test accounts with negative mw_user_ids so they can never
    # collide with real Wikimedia accounts. Only active for local debug runs;
    # never register this bypass on Toolforge or other non-debug deployments.

    _DEV_TEST_USERS = [
        {'username': 'dev-user-1', 'mw_user_id': -1},
        {'username': 'dev-user-2', 'mw_user_id': -2},
        {'username': 'dev-user-3', 'mw_user_id': -3},
    ]

    _fake_login_requested = os.environ.get('DEV_FAKE_LOGIN', '').strip() == '1'
    _fake_login_enabled = bool(app.debug and _fake_login_requested and not _on_toolforge)
    if _fake_login_requested and not _fake_login_enabled:
        app.logger.warning(
            'DEV_FAKE_LOGIN ignored because fake login is only allowed in local debug mode'
        )
    app.config['DEV_FAKE_LOGIN'] = _fake_login_enabled
    app.config['DEV_TEST_USERS'] = (
        _DEV_TEST_USERS if (_fake_login_enabled or _staging_dev_login_enabled) else []
    )

    if _fake_login_enabled or _staging_dev_login_enabled:
        @app.get('/dev/login/<username>')
        @limiter.limit('30 per minute')
        def dev_fake_login(username):
            user = next((u for u in _DEV_TEST_USERS if u['username'] == username), None)
            if user is None:
                return 'Unknown test user', 404
            if _staging_dev_login_enabled and not _fake_login_enabled:
                supplied = request.args.get('token', '')
                expected = _staging_dev_login_token(username, _staging_dev_token)
                if not hmac.compare_digest(supplied, expected):
                    abort(403)
            xid = _derive_xid(f'dev-fake:{user["mw_user_id"]}:{username}')
            participant = reconcile_participant_login(
                Participant.query.filter_by(mw_user_id=user['mw_user_id']).first(),
                mw_user_id=user['mw_user_id'],
                mw_username=username,
                new_xid=xid,
                xid_key_version=_XID_HMAC_VERSION,
            )
            if participant.id is None:
                db.session.add(participant)
            db.session.commit()
            session['username']  = username
            session['xid']       = participant.xid
            session['emailable'] = False
            return redirect(url_for('index'))

    # ── Home ─────────────────────────────────────────────────────────────────

    @app.get('/')
    def index():
        # The homepage is an explicit fork between the demo sandbox and real
        # consultations (#293), so a visitor who only wants to try things can
        # never drift into a live consultation by accident. Shown every visit.
        dev_test_users = current_app.config.get('DEV_TEST_USERS', [])
        return render_template('fork.html',
                               header_mode='fork',
                               dev_test_users=dev_test_users)

    def _render_lane(*, demo: bool, header_mode: str):
        """Render the home listing for one space (#293).

        The demo and real lanes share the SAME interface (home.html) — same tabs,
        same cards — and differ only in the set of conversations shown (demo vs
        real) and the page background (the demo blue wash, via header_mode). This
        keeps one listing implementation instead of a bespoke demo page.
        """
        dev_test_users = current_app.config.get('DEV_TEST_USERS', [])

        if 'username' not in session:
            if demo:
                listing = (Conversation.query
                           .filter_by(active=True, paused=False, access_policy='demo')
                           .order_by(Conversation.created_at.desc()).all())
            else:
                listing = (Conversation.query
                           .filter_by(active=True, paused=False)
                           .filter(Conversation.access_policy == 'public')
                           .order_by(Conversation.created_at.desc()).all())
            signals_map = {c.id: {'phases': _active_phases(c),
                                  'outputs': _output_items(c)} for c in listing}
            return render_template('home.html',
                                   header_mode=header_mode,
                                   public_conversations=listing,
                                   signals_map=signals_map,
                                   dev_test_users=dev_test_users)

        participant = _current_participant()
        username    = session['username']

        joined_parts = (
            Participation.query
            .options(joinedload(Participation.conversation))
            .filter_by(participant_id=participant.id).all()
            if participant else []
        )
        joined_ids = {p.conversation_id for p in joined_parts}

        # Each lane lists only its own space's conversations.
        active_joined   = []
        archived_joined = []
        for part in joined_parts:
            conv = part.conversation
            if conv and (conv.access_policy == 'demo') == demo:
                (active_joined if conv.active else archived_joined).append(conv)

        if demo:
            available = (Conversation.query
                         .filter_by(active=True, paused=False, access_policy='demo')
                         .filter(~Conversation.id.in_(joined_ids or [0]))
                         .order_by(Conversation.created_at.desc()).all())
        else:
            invited_ids = [
                inv.conversation_id
                for inv in ConversationInvite.query.filter_by(mw_username=username).all()
            ]
            available = (Conversation.query
                         .filter_by(active=True, paused=False)
                         .filter(~Conversation.id.in_(joined_ids or [0]))
                         .filter(db.or_(
                             Conversation.access_policy == 'public',
                             db.and_(
                                 Conversation.access_policy == 'invite_only',
                                 Conversation.id.in_(invited_ids or [0]),
                             ),
                         ))
                         .order_by(Conversation.created_at.desc()).all())

        mod_ids: set = set()
        moderating = []
        if participant:
            if _is_global_admin(participant):
                moderating = (Conversation.query
                              .order_by(Conversation.created_at.desc()).all())
                mod_ids = {c.id for c in moderating}
            else:
                roles = AdminRole.query.filter(
                    AdminRole.participant_id == participant.id,
                ).all()
                if roles:
                    mod_ids = {r.conversation_id for r in roles}
                    moderating = Conversation.query.filter(
                        Conversation.id.in_(mod_ids)).all()

        # "You moderate" is scoped to this lane's space too.
        moderating = [c for c in moderating if (c.access_policy == 'demo') == demo]
        # Exclude moderated conversations from Browse — they already appear in "You moderate"
        available = [c for c in available if c.id not in mod_ids]

        pseudonym_map = {p.conversation_id: p for p in joined_parts}
        all_home_convs = active_joined + archived_joined + list(available)

        xid = session.get('xid')
        submission_convs = [c for c in all_home_convs if c.phase_submission and c.active]
        zinvites = [c.polis_id for c in submission_convs if c.polis_id]
        remaining_by_zinvite: dict = {}
        if zinvites and xid:
            result = _polis_server_client().get_statements_remaining_bulk(zinvites, xid)
            if result:
                remaining_by_zinvite = result
        signals_map: dict = {}
        for conv in all_home_convs:
            part = pseudonym_map.get(conv.id)
            reveal = _reveal_context(conv, part) if conv.closed_at else None
            remaining = remaining_by_zinvite.get(
                conv.polis_id) if conv.polis_id else None
            signals_map[conv.id] = {
                'phases':               _active_phases(conv),
                'outputs':              _output_items(conv),
                'statements_remaining': remaining,
                'reveal':               reveal,
            }

        return render_template('home.html',
                               header_mode=header_mode,
                               active_joined=active_joined,
                               archived_joined=archived_joined,
                               available=available,
                               moderating=moderating,
                               pseudonym_map=pseudonym_map,
                               signals_map=signals_map,
                               dev_test_users=dev_test_users)

    @app.get('/demo')
    def demo_lane():
        # The demo lane: the same listing UI as the real lane, filtered to demo
        # conversations and tinted (#293). Available logged in or out.
        session['space'] = 'demo'
        return _render_lane(demo=True, header_mode='demo')

    @app.get('/consultations')
    def consultations():
        # The real lane: the shared listing UI, filtered to real conversations (#293).
        session['space'] = 'real'
        return _render_lane(demo=False, header_mode='real')


    # ── OAuth ─────────────────────────────────────────────────────────────────

    @app.get('/login')
    @limiter.limit('20 per minute')
    def login():
        if not app.config.get('OAUTH_CLIENT_ID'):
            if app.debug and _dev_login_user and not _on_toolforge:
                return redirect(url_for('dev_login'))
            return 'OAuth not configured — set OAUTH_CLIENT_ID, OAUTH_CLIENT_SECRET, OAUTH_REDIRECT_URI', 503

        code_verifier  = secrets.token_urlsafe(64)
        code_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode()).digest()
        ).rstrip(b'=').decode()

        state = secrets.token_urlsafe(32)
        session['oauth_state']         = state
        session['oauth_code_verifier'] = code_verifier

        params = urlencode({
            'response_type':         'code',
            'client_id':             app.config['OAUTH_CLIENT_ID'],
            'redirect_uri':          app.config['OAUTH_REDIRECT_URI'],
            'scope':                 'basic',
            'state':                 state,
            'code_challenge':        code_challenge,
            'code_challenge_method': 'S256',
        })
        return redirect(f'https://meta.wikimedia.org/w/rest.php/oauth2/authorize?{params}')

    @app.get('/oauth-callback')
    @limiter.limit('30 per minute')
    def oauth_callback():
        if request.args.get('state') != session.pop('oauth_state', None):
            app.logger.warning('OAuth callback: state mismatch (likely duplicate login tab or expired session)')
            flash('Login failed — please try again.', 'error')
            return redirect(url_for('login'))

        code          = request.args.get('code', '')
        code_verifier = session.pop('oauth_code_verifier', '')
        if not code:
            return redirect(url_for('index'))

        try:
            token_resp = requests.post(
                'https://meta.wikimedia.org/w/rest.php/oauth2/access_token',
                data={
                    'grant_type':    'authorization_code',
                    'code':          code,
                    'redirect_uri':  app.config['OAUTH_REDIRECT_URI'],
                    'client_id':     app.config['OAUTH_CLIENT_ID'],
                    'client_secret': app.config['OAUTH_CLIENT_SECRET'],
                    'code_verifier': code_verifier,
                },
                headers={'User-Agent': _MW_USER_AGENT},
                timeout=10,
            )
            token_resp.raise_for_status()
            access_token = token_resp.json()['access_token']

            profile_resp = requests.get(
                'https://meta.wikimedia.org/w/rest.php/oauth2/resource/profile',
                headers={'Authorization': f'Bearer {access_token}',
                         'User-Agent': _MW_USER_AGENT},
                timeout=10,
            )
            profile_resp.raise_for_status()
            identity = profile_resp.json()
        except Exception as exc:
            app.logger.warning('OAuth callback failed: %s', exc)
            return redirect(url_for('index'))

        username   = identity.get('username', '').strip()
        mw_user_id = identity.get('sub')
        if not username or not mw_user_id:
            return redirect(url_for('index'))

        xid = _derive_xid(f'mw:{mw_user_id}')

        participant = reconcile_participant_login(
            Participant.query.filter_by(mw_user_id=mw_user_id).first(),
            mw_user_id=mw_user_id,
            mw_username=username,
            new_xid=xid,
            xid_key_version=_XID_HMAC_VERSION,
        )
        if participant.id is None:
            db.session.add(participant)
        db.session.commit()

        next_url = session.pop('next', None)
        session.clear()
        session['username']   = username
        session['xid']        = participant.xid
        session['emailable']  = _is_emailable(username)

        return redirect(_safe_redirect(next_url or '', url_for('index')))

    @app.post('/logout')
    @login_required
    def logout():
        session.clear()
        return redirect(url_for('index'))

    # ── Health ────────────────────────────────────────────────────────────────

    @app.get('/health')
    @limiter.exempt
    def health():
        result = {'db': 'ok', 'particiapi': 'ok'}

        try:
            with db.engine.connect() as conn:
                conn.execute(_sa_text('SELECT 1'))
        except Exception:
            result['db'] = 'error'

        try:
            base = current_app.config.get('PARTICIAPI_BASE', '')
            requests.get(f'{base}/api/conversations/', timeout=2)
        except Exception:
            result['particiapi'] = 'unreachable'

        result['status'] = 'ok' if all(v == 'ok' for v in result.values()) else 'degraded'
        status_code = 200 if result['status'] == 'ok' else 503
        return jsonify(result), status_code


app = create_app()

if __name__ == '__main__':
    app.run(host='127.0.0.1', debug=app.debug)

"""
app.py — Flask application for wiki-polis v2.
"""

import base64
import click
import functools
import hashlib
import hmac
import os
import random
import re
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode, urlparse, urljoin

import coolname
import nh3
import requests
from dotenv import load_dotenv
from flask import (Blueprint, Flask, abort, current_app, flash, g, jsonify,
                   make_response, redirect, render_template, request, session,
                   url_for)
from flask_migrate import Migrate
from flask_session import Session
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect, validate_csrf
from sqlalchemy import text as _sa_text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import joinedload
from wtforms.validators import ValidationError

from db import (ACCESS_POLICIES, ADMIN_ROLES, AdminRole, Argument, ArgumentSideState,
                ArgumentVote, Conversation, ConversationInvite, FeaturedStatement,
                Participant, Participation, db)
from polis_admin import (PolisParticipantClient, PolisParticipantError,
                         PolisServerClient, PolisServerError)
from seed_csv import MAX_FILE_BYTES, MAX_ROWS, parse_csv_bytes, strip_formula_prefixes

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))

_MW_USER_AGENT   = 'wiki-polis/2.0 (Toolforge tool; https://wiki-polis.toolforge.org)'
_TEXT_ALLOWED_TAGS  = {'p', 'strong', 'em', 'a', 'ul', 'ol', 'li', 'br'}
_TEXT_ALLOWED_ATTRS = {'a': {'href', 'title'}}
_POLIS_ID_RE     = re.compile(r'^[A-Za-z0-9]{6,20}$')
_SLUG_RE         = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')
_PSEUDONYM_RE    = re.compile(r'^[a-z]{2,20}-[a-z]{2,20}$')
_REDIS_RATELIMIT_SCHEMES = ('redis://', 'rediss://')
_MIN_RATELIMIT_IDENTITY_SECRET_LEN = 32


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


ADMIN_USERS = [u.strip() for u in _read_secret('admin-users').split(',') if u.strip()]

_REVEAL_COOLDOWN_DAYS = 30   # days after close before reveal window opens
_REVEAL_WINDOW_DAYS   = 30   # days participants may opt in once the window opens
_MATH_RECOMPUTE_COOLDOWN = 600  # seconds between auto-triggered recomputes per conversation
_math_recompute_last: dict[int, float] = {}  # conv.id → epoch of last trigger

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
_PHASE_FLAGS = [s['flag'] for s in PHASE_SEQUENCE if s['flag']]


def _current_stage_index(conv) -> int:
    """Furthest-along stage whose flag is on; 0 (preparation) if none on."""
    idx = 0
    for i, stage in enumerate(PHASE_SEQUENCE):
        if stage['flag'] and getattr(conv, stage['flag']):
            idx = i
    return idx


def _is_linear_phase_state(conv) -> bool:
    """True if at most one phase flag is on — the simple-mode invariant."""
    return sum(1 for f in _PHASE_FLAGS if getattr(conv, f)) <= 1


def _advance_target_index(conv) -> int | None:
    """Index simple-mode advance would move to, or None if no forward move.

    Active conversation: one step forward. Closed conversation: jump straight
    to the final stage (public results) — closed consultations skip the
    intermediate steps. Returns None when already at/after the target.
    """
    i = _current_stage_index(conv)
    last = len(PHASE_SEQUENCE) - 1
    target = last if not conv.active else i + 1
    return target if target > i and target <= last else None


def _advance_confirm_message(conv) -> str:
    """Plain-language confirmation describing what the next forward move does
    to participants in this specific conversation."""
    i = _current_stage_index(conv)
    target = _advance_target_index(conv)
    if target is None:
        return ''
    nxt = PHASE_SEQUENCE[target]
    cur = PHASE_SEQUENCE[i]
    parts = [f'Move to “{nxt["label"]}”? Participants: {nxt["effect"]}.']
    if cur['flag']:
        parts.append(f'This closes the current phase ({cur["effect"]}).')
    parts.append('This cannot be undone here — only a site admin can change it back.')
    return ' '.join(parts)


# Guided phase transitions (#156). Keyed by the TARGET stage. Each transition lists
# the preconditions the organizer must affirm (one checkbox each) before the "Move on"
# button enables. `check` (optional) names a machine-verifiable predicate, shown met/
# unmet and enforced server-side. Behavioural flags: runs_phase6_init, auto_close,
# show_pause.
PHASE_TRANSITIONS = {
    'submission': {'preconditions': [
        {'id': 'seeds',       'label': 'Enough seed statements added (the voting loop isn’t empty)'},
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
        {'id': 'args_modded', 'label': 'I’ve reviewed all arguments and removed those against moderation expectations'},
        {'id': 'reinvite',    'label': 'I’m ready to invite participants back for the informed voting phase'},
        {'id': 'newcomers',   'label': 'I understand participants who didn’t take part earlier can join this round'},
    ]},
    'public_results': {'auto_close': True, 'preconditions': [
        {'id': 'ran_long',    'label': 'The informed voting round has run long enough / had enough participation'},
        {'id': 'public',      'label': 'I understand full aggregate results become public to everyone'},
        {'id': 'no_identity', 'label': 'I understand results won’t expose individual identities (aggregate only)'},
        {'id': 'disclosure',  'label': 'I understand participants can now begin disclosing their identities'},
        {'id': 'inform',      'label': 'I’m ready to inform participants of the results and that they may disclose'},
        {'id': 'final',       'label': 'I understand this is the final phase and closes the consultation'},
    ]},
}

# Recommended number of featured statements. Advisory only (Phase 6 needs ≥1); the
# ideal count depends on topic complexity — surfaced to the organizer as guidance.
# TODO: make this per-conversation configurable when complexity tiers land.
_RECOMMENDED_FEATURED = 15


def _check_confirmed_featured(conv):
    """Machine check for the featured-statement precondition. Returns (met, note):
    met is True when at least one is confirmed (the hard requirement); note shows the
    selected count against the recommended target so the organizer can judge coverage."""
    n = (FeaturedStatement.query
         .filter_by(conversation_id=conv.id, confirmed_by_admin=True).count())
    return n > 0, f'{n} selected, {_RECOMMENDED_FEATURED} recommended'


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
    cur = PHASE_SEQUENCE[_current_stage_index(conv)]
    nxt = PHASE_SEQUENCE[target]
    cfg = PHASE_TRANSITIONS.get(nxt['key'], {})
    preconds = []
    for p in cfg.get('preconditions', []):
        met, note = None, None
        if p.get('check'):
            met, note = _PRECONDITION_CHECKS[p['check']](conv)
        preconds.append({**p, 'met': met, 'note': note})
    # Consequence text — what opens, what closes, irreversibility.
    consequence = {
        'opens':  nxt['effect'],
        'closes': cur['effect'] if cur['flag'] else None,
        'auto_close': bool(cfg.get('auto_close')),
    }
    return {
        'target': nxt,
        'source': cur,
        'preconditions': preconds,
        'consequence': consequence,
        'runs_phase6_init': bool(cfg.get('runs_phase6_init')),
        'show_pause': bool(cfg.get('show_pause')),
        'auto_close': bool(cfg.get('auto_close')),
    }


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


def _sanitise_text(html: str) -> str:
    return nh3.clean(html or '', tags=_TEXT_ALLOWED_TAGS,
                     attributes=_TEXT_ALLOWED_ATTRS, strip_comments=True)


def _valid_polis_id(v: str) -> bool:
    return bool(_POLIS_ID_RE.match(v or ''))


def _valid_slug(v: str) -> bool:
    return bool(_SLUG_RE.match(v or ''))


def _parse_conversation_form() -> dict:
    raw_policy = request.form.get('access_policy', 'public').strip()
    return {
        'title':         request.form.get('title', '').strip(),
        'intro_text':    _sanitise_text(request.form.get('intro_text', '')),
        'outro_text':    _sanitise_text(request.form.get('outro_text', '')),
        'access_policy': raw_policy if raw_policy in ACCESS_POLICIES else 'public',
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


def _check_conversation_access(conversation, participant) -> None:
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

def _validate_same_origin():
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
    abort(403)


def _validate_fetch_csrf():
    """Validate Flask-WTF CSRF for JSON/fetch routes on the exempt proxy blueprint."""
    if not current_app.config.get('WTF_CSRF_ENABLED', True):
        return
    token = (request.headers.get('X-CSRFToken')
             or request.headers.get('X-CSRF-Token')
             or request.form.get('csrf_token'))
    try:
        validate_csrf(token)
    except ValidationError:
        abort(400)


def _proxy_to_particiapi(pa_path: str):
    """
    Proxy a browser request to Particiapi and return the response.

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
    if pa_cookie:
        forwarded_cookies['session'] = pa_cookie

    # HIGH-5: Only forward known safe query parameters to Particiapi.
    _ALLOWED_PARAMS = frozenset({'create', 'zinvite', 'conversation_id', 'tid'})
    params = {k: v for k, v in request.args.items() if k in _ALLOWED_PARAMS}
    # If the web component calls POST /api/session with no existing session,
    # Particiapi returns 403 (auth required) unless we add ?create=true.
    if pa_path == 'api/session' and request.method == 'POST' and not pa_cookie:
        params['create'] = 'true'

    headers = {}
    if request.method in ('POST', 'PUT'):
        csrf = request.headers.get('X-CSRF-Token')
        if csrf:
            headers['X-CSRF-Token'] = csrf
        if request.content_type:
            headers['Content-Type'] = request.content_type

    try:
        upstream = requests.request(
            method=request.method,
            url=url,
            params=params,
            headers=headers,
            cookies=forwarded_cookies,
            json=request.get_json(silent=True),
            data=request.form if not request.is_json else None,
            timeout=10,
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

    flask_resp = make_response(upstream.content, upstream.status_code)
    flask_resp.headers['Content-Type'] = upstream.headers.get(
        'Content-Type', 'application/json')

    if 'session' in upstream.cookies:
        flask_resp.set_cookie(
            'pa_session',
            upstream.cookies['session'],
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

    # Proposer pseudonyms: one query for all proposers across all FSs.
    all_proposer_ids = {a.proposer_id for fs in fss for a in fs.arguments
                        if a.proposer_id is not None}
    if all_proposer_ids:
        proposer_parts = Participation.query.filter(
            Participation.participant_id.in_(all_proposer_ids),
            Participation.conversation_id == conv.id,
        ).all()
        proposer_pseudonym_map = {p.participant_id: p.pseudonym for p in proposer_parts}
    else:
        proposer_pseudonym_map = {}

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
            proposer_id=pid, featured_statement_id=fs.id, side='pro').first()
        con_proposed = Argument.query.filter_by(
            proposer_id=pid, featured_statement_id=fs.id, side='con').first()

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
            'k': conv.argument_vote_data.get('K', 2),
            'pro_voted_count': pro_voted_count,
            'con_voted_count': con_voted_count,
            'proposer_pseudonyms': proposer_pseudonym_map,
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


# ── Proxy + statement-submit blueprint (issue #91, step 7) ──────────────────
# The security-sensitive cluster: both routes are CSRF-exempt with
# _validate_same_origin() as the compensating control, and both bridge the
# browser's renamed 'pa_session' cookie to Particiapi's 'session'. They live on a
# blueprint (CSRF-exempted in create_app via csrf.exempt(proxy_bp)) instead of the
# _register_routes closure. Behaviour is byte-identical to the prior inline routes.
proxy_bp = Blueprint('proxy', __name__)

@proxy_bp.post('/c/<slug>/statements/new')
@login_required
def conversation_statement_new(slug):
    """Submit an entirely new statement; enforces per-participant quota and
    records the Polis statement ID for novelty tracking."""
    # This route lives on the CSRF-exempt proxy blueprint for historical reasons,
    # so validate Flask-WTF's token manually before same-origin checks.
    _validate_fetch_csrf()
    _validate_same_origin()

    conv = Conversation.query.filter_by(slug=slug).first_or_404()
    if not conv.active or conv.paused or not conv.phase_submission:
        abort(403)
    participant = _current_participant()
    if not participant:
        abort(401)

    # Lock the participation row for the duration of this transaction to
    # prevent two concurrent requests from both passing the quota check.
    part = Participation.query.filter_by(
        participant_id=participant.id, conversation_id=conv.id,
    ).with_for_update().first_or_404()

    new_stmt_max = conv.argument_vote_data.get('new_stmt_max', 3) if conv.argument_vote_data else 3
    if len(part.new_stmt_ids or []) >= new_stmt_max:
        return jsonify({'error': 'quota_exceeded'}), 403

    body = request.get_json(silent=True) or {}
    text = (body.get('text') or '').strip()
    if not text or len(text) > 280:
        abort(400)

    # Get CSRF token for this Particiapi session, then submit the statement.
    pa_cookie = request.cookies.get('pa_session')
    forwarded = {'session': pa_cookie} if pa_cookie else {}
    base = current_app.config['PARTICIAPI_BASE']

    try:
        sess_resp = requests.post(
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

        stmt_resp = requests.post(
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
            ids = list(part.new_stmt_ids or [])
            ids.append(stmt_id)
            part.new_stmt_ids = ids
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
@login_required
def proxy_particiapi(pa_path):
    return _proxy_to_particiapi(pa_path)

admin_bp = Blueprint('admin', __name__)

# nh3 tag allowlist for CSV import sanitisation — no HTML tags permitted.
_NH3_NO_TAGS: frozenset[str] = frozenset()
participant_bp = Blueprint('participant', __name__)

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
                           )

@admin_bp.get('/admin/conversations/<int:conv_id>')
@login_required
def admin_conversation_detail(conv_id):
    conv       = _require_mod_for_conv(conv_id)
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
    polis_stats       = _polis_server_client().get_polis_stats(conv.polis_id)
    return render_template('admin_conversation.html',
                           conversation=conv,
                           conv_roles=conv_roles,
                           participants=participants,
                           invite_count=invite_count,
                           participant_count=participant_count,
                           polis_stats=polis_stats,
                           admin_roles=ADMIN_ROLES,
                           can_manage_roles=can_manage_roles,
                           phase_sequence=PHASE_SEQUENCE,
                           current_stage_index=_current_stage_index(conv),
                           linear_phase_state=_is_linear_phase_state(conv),
                           advance_target_index=_advance_target_index(conv),
                           transition=_transition_context(conv))

@admin_bp.post('/admin/conversations/new')
@login_required
@admin_required
def admin_conversation_new():
    slug   = request.form.get('slug', '').strip().lower()
    fields = _parse_conversation_form()

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

    db.session.add(Conversation(slug=slug, active=True, polis_id=polis_id, **fields))
    db.session.commit()
    return redirect(url_for('admin.admin'))

@admin_bp.post('/admin/conversations/<int:conv_id>/edit')
@login_required
@admin_required
def admin_conversation_edit(conv_id):
    conv   = Conversation.query.get_or_404(conv_id)
    fields = _parse_conversation_form()

    if not fields['title']:
        flash('Title is required.', 'error')
        return redirect(url_for('admin.admin_conversation_detail', conv_id=conv_id))

    conv.title         = fields['title']
    conv.intro_text    = fields['intro_text']
    conv.outro_text    = fields['outro_text']
    conv.access_policy = fields['access_policy']
    db.session.commit()
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
    return redirect(url_for('admin.admin_conversation_detail', conv_id=conv_id))

@admin_bp.post('/admin/conversations/<int:conv_id>/close')
@login_required
@admin_required
def admin_conversation_close(conv_id):
    conv = Conversation.query.get_or_404(conv_id)
    if not conv.active:
        abort(400)
    conv.active    = False
    conv.paused    = False
    conv.closed_at = datetime.now(timezone.utc)
    db.session.commit()
    return redirect(url_for('admin.admin_conversation_detail', conv_id=conv_id))

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

    if not _sync_vis_type(conv):
        flash('Phases saved, but updating results visibility in Polis failed — '
              'results may not appear until you save phases again.', 'error')
    return redirect(url_for('admin.admin_conversation_detail', conv_id=conv_id))


@admin_bp.post('/admin/conversations/<int:conv_id>/phase/advance')
@login_required
@admin_required                      # guided forward move — global admin (later: organizer)
def admin_conversation_advance(conv_id):
    """Guided 'Move on' phase transition (#156). The organizer must affirm every
    precondition (one checkbox each) before this is accepted; the route re-enforces
    that server-side and re-runs machine-checkable preconditions.

    Exclusive: the target stage's flag is set and the current stage's flag cleared.
    Active conversation → one step forward; closed → jump to public results. Backward
    / custom-state repair is an advanced-mode action, so a non-linear state is refused.
    The Informed-voting transition runs Phase 6 init atomically; the Public-results
    transition auto-closes the conversation (starting the identity-reveal window).
    """
    conv = Conversation.query.get_or_404(conv_id)
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

    cur, nxt = ctx['source'], ctx['target']
    if cur['flag']:                               # preparation has flag=None
        setattr(conv, cur['flag'], False)
    setattr(conv, nxt['flag'], True)

    if ctx['auto_close'] and conv.closed_at is None:
        conv.active    = False
        conv.paused    = False
        conv.closed_at = datetime.now(timezone.utc)

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

    if not _sync_vis_type(conv):
        flash('Phase moved, but updating results visibility in Polis failed.', 'error')
    if sync_msg:                                  # re-entry re-synced round 6 (#175)
        flash(sync_msg, 'warning' if 'check manually' in sync_msg else 'success')
    flash(f'Moved to: {nxt["label"]}.', 'success')
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
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash('Phase 6 was already initialised by a concurrent request.', 'error')
        return redirect(url_for('admin.admin_conversation_detail', conv_id=conv_id))
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
    return redirect(url_for('admin.admin'))

@admin_bp.post('/admin/global-admins/<int:participant_id>/remove')
@login_required
@admin_required
def admin_global_admin_remove(participant_id):
    p = Participant.query.get_or_404(participant_id)
    p.is_global_admin = False
    db.session.commit()
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
    return redirect(_safe_redirect(request.form.get('redirect_to', ''), url_for('admin.admin')))

@admin_bp.post('/admin/roles/<int:role_id>/remove')
@login_required
@admin_required
def admin_role_remove(role_id):
    role = AdminRole.query.get_or_404(role_id)
    db.session.delete(role)
    db.session.commit()
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
    existing = {inv.mw_username for inv in
                ConversationInvite.query.filter_by(conversation_id=conv_id).all()}
    for username in usernames:
        if username not in existing:
            db.session.add(ConversationInvite(
                conversation_id=conv_id, mw_username=username))
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
    return redirect(url_for('admin.admin_conversation_invites', conv_id=conv_id))

@admin_bp.post('/admin/conversations/<int:conv_id>/invites/<int:invite_id>/remove')
@login_required
def admin_invite_remove(conv_id, invite_id):
    _require_mod_for_conv(conv_id)
    invite = ConversationInvite.query.filter_by(
        id=invite_id, conversation_id=conv_id).first_or_404()
    db.session.delete(invite)
    db.session.commit()
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
    return render_template('admin_statements.html',
                           conversation=conv,
                           pending=pending,
                           approved=approved,
                           hidden=hidden,
                           settings=settings,
                           featured_tids=featured_tids,
                           phase_active=conv.phase_argument_mapping,
                           polis_public_url=current_app.config.get('POLIS_PUBLIC_URL') or 'https://pol.is',
                           max_import_rows=MAX_ROWS,
                           max_import_kb=MAX_FILE_BYTES // 1024)

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
    return redirect(url_for('admin.admin_conversation_statements', conv_id=conv_id))

@admin_bp.post('/admin/conversations/<int:conv_id>/statements/seed')
@login_required
def admin_statement_seed(conv_id):
    conv = _require_mod_for_conv(conv_id)
    text = request.form.get('txt', '').strip()
    text = nh3.clean(text, tags=frozenset())
    if not text or len(text) > 280:
        abort(400)
    try:
        _polis_server_client().add_seed(conv.polis_id, text)
        flash('Seed statement added.', 'success')
    except PolisServerError:
        current_app.logger.exception('add_seed failed')
        flash('Could not add seed statement. Check server logs for details.', 'error')
    return redirect(url_for('admin.admin_conversation_statements', conv_id=conv_id))

@admin_bp.post('/admin/conversations/<int:conv_id>/statements/seed/import')
@login_required
@limiter.limit('5 per minute')
def admin_statement_seed_import(conv_id):
    conv = _require_mod_for_conv(conv_id)
    redirect_target = url_for('admin.admin_conversation_statements', conv_id=conv_id)

    f = request.files.get('csv_file')
    if not f or not f.filename:
        flash('No file selected.', 'error')
        return redirect(redirect_target)

    if not f.filename.lower().endswith('.csv'):
        flash('Please upload a .csv file.', 'error')
        return redirect(redirect_target)

    raw = f.stream.read(MAX_FILE_BYTES + 1)
    if len(raw) > MAX_FILE_BYTES:
        flash(f'File too large — maximum is {MAX_FILE_BYTES // 1024} KB.', 'error')
        return redirect(redirect_target)

    try:
        result = parse_csv_bytes(raw)
    except ValueError as exc:
        flash(str(exc), 'import_row_error')
        flash('✗ Import failed', 'import_result')
        return redirect(redirect_target)

    # Reject if the file exceeds the row limit — partial imports are confusing.
    limit_skipped = [e for e in result.errors if e.limit_skipped]
    if limit_skipped:
        total_rows = len(result.texts) + len(result.errors)
        current_app.logger.warning(
            'CSV import rejected — row limit exceeded: %d rows, max %d (conv %s)',
            total_rows, MAX_ROWS, conv.polis_id,
        )
        flash(
            f'✗ Import rejected — file contains {total_rows} rows, maximum is {MAX_ROWS}. '
            f'Reduce the file and re-upload. '
            f'(Parse errors may also be present — fix both before re-uploading.)',
            'import_result',
        )
        return redirect(redirect_target)

    # Reject the entire batch if any row has a parse error — partial imports
    # are confusing and hard to reconcile.
    parse_errors = [e for e in result.errors if not e.limit_skipped]
    if parse_errors:
        for err in parse_errors:
            flash(f'Row {err.row}: {err.reason}.', 'import_row_error')
        flash('✗ Import rejected — fix errors and re-upload', 'import_result')
        return redirect(redirect_target)

    # Sanitize all texts with nh3 first, then re-strip formula prefixes that
    # HTML-entity encoding could have reintroduced (e.g. &equals; → =).
    # Filter empty strings that result from nh3 stripping all-tag content.
    seen_sanitised: set[str] = set()
    sanitised_texts: list[str] = []
    for raw_text in result.texts:
        san = nh3.clean(raw_text, tags=_NH3_NO_TAGS)
        # Re-apply formula-prefix stripping: nh3 decodes HTML entities (e.g.
        # &equals; → =) which can reintroduce leading formula chars.
        san = strip_formula_prefixes(san).strip()
        if not san or san in seen_sanitised:
            continue  # drop empty-after-nh3 and nh3-induced within-batch dupes
        seen_sanitised.add(san)
        sanitised_texts.append(san)

    # Check for duplicates against statements already in Polis.
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
    clean_texts  = []
    for sanitised in sanitised_texts:
        if sanitised.casefold() in existing_texts:
            dedup_errors.append(f'"{sanitised[:60]}{"…" if len(sanitised) > 60 else ""}" — already exists in this conversation')
        else:
            clean_texts.append(sanitised)

    successes     = 0
    polis_skipped = []  # Polis rejected these — likely already exist
    polis_errors  = []  # Polis login or unexpected failure
    if clean_texts:
        try:
            successes, failures = _polis_server_client().bulk_add_seeds(conv.polis_id, clean_texts)
            for text, exc in failures:
                current_app.logger.warning('Polis rejected imported row (%s, may already exist): %s',
                                           type(exc).__name__, exc)
                polis_skipped.append(f'"{text[:60]}{"…" if len(text) > 60 else ""}"')
        except PolisServerError:
            current_app.logger.exception('Polis login failed during bulk import')
            polis_errors = [f'"{t[:60]}{"…" if len(t) > 60 else ""}"' for t in clean_texts]

    if dedup_check_failed:
        flash('Could not check for existing statements — some may be duplicates. Check server logs.', 'warning')

    for msg in dedup_errors:
        flash(f'Skipped — {msg}.', 'warning')
    for msg in polis_skipped:
        flash(f'Already in Polis, skipped: {msg}.', 'warning')
    for msg in polis_errors:
        flash(f'Could not send to Polis: {msg}.', 'error')
    if not successes and not result.errors and not dedup_errors and not polis_skipped and not polis_errors:
        flash('No statements were imported — the file had no valid rows.', 'warning')

    # Persistent inline result near the upload button.
    n_skipped = len(dedup_errors) + len(polis_skipped)
    n_errors   = len(polis_errors)
    # Note: polis_errors is only set in the except-PolisServerError branch, which
    # means successes == 0 whenever polis_errors is non-empty. The two cannot
    # coexist; n_errors is checked last to keep the ladder exhaustive.
    if successes and not n_skipped:
        flash(f'✓ {successes} statement{"s" if successes != 1 else ""} imported', 'import_result')
    elif successes:
        flash(f'✓ {successes} imported — ⚠ {n_skipped} skipped', 'import_result')
    elif n_errors:
        flash('✗ Import failed — could not reach Polis. Check server logs.', 'import_result')
    elif n_skipped:
        flash(f'⚠ 0 imported — {n_skipped} already existed in Polis', 'import_result')
    else:
        flash('⚠ 0 imported — Polis returned no result', 'import_result')

    return redirect(redirect_target)

@admin_bp.post('/admin/conversations/<int:conv_id>/strict-moderation')
@login_required
def admin_conversation_strict_moderation(conv_id):
    conv    = _require_mod_for_conv(conv_id)
    enabled = request.form.get('strict_moderation') == '1'
    try:
        _polis_server_client().set_strict_moderation(conv.polis_id, enabled)
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
    return render_template('admin_featured.html',
                           conversation=conv,
                           confirmed=confirmed,
                           candidates=candidates,
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
        db.session.commit()
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
        db.session.commit()
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
    db.session.commit()
    return redirect(url_for('admin.admin_conversation_featured', conv_id=conv_id))

@admin_bp.post('/admin/conversations/<int:conv_id>/arguments/<int:arg_id>/delete')
@login_required
def admin_argument_delete(conv_id, arg_id):
    conv = _require_mod_for_conv(conv_id)
    arg  = Argument.query.filter_by(id=arg_id).first_or_404()
    FeaturedStatement.query.filter_by(
        id=arg.featured_statement_id, conversation_id=conv.id).first_or_404()
    db.session.delete(arg)
    db.session.commit()
    return redirect(url_for('admin.admin_conversation_featured', conv_id=conv_id))


# ── Accept ───────────────────────────────────────────────────────────────

@participant_bp.get('/accept/<slug>')
@login_required
def accept(slug):
    conv        = Conversation.query.filter_by(slug=slug).first_or_404()
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

    db.session.add(Participation(
        participant_id=participant.id,
        conversation_id=conv.id,
        pseudonym=pseudonym,
        notify_email=bool(request.form.get('notify_email')) and emailable,
        notify_talk_page=bool(request.form.get('notify_talk_page')),
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
@login_required
def conversation(slug):
    conv        = Conversation.query.filter_by(slug=slug).first_or_404()
    participant = _current_participant()
    _check_conversation_access(conv, participant)

    participation = None
    if participant:
        participation = Participation.query.filter_by(
            participant_id=participant.id,
            conversation_id=conv.id,
        ).first()

    if participation is None:
        return redirect(url_for('participant.accept', slug=slug))

    can_mod = _can_moderate(conv, participant)

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

    # Reveal window state for closed conversations.
    reveal_state    = None
    reveal_opens_at = None
    if conv.closed_at:
        age = datetime.now(timezone.utc) - conv.closed_at.replace(tzinfo=timezone.utc)
        reveal_opens_at = conv.closed_at + timedelta(days=_REVEAL_COOLDOWN_DAYS)
        if participation.public_username:
            reveal_state = 'revealed'
        elif age >= timedelta(days=_REVEAL_COOLDOWN_DAYS + _REVEAL_WINDOW_DAYS):
            reveal_state = 'expired'
        elif age >= timedelta(days=_REVEAL_COOLDOWN_DAYS):
            reveal_state = 'open'
        else:
            reveal_state = 'pending'

    featured_data = []
    if conv.phase_argument_mapping and participation:
        featured_data = _build_featured_data(conv, participation, can_mod=can_mod)

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

    return render_template('conversation.html',
                           conversation=conv,
                           participation=participation,
                           can_moderate=can_mod,
                           results=results,
                           recomputing=recomputing,
                           polis_stats=polis_stats,
                           reveal_state=reveal_state,
                           reveal_opens_at=reveal_opens_at,
                           featured_data=featured_data,
                           new_stmt_unlock_at=conv.argument_vote_data.get('new_stmt_unlock_at', 10) if conv.argument_vote_data else 10,
                           new_stmt_max=conv.argument_vote_data.get('new_stmt_max', 3) if conv.argument_vote_data else 3,
                           new_stmt_ids=participation.new_stmt_ids if participation else [],
                           phase6_data=phase6_data)

# ── Arguments ────────────────────────────────────────────────────────────

@participant_bp.post('/c/<slug>/arguments/<int:fs_id>/submit')
@login_required
def argument_submit(slug, fs_id):
    conv, part = _require_arg_participation(slug)
    FeaturedStatement.query.filter_by(
        id=fs_id, conversation_id=conv.id).first_or_404()
    side = request.form.get('side', '').strip()
    body = nh3.clean(request.form.get('body', '').strip(), tags=frozenset())
    if side not in ('pro', 'con') or not body or len(body) > 280:
        abort(400)

    existing = Argument.query.filter_by(
        proposer_id=part.participant_id,
        featured_statement_id=fs_id,
        side=side,
    ).first()
    if existing:
        if request.headers.get('X-Requested-With') == 'fetch':
            return jsonify({'ok': True, 'id': existing.id, 'body': existing.body})
        return redirect(url_for('participant.conversation', slug=slug) + '#tab-arguments')

    arg = Argument(
        featured_statement_id=fs_id,
        proposer_id=part.participant_id,
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

    db.session.commit()
    if request.headers.get('X-Requested-With') == 'fetch':
        return jsonify({'ok': True, 'id': arg.id, 'body': body})
    return redirect(url_for('participant.conversation', slug=slug) + '#tab-arguments')

@participant_bp.post('/c/<slug>/arguments/<int:fs_id>/<side>/skip')
@login_required
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
        db.session.commit()
    elif not state.skipped:
        state.skipped = True
        db.session.commit()
    if request.headers.get('X-Requested-With') == 'fetch':
        return jsonify({'ok': True})
    return redirect(url_for('participant.conversation', slug=slug) + '#tab-arguments')

@participant_bp.post('/c/<slug>/arguments/<int:arg_id>/vote')
@login_required
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
        proposer_id=part.participant_id,
        featured_statement_id=fs.id, side='pro').first()
    con_proposed = Argument.query.filter_by(
        proposer_id=part.participant_id,
        featured_statement_id=fs.id, side='con').first()
    pro_gate = bool(pro_proposed or (pro_state and pro_state.skipped))
    con_gate = bool(con_proposed or (con_state and con_state.skipped))
    is_ajax = request.headers.get('X-Requested-With') == 'fetch'
    if not (pro_gate and con_gate):
        if is_ajax:
            return jsonify({'ok': False, 'reason': 'gate'}), 403
        abort(403)

    # K-approval cap: count existing votes for this side.
    k = conv.argument_vote_data.get('K', 2)
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

    # Can't vote on hidden or own argument.
    if arg.hidden:
        if is_ajax:
            return jsonify({'ok': False, 'reason': 'hidden'}), 403
        abort(403)
    if arg.proposer_id == part.participant_id:
        if is_ajax:
            return jsonify({'ok': False, 'reason': 'own'}), 403
        abort(403)

    existing = ArgumentVote.query.filter_by(
        participant_id=part.participant_id, argument_id=arg_id).first()
    if not existing:
        db.session.add(ArgumentVote(
            argument_id=arg_id,
            participant_id=part.participant_id,
        ))
        db.session.commit()
    if is_ajax:
        return jsonify({'ok': True})
    return redirect(url_for('participant.conversation', slug=slug) + '#tab-arguments')

@participant_bp.post('/c/<slug>/arguments/<int:arg_id>/unvote')
@login_required
def argument_unvote(slug, arg_id):
    conv, part = _require_arg_participation(slug)
    arg = Argument.query.filter_by(id=arg_id).first_or_404()
    FeaturedStatement.query.filter_by(
        id=arg.featured_statement_id, conversation_id=conv.id).first_or_404()
    existing = ArgumentVote.query.filter_by(
        participant_id=part.participant_id, argument_id=arg_id).first()
    if existing:
        db.session.delete(existing)
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

    age = datetime.now(timezone.utc) - conv.closed_at.replace(tzinfo=timezone.utc)
    opens_at = conv.closed_at + timedelta(days=_REVEAL_COOLDOWN_DAYS)
    return render_template('reveal.html',
                           conversation=conv,
                           participation=participation,
                           window_open=age >= timedelta(days=_REVEAL_COOLDOWN_DAYS),
                           window_closed=age >= timedelta(days=_REVEAL_COOLDOWN_DAYS + _REVEAL_WINDOW_DAYS),
                           opens_at=opens_at)

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

    age = datetime.now(timezone.utc) - conv.closed_at.replace(tzinfo=timezone.utc)
    if age < timedelta(days=_REVEAL_COOLDOWN_DAYS):
        abort(400)
    if age >= timedelta(days=_REVEAL_COOLDOWN_DAYS + _REVEAL_WINDOW_DAYS):
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
@login_required
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

    # Ensure a stable Polis session and CSRF token before voting.
    # Mirrors the exact pattern used in conversation_statement_new.
    pa_cookie = request.cookies.get('pa_session')
    base = current_app.config['PARTICIAPI_BASE']
    forwarded = {'session': pa_cookie} if pa_cookie else {}
    new_pa_cookie = None
    try:
        sess_resp = requests.post(
            f'{base}/api/session',
            cookies=forwarded,
            params={'create': 'true'},
            timeout=5,
        )
        if not sess_resp.ok:
            current_app.logger.error('Particiapi session error in phase6_vote: %s',
                                     sess_resp.status_code)
            abort(502)
        csrf_token    = sess_resp.json().get('csrf_token', '')
        new_pa_cookie = sess_resp.cookies.get('session')
    except requests.RequestException:
        current_app.logger.exception('Particiapi session bootstrap failed in phase6_vote')
        abort(502)

    vote_cookies = {'session': new_pa_cookie or pa_cookie} if (new_pa_cookie or pa_cookie) else {}

    # Particiapi vote endpoint: PUT /api/conversations/{id}/votes/{tid} with {value: N}
    # (matches particiapp-web-client.js line 840-841)
    try:
        upstream = requests.put(
            f'{base}/api/conversations/{polis_conv_id}/votes/{tid}',
            json={'value': vote},
            cookies=vote_cookies,
            headers={'X-CSRF-Token': csrf_token},
            timeout=10,
        )
    except requests.RequestException:
        current_app.logger.exception('Particiapi error in phase6_vote')
        abort(502)

    resp = make_response('', upstream.status_code)
    if new_pa_cookie:
        resp.set_cookie('pa_session', new_pa_cookie, httponly=True,
                        samesite='Lax', secure=not current_app.debug)
    return resp


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
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SQLALCHEMY_ENGINE_OPTIONS']      = {'pool_recycle': 280, 'pool_pre_ping': True}

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
    app.config['POLIS_DATABASE_URL'] = (_read_secret('polis-database-url')
                                        or os.environ.get('POLIS_DATABASE_URL', ''))
    app.config['POLIS_SERVER_URL']   = (_read_secret('polis-server-url')
                                        or os.environ.get('POLIS_SERVER_URL', ''))
    app.config['POLIS_ADMIN_EMAIL']  = (_read_secret('polis-admin-email')
                                        or os.environ.get('POLIS_ADMIN_EMAIL', ''))
    app.config['POLIS_ADMIN_PASSWORD'] = (_read_secret('polis-admin-password')
                                          or os.environ.get('POLIS_ADMIN_PASSWORD', ''))

    # Apply test overrides before extensions are initialised so SESSION_TYPE,
    # SQLALCHEMY_DATABASE_URI, etc. are effective from the first db.init_app call.
    if test_config is not None:
        app.config.update(test_config)

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

    @app.before_request
    def _set_csp_nonce():
        g.csp_nonce = secrets.token_urlsafe(16)

    @app.context_processor
    def _inject_globals():
        participant = _current_participant()
        return {
            'is_admin':   _is_global_admin(participant),
            'username':   session.get('username'),
            'csp_nonce':  g.get('csp_nonce', ''),
            'git_version': _GIT_VERSION,
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

    # Proxy + statement-submit blueprint (#91). Both routes are CSRF-exempt with
    # _validate_same_origin() as the compensating control; exempt the whole
    # blueprint explicitly rather than per-route.
    app.register_blueprint(proxy_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(participant_bp)
    csrf.exempt(proxy_bp)

    return app


# ── Routes ────────────────────────────────────────────────────────────────────

def _register_routes(app: Flask) -> None:

    _dev_login_user = os.environ.get('DEV_LOGIN_USER', '').strip()
    _on_toolforge   = bool(os.environ.get('TOOL_TOOLFORGE_API_URL'))

    if app.debug:
        import pathlib
        from flask import send_file as _send_file

        # Resolve particiapp-web-components.js once at startup.
        # Default: sibling repo layout (particiapp-docker/ next to wiki-polis/).
        # Override with PARTICIAPP_WEB_COMPONENTS=/abs/path/to/file.js in .env.
        _WC_DEFAULT = (pathlib.Path(__file__).parent.parent.parent /
                       'particiapp-docker/subprojects'
                       '/particiapp-web-components/particiapp-web-components.js')
        _WC_PATH = pathlib.Path(
            os.environ.get('PARTICIAPP_WEB_COMPONENTS', str(_WC_DEFAULT))
        ).resolve()

        @app.before_request
        def _dev_serve_webcomponents():
            if request.path == '/static/particiapp-web-components.js':
                if _WC_PATH.exists():
                    return _send_file(_WC_PATH, mimetype='application/javascript')
                app.logger.warning(
                    'particiapp-web-components.js not found at %s — '
                    'set PARTICIAPP_WEB_COMPONENTS in .env', _WC_PATH)

    if app.debug and _dev_login_user and not _on_toolforge:
        @app.get('/dev-login')
        @limiter.limit('20 per minute')
        def dev_login():
            username = _dev_login_user
            xid = hashlib.sha256(f'dev-{username}'.encode()).hexdigest()
            participant = Participant.query.filter_by(mw_username=username).first()
            if participant is None:
                participant = Participant(
                    mw_user_id=abs(hash(username)) % 10**9,
                    mw_username=username,
                    xid=xid,
                )
                db.session.add(participant)
            else:
                participant.xid = xid
            db.session.commit()
            session['username']  = username
            session['xid']       = xid
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
    app.config['DEV_TEST_USERS'] = _DEV_TEST_USERS if _fake_login_enabled else []

    if _fake_login_enabled:
        @app.get('/dev/login/<username>')
        @limiter.limit('30 per minute')
        def dev_fake_login(username):
            user = next((u for u in _DEV_TEST_USERS if u['username'] == username), None)
            if user is None:
                return 'Unknown test user', 404
            xid = hashlib.sha256(f'dev-fake-{username}'.encode()).hexdigest()
            participant = Participant.query.filter_by(mw_user_id=user['mw_user_id']).first()
            if participant is None:
                participant = Participant(
                    mw_user_id=user['mw_user_id'],
                    mw_username=username,
                    xid=xid,
                )
                db.session.add(participant)
            else:
                participant.mw_username = username
                participant.xid = xid
            db.session.commit()
            session['username']  = username
            session['xid']       = xid
            session['emailable'] = False
            return redirect(url_for('index'))

    # ── Home ─────────────────────────────────────────────────────────────────

    @app.get('/')
    def index():
        dev_test_users = current_app.config.get('DEV_TEST_USERS', [])
        if 'username' not in session:
            public_convos = (Conversation.query
                             .filter_by(active=True, paused=False, access_policy='public')
                             .order_by(Conversation.created_at.desc())
                             .all())
            return render_template('home.html',
                                   public_conversations=public_convos,
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

        active_joined   = []
        archived_joined = []
        for part in joined_parts:
            conv = part.conversation
            if conv:
                (active_joined if conv.active else archived_joined).append(conv)

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
                     .order_by(Conversation.created_at.desc())
                     .all())

        moderating = []
        if participant:
            if _is_global_admin(participant):
                moderating = (Conversation.query
                              .order_by(Conversation.created_at.desc()).all())
            else:
                roles = AdminRole.query.filter(
                    AdminRole.participant_id == participant.id,
                ).all()
                if roles:
                    mod_ids = {r.conversation_id for r in roles}
                    moderating = Conversation.query.filter(
                        Conversation.id.in_(mod_ids)).all()

        # keyed by conversation_id, scoped to current user only
        # assumes at most one Participation per (user, conversation) — last row wins if duplicates exist
        pseudonym_map = {p.conversation_id: p for p in joined_parts}
        return render_template('home.html',
                               active_joined=active_joined,
                               archived_joined=archived_joined,
                               available=available,
                               moderating=moderating,
                               pseudonym_map=pseudonym_map,
                               dev_test_users=dev_test_users)


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

        xid = hashlib.sha256(str(mw_user_id).encode()).hexdigest()

        participant = Participant.query.filter_by(mw_user_id=mw_user_id).first()
        if participant is None:
            participant = Participant(mw_user_id=mw_user_id, mw_username=username, xid=xid)
            db.session.add(participant)
        elif participant.mw_username != username:
            participant.mw_username = username
        if participant.xid != xid:
            participant.xid = xid
        db.session.commit()

        next_url = session.pop('next', None)
        session.clear()
        session['username']   = username
        session['xid']        = xid
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

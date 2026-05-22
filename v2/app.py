"""
app.py — Flask application for wiki-polis v2.
"""

import base64
import click
import functools
import hashlib
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode, urlparse, urljoin

import coolname
import nh3
import requests
from dotenv import load_dotenv
from flask import (Flask, abort, current_app, g, jsonify, make_response,
                   redirect, render_template, request, session, url_for)
from flask_migrate import Migrate
from flask_session import Session
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from db import (ACCESS_POLICIES, ADMIN_ROLES, AdminRole, Argument, ArgumentSideState,
                ArgumentVote, Conversation, ConversationInvite, FeaturedStatement,
                Participant, Participation, db)
from polis_admin import (PolisAdminClient, PolisAdminError, PolisServerClient,
                         PolisServerError, get_featured_candidates, get_polis_stats)

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))

_MW_USER_AGENT   = 'wiki-polis/2.0 (Toolforge tool; https://wiki-polis.toolforge.org)'
_TEXT_ALLOWED_TAGS  = {'p', 'strong', 'em', 'a', 'ul', 'ol', 'li', 'br'}
_TEXT_ALLOWED_ATTRS = {'a': {'href', 'title'}}
_POLIS_ID_RE     = re.compile(r'^[A-Za-z0-9]{6,20}$')
_SLUG_RE         = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')
_PSEUDONYM_RE    = re.compile(r'^[a-z]{2,20}-[a-z]{2,20}$')


def _read_secret(name: str) -> str:
    """Read from /run/secrets/wiki-polis/<name> (Kubernetes) or fall back to env var."""
    file_path = f'/run/secrets/wiki-polis/{name}'
    if os.path.exists(file_path):
        with open(file_path) as f:
            return f.read().strip()
    return os.environ.get(name.upper().replace('-', '_'), '')


ADMIN_USERS = [u.strip() for u in _read_secret('admin-users').split(',') if u.strip()]

_REVEAL_COOLDOWN_DAYS = 30   # days after close before reveal window opens
_REVEAL_NULLIFY_DAYS  = 30   # days after window opens before nullification (total = cooldown + nullify)


def _nullify_expired_reveals(conv: 'Conversation') -> None:
    """Clear public_username / revealed_at for all participations once past internal deadline."""
    if not conv.closed_at:
        return
    # closed_at is stored as naive UTC
    age = datetime.now(timezone.utc) - conv.closed_at.replace(tzinfo=timezone.utc)
    if age < timedelta(days=_REVEAL_COOLDOWN_DAYS + _REVEAL_NULLIFY_DAYS):
        return
    stale = (Participation.query
             .filter_by(conversation_id=conv.id)
             .filter(Participation.public_username.isnot(None))
             .all())
    for p in stale:
        p.public_username = None
        p.revealed_at     = None
    if stale:
        db.session.commit()


csrf    = CSRFProtect()
# No global default — limits applied per endpoint only.
# On multi-worker deployments configure RATELIMIT_STORAGE_URI=redis://... in env.
limiter = Limiter(key_func=get_remote_address, default_limits=[])


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
    username = session.get('username')
    if not username:
        g.participant = None
        return None
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
        abort(403)


# ── Particiapi proxy ──────────────────────────────────────────────────────────

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
        sec_fetch = request.headers.get('Sec-Fetch-Site')
        if sec_fetch:
            if sec_fetch != 'same-origin':
                abort(403)
        else:
            origin = request.headers.get('Origin')
            if origin and urlparse(origin).netloc != urlparse(request.host_url).netloc:
                abort(403)

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
    except requests.RequestException as exc:
        current_app.logger.error('Particiapi proxy error: %s', exc)
        abort(502)

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
    _polis_public_url = (_read_secret('polis-public-url')
                         or os.environ.get('POLIS_PUBLIC_URL', ''))
    if _polis_public_url and not _polis_public_url.startswith('https://'):
        app.logger.warning('POLIS_PUBLIC_URL is not https:// — ignoring')
        _polis_public_url = ''
    app.config['POLIS_PUBLIC_URL'] = _polis_public_url
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

    db.init_app(app)
    Migrate(app, db)
    Session(app)
    csrf.init_app(app)
    limiter.init_app(app)

    if not app.debug and not os.environ.get('RATELIMIT_STORAGE_URI'):
        app.logger.warning(
            'RATELIMIT_STORAGE_URI not set — rate limits are per-worker and '
            'ineffective on multi-replica deployments. Set RATELIMIT_STORAGE_URI=redis://...'
        )

    @app.cli.command('init-db')
    def init_db_cmd():
        """Initialise or migrate the database. Idempotent.

        Fresh DB: creates all tables via SQLAlchemy then stamps Alembic at head
        (the incremental migrations assume a base schema already exists).
        Existing DB: runs any pending Alembic migrations.
        """
        import sqlalchemy as _sa
        from flask_migrate import upgrade as _upgrade
        from alembic.config import Config as _AlembicConfig
        from alembic import command as _alembic_cmd
        inspector = _sa.inspect(db.engine)
        # Check for an app-specific table to distinguish a truly fresh DB
        # from one that only has the alembic_version tracking table.
        if 'participants' not in inspector.get_table_names():
            db.create_all()
            # Stamp without running migrations: build config from Flask-Migrate.
            from flask_migrate import Migrate as _Migrate
            migrate_ext = app.extensions.get('migrate')
            alembic_cfg = migrate_ext.migrate.get_config()
            _alembic_cmd.stamp(alembic_cfg, 'head')
            click.echo('Fresh database created and stamped at head.')
        else:
            _upgrade()
            click.echo('Database is at head revision.')

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
        return response

    _register_routes(app)
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
                db.session.commit()
            session['username']  = username
            session['xid']       = xid
            session['emailable'] = _is_emailable(username)
            return redirect(url_for('index'))

    # ── Home ─────────────────────────────────────────────────────────────────

    @app.get('/')
    def index():
        if 'username' not in session:
            public_convos = (Conversation.query
                             .filter_by(active=True, paused=False, access_policy='public')
                             .order_by(Conversation.created_at.desc())
                             .all())
            return render_template('home.html', public_conversations=public_convos)

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

        return render_template('home.html',
                               active_joined=active_joined,
                               archived_joined=archived_joined,
                               available=available,
                               moderating=moderating)

    # ── Accept ───────────────────────────────────────────────────────────────

    @app.get('/accept/<slug>')
    @login_required
    def accept(slug):
        conv        = Conversation.query.filter_by(slug=slug).first_or_404()
        participant = _current_participant()
        _check_conversation_access(conv, participant)
        if participant and Participation.query.filter_by(
                participant_id=participant.id,
                conversation_id=conv.id).first():
            return redirect(url_for('conversation', slug=slug))
        pseudonyms = _generate_pseudonyms(5)
        emailable  = session.get('emailable', False)
        return render_template('accept.html', conversation=conv,
                               emailable=emailable, pseudonyms=pseudonyms,
                               reveal_cooldown=_REVEAL_COOLDOWN_DAYS,
                               reveal_window_end=_REVEAL_COOLDOWN_DAYS + _REVEAL_NULLIFY_DAYS,
                               retention_public_days=120)

    @app.post('/accept/<slug>')
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
            return redirect(url_for('conversation', slug=slug))

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
        return redirect(url_for('conversation', slug=slug))

    @app.get('/accept/<slug>/pseudonyms')
    @login_required
    @limiter.limit('30 per minute')
    def accept_pseudonyms(slug):
        Conversation.query.filter_by(slug=slug).first_or_404()
        return jsonify({'pseudonyms': _generate_pseudonyms(5)})

    # ── Argument helpers ──────────────────────────────────────────────────────

    def _get_or_create_side_state(participant_id, fs_id, side, current_args):
        """Return ArgumentSideState, creating it on first view.

        On creation: randomise argument_order from current_args.
        On subsequent views: append any new arguments at a random position.
        Commits to DB if any change is made.
        """
        import random
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

    def _build_featured_data(conv, participation, can_mod=False):
        """Return list of dicts for the argument tab, one per confirmed FS.

        Each dict: {fs, text, pro_args, con_args, pro_state, con_state, voted_ids,
                    pro_gate, con_gate}
        Creates/updates ArgumentSideState records as a side effect.
        Moderators see hidden arguments (marked); participants never see them.
        """
        from sqlalchemy.orm import joinedload
        fss = (FeaturedStatement.query
               .filter_by(conversation_id=conv.id, confirmed_by_admin=True)
               .options(joinedload(FeaturedStatement.arguments))
               .order_by(FeaturedStatement.created_at)
               .all())
        if not fss:
            return []

        stmt_texts = {}
        try:
            client = PolisAdminClient(current_app.config['PARTICIAPI_BASE'])
            _, approved, _ = client.get_statements(conv.polis_id)
            stmt_texts = {s['tid']: s.get('txt', '') for s in approved}
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

            result.append({
                'fs':        fs,
                'text':      stmt_texts.get(fs.polis_statement_id)
                             or fs.statement_text
                             or f'Statement #{fs.polis_statement_id}',
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
        return result

    # ── Conversation ─────────────────────────────────────────────────────────

    @app.get('/c/<slug>')
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
            return redirect(url_for('accept', slug=slug))

        # Lazy nullification: clear identity links past the internal retention deadline.
        if conv.closed_at:
            _nullify_expired_reveals(conv)
            db.session.refresh(participation)

        can_mod = _can_moderate(conv, participant)

        results     = None
        polis_stats = None
        if conv.phase_public_results:
            client      = PolisAdminClient(current_app.config['PARTICIAPI_BASE'])
            results     = client.get_results(conv.polis_id)
            polis_stats = get_polis_stats(conv.polis_id,
                                          current_app.config['POLIS_DATABASE_URL'])

        # Reveal window state for closed conversations.
        reveal_state    = None
        reveal_opens_at = None
        if conv.closed_at:
            age = datetime.now(timezone.utc) - conv.closed_at.replace(tzinfo=timezone.utc)
            reveal_opens_at = conv.closed_at + timedelta(days=_REVEAL_COOLDOWN_DAYS)
            if participation.public_username:
                reveal_state = 'revealed'
            elif age >= timedelta(days=_REVEAL_COOLDOWN_DAYS + _REVEAL_NULLIFY_DAYS):
                reveal_state = 'expired'
            elif age >= timedelta(days=_REVEAL_COOLDOWN_DAYS):
                reveal_state = 'open'
            else:
                reveal_state = 'pending'

        featured_data = []
        if conv.phase_argument_mapping and participation:
            featured_data = _build_featured_data(conv, participation, can_mod=can_mod)

        return render_template('conversation.html',
                               conversation=conv,
                               participation=participation,
                               can_moderate=can_mod,
                               results=results,
                               polis_stats=polis_stats,
                               polis_public_url=current_app.config.get('POLIS_PUBLIC_URL', ''),
                               reveal_state=reveal_state,
                               reveal_opens_at=reveal_opens_at,
                               featured_data=featured_data)

    # ── Arguments ────────────────────────────────────────────────────────────

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

    @app.post('/c/<slug>/arguments/<int:fs_id>/submit')
    @login_required
    def argument_submit(slug, fs_id):
        conv, part = _require_arg_participation(slug)
        fs   = FeaturedStatement.query.filter_by(
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
            return redirect(url_for('conversation', slug=slug) + '#tab-arguments')

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
        import random
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
        return redirect(url_for('conversation', slug=slug) + '#tab-arguments')

    @app.post('/c/<slug>/arguments/<int:fs_id>/<side>/skip')
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
        return redirect(url_for('conversation', slug=slug) + '#tab-arguments')

    @app.post('/c/<slug>/arguments/<int:arg_id>/vote')
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
        return redirect(url_for('conversation', slug=slug) + '#tab-arguments')

    @app.post('/c/<slug>/arguments/<int:arg_id>/unvote')
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
        return redirect(url_for('conversation', slug=slug) + '#tab-arguments')

    @app.post('/c/<slug>/arguments/<int:arg_id>/delete')
    @login_required
    def argument_delete(slug, arg_id):
        conv = Conversation.query.filter_by(slug=slug).first_or_404()
        if not _can_moderate(conv):
            abort(403)
        arg = Argument.query.filter_by(id=arg_id).first_or_404()
        FeaturedStatement.query.filter_by(
            id=arg.featured_statement_id, conversation_id=conv.id).first_or_404()
        db.session.delete(arg)
        db.session.commit()
        return redirect(url_for('conversation', slug=slug) + '#tab-arguments')

    @app.post('/c/<slug>/arguments/<int:arg_id>/hide')
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
        return redirect(url_for('conversation', slug=slug) + '#tab-arguments')

    @app.post('/c/<slug>/arguments/<int:arg_id>/unhide')
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
        return redirect(url_for('conversation', slug=slug) + '#tab-arguments')

    # ── Particiapi proxy ──────────────────────────────────────────────────────

    @app.route('/proxy/particiapi/<path:pa_path>',
               methods=['GET', 'POST', 'PUT'])
    @login_required
    @csrf.exempt
    def proxy_particiapi(pa_path):
        return _proxy_to_particiapi(pa_path)

    # ── Identity reveal ───────────────────────────────────────────────────────

    @app.get('/c/<slug>/reveal')
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

        _nullify_expired_reveals(conv)
        db.session.refresh(participation)

        age = datetime.now(timezone.utc) - conv.closed_at.replace(tzinfo=timezone.utc)
        opens_at = conv.closed_at + timedelta(days=_REVEAL_COOLDOWN_DAYS)
        return render_template('reveal.html',
                               conversation=conv,
                               participation=participation,
                               window_open=age >= timedelta(days=_REVEAL_COOLDOWN_DAYS),
                               window_closed=age >= timedelta(days=_REVEAL_COOLDOWN_DAYS + _REVEAL_NULLIFY_DAYS),
                               opens_at=opens_at)

    @app.post('/c/<slug>/reveal')
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
        if age >= timedelta(days=_REVEAL_COOLDOWN_DAYS + _REVEAL_NULLIFY_DAYS):
            abort(400)
        if participation.public_username is not None:
            abort(400)
        if request.form.get('confirm') != '1':
            return redirect(url_for('reveal_identity', slug=slug))

        participation.public_username = participant.mw_username
        participation.revealed_at     = datetime.now(timezone.utc)
        db.session.commit()
        return redirect(url_for('conversation', slug=slug))

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
            app.logger.warning('OAuth callback: state mismatch')
            abort(400)

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
        return redirect(url_for('login'))

    # ── Admin ─────────────────────────────────────────────────────────────────

    @app.get('/admin')
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
                               admin_error=request.args.get('error'))

    @app.get('/admin/conversations/<int:conv_id>')
    @login_required
    def admin_conversation_detail(conv_id):
        conv        = _require_mod_for_conv(conv_id)
        participant = _current_participant()
        conv_roles  = (AdminRole.query
                       .filter_by(conversation_id=conv_id)
                       .all())
        participants      = Participant.query.order_by(Participant.mw_username).all()
        invite_count      = ConversationInvite.query.filter_by(conversation_id=conv_id).count()
        participant_count = Participation.query.filter_by(conversation_id=conv_id).count()
        polis_stats       = get_polis_stats(conv.polis_id,
                                            current_app.config['POLIS_DATABASE_URL'])
        return render_template('admin_conversation.html',
                               conversation=conv,
                               conv_roles=conv_roles,
                               participants=participants,
                               invite_count=invite_count,
                               participant_count=participant_count,
                               polis_stats=polis_stats,
                               polis_public_url=current_app.config.get('POLIS_PUBLIC_URL', ''),
                               admin_roles=ADMIN_ROLES)

    @app.post('/admin/conversations/new')
    @login_required
    @admin_required
    def admin_conversation_new():
        slug   = request.form.get('slug', '').strip().lower()
        fields = _parse_conversation_form()

        if not fields['title'] or not _valid_slug(slug):
            abort(400)

        polis_url      = current_app.config.get('POLIS_SERVER_URL', '')
        polis_email    = current_app.config.get('POLIS_ADMIN_EMAIL', '')
        polis_password = current_app.config.get('POLIS_ADMIN_PASSWORD', '')

        if polis_url and polis_email and polis_password:
            try:
                client   = PolisServerClient(polis_url, polis_email, polis_password)
                polis_id = client.create_conversation(fields['title'])
            except PolisServerError as exc:
                current_app.logger.error('Polis conversation creation failed: %s', exc)
                return redirect(url_for('admin', error=f'Could not create Polis conversation: {exc}'))
        else:
            # Fallback: accept manually supplied polis_id (local dev / misconfigured prod)
            polis_id = request.form.get('polis_id', '').strip()
            if not _valid_polis_id(polis_id):
                return redirect(url_for('admin', error=(
                    'POLIS_SERVER_URL / POLIS_ADMIN_EMAIL / POLIS_ADMIN_PASSWORD not configured. '
                    'Pass a polis_id manually or set the env vars.'
                )))

        db.session.add(Conversation(slug=slug, active=True, polis_id=polis_id, **fields))
        db.session.commit()
        return redirect(url_for('admin'))

    @app.post('/admin/conversations/<int:conv_id>/edit')
    @login_required
    @admin_required
    def admin_conversation_edit(conv_id):
        conv   = Conversation.query.get_or_404(conv_id)
        fields = _parse_conversation_form()

        if not fields['title']:
            abort(400)

        conv.title         = fields['title']
        conv.intro_text    = fields['intro_text']
        conv.outro_text    = fields['outro_text']
        conv.access_policy = fields['access_policy']
        db.session.commit()
        return redirect(url_for('admin_conversation_detail', conv_id=conv_id))

    @app.post('/admin/conversations/<int:conv_id>/pause')
    @login_required
    @admin_required
    def admin_conversation_pause(conv_id):
        conv = Conversation.query.get_or_404(conv_id)
        if not conv.active:
            abort(400)
        conv.paused = not conv.paused
        db.session.commit()
        return redirect(url_for('admin_conversation_detail', conv_id=conv_id))

    @app.post('/admin/conversations/<int:conv_id>/close')
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
        return redirect(url_for('admin_conversation_detail', conv_id=conv_id))

    @app.post('/admin/conversations/<int:conv_id>/phases')
    @login_required
    @admin_required
    def admin_conversation_phases(conv_id):
        conv = Conversation.query.get_or_404(conv_id)
        conv.phase_submission       = bool(request.form.get('phase_submission'))
        conv.phase_personal_results = bool(request.form.get('phase_personal_results'))
        conv.phase_argument_mapping = bool(request.form.get('phase_argument_mapping'))
        conv.phase_public_results   = bool(request.form.get('phase_public_results'))
        db.session.commit()
        return redirect(url_for('admin_conversation_detail', conv_id=conv_id))

    @app.post('/admin/global-admins/add')
    @login_required
    @admin_required
    def admin_global_admin_add():
        mw_username = (request.form.get('mw_username') or '').strip()
        if not mw_username:
            return redirect(url_for('admin', error='Enter a Wikimedia username.'))
        p = Participant.query.filter_by(mw_username=mw_username).first()
        if not p:
            return redirect(url_for('admin', error=f'No account found for "{mw_username}". They must log in at least once first.'))
        p.is_global_admin = True
        db.session.commit()
        return redirect(url_for('admin'))

    @app.post('/admin/global-admins/<int:participant_id>/remove')
    @login_required
    @admin_required
    def admin_global_admin_remove(participant_id):
        p = Participant.query.get_or_404(participant_id)
        p.is_global_admin = False
        db.session.commit()
        return redirect(url_for('admin'))

    @app.post('/admin/roles/add')
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
        return redirect(_safe_redirect(request.form.get('redirect_to', ''), url_for('admin')))

    @app.post('/admin/roles/<int:role_id>/remove')
    @login_required
    @admin_required
    def admin_role_remove(role_id):
        role = AdminRole.query.get_or_404(role_id)
        db.session.delete(role)
        db.session.commit()
        return redirect(_safe_redirect(request.form.get('redirect_to', ''), url_for('admin')))

    @app.get('/admin/conversations/<int:conv_id>/invites')
    @login_required
    def admin_conversation_invites(conv_id):
        conv    = _require_mod_for_conv(conv_id)
        invites = (ConversationInvite.query
                   .filter_by(conversation_id=conv_id)
                   .order_by(ConversationInvite.mw_username)
                   .all())
        return render_template('admin_invites.html',
                               conversation=conv, invites=invites)

    @app.post('/admin/conversations/<int:conv_id>/invites/add')
    @login_required
    def admin_invite_add(conv_id):
        _require_mod_for_conv(conv_id)
        raw = [l.strip() for l in
               request.form.get('mw_usernames', '').splitlines() if l.strip()]
        usernames = [u for u in raw if 1 <= len(u) <= 255]
        if not usernames:
            return redirect(url_for('admin_conversation_invites', conv_id=conv_id))
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
        return redirect(url_for('admin_conversation_invites', conv_id=conv_id))

    @app.post('/admin/conversations/<int:conv_id>/invites/<int:invite_id>/remove')
    @login_required
    def admin_invite_remove(conv_id, invite_id):
        _require_mod_for_conv(conv_id)
        invite = ConversationInvite.query.filter_by(
            id=invite_id, conversation_id=conv_id).first_or_404()
        db.session.delete(invite)
        db.session.commit()
        return redirect(url_for('admin_conversation_invites', conv_id=conv_id))

    # ── Admin: Polis statement moderation ─────────────────────────────────────

    @app.get('/admin/conversations/<int:conv_id>/statements')
    @login_required
    def admin_conversation_statements(conv_id):
        conv   = _require_mod_for_conv(conv_id)
        client = PolisAdminClient(current_app.config['PARTICIAPI_BASE'])
        error  = request.args.get('error')
        pending = approved = hidden = []
        settings = {}
        try:
            pending, approved, hidden = client.get_statements(conv.polis_id)
            settings = client.get_settings(conv.polis_id)
        except PolisAdminError as exc:
            error = str(exc)
        return render_template('admin_statements.html',
                               conversation=conv,
                               pending=pending,
                               approved=approved,
                               hidden=hidden,
                               settings=settings,
                               error=error,
                               polis_public_url=current_app.config.get('POLIS_PUBLIC_URL', 'https://pol.is'))

    @app.post('/admin/conversations/<int:conv_id>/statements/<int:tid>/moderate')
    @login_required
    def admin_statement_moderate(conv_id, tid):
        conv = _require_mod_for_conv(conv_id)
        mod  = request.form.get('mod', type=int)
        if mod not in (-1, 0, 1):
            abort(400)
        client = PolisAdminClient(current_app.config['PARTICIAPI_BASE'])
        try:
            client.moderate(conv.polis_id, tid, mod)
        except PolisAdminError as exc:
            current_app.logger.error('moderate failed: %s', exc)
            return redirect(url_for('admin_conversation_statements',
                                    conv_id=conv_id, error=str(exc)))
        return redirect(url_for('admin_conversation_statements', conv_id=conv_id))

    @app.post('/admin/conversations/<int:conv_id>/statements/seed')
    @login_required
    def admin_statement_seed(conv_id):
        conv = _require_mod_for_conv(conv_id)
        text = request.form.get('txt', '').strip()
        text = nh3.clean(text, tags=frozenset())
        if not text or len(text) > 280:
            abort(400)
        client = PolisAdminClient(current_app.config['PARTICIAPI_BASE'])
        try:
            client.add_seed(conv.polis_id, text)
        except PolisAdminError as exc:
            current_app.logger.error('add_seed failed: %s', exc)
        return redirect(url_for('admin_conversation_statements', conv_id=conv_id))

    @app.post('/admin/conversations/<int:conv_id>/strict-moderation')
    @login_required
    def admin_conversation_strict_moderation(conv_id):
        conv    = _require_mod_for_conv(conv_id)
        enabled = request.form.get('strict_moderation') == '1'
        client  = PolisAdminClient(current_app.config['PARTICIAPI_BASE'])
        try:
            client.set_strict_moderation(conv.polis_id, enabled)
        except PolisAdminError as exc:
            current_app.logger.error('set_strict_moderation failed: %s', exc)
        return redirect(url_for('admin_conversation_statements', conv_id=conv_id))

    # ── Featured statements ───────────────────────────────────────────────────

    def _backfill_statement_texts(conv, confirmed: list) -> bool:
        """Fetch and store statement_text for any confirmed FS that is missing it."""
        missing = [fs for fs in confirmed if not fs.statement_text]
        if not missing:
            return False
        client = PolisAdminClient(current_app.config['PARTICIAPI_BASE'])
        try:
            _, approved, _ = client.get_statements(conv.polis_id)
            text_by_tid = {s['tid']: (s.get('text') or s.get('txt', '')) for s in approved}
        except PolisAdminError:
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

    @app.get('/admin/conversations/<int:conv_id>/featured')
    @login_required
    def admin_conversation_featured(conv_id):
        conv        = _require_mod_for_conv(conv_id)
        confirmed   = (FeaturedStatement.query
                       .filter_by(conversation_id=conv_id)
                       .order_by(FeaturedStatement.created_at).all())
        _backfill_statement_texts(conv, confirmed)
        confirmed_tids = {fs.polis_statement_id for fs in confirmed}
        candidates  = get_featured_candidates(
            conv.polis_id, current_app.config.get('POLIS_DATABASE_URL', ''))
        if candidates is not None:
            candidates = [c for c in candidates if c['tid'] not in confirmed_tids]
        return render_template('admin_featured.html',
                               conversation=conv,
                               confirmed=confirmed,
                               candidates=candidates)

    def _fetch_statement_text(conv_polis_id: str, tid: int) -> str:
        client = PolisAdminClient(current_app.config['PARTICIAPI_BASE'])
        try:
            _, approved, _ = client.get_statements(conv_polis_id)
            for s in approved:
                if s.get('tid') == tid:
                    return s.get('text') or s.get('txt', '')
        except PolisAdminError:
            pass
        return ''

    @app.post('/admin/conversations/<int:conv_id>/featured/confirm')
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
        return redirect(url_for('admin_conversation_featured', conv_id=conv_id))

    @app.post('/admin/conversations/<int:conv_id>/featured/add')
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
        return redirect(url_for('admin_conversation_featured', conv_id=conv_id))

    @app.post('/admin/conversations/<int:conv_id>/featured/<int:fs_id>/remove')
    @login_required
    def admin_featured_remove(conv_id, fs_id):
        _require_mod_for_conv(conv_id)
        fs = FeaturedStatement.query.filter_by(
            id=fs_id, conversation_id=conv_id).first_or_404()
        db.session.delete(fs)
        db.session.commit()
        return redirect(url_for('admin_conversation_featured', conv_id=conv_id))


app = create_app()

if __name__ == '__main__':
    app.run(debug=True)

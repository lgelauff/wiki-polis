"""
app.py — Flask application for wiki-polis.

Community-specific settings are in the config block immediately below.
Edit only that block when deploying for a different event or community.
"""

# ── Community configuration ───────────────────────────────────────────────────
# Edit this block for each deployment; do not touch anything below it.

TOOL_NAME   = "wiki-polis"
EVENT_NAME  = "Community Consultation"

# Admin usernames are loaded from the 'admin-users' secret (comma-separated).
# Locally: set ADMIN_USERS=Username1,Username2 in .env
# Toolforge: toolforge secrets create wiki-polis-admin-users --from-literal=value=Username1,Username2

# Conversations are managed via the admin UI — no config needed here.

# ── End of community configuration ───────────────────────────────────────────

import base64
import functools
import hashlib
import os
import re
import secrets
from datetime import timedelta
from urllib.parse import urlencode

import nh3
import requests
from dotenv import load_dotenv
from flask import (Flask, abort, redirect, render_template, request,
                   session, url_for)
from flask_migrate import Migrate
from flask_session import Session

from db import (ACCESS_POLICIES, Conversation, ConversationInvite,
                Participant, Participation, db)

load_dotenv()

_MW_USER_AGENT = 'wiki-polis/1.0 (Toolforge tool; https://wiki-polis.toolforge.org)'

# Allowed HTML tags and attributes for intro/outro text
_TEXT_ALLOWED_TAGS  = {'p', 'strong', 'em', 'a', 'ul', 'ol', 'li', 'br'}
_TEXT_ALLOWED_ATTRS = {'a': {'href', 'title'}}

# Valid Polis conversation ID format
_POLIS_ID_RE = re.compile(r'^[A-Za-z0-9]{6,20}$')

# Valid slug format: lowercase letters, digits, hyphens
_SLUG_RE = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')


def _read_secret(name: str) -> str:
    """Read from /run/secrets/<TOOL_NAME>/<name> (Kubernetes), fall back to env var."""
    file_path = f'/run/secrets/{TOOL_NAME}/{name}'
    if os.path.exists(file_path):
        with open(file_path) as f:
            return f.read().strip()
    return os.environ.get(name.upper().replace('-', '_'), '')


ADMIN_USERS = [u.strip() for u in _read_secret('admin-users').split(',') if u.strip()]


def _sanitise_text(html: str) -> str:
    """Sanitise intro/outro HTML — strip everything except the safe allowlist."""
    return nh3.clean(html or '', tags=_TEXT_ALLOWED_TAGS,
                     attributes=_TEXT_ALLOWED_ATTRS, strip_comments=True)


def _valid_polis_id(polis_id: str) -> bool:
    return bool(_POLIS_ID_RE.match(polis_id or ''))


def _valid_slug(slug: str) -> bool:
    return bool(_SLUG_RE.match(slug or ''))


def _parse_conversation_form() -> dict:
    """Extract and sanitise shared conversation form fields from request.form."""
    raw_policy = request.form.get('access_policy', 'public').strip()
    return {
        'polis_id':     request.form.get('polis_id', '').strip(),
        'title':        request.form.get('title', '').strip(),
        'intro_text':   _sanitise_text(request.form.get('intro_text', '')),
        'outro_text':   _sanitise_text(request.form.get('outro_text', '')),
        'access_policy': raw_policy if raw_policy in ACCESS_POLICIES else 'public',
    }


def _current_participant() -> 'Participant | None':
    """Return the Participant row for the logged-in user, or None."""
    username = session.get('username')
    if not username:
        return None
    return Participant.query.filter_by(mw_username=username).first()


def _is_emailable(username: str) -> bool:
    """Check via MW API whether the user has a confirmed email address."""
    try:
        resp = requests.get(
            'https://meta.wikimedia.org/w/api.php',
            params={
                'action':   'query',
                'list':     'users',
                'ususers':  username,
                'usprop':   'emailable',
                'format':   'json',
            },
            headers={'User-Agent': _MW_USER_AGENT},
            timeout=5,
        )
        resp.raise_for_status()
        user = resp.json()['query']['users'][0]
        return 'emailable' in user
    except Exception:
        return False


def create_app() -> Flask:
    app = Flask(__name__)

    app.config['SECRET_KEY']                     = _read_secret('secret-key') or 'dev-insecure-key'
    app.config['SQLALCHEMY_DATABASE_URI']        = _read_secret('database-url') or 'sqlite:///dev.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SQLALCHEMY_ENGINE_OPTIONS']      = {
        'pool_recycle': 280,
        'pool_pre_ping': True,
    }

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

    app.config['EVENT_NAME']   = EVENT_NAME
    app.config['ADMIN_USERS']  = ADMIN_USERS

    db.init_app(app)
    Migrate(app, db)
    Session(app)

    with app.app_context():
        with db.engine.begin() as conn:
            db.metadata.create_all(conn)

    @app.context_processor
    def _inject_globals():
        return {
            'event_name': app.config['EVENT_NAME'],
            'is_admin':   _is_admin(),
            'username':   session.get('username'),
        }

    _register_routes(app)
    return app


# ── Auth helpers ──────────────────────────────────────────────────────────────

def login_required(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        if 'username' not in session:
            session['next'] = request.url
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return wrapper


def _is_admin() -> bool:
    """True if the logged-in user is a superadmin (secret) or a DB-granted admin."""
    if session.get('username') in ADMIN_USERS:
        return True
    participant = _current_participant()
    return bool(participant and participant.is_admin)


def admin_required(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        if not _is_admin():
            abort(403)
        return f(*args, **kwargs)
    return wrapper


def _check_conversation_access(conversation, participant) -> None:
    """Abort 403 if the current user may not access this conversation."""
    if conversation.access_policy != 'invite_only':
        return
    # Already accepted → always allow, even if later removed from invite list
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


# ── Routes ────────────────────────────────────────────────────────────────────

def _register_routes(app: Flask) -> None:

    # Dev-only login bypass
    if app.debug:
        @app.get('/dev-login')
        def dev_login():
            username = request.args.get('username', '').strip()
            if not username:
                return 'Usage: /dev-login?username=YourWikimediaName', 400
            xid = hashlib.sha256(f'dev-{username}'.encode()).hexdigest()
            participant = Participant.query.filter_by(mw_username=username).first()
            if participant is None:
                participant = Participant(mw_user_id=abs(hash(username)) % 10**9,
                                         mw_username=username, xid=xid)
                db.session.add(participant)
                db.session.commit()
            session['username'] = username
            session['xid']      = xid
            return redirect(url_for('index'))

    @app.get('/')
    def index():
        if 'username' not in session:
            public_convos = (Conversation.query
                             .filter_by(active=True, access_policy='public')
                             .order_by(Conversation.created_at.desc())
                             .all())
            first_admin = ADMIN_USERS[0] if ADMIN_USERS else ''
            return render_template('welcome.html', debug=app.debug,
                                   first_admin=first_admin,
                                   public_conversations=public_convos)

        participant = _current_participant()
        username    = session['username']

        accepted = []
        if participant:
            accepted = (Conversation.query
                        .join(Participation)
                        .filter(Participation.participant_id == participant.id)
                        .order_by(Conversation.created_at.desc())
                        .all())

        accepted_ids    = {c.id for c in accepted}
        invited_conv_ids = [
            inv.conversation_id
            for inv in ConversationInvite.query.filter_by(mw_username=username).all()
        ]

        open_conversations = (Conversation.query
                              .filter_by(active=True)
                              .filter(~Conversation.id.in_(accepted_ids))
                              .filter(db.or_(
                                  Conversation.access_policy == 'public',
                                  db.and_(
                                      Conversation.access_policy == 'invite_only',
                                      Conversation.id.in_(invited_conv_ids or [0]),
                                  ),
                              ))
                              .order_by(Conversation.created_at.desc())
                              .all())

        return render_template('landing.html',
                               accepted=accepted,
                               open_conversations=open_conversations)

    @app.get('/c/<slug>')
    @login_required
    def conversation(slug):
        conversation = Conversation.query.filter_by(slug=slug).first_or_404()
        participant  = _current_participant()
        _check_conversation_access(conversation, participant)

        participation = None
        if participant:
            participation = Participation.query.filter_by(
                participant_id=participant.id,
                conversation_id=conversation.id,
            ).first()

        if participation is None:
            return redirect(url_for('accept', slug=slug))

        return render_template('index.html', conversation=conversation, xid=session.get('xid'))

    @app.get('/accept/<slug>')
    @login_required
    def accept(slug):
        conversation = Conversation.query.filter_by(slug=slug).first_or_404()
        _check_conversation_access(conversation, _current_participant())
        emailable    = _is_emailable(session['username'])
        return render_template('accept.html', conversation=conversation, emailable=emailable)

    @app.post('/accept/<slug>')
    @login_required
    def accept_post(slug):
        conversation = Conversation.query.filter_by(slug=slug).first_or_404()
        participant  = _current_participant()
        if participant is None:
            abort(404)
        _check_conversation_access(conversation, participant)

        notify_email     = bool(request.form.get('notify_email'))
        notify_talk_page = bool(request.form.get('notify_talk_page'))
        talk_page_wiki   = request.form.get('talk_page_wiki', '').strip() or None
        # emailable was checked on GET; re-use value passed via hidden field to avoid a second API call
        emailable        = request.form.get('emailable') == '1'

        if notify_talk_page and not talk_page_wiki:
            return render_template('accept.html', conversation=conversation,
                                   emailable=emailable,
                                   error='Please specify which wiki for talk page notifications.')

        participation = Participation(
            participant_id   = participant.id,
            conversation_id  = conversation.id,
            notify_email     = notify_email,
            notify_talk_page = notify_talk_page,
            talk_page_wiki   = talk_page_wiki,
        )
        db.session.add(participation)
        db.session.commit()
        return redirect(url_for('conversation', slug=slug))

    @app.get('/login')
    def login():
        if not app.config.get('OAUTH_CLIENT_ID'):
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
    def oauth_callback():
        if request.args.get('state') != session.pop('oauth_state', None):
            app.logger.warning('OAuth callback: state mismatch')
            return redirect(url_for('index'))

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
                headers={
                    'Authorization': f'Bearer {access_token}',
                    'User-Agent':    _MW_USER_AGENT,
                },
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
        session['username'] = username
        session['xid']      = xid

        return redirect(next_url or url_for('index'))

    @app.get('/logout')
    @login_required
    def logout():
        session.clear()
        return redirect(url_for('login'))

    # ── Admin routes ──────────────────────────────────────────────────────────

    @app.get('/admin')
    @login_required
    @admin_required
    def admin():
        search = request.args.get('q', '').strip()
        page   = request.args.get('page', 1, type=int)

        participant_q = Participant.query.order_by(Participant.created_at.desc())
        if search:
            participant_q = participant_q.filter(
                Participant.mw_username.ilike(f'%{search}%')
            )
        pagination    = participant_q.paginate(page=page, per_page=50, error_out=False)
        conversations = Conversation.query.order_by(Conversation.created_at.desc()).all()

        return render_template('admin.html',
                               pagination=pagination,
                               search=search,
                               conversations=conversations)

    @app.post('/admin/conversations/new')
    @login_required
    @admin_required
    def admin_conversation_new():
        slug   = request.form.get('slug', '').strip().lower()
        fields = _parse_conversation_form()

        if not fields['title'] or not _valid_polis_id(fields['polis_id']) or not _valid_slug(slug):
            abort(400)

        conversation = Conversation(slug=slug, active=True, **fields)
        db.session.add(conversation)
        db.session.commit()
        return redirect(url_for('admin'))

    @app.post('/admin/conversations/<int:conv_id>/edit')
    @login_required
    @admin_required
    def admin_conversation_edit(conv_id):
        conversation = Conversation.query.get_or_404(conv_id)
        fields       = _parse_conversation_form()

        if not fields['title'] or not _valid_polis_id(fields['polis_id']):
            abort(400)

        # Slug is immutable after creation to avoid breaking existing links
        conversation.polis_id     = fields['polis_id']
        conversation.title        = fields['title']
        conversation.intro_text   = fields['intro_text']
        conversation.outro_text   = fields['outro_text']
        conversation.access_policy = fields['access_policy']
        db.session.commit()
        return redirect(url_for('admin'))

    @app.post('/admin/participants/<int:participant_id>/toggle-admin')
    @login_required
    @admin_required
    def admin_toggle_admin(participant_id):
        participant = Participant.query.get_or_404(participant_id)
        # Superadmins (from secret) cannot be demoted via UI
        if participant.mw_username in ADMIN_USERS:
            abort(403)
        participant.is_admin = not participant.is_admin
        db.session.commit()
        return redirect(url_for('admin'))

    @app.post('/admin/conversations/<int:conv_id>/toggle')
    @login_required
    @admin_required
    def admin_conversation_toggle(conv_id):
        conversation = Conversation.query.get_or_404(conv_id)
        conversation.active = not conversation.active
        db.session.commit()
        return redirect(url_for('admin'))

    @app.get('/admin/conversations/<int:conv_id>/invites')
    @login_required
    @admin_required
    def admin_conversation_invites(conv_id):
        conversation = Conversation.query.get_or_404(conv_id)
        invites = (ConversationInvite.query
                   .filter_by(conversation_id=conv_id)
                   .order_by(ConversationInvite.mw_username)
                   .all())
        return render_template('admin_invites.html',
                               conversation=conversation,
                               invites=invites)

    @app.post('/admin/conversations/<int:conv_id>/invites/add')
    @login_required
    @admin_required
    def admin_invite_add(conv_id):
        conversation = Conversation.query.get_or_404(conv_id)
        # Sanitise: split lines, strip whitespace, drop empty and oversized entries
        raw_usernames = [
            line.strip()
            for line in request.form.get('mw_usernames', '').splitlines()
            if line.strip()
        ]
        usernames = [u for u in raw_usernames if 1 <= len(u) <= 255]
        if not usernames:
            return redirect(url_for('admin_conversation_invites', conv_id=conv_id))
        existing = {
            inv.mw_username
            for inv in ConversationInvite.query.filter_by(conversation_id=conv_id).all()
        }
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
    @admin_required
    def admin_invite_remove(conv_id, invite_id):
        invite = ConversationInvite.query.filter_by(
            id=invite_id, conversation_id=conv_id).first_or_404()
        db.session.delete(invite)
        db.session.commit()
        return redirect(url_for('admin_conversation_invites', conv_id=conv_id))


app = create_app()

if __name__ == '__main__':
    app.run(debug=True)

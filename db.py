"""
db.py — SQLAlchemy models for wiki-polis.
"""

from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

ACCESS_POLICIES = ('public', 'link_based', 'invite_only')


class Participant(db.Model):
    __tablename__ = 'participants'

    id           = db.Column(db.Integer, primary_key=True)
    mw_user_id   = db.Column(db.Integer, nullable=False, unique=True)  # stable across renames
    mw_username  = db.Column(db.String(255), nullable=False)            # updated on rename
    xid          = db.Column(db.String(64), nullable=False, unique=True)  # sha256(mw_user_id), never changes
    is_admin     = db.Column(db.Boolean, default=False, nullable=False)  # granted via admin UI
    created_at   = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    participations = db.relationship('Participation', back_populates='participant')


class Conversation(db.Model):
    __tablename__ = 'conversations'

    id          = db.Column(db.Integer, primary_key=True)
    slug        = db.Column(db.String(80), nullable=False, unique=True)  # URL-safe, e.g. 'community-consultation-2026'
    polis_id    = db.Column(db.String(50), nullable=False)   # Polis conversation_id, validated on save
    title       = db.Column(db.String(255), nullable=False)
    intro_text  = db.Column(db.Text, nullable=True)          # sanitised HTML, safe to render
    outro_text  = db.Column(db.Text, nullable=True)          # sanitised HTML, safe to render
    active        = db.Column(db.Boolean, default=True, nullable=False)
    access_policy = db.Column(db.String(20), nullable=False, default='public', server_default='public')
    created_at    = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    participations = db.relationship('Participation', back_populates='conversation')
    invites        = db.relationship('ConversationInvite', back_populates='conversation',
                                     cascade='all, delete-orphan')


class Participation(db.Model):
    __tablename__  = 'participations'
    __table_args__ = (db.UniqueConstraint('participant_id', 'conversation_id'),)

    id                = db.Column(db.Integer, primary_key=True)
    participant_id    = db.Column(db.Integer, db.ForeignKey('participants.id'), nullable=False)
    conversation_id   = db.Column(db.Integer, db.ForeignKey('conversations.id'), nullable=False)
    accepted_at       = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    notify_email      = db.Column(db.Boolean, default=False, nullable=False)
    notify_talk_page  = db.Column(db.Boolean, default=False, nullable=False)
    talk_page_wiki    = db.Column(db.String(50), nullable=True)  # e.g. 'enwiki', 'nlwiki', 'meta'

    participant  = db.relationship('Participant', back_populates='participations')
    conversation = db.relationship('Conversation', back_populates='participations')


class AdminRole(db.Model):
    __tablename__ = 'admin_roles'

    id              = db.Column(db.Integer, primary_key=True)
    participant_id  = db.Column(db.Integer, db.ForeignKey('participants.id'), nullable=False)
    conversation_id = db.Column(db.Integer, db.ForeignKey('conversations.id'), nullable=True)
    role            = db.Column(db.Enum('admin', 'moderator', 'curator', name='admin_role_type'), nullable=False)
    granted_at      = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    granted_by      = db.Column(db.Integer, db.ForeignKey('participants.id'), nullable=True)

    participant  = db.relationship('Participant', foreign_keys=[participant_id], backref='roles')
    conversation = db.relationship('Conversation', backref='roles')


class ModAction(db.Model):
    __tablename__ = 'mod_actions'

    id            = db.Column(db.Integer, primary_key=True)
    moderator_id  = db.Column(db.Integer, db.ForeignKey('participants.id'), nullable=False)
    action_type   = db.Column(db.Enum('hide_statement', 'show_statement', 'block_user', 'unblock_user', name='mod_action_type'), nullable=False)
    target_type   = db.Column(db.String(50))
    target_id     = db.Column(db.Integer)
    reason        = db.Column(db.Text)
    created_at    = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    moderator = db.relationship('Participant', foreign_keys=[moderator_id])


class ConversationInvite(db.Model):
    __tablename__  = 'conversation_invites'
    __table_args__ = (db.UniqueConstraint('conversation_id', 'mw_username'),)

    id              = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('conversations.id'), nullable=False)
    mw_username     = db.Column(db.String(255), nullable=False)
    created_at      = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    conversation = db.relationship('Conversation', back_populates='invites')

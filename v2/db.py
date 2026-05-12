from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

ACCESS_POLICIES = ('public', 'invite_only')
ADMIN_ROLES     = ('admin', 'moderator')
ARGUMENT_SIDES  = ('pro', 'con')


class Participant(db.Model):
    __tablename__ = 'participants'

    id          = db.Column(db.Integer, primary_key=True)
    mw_user_id  = db.Column(db.Integer, nullable=False, unique=True)
    mw_username = db.Column(db.String(255), nullable=False)
    xid         = db.Column(db.String(64), nullable=False, unique=True)  # sha256(mw_user_id)
    created_at  = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    participations = db.relationship('Participation', back_populates='participant')
    roles          = db.relationship('AdminRole', foreign_keys='AdminRole.participant_id',
                                     back_populates='participant')


class Conversation(db.Model):
    __tablename__ = 'conversations'

    id           = db.Column(db.Integer, primary_key=True)
    slug         = db.Column(db.String(80), nullable=False, unique=True)
    polis_id     = db.Column(db.String(50), nullable=False)  # Polis zinvite
    title        = db.Column(db.String(255), nullable=False)
    intro_text   = db.Column(db.Text, nullable=True)   # sanitised HTML
    outro_text   = db.Column(db.Text, nullable=True)   # sanitised HTML
    active       = db.Column(db.Boolean, default=True, nullable=False)
    paused       = db.Column(db.Boolean, default=False, nullable=False)  # reversible; does NOT start reveal clock
    access_policy = db.Column(db.String(20), nullable=False, default='public')
    created_at   = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    closed_at    = db.Column(db.DateTime, nullable=True)   # set on permanent close; drives reveal timeline (irreversible)

    # Phase toggles — independent, default off
    phase_submission       = db.Column(db.Boolean, default=False, nullable=False)
    phase_personal_results = db.Column(db.Boolean, default=False, nullable=False)
    phase_argument_mapping = db.Column(db.Boolean, default=False, nullable=False)
    phase_public_results   = db.Column(db.Boolean, default=False, nullable=False)

    participations     = db.relationship('Participation', back_populates='conversation')
    invites            = db.relationship('ConversationInvite', back_populates='conversation',
                                         cascade='all, delete-orphan')
    roles              = db.relationship('AdminRole', back_populates='conversation')
    featured_statements = db.relationship('FeaturedStatement', back_populates='conversation',
                                          cascade='all, delete-orphan')


class Participation(db.Model):
    __tablename__  = 'participations'
    __table_args__ = (db.UniqueConstraint('participant_id', 'conversation_id'),
                      db.UniqueConstraint('pseudonym'))

    id              = db.Column(db.Integer, primary_key=True)
    participant_id  = db.Column(db.Integer, db.ForeignKey('participants.id'), nullable=False)
    conversation_id = db.Column(db.Integer, db.ForeignKey('conversations.id'), nullable=False)
    pseudonym       = db.Column(db.String(80), nullable=False)  # unique across all participations; never deleted
    accepted_at     = db.Column(db.DateTime, nullable=False,
                                default=lambda: datetime.now(timezone.utc))
    notify_email      = db.Column(db.Boolean, default=False, nullable=False)
    notify_talk_page  = db.Column(db.Boolean, default=False, nullable=False)
    # Opt-in identity reveal: set once by participant, irreversible during reveal window.
    # Stored here (not derived from Participant) so older exports remain valid.
    # Nullified automatically 60 days after conversation close (data minimisation).
    public_username   = db.Column(db.String(255), nullable=True)
    revealed_at       = db.Column(db.DateTime, nullable=True)

    participant  = db.relationship('Participant', back_populates='participations')
    conversation = db.relationship('Conversation', back_populates='participations')


class ConversationInvite(db.Model):
    __tablename__  = 'conversation_invites'
    __table_args__ = (db.UniqueConstraint('conversation_id', 'mw_username'),)

    id              = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('conversations.id'), nullable=False)
    mw_username     = db.Column(db.String(255), nullable=False)
    created_at      = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    conversation = db.relationship('Conversation', back_populates='invites')


class AdminRole(db.Model):
    __tablename__  = 'admin_roles'
    __table_args__ = (db.UniqueConstraint('participant_id', 'conversation_id', 'role'),)

    id              = db.Column(db.Integer, primary_key=True)
    participant_id  = db.Column(db.Integer, db.ForeignKey('participants.id'), nullable=False)
    conversation_id = db.Column(db.Integer, db.ForeignKey('conversations.id'), nullable=True)
    role            = db.Column(db.Enum(*ADMIN_ROLES, name='admin_role_type'), nullable=False)
    granted_at      = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    granted_by      = db.Column(db.Integer, db.ForeignKey('participants.id'), nullable=True)

    participant  = db.relationship('Participant', foreign_keys=[participant_id],
                                   back_populates='roles')
    conversation = db.relationship('Conversation', back_populates='roles')


class FeaturedStatement(db.Model):
    __tablename__  = 'featured_statements'
    __table_args__ = (db.UniqueConstraint('conversation_id', 'polis_statement_id'),)

    id                  = db.Column(db.Integer, primary_key=True)
    conversation_id     = db.Column(db.Integer, db.ForeignKey('conversations.id'), nullable=False)
    polis_statement_id  = db.Column(db.Integer, nullable=False)
    suggested_by_system = db.Column(db.Boolean, default=False, nullable=False)
    confirmed_by_admin  = db.Column(db.Boolean, default=False, nullable=False)
    created_at          = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    conversation = db.relationship('Conversation', back_populates='featured_statements')
    arguments    = db.relationship('Argument', back_populates='featured_statement',
                                   cascade='all, delete-orphan')


class Argument(db.Model):
    __tablename__ = 'arguments'

    id                   = db.Column(db.Integer, primary_key=True)
    featured_statement_id = db.Column(db.Integer, db.ForeignKey('featured_statements.id'),
                                       nullable=False)
    author_id            = db.Column(db.Integer, db.ForeignKey('participants.id'), nullable=False)
    body                 = db.Column(db.String(280), nullable=False)
    side                 = db.Column(db.Enum(*ARGUMENT_SIDES, name='argument_side'), nullable=False)
    created_at           = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    featured_statement = db.relationship('FeaturedStatement', back_populates='arguments')
    author             = db.relationship('Participant')
    votes              = db.relationship('ArgumentVote', back_populates='argument',
                                         cascade='all, delete-orphan')


class ArgumentVote(db.Model):
    __tablename__  = 'argument_votes'
    __table_args__ = (db.UniqueConstraint('argument_id', 'participant_id'),)

    id             = db.Column(db.Integer, primary_key=True)
    argument_id    = db.Column(db.Integer, db.ForeignKey('arguments.id'), nullable=False)
    participant_id = db.Column(db.Integer, db.ForeignKey('participants.id'), nullable=False)
    useful         = db.Column(db.Boolean, nullable=False)
    created_at     = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    argument    = db.relationship('Argument', back_populates='votes')
    participant = db.relationship('Participant')

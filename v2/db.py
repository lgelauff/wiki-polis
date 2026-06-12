from datetime import datetime, timezone

import sqlalchemy as sa
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

# All DateTime columns store UTC (naive). datetime.now(timezone.utc) is used
# everywhere so values are correct; timezone metadata is not stored at DB level
# because SQLite and MySQL both ignore DateTime(timezone=True).

ACCESS_POLICIES = ('public', 'invite_only')
ADMIN_ROLES     = ('moderator',)   # conversation-scoped only; site-wide access is Participant.is_global_admin
ARGUMENT_SIDES  = ('pro', 'con')


class Participant(db.Model):
    __tablename__ = 'participants'

    id               = db.Column(db.Integer, primary_key=True)
    mw_user_id       = db.Column(db.Integer, nullable=False, unique=True)
    mw_username      = db.Column(db.String(255), nullable=False)
    # xid: sha256(mw_user_id). Stable opaque token passed to Particiapi — not a privacy guarantee.
    # MW user IDs are sequential integers; the hash space is brute-forceable. Do not treat xid
    # as a pseudonym or publish it. Salt before any public exposure.
    xid              = db.Column(db.String(64), nullable=False, unique=True)
    is_global_admin  = db.Column(db.Boolean, default=False, nullable=False)
    created_at       = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    participations = db.relationship('Participation', back_populates='participant')
    roles          = db.relationship('AdminRole', foreign_keys='AdminRole.participant_id',
                                     back_populates='participant')


class Conversation(db.Model):
    __tablename__ = 'conversations'
    __table_args__ = (
        # Invariant: permanently closed conversations must not be active or paused.
        db.CheckConstraint(
            '(closed_at IS NULL) OR (active = 0 AND paused = 0)',
            name='closed_conversation_inactive',
        ),
        # One-to-one: each wiki-polis conversation maps to at most one Phase 6 Polis
        # conversation. The UNIQUE constraint converts a double-init race into a loud
        # IntegrityError rather than a silent overwrite.
        db.UniqueConstraint('phase6_polis_conversation_id',
                            name='uq_conversations_phase6_polis_conversation_id'),
    )

    id           = db.Column(db.Integer, primary_key=True)
    slug         = db.Column(db.String(80), nullable=False, unique=True)
    polis_id     = db.Column(db.String(50), nullable=False, unique=True)  # Polis zinvite
    title        = db.Column(db.String(255), nullable=False)
    language     = db.Column(db.String(10), nullable=False, default='en')  # BCP 47 tag
    intro_text   = db.Column(db.Text, nullable=True)   # sanitised HTML
    outro_text   = db.Column(db.Text, nullable=True)   # sanitised HTML
    active       = db.Column(db.Boolean, default=True, nullable=False)
    paused       = db.Column(db.Boolean, default=False, nullable=False)  # reversible; does NOT start reveal clock
    access_policy = db.Column(db.String(20), nullable=False, default='public')
    created_at   = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    closed_at    = db.Column(db.DateTime, nullable=True)   # set on permanent close; drives reveal timeline (irreversible)

    # Phase toggles — each controls whether that phase is available to participants.
    # Independent, default off; admin sets them via the conversation panel.
    phase_submission       = db.Column(db.Boolean, default=False, nullable=False)
    phase_personal_results = db.Column(db.Boolean, default=False, nullable=False)
    phase_argument_mapping = db.Column(db.Boolean, default=False, nullable=False)
    # Cleanup — a passive phase between argument mapping and informed voting (#163):
    # participants do nothing; the organizer moderates arguments before the second
    # voting round. Default off; set via the guided transition.
    phase_cleanup          = db.Column(db.Boolean, default=False, nullable=False,
                                       server_default=sa.false())
    phase_public_results   = db.Column(db.Boolean, default=False, nullable=False)
    # Phase 6 — informed voting: a second, independent voting round on featured
    # statements only, with arguments shown inline. Enabling this toggle triggers
    # creation of a dedicated Polis conversation (see phase6_polis_conversation_id).
    phase_informed_voting  = db.Column(db.Boolean, default=False, nullable=False,
                                       server_default=sa.false())

    # Phase 6 Polis mapping — nullable until Phase 6 is initialised by the admin.
    # Uniqueness enforced by the table-level constraint above.
    phase6_polis_conversation_id = db.Column(db.String(50), nullable=True)

    # Argument vote method + method-specific config, e.g.:
    #   vote_method='kApproval', vote_data={'k': 2}
    argument_vote_method   = db.Column(db.String(50), nullable=False, default='kApproval')
    argument_vote_data     = db.Column(db.JSON, nullable=False, default=lambda: {'K': 2})

    participations     = db.relationship('Participation', back_populates='conversation')
    invites            = db.relationship('ConversationInvite', back_populates='conversation',
                                         cascade='all, delete-orphan')
    roles              = db.relationship('AdminRole', back_populates='conversation')
    featured_statements = db.relationship('FeaturedStatement', back_populates='conversation',
                                          cascade='all, delete-orphan')


class Participation(db.Model):
    __tablename__  = 'participations'
    __table_args__ = (db.UniqueConstraint('participant_id', 'conversation_id'),
                      db.UniqueConstraint('pseudonym'),
                      db.CheckConstraint('pseudonym = LOWER(pseudonym)', name='pseudonym_lowercase'))

    id              = db.Column(db.Integer, primary_key=True)
    participant_id  = db.Column(db.Integer, db.ForeignKey('participants.id', ondelete='RESTRICT'), nullable=False)
    conversation_id = db.Column(db.Integer, db.ForeignKey('conversations.id', ondelete='CASCADE'), nullable=False)
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
    # Polis statement IDs of entirely new statements submitted by this participant.
    # Quota = len(new_stmt_ids). Slots consumed at submit time; never returned.
    new_stmt_ids      = db.Column(db.JSON, nullable=False, default=list)
    # Phase 6 card display order: list of FeaturedStatement IDs in the order shown to
    # this participant. Set once on first visit to the informed-voting tab; stable across
    # reloads. Same pattern as ArgumentSideState.argument_order.
    phase6_card_order = db.Column(db.JSON, nullable=True)

    participant  = db.relationship('Participant', back_populates='participations')
    conversation = db.relationship('Conversation', back_populates='participations')


class ConversationInvite(db.Model):
    __tablename__  = 'conversation_invites'
    __table_args__ = (db.UniqueConstraint('conversation_id', 'mw_username'),)

    id              = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('conversations.id', ondelete='CASCADE'), nullable=False)
    mw_username     = db.Column(db.String(255), nullable=False)
    created_at      = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    conversation = db.relationship('Conversation', back_populates='invites')


class AdminRole(db.Model):
    __tablename__  = 'admin_roles'
    __table_args__ = (db.UniqueConstraint('participant_id', 'conversation_id', 'role'),)

    id              = db.Column(db.Integer, primary_key=True)
    participant_id  = db.Column(db.Integer, db.ForeignKey('participants.id', ondelete='CASCADE'), nullable=False)
    conversation_id = db.Column(db.Integer, db.ForeignKey('conversations.id', ondelete='CASCADE'), nullable=False)
    role            = db.Column(db.Enum(*ADMIN_ROLES, name='admin_role_type'), nullable=False)
    granted_at      = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    granted_by      = db.Column(db.Integer, db.ForeignKey('participants.id', ondelete='SET NULL'), nullable=True)

    participant  = db.relationship('Participant', foreign_keys=[participant_id],
                                   back_populates='roles')
    conversation = db.relationship('Conversation', back_populates='roles')


class FeaturedStatement(db.Model):
    __tablename__  = 'featured_statements'
    __table_args__ = (
        db.UniqueConstraint('conversation_id', 'polis_statement_id'),
        # Phase 6: each featured statement maps to at most one Polis statement in the
        # Phase 6 conversation. NULL values are excluded from the uniqueness check by
        # SQL semantics (NULL != NULL), so un-seeded rows do not conflict.
        db.UniqueConstraint('conversation_id', 'phase6_polis_statement_id',
                            name='uq_featured_statements_phase6_polis_statement_id'),
    )

    id                  = db.Column(db.Integer, primary_key=True)
    conversation_id     = db.Column(db.Integer, db.ForeignKey('conversations.id', ondelete='CASCADE'), nullable=False)
    polis_statement_id  = db.Column(db.Integer, nullable=False)
    statement_text      = db.Column(db.Text, nullable=True)  # cached from Particiapi; used when API is unavailable
    suggested_by_system = db.Column(db.Boolean, default=False, nullable=False)
    confirmed_by_admin  = db.Column(db.Boolean, default=False, nullable=False)
    created_at          = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    # Phase 6 mapping: Polis statement ID within the Phase 6 conversation.
    # Null until Phase 6 is initialised. Links to polis_statement_id via our record.
    phase6_polis_statement_id = db.Column(db.Integer, nullable=True)

    conversation = db.relationship('Conversation', back_populates='featured_statements')
    arguments    = db.relationship('Argument', back_populates='featured_statement',
                                   cascade='all, delete-orphan')


class Argument(db.Model):
    __tablename__  = 'arguments'
    __table_args__ = (
        # Enforces one argument per side per participant per featured statement.
        # NULL proposer_id (seeded arguments) is exempt — SQL NULL != NULL.
        db.UniqueConstraint('featured_statement_id', 'proposer_id', 'side'),
    )

    id                    = db.Column(db.Integer, primary_key=True)
    featured_statement_id = db.Column(db.Integer, db.ForeignKey('featured_statements.id', ondelete='CASCADE'),
                                      nullable=False)
    proposer_id           = db.Column(db.Integer, db.ForeignKey('participants.id', ondelete='SET NULL'), nullable=True)
    body                  = db.Column(db.String(280), nullable=False)
    side                  = db.Column(db.Enum(*ARGUMENT_SIDES, name='argument_side'), nullable=False)
    hidden                = db.Column(db.Boolean, nullable=False, default=False)
    created_at            = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    featured_statement = db.relationship('FeaturedStatement', back_populates='arguments')
    proposer           = db.relationship('Participant')
    votes              = db.relationship('ArgumentVote', back_populates='argument',
                                         cascade='all, delete-orphan')


class ArgumentVote(db.Model):
    __tablename__  = 'argument_votes'
    __table_args__ = (db.UniqueConstraint('argument_id', 'participant_id'),)

    id             = db.Column(db.Integer, primary_key=True)
    argument_id    = db.Column(db.Integer, db.ForeignKey('arguments.id', ondelete='CASCADE'), nullable=False)
    participant_id = db.Column(db.Integer, db.ForeignKey('participants.id', ondelete='CASCADE'), nullable=False)
    # Interpretation depends on conversation.argument_vote_method:
    #   kApproval → value is null (row presence = approval)
    #   ranking   → value is the rank position (1 = highest)
    value          = db.Column(db.Integer, nullable=True)
    created_at     = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    argument    = db.relationship('Argument', back_populates='votes')
    voter       = db.relationship('Participant')


class ArgumentSideState(db.Model):
    """Per-participant per-featured-statement per-side state.

    Created on first view of a side. Stores the randomised display order
    (list of argument IDs) so each participant sees a stable personal order
    that is independent of insertion order. Also records whether the
    participant explicitly skipped proposing on this side (gate tracking).
    """
    __tablename__  = 'argument_side_states'
    __table_args__ = (db.UniqueConstraint('participant_id', 'featured_statement_id', 'side'),)

    id                    = db.Column(db.Integer, primary_key=True)
    participant_id        = db.Column(db.Integer, db.ForeignKey('participants.id', ondelete='CASCADE'), nullable=False)
    featured_statement_id = db.Column(db.Integer, db.ForeignKey('featured_statements.id', ondelete='CASCADE'),
                                      nullable=False)
    side                  = db.Column(db.Enum(*ARGUMENT_SIDES, name='argument_side_state_side'),
                                      nullable=False)
    # Ordered list of argument IDs as shown to this participant.
    # New arguments appended at a random position when first encountered.
    argument_order        = db.Column(db.JSON, nullable=False, default=list)
    skipped               = db.Column(db.Boolean, nullable=False, default=False)
    created_at            = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    participant        = db.relationship('Participant')
    featured_statement = db.relationship('FeaturedStatement')


class AuditEvent(db.Model):
    """Append-only accountability record (#135): who did what when, for admin/moderation
    write actions. NEVER updated. Holds ids / enums / counts only — never statement text,
    vote content, usernames, xid, or any PII (the writer's contract; see record_audit).

    FKs use ON DELETE SET NULL (not CASCADE): the trail must outlive a deleted participant
    or conversation — governance durability.
    """
    __tablename__ = 'audit_events'

    id                   = db.Column(db.Integer, primary_key=True)
    ts                   = db.Column(db.DateTime, nullable=False,
                                     default=lambda: datetime.now(timezone.utc))
    actor_participant_id = db.Column(db.Integer,
                                     db.ForeignKey('participants.id', ondelete='SET NULL'),
                                     nullable=True)
    conversation_id      = db.Column(db.Integer,
                                     db.ForeignKey('conversations.id', ondelete='SET NULL'),
                                     nullable=True)
    operation            = db.Column(db.String(64), nullable=False)
    target_type          = db.Column(db.String(32), nullable=True)
    target_id            = db.Column(db.String(64), nullable=True)
    outcome              = db.Column(db.String(16), nullable=False, default='ok')
    detail               = db.Column(db.JSON, nullable=False, default=dict)

    __table_args__ = (
        db.Index('ix_audit_events_conv_ts', 'conversation_id', 'ts'),
        db.Index('ix_audit_events_actor_ts', 'actor_participant_id', 'ts'),
    )


class StatementProvenance(db.Model):
    """Records that a statement is a *derivative* of an existing one (#143).

    wiki-polis has no general statement table — statements live in Polis (`comments`),
    keyed by a Polis statement id (`tid`). So provenance lives here, keyed by
    (conversation_id, polis_statement_id of the NEW statement). Absence of a row = `new`
    (the default); a row exists only for derivatives.

    `derived_from_tid` is a parent pointer, so derivatives form a chain/tree that the
    clustering/weighting consumers resolve into lineage groups (see _lineage_group).

    Similarity-at-creation scores live in the related StatementSimilarityScore rows — one
    per metric (e.g. a cheap 'char' fallback now, a 'semantic' model from #207 later), so a
    link can carry several kinds of score without a schema change.
    """
    __tablename__ = 'statement_provenance'

    id                 = db.Column(db.Integer, primary_key=True)
    conversation_id    = db.Column(db.Integer,
                                   db.ForeignKey('conversations.id', ondelete='CASCADE'),
                                   nullable=False)
    polis_statement_id = db.Column(db.Integer, nullable=False)   # the NEW (derivative) tid
    derived_from_tid   = db.Column(db.Integer, nullable=False)   # the parent it improves on
    provenance_type    = db.Column(db.String(16), nullable=False, default='derivative')  # new|derivative
    link_method        = db.Column(db.String(16), nullable=False, default='declared')    # declared|detected
    created_at         = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    scores = db.relationship('StatementSimilarityScore', back_populates='provenance',
                             cascade='all, delete-orphan')

    __table_args__ = (
        db.UniqueConstraint('conversation_id', 'polis_statement_id',
                            name='uq_statement_provenance_conv_tid'),
        db.Index('ix_statement_provenance_conv', 'conversation_id'),
    )


class StatementSimilarityScore(db.Model):
    """One similarity-at-creation score for a provenance link (#143/#207).

    Several kinds coexist — a cheap always-available `char` fallback and a `semantic`
    model score (#207) — so consumers can prefer semantic when present and fall back to
    char. `model` names the scorer/version; `value` is a similarity in [0, 1], **higher =
    more similar** (cosine similarity is the standard metric). Unique per (provenance,
    model) so re-scoring a metric replaces rather than duplicates.
    """
    __tablename__ = 'statement_similarity_scores'

    id            = db.Column(db.Integer, primary_key=True)
    provenance_id = db.Column(db.Integer,
                              db.ForeignKey('statement_provenance.id', ondelete='CASCADE'),
                              nullable=False)
    model         = db.Column(db.String(64), nullable=False)   # scorer name/version, e.g. 'char', 'semantic-v1'
    value         = db.Column(db.Float, nullable=False)        # similarity, higher = more similar
    scored_at     = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    provenance = db.relationship('StatementProvenance', back_populates='scores')

    __table_args__ = (
        db.UniqueConstraint('provenance_id', 'model', name='uq_similarity_score_prov_model'),
    )


# Explicit indexes — MySQL/MariaDB does not auto-index FK columns.
# Cover the highest-volume lookup patterns in the argument mapping flow.
db.Index('ix_participations_participant_id', Participation.participant_id)
db.Index('ix_participations_conversation_id', Participation.conversation_id)
db.Index('ix_arguments_featured_statement_id', Argument.featured_statement_id)
db.Index('ix_arguments_proposer_id', Argument.proposer_id)
db.Index('ix_argument_votes_argument_id', ArgumentVote.argument_id)
db.Index('ix_argument_votes_participant_id', ArgumentVote.participant_id)
db.Index('ix_argument_side_states_participant_id', ArgumentSideState.participant_id)
db.Index('ix_argument_side_states_featured_statement_id', ArgumentSideState.featured_statement_id)
db.Index('ix_featured_statements_conversation_id', FeaturedStatement.conversation_id)
db.Index('ix_featured_statements_phase6_polis_statement_id',
         FeaturedStatement.conversation_id, FeaturedStatement.phase6_polis_statement_id)

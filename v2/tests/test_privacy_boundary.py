"""Opinion content must never enter ToolsDB.

Votes live in Polis under a Polis uid; identity and participation metadata live in
ToolsDB. Neither database completes the link to a person on its own, and computing the
subject additionally needs PARTICIAPI_SUB_SECRET. That separation is what makes "no one
can see who voted what" (pub_privacy.md) structural rather than a promise.

A column holding a participant's vote on our side collapses it: one join from
participations to participants.mw_username turns ToolsDB alone into a record of who holds
which opinion. This was added once, in a change that passed the entire suite, ruff and
four CI jobs -- every one of which asks whether the code works, and none of which asked
whether the data belonged there. Hence this file.

See ref_data-model.md, "Opinion content never enters ToolsDB".
"""
import db as db_module

# Substrings that suggest a column holds an opinion rather than metadata about one.
# Deliberately blunt: a false positive costs one rename or one line in ALLOWED, while a
# false negative is a privacy regression that ships green.
OPINION_WORDS = ('vote', 'choice', 'agree', 'disagree', 'opinion', 'ballot')

# Columns whose names trip the check but hold no opinion content. Each needs a reason,
# and adding to this list should feel heavier than renaming the column.
ALLOWED = {
    # Per-conversation configuration -- how argument rating works in this conversation,
    # not anyone's answer.
    ('conversations', 'argument_vote_method'),
    ('conversations', 'argument_vote_data'),
}

# NOT allow-listed, and deliberately out of this guard's reach: `argument_votes` links
# participant_id to an argument with a rating value (db.py). Its column names carry no
# opinion word, so a name-based check cannot see it. That table is a pre-existing
# instance of the same shape this file guards against -- who rated which argument, on the
# identity side, one join from mw_username. Whether that is intended is a product
# decision, not one to settle by editing a list here.


def _tables():
    return db_module.db.metadata.tables


def test_no_toolsdb_column_holds_opinion_content():
    offenders = []
    for table_name, table in _tables().items():
        for column in table.columns:
            lowered = column.name.lower()
            if any(word in lowered for word in OPINION_WORDS):
                if (table_name, column.name) not in ALLOWED:
                    offenders.append(f'{table_name}.{column.name}')

    assert not offenders, (
        'These ToolsDB columns look like they hold opinion content: '
        + ', '.join(sorted(offenders))
        + '. Votes belong in Polis. If the column holds metadata rather than an answer, '
          'add it to ALLOWED with a reason; see ref_data-model.md.'
    )


def test_participations_holds_no_per_statement_answer():
    """The specific shape that was added and reverted: a per-statement answer map."""
    suspicious = [
        column.name for column in _tables()['participations'].columns
        if any(word in column.name.lower() for word in OPINION_WORDS)
    ]
    assert suspicious == [], (
        f'participations gained {suspicious}. A participant\'s own answers must not live '
        'next to their identity -- that is one join from mw_username.'
    )


def test_the_guard_would_catch_a_reintroduction():
    """Non-vacuity: prove the check fails when such a column exists.

    Without this, a broken predicate (say OPINION_WORDS emptied) would leave both tests
    passing over nothing, which is the failure mode this file exists to prevent.
    """
    import sqlalchemy as sa

    table = _tables()['participations']
    planted = sa.Column('phase6_choices', sa.JSON(), nullable=True)
    table.append_column(planted)
    try:
        offenders = [
            column.name for column in table.columns
            if any(word in column.name.lower() for word in OPINION_WORDS)
        ]
        assert 'phase6_choices' in offenders
    finally:
        table._columns.remove(planted)

    assert 'phase6_choices' not in [c.name for c in _tables()['participations'].columns]

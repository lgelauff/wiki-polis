"""#616 migration: plain text stored nh3-escaped is converted back once."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

MIGRATION_PATH = (
    Path(__file__).parents[1] / 'migrations' / 'versions' / 'b8c9d0e1f2a3_store_text_clean.py'
)


def _migration_module():
    spec = spec_from_file_location('clean_text_migration', MIGRATION_PATH)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _old_schema(metadata):
    sa.Table('arguments', metadata,
             sa.Column('id', sa.Integer, primary_key=True),
             sa.Column('body', sa.String(280), nullable=False))
    sa.Table('conversation_bans', metadata,
             sa.Column('id', sa.Integer, primary_key=True),
             sa.Column('summary', sa.Text, nullable=True),
             sa.Column('lift_summary', sa.Text, nullable=True))
    sa.Table('content_flags', metadata,
             sa.Column('id', sa.Integer, primary_key=True),
             sa.Column('detail', sa.Text, nullable=True),
             sa.Column('resolution_note', sa.Text, nullable=True))


def _column_length(engine, table, column):
    for info in sa.inspect(engine).get_columns(table):
        if info['name'] == column:
            return getattr(info['type'], 'length', None)


def test_upgrade_unescapes_every_column_once_and_widens_the_argument_body():
    migration = _migration_module()
    metadata = sa.MetaData()
    _old_schema(metadata)
    engine = sa.create_engine('sqlite://')
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(sa.text(
            "INSERT INTO arguments (id, body) VALUES "
            "(1, 'Tom &amp; Jerry'), (2, '1 &lt; 2 &gt; 0'), (3, 'plain'), "
            "(4, 'typed &amp;amp; once')"
        ))
        connection.execute(sa.text(
            "INSERT INTO conversation_bans (id, summary, lift_summary) VALUES "
            "(1, 'A &amp; B', NULL), (2, NULL, 'C &lt;D&gt;')"
        ))
        connection.execute(sa.text(
            "INSERT INTO content_flags (id, detail, resolution_note) VALUES "
            "(1, 'x &amp; y', 'done &amp; dusted'), (2, NULL, NULL)"
        ))

    with engine.begin() as connection:
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()

    with engine.connect() as connection:
        bodies = dict(connection.execute(sa.text('SELECT id, body FROM arguments')).all())
        bans = connection.execute(sa.text(
            'SELECT summary, lift_summary FROM conversation_bans ORDER BY id')).all()
        flags = connection.execute(sa.text(
            'SELECT detail, resolution_note FROM content_flags ORDER BY id')).all()
    assert bodies == {1: 'Tom & Jerry', 2: '1 < 2 > 0', 3: 'plain',
                      4: 'typed &amp; once'}   # one unescape only
    assert [tuple(row) for row in bans] == [('A & B', None), (None, 'C <D>')]
    assert [tuple(row) for row in flags] == [('x & y', 'done & dusted'), (None, None)]
    assert _column_length(engine, 'arguments', 'body') == 1000

    with engine.begin() as connection:
        migration.op = Operations(MigrationContext.configure(connection))
        migration.downgrade()
    assert _column_length(engine, 'arguments', 'body') == 280
    with engine.connect() as connection:
        assert connection.execute(sa.text(
            'SELECT body FROM arguments WHERE id = 1')).scalar() == 'Tom &amp; Jerry'


def test_downgrade_refuses_while_an_argument_is_longer_than_280():
    migration = _migration_module()
    metadata = sa.MetaData()
    _old_schema(metadata)
    engine = sa.create_engine('sqlite://')
    metadata.create_all(engine)
    with engine.begin() as connection:
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        connection.execute(sa.text('INSERT INTO arguments (id, body) VALUES (1, :b), (2, :s)'),
                           {'b': 'é' * 281, 's': 'short'})

    with engine.begin() as connection:
        migration.op = Operations(MigrationContext.configure(connection))
        try:
            migration.downgrade()
        except RuntimeError as error:
            assert str(error).endswith('longer: 1')
        else:
            raise AssertionError('downgrade narrowed a 281-character argument')
    assert _column_length(engine, 'arguments', 'body') == 1000


def test_up_down_up_gives_back_the_text_stored_in_between():
    migration = _migration_module()
    metadata = sa.MetaData()
    _old_schema(metadata)
    engine = sa.create_engine('sqlite://')
    metadata.create_all(engine)

    def run(step):
        with engine.begin() as connection:
            migration.op = Operations(MigrationContext.configure(connection))
            step()

    with engine.begin() as connection:
        connection.execute(sa.text("INSERT INTO arguments (id, body) VALUES (1, 'A &amp; B')"))
        connection.execute(sa.text(
            "INSERT INTO content_flags (id, detail, resolution_note) VALUES (1, NULL, NULL)"))
    run(migration.upgrade)
    typed = {2: 'typed &amp; literally', 3: '1 < 2 > 0 & more'}
    with engine.begin() as connection:
        for row_id, body in typed.items():
            connection.execute(sa.text('INSERT INTO arguments (id, body) VALUES (:i, :b)'),
                               {'i': row_id, 'b': body})
        connection.execute(sa.text("UPDATE content_flags SET detail = 'x &amp; y' WHERE id = 1"))
    run(migration.downgrade)
    with engine.connect() as connection:
        assert connection.execute(sa.text(
            'SELECT body FROM arguments WHERE id = 3')).scalar() == '1 &lt; 2 &gt; 0 &amp; more'
    run(migration.upgrade)
    with engine.connect() as connection:
        bodies = dict(connection.execute(sa.text('SELECT id, body FROM arguments')).all())
        detail = connection.execute(sa.text('SELECT detail FROM content_flags')).scalar()
    assert bodies == {1: 'A & B', **typed}
    assert detail == 'x &amp; y'


def test_downgrade_counts_the_escaped_length():
    migration = _migration_module()
    metadata = sa.MetaData()
    _old_schema(metadata)
    engine = sa.create_engine('sqlite://')
    metadata.create_all(engine)
    with engine.begin() as connection:
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        connection.execute(sa.text('INSERT INTO arguments (id, body) VALUES (5, :b)'),
                           {'b': 'a' * 270 + '&' * 10})   # 280 typed, 320 escaped
    with engine.begin() as connection:
        migration.op = Operations(MigrationContext.configure(connection))
        try:
            migration.downgrade()
        except RuntimeError as error:
            assert str(error).endswith('longer: 5')
        else:
            raise AssertionError('downgrade narrowed an argument longer than 280 escaped')

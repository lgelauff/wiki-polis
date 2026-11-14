"""The phase-scheduler job must not fail while a deploy has new code but no migration yet (#456)."""

from unittest.mock import patch

from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory

from db import db


_EMPTY_RUN = {'fired': 0, 'aborted': 0, 'skipped': 0, 'failed': 0}


def test_scheduler_skips_and_exits_0_while_migrations_are_pending(app):
    # The test database is built with create_all() and never stamped: its revision is not head.
    with patch('app._process_due_scheduled_transitions', return_value=_EMPTY_RUN) as run:
        result = app.test_cli_runner().invoke(args=['process-phase-schedules'])

    assert result.exit_code == 0, result.output
    run.assert_not_called()


def test_scheduler_runs_when_the_database_is_at_head(app):
    # Stamp through MigrationContext, not flask_migrate.stamp: that runs migrations/env.py,
    # whose fileConfig() disables the app's loggers for every later test.
    with app.app_context():
        script = ScriptDirectory.from_config(app.extensions['migrate'].migrate.get_config())
        with db.engine.begin() as conn:
            MigrationContext.configure(conn).stamp(script, 'head')
    with patch('app._process_due_scheduled_transitions', return_value=_EMPTY_RUN) as run:
        result = app.test_cli_runner().invoke(args=['process-phase-schedules'])

    assert result.exit_code == 0, result.output
    run.assert_called_once()

"""#616: the read-only list of seeds stored HTML-escaped before the fix."""
from unittest.mock import patch

from db import FeaturedStatement, db


def _row(tid, txt, is_seed=True):
    return {'tid': tid, 'txt': txt, 'mod': 1, 'is_seed': is_seed,
            'agree_count': 0, 'disagree_count': 0, 'pass_count': 0}


def test_lists_escaped_seeds_in_polis_and_in_the_cache(app, conversation):
    db.session.add(FeaturedStatement(conversation_id=conversation.id, polis_statement_id=7,
                                     statement_text='Cats &lt;3 dogs'))
    db.session.commit()
    buckets = ([], [_row(3, 'Tom &amp; Jerry'), _row(4, 'Plain seed'),
                    _row(5, 'Typed &amp; by a participant', is_seed=False)], [])
    with patch('app._load_admin_statement_sources', return_value=(buckets, False)):
        result = app.test_cli_runner().invoke(args=['escaped-seeds'])
    assert result.exit_code == 0, result.output
    lines = result.stdout.splitlines()
    assert lines == [
        f'{conversation.slug}\tpolis\t3\tTom &amp; Jerry\tTom & Jerry',
        f'{conversation.slug}\tcache\t7\tCats &lt;3 dogs\tCats <3 dogs',
    ]
    assert '2 escaped text(s) found.' in result.stderr


def test_says_when_polis_cannot_be_reached(app, conversation):
    with patch('app._load_admin_statement_sources', return_value=(None, None)):
        result = app.test_cli_runner().invoke(
            args=['escaped-seeds', conversation.slug])
    assert result.exit_code == 0
    assert 'not checked' in result.stderr


def test_refuses_an_unknown_slug(app):
    result = app.test_cli_runner().invoke(args=['escaped-seeds', 'no-such-slug'])
    assert result.exit_code != 0


def test_clear_cache_empties_only_the_escaped_copies(app, conversation):
    escaped = FeaturedStatement(conversation_id=conversation.id, polis_statement_id=7,
                                statement_text='Cats &lt;3 dogs')
    clean = FeaturedStatement(conversation_id=conversation.id, polis_statement_id=8,
                              statement_text='Cats and dogs')
    db.session.add_all([escaped, clean])
    db.session.commit()
    with patch('app._load_admin_statement_sources', return_value=(([], [], []), False)):
        result = app.test_cli_runner().invoke(args=['escaped-seeds', '--clear-cache'])
    assert result.exit_code == 0, result.output
    db.session.refresh(escaped)
    db.session.refresh(clean)
    assert escaped.statement_text is None
    assert clean.statement_text == 'Cats and dogs'


def test_without_the_flag_nothing_is_written(app, conversation):
    featured = FeaturedStatement(conversation_id=conversation.id, polis_statement_id=7,
                                 statement_text='Cats &lt;3 dogs')
    db.session.add(featured)
    db.session.commit()
    with patch('app._load_admin_statement_sources', return_value=(([], [], []), False)):
        app.test_cli_runner().invoke(args=['escaped-seeds'])
    db.session.refresh(featured)
    assert featured.statement_text == 'Cats &lt;3 dogs'

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
    unflagged = {'tid': 9, 'txt': 'R&amp;D\tnote'}
    buckets = ([], [_row(3, 'Tom &amp; Jerry'), _row(4, 'Plain seed'),
                    _row(5, 'Typed &amp; by a participant', is_seed=False),
                    _row(6, 'Pourquoi&nbsp;?'), unflagged], [])
    with patch('app._load_admin_statement_sources', return_value=(buckets, False)):
        result = app.test_cli_runner().invoke(args=['escaped-seeds'])
    assert result.exit_code == 0, result.output
    lines = result.stdout.splitlines()
    assert lines == [
        f'{conversation.slug}\tpolis\t3\tTom &amp; Jerry\tTom & Jerry',
        f'{conversation.slug}\tpolis\t6\tPourquoi&nbsp;?\tPourquoi\\xa0?',
        f'{conversation.slug}\tcache\t7\tCats &lt;3 dogs\tCats <3 dogs',
        f'{conversation.slug}\tpolis-unflagged\t9\tR&amp;D\\tnote\tR&D\\tnote',
    ]
    assert '4 escaped text(s) found.' in result.stderr


def test_says_when_polis_cannot_be_reached(app, conversation):
    with patch('app._load_admin_statement_sources', return_value=(None, None)):
        result = app.test_cli_runner().invoke(
            args=['escaped-seeds', conversation.slug])
    assert result.exit_code == 0
    assert 'not checked' in result.stderr


def test_refuses_an_unknown_slug(app):
    result = app.test_cli_runner().invoke(args=['escaped-seeds', 'no-such-slug'])
    assert result.exit_code != 0


def _featured(conversation, tid, text):
    featured = FeaturedStatement(conversation_id=conversation.id, polis_statement_id=tid,
                                 statement_text=text)
    db.session.add(featured)
    return featured


def test_refresh_cache_copies_the_fixed_polis_text(app, conversation):
    fixed = _featured(conversation, 7, 'Cats &lt;3 dogs')
    still = _featured(conversation, 8, 'Tom &amp; Jerry')
    missing = _featured(conversation, 9, 'Gone &amp; away')
    clean = _featured(conversation, 10, 'Cats and dogs')
    db.session.commit()
    buckets = ([], [_row(7, 'Cats <3 dogs'), _row(8, 'Tom &amp; Jerry'),
                    _row(10, 'Cats and dogs')], [])
    with patch('app._load_admin_statement_sources', return_value=(buckets, False)):
        result = app.test_cli_runner().invoke(args=['escaped-seeds', '--refresh-cache'])
    assert result.exit_code == 0, result.output
    for row in (fixed, still, missing, clean):
        db.session.refresh(row)
    assert fixed.statement_text == 'Cats <3 dogs'
    assert still.statement_text == 'Tom &amp; Jerry'
    assert missing.statement_text == 'Gone &amp; away'
    assert clean.statement_text == 'Cats and dogs'
    assert '1 cache row(s) refreshed.' in result.stderr


def test_refresh_cache_leaves_everything_when_polis_cannot_be_reached(app, conversation):
    featured = _featured(conversation, 7, 'Cats &lt;3 dogs')
    db.session.commit()
    with patch('app._load_admin_statement_sources', return_value=(None, None)):
        result = app.test_cli_runner().invoke(args=['escaped-seeds', '--refresh-cache'])
    assert result.exit_code == 0, result.output
    db.session.refresh(featured)
    assert featured.statement_text == 'Cats &lt;3 dogs'


class _Round6Client:
    def __init__(self, rows):
        self.rows = rows

    def get_statements(self, conversation_id):
        return self.rows


def test_round6_copies_are_listed_and_hold_back_only_their_own_statement(app, conversation):
    conversation.phase6_polis_conversation_id = 'round6conv'
    mapped = _featured(conversation, 7, 'Cats &lt;3 dogs')
    mapped.phase6_polis_statement_id = 70
    unmapped = _featured(conversation, 8, 'Tom &amp; Jerry')       # matched by text
    free = _featured(conversation, 9, 'Salt &amp; pepper')
    free.phase6_polis_statement_id = 90
    db.session.commit()
    buckets = ([], [_row(7, 'Cats <3 dogs'), _row(8, 'Tom & Jerry'),
                    _row(9, 'Salt & pepper')], [])
    round6 = ([], [_row(70, 'Cats &lt;3 dogs'), _row(80, 'tom &amp; jerry'),
                   _row(90, 'Salt & pepper'),
                   _row(91, 'A participant typed R&amp;D', is_seed=False)], [])
    with patch('app._load_admin_statement_sources', return_value=(buckets, False)), \
            patch('app._polis_server_client', return_value=_Round6Client(round6)):
        result = app.test_cli_runner().invoke(args=['escaped-seeds', '--refresh-cache'])
    assert result.exit_code == 0, result.output
    assert f'{conversation.slug}\tround6\t70\tCats &lt;3 dogs\tCats <3 dogs' in result.stdout
    for row in (mapped, unmapped, free):
        db.session.refresh(row)
    assert mapped.statement_text == 'Cats &lt;3 dogs'
    assert unmapped.statement_text == 'Tom &amp; Jerry'
    # A participant's own Round 6 text with an entity holds nothing back.
    assert free.statement_text == 'Salt & pepper'
    assert '1 cache row(s) refreshed.' in result.stderr

    round6 = ([], [_row(70, 'Cats <3 dogs'), _row(80, 'Tom & Jerry'), _row(90, 'Salt & pepper'),
                   _row(91, 'A participant typed R&amp;D', is_seed=False)], [])
    with patch('app._load_admin_statement_sources', return_value=(buckets, False)), \
            patch('app._polis_server_client', return_value=_Round6Client(round6)):
        result = app.test_cli_runner().invoke(args=['escaped-seeds', '--refresh-cache'])
    for row in (mapped, unmapped):
        db.session.refresh(row)
    assert mapped.statement_text == 'Cats <3 dogs'
    assert unmapped.statement_text == 'Tom & Jerry'


def test_a_stale_round6_mapping_still_holds_back_the_escaped_copy(app, conversation):
    """The re-sync matches Round 6 by text, so an escaped copy at another tid than the
    mapped one still holds the refresh back (else it adds a duplicate and hides the copy)."""
    conversation.phase6_polis_conversation_id = 'round6conv'
    featured = _featured(conversation, 7, 'Cats &lt;3 dogs')
    featured.phase6_polis_statement_id = 70          # stale: the live copy is tid 71
    db.session.commit()
    buckets = ([], [_row(7, 'Cats <3 dogs')], [])
    round6 = ([], [_row(70, 'something else'), _row(71, 'Cats &lt;3 dogs')], [])
    with patch('app._load_admin_statement_sources', return_value=(buckets, False)), \
            patch('app._polis_server_client', return_value=_Round6Client(round6)):
        result = app.test_cli_runner().invoke(args=['escaped-seeds', '--refresh-cache'])
    assert result.exit_code == 0, result.output
    db.session.refresh(featured)
    assert featured.statement_text == 'Cats &lt;3 dogs'


def test_refresh_waits_when_round6_cannot_be_read(app, conversation):
    conversation.phase6_polis_conversation_id = 'round6conv'
    featured = _featured(conversation, 7, 'Cats &lt;3 dogs')
    db.session.commit()
    buckets = ([], [_row(7, 'Cats <3 dogs')], [])
    with patch('app._load_admin_statement_sources', return_value=(buckets, False)), \
            patch('app._polis_server_client', return_value=_Round6Client(None)):
        result = app.test_cli_runner().invoke(args=['escaped-seeds', '--refresh-cache'])
    assert result.exit_code == 0, result.output
    db.session.refresh(featured)
    assert featured.statement_text == 'Cats &lt;3 dogs'


def test_without_the_flag_nothing_is_written(app, conversation):
    featured = FeaturedStatement(conversation_id=conversation.id, polis_statement_id=7,
                                 statement_text='Cats &lt;3 dogs')
    db.session.add(featured)
    db.session.commit()
    with patch('app._load_admin_statement_sources', return_value=(([], [], []), False)):
        app.test_cli_runner().invoke(args=['escaped-seeds'])
    db.session.refresh(featured)
    assert featured.statement_text == 'Cats &lt;3 dogs'

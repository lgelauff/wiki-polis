"""#143 statement provenance — capture + lineage resolver (the socket + stub).

Covers: a derivative seed writes a provenance row keyed by the NEW tid; the distance
scorer is best-effort (stub None, and a raising scorer still commits the link); the
lineage resolver walks a chain to its root; and the audit detail carries derived_from.
"""
import logging
from unittest.mock import MagicMock, patch

from db import Conversation, Participant, Participation, StatementProvenance, db


def _login_admin(client, app):
    with app.app_context():
        p = Participant(mw_user_id=7, mw_username='Mod', xid='a' * 64, is_global_admin=True)
        db.session.add(p)
        db.session.commit()
    with client.session_transaction() as s:
        s['xid'] = 'a' * 64
        s['username'] = 'Mod'


def _conv(app, slug='provc'):
    with app.app_context():
        c = Conversation(slug=slug, title='Prov', active=True, polis_id='pz')
        db.session.add(c)
        db.session.commit()
        return c.id


# ── record_statement_provenance / helpers ───────────────────────────────────

def test_record_provenance_writes_row_with_char_score(app):
    from app import record_statement_provenance
    conv_id = _conv(app)
    with app.app_context():
        # No texts → link recorded, but no scores computed.
        row = record_statement_provenance(conv_id, new_tid=20, derived_from_tid=11)
        assert row is not None
        got = StatementProvenance.query.filter_by(conversation_id=conv_id,
                                                  polis_statement_id=20).one()
        assert got.derived_from_tid == 11
        assert got.provenance_type == 'derivative'
        assert got.link_method == 'declared'
        assert got.scores == []
        # With texts → the always-available 'char' similarity is written; 'semantic' (stub) is not.
        record_statement_provenance(conv_id, 21, 11, parent_text='the cat sat', new_text='the cat sat down')
        r = StatementProvenance.query.filter_by(conversation_id=conv_id, polis_statement_id=21).one()
        models = {s.model: s.value for s in r.scores}
        assert 'char' in models and 0.0 <= models['char'] <= 1.0   # similarity, higher = more similar
        assert 'semantic' not in models             # #207 stub returns None → no row


def test_distance_scorers_best_effort(app, monkeypatch):
    import app as appmod
    from app import record_statement_provenance
    conv_id = _conv(app, 'provd')
    # A working 'semantic' scorer (simulating #207) adds a second score alongside 'char'.
    monkeypatch.setitem(appmod._SIMILARITY_SCORERS, 'semantic', lambda a, b: 0.25)
    with app.app_context():
        record_statement_provenance(conv_id, 30, 12, parent_text='p', new_text='n')
        r = StatementProvenance.query.filter_by(conversation_id=conv_id, polis_statement_id=30).one()
        models = {s.model: s.value for s in r.scores}
        assert models.get('semantic') == 0.25 and 'char' in models   # multiple kinds coexist
    # A raising scorer must NOT block the link or the other scores.
    monkeypatch.setitem(appmod._SIMILARITY_SCORERS, 'semantic',
                        lambda a, b: (_ for _ in ()).throw(RuntimeError('boom')))
    with app.app_context():
        row = record_statement_provenance(conv_id, 31, 12, parent_text='p', new_text='n')
        assert row is not None
        r = StatementProvenance.query.filter_by(conversation_id=conv_id, polis_statement_id=31).one()
        models = {s.model for s in r.scores}
        assert 'char' in models and 'semantic' not in models   # char still recorded, semantic skipped


def test_semantic_similarity_sidecar_score_is_recorded(app):
    from app import record_statement_provenance
    conv_id = _conv(app, 'provsemantic')
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = {'similarity': 0.82}
    app.config['STATEMENT_SIMILARITY_URL'] = 'http://sidecar/similarity'
    with app.app_context(), patch('app.requests.post', return_value=resp) as post:
        record_statement_provenance(conv_id, 40, 12,
                                    parent_text='the parent statement',
                                    new_text='the revised parent statement')
        r = StatementProvenance.query.filter_by(conversation_id=conv_id,
                                                polis_statement_id=40).one()
        models = {s.model: s.value for s in r.scores}
    assert models['semantic'] == 0.82
    assert 'char' in models
    assert post.call_args.kwargs['json'] == {
        'left': 'the parent statement',
        'right': 'the revised parent statement',
    }


def test_lineage_group_walks_to_root(app):
    from app import _lineage_group, record_statement_provenance
    conv_id = _conv(app, 'provl')
    with app.app_context():
        record_statement_provenance(conv_id, 3, 2)   # 3 derived from 2
        record_statement_provenance(conv_id, 2, 1)   # 2 derived from 1 (root)
        assert _lineage_group(conv_id, 3) == [3, 2, 1]
        assert _lineage_group(conv_id, 1) == [1]     # a root resolves to itself


def test_lineage_group_cycle_safe(app):
    from app import _lineage_group, record_statement_provenance
    conv_id = _conv(app, 'provcyc')
    with app.app_context():
        record_statement_provenance(conv_id, 5, 6)
        record_statement_provenance(conv_id, 6, 5)   # cycle
        chain = _lineage_group(conv_id, 5)
        assert chain[0] == 5 and len(chain) <= 3     # terminates, no infinite loop


# ── Admin seed writes provenance + audit when derivedFromId is given ─────────

def test_seed_derivative_route_records_provenance_and_audit(client, app):
    from unittest.mock import patch

    from db import AuditEvent
    _login_admin(client, app)
    conv_id = _conv(app, 'provseed')
    with patch('app.PolisServerClient.add_seed_return_id', return_value=99) as add_id, \
         patch('app._statement_text_map', return_value={11: 'parent text'}):
        r = client.post(f'/api/v1/admin/conversations/{conv_id}/statements',
                        json={'text': 'a corrected statement', 'derivedFromId': 11})
    assert r.status_code == 201
    add_id.assert_called_once()                       # used the id-returning seed
    with app.app_context():
        prov = StatementProvenance.query.filter_by(conversation_id=conv_id, polis_statement_id=99).one()
        assert prov.derived_from_tid == 11
        audit = AuditEvent.query.filter_by(operation='statement.seed').all()
        assert audit and audit[0].detail.get('derived_from') == 11
        assert audit[0].target_id == '99'


def test_seed_derivative_unknown_tid_is_rejected(client, app):
    """A derivedFromId not in this conversation → reject, seed nothing, record nothing."""
    from unittest.mock import patch
    _login_admin(client, app)
    conv_id = _conv(app, 'provbad')
    with patch('app._statement_text_map', return_value={5: 'a real one'}), \
         patch('app.PolisServerClient.add_seed_return_id') as add_id:
        resp = client.post(f'/api/v1/admin/conversations/{conv_id}/statements',
                           json={'text': 'x', 'derivedFromId': 999})
    # Checking the rejection is what keeps the two negative assertions below
    # meaningful: without it they also hold when the request never routes at all.
    assert resp.status_code == 404
    assert resp.get_json()['error']['code'] == 'derived_statement_not_found'
    add_id.assert_not_called()                        # nothing seeded
    with app.app_context():
        assert StatementProvenance.query.filter_by(conversation_id=conv_id).count() == 0


def test_plain_seed_route_writes_no_provenance(client, app):
    from unittest.mock import patch
    _login_admin(client, app)
    conv_id = _conv(app, 'provplain')
    with patch('app.PolisServerClient.add_seed'):
        resp = client.post(f'/api/v1/admin/conversations/{conv_id}/statements',
                           json={'text': 'just a new one', 'derivedFromId': None})
    assert resp.status_code == 201                    # the seed really was accepted
    with app.app_context():
        assert StatementProvenance.query.filter_by(conversation_id=conv_id).count() == 0


# ── Participant derivative submissions (#143/#210) ───────────────────────────

def _fake_upstream(status_code=200, content=b'{}', cookies=None):
    m = MagicMock()
    m.status_code = status_code
    m.ok = status_code < 400
    m.content = content
    m.headers = {'Content-Type': 'application/json'}
    m.cookies = cookies or {}
    return m


def _login_participant_for_submission(client, app):
    with app.app_context():
        p = Participant(mw_user_id=17, mw_username='Submitter', xid='b' * 64)
        c = Conversation(slug='subderiv', title='Sub', active=True, polis_id='subpolis',
                         phase_submission=True)
        db.session.add_all([p, c])
        db.session.commit()
        db.session.add(Participation(participant_id=p.id, conversation_id=c.id,
                                     pseudonym='submit-fox'))
        db.session.commit()
        conv_id = c.id
    with client.session_transaction() as s:
        s['xid'] = 'b' * 64
        s['username'] = 'Submitter'
        # Pre-seed the upstream session so a submit makes exactly one Particiapi
        # call, the way the API tests in test_explore_api.py do.
        s['particiapi_api_sessions'] = {
            str(conv_id): {'cookie': 'existing-cookie', 'csrfToken': 'existing-csrf'},
        }


def test_participant_derivative_submission_records_provenance(client, app):
    _login_participant_for_submission(client, app)
    stmt_resp = _fake_upstream(status_code=201, content=b'{"id":777}')
    stmt_resp.json = lambda: {'id': 777}

    with patch('app._statement_text_map', return_value={12: 'parent statement'}), \
         patch('app.polis_http.post', return_value=stmt_resp):
        resp = client.post('/api/v1/conversations/subderiv/statements',
                           headers={'Idempotency-Key': 'prov-key-777'},
                           json={'text': 'parent statement improved',
                                 'derivedFromStatementId': 12})

    assert resp.status_code == 201
    with app.app_context():
        row = StatementProvenance.query.filter_by(polis_statement_id=777).one()
        assert row.derived_from_tid == 12
        assert {s.model for s in row.scores} == {'char'}


def test_participant_derivative_submission_rejects_below_similarity_bound(client, app):
    _login_participant_for_submission(client, app)
    app.config['STATEMENT_DERIVATIVE_MIN_SIMILARITY'] = 0.8

    with patch('app._statement_text_map', return_value={12: 'cats are good'}), \
         patch('app.polis_http.post') as post:
        resp = client.post('/api/v1/conversations/subderiv/statements',
                           headers={'Idempotency-Key': 'prov-key-low'},
                           json={'text': 'unrelated policy claim',
                                 'derivedFromStatementId': 12})

    assert resp.status_code == 409
    error = resp.get_json()['error']
    assert error['code'] == 'derivative_similarity_too_low'
    assert error['details']['model'] == 'char'
    post.assert_not_called()
    with app.app_context():
        assert StatementProvenance.query.count() == 0


def test_derivative_submission_scores_similarity_once(client, app):
    """A6 dedupe: the gate scores the pair, and provenance reuses those scores rather
    than recomputing (which would repeat the similarity sidecar call)."""
    _login_participant_for_submission(client, app)
    stmt_resp = _fake_upstream(status_code=201, content=b'{"id":778}')
    stmt_resp.json = lambda: {'id': 778}

    with patch('app._statement_text_map', return_value={12: 'parent statement'}), \
         patch('app._statement_similarity_scores', return_value={'char': 0.9}) as sim, \
         patch('app.polis_http.post', return_value=stmt_resp):
        resp = client.post('/api/v1/conversations/subderiv/statements',
                           headers={'Idempotency-Key': 'prov-key-778'},
                           json={'text': 'parent statement improved',
                                 'derivedFromStatementId': 12})

    assert resp.status_code == 201
    assert sim.call_count == 1   # scored once for the gate, reused for provenance
    with app.app_context():
        row = StatementProvenance.query.filter_by(polis_statement_id=778).one()
        assert {s.model for s in row.scores} == {'char'}


def test_quota_exceeded_rejects_before_upstream(client, app):
    """A6: the optimistic quota fast-fail rejects an over-quota submit before any
    Particiapi call, so a quota-rejected request never creates an orphaned statement."""
    _login_participant_for_submission(client, app)
    with app.app_context():
        part = Participation.query.filter_by(pseudonym='submit-fox').one()
        part.new_stmt_ids = [1, 2, 3]   # default quota is 3
        db.session.commit()

    with patch('app.polis_http.post') as post:
        resp = client.post('/api/v1/conversations/subderiv/statements',
                           headers={'Idempotency-Key': 'prov-key-quota'},
                           json={'text': 'one more statement'})

    # The JSON API reports the exhausted quota as 409 statement_quota_exceeded,
    # where the Jinja route answered 403 quota_exceeded.
    assert resp.status_code == 409
    assert resp.get_json()['error']['code'] == 'statement_quota_exceeded'
    post.assert_not_called()   # rejected before any Particiapi submit

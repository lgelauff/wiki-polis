"""Executable completeness gates for the Jinja-to-React parity program."""

import hashlib
import json
from pathlib import Path


V2_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((V2_ROOT / 'parity' / 'routes.json').read_text(encoding='utf-8'))


def _declared_endpoints():
    groups = MANIFEST['pages'] + MANIFEST['features']
    return [endpoint for group in groups for endpoint in group['legacyEndpoints']]


def _ui_endpoints(app):
    excluded = {'health', 'spa_shell', 'static'}
    return {
        rule.endpoint
        for rule in app.url_map.iter_rules()
        if not rule.endpoint.startswith(('api_v1.', 'proxy.'))
        and rule.endpoint not in excluded
    }


def _openapi_operation_ids():
    document = json.loads((V2_ROOT / 'openapi.json').read_text(encoding='utf-8'))
    return {
        operation['operationId']
        for path_item in document['paths'].values()
        for operation in path_item.values()
        if isinstance(operation, dict) and 'operationId' in operation
    }


def test_every_registered_legacy_ui_endpoint_is_classified_once(app):
    declared = _declared_endpoints()
    assert len(declared) == len(set(declared)), 'Legacy endpoints must have one owner.'

    conditional = set(MANIFEST['conditionalEndpoints'])
    assert _ui_endpoints(app) == set(declared) - conditional


def test_manifest_accounts_for_every_jinja_template():
    declared = set(MANIFEST['sharedTemplates'])
    declared.update(
        template
        for page in MANIFEST['pages']
        for template in page['templates']
    )
    actual = {path.name for path in (V2_ROOT / 'templates').glob('*.html')}
    assert actual == declared


def test_manifest_references_real_api_operations():
    actual = _openapi_operation_ids()
    referenced = {
        operation
        for group in MANIFEST['pages'] + MANIFEST['features']
        for operation in group['apiOperations']
    }
    assert referenced <= actual


def test_page_entries_define_routes_states_and_valid_statuses():
    allowed_statuses = set(MANIFEST['statusValues'])
    ids = [page['id'] for page in MANIFEST['pages']]
    assert len(ids) == len(set(ids))
    for page in MANIFEST['pages']:
        assert page['legacyRoutes']
        assert page['targetReactRoutes']
        assert page['scenarios']
        assert page['status'] in allowed_statuses


def test_parity_status_requires_no_known_api_gap():
    blocked_pages = {
        page_id
        for gap in MANIFEST['knownApiGaps']
        for page_id in gap['requiredBy']
    }
    statuses = {page['id']: page['status'] for page in MANIFEST['pages']}
    assert all(statuses[page_id] != 'parity' for page_id in blocked_pages)


def test_visual_scenarios_reference_declared_pages_and_states():
    visual = json.loads(
        (V2_ROOT / 'parity' / 'visual-scenarios.json').read_text(encoding='utf-8')
    )
    pages = {page['id']: page for page in MANIFEST['pages']}
    ids = [scenario['id'] for scenario in visual['scenarios']]
    assert len(ids) == len(set(ids))
    for scenario in visual['scenarios']:
        page = pages[scenario['pageId']]
        assert scenario['state'] in page['scenarios']
        assert scenario['legacyPath'].startswith('/')
        assert scenario['reactPath'] is None or scenario['reactPath'].startswith('/')
        assert scenario['auth'] in {
            'anonymous', 'dev-admin', 'dev-user-1', 'dev-user-2', 'dev-user-3'
        }
        assert scenario.get('serverFixture', 'dev') in {'dev', 'isolated'}
        assert scenario['viewport']['width'] > 0
        assert scenario['viewport']['height'] > 0


def test_parity_pages_require_gated_visual_scenarios():
    visual = json.loads(
        (V2_ROOT / 'parity' / 'visual-scenarios.json').read_text(encoding='utf-8')
    )
    gated_pages = {
        scenario['pageId']
        for scenario in visual['scenarios']
        if scenario['parityGate']
    }
    parity_pages = {
        page['id'] for page in MANIFEST['pages'] if page['status'] == 'parity'
    }
    assert parity_pages <= gated_pages


def test_committed_golden_images_match_manifest_digests():
    visual = json.loads(
        (V2_ROOT / 'parity' / 'visual-scenarios.json').read_text(encoding='utf-8')
    )
    golden_root = V2_ROOT.parent / 'output' / 'playwright' / 'golden'
    for scenario in visual['scenarios']:
        golden = golden_root / f"{scenario['id']}.png"
        assert golden.is_file(), f'Missing Jinja golden: {golden}'
        digest = hashlib.sha256(golden.read_bytes()).hexdigest()
        assert digest == scenario['goldenSha256']


def test_completed_parity_program_stays_fully_gated():
    visual = json.loads(
        (V2_ROOT / 'parity' / 'visual-scenarios.json').read_text(encoding='utf-8')
    )
    groups = MANIFEST['pages'] + MANIFEST['features']

    assert MANIFEST['knownApiGaps'] == []
    assert all(group['status'] == 'parity' for group in groups)
    assert all(scenario['parityGate'] is True for scenario in visual['scenarios'])

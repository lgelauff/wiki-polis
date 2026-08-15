from pathlib import Path


SPA_DOCUMENT = Path(__file__).parents[1] / 'frontend' / 'index.html'
SPA_ENTRYPOINT = Path(__file__).parents[1] / 'frontend' / 'src' / 'main.tsx'
SPA_SOURCE = SPA_ENTRYPOINT.parent


def test_spa_bundles_parity_styles_after_application_adjustments():
    entrypoint = SPA_ENTRYPOINT.read_text(encoding='utf-8')

    application_styles = entrypoint.index("import './styles.css'")
    legacy_styles = entrypoint.index("import '../../static/style.css'")

    assert application_styles < legacy_styles


def test_spa_preloads_route_specific_admin_styles():
    document = SPA_DOCUMENT.read_text(encoding='utf-8')

    assert 'rel="preload" href="/static/redesign.css" as="style"' in document


def test_react_owned_forms_do_not_fall_back_to_legacy_posts():
    server_form_sources = []
    for source in SPA_SOURCE.rglob('*.tsx'):
        for line in source.read_text(encoding='utf-8').splitlines():
            if '<form' in line and ('action=' in line or 'method=' in line):
                server_form_sources.append((source.relative_to(SPA_SOURCE), line.strip()))
    server_form_sources.sort(key=lambda item: str(item[0]))

    assert server_form_sources == [
        (
            Path('features/admin/admin-routes.tsx'),
            '<form method="post" action={session.links.logout} className="account-form">',
        ),
        (
            Path('features/legacy/legacy-shell.tsx'),
            "<form method=\"post\" action={session.links.logout} style={{display: 'inline'}}>",
        ),
    ]


def test_document_navigation_is_confined_to_the_server_redirect_boundary():
    navigation_sources = []
    for source in SPA_SOURCE.rglob('*.tsx'):
        if 'globalThis.location.assign(' in source.read_text(encoding='utf-8'):
            navigation_sources.append(source.relative_to(SPA_SOURCE))

    assert sorted(navigation_sources) == [Path('features/legacy/external-redirect.tsx')]

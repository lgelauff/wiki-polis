from pathlib import Path


SPA_DOCUMENT = Path(__file__).parents[1] / 'frontend' / 'index.html'
SPA_ENTRYPOINT = Path(__file__).parents[1] / 'frontend' / 'src' / 'main.tsx'


def test_spa_bundles_parity_styles_after_application_adjustments():
    entrypoint = SPA_ENTRYPOINT.read_text(encoding='utf-8')

    application_styles = entrypoint.index("import './styles.css'")
    legacy_styles = entrypoint.index("import '../../static/style.css'")

    assert application_styles < legacy_styles


def test_spa_preloads_route_specific_admin_styles():
    document = SPA_DOCUMENT.read_text(encoding='utf-8')

    assert 'rel="preload" href="/static/redesign.css" as="style"' in document

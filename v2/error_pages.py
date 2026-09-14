"""Branded HTML error pages that render with nothing else working.

Why a Python string and not a template
--------------------------------------
These pages exist for the case where the deploy is broken. ``_SPA_BUILD_DIR``
(``v2/static/spa``) is gitignored and produced at deploy time by
``v2/bin/build-spa.sh``; if that build is missing, stale or half-written, every
canonical path 404s out of ``send_from_directory``. That is precisely when the
error page has to work, so it must not need the SPA bundle, a template loader, a
context processor, or a stylesheet fetched over the network.

Writing these as templates was rejected when ``templates/`` still existed, on the
grounds that a template is one ``{% extends %}`` away from depending on the thing
that is broken. That directory has since been deleted outright, which settles the
question. A module-level string is imported once at process start and has no loader
between the exception and the bytes. The cost is that the markup lives in Python;
the payoff is that there is no configuration under which it can fail to render.

No request data is interpolated, so the page cannot leak internals. Werkzeug's
own ``description`` is deliberately not shown for the same reason. The copy is
no longer entirely static, though — see below — so ``title``, ``message`` and the
error-code label are escaped before they reach the template. ``hint`` is not: it
carries the front-page link. A translation of it may only use the markup its English
uses — the same ``<a href="/">`` — because ``i18n.load()`` refuses any other, so what
reaches the page unescaped is still markup we wrote.

Translation, without giving up the guarantee
--------------------------------------------
The copy is looked up in the message catalogue, because these pages are read by
participants and an English 404 in a Dutch interface is a worse experience than a
translated one. That would ordinarily add exactly the kind of dependency the rest of
this docstring argues against, so every lookup carries its English original as a
fallback: ``i18n`` returns ``⧼key⧽`` for a message it cannot find, and ``_t`` treats
that as a miss. A missing, unreadable or half-written catalogue therefore renders the
same page it rendered before this was added — the guarantee is unchanged, and the
translation is an improvement layered on top of it rather than a new way to fail.
"""

from __future__ import annotations

import html

from flask import g, has_request_context

import i18n

# Cluster palette, inlined from static/style.css. Duplicated on purpose: the point
# of this page is that it does not fetch a stylesheet.
_PAGE = """<!doctype html>
<html lang="{lang}" dir="{dir}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{code} {title} — Proto</title>
<link rel="icon" href="data:,">
<style>
  :root {{
    --ink: #0c0c0e; --body: #3f3f43; --muted: #5f5f68;
    --bg: #fafaf9; --surface: #ffffff; --hairline: #e5e5e6; --blue: #3d6dba;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background: var(--bg); color: var(--body);
    font-family: "Inter Tight", "Inter", system-ui, -apple-system, sans-serif;
    line-height: 1.55; min-height: 100vh;
    display: flex; flex-direction: column;
  }}
  header {{
    border-bottom: 1px solid var(--hairline); background: var(--surface);
    padding: 14px 20px;
  }}
  .brand {{
    display: inline-flex; align-items: center; gap: 8px;
    color: var(--ink); text-decoration: none; font-weight: 600; font-size: 15px;
  }}
  main {{
    flex: 1; display: flex; align-items: center; justify-content: center;
    padding: 48px 20px;
  }}
  .card {{
    background: var(--surface); border: 1px solid var(--hairline);
    border-radius: 10px; padding: 32px; max-width: 34rem; width: 100%;
  }}
  .code {{
    font-family: "JetBrains Mono", ui-monospace, monospace;
    font-size: 13px; letter-spacing: .08em; color: var(--muted);
    text-transform: uppercase;
  }}
  h1 {{ font-size: 24px; color: var(--ink); margin: 6px 0 12px; font-weight: 600; }}
  p {{ margin: 0 0 12px; }}
  p:last-child {{ margin-bottom: 0; }}
  .muted {{ color: var(--muted); font-size: 14px; }}
  a {{ color: var(--blue); }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --ink: #f4f4f3; --body: #d4d4d6; --muted: #a1a1aa;
      --bg: #111113; --surface: #1a1a1d; --hairline: #2e2e33; --blue: #8ab0ea;
    }}
  }}
</style>
</head>
<body>
<header>
  <a class="brand" href="/">
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         stroke-width="1" stroke-linecap="round" stroke-dasharray="1.4 1.6" aria-hidden="true">
      <circle cx="12" cy="12" r="9"/>
      <ellipse cx="12" cy="12" rx="9" ry="3.5"/>
      <ellipse cx="12" cy="12" rx="3.5" ry="9"/>
    </svg>
    <span>Proto</span>
  </a>
</header>
<main>
  <div class="card">
    <p class="code">{code_label}</p>
    <h1>{title}</h1>
    <p>{message}</p>
    <p class="muted">{hint}</p>
  </div>
</main>
</body>
</html>
"""

def _t(key: str, fallback: str) -> str:
    """The catalogue's text for ``key``, or ``fallback`` if it cannot supply one.

    Deliberately total: an error page must not be able to raise. Outside a request there
    is no negotiated locale, so this falls back to the source language.
    """
    try:
        locale = g.get('locale') if has_request_context() else None
        text = i18n.resolve(key, locale or i18n.SOURCE_LOCALE)
    except Exception:          # noqa: BLE001 — see the module docstring
        return fallback
    return fallback if text.startswith(i18n._MISSING_L) else text


# English originals, kept as the fallback for every lookup. These are what renders if the
# catalogue is missing or unreadable, which is the scenario this module exists for.
_ERRORS = {
    404: {
        'title': 'Page not found',
        'message': 'There is nothing at this address.',
        'hint': 'The link may be out of date, or the page may have moved. '
                'Go to <a href="/">the front page</a> to start again.',
    },
    403: {
        'title': 'Not allowed',
        'message': 'You do not have access to this page.',
        'hint': 'If you expected access, you may need to log in as a different '
                'account, or ask an organizer for the role that grants it.',
    },
    500: {
        'title': 'Something went wrong',
        'message': 'The server could not complete this request.',
        'hint': 'This has been logged. Try again in a moment; if it keeps '
                'happening, report it to a site admin.',
    },
}

DEFAULT_ERROR_CODE = 500


def render_error_page(code: int) -> str:
    """Return the full HTML document for ``code``, falling back to the 500 page."""
    detail = _ERRORS.get(code)
    if detail is None:
        code, detail = DEFAULT_ERROR_CODE, _ERRORS[DEFAULT_ERROR_CODE]
    translated = {
        part: _t(f'errorpage-{code}-{part}', english)
        for part, english in detail.items()
    }
    # Catalogue text is not request data, but it is no longer written only by us: it comes
    # back from translatewiki. Escape everything that lands in element text or an attribute.
    # `hint` is left raw on purpose — it carries the front-page link, and i18n.load() has
    # already refused any translation of it that adds markup beyond that link.
    return _PAGE.format(
        code=code,
        lang=html.escape(_page_language(), quote=True),
        dir=html.escape(_page_direction(), quote=True),
        code_label=html.escape(
            _t('errorpage-code', f'Error {code}').replace('$1', str(code))),
        title=html.escape(translated['title']),
        message=html.escape(translated['message']),
        hint=translated['hint'],
    )


def _page_language() -> str:
    """The negotiated locale, or the source language outside a request."""
    try:
        return (has_request_context() and g.get('locale')) or i18n.SOURCE_LOCALE
    except Exception:          # noqa: BLE001 — see the module docstring
        return i18n.SOURCE_LOCALE


def _page_direction() -> str:
    """The negotiated text direction. Without it an RTL locale renders left-to-right, and
    this is the one page the SPA cannot correct afterwards — it renders when the SPA is the
    thing that is broken."""
    try:
        return (has_request_context() and g.get('dir')) or i18n.text_direction(_page_language())
    except Exception:          # noqa: BLE001 — see the module docstring
        return 'ltr'


SUPPORTED_ERROR_CODES = tuple(_ERRORS)

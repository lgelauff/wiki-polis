"""Real-browser gate for canonical React Router navigation."""

from __future__ import annotations

import argparse
import json
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright


def run(base_url: str) -> dict:
    document_requests: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        page.on(
            'request',
            lambda request: document_requests.append(request.url)
            if request.resource_type == 'document' else None,
        )
        try:
            page.goto(f'{base_url}/dev-login', wait_until='networkidle')
            page.goto(f'{base_url}/admin', wait_until='networkidle')
            assert page.get_by_role('switch', name='SPA only on').is_visible()

            before_click = len(document_requests)
            page.get_by_role('link', name='manage').first.click()
            page.wait_for_load_state('networkidle')

            destination = urlparse(page.url).path
            assert destination.startswith('/admin/conversations/')
            assert document_requests[before_click:] == [], (
                'Internal navigation triggered a document request: '
                f'{document_requests[before_click:]}'
            )
            assert page.get_by_role('alertdialog').count() == 0
            assert page.locator('footer code').text_content()

            page.reload(wait_until='networkidle')
            assert urlparse(page.url).path == destination
            assert page.get_by_role('switch', name='SPA only on').is_visible()
            assert page.locator('footer code').text_content()

            return {
                'destination': destination,
                'documentRequestsAfterClick': 0,
                'canonicalReload': 'react',
            }
        finally:
            context.close()
            browser.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:5002')
    args = parser.parse_args()
    result = run(args.base_url.rstrip('/'))
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

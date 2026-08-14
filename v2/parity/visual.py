"""Deterministic Jinja golden capture and React screenshot parity runner."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

from playwright.sync_api import Browser, Page, sync_playwright


V2_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = V2_ROOT.parent
SCENARIO_PATH = V2_ROOT / 'parity' / 'visual-scenarios.json'
DEFAULT_OUTPUT = REPO_ROOT / 'output' / 'playwright'
STABILIZING_CSS = """
*, *::before, *::after {
  animation-delay: 0s !important;
  animation-duration: 0s !important;
  caret-color: transparent !important;
  scroll-behavior: auto !important;
  transition-delay: 0s !important;
  transition-duration: 0s !important;
}
footer code { visibility: hidden !important; }
"""


def load_scenarios(selected: set[str] | None = None) -> tuple[dict, list[dict]]:
    manifest = json.loads(SCENARIO_PATH.read_text(encoding='utf-8'))
    scenarios = manifest['scenarios']
    if selected:
        unknown = selected - {scenario['id'] for scenario in scenarios}
        if unknown:
            raise ValueError(f"Unknown scenario(s): {', '.join(sorted(unknown))}")
        scenarios = [scenario for scenario in scenarios if scenario['id'] in selected]
    return manifest, scenarios


def prepare_page(page: Page, url: str) -> None:
    page.goto(url, wait_until='networkidle')
    page.wait_for_function(
        """() => [...document.styleSheets].some(sheet =>
            sheet.href && new URL(sheet.href).pathname === '/static/style.css'
        )"""
    )
    page.wait_for_function("document.fonts.status === 'loaded'")
    page.add_style_tag(content=STABILIZING_CSS)
    page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")


def authenticate(page: Page, base_url: str, auth: str) -> None:
    if auth == 'anonymous':
        return
    if auth == 'dev-admin':
        page.goto(f'{base_url}/dev-login', wait_until='networkidle')
        return
    if auth.startswith('dev-user-'):
        page.goto(f'{base_url}/dev/login/{auth}', wait_until='networkidle')
        return
    raise ValueError(f'Unsupported auth fixture: {auth}')


def capture(
    browser: Browser,
    *,
    base_url: str,
    defaults: dict,
    scenario: dict,
    path_key: str,
    destination: Path,
) -> None:
    viewport = scenario['viewport']
    context = browser.new_context(
        viewport=viewport,
        locale=defaults['locale'],
        timezone_id=defaults['timezone'],
        color_scheme=defaults['colorScheme'],
        reduced_motion='reduce',
        device_scale_factor=defaults['deviceScaleFactor'],
    )
    try:
        page = context.new_page()
        authenticate(page, base_url, scenario['auth'])
        prepare_page(page, f"{base_url}{scenario[path_key]}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=destination, full_page=defaults['fullPage'])
    finally:
        context.close()


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_capture(args: argparse.Namespace) -> int:
    manifest, scenarios = load_scenarios(set(args.scenario) or None)
    output = Path(args.output).resolve()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            for scenario in scenarios:
                destination = output / 'golden' / f"{scenario['id']}.png"
                capture(
                    browser,
                    base_url=args.base_url,
                    defaults=manifest['defaults'],
                    scenario=scenario,
                    path_key='legacyPath',
                    destination=destination,
                )
                print(f"CAPTURED {scenario['id']} {digest(destination)[:12]}")
        finally:
            browser.close()
    return 0


def run_compare(args: argparse.Namespace) -> int:
    manifest, scenarios = load_scenarios(set(args.scenario) or None)
    output = Path(args.output).resolve()
    failures = 0
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            for scenario in scenarios:
                golden = output / 'golden' / f"{scenario['id']}.png"
                react_path = scenario['reactPath']
                if not golden.exists():
                    print(f"MISSING-GOLDEN {scenario['id']}")
                    if args.require_parity or scenario['parityGate']:
                        failures += 1
                    continue
                if react_path is None:
                    print(f"MISSING-REACT {scenario['id']}")
                    if args.require_parity or scenario['parityGate']:
                        failures += 1
                    continue

                actual = output / 'actual' / f"{scenario['id']}.png"
                capture(
                    browser,
                    base_url=args.base_url,
                    defaults=manifest['defaults'],
                    scenario=scenario,
                    path_key='reactPath',
                    destination=actual,
                )
                if golden.read_bytes() == actual.read_bytes():
                    print(f"MATCH {scenario['id']} {digest(actual)[:12]}")
                else:
                    print(
                        f"DIFF {scenario['id']} golden={digest(golden)[:12]} "
                        f"actual={digest(actual)[:12]}"
                    )
                    if args.require_parity or scenario['parityGate']:
                        failures += 1
        finally:
            browser.close()
    return 1 if failures else 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument('command', choices=('capture', 'compare'))
    result.add_argument(
        '--base-url',
        default=os.environ.get('PARITY_BASE_URL', 'http://127.0.0.1:5001'),
    )
    result.add_argument('--output', default=str(DEFAULT_OUTPUT))
    result.add_argument('--scenario', action='append', default=[])
    result.add_argument('--require-parity', action='store_true')
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == 'capture':
            return run_capture(args)
        return run_compare(args)
    except (OSError, ValueError) as error:
        print(f'parity runner error: {error}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())

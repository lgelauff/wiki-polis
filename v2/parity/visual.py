"""Deterministic Jinja golden capture and React screenshot parity runner."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import zlib

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


def load_scenarios(
    selected: set[str] | None = None,
    fixture: str | None = None,
) -> tuple[dict, list[dict]]:
    manifest = json.loads(SCENARIO_PATH.read_text(encoding='utf-8'))
    scenarios = manifest['scenarios']
    if selected:
        unknown = selected - {scenario['id'] for scenario in scenarios}
        if unknown:
            raise ValueError(f"Unknown scenario(s): {', '.join(sorted(unknown))}")
        scenarios = [scenario for scenario in scenarios if scenario['id'] in selected]
    if fixture:
        scenarios = [
            scenario for scenario in scenarios
            if scenario.get('serverFixture', 'dev') == fixture
        ]
    elif not selected:
        scenarios = [
            scenario for scenario in scenarios
            if scenario.get('serverFixture', 'dev') == 'dev'
        ]
    return manifest, scenarios


def prepare_page(page: Page, url: str, *, require_legacy_stylesheet: bool = True) -> None:
    page.goto(url, wait_until='networkidle')
    stabilize_page(page, require_legacy_stylesheet=require_legacy_stylesheet)


def stabilize_page(page: Page, *, require_legacy_stylesheet: bool = True) -> None:
    if require_legacy_stylesheet:
        page.wait_for_function(
            """() => [...document.styleSheets].some(sheet =>
                sheet.href && new URL(sheet.href).pathname === '/static/style.css'
            )"""
        )
    page.wait_for_function("document.fonts.status === 'loaded'")
    page.add_style_tag(content=STABILIZING_CSS)
    page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")


def run_actions(page: Page, actions: list[dict]) -> None:
    for action in actions:
        action_type = action.get('type')
        if action_type == 'check':
            page.get_by_label(action['label'], exact=True).check()
        elif action_type == 'click':
            target = page.get_by_role(
                action['role'], name=action['name'], exact=True,
            )
            if 'nth' in action:
                target = target.nth(action['nth'])
            target.click()
        else:
            raise ValueError(f'Unsupported visual action: {action_type!r}')
        page.wait_for_load_state('networkidle')
    if actions:
        stabilize_page(page)


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
    if scenario.get('clock'):
        timestamp = scenario['clock']
        context.add_init_script(
            f"Date.now = () => new Date({json.dumps(timestamp)}).getTime();"
        )
    try:
        page = context.new_page()
        authenticate(page, base_url, scenario['auth'])
        require_legacy_stylesheet = scenario.get('legacyStylesheet', True)
        prepare_page(
            page,
            f"{base_url}{scenario[path_key]}",
            require_legacy_stylesheet=require_legacy_stylesheet,
        )
        run_actions(page, scenario.get('actions', []))
        destination.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=destination, full_page=defaults['fullPage'])
    finally:
        context.close()


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def decode_png(path: Path) -> tuple[int, int, int, bytes]:
    raw = path.read_bytes()
    if raw[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError(f'Unsupported image format: {path}')
    offset = 8
    compressed = bytearray()
    width = height = color_type = bit_depth = interlace = None
    while offset < len(raw):
        length = struct.unpack('>I', raw[offset:offset + 4])[0]
        kind = raw[offset + 4:offset + 8]
        payload = raw[offset + 8:offset + 8 + length]
        offset += 12 + length
        if kind == b'IHDR':
            width, height, bit_depth, color_type, _, _, interlace = struct.unpack(
                '>IIBBBBB', payload,
            )
        elif kind == b'IDAT':
            compressed.extend(payload)
        elif kind == b'IEND':
            break
    channels = {2: 3, 6: 4}.get(color_type)
    if not width or not height or bit_depth != 8 or channels is None or interlace != 0:
        raise ValueError(f'Unsupported PNG encoding: {path}')
    scanlines = zlib.decompress(compressed)
    stride = width * channels
    pixels = bytearray(height * stride)
    source = 0
    for row in range(height):
        filter_type = scanlines[source]
        source += 1
        target = row * stride
        for column in range(stride):
            value = scanlines[source]
            source += 1
            left = pixels[target + column - channels] if column >= channels else 0
            above = pixels[target + column - stride] if row > 0 else 0
            upper_left = (
                pixels[target + column - stride - channels]
                if row > 0 and column >= channels else 0
            )
            if filter_type == 1:
                value = (value + left) & 0xff
            elif filter_type == 2:
                value = (value + above) & 0xff
            elif filter_type == 3:
                value = (value + ((left + above) // 2)) & 0xff
            elif filter_type == 4:
                estimate = left + above - upper_left
                pa = abs(estimate - left)
                pb = abs(estimate - above)
                pc = abs(estimate - upper_left)
                predictor = left if pa <= pb and pa <= pc else above if pb <= pc else upper_left
                value = (value + predictor) & 0xff
            elif filter_type != 0:
                raise ValueError(f'Unsupported PNG filter {filter_type}: {path}')
            pixels[target + column] = value
    return width, height, channels, bytes(pixels)


def raster_equivalent(expected: Path, actual: Path) -> tuple[bool, int, int]:
    expected_width, expected_height, expected_channels, expected_pixels = decode_png(expected)
    actual_width, actual_height, actual_channels, actual_pixels = decode_png(actual)
    if (
        expected_width != actual_width
        or expected_height != actual_height
        or expected_channels != actual_channels
    ):
        return False, expected_width * expected_height, 255
    changed = 0
    max_delta = 0
    total_delta = 0
    for offset in range(0, len(expected_pixels), expected_channels):
        delta = max(
            abs(expected_pixels[offset + channel] - actual_pixels[offset + channel])
            for channel in range(min(3, expected_channels))
        )
        if delta:
            changed += 1
            max_delta = max(max_delta, delta)
            total_delta += delta
    pixel_count = expected_width * expected_height
    edge_noise = changed <= max(1, int(pixel_count * 0.001)) and max_delta <= 20
    glyph_noise = (
        changed <= max(1, int(pixel_count * 0.005))
        and total_delta / pixel_count <= 0.25
    )
    return edge_noise or glyph_noise, changed, max_delta


def run_capture(args: argparse.Namespace) -> int:
    manifest, scenarios = load_scenarios(set(args.scenario) or None, args.fixture)
    output = Path(args.output).resolve()
    with sync_playwright() as playwright:
        for scenario in scenarios:
            browser = playwright.chromium.launch(headless=True)
            try:
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
    manifest, scenarios = load_scenarios(set(args.scenario) or None, args.fixture)
    output = Path(args.output).resolve()
    failures = 0
    with sync_playwright() as playwright:
        for scenario in scenarios:
            browser = playwright.chromium.launch(headless=True)
            try:
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

                current_legacy = (
                    output / 'current-legacy' / f"{scenario['id']}.png"
                )
                capture(
                    browser,
                    base_url=args.base_url,
                    defaults=manifest['defaults'],
                    scenario=scenario,
                    path_key='legacyPath',
                    destination=current_legacy,
                )
                if golden.read_bytes() != current_legacy.read_bytes():
                    equivalent, changed, max_delta = raster_equivalent(
                        golden, current_legacy,
                    )
                    if equivalent:
                        print(
                            f"GOLDEN-RASTER-EQUIVALENT {scenario['id']} "
                            f"changed={changed} max-delta={max_delta}"
                        )
                    else:
                        print(
                            f"GOLDEN-DRIFT {scenario['id']} "
                            f"golden={digest(golden)[:12]} "
                            f"current={digest(current_legacy)[:12]}"
                        )
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
                if current_legacy.read_bytes() == actual.read_bytes():
                    print(f"MATCH {scenario['id']} {digest(actual)[:12]}")
                else:
                    equivalent, changed, max_delta = raster_equivalent(
                        current_legacy, actual,
                    )
                    if equivalent:
                        print(
                            f"RASTER-EQUIVALENT {scenario['id']} "
                            f"changed={changed} max-delta={max_delta}"
                        )
                    else:
                        print(
                            f"DIFF {scenario['id']} "
                            f"golden={digest(current_legacy)[:12]} "
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
    result.add_argument('--fixture', choices=('dev', 'isolated'))
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

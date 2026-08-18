#!/usr/bin/env python3
"""Audit a bundle for personal information — independently of the exporter.

Deliberately does NOT import the exporter's own check. The exporter already passed
its self-check on a bundle that reconstructed statement authorship through a join, so
re-running that logic would only re-confirm the same blind spot. This walks the
delivered files as a stranger would.

    ./.venv/bin/python audit_bundle.py 2026-nlwiki-arbcom_bundle
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pandas as pd

# Columns that must never appear, whatever the manifest says.
FORBIDDEN = {
    'uid', 'xid', 'subject', 'mw_user_id', 'mw_username', 'public_username',
    'revealed_at', 'email', 'hname', 'notify_email', 'notify_talk_page',
    'eligibility_detail', 'ip', 'ip_address', 'referrer', 'parent_url',
    'subscribe_email', 'owner', 'author_person_key', 'author_pid',
    'proposer_person_key', 'proposer_pseudonym',
}
# Allowed only when the manifest says so, explicitly.
CONDITIONAL = {'pseudonym'}

EMAIL = re.compile(r'[\w.+-]+@[\w-]+\.[\w.]{2,}')
HEX64 = re.compile(r'\b[0-9a-f]{64}\b')
# A Wikimedia username in running text, e.g. [[User:Foo]] or @Foo
USER_MARKUP = re.compile(r'\[\[\s*(?:User|Gebruiker)\s*:', re.I)

PASS, FAIL, WARN = ' PASS ', ' FAIL ', ' WARN '


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else '.')
    manifests = {p.stem.replace('manifest_', ''): json.loads(p.read_text())
                 for p in sorted(root.glob('manifest_*.json'))}
    allowed = set()
    for m in manifests.values():
        allowed |= {c.lower() for c in m.get('allowed_columns', [])}

    print(f'auditing {root}')
    print(f'  declared allowances: {sorted(allowed) or "none"}')
    print(f'  salt ids: {[m["salt_id"] for m in manifests.values()]}')
    print()

    frames: dict[str, pd.DataFrame] = {}
    for path in sorted(root.rglob('*.csv')):
        frames[str(path.relative_to(root))] = pd.read_csv(path)

    problems: list[str] = []

    # ── 1. columns ───────────────────────────────────────────────────────────
    print('1. columns present')
    for name, df in frames.items():
        bad = [c for c in df.columns if c.lower() in FORBIDDEN]
        conditional = [c for c in df.columns if c.lower() in CONDITIONAL]
        undeclared = [c for c in conditional if c.lower() not in allowed]
        status = FAIL if (bad or undeclared) else PASS
        print(f' {status} {name:<38} {len(df):>5} rows · {", ".join(df.columns)}')
        for col in bad:
            problems.append(f'{name}: forbidden column {col!r}')
        for col in undeclared:
            problems.append(f'{name}: {col!r} present but not declared in any manifest')

    # ── 2. the join that leaked last time ────────────────────────────────────
    print('\n2. re-identifying joins')
    id_cols = {'person_key', 'pseudonym'}
    carriers = {name: sorted(id_cols & set(df.columns))
                for name, df in frames.items() if id_cols & set(df.columns)}
    for name, cols in carriers.items():
        print(f'      {name}: carries {", ".join(cols)}')

    pseudonym_files = [n for n, c in carriers.items() if 'pseudonym' in c]
    linkable = [n for n, c in carriers.items() if 'person_key' in c]

    authorship = []
    for name, df in frames.items():
        lowered = {c.lower() for c in df.columns}
        if lowered & {'author_person_key', 'proposer_person_key', 'author_pid'}:
            authorship.append(name)
    if authorship:
        problems.append(f'authorship columns present in {authorship}')
        print(f' {FAIL} statement/argument authorship is present: {authorship}')
    else:
        print(f' {PASS} no statement or argument authorship anywhere in the bundle')

    if pseudonym_files and linkable:
        others = [n for n in linkable if n not in pseudonym_files]
        print(f' {WARN} pseudonyms in {pseudonym_files} share person_key with '
              f'{len(others)} other file(s)')
        print(f'        → a holder of this bundle can attach a pseudonym to that '
              f"person's votes.")
        print(f'        → they CANNOT attach it to a username (none exported) or to '
              f'a statement (no authorship).')

    # ── 3. value scan ────────────────────────────────────────────────────────
    print('\n3. value scan across every cell')
    hits = {'email': 0, 'hex64': 0, 'user markup': 0}
    for name, df in frames.items():
        for col in df.columns:
            if df[col].dtype != object:
                continue
            for value in df[col].dropna().astype(str):
                if EMAIL.search(value):
                    hits['email'] += 1
                    problems.append(f'{name}.{col}: email-shaped value')
                if HEX64.search(value):
                    hits['hex64'] += 1
                    problems.append(f'{name}.{col}: 64-hex value (xid?)')
                if USER_MARKUP.search(value):
                    hits['user markup'] += 1
                    problems.append(f'{name}.{col}: wiki user link in text')
    for label, n in hits.items():
        print(f' {FAIL if n else PASS} {label}: {n} occurrence(s)')

    # ── 4. math_main ─────────────────────────────────────────────────────────
    print('\n4. math_main payloads')
    for path in sorted(root.rglob('math_main/*.json')):
        payload = json.loads(path.read_text())
        strings = [v for v in _leaves(payload) if isinstance(v, str)]
        suspicious = [s for s in strings if EMAIL.search(s) or HEX64.search(s)]
        print(f' {FAIL if suspicious else PASS} {path.name}: {len(strings)} string '
              f'values, keys are {"numeric/structural" if not suspicious else "SUSPECT"}')
        if suspicious:
            problems.append(f'{path.name}: suspicious strings {suspicious[:3]}')

    # ── 5. free text ─────────────────────────────────────────────────────────
    print('\n5. free text (unavoidably participant-authored)')
    for name, df in frames.items():
        for col in ('txt', 'body', 'statement_text', 'title'):
            if col in df.columns:
                filled = int(df[col].notna().sum())
                if filled:
                    longest = df[col].dropna().astype(str).str.len().max()
                    print(f'      {name}.{col}: {filled} values, longest {longest} chars')
    print('      Statement text is the object of study and cannot be removed, but it is')
    print('      participant-authored: treat the bundle as confidential, and re-read any')
    print('      text before it is quoted publicly.')

    # ── 6. named accounts ────────────────────────────────────────────────────
    # Usernames are never exported as a column, but statement text is written by
    # participants and can name people ("zoals X al zei"). Nothing structural
    # prevents that, so it has to be looked for.
    usernames = [u for u in sys.argv[2:] if not u.startswith('-')]
    print('\n6. named accounts in any cell, including free text')
    if not usernames:
        print('      (none given — pass usernames as extra arguments to check them)')
    for username in usernames:
        needle = username.lower()
        found = []
        for name, df in frames.items():
            for col in df.columns:
                if df[col].dtype != object:
                    continue
                for i, value in df[col].dropna().astype(str).items():
                    if needle in value.lower():
                        found.append(f'{name}.{col} row {i}')
        if found:
            problems.append(f'username {username!r} appears in {found[:5]}')
            print(f' {FAIL} {username}: {len(found)} occurrence(s) — {found[:3]}')
        else:
            print(f' {PASS} {username}: not present anywhere in the bundle')

    # ── 7. pseudonyms leaking into other files ───────────────────────────────
    print('\n7. pseudonyms appearing outside people.csv')
    pseudonyms = set()
    for name in pseudonym_files:
        pseudonyms |= set(frames[name]['pseudonym'].dropna().astype(str))
    leaked = []
    for name, df in frames.items():
        if name in pseudonym_files:
            continue
        for col in df.columns:
            if df[col].dtype != object:
                continue
            for i, value in df[col].dropna().astype(str).items():
                lowered = value.lower()
                for pseudonym in pseudonyms:
                    if len(pseudonym) > 4 and pseudonym.lower() in lowered:
                        leaked.append(f'{name}.{col} row {i}: {pseudonym!r}')
    if leaked:
        problems.append(f'pseudonyms appear outside people.csv: {leaked[:3]}')
        print(f' {FAIL} {len(leaked)} occurrence(s) — {leaked[:3]}')
    else:
        print(f' {PASS} none of the {len(pseudonyms)} pseudonyms appear in any other file')

    print('\n' + '=' * 72)
    if problems:
        print(f'{len(problems)} PROBLEM(S):')
        for p in problems[:25]:
            print(f'  - {p}')
        return 1
    print('No personal information found. No usernames, no authorship, no raw identifiers.')
    print('Residual, by design: pseudonym → that person\'s votes and opinion group.')
    return 0


def _leaves(node):
    if isinstance(node, dict):
        for v in node.values():
            yield from _leaves(v)
    elif isinstance(node, list):
        for v in node:
            yield from _leaves(v)
    else:
        yield node


if __name__ == '__main__':
    raise SystemExit(main())

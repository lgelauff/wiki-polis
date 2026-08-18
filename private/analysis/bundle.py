"""Shared plumbing for the wiki-polis analysis export bundles.

Both exporters (`export_polis_bundle.py`, `export_app_bundle.py`) run ON a server
holding real data and write a **de-identified bundle** that is the only thing allowed
to travel. This module owns the three things they must agree on:

  1. `person_key` — the salted pseudonym that lets the two bundles be joined without
     either of them carrying `uid`, `xid`, `subject`, `pseudonym` or a username.
  2. the manifest — including `salt_id`, so a salt mismatch between the two hosts
     fails loudly in the notebook instead of silently producing an empty join.
  3. the self-check — a denylist + content scan that refuses to write a bundle
     containing anything from the never-export list.

Stdlib only, so either exporter can be copied to a host and run on its own.
"""
from __future__ import annotations

import base64
import csv
import datetime as _dt
import hashlib
import hmac
import json
import os
import re
import subprocess
import sys
from pathlib import Path

SCHEMA_VERSION = 1

# ── never-export list ────────────────────────────────────────────────────────
# Column names that must not appear in any bundle file. Checked against the header
# row of every CSV written, so an accidental `SELECT *` is caught at write time.
DENIED_COLUMNS = {
    'uid', 'xid', 'subject', 'mw_user_id', 'mw_username', 'pseudonym',
    'proposer_pseudonym', 'public_username', 'revealed_at', 'email', 'hname',
    'notify_email', 'notify_talk_page', 'eligibility_detail', 'owner',
    'ip', 'ip_address', 'referrer', 'parent_url', 'subscribe_email',
}

_EMAIL_RE = re.compile(r'[\w.+-]+@[\w-]+\.[\w.]{2,}')
# A wiki-polis xid is 64 hex chars (sha256 / HMAC-SHA256 hexdigest). If one ever
# reaches a bundle we want to know, whatever column it arrived in.
_XID_RE = re.compile(r'\b[0-9a-f]{64}\b')


class SelfCheckError(RuntimeError):
    """Raised when a bundle fails its PII self-check. Nothing is written."""


def scan_value(value) -> list[str]:
    """Return a list of self-check violations for one cell value."""
    if not isinstance(value, str) or not value:
        return []
    problems = []
    if _EMAIL_RE.search(value):
        problems.append('looks like an email address')
    if _XID_RE.search(value):
        problems.append('looks like a 64-hex identifier (xid?)')
    return problems


# ── salt + person_key ────────────────────────────────────────────────────────

def load_salt(path: str | os.PathLike) -> bytes:
    """Read the shared export salt. Whitespace-stripped, so the same file gives the
    same salt_id whether or not it ends in a newline."""
    raw = Path(path).read_text(encoding='utf-8').strip()
    if not raw:
        raise ValueError(f'salt file {path} is empty')
    if len(raw) < 32:
        raise ValueError(
            f'salt file {path} holds only {len(raw)} characters; generate it with '
            '`openssl rand -hex 32`'
        )
    return raw.encode('utf-8')


def salt_id(salt: bytes) -> str:
    """Public fingerprint of the salt. Safe to put in a manifest — it does not
    reveal the salt, but two bundles built with different salts will differ here."""
    return hashlib.sha256(salt).hexdigest()[:8]


def _key(salt: bytes, namespace: str, value: str) -> str:
    dig = hmac.new(salt, f'{namespace}:{value}'.encode('utf-8'), hashlib.sha256).digest()
    return base64.b32encode(dig[:10]).decode('ascii').rstrip('=').lower()


def person_key(salt: bytes, subject: str) -> str:
    """Stable pseudonym for a person, derived from the subject Polis knows them by.

    That subject is *not* the xid. Since #246 wiki-polis asserts a conversation-scoped
    value — `HMAC(PARTICIAPI_SUB_SECRET, f'{xid}:{conversation_id}')`, see
    `v2/app.py::_conversation_subject` — and that is what lands in
    `particiapi_users.subject`. The Polis exporter hashes it directly; the app exporter
    must recompute it with `conversation_subject()` below before calling this.

    Hashing the raw xid on the app side (as this did until the join was found empty)
    produces keys in a disjoint space from the Polis side, so `people.csv` and
    `votes_latest.csv` silently fail to join and every pseudonym-linked result is lost.
    """
    return _key(salt, 'u', subject)


def conversation_subject(sub_secret: bytes, xid: str, conversation_id) -> str:
    """Recompute the conversation-scoped subject wiki-polis asserts to Particiapi.

    Byte-for-byte mirror of `v2/app.py::_conversation_subject` (#246). Kept here rather
    than imported because the exporters run without the Flask app on the path.

    The scoping is deliberate upstream: it stops the same person being linkable across
    conversations. Recomputing it here preserves that property — the resulting
    `person_key` is per-conversation, exactly as the Polis side already is.
    """
    return hmac.new(sub_secret, f'{xid}:{conversation_id}'.encode('utf-8'),
                    hashlib.sha256).hexdigest()


def secret_id(secret: bytes) -> str:
    """Public fingerprint of the sub-secret, for the manifest. A rotated secret
    produces subjects that never existed, and the join goes quiet rather than loud —
    so record which one built the bundle."""
    return hashlib.sha256(secret).hexdigest()[:8]


def anon_key(salt: bytes, uid) -> str:
    """Pseudonym for a Polis uid with no `particiapi_users` row — an anonymous
    session, the conversation owner, or a pre-trusted-sub participant.

    Deliberately *not* joinable to the app side: an unlinkable participant must
    show up as an unlinked row, never as a silent false merge.
    """
    return 'anon-' + _key(salt, 'anon', str(uid))


# ── bundle writer ────────────────────────────────────────────────────────────

class BundleWriter:
    """Collects CSV/JSON parts, self-checks them, then writes the bundle directory.

    Nothing touches disk until `close()` succeeds, so a failed self-check cannot
    leave a partial bundle lying around on a production host.
    """

    def __init__(self, out_dir, *, kind: str, env: str, salt: bytes,
                 with_text: bool, allow_columns: set[str] | None = None,
                 extra_manifest: dict | None = None):
        self.out_dir = Path(out_dir)
        self.kind = kind                 # 'polis' | 'app'
        self.env = env                   # 'local' | 'staging' | 'prod'
        self.salt_id = salt_id(salt)
        self.with_text = with_text
        # Columns deliberately lifted off the never-export list for this run. Only
        # ever set from an explicit command-line flag, and recorded in the manifest
        # so a bundle always says what it was allowed to carry.
        self.allow_columns = {c.lower() for c in (allow_columns or set())}
        self.extra = dict(extra_manifest or {})
        self._csvs: dict[str, tuple[list[str], list[list]]] = {}
        self._jsons: dict[str, object] = {}

    def add_csv(self, name: str, columns: list[str], rows) -> None:
        """Stage one CSV. `name` is relative to the bundle's kind directory."""
        self._csvs[name] = (list(columns), [list(r) for r in rows])

    def add_json(self, name: str, payload) -> None:
        self._jsons[name] = payload

    # ── self-check ───────────────────────────────────────────────────────────
    def _check(self) -> dict:
        violations: list[str] = []
        scanned_cells = 0

        for name, (columns, rows) in self._csvs.items():
            for col in columns:
                if col.lower() in DENIED_COLUMNS and col.lower() not in self.allow_columns:
                    violations.append(f'{name}: column {col!r} is on the never-export list')
            for row_no, row in enumerate(rows):
                for col, value in zip(columns, row):
                    scanned_cells += 1
                    for problem in scan_value(value):
                        violations.append(
                            f'{name}: row {row_no + 1} column {col!r} {problem}'
                        )
                        break   # one report per cell is enough

        for name, payload in self._jsons.items():
            for path, leaf in _walk_json(payload):
                if isinstance(leaf, str):
                    scanned_cells += 1
                    for problem in scan_value(leaf):
                        violations.append(f'{name}: at {path} {problem}')
                        break

        if violations:
            raise SelfCheckError(
                'bundle self-check failed — nothing written:\n  '
                + '\n  '.join(violations[:40])
                + ('\n  …' if len(violations) > 40 else '')
            )
        return {'passed': True, 'cells_scanned': scanned_cells,
                'denylist_size': len(DENIED_COLUMNS)}

    def close(self) -> Path:
        checks = self._check()          # raises before anything is written

        base = self.out_dir / self.kind
        base.mkdir(parents=True, exist_ok=True)

        counts = {}
        for name, (columns, rows) in self._csvs.items():
            target = base / name
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('w', newline='', encoding='utf-8') as fh:
                writer = csv.writer(fh)
                writer.writerow(columns)
                writer.writerows(rows)
            counts[f'{self.kind}/{name}'] = len(rows)

        for name, payload in self._jsons.items():
            target = base / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(payload, indent=1, sort_keys=True,
                                         default=str), encoding='utf-8')
            counts[f'{self.kind}/{name}'] = 1

        manifest = {
            'schema_version': SCHEMA_VERSION,
            'kind': self.kind,
            'env': self.env,
            'exported_at': _dt.datetime.now(_dt.timezone.utc).isoformat(timespec='seconds'),
            'salt_id': self.salt_id,
            'with_text': self.with_text,
            'allowed_columns': sorted(self.allow_columns),
            'git_sha': _git_sha(),
            'python': sys.version.split()[0],
            'counts': counts,
            'checks': checks,
            **self.extra,
        }
        manifest_path = self.out_dir / f'manifest_{self.kind}.json'
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, indent=1, sort_keys=True),
                                 encoding='utf-8')

        _print_summary(self.kind, manifest, counts)
        return self.out_dir


def _walk_json(node, path='$'):
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _walk_json(value, f'{path}.{key}')
    elif isinstance(node, list):
        for i, value in enumerate(node):
            yield from _walk_json(value, f'{path}[{i}]')
    else:
        yield path, node


def _git_sha() -> str | None:
    try:
        out = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'],
                             capture_output=True, text=True, timeout=5)
        return out.stdout.strip() or None
    except Exception:
        return None


def _print_summary(kind: str, manifest: dict, counts: dict) -> None:
    print(f'\n{kind} bundle written  (env={manifest["env"]}, '
          f'salt_id={manifest["salt_id"]}, with_text={manifest["with_text"]})')
    for name, n in sorted(counts.items()):
        print(f'  {n:>8,}  {name}')
    print(f'  self-check: passed ({manifest["checks"]["cells_scanned"]:,} cells scanned)')

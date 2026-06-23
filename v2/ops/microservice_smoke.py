#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass

import requests


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str


def _url(base: str, path: str) -> str:
    return base.rstrip("/") + "/" + path.lstrip("/")


def check_wiki_health(base_url: str, *, session=None, timeout: float = 10.0) -> CheckResult:
    session = session or requests.Session()
    url = _url(base_url, "/health")
    try:
        resp = session.get(url, timeout=timeout)
        if resp.status_code != 200:
            return CheckResult("wiki-health", False, f"HTTP {resp.status_code}")
        data = resp.json()
    except Exception as exc:
        return CheckResult("wiki-health", False, str(exc))
    if data.get("status") != "ok" or data.get("db") != "ok":
        return CheckResult("wiki-health", False, f"unhealthy payload: {data}")
    if data.get("particiapi") == "unreachable":
        return CheckResult("wiki-health", False, f"particiapi unreachable: {data}")
    return CheckResult("wiki-health", True, "ok")


def check_embedding_sidecar(base_url: str, *, session=None, timeout: float = 20.0) -> CheckResult:
    session = session or requests.Session()
    try:
        health = session.get(_url(base_url, "/health"), timeout=timeout)
        if health.status_code != 200:
            return CheckResult("embedding-sidecar", False, f"health HTTP {health.status_code}")
        payload = {"left": "Cats are good companions.", "right": "Cats are good companions."}
        sim = session.post(_url(base_url, "/similarity"), json=payload, timeout=timeout)
        if sim.status_code != 200:
            return CheckResult("embedding-sidecar", False, f"similarity HTTP {sim.status_code}")
        score = float(sim.json().get("similarity"))
    except Exception as exc:
        return CheckResult("embedding-sidecar", False, str(exc))
    if score < 0.95:
        return CheckResult("embedding-sidecar", False, f"unexpected self-similarity {score:.3f}")
    return CheckResult("embedding-sidecar", True, f"self-similarity {score:.3f}")


def ping_deadman(url: str, ok: bool, detail: str, *, session=None, timeout: float = 10.0) -> None:
    if not url:
        return
    session = session or requests.Session()
    target = url.rstrip("/") if ok else url.rstrip("/") + "/fail"
    try:
        session.get(target, params={"summary": detail[:200]}, timeout=timeout)
    except requests.RequestException:
        pass


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Smoke-test deployed wiki-polis microservices.")
    parser.add_argument("--wiki-base-url", default=os.environ.get("WIKI_POLIS_URL", ""),
                        help="wiki-polis base URL; defaults to WIKI_POLIS_URL")
    parser.add_argument("--embedding-url", default=os.environ.get("EMBEDDING_SIDECAR_URL", ""),
                        help="optional embedding sidecar URL")
    parser.add_argument("--heartbeat-url", default=os.environ.get("HEALTHCHECKS_URL", ""),
                        help="optional Healthchecks/dead-man ping URL")
    parser.add_argument("--timeout", type=float, default=10.0)
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    if not args.wiki_base_url:
        print("missing --wiki-base-url or WIKI_POLIS_URL", file=sys.stderr)
        return 2

    results = [check_wiki_health(args.wiki_base_url, timeout=args.timeout)]
    if args.embedding_url:
        results.append(check_embedding_sidecar(args.embedding_url, timeout=max(args.timeout, 20.0)))

    ok = all(result.ok for result in results)
    summary = "; ".join(
        f"{result.name}={'ok' if result.ok else 'fail'} ({result.detail})"
        for result in results
    )
    print(summary)
    ping_deadman(args.heartbeat_url, ok, summary, timeout=args.timeout)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

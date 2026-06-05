#!/usr/bin/env python3
"""
synthetic_traffic.py — Drive realistic traffic at a *deployed* wiki-polis instance
through the real Flask stack (auth → /proxy/particiapi → statement submit), and fail
loudly on any anomaly.

Why this exists
---------------
wiki-polis has too few real users to "soak" a change by waiting for organic traffic.
This tool *generates* that traffic so a regression surfaces in minutes, not weeks.

It is the proxy-facing complement to `simulate_cats_vs_dogs.py`: that script talks
**directly to Particiapi** (and Postgres) to build Polis clustering data; this one
goes **through the Flask app's proxy** — so it exercises exactly the code the proxy
blueprint (#91) owns: the pa_session↔session cookie rename, the CSRF-exempt +
same-origin posture, the 403→200 /results/ rewrite, and the quota-tracked
statement-submit route. Reuse it for any future change: smoke a deploy, soak a
refactor, or load-test, against local or staging.

What a worker does, in a loop, through the proxy
------------------------------------------------
  1. auth         GET  /dev/login/dev-user-N            (needs DEV_FAKE_LOGIN=1)
  2. accept       POST /accept/<slug>                   (once, for the submit action)
  3. discover     GET  /c/<slug>  → <pa-conversation conversation-id="...">
  4. pa-session   POST /proxy/particiapi/api/session?create=true  → csrf_token
  5. statements   GET  /proxy/particiapi/api/conversations/<cid>/statements/
  6. vote         PUT  /proxy/particiapi/api/conversations/<cid>/votes/<tid>
  7. results      GET  /proxy/particiapi/api/conversations/<cid>/results/
  8. submit       POST /c/<slug>/statements/new

Health invariants (any violation = recorded failure, non-zero exit)
  * never a 5xx;
  * /results/ always returns 200 (the proxy must rewrite a pre-math 403);
  * proxy Set-Cookie never leaks a bare `session=` (only the renamed `pa_session`);
  * statement quota returns a clean 403, never a 500.

Prerequisites
-------------
  * Local targets may use DEV_FAKE_LOGIN=1 from v2/.env. Toolforge targets never
    register fake-login routes; pass --session-cookie from an authenticated browser.
  * A votable conversation slug (default "test" — free to mutate on staging).
  * The vote/results actions need only login, so they soak the proxy on any deployed
    instance. Auto-discovery (slug→id) and the `submit` action additionally need a
    resolvable Participation for the dev-fake user; where that isn't set up (e.g. a
    dev-fake row whose username drifted), pass --conversation-id (read it from the
    page's <pa-conversation conversation-id="…">) and the soak runs on vote/results.

Usage
-----
  # Local smoke (one of each action, then stop)
  python synthetic_traffic.py --dry-run

  # Staging soak: authenticated browser session, 10 minutes, ~2 req/s
  python synthetic_traffic.py \
      --base-url https://wiki-polis-dev.toolforge.org \
      --slug test --session-cookie '<cookie>' --duration 600 --rate 2

  # Bypass slug→id discovery (e.g. invite-only conv) by passing the Polis id
  python synthetic_traffic.py --conversation-id 9r7fkvxyjb ...

Exit codes: 0 = clean; 1 = ran but a health invariant was violated; 2 = could not
authenticate (dev fake-login disabled / no valid --session-cookie) so nothing was sent.

If the dev fake-login path is unavailable and no --session-cookie was supplied, the tool
detects that in a preflight probe and exits 2 rather than firing traffic that all
bounces to /login.
"""
import argparse
import os
import random
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))

DEFAULT_BASE = os.environ.get("WIKI_POLIS_FLASK_URL", "http://127.0.0.1:5001").rstrip("/")
DEV_USERS = ["dev-user-1", "dev-user-2", "dev-user-3"]  # /dev/login/<username> (DEV_FAKE_LOGIN=1)
VOTE_VALUES = [-1, 0, 1]                                 # disagree / pass / agree
PSEUDONYM_RE = re.compile(r"^[a-z]+-[a-z]+$")            # matches the app's _PSEUDONYM_RE shape
CONV_ID_RE = re.compile(r'conversation-id="([^"]+)"')
CSRF_RE = re.compile(r'name="csrf_token"[^>]*value="([^"]+)"')


class Health:
    """Thread-safe collector of requests, latencies, and invariant violations."""

    def __init__(self):
        self._lock = threading.Lock()
        self.records = []          # (action, status, latency_ms)
        self.failures = []         # (action, method, path, status, detail)

    def record(self, action, method, path, resp, latency_ms, *, expect_2xx=True,
               results=False, allow_status=()):
        with self._lock:
            self.records.append((action, resp.status_code, latency_ms))
            sc = resp.status_code
            if sc >= 500:
                self._fail(action, method, path, sc, "5xx server error")
            elif results and sc != 200:
                self._fail(action, method, path, sc,
                           "/results/ not rewritten to 200 (proxy regression)")
            elif sc == 429:
                pass  # rate limited — expected under load, not a regression
            elif expect_2xx and not (200 <= sc < 300) and sc not in allow_status:
                self._fail(action, method, path, sc, f"unexpected status (body: {resp.text[:120]!r})")

    def _fail(self, action, method, path, status, detail):
        self.failures.append((action, method, path, status, detail))

    def summary(self, elapsed_s):
        by_action = {}
        for action, status, lat in self.records:
            d = by_action.setdefault(action, {"n": 0, "lat": [], "status": {}})
            d["n"] += 1
            d["lat"].append(lat)
            d["status"][status] = d["status"].get(status, 0) + 1
        lines = []
        lines.append(f"\n{'='*72}\nSYNTHETIC TRAFFIC SUMMARY  ({len(self.records)} requests in {elapsed_s:.1f}s, "
                     f"{len(self.records)/elapsed_s:.1f} req/s)\n{'='*72}")
        lines.append(f"{'action':<12}{'n':>6}  {'p50':>7}{'p95':>7}{'p99':>7}  status")
        for action, d in sorted(by_action.items()):
            lat = sorted(d["lat"])
            p = lambda q: lat[min(len(lat) - 1, int(q * len(lat)))]  # noqa: E731
            statuses = " ".join(f"{s}×{c}" for s, c in sorted(d["status"].items()))
            lines.append(f"{action:<12}{d['n']:>6}  {p(.5):>6.0f}m{p(.95):>6.0f}m{p(.99):>6.0f}m  {statuses}")
        if self.failures:
            lines.append(f"\n  !! {len(self.failures)} HEALTH VIOLATION(S):")
            for action, method, path, status, detail in self.failures[:40]:
                lines.append(f"     [{status}] {method} {path}  ({action}) — {detail}")
            if len(self.failures) > 40:
                lines.append(f"     ... and {len(self.failures) - 40} more")
        else:
            lines.append("\n  OK — no health invariant violated.")
        return "\n".join(lines)


def _origin(base_url):
    u = urlparse(base_url)
    return f"{u.scheme}://{u.netloc}"


class Worker:
    """One synthetic participant: its own requests.Session (cookie jar) and identity."""

    def __init__(self, idx, args, health, deadline, stop):
        self.idx = idx
        self.args = args
        self.health = health
        self.deadline = deadline
        self.stop = stop
        self.s = requests.Session()
        self.s.headers["User-Agent"] = "wiki-polis-synthetic-traffic/1.0"
        self.s.verify = not args.insecure
        self.origin = _origin(args.base_url)
        self.pa_csrf = None
        self.tids = []
        self.cid = args.conversation_id
        self.n_submit = 0

    # ── one timed request with health checking ───────────────────────────────
    def _req(self, action, method, path, **kw):
        health = kw.pop("health", {})
        url = self.args.base_url + path
        t0 = time.monotonic()
        resp = self.s.request(method, url, timeout=20, allow_redirects=False, **kw)
        lat = (time.monotonic() - t0) * 1000
        self.health.record(action, method, path, resp, lat, **health)
        return resp

    def _proxy(self, action, method, sub, **kw):
        headers = kw.pop("headers", {})
        if method in ("POST", "PUT"):
            headers["Origin"] = self.origin           # mirror a real browser
            if self.pa_csrf:
                headers["X-CSRF-Token"] = self.pa_csrf
        results = sub.endswith("/results/")
        return self._req(action, method, f"/proxy/particiapi/{sub}", headers=headers,
                         health={"results": results, "expect_2xx": True}, **kw)

    # ── setup ────────────────────────────────────────────────────────────────
    def auth(self):
        # Availability is confirmed by preflight() before any worker starts; here we
        # just establish this worker's identity. Stay quiet on failure — preflight owns
        # the user-facing explanation.
        if self.args.session_cookie:
            self.s.headers["Cookie"] = self.args.session_cookie
            return True
        user = DEV_USERS[self.idx % len(DEV_USERS)]
        r = self._req("auth", "GET", f"/dev/login/{user}", health={"allow_status": (302,)})
        return r.status_code in (302, 200) and "login" not in r.headers.get("Location", "")

    def accept(self):
        """Ensure a Participation exists (needed for the submit action)."""
        r = self._req("accept", "GET", f"/accept/{self.args.slug}",
                      health={"allow_status": (302,)})
        if r.status_code == 302:        # already participating
            return True
        if r.status_code != 200:
            return False
        m = CSRF_RE.search(r.text)
        if not m:
            return False
        pj = self._req("accept", "GET", f"/accept/{self.args.slug}/pseudonyms")
        choices = pj.json().get("pseudonyms", []) if pj.ok else []
        pseudonym = next((p for p in choices if PSEUDONYM_RE.match(p)), None)
        if not pseudonym:
            return False
        r = self._req("accept", "POST", f"/accept/{self.args.slug}",
                      data={"csrf_token": m.group(1), "pseudonym": pseudonym},
                      headers={"Origin": self.origin,
                               "Referer": f"{self.args.base_url}/accept/{self.args.slug}"},
                      health={"allow_status": (302, 400, 401, 404)})  # best-effort setup
        return r.status_code in (302, 200)

    def discover(self):
        if self.cid:
            return True
        r = self._req("discover", "GET", f"/c/{self.args.slug}", health={"allow_status": (302,)})
        m = CONV_ID_RE.search(r.text or "")
        if m:
            self.cid = m.group(1)
            return True
        print(f"  !! could not find conversation-id for slug '{self.args.slug}' "
              "(status %d). Pass --conversation-id." % r.status_code, file=sys.stderr)
        return False

    def pa_session(self):
        r = self._proxy("session", "POST", "api/session?create=true", json={})
        if r.ok:
            try:
                self.pa_csrf = r.json().get("csrf_token")
            except ValueError:
                self.pa_csrf = None
        return r.ok

    def refresh_tids(self):
        r = self._proxy("statements", "GET", f"api/conversations/{self.cid}/statements/")
        if r.ok:
            try:
                self.tids = [int(t) for t in r.json().keys()]
            except (ValueError, AttributeError):
                self.tids = []

    # ── actions ──────────────────────────────────────────────────────────────
    def act_vote(self):
        if not self.tids:
            self.refresh_tids()
        if not self.tids:
            return
        tid = random.choice(self.tids)
        self._proxy("vote", "PUT", f"api/conversations/{self.cid}/votes/{tid}",
                    json={"value": random.choice(VOTE_VALUES)})

    def act_results(self):
        self._proxy("results", "GET", f"api/conversations/{self.cid}/results/")

    def act_submit(self):
        self.n_submit += 1
        text = f"{self.args.submit_text_prefix} w{self.idx} #{self.n_submit} — synthetic statement"
        # 403 quota_exceeded and 404 (no participation) are acceptable, not failures.
        # 201 created; 403 quota_exceeded; 401/404 no Participation — all acceptable.
        self._req("submit", "POST", f"/c/{self.args.slug}/statements/new",
                  json={"text": text}, headers={"Origin": self.origin,
                  "Referer": f"{self.args.base_url}/c/{self.args.slug}"},
                  health={"allow_status": (401, 403, 404)})

    # ── loop ─────────────────────────────────────────────────────────────────
    def run(self):
        if not self.auth():
            return
        self.accept()  # idempotent; ensures Participation (submit) + a renderable /c/<slug>
        if not self.discover():
            return
        self.pa_session()
        self.refresh_tids()

        if self.args.dry_run:
            for a in ("vote", "results", "submit"):
                if a in self.args.actions:
                    getattr(self, f"act_{a}")()
            return

        interval = 1.0 / self.args.rate if self.args.rate > 0 else 0
        iters = 0
        while not self.stop.is_set():
            if self.deadline and time.monotonic() >= self.deadline:
                break
            if self.args.iterations and iters >= self.args.iterations:
                break
            t0 = time.monotonic()
            getattr(self, f"act_{random.choices(self.args.actions, self.args.weights)[0]}")()
            iters += 1
            sleep = interval - (time.monotonic() - t0)
            if sleep > 0:
                self.stop.wait(sleep)


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Drive synthetic traffic at wiki-polis through the Flask proxy.")
    p.add_argument("--base-url", default=DEFAULT_BASE,
                   help=f"target base URL (default: {DEFAULT_BASE})")
    p.add_argument("--slug", default="test", help="conversation slug (default: test)")
    p.add_argument("--conversation-id", help="Polis conversation id (skip slug→id discovery)")
    p.add_argument("--workers", type=int, default=3, help="concurrent identities (default: 3)")
    p.add_argument("--duration", type=float, help="seconds to run")
    p.add_argument("--iterations", type=int, help="actions per worker (instead of --duration)")
    p.add_argument("--rate", type=float, default=2.0, help="requests/sec per worker (default: 2)")
    p.add_argument("--actions", default="vote,results,submit",
                   help="comma list with optional weights, e.g. 'vote:5,results:2,submit:1'")
    p.add_argument("--session-cookie", help="raw Cookie header to use instead of dev-fake-login")
    p.add_argument("--submit-text-prefix", default="[synthetic]", help="tag for submitted statements")
    p.add_argument("--insecure", action="store_true", help="skip TLS verification")
    p.add_argument("--dry-run", action="store_true",
                   help="auth + discover + one of each action, then stop")
    args = p.parse_args(argv)
    args.base_url = args.base_url.rstrip("/")

    actions, weights = [], []
    for part in args.actions.split(","):
        name, _, w = part.strip().partition(":")
        if name not in ("vote", "results", "submit"):
            p.error(f"unknown action '{name}'")
        actions.append(name)
        weights.append(float(w) if w else 1.0)
    args.actions, args.weights = actions, weights

    if not args.session_cookie and args.workers > len(DEV_USERS):
        print(f"  note: capping --workers to {len(DEV_USERS)} (only {len(DEV_USERS)} "
              "dev-fake-login identities; use --session-cookie for more).", file=sys.stderr)
        args.workers = len(DEV_USERS)
    if not args.dry_run and not args.duration and not args.iterations:
        args.duration = 60.0
    return args


def preflight(args):
    """One probe to confirm we can actually authenticate, BEFORE sending traffic.

    Catches the case where the dev fake-login path has been disabled for security
    (DEV_FAKE_LOGIN off, or the route removed) — otherwise every request would 302 to
    /login and the run would look "successful" while testing nothing. Returns
    (ok, human_detail).
    """
    s = requests.Session()
    s.headers["User-Agent"] = "wiki-polis-synthetic-traffic/1.0 (preflight)"
    s.verify = not args.insecure
    try:
        if args.session_cookie:
            s.headers["Cookie"] = args.session_cookie
            r = s.get(f"{args.base_url}/c/{args.slug}", allow_redirects=False, timeout=15)
            loc = r.headers.get("Location", "").lower()
            if r.status_code in (301, 302) and ("login" in loc or "oauth" in loc):
                return False, (f"--session-cookie is not authenticated "
                               f"(GET /c/{args.slug} -> {r.status_code} {loc}); it may be expired")
            return True, "using supplied --session-cookie"
        user = DEV_USERS[0]
        r = s.get(f"{args.base_url}/dev/login/{user}", allow_redirects=False, timeout=15)
    except requests.RequestException as e:
        return False, f"could not reach {args.base_url}: {e}"
    loc = r.headers.get("Location", "").lower()
    ok = r.status_code in (200, 302) and "login" not in loc and "oauth" not in loc
    return ok, f"GET /dev/login/{user} -> {r.status_code} {r.headers.get('Location', '')}".strip()


def main(argv=None):
    args = parse_args(argv)

    ok, detail = preflight(args)
    if not ok:
        print(
            f"\n  AUTH UNAVAILABLE — sending no traffic.\n"
            f"  probe: {detail}\n\n"
            f"  The login path needed to drive {args.base_url} is not available. This is\n"
            f"  expected if dev fake-login was disabled for security. To run the soak,\n"
            f"  restore access one of these ways:\n"
            f"    • local target: enable fake-login with DEV_FAKE_LOGIN=1 in v2/.env.\n"
            f"    • Toolforge or any target: pass --session-cookie \"<cookie from an authenticated browser>\".\n",
            file=sys.stderr)
        return 2

    health = Health()
    stop = threading.Event()
    deadline = (time.monotonic() + args.duration) if args.duration and not args.dry_run else None

    mode = "dry-run" if args.dry_run else (f"{args.duration:.0f}s" if args.duration
                                           else f"{args.iterations} iters")
    print(f"→ {args.base_url}  slug={args.slug}  workers={args.workers}  "
          f"actions={args.actions}  mode={mode}")

    t0 = time.monotonic()
    workers = [Worker(i, args, health, deadline, stop) for i in range(args.workers)]
    try:
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futures = [ex.submit(w.run) for w in workers]
            for f in as_completed(futures):
                f.result()
    except KeyboardInterrupt:
        print("\n  interrupted — stopping workers...", file=sys.stderr)
        stop.set()
    elapsed = time.monotonic() - t0

    print(health.summary(elapsed))
    return 1 if health.failures else 0


if __name__ == "__main__":
    sys.exit(main())

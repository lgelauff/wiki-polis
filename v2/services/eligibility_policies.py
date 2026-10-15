"""canivote's eligibility policies, the only values a consultation's policy may take (#530).

An organizer no longer types a policy id: they choose one from canivote's own list
(``GET <ACCOUNT_ELIGIBILITY_URL>/policies``), and the server refuses any id that is not on
it, so a typo can no longer refuse everyone. Each entry carries its rules
(``GET /policies/<id>``), which the console shows in plain words under the field.

The list changes when canivote's ``policies.yaml`` is edited and redeployed, so it is
cached for ten minutes; a failure is cached for one, so a page that asks while canivote is
down does not wait for the timeout on every request.
"""

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

import requests

CACHE_SECONDS = 600
FAILURE_CACHE_SECONDS = 60
TIMEOUT_SECONDS = 5

# The parts of a canivote rule the console renders. Anything else canivote adds later is
# dropped here rather than passed through to a page that does not know it.
RULE_KEYS = ('metric', 'operator', 'value', 'wiki', 'namespace', 'within')


class EligibilityPolicyRefused(ValueError):
    """Raised when a save names a policy that cannot be stored."""

    def __init__(self, message: str):
        super().__init__(message)
        self.field = 'eligibilityEventId'
        self.message = message


@dataclass(frozen=True)
class PolicyChoice:
    """The eligibility pair to store: an id from canivote's list (or none) and its label."""

    event_id: str
    label: str


def _rule(raw) -> dict | None:
    if not isinstance(raw, dict) or not isinstance(raw.get('metric'), str):
        return None
    return {key: raw[key] for key in RULE_KEYS if key in raw}


def _rules(detail) -> list[dict] | None:
    """The rules canivote evaluates for a policy, each once.

    canivote lists a rule twice when the platform imposes it and the community's policy
    states it as well (``is_blocked`` on the policy's own wiki, tagged ``platform`` and
    ``policy``). A reader is asked to meet it once, so it is shown once.
    """
    if not isinstance(detail, dict) or not isinstance(detail.get('rules'), list):
        return None
    seen, rules = [], []
    for raw in detail['rules']:
        rule = _rule(raw)
        if rule is None or rule in seen:
            continue
        seen.append(rule)
        rules.append(rule)
    return rules


def _sources(detail) -> list[str]:
    if not isinstance(detail, dict) or not isinstance(detail.get('sources'), list):
        return []
    return [url for url in detail['sources']
            if isinstance(url, str) and url.startswith('https://')]


def fetch_policies(base_url: str, *, user_agent: str, get: Callable | None = None) -> list[dict]:
    """canivote's policies with their rules, or raise when the list cannot be read.

    A policy whose detail cannot be read is still listed, with ``rules`` null: it can be
    chosen, only its rules cannot be shown.
    """
    get = get or requests.get
    base = base_url.rstrip('/')
    headers = {'User-Agent': user_agent}
    response = get(f'{base}/policies', headers=headers, timeout=TIMEOUT_SECONDS)
    response.raise_for_status()
    payload = response.json()
    entries = payload.get('policies') if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        raise ValueError('canivote /policies has no policy list')
    policies = []
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get('id'), str):
            continue
        policy_id = entry['id']
        detail = None
        try:
            detail_response = get(f'{base}/policies/{policy_id}', headers=headers,
                                  timeout=TIMEOUT_SECONDS)
            if detail_response.status_code == 200:
                detail = detail_response.json()
        except (requests.RequestException, ValueError):
            detail = None
        policies.append({
            'id': policy_id,
            'title': entry.get('title') if isinstance(entry.get('title'), str) else policy_id,
            'wiki': entry.get('wiki') if isinstance(entry.get('wiki'), str) else None,
            'rules': _rules(detail),
            'sources': _sources(detail),
        })
    return policies


class PolicyCache:
    """canivote's list, kept for ``CACHE_SECONDS`` (a failure for ``FAILURE_CACHE_SECONDS``)."""

    def __init__(self, *, clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self._lock = threading.Lock()
        self._entries: dict[str, tuple[float, list[dict] | None]] = {}

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def get(self, base_url: str, *, user_agent: str, logger=None) -> list[dict] | None:
        """The list, or None when canivote is not configured or cannot be read."""
        base_url = (base_url or '').strip()
        if not base_url:
            return None
        now = self._clock()
        with self._lock:
            cached = self._entries.get(base_url)
        if cached is not None and cached[0] > now:
            return cached[1]
        try:
            policies = fetch_policies(base_url, user_agent=user_agent)
            expires = now + CACHE_SECONDS
        except (requests.RequestException, ValueError) as exc:
            if logger is not None:
                logger.warning('canivote policy list unavailable: %s', type(exc).__name__)
            policies = None
            expires = now + FAILURE_CACHE_SECONDS
        with self._lock:
            self._entries[base_url] = (expires, policies)
        return policies


POLICY_CACHE = PolicyCache()


def find_policy(policies: list[dict] | None, policy_id: str | None) -> dict | None:
    if not policies or not policy_id:
        return None
    return next((policy for policy in policies if policy['id'] == policy_id), None)


def resolve_policy_choice(
    *, requested_id: str, requested_label: str, stored_id: str | None,
    policies: Callable[[], list[dict] | None],
) -> PolicyChoice:
    """The eligibility pair a save stores, or refuse it.

    Only an id on canivote's list is stored. The one exception is the id already stored,
    sent back unchanged: every Save sends the whole settings representation, so refusing it
    would block a title change because of a policy canivote has since removed, or while
    canivote cannot be reached. A label left empty becomes the policy's title; no policy
    means no label, since the label only ever names the policy.
    """
    event_id = requested_id.strip()
    label = requested_label.strip()
    if not event_id:
        return PolicyChoice('', '')
    unchanged = event_id == (stored_id or '').strip()
    if unchanged and label:
        return PolicyChoice(event_id, label)
    listed = policies()
    policy = find_policy(listed, event_id)
    if policy is None:
        if unchanged:
            return PolicyChoice(event_id, label)
        if listed is None:
            raise EligibilityPolicyRefused(
                'The list of eligibility policies cannot be loaded now. Try again later.')
        raise EligibilityPolicyRefused('Choose an eligibility policy from the list.')
    return PolicyChoice(event_id, label or policy['title'])


def policy_status(event_id: str | None, policies: list[dict] | None) -> str:
    """``none``, ``listed``, ``unlisted`` (a stored id canivote does not have), or
    ``unavailable`` (canivote's list cannot be read, so it is not known which)."""
    if not event_id:
        return 'none'
    if policies is None:
        return 'unavailable'
    return 'listed' if find_policy(policies, event_id) else 'unlisted'

"""The Proto bot's MediaWiki API client (#577).

One client per wiki. It logs in with a bot password, checks whether an account can receive
wiki-mail, checks the bot exclusion templates on a talk page, and sends wiki-mail
(`action=emailuser`) or a new talk-page section (`action=edit`, `section=new`).

Every failure is raised as `WikiBotError` with one of the reason codes the delivery log
uses, so callers never parse MediaWiki error codes themselves. Use the client as a context
manager, or call `close()`, so its HTTP session is released.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import dataclass

import requests

# The wikis the bot may work on, by database name. Meta is also the wiki-mail fallback.
WIKI_HOSTS: dict[str, str] = {
    'metawiki': 'meta.wikimedia.org',
    'nlwiki': 'nl.wikipedia.org',
}
FALLBACK_WIKI = 'metawiki'

# Reason codes, shared with the delivery log (#577).
NOT_EMAILABLE = 'not_emailable'
NOBOTS = 'nobots'
THROTTLED = 'throttled'
BLOCKED = 'blocked'
LAGGED = 'lagged'                  # the wiki stayed too busy (maxlag) after waiting
OUTCOME_UNKNOWN = 'outcome_unknown'  # a write got no answer: it may or may not have happened
API_ERROR = 'api_error'

_NOT_EMAILABLE_CODES = {'noemail', 'nowikiemail', 'notarget', 'usermaildisabled'}
_THROTTLED_CODES = {'ratelimited', 'actionthrottledtext'}
_BLOCKED_CODES = {'blocked', 'autoblocked', 'blockedfrommail', 'globalblocking-blockedtext'}

# Writes ask the wiki to refuse them while replication lag is above this many seconds
# (https://www.mediawiki.org/wiki/Manual:Maxlag_parameter). A refused write did nothing, so
# it is retried after the wiki's Retry-After, at most this many times and this long each.
_MAXLAG = 5
_MAXLAG_RETRIES = 2
_MAXLAG_WAIT_CAP = 5.0


class WikiBotError(Exception):
    """A send or check failed. `reason` is a delivery-log code; `code` is MediaWiki's."""

    def __init__(self, reason: str, code: str | None = None, *, retry_after: float | None = None):
        super().__init__(f'{reason}: {code}' if code else reason)
        self.reason = reason
        self.code = code
        self.retry_after = retry_after


def _reason_for(code: str) -> str:
    if code in _NOT_EMAILABLE_CODES:
        return NOT_EMAILABLE
    if code in _THROTTLED_CODES:
        return THROTTLED
    if code in _BLOCKED_CODES:
        return BLOCKED
    if code == 'maxlag':
        return LAGGED
    return API_ERROR


_NOBOTS = re.compile(r'\{\{\s*nobots\s*(\|[^}]*)?\}\}', re.IGNORECASE)
_BOTS = re.compile(r'\{\{\s*bots\s*((?:\|[^}]*)?)\}\}', re.IGNORECASE)


def _name_key(name: str) -> str:
    return ' '.join(name.replace('_', ' ').split()).casefold()


def bot_allowed(wikitext: str, bot_username: str) -> bool:
    """Whether the bot exclusion templates on a page let this bot post there.

    Follows the Template:Bots convention, over every template on the page:
    `{{nobots}}` excludes every bot; `{{bots|deny=…}}` excludes the listed bots (or `all`);
    `{{bots|allow=…}}` admits only the listed bots (`none` admits none); `{{bots|optout=all}}`
    opts out of every automated message.
    """
    if _NOBOTS.search(wikitext):
        return False
    # A bot password logs in as "Name@label"; templates name the account itself.
    me = _name_key(bot_username.split('@', 1)[0])
    for match in _BOTS.finditer(wikitext):
        for param in match.group(1).split('|'):
            key, _, value = param.partition('=')
            key = key.strip().lower()
            names = {_name_key(part) for part in value.split(',') if part.strip()}
            if key == 'deny' and ('all' in names or me in names):
                return False
            if key == 'allow' and not ('all' in names or me in names):
                return False
            if key == 'optout' and 'all' in names:
                return False
    return True


@dataclass(frozen=True)
class BotCredentials:
    username: str
    password: str

    @property
    def account(self) -> str:
        """The account name, without a bot password's "@label" suffix."""
        return self.username.split('@', 1)[0]


class WikiBotClient:
    """The bot on one wiki. Not thread-safe; make one per batch or per test send."""

    def __init__(self, wiki: str, *, credentials: BotCredentials | None, user_agent: str,
                 timeout: float = 10.0,
                 session_factory: Callable[[], requests.Session] = requests.Session,
                 sleep: Callable[[float], None] = time.sleep):
        if wiki not in WIKI_HOSTS:
            raise ValueError(f'unknown wiki: {wiki}')
        self.wiki = wiki
        self._url = f'https://{WIKI_HOSTS[wiki]}/w/api.php'
        self._credentials = credentials
        self._timeout = timeout
        self._sleep = sleep
        self._session = session_factory()
        self._session.headers['User-Agent'] = user_agent
        self._logged_in = False

    def close(self) -> None:
        self._session.close()

    def __enter__(self) -> WikiBotClient:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- transport ---------------------------------------------------------------------

    def _call(self, method: str, params: dict, *, write: bool = False) -> dict:
        params = {**params, 'format': 'json', 'formatversion': '2'}
        try:
            if method == 'GET':
                response = self._session.get(self._url, params=params, timeout=self._timeout)
            else:
                response = self._session.post(self._url, data=params, timeout=self._timeout)
            payload = response.json()
        except requests.ConnectTimeout as exc:
            # The connection never opened, so nothing reached the wiki.
            raise WikiBotError(API_ERROR, 'connect_timeout') from exc
        except (requests.RequestException, ValueError) as exc:
            # Any other failure during a write may come after the wiki acted on it.
            code = 'timeout' if isinstance(exc, requests.Timeout) else type(exc).__name__
            raise WikiBotError(OUTCOME_UNKNOWN if write else API_ERROR, code) from exc
        # The error body comes first: MediaWiki answers a maxlag refusal with HTTP 503.
        error = payload.get('error') if isinstance(payload, dict) else None
        if error:
            code = str(error.get('code') or 'unknown')
            retry_after = None
            if code == 'maxlag':
                try:
                    retry_after = float(response.headers.get('Retry-After') or _MAXLAG_WAIT_CAP)
                except ValueError:
                    retry_after = _MAXLAG_WAIT_CAP
            raise WikiBotError(_reason_for(code), code, retry_after=retry_after)
        if not response.ok:
            raise WikiBotError(API_ERROR, f'http_{response.status_code}')
        return payload

    def _token(self, kind: str) -> str:
        payload = self._call('GET', {'action': 'query', 'meta': 'tokens', 'type': kind})
        try:
            return payload['query']['tokens'][f'{kind}token']
        except (KeyError, TypeError) as exc:
            raise WikiBotError(API_ERROR, 'no_token') from exc

    def _write(self, params: dict) -> dict:
        self.login()
        for attempt in range(_MAXLAG_RETRIES + 1):
            try:
                return self._call('POST', {
                    **params, 'token': self._token('csrf'), 'assert': 'user', 'maxlag': _MAXLAG,
                }, write=True)
            except WikiBotError as exc:
                if exc.reason != LAGGED or attempt == _MAXLAG_RETRIES:
                    raise
                self._sleep(min(exc.retry_after or _MAXLAG_WAIT_CAP, _MAXLAG_WAIT_CAP))
        raise AssertionError('unreachable')

    # -- session -----------------------------------------------------------------------

    def login(self) -> None:
        if self._logged_in:
            return
        if self._credentials is None:
            raise WikiBotError(API_ERROR, 'no_credentials')
        payload = self._call('POST', {
            'action': 'login',
            'lgname': self._credentials.username,
            'lgpassword': self._credentials.password,
            'lgtoken': self._token('login'),
        })
        result = (payload.get('login') or {}).get('result')
        if result != 'Success':
            raise WikiBotError(API_ERROR, f'login_{str(result or "failed").lower()}')
        self._logged_in = True

    # -- checks ------------------------------------------------------------------------

    def is_emailable(self, username: str) -> bool:
        """Whether the account can receive wiki-mail on this wiki (no login needed)."""
        payload = self._call('GET', {
            'action': 'query', 'list': 'users', 'ususers': username, 'usprop': 'emailable',
        })
        users = (payload.get('query') or {}).get('users') or [{}]
        return bool(users[0].get('emailable'))

    def talk_page_allows_bot(self, username: str) -> bool:
        """Whether the user's talk page, after following a redirect, lets this bot post."""
        payload = self._call('GET', {
            'action': 'query', 'prop': 'revisions', 'rvprop': 'content', 'rvslots': 'main',
            'titles': f'User talk:{username}', 'redirects': '1',
        })
        pages = (payload.get('query') or {}).get('pages') or [{}]
        revisions = pages[0].get('revisions') or []
        if not revisions:
            return True   # no talk page yet
        text = (revisions[0].get('slots') or {}).get('main', {}).get('content') or ''
        account = self._credentials.account if self._credentials else ''
        return bot_allowed(text, account)

    # -- sends -------------------------------------------------------------------------

    def send_email(self, username: str, *, subject: str, text: str) -> None:
        payload = self._write({
            'action': 'emailuser', 'target': username, 'subject': subject, 'text': text,
        })
        result = (payload.get('emailuser') or {}).get('result')
        if result != 'Success':
            raise WikiBotError(API_ERROR, f'emailuser_{str(result or "unknown").lower()}')

    def post_talk_section(self, username: str, *, title: str, text: str, summary: str) -> int:
        """Add a new section to the user's talk page (following a redirect, as for a renamed
        account); returns the new revision id."""
        payload = self._write({
            'action': 'edit', 'title': f'User talk:{username}', 'section': 'new',
            'sectiontitle': title, 'text': text, 'summary': summary, 'redirect': '1',
            'bot': '1',   # ignored until the account has the bot flag
        })
        edit = payload.get('edit') or {}
        if edit.get('result') != 'Success':
            raise WikiBotError(API_ERROR, f'edit_{str(edit.get("result") or "unknown").lower()}')
        return int(edit.get('newrevid') or 0)

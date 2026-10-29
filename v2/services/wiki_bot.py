"""The Proto bot's MediaWiki API client (#577).

One client per wiki. It logs in with a bot password, checks whether an account can receive
wiki-mail, checks the bot exclusion templates on a talk page, and sends wiki-mail
(`action=emailuser`) or a new talk-page section (`action=edit`, `section=new`).

Every failure is raised as `WikiBotError` with one of the reason codes the delivery log
uses, so callers never parse MediaWiki error codes themselves.
"""

from __future__ import annotations

import re
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
API_ERROR = 'api_error'

_NOT_EMAILABLE_CODES = {'noemail', 'nowikiemail', 'notarget', 'usermaildisabled'}
_THROTTLED_CODES = {'ratelimited', 'actionthrottledtext'}
_BLOCKED_CODES = {'blocked', 'autoblocked', 'blockedfrommail', 'globalblocking-blockedtext'}

# Wait for replication lag above this many seconds (https://www.mediawiki.org/wiki/Manual:Maxlag_parameter).
_MAXLAG = 5


class WikiBotError(Exception):
    """A send or check failed. `reason` is a delivery-log code; `code` is MediaWiki's."""

    def __init__(self, reason: str, code: str | None = None):
        super().__init__(f'{reason}: {code}' if code else reason)
        self.reason = reason
        self.code = code


def _reason_for(code: str) -> str:
    if code in _NOT_EMAILABLE_CODES:
        return NOT_EMAILABLE
    if code in _THROTTLED_CODES:
        return THROTTLED
    if code in _BLOCKED_CODES:
        return BLOCKED
    return API_ERROR


_NOBOTS = re.compile(r'\{\{\s*nobots\s*(\|[^}]*)?\}\}', re.IGNORECASE)
_BOTS = re.compile(r'\{\{\s*bots\s*\|\s*(allow|deny)\s*=\s*([^}]*)\}\}', re.IGNORECASE)


def _name_key(name: str) -> str:
    return name.strip().replace('_', ' ').casefold()


def bot_allowed(wikitext: str, bot_username: str) -> bool:
    """Whether the bot exclusion templates on a page let this bot post there.

    `{{nobots}}` excludes every bot. `{{bots|deny=…}}` excludes the listed bots, or all of
    them for `all`. `{{bots|allow=…}}` admits only the listed bots; `none` admits none.
    """
    if _NOBOTS.search(wikitext):
        return False
    match = _BOTS.search(wikitext)
    if not match:
        return True
    kind = match.group(1).lower()
    names = {_name_key(part) for part in match.group(2).split(',') if part.strip()}
    me = _name_key(bot_username)
    # A bot password logs in as "Name@label"; templates name the account itself.
    me = me.split('@', 1)[0]
    if kind == 'allow':
        return 'all' in names or me in names
    return not ('all' in names or me in names)


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
                 session_factory: Callable[[], requests.Session] = requests.Session):
        if wiki not in WIKI_HOSTS:
            raise ValueError(f'unknown wiki: {wiki}')
        self.wiki = wiki
        self._url = f'https://{WIKI_HOSTS[wiki]}/w/api.php'
        self._credentials = credentials
        self._timeout = timeout
        self._session = session_factory()
        self._session.headers['User-Agent'] = user_agent
        self._logged_in = False

    # -- transport ---------------------------------------------------------------------

    def _call(self, method: str, params: dict) -> dict:
        params = {**params, 'format': 'json', 'formatversion': '2'}
        try:
            if method == 'GET':
                response = self._session.get(self._url, params=params, timeout=self._timeout)
            else:
                response = self._session.post(self._url, data=params, timeout=self._timeout)
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise WikiBotError(API_ERROR, type(exc).__name__) from exc
        error = payload.get('error') if isinstance(payload, dict) else None
        if error:
            code = str(error.get('code') or 'unknown')
            raise WikiBotError(_reason_for(code), code)
        return payload

    def _token(self, kind: str) -> str:
        payload = self._call('GET', {'action': 'query', 'meta': 'tokens', 'type': kind})
        try:
            return payload['query']['tokens'][f'{kind}token']
        except (KeyError, TypeError) as exc:
            raise WikiBotError(API_ERROR, 'no_token') from exc

    def _write(self, params: dict) -> dict:
        self.login()
        return self._call('POST', {
            **params, 'token': self._token('csrf'), 'assert': 'user', 'maxlag': _MAXLAG,
        })

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
        """Whether the user's talk page lets this bot post (bot exclusion templates)."""
        payload = self._call('GET', {
            'action': 'query', 'prop': 'revisions', 'rvprop': 'content', 'rvslots': 'main',
            'titles': f'User talk:{username}',
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
        """Add a new section to the user's talk page; returns the new revision id."""
        payload = self._write({
            'action': 'edit', 'title': f'User talk:{username}', 'section': 'new',
            'sectiontitle': title, 'text': text, 'summary': summary,
            'bot': '1',   # ignored until the account has the bot flag
        })
        edit = payload.get('edit') or {}
        if edit.get('result') != 'Success':
            raise WikiBotError(API_ERROR, f'edit_{str(edit.get("result") or "unknown").lower()}')
        return int(edit.get('newrevid') or 0)

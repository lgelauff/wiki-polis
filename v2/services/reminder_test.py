"""Send one test message from the Proto bot to a test account (#577, bot approval #581 #582).

Two guards, both empty by default, decide whether anything really leaves Proto:
  - `live_wikis`: the wikis where real sends are switched on;
  - `test_recipients`: the only accounts that may receive anything.
A recipient outside the list is refused. A wiki that is not live, or a bot without
credentials, gives a dry run: nothing is sent and the result says why.

Wiki-mail is checked on the chosen wiki first. If the account can't receive it there, it is
checked on Meta and sent from Meta, when Meta is live too.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from services.wiki_bot import (
    FALLBACK_WIKI, NOBOTS, NOT_EMAILABLE, WIKI_HOSTS, BotCredentials, WikiBotClient,
    WikiBotError,
)

CHANNELS = ('email', 'talk')

SENT = 'sent'
DRY_RUN = 'dry_run'
FAILED = 'failed'

# Why a test was a dry run.
WIKI_NOT_LIVE = 'wiki_not_live'
NO_CREDENTIALS = 'no_credentials'


def normalize_username(name: str) -> str:
    """MediaWiki's form of a username: spaces, not underscores; first letter upper case."""
    name = ' '.join(name.replace('_', ' ').split())
    return name[:1].upper() + name[1:]


@dataclass(frozen=True)
class ReminderSettings:
    credentials: BotCredentials | None
    live_wikis: frozenset[str]
    test_recipients: tuple[str, ...]
    user_agent: str

    @classmethod
    def from_config(cls, config, *, user_agent: str) -> ReminderSettings:
        username = (config.get('REMINDERS_BOT_USERNAME') or '').strip()
        password = config.get('REMINDERS_BOT_PASSWORD') or ''
        return cls(
            credentials=BotCredentials(username, password) if username and password else None,
            live_wikis=frozenset(
                wiki for wiki in config.get('REMINDERS_LIVE_WIKIS') or () if wiki in WIKI_HOSTS
            ),
            test_recipients=tuple(dict.fromkeys(
                normalize_username(name) for name in config.get('REMINDERS_TEST_RECIPIENTS') or ()
                if name.strip()
            )),
            user_agent=user_agent,
        )


@dataclass(frozen=True)
class ReminderTestMessage:
    subject: str
    body: str
    summary: str


@dataclass(frozen=True)
class ReminderTestResult:
    outcome: str                 # sent | dry_run | failed
    reason: str | None = None    # why a dry run or a failure
    code: str | None = None      # MediaWiki's error code, for api_error
    sent_via: str | None = None  # the wiki that sent it


class ReminderTestRefused(ValueError):
    """The request itself is not allowed; nothing was attempted."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


ClientFactory = Callable[[str], WikiBotClient]


def default_client_factory(settings: ReminderSettings) -> ClientFactory:
    def make(wiki: str) -> WikiBotClient:
        return WikiBotClient(wiki, credentials=settings.credentials, user_agent=settings.user_agent)
    return make


def send_test_message(*, wiki: str, channel: str, recipient: str, settings: ReminderSettings,
                      message: ReminderTestMessage, client_factory: ClientFactory) -> ReminderTestResult:
    if wiki not in WIKI_HOSTS:
        raise ReminderTestRefused('unknown_wiki')
    if channel not in CHANNELS:
        raise ReminderTestRefused('unknown_channel')
    recipient = normalize_username(recipient)
    if recipient not in settings.test_recipients:
        raise ReminderTestRefused('recipient_not_allowed')
    if wiki not in settings.live_wikis:
        return ReminderTestResult(DRY_RUN, WIKI_NOT_LIVE)
    if settings.credentials is None:
        return ReminderTestResult(DRY_RUN, NO_CREDENTIALS)

    try:
        if channel == 'email':
            return _send_email(wiki, recipient, settings, message, client_factory)
        client = client_factory(wiki)
        if not client.talk_page_allows_bot(recipient):
            return ReminderTestResult(FAILED, NOBOTS)
        client.post_talk_section(
            recipient, title=message.subject, text=f'{message.body} ~~~~',
            summary=message.summary,
        )
        return ReminderTestResult(SENT, sent_via=wiki)
    except WikiBotError as exc:
        return ReminderTestResult(FAILED, exc.reason, code=exc.code)


def _send_email(wiki, recipient, settings, message, client_factory) -> ReminderTestResult:
    client = client_factory(wiki)
    if not client.is_emailable(recipient):
        if wiki == FALLBACK_WIKI or FALLBACK_WIKI not in settings.live_wikis:
            return ReminderTestResult(FAILED, NOT_EMAILABLE)
        client = client_factory(FALLBACK_WIKI)
        if not client.is_emailable(recipient):
            return ReminderTestResult(FAILED, NOT_EMAILABLE)
    client.send_email(recipient, subject=message.subject, text=message.body)
    return ReminderTestResult(SENT, sent_via=client.wiki)

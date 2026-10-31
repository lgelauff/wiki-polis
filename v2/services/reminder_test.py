"""Send one test message from the Proto bot to a test account (#577, bot approval #581 #582).

A test goes only to an account on `test_recipients` (empty by default); any other recipient
is refused. Test sends are allowed on every wiki the bot knows, approved or not: the
pre-approved test list is the guard (owner, 2026-10-30). Sends to participants are limited
to the wikis where the bot is approved; that is #577, not this module. A channel whose bot
login is not set gives a dry run: nothing is sent and the result says why.

Wiki-mail and talk-page posts log in with separate bot passwords, each with only the grants
its channel needs (owner, 2026-10-29).

Wiki-mail is checked on the chosen wiki first. If the account can't receive it there, it is
checked on Meta and sent from Meta.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import ExitStack
from dataclasses import dataclass

from services.wiki_bot import (
    FALLBACK_WIKI, NOBOTS, NOT_EMAILABLE, OUTCOME_UNKNOWN, WIKI_HOSTS, BotCredentials,
    WikiBotClient, WikiBotError,
)

CHANNELS = ('email', 'talk')

SENT = 'sent'
DRY_RUN = 'dry_run'
FAILED = 'failed'
UNKNOWN = 'unknown'   # a send got no answer: it may have been delivered

# Why a test was a dry run.
NO_CREDENTIALS = 'no_credentials'


def normalize_username(name: str) -> str:
    """MediaWiki's form of a username: spaces, not underscores; first letter upper case."""
    name = ' '.join(name.replace('_', ' ').split())
    return name[:1].upper() + name[1:]


# The Toolforge secret behind each login setting, per channel.
LOGIN_PREFIX = {'email': 'REMINDERS_BOT_EMAIL', 'talk': 'REMINDERS_BOT_TALK'}


def login_settings(read_secret: Callable[[str], str]) -> dict[str, str]:
    """The bot-login settings, read from their secrets (`reminders-bot-email-username` →
    `REMINDERS_BOT_EMAIL_USERNAME`, …). One place, so a test can check the names."""
    return {
        f'{prefix}_{part.upper()}': read_secret(f'{prefix.lower().replace("_", "-")}-{part}')
        for prefix in LOGIN_PREFIX.values() for part in ('username', 'password')
    }


def missing_login_parts(config) -> dict[str, list[str]]:
    """Per channel, the login settings that are empty while the other one is set: a
    half-set login, which counts as not set."""
    half = {}
    for channel, prefix in LOGIN_PREFIX.items():
        names = [f'{prefix}_USERNAME', f'{prefix}_PASSWORD']
        empty = [name for name in names if not (config.get(name) or '').strip()]
        if len(empty) == 1:
            half[channel] = empty
    return half


def _as_list(value) -> list[str]:
    """A list setting, given as a list or as one comma-separated string."""
    if isinstance(value, str):
        value = value.split(',')
    return [item.strip() for item in value or () if isinstance(item, str) and item.strip()]


@dataclass(frozen=True)
class ReminderSettings:
    email_credentials: BotCredentials | None
    talk_credentials: BotCredentials | None
    test_recipients: tuple[str, ...]
    user_agent: str

    @classmethod
    def from_config(cls, config, *, user_agent: str) -> ReminderSettings:
        def login(prefix: str) -> BotCredentials | None:
            username = (config.get(f'{prefix}_USERNAME') or '').strip()
            password = config.get(f'{prefix}_PASSWORD') or ''
            return BotCredentials(username, password) if username and password else None
        return cls(
            email_credentials=login(LOGIN_PREFIX['email']),
            talk_credentials=login(LOGIN_PREFIX['talk']),
            test_recipients=tuple(dict.fromkeys(
                normalize_username(name) for name in _as_list(config.get('REMINDERS_TEST_RECIPIENTS'))
            )),
            user_agent=user_agent,
        )

    def credentials_for(self, channel: str) -> BotCredentials | None:
        """The login for a channel; an unknown channel raises KeyError, never a fallback."""
        return {'email': self.email_credentials, 'talk': self.talk_credentials}[channel]


@dataclass(frozen=True)
class ReminderTestMessage:
    subject: str
    body: str
    summary: str


@dataclass(frozen=True)
class ReminderTestResult:
    outcome: str                 # sent | dry_run | failed | unknown
    reason: str | None = None    # why a dry run or a failure
    code: str | None = None      # MediaWiki's error code, for api_error
    sent_via: str | None = None  # the wiki that sent it


class ReminderTestRefused(ValueError):
    """The request itself is not allowed; nothing was attempted."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


ClientFactory = Callable[[str, BotCredentials], WikiBotClient]


def default_client_factory(settings: ReminderSettings) -> ClientFactory:
    def make(wiki: str, credentials: BotCredentials) -> WikiBotClient:
        return WikiBotClient(wiki, credentials=credentials, user_agent=settings.user_agent)
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
    credentials = settings.credentials_for(channel)
    if credentials is None:
        return ReminderTestResult(DRY_RUN, NO_CREDENTIALS)

    with ExitStack() as clients:
        def open_client(name: str):
            client = client_factory(name, credentials)
            if hasattr(client, 'close'):
                clients.callback(client.close)
            return client
        try:
            if channel == 'email':
                return _send_email(wiki, recipient, message, open_client)
            client = open_client(wiki)
            if not client.talk_page_allows_bot(recipient):
                return ReminderTestResult(FAILED, NOBOTS)
            client.post_talk_section(
                recipient, title=message.subject, text=f'{message.body} ~~~~',
                summary=message.summary,
            )
            return ReminderTestResult(SENT, sent_via=wiki)
        except WikiBotError as exc:
            outcome = UNKNOWN if exc.reason == OUTCOME_UNKNOWN else FAILED
            return ReminderTestResult(outcome, exc.reason, code=exc.code)


def _send_email(wiki, recipient, message, open_client) -> ReminderTestResult:
    client = open_client(wiki)
    if not client.is_emailable(recipient):
        if wiki == FALLBACK_WIKI:
            return ReminderTestResult(FAILED, NOT_EMAILABLE)
        client = open_client(FALLBACK_WIKI)
        if not client.is_emailable(recipient):
            return ReminderTestResult(FAILED, NOT_EMAILABLE)
    client.send_email(recipient, subject=message.subject, text=message.body)
    return ReminderTestResult(SENT, sent_via=client.wiki)

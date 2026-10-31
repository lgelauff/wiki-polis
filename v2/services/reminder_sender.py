"""The real reminder sender (#577), through the Proto bot's MediaWiki client.

Nothing wires this into ``flask process-reminders`` yet: the command still uses
``DryRunSender``, and #577 adds no live switch. It exists so its behaviour can be
reviewed and tested against a fake wiki before any real send is allowed.

Per message:

- Wiki-mail: check on the consultation's wiki that the account can receive
  wiki-mail; if not, check on Meta and send from there. Neither: ``not_emailable``.
  If the check passed and the wiki still refuses the mail, the person muted the
  bot or refuses mail from new accounts: ``refused``, with no retry from Meta.
- Talk page: skip a page that keeps bots out ({{nobots}}, {{bots|…}}) or is in
  the wiki's MassMessage opt-out category (``nobots``). Posts on one wiki are
  spaced by that wiki's interval (services/reminder_wikis.py).
- Any other failure keeps the client's reason (``blocked``, ``throttled``,
  ``lagged``, ``outcome_unknown``, ``api_error``) and the wiki's code.

It never logs a username or message text.
"""

import time
from typing import Callable

from services import reminder_wikis
from services.reminder_batch import Outcome
from services.reminder_messages import MessageSettings, build_email, build_talk
from services.wiki_bot import FALLBACK_WIKI, NOT_EMAILABLE, NOBOTS, WikiBotError

ClientFor = Callable[[str, str], object]    # (wiki, channel) -> WikiBotClient


class LiveSender:
    def __init__(self, *, client_for: ClientFor, messages: MessageSettings,
                 approved: dict[str, str] | None = None,
                 sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic):
        self._client_for = client_for
        self._messages = messages
        self._approved = approved
        self._sleep = sleep
        self._clock = clock
        self._clients: dict[tuple[str, str], object] = {}
        self._last_post: dict[str, float] = {}

    def close(self) -> None:
        for client in self._clients.values():
            close = getattr(client, 'close', None)
            if close:
                close()
        self._clients.clear()

    def _client(self, wiki: str, channel: str):
        key = (wiki, channel)
        if key not in self._clients:
            self._clients[key] = self._client_for(wiki, channel)
        return self._clients[key]

    def send(self, *, channel, wiki, participation, reminders) -> Outcome:
        username = participation.participant.mw_username
        try:
            if channel == 'email':
                return self._email(wiki, username, reminders)
            return self._talk(wiki, username, reminders)
        except WikiBotError as exc:
            return Outcome('failed', reason=exc.reason, error_code=exc.code)

    def _email(self, wiki, username, reminders) -> Outcome:
        client = self._client(wiki, 'email')
        if not client.is_emailable(username):
            if wiki == FALLBACK_WIKI:
                return Outcome('failed', reason=NOT_EMAILABLE)
            client = self._client(FALLBACK_WIKI, 'email')
            if not client.is_emailable(username):
                return Outcome('failed', reason=NOT_EMAILABLE)
        message = build_email(reminders, self._messages)
        try:
            client.send_email(username, subject=message.subject, text=message.body)
        except WikiBotError as exc:
            if exc.reason == NOT_EMAILABLE:
                # The check said yes and the wiki said no: the person muted the bot or
                # refuses mail from new accounts. The wiki does not say which.
                return Outcome('failed', reason='refused', error_code=exc.code)
            raise
        return Outcome('sent', sent_via=client.wiki)

    def _talk(self, wiki, username, reminders) -> Outcome:
        client = self._client(wiki, 'talk')
        if not client.talk_page_allows_bot(username) or client.talk_page_opted_out(username):
            return Outcome('failed', reason=NOBOTS)
        self._wait_for_turn(wiki)
        message = build_talk(reminders, self._messages)
        try:
            client.post_talk_section(username, title=message.subject,
                                     text=f'{message.body} ~~~~', summary=message.summary)
        finally:
            # A failed or unknown write still counts: the wiki may have acted on it.
            self._last_post[wiki] = self._clock()
        return Outcome('sent', sent_via=wiki)

    def _wait_for_turn(self, wiki: str) -> None:
        last = self._last_post.get(wiki)
        if last is None:
            return
        gap = reminder_wikis.talk_edit_interval(wiki, self._approved)
        wait = last + gap - self._clock()
        if wait > 0:
            self._sleep(wait)

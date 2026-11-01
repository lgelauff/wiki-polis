"""The text of a reminder (#577): one message per person, day and channel.

Fixed texts from the message catalogue, with the consultation and a link filled
in. Whoever triggers a send cannot add free text. Every message ends with the
same footer: why the person gets it, who sends it, and how to stop it.

A talk page is public. A consultation is named on a talk page only when its
``reminder_talk_names_consultation`` setting is on; otherwise the note says "a
Proto consultation" and links to Proto's front page, not to the consultation.
On a talk page the organizer-written title is shown as plain text, never as
wikitext.

Every message is in English for now. A message in the consultation's language
would tell anyone reading a public talk page, or the wiki-mail log, which
language community's consultation the person joined, so the language choice
waits for its own decision.
"""

from dataclasses import dataclass
from urllib.parse import quote

import i18n
from services.reminders import PHASE_CLOSING, PHASE_OPENED, RESULTS
from services.wiki_bot import FALLBACK_WIKI, WIKI_HOSTS

BOT_ACCOUNT = 'Protowikibot'
_TYPES = (PHASE_OPENED, PHASE_CLOSING, RESULTS)


@dataclass(frozen=True)
class ReminderMessage:
    subject: str     # wiki-mail subject, or the talk-page section title
    body: str        # plain text for wiki-mail; wikitext for a talk page
    summary: str     # edit summary (talk page only)


@dataclass(frozen=True)
class MessageSettings:
    base_url: str          # Proto's public address, e.g. https://wiki-polis.toolforge.org
    operator: str          # the operator's Wikimedia username


def _locale(reminders) -> str:
    return i18n.SOURCE_LOCALE


def _plain_wikitext(text: str) -> str:
    """Organizer-written text shown literally in wikitext: one line, inside <nowiki>."""
    flat = ' '.join(str(text).split())
    return '<nowiki>' + flat.replace('</nowiki', '&lt;/nowiki') + '</nowiki>'


def _consultations(reminders) -> int:
    return len({r.conversation.id for r in reminders})


def _link(settings: MessageSettings, conversation) -> str:
    return f"{settings.base_url.rstrip('/')}/c/{quote(conversation.slug)}"


def _phase(reminder, locale: str) -> str:
    return i18n.resolve(f'phase-label-{reminder.phase_key}', locale)


def _item(reminder, settings, locale, *, named: bool, wikitext: bool = False) -> str:
    kind = reminder.reminder_type
    if kind not in _TYPES:
        raise ValueError(f'unknown reminder type: {kind}')
    conv = reminder.conversation
    title = _plain_wikitext(conv.title) if wikitext else conv.title
    if not named:
        params = () if kind == RESULTS else (_phase(reminder, locale),)
        return i18n.resolve(f'reminder-item-unnamed-{kind}', locale, params)
    if kind == RESULTS:
        return i18n.resolve('reminder-item-results', locale, (title, _link(settings, conv)))
    return i18n.resolve(f'reminder-item-{kind}', locale,
                        (title, _phase(reminder, locale), _link(settings, conv)))


def _user_page_url(username: str) -> str:
    return f'https://{WIKI_HOSTS[FALLBACK_WIKI]}/wiki/User:{quote(username.replace(" ", "_"))}'


def build_email(reminders, settings: MessageSettings) -> ReminderMessage:
    """One wiki-mail for everything due for one person today."""
    if not reminders:
        raise ValueError('no reminders')
    locale = _locale(reminders)
    if len(reminders) == 1:
        only = reminders[0]
        subject = i18n.resolve(f'reminder-mail-subject-{only.reminder_type}', locale,
                               (only.conversation.title,))
    else:
        subject = i18n.resolve('reminder-mail-subject-combined', locale, (len(reminders),))
    items = [_item(r, settings, locale, named=True) for r in reminders]
    footer = i18n.resolve('reminder-mail-footer', locale, (
        _consultations(reminders), _user_page_url(settings.operator), _user_page_url(BOT_ACCOUNT).replace(
            '/wiki/User:', '/wiki/User_talk:'),
    ))
    body = '\n\n'.join(items + ['--', footer])
    return ReminderMessage(subject=subject, body=body, summary='')


def build_talk(reminders, settings: MessageSettings) -> ReminderMessage:
    """One talk-page section for everything due for one person today on one wiki."""
    if not reminders:
        raise ValueError('no reminders')
    locale = _locale(reminders)
    named = [r.conversation.reminder_talk_names_consultation for r in reminders]
    items = [_item(r, settings, locale, named=n, wikitext=True) for r, n in zip(reminders, named)]
    if not all(named):
        items.append(i18n.resolve('reminder-talk-see-proto', locale,
                                  (settings.base_url.rstrip('/'),)))
    footer = i18n.resolve('reminder-talk-footer-named' if all(named) else
                          'reminder-talk-footer-unnamed', locale,
                          (_consultations(reminders), settings.operator))
    title = i18n.resolve('reminder-talk-title', locale, (len(reminders),))
    body = '\n\n'.join([f'* {item}' for item in items] + [f"''{footer}''"])
    summary = i18n.resolve('reminder-talk-summary', locale)
    return ReminderMessage(subject=title, body=body, summary=summary)

"""Per-wiki reminder settings (#577), kept in the repo and changed by reviewed PR.

``AUTOMATED_SEND_WIKIS`` lists the wikis where the scheduled run may send to
participants. Each entry names the bot approval it rests on. It is empty until a
bot approval is granted (#581 nlwiki, #582 Meta). On any other wiki a super admin
can still trigger a send by hand, after a warning (#576).

Talk-page posts on one wiki are spaced by that wiki's interval: the
``not_approved`` value while the wiki is not on the list, the ``approved`` value
once it is.
"""

from dataclasses import dataclass

from services.wiki_bot import WIKI_HOSTS

DEFAULT_REMINDER_WIKI = 'metawiki'
DEFAULT_TALK_INTERVAL_NOT_APPROVED = 10.0
DEFAULT_TALK_INTERVAL_APPROVED = 2.0


@dataclass(frozen=True)
class WikiSettings:
    talk_edit_interval_not_approved: float = DEFAULT_TALK_INTERVAL_NOT_APPROVED
    talk_edit_interval_approved: float = DEFAULT_TALK_INTERVAL_APPROVED


# Wiki key -> the bot approval the scheduled run rests on (a link or issue).
AUTOMATED_SEND_WIKIS: dict[str, str] = {}

WIKI_SETTINGS: dict[str, WikiSettings] = {
    # Meta's bot policy asks for at least 5 seconds between edits once flagged (#582).
    'metawiki': WikiSettings(talk_edit_interval_approved=5.0),
    'nlwiki': WikiSettings(),
}


def known_wikis() -> tuple[str, ...]:
    return tuple(WIKI_HOSTS)


def is_known_wiki(wiki: str) -> bool:
    return wiki in WIKI_HOSTS


def is_approved(wiki: str, approved: dict[str, str] | None = None) -> bool:
    """True when the scheduled run may send on this wiki."""
    return wiki in (AUTOMATED_SEND_WIKIS if approved is None else approved)


def talk_edit_interval(wiki: str, approved: dict[str, str] | None = None) -> float:
    """Seconds between two talk-page posts on this wiki."""
    if not is_known_wiki(wiki):
        raise ValueError(f'unknown wiki: {wiki}')
    settings = WIKI_SETTINGS.get(wiki, WikiSettings())
    if is_approved(wiki, approved):
        return settings.talk_edit_interval_approved
    return settings.talk_edit_interval_not_approved

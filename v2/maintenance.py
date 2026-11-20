"""Maintenance mode (#619): pause participation during an upgrade without stopping the site.

One switch: a flag file. While it exists, the app

  - refuses every write under ``/api/v1/`` (votes, statements, arguments, flags, joins, admin
    commands) with 503 JSON ``maintenance``, for everyone, site admins included, so a backup
    taken in the window is consistent;
  - answers the participation pages and the API reads behind them, which need Polis, with the
    branded 503 page or 503 JSON — except for site admins, who can still look around and see a
    banner that maintenance is on;
  - keeps everything else readable: the front page, the about pages, the published report,
    the help pages, the message catalogue, the session, login and logout;
  - and the ``process-phase-schedules`` job skips its run.

The file is read on each request, so turning it on or off needs no deploy and no restart.
Where it lives: ``MAINTENANCE_FLAG_PATH`` if set, else ``maintenance.flag`` in the tool's home
(``$TOOL_DATA_DIR`` on Toolforge, the home directory elsewhere). The commands are in
guide_deployment.md.

Not covered: the few seconds of the web service restart at the end of a deploy.
"""

from __future__ import annotations

import os
import re

from flask import current_app

FLAG_FILENAME = 'maintenance.flag'

# Seconds a client is told to wait. "A few minutes": long enough not to hammer the site,
# short enough that a participant who retries after the window is not kept waiting.
RETRY_AFTER_SECONDS = 300

# Participation pages: what a participant opens to vote, write, argue, join or reveal.
_PAUSED_PAGES = re.compile(r'/c/[^/]+|/c/[^/]+/v|/c/[^/]+/reveal|/accept/[^/]+')

# API reads behind those pages. They call Polis, which is being restarted, so they answer
# with the maintenance message rather than an upstream error. The about page, the moderation
# log, the published report (``results``) and published outputs are not in this list.
_PAUSED_API_READS = re.compile(
    r'/api/v1/conversations/[^/]+/(?:workspace|participation-entry|pseudonym-suggestions'
    r'|explore|arguments|informed-voting|intermediate-results|identity-reveal)'
)

_READ_METHODS = frozenset({'GET', 'HEAD', 'OPTIONS'})


def default_flag_path() -> str:
    """``maintenance.flag`` in the tool's home: ``$TOOL_DATA_DIR`` on Toolforge, ``~`` elsewhere."""
    home = os.environ.get('TOOL_DATA_DIR', '').strip() or os.path.expanduser('~')
    return os.path.join(home, FLAG_FILENAME)


def configured_flag_path() -> str:
    """The path from the environment, for ``create_app`` to put in config."""
    return os.environ.get('MAINTENANCE_FLAG_PATH', '').strip() or default_flag_path()


def is_on() -> bool:
    """Whether maintenance mode is on. The one place the switch is read.

    A stat per call. The flag lives on the tool's NFS home on Toolforge; the kernel caches its
    attributes, so this is cheap, and it is what lets the switch take effect without a restart.
    """
    path = current_app.config.get('MAINTENANCE_FLAG_PATH')
    return bool(path) and os.path.exists(path)


def blocks(method: str, path: str, *, site_admin: bool) -> bool:
    """Whether a request is refused while maintenance is on.

    Writes are refused for everyone. Participation reads are refused for everyone but site
    admins. Logging in and out stays possible, so an admin can reach the site to see the
    banner and so nobody is stuck with a session they cannot end.
    """
    if path.startswith('/api/v1/'):
        if method not in _READ_METHODS:
            return True
        return not site_admin and _PAUSED_API_READS.fullmatch(path) is not None
    if path.startswith('/static/'):
        return False
    if method not in _READ_METHODS:
        return path != '/logout'
    return not site_admin and _PAUSED_PAGES.fullmatch(path) is not None

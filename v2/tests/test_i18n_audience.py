"""Which messages are offered to translators, and which are held back.

Two groups are held back, for different reasons, and they are tracked separately so either
can be released without the other:

  - **The admin console.** It needs product work before it is worth a volunteer's time, and
    it is a third of the catalogue's words while serving a handful of organisers.
  - **The help pages.** Their content is still being worked on and may be expanded or
    dropped. translatewiki freezes key names once translators start, and churning the text
    behind a frozen key spends volunteer effort twice.

Holding either back is a translatewiki configuration choice — the keys, the `msg()` call
sites and the `qqq` entries all stay exactly as they are, so nothing has to be rebuilt when
they are released.

The partition is computed here rather than hand-listed, because a hand-list rots: wiring a
new screen can quietly move a message from one audience to the other.

**Tie-break: participants win.** A message reachable from a participant screen is offered for
translation even if the admin console shows it too. Under-translating a participant string is
a user-facing defect; over-translating an admin one costs only a little volunteer time.
"""

import json
import re
from pathlib import Path

_V2 = Path(__file__).resolve().parents[1]
_SRC = _V2 / 'frontend' / 'src'
_CALL = re.compile(r"""\b(?:msg|_)\(\s*(['"])([A-Za-z0-9][A-Za-z0-9._-]*)\1\s*[,)]""")
_MAP_ENTRY = re.compile(r"""^\s*'?[A-Za-z0-9_-]+'?\s*:\s*'([a-z0-9][a-z0-9._-]*)'\s*,""", re.M)

# Messages with no call site yet: their screens are not converted, so reachability cannot be
# computed and the key's own namespace is the only available signal. `phase-` is deliberately
# absent — phase-label-* renders in the participant scheduled-transition banner.
_ADMIN_NAMESPACES = (
    'admin', 'adminconv-', 'stmts-', 'featured-', 'invites-', 'participants-',
    'modlog-', 'flags-', 'role-', 'precond-', 'rec-',
)

# Held back for a different reason: the copy itself is unsettled. Unlike the admin console
# these are participant-facing, so they come back as soon as the content stops moving.
_UNSTABLE_NAMESPACES = ('guidance-',)


def _source_files(suffix):
    return [p for p in _SRC.rglob(f'*{suffix}') if not p.name.endswith(f'.test{suffix}')]


def _keys_in(path):
    return {m.group(2) for m in _CALL.finditer(path.read_text(encoding='utf-8'))}


def _server_label_tables():
    """{table name: keys} from i18n/server-labels.ts, which reaches its keys through a map."""
    source = (_SRC / 'i18n' / 'server-labels.ts').read_text(encoding='utf-8')
    return {
        name: set(_MAP_ENTRY.findall(body))
        for name, body in re.findall(r'const (\w+_MESSAGES)[^=]*= \{(.*?)\n\};', source, re.S)
    }


def audiences():
    """(participant, admin_only) over every key in en.json."""
    catalogue = {k for k in json.loads((_V2 / 'i18n' / 'en.json').read_text(encoding='utf-8'))
                 if not k.startswith('@')}
    participant, admin = set(), set()
    for path in _source_files('.tsx'):
        target = admin if 'features/admin/' in path.as_posix() else participant
        target |= set()
        (admin if 'features/admin/' in path.as_posix() else participant).update(_keys_in(path))

    # server-labels.ts maps an identifier to a key, so attribute each table to the audience
    # of whoever calls its helper.
    tables = _server_label_tables()
    for helper, table in (('phaseLabel', 'PHASE_MESSAGES'),
                          ('tabLabel', 'TAB_MESSAGES'),
                          ('routeLabel', 'ROUTE_MESSAGES')):
        seen = {'admin' if 'features/admin/' in p.as_posix() else 'participant'
                for p in _source_files('.tsx')
                if re.search(rf'\b{helper}\(', p.read_text(encoding='utf-8'))}
        (participant if 'participant' in seen else admin).update(tables.get(table, set()))

    participant &= catalogue
    admin &= catalogue
    unreferenced = catalogue - participant - admin
    admin |= {k for k in unreferenced if k.startswith(_ADMIN_NAMESPACES)}
    admin -= participant                             # participants win a tie
    unstable = {k for k in catalogue if k.startswith(_UNSTABLE_NAMESPACES)}
    return participant - unstable, admin | unstable


def _deferred_from_config():
    """The keys the translatewiki group config holds back, i.e. its TAGS: ignored: list."""
    text = (_V2 / 'i18n' / 'translatewiki-group.yaml').read_text(encoding='utf-8')
    block = re.search(r'^TAGS:\n  ignored:\n((?:    - \S+\n)+)', text, re.M)
    return set(re.findall(r'- (\S+)', block.group(1))) if block else set()


def test_the_config_holds_back_exactly_the_admin_only_messages():
    _, admin_only = audiences()
    deferred = _deferred_from_config()
    assert deferred == admin_only, (
        'translatewiki-group.yaml TAGS: ignored: has drifted from the computed audience split. '
        f'only in config={sorted(deferred - admin_only)[:8]}, '
        f'only computed={sorted(admin_only - deferred)[:8]}'
    )


def test_no_participant_message_is_held_back():
    """The tie-break, enforced: a participant never waits on the admin console's schedule."""
    participant, admin_only = audiences()
    assert not (participant & admin_only)
    assert not (participant & _deferred_from_config())


def test_the_help_pages_are_held_back_while_their_copy_is_unsettled():
    """Separately from the admin console, so either can be released on its own."""
    _, deferred = audiences()
    guidance = {k for k in json.loads((_V2 / 'i18n' / 'en.json').read_text(encoding='utf-8'))
                if k.startswith('guidance-')}
    assert guidance, 'no guidance-* messages found; has the namespace been renamed?'
    assert guidance <= deferred
    assert guidance <= _deferred_from_config()


def test_the_split_is_not_vacuous():
    """Both sides must be non-empty, and the audience scan must actually resolve call sites."""
    participant, admin_only = audiences()
    assert len(participant) > 100, len(participant)
    assert len(admin_only) > 100, len(admin_only)
    # A key known to render on a participant screen through the server-label map.
    assert 'phase-label-submission' in participant
    # A key only the admin console reaches.
    assert 'phase-route-default_7' in admin_only

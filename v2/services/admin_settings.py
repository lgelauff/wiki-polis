"""Conversation settings projection and convergent update commands."""

from dataclasses import dataclass

from db import GATING_TYPES
from services.access import conversation_gating_type, is_gated_conversation


class AccessSettingsLocked(ValueError):
    """Raised when a preparation-only access setting changes after Explore."""

    def __init__(self, field: str):
        super().__init__(field)
        self.field = field


class InvalidAccessSettings(ValueError):
    """Raised when the explicit gated settings are internally inconsistent."""


def build_admin_settings(
    *, conversation, recommendation_tiers: dict, recommendation_profile: dict,
    phase_route_label: str, can_edit: bool, self_link: str, lifecycle_link: str,
) -> dict:
    return {
        'conversation': {
            'id': conversation.id,
            'slug': conversation.slug,
            'title': conversation.title,
            'introHtml': conversation.intro_text or '',
            'outroHtml': conversation.outro_text or '',
            'accessPolicy': conversation.access_policy,
            'gated': is_gated_conversation(conversation),
            'gatingType': conversation_gating_type(conversation),
            'announce': bool(getattr(conversation, 'announce', False)),
            'information': bool(getattr(conversation, 'information', False)),
            'resultsShared': bool(getattr(conversation, 'results_shared', False)),
            'showUsernames': bool(getattr(conversation, 'show_usernames', False)),
            'accessRequestText': getattr(conversation, 'access_request_text', None),
            'phaseRoute': conversation.phase_route,
            'phaseRouteLabel': phase_route_label,
            'polisId': conversation.polis_id,
        },
        'recommendations': {
            'tier': recommendation_profile['tier'],
            'tiers': [{
                'key': key,
                'label': values['label'],
                'quantities': {
                    quantity: value for quantity, value in values.items()
                    if quantity != 'label'
                },
            } for key, values in recommendation_tiers.items()],
        },
        'eligibility': {
            'configured': bool(conversation.eligibility_event_id),
            'eventId': conversation.eligibility_event_id or '',
            'label': conversation.eligibility_label,
            'configurationMode': 'editable',
            'note': 'Leave the event ID blank when no external eligibility check applies.',
        },
        'capabilities': {'edit': can_edit},
        'locks': {
            'gated': bool(conversation.phase_submission),
            'gatingType': bool(conversation.phase_submission),
            'showUsernames': bool(conversation.phase_submission),
        },
        'links': {'self': self_link, 'lifecycle': lifecycle_link},
    }


@dataclass(frozen=True)
class SettingsUpdateResult:
    changed: bool
    changed_fields: list[str]


def update_recommendation_tier(
    *, conversation, tier: str, session, audit,
) -> bool:
    desired = {'tier': tier}
    changed = conversation.recommended_quantities != desired
    if changed:
        conversation.recommended_quantities = desired
    session.commit()
    if changed:
        audit('recommendations.set', conv_id=conversation.id, tier=tier)
    return changed


def update_conversation_settings(
    *, conversation, title: str, intro_html: str, outro_html: str,
    access_policy: str, eligibility_event_id: str, eligibility_label: str,
    tier: str, sanitise, session, audit,
    gated: bool | None = None, gating_type: str | None = None,
    announce: bool = False, information: bool = False,
    results_shared: bool = False, show_usernames: bool = False,
    access_request_text: str | None = None,
) -> SettingsUpdateResult:
    # The legacy access-policy representation remains accepted for old clients,
    # but every new write is normalised to the explicit gated settings.
    legacy_access_input = gated is None
    if gated is None:
        gated = access_policy == 'invite_only'
        if gated and gating_type is None:
            gating_type = 'invite_only'
    if not isinstance(gated, bool):
        raise InvalidAccessSettings('gated must be boolean')
    if gating_type is not None and gating_type not in GATING_TYPES:
        raise InvalidAccessSettings('unsupported gating type')
    if gated and gating_type is None:
        # A migrated event-id conversation is allowed to remain unconfigured, but
        # a new gated process must choose a provider before it can admit anyone.
        gating_type = conversation_gating_type(conversation)
    if (gated and gating_type is None and not legacy_access_input
            and not getattr(conversation, 'gated', False)):
        raise InvalidAccessSettings('a gated conversation needs a gating type')
    if not gated:
        gating_type = None

    locked_fields = {
        'gated': gated,
        'gating_type': gating_type,
        'show_usernames': bool(show_usernames),
    }
    if conversation.phase_submission:
        for field, desired in locked_fields.items():
            current = getattr(conversation, field, None)
            # A public+event migration is deliberately gated but has no
            # provider selected. It may choose its first provider after
            # Explore starts; subsequent provider changes remain locked.
            if (field == 'gating_type' and current is None
                    and getattr(conversation, 'gated', False)):
                continue
            if current != desired:
                raise AccessSettingsLocked(field)

    legacy_policy = (
        'demo' if access_policy == 'demo'
        else 'invite_only' if gated else 'public'
    )
    desired = {
        'title': title.strip(),
        'intro_text': sanitise(intro_html),
        'outro_text': sanitise(outro_html),
        'access_policy': legacy_policy,
        'gated': gated,
        'gating_type': gating_type,
        'announce': bool(announce),
        'information': bool(information),
        'results_shared': bool(results_shared),
        'show_usernames': bool(show_usernames),
        'access_request_text': (access_request_text or '').strip() or None,
        'eligibility_event_id': eligibility_event_id.strip() or None,
        'eligibility_label': eligibility_label.strip() or None,
        'recommended_quantities': {'tier': tier},
    }
    changed_fields = sorted(
        field for field, value in desired.items()
        if getattr(conversation, field) != value
    )
    for field in changed_fields:
        setattr(conversation, field, desired[field])
    session.commit()
    if changed_fields:
        audit(
            'conversation.settings.update', conv_id=conversation.id,
            fields=changed_fields,
        )
    return SettingsUpdateResult(bool(changed_fields), changed_fields)

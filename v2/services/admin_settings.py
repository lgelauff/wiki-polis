"""Conversation settings projection and convergent update commands."""

from dataclasses import dataclass


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
) -> SettingsUpdateResult:
    desired = {
        'title': title.strip(),
        'intro_text': sanitise(intro_html),
        'outro_text': sanitise(outro_html),
        'access_policy': access_policy,
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

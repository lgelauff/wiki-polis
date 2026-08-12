"""Privacy-safe participant read model for the argument-mapping phase."""

from db import Conversation, Participation


def _side_projection(item: dict, side: str, pseudonym: str,
                     both_contributions_done: bool) -> dict:
    arguments = item[f'{side}_args']
    proposed = item[f'{side}_proposed']
    state = item[f'{side}_state']
    selected_ids = item['voted_ids']
    budget = item['k']
    selected_count = sum(argument.id in selected_ids for argument in arguments)
    prioritization_available = both_contributions_done and len(arguments) > budget
    contribution_status = (
        'submitted' if proposed else 'skipped' if state.skipped else 'pending'
    )
    return {
        'contribution': {
            'status': contribution_status,
            'argumentId': proposed.id if proposed else None,
            'capabilities': {
                'submit': proposed is None,
                'skip': contribution_status == 'pending',
            },
        },
        'prioritization': {
            'available': prioritization_available,
            'requiredArgumentCount': budget + 1,
            'argumentCount': len(arguments),
            'selectionBudget': budget,
            'selectedCount': selected_count,
            'complete': not prioritization_available or selected_count == budget,
        },
        'arguments': [
            {
                'id': argument.id,
                'body': argument.body,
                'own': argument.proposer_pseudonym == pseudonym,
                'selected': argument.id in selected_ids,
                'capabilities': {
                    'prioritize': prioritization_available,
                    'flag': argument.proposer_pseudonym != pseudonym,
                },
            }
            for argument in arguments
        ],
    }


def build_argument_mapping_state(
    *, conversation: Conversation, participation: Participation,
    featured_data: list[dict], links: dict,
) -> dict:
    featured_statements = []
    for item in featured_data:
        both_done = item['pro_gate'] and item['con_gate']
        pro = _side_projection(item, 'pro', participation.pseudonym, both_done)
        con = _side_projection(item, 'con', participation.pseudonym, both_done)
        complete = (
            both_done
            and pro['prioritization']['complete']
            and con['prioritization']['complete']
        )
        featured_statements.append({
            'id': item['fs'].id,
            'statement': {
                'id': item['fs'].polis_statement_id,
                'text': item['text'],
            },
            'contributionsComplete': both_done,
            'complete': complete,
            'sides': {'pro': pro, 'con': con},
            'capabilities': {'flagStatement': True},
        })

    complete_count = sum(item['complete'] for item in featured_statements)
    current = next(
        (item['id'] for item in featured_statements if not item['complete']),
        featured_statements[0]['id'] if featured_statements else None,
    )
    return {
        'slug': conversation.slug,
        'title': conversation.title,
        'pseudonym': participation.pseudonym,
        'progress': {
            'completed': complete_count,
            'total': len(featured_statements),
            'allDone': bool(featured_statements) and complete_count == len(featured_statements),
            'currentFeaturedStatementId': current,
        },
        'featuredStatements': featured_statements,
        'capabilities': {
            'contribute': True,
            'prioritize': True,
            'flag': True,
        },
        'links': links,
    }

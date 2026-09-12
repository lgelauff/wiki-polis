import type {Message} from './messages';

/** Rule 6 of `plan_i18n.md`: a UI label is never shipped from the server as English.
 *
 *  Several API reads still send both a stable identifier and a display label — the label
 *  predates the catalogue. The identifier is the translatable one, so map it here and
 *  ignore the label. Until those fields are dropped from the contract they stay available
 *  as a last-resort fallback: an identifier the catalogue does not know degrades to the
 *  server's English rather than to a visible message key.
 *
 *  These maps are deliberately explicit rather than built by string concatenation. A
 *  runtime-built key (`msg('phase-label-' + target)`) is invisible to the key-existence
 *  guard in `tests/test_i18n.py`, which is what let the previous generation of these keys
 *  rot unnoticed when the templates using them were deleted. */

/** Phase identifiers as they appear in `scheduled_transition.target` and the phase DTOs. */
const PHASE_MESSAGES: Record<string, string> = {
  preparation: 'phase-label-preparation',
  submission: 'phase-label-submission',
  featured_selection: 'phase-label-featured_selection',
  argument_mapping: 'phase-label-argument_mapping',
  cleanup: 'phase-label-cleanup',
  // The server distinguishes the cleanup *window* from the cleanup phase; participants see
  // one concept, so both resolve to one message rather than minting a near-duplicate.
  cleanup_window: 'phase-label-cleanup',
  informed_voting: 'phase-label-informed_voting',
  public_results: 'phase-label-public_results',
  closed: 'adminconv-status-closed',
};

/** Workspace tab identifiers from `conversation_workspace.TAB_LABELS`. */
const TAB_MESSAGES: Record<string, string> = {
  vote: 'conv-tab-vote',
  results: 'conv-tab-results',
  arguments: 'conv-tab-arguments',
  'informed-voting': 'conv-tab-informed',
  'p6-results': 'conv-tab-preliminary',
};

/** Phase-route identifiers from `app.PHASE_ROUTES`. */
const ROUTE_MESSAGES: Record<string, string> = {
  default_7: 'phase-route-default_7',
  no_informed_vote: 'phase-route-no_informed_vote',
  short_results: 'phase-route-short_results',
};

function resolve(
  table: Record<string, string>,
  msg: Message,
  id: string | null | undefined,
  serverLabel?: string | null,
): string {
  const key = id ? table[id] : undefined;
  if (key) return msg(key);
  return serverLabel ?? id ?? '';
}

export const phaseLabel = (msg: Message, id: string | null | undefined, serverLabel?: string | null) =>
  resolve(PHASE_MESSAGES, msg, id, serverLabel);

export const tabLabel = (msg: Message, id: string | null | undefined, serverLabel?: string | null) =>
  resolve(TAB_MESSAGES, msg, id, serverLabel);

export const routeLabel = (msg: Message, id: string | null | undefined, serverLabel?: string | null) =>
  resolve(ROUTE_MESSAGES, msg, id, serverLabel);

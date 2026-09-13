import type {Message} from './messages';

/** Rule 6 of `plan_i18n.md`: a UI label is never shipped from the server as English.
 *
 *  Several API reads still send both a stable identifier and a display label — the label
 *  predates the catalogue. The identifier is the translatable one, so map it here and
 *  ignore the label. Until those fields are dropped from the contract they stay available
 *  as a fallback, for BOTH ways this can fail: an identifier the table does not know, and
 *  a key the catalogue does not hold (the likelier case, and the reason `resolve()` below
 *  compares the result against the key rather than trusting it).
 *
 *  The maps are explicit rather than built by string concatenation so that the keys are
 *  greppable and reviewable. That alone does not make them visible to the key-existence
 *  guard in `tests/test_i18n.py` — its scanner only matches literal `msg('...')` call
 *  sites, and the sole call site here passes a variable. `_MAP_KEY_RE` in that file scans
 *  this module's map values specifically; keep the `<id>: 'message-key',` shape so it
 *  keeps matching. Without that scan these keys would rot exactly as the previous
 *  generation did when the templates using them were deleted. */

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
  closed: 'phase-label-closed',
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
  // Object.hasOwn, not a bare lookup: a bare lookup reaches Object.prototype, so an id of
  // 'constructor' or 'toString' would hand a non-string to msg().
  const key = id && Object.hasOwn(table, id) ? table[id] : undefined;
  if (key) {
    const text = msg(key);
    // banana returns the key itself for a message it does not have, so an absent key or a
    // catalogue that failed to load would otherwise render `conv-tab-vote` to the user --
    // and for a tab, that string is its accessible name. Compare against the key rather
    // than against emptiness so ?uselang=qqx ('(conv-tab-vote)') still wins.
    if (text !== key) return text;
  }
  return serverLabel ?? id ?? '';
}

export const phaseLabel = (msg: Message, id: string | null | undefined, serverLabel?: string | null) =>
  resolve(PHASE_MESSAGES, msg, id, serverLabel);

export const tabLabel = (msg: Message, id: string | null | undefined, serverLabel?: string | null) =>
  resolve(TAB_MESSAGES, msg, id, serverLabel);

export const routeLabel = (msg: Message, id: string | null | undefined, serverLabel?: string | null) =>
  resolve(ROUTE_MESSAGES, msg, id, serverLabel);

/** Consultation-output identifiers from `app.OUTPUT_DEFINITIONS`, as they reach the
 *  conversation lane. Three tables rather than one key built from `output-${key}-label`:
 *  a concatenated key is invisible to the key-existence guard, which is the failure these
 *  tables exist to prevent. */
const OUTPUT_LABEL_MESSAGES: Record<string, string> = {
  'initial-clustering': 'output-initial-clustering-label',
  'argument-map': 'output-argument-map-label',
  'preliminary-results': 'output-preliminary-results-label',
  report: 'output-report-label',
  dataset: 'output-dataset-label',
};

const OUTPUT_TOOLTIP_MESSAGES: Record<string, string> = {
  'initial-clustering': 'output-initial-clustering-tooltip',
  'argument-map': 'output-argument-map-tooltip',
  'preliminary-results': 'output-preliminary-results-tooltip',
  report: 'output-report-tooltip',
  dataset: 'output-dataset-tooltip',
};

const OUTPUT_PENDING_MESSAGES: Record<string, string> = {
  'initial-clustering': 'output-initial-clustering-pending',
  'argument-map': 'output-argument-map-pending',
  'preliminary-results': 'output-preliminary-results-pending',
  report: 'output-report-pending',
  dataset: 'output-dataset-pending',
};

export const outputLabel = (msg: Message, id: string | null | undefined, serverLabel?: string | null) =>
  resolve(OUTPUT_LABEL_MESSAGES, msg, id, serverLabel);

export const outputTooltip = (msg: Message, id: string | null | undefined, serverLabel?: string | null) =>
  resolve(OUTPUT_TOOLTIP_MESSAGES, msg, id, serverLabel);

export const outputPending = (msg: Message, id: string | null | undefined, serverLabel?: string | null) =>
  resolve(OUTPUT_PENDING_MESSAGES, msg, id, serverLabel);

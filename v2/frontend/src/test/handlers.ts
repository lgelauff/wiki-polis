import {http, HttpResponse} from 'msw';

import type {components} from '../api/schema';

type Role = 'moderator' | 'organizer';

function lifecycleFixture(schedule = {canSchedule: true, scheduledAt: null as string | null, targetKey: null as string | null, targetLabel: null as string | null, frozen: false}): components['schemas']['AdminLifecycle'] {
  return {
    conversation: {id: 7, slug: 'community-strategy', title: 'Community strategy', accessPolicy: 'public', status: schedule.scheduledAt && !schedule.frozen ? 'scheduled' : 'active', publication: 'not_applicable', closedAt: null, identityReveal: null},
    operator: {roleLabel: 'Global admin'},
    phase: {linear: true, currentIndex: 0, activeKeys: ['preparation'], steps: [
      {key: 'preparation', label: 'Preparation', effect: 'Configure and seed the conversation.', state: 'current'},
      {key: 'submission', label: 'Explore', effect: 'Participants submit and vote on statements.', state: 'upcoming'},
      {key: 'public_results', label: 'Report', effect: 'Prepare and publish final results.', state: 'upcoming'},
    ], transition: {source: {key: 'preparation', label: 'Preparation'}, target: {key: 'submission', label: 'Explore'}, consequence: {opens: 'Participant statement submission and voting', closes: 'Conversation setup'}, preconditions: [{id: 'ready', label: 'The statement set and introduction are ready', met: null, note: null}], requiresPhase6Initialization: false, showPauseGuidance: false}, phase6Setup: null, advancedControls: [
      {key: 'submission', label: 'Explore', effect: 'Participants submit and vote on statements.', active: false, requiresInitialization: false, initialized: true},
      {key: 'argument_mapping', label: 'Arguments', effect: 'Participants add and rate arguments.', active: false, requiresInitialization: false, initialized: true},
      {key: 'informed_voting', label: 'Informed vote', effect: 'Participants vote after reviewing arguments.', active: false, requiresInitialization: true, initialized: false},
      {key: 'public_results', label: 'Report', effect: 'Prepare final results.', active: false, requiresInitialization: false, initialized: true},
    ]},
    schedule,
    publicationReadiness: {windowOpen: false, preconditions: [{id: 'phase6_initialized', label: 'Informed voting round initialized', met: false, note: 'Initialize informed voting before publishing.'}]},
    statistics: {upstreamUnavailable: false, groups: [{key: 'preparation', label: 'Preparation', tiles: []}], informedVoting: null},
    counts: {participants: 12, invitations: 3, openFlags: 1, featuredStatements: 4}, capabilities: {advancePhase: true, pause: true, publish: false, editSettings: true, useAdvancedPhases: true, initializePhase6: false, archive: true},
    links: {self: '/api/v1/admin/conversations/7', participantView: '/c/community-strategy', participants: '/admin/conversations/7/participants', moderation: '/admin/conversations/7/flags', invitations: '/admin/conversations/7/invites', roles: '/admin/conversations/7/roles', statements: '/admin/conversations/7/statements', featuredStatements: '/admin/conversations/7/featured', settings: '/admin/conversations/7/settings', termination: '/admin/conversations/7/termination'},
  };
}

function statementWorkspaceFixture(
  mode: 'moderate' | 'auto_approve' = 'moderate',
): components['schemas']['AdminStatementWorkspace'] {
  return {
    conversation: {id: 7, slug: 'community-strategy', title: 'Community strategy'},
    statements: {
      pending: [{id: 11, text: 'A participant proposal awaiting review.', moderation: 'pending', seed: false, featured: false, votes: {agree: 2, pass: 1, disagree: 3}, provenance: null}],
      approved: [{id: 12, text: 'An approved seed statement.', moderation: 'approved', seed: true, featured: true, votes: {agree: 8, pass: 2, disagree: 1}, provenance: null}],
      hidden: [],
    },
    moderationPolicy: {mode, newStatements: mode === 'moderate' ? 'pending' : 'approved', available: true},
    dataAvailability: {statements: true},
    seeding: {allowed: true, lockReason: null, maxStatementsPerImport: 20, maxCharactersPerStatement: 280},
    capabilities: {moderate: true, seed: true},
    links: {self: '/api/v1/admin/conversations/7/statements', lifecycle: '/admin/conversations/7'},
  };
}

export function adminCatalogFixture(
  includeNewAdmin = false,
): components['schemas']['AdminCatalog'] {
  return {
    conversations: [{id: 7, slug: 'community-strategy', title: 'Community strategy', accessPolicy: 'public', status: 'active', createdAt: '2026-08-01T10:00:00Z', links: {participant: '/c/community-strategy', manage: '/admin/conversations/7'}}],
    globalAdmins: [
      {participantId: 1, username: 'adminuser'},
      ...(includeNewAdmin ? [{participantId: 23, username: 'Example editor'}] : []),
    ],
    phaseRoutes: [{key: 'default_7', label: 'Full consultation', description: 'Explore through informed voting and report.'}],
    creation: {mode: 'manual_polis_id', defaultModerationPolicy: 'moderate'},
    links: {self: '/api/v1/admin'},
  };
}

/** Receipt returned by a successful guided phase advance.
 *
 * `transition` overrides let a test model a partial failure (for example a Polis
 * results-visibility desync) without restating the whole lifecycle payload. */
export function phaseAdvanceFixture(
  transition: Partial<components['schemas']['AdminPhaseAdvanceReceipt']['transition']> = {},
): components['schemas']['AdminPhaseAdvanceReceipt'] {
  const receipt = {
      transition: {sourceKey: 'preparation', targetKey: 'submission', targetLabel: 'Explore', phase6Created: false, phase6SyncMessage: null, visibilitySynced: true},
      lifecycle: {
        conversation: {id: 7, slug: 'community-strategy', title: 'Community strategy', accessPolicy: 'public', status: 'active', publication: 'not_applicable', closedAt: null, identityReveal: null},
        operator: {roleLabel: 'Global admin'},
        phase: {linear: true, currentIndex: 1, activeKeys: ['submission'], steps: [{key: 'preparation', label: 'Preparation', effect: 'Configure and seed the conversation.', state: 'completed'}, {key: 'submission', label: 'Explore', effect: 'Participants submit and vote on statements.', state: 'current'}, {key: 'public_results', label: 'Report', effect: 'Prepare and publish final results.', state: 'upcoming'}], transition: null, phase6Setup: null, advancedControls: [{key: 'submission', label: 'Explore', effect: 'Participants submit and vote on statements.', active: true, requiresInitialization: false, initialized: true}]},
        schedule: {canSchedule: true, scheduledAt: null, targetKey: null, targetLabel: null, frozen: false},
        publicationReadiness: {windowOpen: false, preconditions: [{id: 'phase6_initialized', label: 'Informed voting round initialized', met: false, note: 'Initialize informed voting before publishing.'}]},
        statistics: {upstreamUnavailable: false, groups: [{key: 'submission', label: 'Explore', tiles: []}], informedVoting: null},
        counts: {participants: 12, invitations: 3, openFlags: 1, featuredStatements: 4},
        capabilities: {advancePhase: false, pause: true, publish: false, editSettings: true, useAdvancedPhases: true, initializePhase6: false, archive: true},
        links: {self: '/api/v1/admin/conversations/7', participantView: '/c/community-strategy', participants: '/admin/conversations/7/participants', moderation: '/admin/conversations/7/flags', invitations: '/admin/conversations/7/invites', roles: '/admin/conversations/7/roles', statements: '/admin/conversations/7/statements', featuredStatements: '/admin/conversations/7/featured', settings: '/admin/conversations/7/settings', termination: '/admin/conversations/7/termination'},
      },
  } as components['schemas']['AdminPhaseAdvanceReceipt'];
  return {...receipt, transition: {...receipt.transition, ...transition}};
}

/** Messages the wired surfaces need. Values are copied from v2/i18n/en.json --
 *  a test asserting rendered text is then asserting the real English. */
export const testMessages: Record<string, string> = {
  'conv-tab-preliminary': 'Preliminary results',
  'conv-p6-badge-prelim': 'Preliminary',
  'conv-participant-count': '$1 {{PLURAL:$1|participant|participants}}',
  'conv-p6-counts-unavailable': 'Detailed vote counts are not available right now.',
  'conv-p6-table-aria': 'Preliminary informed voting results by statement',
  'conv-col-statement': 'Statement',
  'conv-col-initial-vote': 'Initial vote',
  'conv-col-initial-title': 'Phase 2 — initial voting',
  'conv-col-informed-vote': 'Informed vote',
  'conv-col-informed-title': 'Phase 6 — informed voting',
  'conv-col-shift': 'Shift',
  'conv-col-shift-title': 'Change in agree rate',
  'conv-col-yours': 'Yours',
  'conv-bar-title': 'Agree $1% · Disagree $2% · Pass $3%',
  'conv-bar-label': '$1% agree · $2% pass',

  // The admin lifecycle console.
  "admin-btn-remove": "remove",
  "admin-crumb-aria": "Admin breadcrumb",
  "admin-label-access": "Access policy",
  "admin-label-elig-event": "Eligibility event ID",
  "admin-label-elig-label": "Eligibility label",
  "admin-label-intro": "Intro text (HTML, optional)",
  "admin-label-outro": "Outro text (HTML, optional)",
  "admin-label-title": "Title",
  "admin-nav-panel": "Admin panel",
  "admin-th-participant": "Participant",
  "adminconv-add-role": "Add role",
  "adminconv-admin-can-adjust": "A site admin can adjust this.",
  "adminconv-advanced-note": "<strong>Advanced.</strong> These toggles act independently and out of order, with no readiness checks — for demos and recovery, not routine runs.",
  "adminconv-assigned-count": "$1 assigned",
  "adminconv-card-featured": "Featured statements",
  "adminconv-card-featured-desc": "Curate the set for arguments & informed voting",
  "adminconv-card-invites": "Invites & access",
  "adminconv-card-invites-desc": "Who can join this consultation",
  "adminconv-card-modqueue": "Moderation queue",
  "adminconv-card-modqueue-desc": "Review participant flags for statements and arguments",
  "adminconv-card-participants": "Participants",
  "adminconv-card-participants-desc": "Review per-participant engagement and drop-off signals",
  "adminconv-card-roles-desc": "Review moderator and organizer access",
  "adminconv-card-statements": "Statements",
  "adminconv-card-statements-desc": "Review, approve or hide statements; add seed statements",
  "adminconv-closed-cannot-reopen": "Cannot be reopened.",
  "adminconv-closed-on": "Closed $1.",
  "adminconv-closed-undated": "Closed.",
  "adminconv-command-failed": "The command could not be completed.",
  "adminconv-config-label": "Configuration",
  "adminconv-confirm-delete": "Delete this consultation?\n\nThis removes local ProtoWiki records after hiding the Polis conversation. This cannot be undone.",
  "adminconv-confirm-publish": "Publish the final report?\n\nThis freezes report exclusions, closes the consultation, and starts the identity reveal timeline.",
  "adminconv-content-access": "Content & access",
  "adminconv-countdown-days": "$1d",
  "adminconv-countdown-hours": "$1h",
  "adminconv-countdown-lt1m": "<1m",
  "adminconv-countdown-minutes": "$1m",
  "adminconv-custom-state": "Phases are in a custom state (more than one active).",
  "adminconv-danger-label": "Ending the consultation",
  "adminconv-delete-available": "Available because Polis has no valid votes for this consultation.",
  "adminconv-delete-btn": "Delete consultation",
  "adminconv-delete-desc": "Deletes the local consultation after deactivating and hiding it in Polis.",
  "adminconv-delete-hasvotes": "Disabled because Polis has $1 valid {{PLURAL:$1|vote|votes}}.",
  "adminconv-delete-title": "Delete empty consultation",
  "adminconv-delete-unverified": "Disabled because Polis vote data could not be verified.",
  "adminconv-doc-title": "Manage $1 — ProtoWiki",
  "adminconv-due-now": "due now",
  "adminconv-edit": "Edit",
  "adminconv-featured-count": "$1 featured",
  "adminconv-freeze": "Freeze",
  "adminconv-frozen": "frozen",
  "adminconv-informed-voting-label": "Informed voting",
  "adminconv-invite-count": "$1 {{PLURAL:$1|invite|invites}}",
  "adminconv-joined": "$1 joined",
  "adminconv-journey-aria": "Consultation phase progress",
  "adminconv-label-participant": "Participant",
  "adminconv-label-polis-id": "Polis ID (zinvite, read-only)",
  "adminconv-label-role": "Role",
  "adminconv-label-route-locked": "Route (locked after launch)",
  "adminconv-label-tier": "Complexity tier",
  "adminconv-largest-shift": "Largest shift",
  "adminconv-managing": "managing",
  "adminconv-met": "met",
  "adminconv-mode-advanced": "Advanced",
  "adminconv-mode-aria": "Phase control mode",
  "adminconv-mode-simple": "Simple",
  "adminconv-moderation": "Moderation:",
  "adminconv-move-hint": "Confirm every item above to enable “Move on”. Anything marked “not met yet” must be resolved first.",
  "adminconv-move-on-to": "Move on to $1 →",
  "adminconv-multiple-active": "Multiple phases active",
  "adminconv-need-time": "Need time to coordinate inviting people back? You can pause first.",
  "adminconv-no-blocking": "No blocking checks — confirm each item below to move on to $1",
  "adminconv-no-roles": "No conversation roles assigned.",
  "adminconv-no-schedule": "No scheduled transition set.",
  "adminconv-not-met": "not met yet",
  "adminconv-only-organizer": "Only an organizer or site admin can change phases.",
  "adminconv-open-count": "$1 open",
  "adminconv-p6-conv": "Phase 6 Polis conversation:",
  "adminconv-p6-init-btn": "Initialise Phase 6",
  "adminconv-p6-not-init": "Enabled but not initialised. Initialising creates a dedicated Polis conversation and seeds all confirmed featured statements.",
  "adminconv-p6-seeded": "$1 of $2 statements seeded.",
  "adminconv-p6-setup-label": "Informed voting — setup",
  "adminconv-participant-count-unavailable": "participant count unavailable",
  "adminconv-participant-excluded": "· $1 participant excluded",
  "adminconv-participants-round6": "participants in round 6",
  "adminconv-pause": "Pause",
  "adminconv-pause-note": "Pause temporarily disables voting without starting the reveal timeline.",
  "adminconv-paused-note": "Paused — participants cannot vote. The identity-reveal clock has <strong>not</strong> started; resuming is possible.",
  "adminconv-perm-closed": "Permanently closed",
  "adminconv-phase-argmap": "Argument mapping",
  "adminconv-phase-cleanup": "Cleanup",
  "adminconv-phase-control": "Phase control",
  "adminconv-phase-desc-published": "The final aggregate report is published and participant activity is closed.",
  "adminconv-phase-informed": "Informed voting",
  "adminconv-phase-personal": "Personal results",
  "adminconv-phase-public": "Public results",
  "adminconv-phase-submission": "Statement submission (Explore)",
  "adminconv-publish-irrev": "Irreversible. Publishes <code>$1</code>, freezes moderation exclusions, and starts the identity-reveal window.",
  "adminconv-publish-report": "Publish final report",
  "adminconv-publish-unavailable": "Available after informed voting has ended and the consultation is in the cleanup window.",
  "adminconv-readiness-label": "Readiness",
  "adminconv-readiness-unmet": "$1 {{PLURAL:$1|readiness check|readiness checks}} still need resolving before $2",
  "adminconv-rec-help": "These numbers are advisory. They appear in readiness checks and stats so organizers can judge whether the consultation has enough material to move on.",
  "adminconv-rec-summary": "Recommended quantities",
  "adminconv-report-published-note": "<strong>Final report published.</strong> The frozen aggregate results are open.",
  "adminconv-report-unpublished-note": "<strong>Report phase reached — not yet published.</strong> Complete cleanup and use “Publish final report” below to open the frozen results.",
  "adminconv-resume": "Resume",
  "adminconv-reveal-ended": "The identity-reveal window has ended — records are permanently pseudonymous.",
  "adminconv-reveal-open-date": "The identity-reveal window is open until $1.",
  "adminconv-reveal-pending": "The identity-reveal window opens on $1 ($2 {{PLURAL:$2|day|days}} away) — nothing to do until then.",
  "adminconv-role-title": "Your assigned role on this platform",
  "adminconv-roles-label": "Conversation roles",
  "adminconv-roles-summary": "Roles",
  "adminconv-roles-summary-count": "Roles ($1)",
  "adminconv-save-phases": "Save phases",
  "adminconv-save-rec": "Save recommendations",
  "adminconv-save-settings": "Save settings",
  "adminconv-schedule-title": "Schedule wind-down to $1",
  "adminconv-scheduled-aria": "Scheduled transition time in UTC",
  "adminconv-scheduling-unavailable": "Scheduling unavailable.",
  "adminconv-scheduling-why": "Opening an active participant phase still requires the full manual checklist.",
  "adminconv-select-placeholder": "— select —",
  "adminconv-set": "Set",
  "adminconv-settings-summary": "Settings — title, intro/outro, access policy",
  "adminconv-several-open": "Several phases are open at once (advanced mode).",
  "adminconv-statements-voted-on": "statements voted on",
  "adminconv-stats-below": "Statistics for the phases with available data are shown below.",
  "adminconv-stats-warning": "<strong>Live statistics unavailable.</strong> Vote and participant counts may be missing or stale — the Polis statistics database may be unreachable, or this conversation may not yet be registered in Polis. Check the server logs.",
  "adminconv-status-active": "Active",
  "adminconv-status-closed": "Closed",
  "adminconv-status-paused": "Paused",
  "adminconv-status-published": "Published",
  "adminconv-status-scheduled": "Scheduled",
  "adminconv-status-unpublished": "Not yet published",
  "adminconv-step-completed": "(completed)",
  "adminconv-step-current": "(current phase)",
  "adminconv-step-upcoming": "(upcoming)",
  "adminconv-stmt-excluded": "$1 stmt excluded",
  "adminconv-tag-closes": "Closes",
  "adminconv-tag-opens": "Opens",
  "adminconv-tag-undo": "Undo",
  "adminconv-th-role": "Role",
  "adminconv-undo-text": "Reversible only by a site admin via advanced controls.",
  "adminconv-unfreeze": "Unfreeze",
  "adminconv-use-advanced": "Use Advanced below to adjust.",
  "adminconv-utc-timestamp": "UTC timestamp",
  "adminconv-view-as": "View as participant →",
  "adminconv-view-report": "View final report",
  "adminconv-you-are-in-phase": "You are in phase $1 of $2",
  'common-cancel': 'Cancel',
  "flash-move-sync-failed": "Phase moved, but updating results visibility in Polis failed.",
  "flash-moved-to": "Moved to: $1.",
  "flash-phases-saved-sync-failed": "Phases saved, but updating results visibility in Polis failed — results may not appear until you save phases again.",

  // The final report page.
  'output-howto-heading': 'How to read this output',
  'output-method-label': 'Method',
  'output-produced-from': 'Produced from',
  'output-status-label': 'Status',
  'report-argmap-heading': 'Argument mapping',
  'report-argmap-placeholder': 'Argument mapping summary not yet available. This section will show: arguments submitted per statement, most-upvoted pro/con arguments, and participation in argument voting.',
  'report-badge-agree': 'agree',
  'report-badge-disagree': 'disagree',
  'report-badge-final': 'Final',
  'report-bar-label': '$1% agree · $2% pass · $3 {{PLURAL:$3|vote|votes}}',
  'report-bar-title': 'Agree $1% · Disagree $2% · Pass $3%',
  'report-closed-suffix': '· closed',
  'report-col-informed': 'Informed',
  'report-col-initial': 'Initial',
  'report-col-shift': 'Shift',
  'report-col-shift-note': '(aggregate)',
  'report-col-statement': 'Statement',
  'report-crumb': 'report',
  'report-divisive-intro': 'Statements with the most evenly split agree/disagree response.',
  'report-featured-count': 'Featured statements used in informed voting: $1',
  'report-group-members': '· $1 {{PLURAL:$1|participant|participants}}',
  'report-groups-heading': 'Opinion groups',
  'report-groups-intro': 'Groups represent clusters of participants with similar voting patterns, identified by PCA + k-means on the informed voting matrix. Statements listed here were most characteristic of each group.',
  'report-groups-sub': '$1 {{PLURAL:$1|group|groups}} identified in the informed voting round',
  'report-highest-agreement': 'Highest agreement',
  'report-initial-heading': 'Initial opinions',
  'report-initial-intro': 'Based on votes cast during the initial submission phase, before participants saw any arguments.',
  'report-initial-sub': 'Phase 2 — before argument mapping',
  'report-intro-heading': 'Introduction',
  'report-intro-placeholder': 'Organizer introduction not yet added. This section should explain what the consultation was about, who organised it, and how the results will be used.',
  'report-landed-body': 'Personalised group comparison — coming soon. This will show how your informed votes compare to each opinion group and where your views sit in the overall distribution.',
  'report-landed-heading': 'Where did you land?',
  'report-matched-heading': 'Matched participant analysis',
  'report-matched-note': 'Note: delta is only directly observable for participants who cast a vote in both Phase 2 and Phase 6. Extrapolation to the full initial-voting cohort requires statistical adjustment; confidence intervals for this extrapolation are under development (pending methodology review).',
  'report-matched-placeholder': 'Matched participant analysis not yet available. This section will show the individual-level opinion change for participants who voted in both rounds, and a population-level extrapolation with confidence intervals.',
  'report-methodology-clustering-body': 'Opinion groups are produced by the Polis algorithm: PCA reduces the participant × statement vote matrix to two dimensions, then k-means clustering groups participants by voting similarity. The number of groups is chosen by silhouette score. Consensus and representative statements for each group are selected by the Polis math service.',
  'report-methodology-clustering-heading': 'Clustering',
  'report-methodology-delta-body': "Individual-level delta — the change in a specific participant's vote between rounds — is only observable for participants who voted in both Phase 2 and Phase 6. Extrapolating from this matched subset to the full initial-voting population requires statistical adjustment for the non-random selection of who returned for Phase 6.",
  'report-methodology-delta-heading': 'Individual delta and extrapolation',
  'report-methodology-delta-placeholder': 'Confidence interval methodology for the extrapolated delta is pending literature review. This section will describe the statistical method used once the approach is finalised.',
  'report-methodology-heading': 'Methodology',
  'report-methodology-link': 'Methodology',
  'report-methodology-shift-body': 'The shift column in the opinion-shift table is computed as <em>Phase 6 agree% − Phase 2 agree%</em>. This is a cross-round <strong>population comparison</strong>, not a paired before/after measurement: Phase 2 and Phase 6 participants are overlapping but not identical sets. A positive shift means the informed-voting cohort agreed at a higher rate, but this may partly reflect differences in who participated rather than genuine attitude change.',
  'report-methodology-shift-heading': 'Aggregate opinion shift',
  'report-methodology-sources-body': 'Vote counts are drawn from the Polis Postgres database (<code>votes_latest_unique</code> view), which holds one vote per participant per statement. Opinion groups (clusters) are computed by the Polis math service and retrieved via the Particiapi results API. Where the two participant counts diverge by more than 5%, a warning is logged. Moderation exclusions (hidden statements, banned participants) are applied before any aggregation.',
  'report-methodology-sources-heading': 'Data sources',
  'report-moderation-applied': 'Moderation applied:',
  'report-moderation-parts': '· $1 {{PLURAL:$1|participant|participants}} excluded',
  'report-moderation-stmts': '$1 {{PLURAL:$1|statement|statements}} excluded',
  'report-most-divisive': 'Most divisive',
  'report-no-results': 'Informed voting results are not available for this consultation yet.',
  'report-participation-both': 'Voted in both rounds',
  'report-participation-heading': 'Participation',
  'report-participation-p2': 'Initial voting (Phase 2)',
  'report-participation-p6': 'Informed voting (Phase 6)',
  'report-participation-unavailable': 'Detailed vote counts are not available — the results database is unreachable.',
  'report-process-argmap': 'Argument mapping',
  'report-process-closed': 'Consultation closed',
  'report-process-dates-tbd': 'dates not stored yet',
  'report-process-heading': 'Process',
  'report-process-informed': 'Informed voting',
  'report-process-opened': 'Consultation opened',
  'report-process-submission': 'Submission phase',
  'report-shift-below': 'below).',
  'report-shift-heading': 'Opinion shift',
  'report-shift-intro': 'Each row compares the initial vote (Phase 2, before arguments) with the informed vote (Phase 6, after argument mapping). <strong>Shift</strong> is the change in population-level agree rate — a cross-round comparison of separate populations, not a matched individual delta (see',
  'report-shift-sorted': 'Sorted by size of shift.',
  'report-shift-sub': 'Did argument exposure change views?',
  'report-statements-heading': 'Statements',
  'report-statements-placeholder': 'Statement inventory not yet available. This section will show: total statements submitted, how many were seed statements vs participant-proposed, and moderation outcomes.',
  'report-status-final': 'Final · frozen at publication',
  'report-subtitle': 'Final results report',
  'report-table-aria': 'Aggregate opinion shift per statement',
  'reveal-callout-link': 'Optionally link your Wikimedia username',
  'reveal-callout-open-text': 'The identity reveal window is open. Your participation is recorded under pseudonym <strong>$1</strong>.',

  // conversation workspace
  'common-opens-in-new-tab': ' (opens in a new tab)',
  'conv-alldone-label': 'For now, you have shared your opinion on all available statements. Please come back later for more!',
  'conv-alldone-sub': 'If you can think of any statements that are missing from the current set, this is your chance to submit them.',
  'conv-closed-on': 'This consultation closed on <strong>$1</strong>. Your votes were recorded under your pseudonym; for a limited time you may optionally and permanently link your Wikimedia username to it.',
  'conv-closed-simple': 'This consultation is closed.',
  'conv-composer-charcount': '$1 / 280',
  'conv-composer-submit': 'Submit & next',
  'conv-crumb-about': 'About',
  'conv-crumb-aria': 'Conversation context',
  'conv-crumb-manage': 'Manage',
  'conv-demo-mode-lock': 'Demonstration conversation — try the full flow. Your input is recorded here, just like a real consultation.',
  'conv-doc-title': '$1 — ProtoWiki',
  'conv-err-submit-vote': 'Could not submit your vote. Please try again.',
  'conv-loading': 'Loading conversation…',
  'conv-newstmt-helper': 'A different angle entirely. One claim, one sentence. Goes to moderation, then into the same pool.',
  'conv-newstmt-hint': 'A separate statement — others will vote on it too',
  'conv-newstmt-limit-reached': 'Limit reached',
  'conv-newstmt-placeholder': 'A new angle on the topic…',
  'conv-newstmt-remaining': '$1 of $2 remaining',
  'conv-newstmt-unlocks-more': 'Unlocks after $1 more {{PLURAL:$1|vote|votes}}',
  'conv-nothing-available': 'Nothing is available yet. Check back soon.',
  'conv-paused': 'This consultation is temporarily paused. Check back soon.',
  'conv-propose-next': 'Next statement',
  'conv-proposed': 'PROPOSED — heading to moderation',
  'conv-read-report': 'Read the final report',
  'conv-reveal-expired': 'The reveal window has closed. Records stay pseudonymous — identities can no longer be linked.',
  'conv-reveal-pending-opens': 'The window opens on $1 — nothing to do until then.',
  'conv-revealed-text': 'You linked your identity — your username is associated with pseudonym <strong>$1</strong> in this consultation\'s records.',
  'conv-scheduled-transition': 'Next: <strong>$1</strong> on $2.',
  'conv-scheduled-tz-title': 'Shown in your local timezone',
  'conv-space-warn-demo-body': 'These are demonstration ballots — not a real consultation.',
  'conv-space-warn-demo-label': 'Demo.',
  'conv-space-warn-demo-link': 'Browse the demo space →',
  'conv-space-warn-live-body': 'These ballots are real — your votes here count. Just exploring?',
  'conv-space-warn-live-label': 'Live consultation.',
  'conv-space-warn-live-link': 'Try the demo space →',
  'conv-space-warn-ok': 'I understand',
  'conv-suggest-helper': 'Stays close to the same idea — just a clearer or fairer phrasing.',
  'conv-suggest-hint': 'Goes into the pool with the original',
  'conv-suggest-placeholder': 'Re-confirmation every five years would balance accountability against admin burnout…',
  'conv-triad-active-label': 'What now?',
  'conv-triad-alldone-label': 'Want to add something new?',
  'conv-triad-idle-label': 'After you vote, you can…',
  'conv-triad-newstmt-action': 'Compose →',
  'conv-triad-newstmt-title': 'Propose a new statement',
  'conv-triad-next-action': 'Next →',
  'conv-triad-next-sub': 'Next statement, nothing to add',
  'conv-triad-next-title': 'Move on',
  'conv-triad-suggest-action': 'Write yours →',
  'conv-triad-suggest-sub': 'Same idea, clearer phrasing',
  'conv-triad-suggest-title': 'Suggest different wording',
  'conv-unavailable-doc-title': 'Conversation unavailable — ProtoWiki',
  'conv-unavailable-heading': 'Conversation unavailable',
  'conv-vote-agree': 'Agree',
  'conv-vote-change': 'change',
  'conv-vote-disagree': 'Disagree',
  'conv-vote-label-agree': 'AGREE',
  'conv-vote-label-disagree': 'DISAGREE',
  'conv-vote-label-pass': 'PASS',
  'conv-vote-pass': 'Pass',
  'conv-vote-private': 'private vote',
  'conv-vote-progress-aria': 'Statements voted',
  'conv-vote-progress-valuetext': '$1 of $2 {{PLURAL:$2|statement|statements}} voted',
  'conv-vote-statement-label': 'STATEMENT',
  'conv-vote-voted-label': 'voted',
  'conv-vote-you-voted': 'YOU VOTED',
  'conv-writing-tips': 'Writing tips',
  'forbidden-invite-back-home': '← back to home',
  'forbidden-invite-body': '<strong>$1</strong> is restricted to invited participants. You have not been added to the invite list for this consultation.',
  'forbidden-invite-doc-title': 'Access restricted — ProtoWiki',
  'forbidden-invite-heading': 'This consultation is invite-only',
  'forbidden-invite-mod-body': 'To participate as a voter, add yourself to the invite list first:',
  'forbidden-invite-mod-lead': 'You can moderate this consultation.',
  'forbidden-invite-mod-link': 'Manage invites →',
  'reveal-tl-aria': 'Identity reveal timeline',
  'reveal-tl-closed-what': 'Closed — linking stays sealed for $1 {{PLURAL:$1|day|days}}',
  'reveal-tl-closes-what': 'Window closes — records stay pseudonymous permanently',
  'reveal-tl-deadline-closes': '<strong>Window closes in</strong> $1.',
  'reveal-tl-deadline-closes-permanent': '<strong>Window closes in</strong> $1 — linking is <strong>permanent and cannot be undone</strong>.',
  'reveal-tl-deadline-opens': 'Reveal window opens in $1.',
  'reveal-tl-now': 'now',
  'reveal-tl-opens-what': 'Window opens — $1 {{PLURAL:$1|day|days}} to optionally link your Wikimedia username',
  'reveal-tl-step-completed': '(completed)',
  'reveal-tl-step-current': '(current)',
  'reveal-tl-step-inprogress': '(in progress — cooldown)',
  'reveal-tl-step-upcoming': '(upcoming)',
};

export const handlers = [
  http.get(new URL('/api/v1/admin', globalThis.location.origin).toString(), () => HttpResponse.json({data: adminCatalogFixture()})),
  http.post(new URL('/api/v1/admin/conversations', globalThis.location.origin).toString(), () => HttpResponse.json({data: {conversation: {id: 7, slug: 'community-strategy', title: 'Community strategy'}, links: {manage: '/admin/conversations/7', catalog: '/api/v1/admin'}}}, {status: 201})),
  http.post(new URL('/api/v1/admin/global-admin-grants', globalThis.location.origin).toString(), async ({request}) => {
    const body = await request.json() as {username: string};
    return HttpResponse.json({data: {participantId: 23, username: body.username, granted: true, changed: true, catalog: adminCatalogFixture(true)}}, {status: 201});
  }),
  http.put(new URL('/api/v1/admin/global-admins/:participantId', globalThis.location.origin).toString(), async ({params, request}) => {
    const body = await request.json() as {granted: boolean};
    return HttpResponse.json({data: {participantId: Number(params.participantId), username: 'Example editor', granted: body.granted, changed: true, catalog: adminCatalogFixture(body.granted)}});
  }),
  http.get(new URL('/api/v1/admin/conversations/7/featured-statements', globalThis.location.origin).toString(), () => HttpResponse.json({data: {
    conversation: {id: 7, slug: 'community-strategy', title: 'Community strategy'},
    selected: [{featuredId: 61, statementId: 12, text: 'An approved seed statement.', systemSuggested: true, provenance: null, arguments: [{id: 71, side: 'pro', body: 'A useful supporting argument.', proposerPseudonym: 'quiet-otter', hidden: false, createdAt: '2026-08-13T10:00:00Z'}]}],
    candidates: [{statementId: 13, text: 'A candidate preserving another viewpoint.', seed: false, votes: {agree: 3, pass: 2, disagree: 1, total: 6, agreementPercent: 75}, provenance: null}],
    dataAvailability: {candidates: true}, phase: {argumentMappingActive: false, informedVotingLive: false}, guidance: {recommendedCount: 15, note: 'Preserve meaningful viewpoints; agreement percentage is descriptive, not a selection score.'}, capabilities: {manage: true},
    links: {self: '/api/v1/admin/conversations/7/featured-statements', lifecycle: '/admin/conversations/7'},
  }})),
  http.put(new URL('/api/v1/admin/conversations/7/featured-statements/:statementId', globalThis.location.origin).toString(), ({params}) => HttpResponse.json({data: {featuredId: 62, statementId: Number(params.statementId), changed: true, links: {featured: '/api/v1/admin/conversations/7/featured-statements'}}})),
  http.delete(new URL('/api/v1/admin/conversations/7/featured-selections/:featuredId', globalThis.location.origin).toString(), ({params}) => HttpResponse.json({data: {featuredId: Number(params.featuredId), statementId: 12, removed: true, links: {featured: '/api/v1/admin/conversations/7/featured-statements'}}})),
  http.put(new URL('/api/v1/admin/conversations/7/featured-arguments/:argumentId', globalThis.location.origin).toString(), async ({params, request}) => {
    const body = await request.json() as {hidden: boolean};
    return HttpResponse.json({data: {argumentId: Number(params.argumentId), hidden: body.hidden, changed: true, links: {featured: '/api/v1/admin/conversations/7/featured-statements'}}});
  }),
  http.delete(new URL('/api/v1/admin/conversations/7/featured-arguments/:argumentId', globalThis.location.origin).toString(), ({params}) => HttpResponse.json({data: {argumentId: Number(params.argumentId), featuredId: 61, deleted: true, links: {featured: '/api/v1/admin/conversations/7/featured-statements'}}})),
  http.get(new URL('/api/v1/admin/conversations/7/statements', globalThis.location.origin).toString(), () => HttpResponse.json({data: statementWorkspaceFixture()})),
  http.post(new URL('/api/v1/admin/conversations/7/statements', globalThis.location.origin).toString(), async ({request}) => {
    const body = await request.json() as {text: string; derivedFromId: number | null};
    return HttpResponse.json({data: {statementId: body.derivedFromId === null ? null : 14, derivedFromId: body.derivedFromId, provenanceRecorded: body.derivedFromId === null ? null : true, links: {statements: '/api/v1/admin/conversations/7/statements'}}}, {status: 201});
  }),
  http.put(new URL('/api/v1/admin/conversations/7/statement-moderation-policy', globalThis.location.origin).toString(), async ({request}) => {
    const body = await request.json() as {mode: 'moderate' | 'auto_approve'};
    return HttpResponse.json({data: {mode: body.mode, changed: true, reconciledStatements: 0, workspace: statementWorkspaceFixture(body.mode)}});
  }),
  http.put(new URL('/api/v1/admin/conversations/7/statements/:statementId/moderation', globalThis.location.origin).toString(), async ({params, request}) => {
    const body = await request.json() as {status: 'approved' | 'pending' | 'hidden'};
    return HttpResponse.json({data: {statementId: Number(params.statementId), status: body.status, links: {statements: '/api/v1/admin/conversations/7/statements'}}});
  }),
  http.post(new URL('/api/v1/admin/conversations/7/statement-imports', globalThis.location.origin).toString(), async ({request}) => {
    const body = await request.json() as {statements: string[]};
    return HttpResponse.json({data: {outcome: {imported: body.statements.length, skippedExisting: 0, skippedDuplicateInput: 0, failedUpstream: 0}, links: {statements: '/api/v1/admin/conversations/7/statements'}}});
  }),
  http.get(new URL('/api/v1/admin/conversations/7/termination', globalThis.location.origin).toString(), () => HttpResponse.json({data: {
    conversation: {id: 7, slug: 'community-strategy', title: 'Community strategy'},
    deletion: {state: 'eligible', validVoteCount: 0, reason: 'No valid votes were found.'},
    links: {self: '/api/v1/admin/conversations/7/termination', lifecycle: '/admin/conversations/7'},
  }})),
  http.delete(new URL('/api/v1/admin/conversations/7', globalThis.location.origin).toString(), () => HttpResponse.json({data: {
    conversationId: 7, deleted: true, links: {admin: '/admin'},
  }})),
  http.get(new URL('/api/v1/admin/conversations/7/settings', globalThis.location.origin).toString(), () => HttpResponse.json({data: {
    conversation: {id: 7, slug: 'community-strategy', title: 'Community strategy', introHtml: '<p>Shape the future.</p>', outroHtml: '', accessPolicy: 'public', phaseRoute: 'default_7', phaseRouteLabel: 'Full consultation', polisId: 'polis-community-strategy'},
    recommendations: {tier: 'medium', tiers: [
      {key: 'simple', label: 'Simple topic', quantities: {seed_statements: 5, featured_statements: 8}},
      {key: 'medium', label: 'Medium topic', quantities: {seed_statements: 8, featured_statements: 15}},
      {key: 'complex', label: 'Complex topic', quantities: {seed_statements: 12, featured_statements: 24}},
    ]},
    eligibility: {configured: true, eventId: 'extended-confirmed', label: 'Extended-confirmed editors', configurationMode: 'editable', note: 'Leave the event ID blank when no external eligibility check applies.'},
    capabilities: {edit: true}, links: {self: '/api/v1/admin/conversations/7/settings', lifecycle: '/admin/conversations/7'},
  }})),
  http.put(new URL('/api/v1/admin/conversations/7/settings', globalThis.location.origin).toString(), async ({request}) => {
    const body = await request.json() as {title: string; introHtml: string; outroHtml: string; accessPolicy: 'public' | 'invite_only' | 'demo'; eligibilityEventId: string; eligibilityLabel: string; recommendationTier: 'simple' | 'medium' | 'complex'};
    return HttpResponse.json({data: {changed: true, changedFields: ['title'], settings: {
      conversation: {id: 7, slug: 'community-strategy', title: body.title.trim(), introHtml: body.introHtml, outroHtml: body.outroHtml, accessPolicy: body.accessPolicy, phaseRoute: 'default_7', phaseRouteLabel: 'Full consultation', polisId: 'polis-community-strategy'},
      recommendations: {tier: body.recommendationTier, tiers: [{key: 'simple', label: 'Simple topic', quantities: {seed_statements: 5}}, {key: 'medium', label: 'Medium topic', quantities: {seed_statements: 8}}, {key: 'complex', label: 'Complex topic', quantities: {seed_statements: 12}}]},
      eligibility: {configured: Boolean(body.eligibilityEventId), eventId: body.eligibilityEventId, label: body.eligibilityLabel || null, configurationMode: 'editable', note: 'Leave the event ID blank when no external eligibility check applies.'}, capabilities: {edit: true}, links: {self: '/api/v1/admin/conversations/7/settings', lifecycle: '/admin/conversations/7'},
    }}});
  }),
  http.put(new URL('/api/v1/admin/conversations/7/recommendation-tier', globalThis.location.origin).toString(), async ({request}) => {
    const body = await request.json() as {tier: 'simple' | 'medium' | 'complex'};
    return HttpResponse.json({data: {changed: true, recommendations: {
      tier: body.tier,
      tiers: [{key: 'simple', label: 'Simple topic', quantities: {seed_statements: 5}}, {key: 'medium', label: 'Medium topic', quantities: {seed_statements: 8}}, {key: 'complex', label: 'Complex topic', quantities: {seed_statements: 12}}],
    }}});
  }),
  http.get(new URL('/api/v1/admin/conversations/7', globalThis.location.origin).toString(), () => HttpResponse.json({data: lifecycleFixture()})),
  http.put(new URL('/api/v1/admin/conversations/7/schedule', globalThis.location.origin).toString(), async ({request}) => {
    const body = await request.json() as {scheduledAt: string | null; frozen: boolean};
    return HttpResponse.json({data: {changed: true, lifecycle: lifecycleFixture({canSchedule: true, scheduledAt: body.scheduledAt, targetKey: body.scheduledAt ? 'submission' : null, targetLabel: body.scheduledAt ? 'Explore' : null, frozen: body.frozen})}});
  }),
  http.put(new URL('/api/v1/admin/conversations/7/pause', globalThis.location.origin).toString(), async ({request}) => {
    const body = await request.json() as {paused: boolean};
    const lifecycle = lifecycleFixture();
    lifecycle.conversation.status = body.paused ? 'paused' : 'active';
    return HttpResponse.json({data: {paused: body.paused, changed: true, lifecycle}});
  }),
  http.put(new URL('/api/v1/admin/conversations/7/archive', globalThis.location.origin).toString(), async ({request}) => {
    const body = await request.json() as {archived: boolean};
    const lifecycle = lifecycleFixture();
    lifecycle.conversation.status = body.archived ? 'archived' : 'active';
    lifecycle.phase.activeKeys = body.archived ? [] : lifecycle.phase.activeKeys;
    lifecycle.schedule.canSchedule = !body.archived;
    lifecycle.capabilities.advancePhase = !body.archived;
    lifecycle.capabilities.pause = !body.archived;
    return HttpResponse.json({data: {archived: body.archived, changed: true, lifecycle}});
  }),
  http.put(new URL('/api/v1/admin/conversations/7/phases', globalThis.location.origin).toString(), async ({request}) => {
    const body = await request.json() as {activeKeys: string[]};
    const lifecycle = lifecycleFixture();
    lifecycle.phase.linear = body.activeKeys.length <= 1;
    lifecycle.phase.activeKeys = body.activeKeys;
    lifecycle.phase.transition = body.activeKeys.length > 1 ? null : lifecycle.phase.transition;
    lifecycle.phase.advancedControls = lifecycle.phase.advancedControls.map((row) => ({...row, active: body.activeKeys.includes(row.key)}));
    lifecycle.capabilities.initializePhase6 = body.activeKeys.includes('informed_voting');
    return HttpResponse.json({data: {changed: true, activeKeys: body.activeKeys, visibilitySynced: true, lifecycle}});
  }),
  http.post(new URL('/api/v1/admin/conversations/7/phase6-initialization', globalThis.location.origin).toString(), () => {
    const lifecycle = lifecycleFixture();
    lifecycle.phase.linear = false;
    lifecycle.phase.activeKeys = ['argument_mapping', 'informed_voting'];
    lifecycle.phase.advancedControls = lifecycle.phase.advancedControls.map((row) => ({
      ...row,
      active: lifecycle.phase.activeKeys.includes(row.key),
      initialized: row.key === 'informed_voting' ? true : row.initialized,
    }));
    lifecycle.phase.phase6Setup = {
      polisConversationId: 'polis-community-strategy-phase6',
      seededStatementCount: 4,
      confirmedStatementCount: 4,
    };
    lifecycle.capabilities.initializePhase6 = false;
    return HttpResponse.json({data: {initialized: true, lifecycle}}, {status: 201});
  }),
  http.put(new URL('/api/v1/admin/conversations/7/phase', globalThis.location.origin).toString(), () => HttpResponse.json({data: phaseAdvanceFixture()})),
  http.get(new URL('/api/v1/admin/conversations/7/roles', globalThis.location.origin).toString(), () => HttpResponse.json({data: {
    conversation: {id: 7, slug: 'community-strategy', title: 'Community strategy'},
    assignments: [{participantId: 23, username: 'Example editor', roles: ['moderator'], grantedAt: ['2026-08-01T10:00:00Z']}],
    candidates: [{participantId: 23, username: 'Example editor'}],
    availableRoles: ['moderator', 'organizer'], capabilities: {manageRoles: true},
    links: {self: '/api/v1/admin/conversations/7/roles', conversation: '/admin/conversations/7'},
  }})),
  http.put(new URL('/api/v1/admin/conversations/7/roles/23', globalThis.location.origin).toString(), async ({request}) => {
    const body = await request.json() as {roles: Role[]};
    return HttpResponse.json({data: {participantId: 23, username: 'Example editor', roles: body.roles, changed: true, added: ['organizer'], removed: [], links: {roles: '/api/v1/admin/conversations/7/roles'}}});
  }),
  http.get(
    new URL('/api/v1/admin/conversations/7/invitations', globalThis.location.origin).toString(),
    () => HttpResponse.json({data: {
      conversation: {id: 7, slug: 'community-strategy', title: 'Community strategy', accessPolicy: 'invite_only'},
      invitations: [{id: 51, username: 'Existing editor', createdAt: '2026-08-01T10:00:00Z'}],
      capabilities: {manageInvitations: true},
      links: {self: '/api/v1/admin/conversations/7/invitations', conversation: '/admin/conversations/7'},
    }}),
  ),
  http.put(
    new URL('/api/v1/admin/conversations/7/invitations', globalThis.location.origin).toString(),
    async ({request}) => {
      const body = await request.json() as {usernames: string[]};
      return HttpResponse.json({data: {
        outcome: {added: 1, alreadyPresent: 0, concurrentConflicts: 0, duplicateInputs: body.usernames.length - 1},
        invitations: [
          {id: 51, username: 'Existing editor', createdAt: '2026-08-01T10:00:00Z'},
          {id: 52, username: body.usernames[0], createdAt: '2026-08-13T10:00:00Z'},
        ],
        links: {invitations: '/api/v1/admin/conversations/7/invitations'},
      }});
    },
  ),
  http.delete(
    new URL('/api/v1/admin/conversations/7/invitations/:inviteId', globalThis.location.origin).toString(),
    ({params}) => HttpResponse.json({data: {
      invitationId: Number(params.inviteId), removed: true, invitations: [],
      links: {invitations: '/api/v1/admin/conversations/7/invitations'},
    }}),
  ),
  http.get(
    new URL('/api/v1/admin/conversations/7/flags', globalThis.location.origin).toString(),
    () => HttpResponse.json({
      data: {
        conversation: {id: 7, slug: 'community-strategy', title: 'Community strategy'},
        open: [{
          id: 41,
          status: 'open',
          category: 'privacy',
          categoryLabel: 'Privacy violation',
          detail: 'Includes a real name.',
          flaggedAt: '2026-08-13T09:30:00Z',
          target: {
            type: 'statement', id: 12, label: 'Statement #12',
            text: 'A statement containing private information.',
            reviewHref: '/admin/conversations/7/statements',
          },
          resolution: null,
        }],
        resolved: [],
        dataAvailability: {statementText: true},
        capabilities: {resolveFlags: true},
        links: {self: '/api/v1/admin/conversations/7/flags', conversation: '/admin/conversations/7'},
      },
    }),
  ),
  http.put(
    new URL('/api/v1/admin/conversations/7/flags/41/resolution', globalThis.location.origin).toString(),
    async ({request}) => {
      const body = await request.json() as {resolved: true; note?: string | null};
      return HttpResponse.json({data: {
        flagId: 41,
        status: 'resolved',
        changed: true,
        resolution: {resolvedAt: '2026-08-13T10:00:00Z', note: body.note ?? null},
        links: {flags: '/api/v1/admin/conversations/7/flags'},
      }});
    },
  ),
  http.get(
    new URL('/api/v1/admin/conversations/7/participants', globalThis.location.origin).toString(),
    () => HttpResponse.json({
      data: {
        conversation: {id: 7, slug: 'community-strategy', title: 'Community strategy'},
        participants: [{
          participantId: 23,
          username: 'Example editor',
          pseudonym: 'quiet-otter',
          statementProgress: {total: 12, voted: 8, remaining: 4},
          arguments: {submitted: 2, prioritized: 5},
          lastEngagementAt: '2026-08-13T09:30:00Z',
          access: {banned: false, changedAt: null, summary: null},
        }],
        dataAvailability: {statementProgress: true},
        capabilities: {setParticipantAccess: true},
        links: {
          self: '/api/v1/admin/conversations/7/participants',
          conversation: '/admin/conversations/7',
        },
      },
    }),
  ),
  http.put(
    new URL('/api/v1/admin/conversations/7/participants/23/access', globalThis.location.origin).toString(),
    async ({request}) => {
      const body = await request.json() as {banned: boolean; summary?: string | null};
      return HttpResponse.json({
        data: {
          participantId: 23,
          banned: body.banned,
          changed: true,
          changedAt: '2026-08-13T10:00:00Z',
          summary: body.summary ?? null,
          links: {participants: '/api/v1/admin/conversations/7/participants'},
        },
      });
    },
  ),
  // The message catalogue. Real keys and real English, so a component that renders a
  // message asserts the same text a user sees. Only the keys the wired surfaces use --
  // the full catalogue is 853 entries and fixtures should not carry it.
  http.get(
    new URL('/api/v1/i18n/:locale', globalThis.location.origin).toString(),
    ({params}) => {
      const locale = String(params.locale);
      if (locale === 'qqx') {
        return HttpResponse.json(Object.fromEntries(
          Object.keys(testMessages).map((key) => [key, `(${key})`]),
        ));
      }
      return HttpResponse.json(testMessages);
    },
  ),
  http.get(
    new URL('/api/v1/session', globalThis.location.origin).toString(),
    () => HttpResponse.json({
      data: {
        state: 'authenticated',
        user: {username: 'Example editor', emailable: true},
        capabilities: {administerSite: false},
        csrfToken: 'test-csrf-token',
        developerLogins: [],
        gitVersion: 'test-version',
        links: {login: '/login', logout: '/logout'},
      },
    }),
  ),
  http.get(
    new URL('/api/v1/conversations/:slug/moderation-log', globalThis.location.origin).toString(),
    ({params}) => HttpResponse.json({data: {
      slug: String(params.slug),
      title: 'Community strategy',
      events: [
        {occurredAt: '2026-08-14T09:30:00Z', action: 'Banned', pseudonym: 'quiet-otter', scope: 'conversation', actor: 'adminuser'},
        {occurredAt: '2026-08-13T08:15:00Z', action: 'Unbanned', pseudonym: 'patient-fox', scope: 'conversation', actor: 'moderator'},
      ],
      links: {self: `/api/v1/conversations/${String(params.slug)}/moderation-log`, conversation: `/c/${String(params.slug)}`, about: `/c/${String(params.slug)}/about`},
    }}),
  ),
  http.get(
    new URL('/api/v1/conversations/:slug/outputs/:outputKey', globalThis.location.origin).toString(),
    ({params}) => {
      const key = String(params.outputKey) as components['schemas']['ConversationOutputDetail']['key'];
      const labels = {dataset: 'Dataset', 'argument-map': 'Argument map', 'preliminary-results': 'Preliminary results', report: 'Report', 'initial-clustering': 'Initial clustering'};
      const phases = {dataset: 'Opt-in identity window', 'argument-map': 'Arguments', 'preliminary-results': 'Informed vote', report: 'Publish', 'initial-clustering': 'Explore'};
      return HttpResponse.json({data: {
        slug: String(params.slug),
        title: 'Community strategy',
        output: {
          key,
          label: labels[key],
          phase: phases[key],
          status: key === 'report' ? 'final' : 'provisional',
          ready: key !== 'initial-clustering',
          method: 'A stable, participant-safe method description.',
          pending: 'This output is pending.',
        },
        links: {self: `/api/v1/conversations/${String(params.slug)}/outputs/${key}`, conversation: `/c/${String(params.slug)}`, about: `/c/${String(params.slug)}/about`},
      }});
    },
  ),
  http.get(
    new URL('/api/v1/conversations', globalThis.location.origin).toString(),
    ({request}) => {
    const space = new URL(request.url).searchParams.get('space') ?? 'real';
    return HttpResponse.json({
      data: {
        space,
        authenticated: true,
        groups: {
          needsAttention: [{
            slug: 'community-strategy',
            title: 'Community strategy',
            relationship: 'joined',
            participantState: 'needs_attention',
            pseudonym: 'quiet-otter',
            status: 'open',
            closedAt: null,
            phases: ['submission'],
            statementsRemaining: 4,
            scheduledTransition: null,
            reveal: null,
            outputs: [],
            capabilities: {join: false, participate: true, moderate: false},
            links: {
              self: '/c/community-strategy',
              about: '/c/community-strategy/about',
              explore: '/c/community-strategy',
              informedVoting: '/c/community-strategy#tab-informed-voting',
              results: '/c/community-strategy/report',
              identityReveal: '/c/community-strategy/reveal',
            },
          }],
          caughtUp: [],
          inactive: [],
          archived: [],
          available: [],
          moderating: [],
        },
      },
    });
    },
  ),
  http.get(
    new URL('/api/v1/conversations/community-strategy/workspace', globalThis.location.origin).toString(),
    () => HttpResponse.json({data: {
      slug: 'community-strategy',
      title: 'Community strategy',
      space: 'real',
      status: 'open',
      descriptionHtml: '<p>Shape the future together.</p>',
      outroHtml: '<p>A closing note for participants.</p>',
      viewer: {state: 'participant', pseudonym: 'quiet-otter'},
      spaceWarning: null,
      scheduledTransition: null,
      tabs: [
        {key: 'vote', label: 'Vote', dataHref: '/api/v1/conversations/community-strategy/explore'},
        {key: 'results', label: 'Intermediate results', dataHref: '/api/v1/conversations/community-strategy/intermediate-results'},
        {key: 'arguments', label: 'Arguments', dataHref: '/api/v1/conversations/community-strategy/arguments'},
        {key: 'informed-voting', label: 'Informed vote', dataHref: '/api/v1/conversations/community-strategy/informed-voting'},
      ],
      defaultTab: 'vote',
      reveal: null,
      statementContribution: {unlockAfter: 0, quota: 3, used: 0},
      capabilities: {participate: true, moderate: false},
      links: {
        self: '/api/v1/conversations/community-strategy/workspace',
        conversation: '/c/community-strategy',
        about: '/c/community-strategy/about',
        join: '/accept/community-strategy',
        explore: '/api/v1/conversations/community-strategy/explore',
        intermediateResults: '/api/v1/conversations/community-strategy/intermediate-results',
        arguments: '/api/v1/conversations/community-strategy/arguments',
        informedVoting: '/api/v1/conversations/community-strategy/informed-voting',
      },
    }}),
  ),
  http.get(
    new URL('/api/v1/conversations/community-strategy/about', globalThis.location.origin).toString(),
    () => HttpResponse.json({
      data: {
        conversationId: 7,
        slug: 'community-strategy',
        title: 'Community strategy',
        space: 'real',
        descriptionHtml: '<p>Shape the next chapter together.</p>',
        outroHtml: null,
        status: 'open',
        phases: [{key: 'submission', label: 'Explore'}],
        scheduledTransition: null,
        pseudonym: 'quiet-otter',
        statistics: {
          participants: 24,
          statementVotes: 312,
          statements: 42,
          arguments: 9,
          argumentContributors: 6,
        },
        personal: {
          statementsSuggested: 2,
          statementVotes: 18,
          statementVotesAvailable: true,
          argumentsAdded: 1,
          argumentsRated: 3,
        },
        outputs: [{
          key: 'report', label: 'Final report', status: 'final', ready: false,
          href: '/c/community-strategy/report',
        }],
        moderation: {eventCount: 1, href: '/c/community-strategy/moderation-log'},
        capabilities: {participate: true, moderate: false},
        links: {
          self: '/api/v1/conversations/community-strategy/about',
          conversation: '/c/community-strategy',
        },
      },
    }),
  ),
  http.get(
    new URL('/api/v1/conversations/community-strategy/intermediate-results', globalThis.location.origin).toString(),
    () => HttpResponse.json({data: {
      slug: 'community-strategy',
      title: 'Community strategy',
      state: 'ready',
      participantCount: 12,
      smallSample: true,
      consensus: [
        {choice: 'agree', statement: 'Shared maintenance matters.', percentage: 82},
        {choice: 'disagree', statement: 'Centralize every budget.', percentage: 64},
      ],
      groups: [{
        label: 'Group 1',
        positions: [{choice: 'agree', statement: 'Local autonomy matters.', percentage: 76}],
      }],
      links: {
        self: '/api/v1/conversations/community-strategy/intermediate-results',
        conversation: '/c/community-strategy',
        about: '/c/community-strategy/about',
      },
    }}),
  ),
  http.get(
    new URL('/api/v1/conversations/community-strategy/results', globalThis.location.origin).toString(),
    () => HttpResponse.json({
      data: {
        slug: 'community-strategy',
        title: 'Community strategy',
        publication: 'final',
        resultsAvailable: true,
        openedAt: '2026-05-01T12:00:00Z',
        closedAt: '2026-07-01T12:00:00Z',
        context: {
          phase: 'Publish',
          status: 'final',
          method: 'Informed-voting tallies frozen at publication.',
        },
        participation: {initialRound: 25, informedRound: 22, matchedRounds: null},
        dataAvailability: {detailedCounts: true, opinionGroups: true},
        moderation: {excludedStatements: 1, excludedParticipants: 0},
        statements: [{
          featuredStatementId: 31,
          statement: 'Regional communities should share infrastructure funding.',
          initial: {
            counts: {agree: 12, pass: 3, disagree: 5, voters: 20},
            percentages: {agree: 60, pass: 15, disagree: 25},
          },
          informed: {
            counts: {agree: 14, pass: 4, disagree: 2, voters: 20},
            percentages: {agree: 70, pass: 20, disagree: 10},
          },
          agreementShift: 10,
          viewerChoice: null,
        }],
        opinionGroups: [{
          label: 'Group 1',
          memberCount: 11,
          positions: [{
            choice: 'agree',
            statement: 'Shared maintenance matters.',
            percentage: 82,
          }],
        }],
        viewer: {participating: true, pseudonym: 'quiet-otter', revealState: 'open'},
        links: {
          self: '/api/v1/conversations/community-strategy/results',
          conversation: '/c/community-strategy',
          about: '/c/community-strategy/about',
          identityReveal: '/c/community-strategy/reveal',
        },
      },
    }),
  ),
  http.get(
    new URL('/api/v1/conversations/community-strategy/informed-voting', globalThis.location.origin).toString(),
    () => HttpResponse.json({
      data: {
        slug: 'community-strategy',
        title: 'Community strategy',
        pseudonym: 'quiet-otter',
        cards: [{
          featuredStatementId: 31,
          statement: 'Regional communities should share infrastructure funding.',
          canVote: true,
          voted: false,
          arguments: {
            for: [{id: 81, body: 'Shared funding reduces duplicated maintenance.', helpfulVotes: 7}],
            against: [{id: 82, body: 'Regional priorities may require independent budgets.', helpfulVotes: 4}],
          },
        }],
        progress: {completed: 0, total: 1, remaining: 1, allDone: false},
        capabilities: {vote: true},
        links: {
          self: '/api/v1/conversations/community-strategy/informed-voting',
          about: '/c/community-strategy/about',
          conversation: '/c/community-strategy',
          explore: '/c/community-strategy',
          arguments: '/c/community-strategy#tab-arguments',
        },
      },
    }),
  ),
  http.put(
    new URL('/api/v1/conversations/community-strategy/featured-statements/31/informed-vote', globalThis.location.origin).toString(),
    async ({request}) => {
      const body = await request.json() as {choice: 'agree' | 'pass' | 'disagree'};
      return HttpResponse.json({
        data: {
          featuredStatementId: 31,
          choice: body.choice,
          links: {informedVoting: '/api/v1/conversations/community-strategy/informed-voting'},
        },
      });
    },
  ),
  http.get(
    new URL('/api/v1/conversations/community-strategy/identity-reveal', globalThis.location.origin).toString(),
    () => HttpResponse.json({
      data: {
        slug: 'community-strategy',
        title: 'Community strategy',
        state: 'open',
        pseudonym: 'quiet-otter',
        wikimediaUsername: 'Example editor',
        publicUsername: null,
        timeline: {
          closedAt: '2026-06-01T12:00:00Z',
          opensAt: '2026-07-01T12:00:00Z',
          closesAt: '2026-07-31T12:00:00Z',
          nextBoundaryAt: '2026-07-31T12:00:00Z',
          daysRemaining: 12,
        },
        capabilities: {revealIdentity: true},
        links: {
          self: '/api/v1/conversations/community-strategy/identity-reveal',
          conversation: '/c/community-strategy',
          about: '/c/community-strategy/about',
        },
      },
    }),
  ),
  http.post(
    new URL('/api/v1/conversations/community-strategy/identity-reveal', globalThis.location.origin).toString(),
    () => HttpResponse.json({
      data: {
        slug: 'community-strategy',
        title: 'Community strategy',
        state: 'revealed',
        pseudonym: 'quiet-otter',
        wikimediaUsername: 'Example editor',
        publicUsername: 'Example editor',
        timeline: {
          closedAt: '2026-06-01T12:00:00Z',
          opensAt: '2026-07-01T12:00:00Z',
          closesAt: '2026-07-31T12:00:00Z',
          nextBoundaryAt: null,
          daysRemaining: 0,
        },
        capabilities: {revealIdentity: false},
        links: {
          self: '/api/v1/conversations/community-strategy/identity-reveal',
          conversation: '/c/community-strategy',
          about: '/c/community-strategy/about',
        },
      },
    }, {status: 201}),
  ),
  http.get(
    new URL('/api/v1/conversations/community-strategy/participation-entry', globalThis.location.origin).toString(),
    () => HttpResponse.json({
      data: {
        state: 'join',
        conversation: {
          id: 7,
          slug: 'community-strategy',
          title: 'Community strategy',
          descriptionHtml: '<p>Shape the next chapter together.</p>',
          eligibilityLabel: null,
        },
        pseudonyms: ['quiet-otter', 'bright-fox', 'steady-heron'],
        emailable: true,
        reveal: {cooldownDays: 30, windowEndDays: 60},
        links: {home: '/', conversation: '/c/community-strategy'},
      },
    }),
  ),
  http.get(
    new URL('/api/v1/conversations/community-strategy/pseudonym-suggestions', globalThis.location.origin).toString(),
    () => HttpResponse.json({
      data: {pseudonyms: ['quiet-otter', 'bright-fox', 'steady-heron']},
    }),
  ),
  http.post(
    new URL('/api/v1/conversations/community-strategy/participation', globalThis.location.origin).toString(),
    () => HttpResponse.json({
      data: {
        pseudonym: 'quiet-otter',
        notifications: {email: false, talkPage: false},
        eligibilityStatus: 'not_required',
        links: {
          conversation: '/c/community-strategy',
          about: '/c/community-strategy/about',
        },
      },
    }, {status: 201}),
  ),
  http.get(
    new URL('/api/v1/conversations/community-strategy/explore', globalThis.location.origin).toString(),
    () => HttpResponse.json({
      data: {
        slug: 'community-strategy',
        title: 'Community strategy',
        pseudonym: 'quiet-otter',
        currentStatement: {
          id: 12,
          text: 'Our movement should invest more in shared technical infrastructure.',
          isMeta: false,
          isSeed: true,
        },
        progress: {completed: 3, total: 12, remaining: 9, allDone: false},
        newStatement: {unlocked: true, unlockAfter: 0, quota: 3, used: 0, remaining: 3},
        capabilities: {vote: true, suggestWording: true, submitNewStatement: true},
        links: {
          self: '/api/v1/conversations/community-strategy/explore',
          about: '/c/community-strategy/about',
          conversation: '/c/community-strategy',
          arguments: '/c/community-strategy#tab-arguments',
        },
      },
    }),
  ),
  http.put(
    new URL('/api/v1/conversations/community-strategy/statements/12/vote', globalThis.location.origin).toString(),
    async ({request}) => {
      const body = await request.json() as {
        choice: 'agree' | 'pass' | 'disagree';
        passReason?: 'unsure' | 'confusing';
      };
      return HttpResponse.json({
        data: {
          statementId: 12,
          choice: body.choice,
          passReason: body.passReason ?? null,
          links: {explore: '/api/v1/conversations/community-strategy/explore'},
        },
      });
    },
  ),
  http.post(
    new URL('/api/v1/conversations/community-strategy/statements', globalThis.location.origin).toString(),
    async ({request}) => {
      const body = await request.json() as {
        text: string;
        derivedFromStatementId?: number;
      };
      return HttpResponse.json({
        data: {
          statementId: 44,
          kind: body.derivedFromStatementId === undefined ? 'new' : 'derivative',
          derivedFromStatementId: body.derivedFromStatementId ?? null,
          newStatementQuotaRemaining: 2,
          links: {explore: '/api/v1/conversations/community-strategy/explore'},
        },
      }, {status: 201});
    },
  ),
  http.get(
    new URL('/api/v1/conversations/community-strategy/arguments', globalThis.location.origin).toString(),
    () => HttpResponse.json({
      data: {
        conversationId: 7,
        slug: 'community-strategy',
        title: 'Community strategy',
        pseudonym: 'quiet-otter',
        progress: {completed: 0, total: 1, allDone: false, currentFeaturedStatementId: 8},
        featuredStatements: [{
          id: 8,
          statement: {id: 12, text: 'Our movement should invest more in shared technical infrastructure.'},
          contributionsComplete: false,
          complete: false,
          sides: {
            pro: {
              contribution: {status: 'pending', argumentId: null, capabilities: {submit: true, skip: true}},
              prioritization: {available: false, requiredArgumentCount: 3, argumentCount: 3, selectionBudget: 2, selectedCount: 0, complete: false},
              arguments: [],
            },
            con: {
              contribution: {status: 'skipped', argumentId: null, capabilities: {submit: true, skip: false}},
              prioritization: {available: false, requiredArgumentCount: 3, argumentCount: 2, selectionBudget: 2, selectedCount: 0, complete: true},
              arguments: [],
            },
          },
          capabilities: {flagStatement: true},
        }],
        capabilities: {contribute: true, prioritize: true, flag: true, moderate: false},
        links: {
          self: '/api/v1/conversations/community-strategy/arguments',
          about: '/c/community-strategy/about',
          conversation: '/c/community-strategy',
          explore: '/c/community-strategy',
        },
      },
    }),
  ),
  http.post(
    new URL('/api/v1/conversations/community-strategy/featured-statements/8/arguments', globalThis.location.origin).toString(),
    async ({request}) => {
      const body = await request.json() as {side: 'pro' | 'con'; body: string};
      return HttpResponse.json({
        data: {
          featuredStatementId: 8,
          side: body.side,
          status: 'submitted',
          argument: {id: 91, body: body.body, own: true, selected: false, hidden: false, importanceVoteCount: 0, capabilities: {prioritize: false, flag: false, moderate: false}},
          links: {arguments: '/api/v1/conversations/community-strategy/arguments'},
        },
      }, {status: 201});
    },
  ),
  http.put(
    new URL('/api/v1/conversations/community-strategy/featured-statements/8/contributions/:side/skip', globalThis.location.origin).toString(),
    ({params}) => HttpResponse.json({
      data: {
        featuredStatementId: 8,
        side: params.side,
        status: 'skipped',
        links: {arguments: '/api/v1/conversations/community-strategy/arguments'},
      },
    }),
  ),
  http.put(
    new URL('/api/v1/conversations/community-strategy/arguments/:argumentId/priority', globalThis.location.origin).toString(),
    async ({params, request}) => {
      const body = await request.json() as {selected: boolean};
      return HttpResponse.json({
        data: {
          argumentId: Number(params.argumentId), selected: body.selected,
          selectedCount: body.selected ? 2 : 1, selectionBudget: 2,
          links: {arguments: '/api/v1/conversations/community-strategy/arguments'},
        },
      });
    },
  ),
  http.post(
    new URL('/api/v1/conversations/community-strategy/flags', globalThis.location.origin).toString(),
    async ({request}) => {
      const body = await request.json() as {
        contentType: 'statement' | 'argument';
        targetId: number;
        category: 'personal_attack' | 'privacy' | 'off_topic' | 'other';
      };
      return HttpResponse.json({
        data: {
          ...body,
          status: 'open',
          created: true,
          links: {conversation: '/c/community-strategy'},
        },
      }, {status: 201});
    },
  ),
];

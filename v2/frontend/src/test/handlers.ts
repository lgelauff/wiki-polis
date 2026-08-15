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

function adminCatalogFixture(
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
  http.put(new URL('/api/v1/admin/conversations/7/phase', globalThis.location.origin).toString(), () => HttpResponse.json({data: {
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
  }})),
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
  http.get(
    new URL('/api/v1/session', globalThis.location.origin).toString(),
    () => HttpResponse.json({
      data: {
        state: 'authenticated',
        user: {username: 'Example editor', emailable: true},
        capabilities: {administerSite: false},
        csrfToken: 'test-csrf-token',
        developerMode: true,
        developerLogins: [],
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

import {queryOptions} from '@tanstack/react-query';

import type {components} from './schema';
import {api, requireApiData} from './client';

export type ConversationSpace = 'real' | 'demo';

export const sessionQuery = () => queryOptions({
  queryKey: ['session'],
  queryFn: async () => (await requireApiData(api.GET('/session'))).data,
  staleTime: 30_000,
});

export const conversationLaneQuery = (space: ConversationSpace) => queryOptions({
  queryKey: ['conversation-lane', space],
  queryFn: async () => (
    await requireApiData(api.GET('/conversations', {
      params: {query: {space}},
    }))
  ).data,
  staleTime: 15_000,
});

export const conversationAboutQuery = (slug: string) => queryOptions({
  queryKey: ['conversation-about', slug],
  queryFn: async () => (
    await requireApiData(api.GET('/conversations/{slug}/about', {
      params: {path: {slug}},
    }))
  ).data,
  staleTime: 15_000,
});

export const identityRevealQuery = (slug: string) => queryOptions({
  queryKey: ['identity-reveal', slug],
  queryFn: async () => (
    await requireApiData(api.GET('/conversations/{slug}/identity-reveal', {
      params: {path: {slug}},
    }))
  ).data,
  staleTime: 0,
});

export async function createIdentityReveal(slug: string, csrfToken: string) {
  return (
    await requireApiData(api.POST('/conversations/{slug}/identity-reveal', {
      params: {path: {slug}},
      body: {confirm: true},
      headers: {'X-CSRFToken': csrfToken},
    }))
  ).data;
}

export const informedVotingQuery = (slug: string) => queryOptions({
  queryKey: ['informed-voting', slug],
  queryFn: async () => (
    await requireApiData(api.GET('/conversations/{slug}/informed-voting', {
      params: {path: {slug}},
    }))
  ).data,
  staleTime: 0,
});

export async function putInformedVote(
  slug: string,
  featuredStatementId: number,
  body: components['schemas']['InformedVoteRequest'],
  csrfToken: string,
) {
  return (
    await requireApiData(api.PUT(
      '/conversations/{slug}/featured-statements/{featuredStatementId}/informed-vote',
      {
        params: {path: {slug, featuredStatementId}},
        body,
        headers: {'X-CSRFToken': csrfToken},
      },
    ))
  ).data;
}

export const resultsReportQuery = (slug: string) => queryOptions({
  queryKey: ['results-report', slug],
  queryFn: async () => (
    await requireApiData(api.GET('/conversations/{slug}/results', {
      params: {path: {slug}},
    }))
  ).data,
  staleTime: 30_000,
});

export const adminParticipantRosterQuery = (conversationId: number) => queryOptions({
  queryKey: ['admin-participant-roster', conversationId],
  queryFn: async () => (
    await requireApiData(api.GET('/admin/conversations/{conversationId}/participants', {
      params: {path: {conversationId}},
    }))
  ).data,
  staleTime: 10_000,
});

export async function putAdminParticipantAccess(
  conversationId: number,
  participantId: number,
  body: components['schemas']['AdminParticipantAccessRequest'],
  csrfToken: string,
) {
  return (
    await requireApiData(api.PUT(
      '/admin/conversations/{conversationId}/participants/{participantId}/access',
      {
        params: {path: {conversationId, participantId}},
        body,
        headers: {'X-CSRFToken': csrfToken},
      },
    ))
  ).data;
}

export const adminFlagQueueQuery = (conversationId: number) => queryOptions({
  queryKey: ['admin-flag-queue', conversationId],
  queryFn: async () => (
    await requireApiData(api.GET('/admin/conversations/{conversationId}/flags', {
      params: {path: {conversationId}},
    }))
  ).data,
  staleTime: 5_000,
});

export async function putAdminFlagResolution(
  conversationId: number,
  flagId: number,
  body: components['schemas']['AdminFlagResolutionRequest'],
  csrfToken: string,
) {
  return (
    await requireApiData(api.PUT(
      '/admin/conversations/{conversationId}/flags/{flagId}/resolution',
      {
        params: {path: {conversationId, flagId}},
        body,
        headers: {'X-CSRFToken': csrfToken},
      },
    ))
  ).data;
}

export const adminInvitationRosterQuery = (conversationId: number) => queryOptions({
  queryKey: ['admin-invitation-roster', conversationId],
  queryFn: async () => (
    await requireApiData(api.GET('/admin/conversations/{conversationId}/invitations', {
      params: {path: {conversationId}},
    }))
  ).data,
  staleTime: 10_000,
});

export async function putAdminInvitations(
  conversationId: number,
  body: components['schemas']['AdminInvitationBatchRequest'],
  csrfToken: string,
) {
  return (
    await requireApiData(api.PUT('/admin/conversations/{conversationId}/invitations', {
      params: {path: {conversationId}}, body, headers: {'X-CSRFToken': csrfToken},
    }))
  ).data;
}

export async function deleteAdminInvitation(
  conversationId: number,
  inviteId: number,
  csrfToken: string,
) {
  return (
    await requireApiData(api.DELETE(
      '/admin/conversations/{conversationId}/invitations/{inviteId}',
      {
        params: {path: {conversationId, inviteId}},
        headers: {'X-CSRFToken': csrfToken},
      },
    ))
  ).data;
}

export const adminRoleRosterQuery = (conversationId: number) => queryOptions({
  queryKey: ['admin-role-roster', conversationId],
  queryFn: async () => (await requireApiData(api.GET('/admin/conversations/{conversationId}/roles', {params: {path: {conversationId}}}))).data,
  staleTime: 10_000,
});

export async function putAdminRoles(
  conversationId: number, participantId: number,
  body: components['schemas']['AdminRoleSetRequest'], csrfToken: string,
) {
  return (await requireApiData(api.PUT('/admin/conversations/{conversationId}/roles/{participantId}', {
    params: {path: {conversationId, participantId}}, body,
    headers: {'X-CSRFToken': csrfToken},
  }))).data;
}

export const adminLifecycleQuery = (conversationId: number) => queryOptions({
  queryKey: ['admin-lifecycle', conversationId],
  queryFn: async () => (
    await requireApiData(api.GET('/admin/conversations/{conversationId}', {
      params: {path: {conversationId}},
    }))
  ).data,
  staleTime: 5_000,
});

export async function putAdminPhase(
  conversationId: number,
  body: components['schemas']['AdminPhaseAdvanceRequest'],
  csrfToken: string,
) {
  return (await requireApiData(api.PUT('/admin/conversations/{conversationId}/phase', {
    params: {path: {conversationId}}, body,
    headers: {'X-CSRFToken': csrfToken},
  }))).data;
}

export async function putAdminPhases(
  conversationId: number,
  body: components['schemas']['AdminAdvancedPhasesRequest'],
  csrfToken: string,
) {
  return (await requireApiData(api.PUT('/admin/conversations/{conversationId}/phases', {
    params: {path: {conversationId}}, body,
    headers: {'X-CSRFToken': csrfToken},
  }))).data;
}

export async function putAdminPause(
  conversationId: number,
  body: components['schemas']['AdminPauseRequest'],
  csrfToken: string,
) {
  return (await requireApiData(api.PUT('/admin/conversations/{conversationId}/pause', {
    params: {path: {conversationId}}, body,
    headers: {'X-CSRFToken': csrfToken},
  }))).data;
}

export async function putAdminSchedule(
  conversationId: number,
  body: components['schemas']['AdminScheduleRequest'],
  csrfToken: string,
) {
  return (await requireApiData(api.PUT('/admin/conversations/{conversationId}/schedule', {
    params: {path: {conversationId}}, body,
    headers: {'X-CSRFToken': csrfToken},
  }))).data;
}

export async function createAdminPublication(
  conversationId: number,
  body: components['schemas']['AdminPublicationRequest'],
  csrfToken: string,
) {
  return (await requireApiData(api.POST('/admin/conversations/{conversationId}/publication', {
    params: {path: {conversationId}}, body,
    headers: {'X-CSRFToken': csrfToken},
  }))).data;
}

export const adminSettingsQuery = (conversationId: number) => queryOptions({
  queryKey: ['admin-settings', conversationId],
  queryFn: async () => (await requireApiData(api.GET(
    '/admin/conversations/{conversationId}/settings',
    {params: {path: {conversationId}}},
  ))).data,
  staleTime: 10_000,
});

export async function putAdminSettings(
  conversationId: number,
  body: components['schemas']['AdminSettingsRequest'],
  csrfToken: string,
) {
  return (await requireApiData(api.PUT(
    '/admin/conversations/{conversationId}/settings',
    {params: {path: {conversationId}}, body, headers: {'X-CSRFToken': csrfToken}},
  ))).data;
}

export const pseudonymSuggestionsQuery = (slug: string) => queryOptions({
  queryKey: ['pseudonym-suggestions', slug],
  queryFn: async () => (
    await requireApiData(api.GET('/conversations/{slug}/pseudonym-suggestions', {
      params: {path: {slug}},
    }))
  ).data,
  staleTime: 0,
});

export async function createParticipation(
  slug: string,
  body: components['schemas']['CreateParticipationRequest'],
  csrfToken: string,
) {
  return (
    await requireApiData(api.POST('/conversations/{slug}/participation', {
      params: {path: {slug}},
      body,
      headers: {'X-CSRFToken': csrfToken},
    }))
  ).data;
}

export const exploreStateQuery = (slug: string) => queryOptions({
  queryKey: ['explore-state', slug],
  queryFn: async () => (
    await requireApiData(api.GET('/conversations/{slug}/explore', {
      params: {path: {slug}},
    }))
  ).data,
  staleTime: 0,
});

export async function putExploreVote(
  slug: string,
  statementId: number,
  body: components['schemas']['ExploreVoteRequest'],
  csrfToken: string,
) {
  return (
    await requireApiData(api.PUT('/conversations/{slug}/statements/{statementId}/vote', {
      params: {path: {slug, statementId}},
      body,
      headers: {'X-CSRFToken': csrfToken},
    }))
  ).data;
}

export async function createStatement(
  slug: string,
  body: components['schemas']['CreateStatementRequest'],
  csrfToken: string,
  idempotencyKey: string,
) {
  return (
    await requireApiData(api.POST('/conversations/{slug}/statements', {
      params: {
        path: {slug},
        header: {'Idempotency-Key': idempotencyKey},
      },
      body,
      headers: {'X-CSRFToken': csrfToken},
    }))
  ).data;
}

export const argumentMappingQuery = (slug: string) => queryOptions({
  queryKey: ['argument-mapping', slug],
  queryFn: async () => (
    await requireApiData(api.GET('/conversations/{slug}/arguments', {
      params: {path: {slug}},
    }))
  ).data,
  staleTime: 0,
});

export async function createArgument(
  slug: string,
  featuredStatementId: number,
  body: components['schemas']['CreateArgumentRequest'],
  csrfToken: string,
) {
  return (
    await requireApiData(api.POST(
      '/conversations/{slug}/featured-statements/{featuredStatementId}/arguments',
      {
        params: {path: {slug, featuredStatementId}},
        body,
        headers: {'X-CSRFToken': csrfToken},
      },
    ))
  ).data;
}

export async function skipArgumentContribution(
  slug: string,
  featuredStatementId: number,
  side: 'pro' | 'con',
  csrfToken: string,
) {
  return (
    await requireApiData(api.PUT(
      '/conversations/{slug}/featured-statements/{featuredStatementId}/contributions/{side}/skip',
      {
        params: {path: {slug, featuredStatementId, side}},
        headers: {'X-CSRFToken': csrfToken},
      },
    ))
  ).data;
}

export async function putArgumentPriority(
  slug: string,
  argumentId: number,
  selected: boolean,
  csrfToken: string,
) {
  return (
    await requireApiData(api.PUT(
      '/conversations/{slug}/arguments/{argumentId}/priority',
      {
        params: {path: {slug, argumentId}},
        body: {selected},
        headers: {'X-CSRFToken': csrfToken},
      },
    ))
  ).data;
}

export async function createContentFlag(
  slug: string,
  body: components['schemas']['CreateContentFlagRequest'],
  csrfToken: string,
) {
  return (
    await requireApiData(api.POST('/conversations/{slug}/flags', {
      params: {path: {slug}},
      body,
      headers: {'X-CSRFToken': csrfToken},
    }))
  ).data;
}

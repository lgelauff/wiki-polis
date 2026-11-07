import {queryOptions} from '@tanstack/react-query';

import type {components} from '../schema';
import {ApiContractError, api, requireApiData} from '../client';

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

/** Admin home (#538): the consultations the viewer holds a role in. Always refetched on
 *  arrival (`staleTime: 0`): a role, status, delete or moderation elsewhere in the console
 *  changes what it shows, and nothing invalidates it from there. */
export const adminHomeQuery = () => queryOptions({
  queryKey: ['admin-home'],
  queryFn: async () => (await requireApiData(api.GET('/admin/home'))).data,
  staleTime: 0,
});

export const adminCatalogQuery = () => queryOptions({
  queryKey: ['admin-catalog'],
  queryFn: async () => (await requireApiData(api.GET('/admin'))).data,
  staleTime: 5_000,
});

export async function postAdminConversation(
  body: components['schemas']['AdminConversationCreateRequest'],
  csrfToken: string,
) {
  return (await requireApiData(api.POST('/admin/conversations', {
    body, headers: {'X-CSRFToken': csrfToken},
  }))).data;
}

export async function postGlobalAdminGrant(
  body: components['schemas']['GlobalAdminGrantRequest'], csrfToken: string,
) {
  return (await requireApiData(api.POST('/admin/global-admin-grants', {
    body, headers: {'X-CSRFToken': csrfToken},
  }))).data;
}

export async function putGlobalAdmin(
  participantId: number,
  body: components['schemas']['GlobalAdminSetRequest'],
  csrfToken: string,
) {
  return (await requireApiData(api.PUT('/admin/global-admins/{participantId}', {
    params: {path: {participantId}}, body,
    headers: {'X-CSRFToken': csrfToken},
  }))).data;
}

export const reminderTestQuery = () => queryOptions({
  queryKey: ['admin-reminder-test'],
  queryFn: async () => (await requireApiData(api.GET('/admin/reminder-test'))).data,
  staleTime: 30_000,
});

export async function postReminderTestSend(
  body: components['schemas']['ReminderTestSendRequest'], csrfToken: string,
) {
  return (await requireApiData(api.POST('/admin/reminder-test-sends', {
    body, headers: {'X-CSRFToken': csrfToken},
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

export async function createAdminPhase6Initialization(
  conversationId: number, csrfToken: string,
) {
  return (await requireApiData(api.POST(
    '/admin/conversations/{conversationId}/phase6-initialization',
    {
      params: {path: {conversationId}},
      headers: {'X-CSRFToken': csrfToken},
    },
  ))).data;
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

export async function putAdminArchive(
  conversationId: number,
  body: components['schemas']['AdminArchiveRequest'],
  csrfToken: string,
) {
  return (await requireApiData(api.PUT('/admin/conversations/{conversationId}/archive', {
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

export async function putAdminRecommendationTier(
  conversationId: number,
  body: components['schemas']['AdminRecommendationTierRequest'],
  csrfToken: string,
) {
  return (await requireApiData(api.PUT(
    '/admin/conversations/{conversationId}/recommendation-tier',
    {params: {path: {conversationId}}, body, headers: {'X-CSRFToken': csrfToken}},
  ))).data;
}

/** A site admin's preview of the results report, or, once the report is published, the
 *  published report's path to go to instead. */
export type AdminReportPreview =
  | {state: 'preview'; report: components['schemas']['ResultsReport']}
  | {state: 'published'; reportPath: string};

/** Every open of the page fetches once: nothing is kept after it closes (`gcTime: 0`), so
 *  the numbers are live and each open writes one audit event. Focus and reconnect do not
 *  refetch, so leaving the tab and coming back adds no rows. Read it with `useQuery`, not
 *  `useSuspenseQuery`: suspense raises gcTime to at least a second, so a quick reopen
 *  would be served from the cache. */
export const adminReportPreviewQuery = (conversationId: number) => queryOptions({
  queryKey: ['admin-report-preview', conversationId],
  queryFn: async (): Promise<AdminReportPreview> => {
    try {
      const {data} = await requireApiData(api.GET(
        '/admin/conversations/{conversationId}/report-preview',
        {params: {path: {conversationId}}},
      ));
      return {state: 'preview', report: data};
    } catch (error) {
      const report = error instanceof ApiContractError && error.code === 'conversation_closed'
        ? (error.details as {report?: unknown} | undefined)?.report : undefined;
      if (typeof report === 'string') return {state: 'published', reportPath: report};
      throw error;
    }
  },
  gcTime: 0,
  refetchOnWindowFocus: false,
  refetchOnReconnect: false,
});

export const adminTerminationQuery = (conversationId: number) => queryOptions({
  queryKey: ['admin-termination', conversationId],
  queryFn: async () => (await requireApiData(api.GET(
    '/admin/conversations/{conversationId}/termination',
    {params: {path: {conversationId}}},
  ))).data,
  staleTime: 0,
});

export async function deleteAdminConversation(
  conversationId: number,
  csrfToken: string,
) {
  return (await requireApiData(api.DELETE(
    '/admin/conversations/{conversationId}',
    {
      params: {path: {conversationId}},
      headers: {'X-CSRFToken': csrfToken},
    },
  ))).data;
}

export const adminStatementWorkspaceQuery = (conversationId: number) => queryOptions({
  queryKey: ['admin-statement-workspace', conversationId],
  queryFn: async () => (await requireApiData(api.GET(
    '/admin/conversations/{conversationId}/statements',
    {params: {path: {conversationId}}},
  ))).data,
  staleTime: 5_000,
});

export async function putAdminStatementModerationPolicy(
  conversationId: number,
  body: components['schemas']['AdminStatementModerationPolicyRequest'],
  csrfToken: string,
) {
  return (await requireApiData(api.PUT(
    '/admin/conversations/{conversationId}/statement-moderation-policy',
    {
      params: {path: {conversationId}}, body,
      headers: {'X-CSRFToken': csrfToken},
    },
  ))).data;
}

export async function putAdminStatementModeration(
  conversationId: number,
  statementId: number,
  body: components['schemas']['AdminStatementModerationRequest'],
  csrfToken: string,
) {
  return (await requireApiData(api.PUT(
    '/admin/conversations/{conversationId}/statements/{statementId}/moderation',
    {
      params: {path: {conversationId, statementId}},
      body,
      headers: {'X-CSRFToken': csrfToken},
    },
  ))).data;
}

export async function postAdminStatementImport(
  conversationId: number,
  body: components['schemas']['AdminStatementImportRequest'],
  csrfToken: string,
) {
  return (await requireApiData(api.POST(
    '/admin/conversations/{conversationId}/statement-imports',
    {
      params: {path: {conversationId}},
      body,
      headers: {'X-CSRFToken': csrfToken},
    },
  ))).data;
}

export async function postAdminSeedStatement(
  conversationId: number,
  body: components['schemas']['AdminSeedStatementRequest'],
  csrfToken: string,
) {
  return (await requireApiData(api.POST(
    '/admin/conversations/{conversationId}/statements',
    {
      params: {path: {conversationId}},
      body,
      headers: {'X-CSRFToken': csrfToken},
    },
  ))).data;
}

export const adminFeaturedWorkspaceQuery = (conversationId: number) => queryOptions({
  queryKey: ['admin-featured-workspace', conversationId],
  queryFn: async () => (await requireApiData(api.GET(
    '/admin/conversations/{conversationId}/featured-statements',
    {params: {path: {conversationId}}},
  ))).data,
  staleTime: 5_000,
});

export async function putAdminFeaturedStatement(
  conversationId: number,
  statementId: number,
  body: components['schemas']['AdminFeaturedSelectionRequest'],
  csrfToken: string,
) {
  return (await requireApiData(api.PUT(
    '/admin/conversations/{conversationId}/featured-statements/{statementId}',
    {
      params: {path: {conversationId, statementId}}, body,
      headers: {'X-CSRFToken': csrfToken},
    },
  ))).data;
}

export async function deleteAdminFeaturedSelection(
  conversationId: number, featuredId: number, csrfToken: string,
) {
  return (await requireApiData(api.DELETE(
    '/admin/conversations/{conversationId}/featured-selections/{featuredId}',
    {
      params: {path: {conversationId, featuredId}},
      headers: {'X-CSRFToken': csrfToken},
    },
  ))).data;
}

export async function putAdminFeaturedArgument(
  conversationId: number,
  argumentId: number,
  body: components['schemas']['AdminFeaturedArgumentRequest'],
  csrfToken: string,
) {
  return (await requireApiData(api.PUT(
    '/admin/conversations/{conversationId}/featured-arguments/{argumentId}',
    {
      params: {path: {conversationId, argumentId}}, body,
      headers: {'X-CSRFToken': csrfToken},
    },
  ))).data;
}

export async function deleteAdminFeaturedArgument(
  conversationId: number, argumentId: number, csrfToken: string,
) {
  return (await requireApiData(api.DELETE(
    '/admin/conversations/{conversationId}/featured-arguments/{argumentId}',
    {
      params: {path: {conversationId, argumentId}},
      headers: {'X-CSRFToken': csrfToken},
    },
  ))).data;
}

/** canivote's eligibility policies an organizer may choose from (#530). The server caches
 *  canivote's answer for ten minutes, so a list that loaded is kept as long; "cannot be
 *  loaded" is not kept, so the next page that needs the list asks again. */
export const adminEligibilityPoliciesQuery = () => queryOptions({
  queryKey: ['admin-eligibility-policies'],
  queryFn: async () => (await requireApiData(api.GET('/admin/eligibility-policies'))).data,
  staleTime: (query) => (query.state.data?.available ? 600_000 : 0),
});

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

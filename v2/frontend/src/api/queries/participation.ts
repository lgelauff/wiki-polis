import {queryOptions} from '@tanstack/react-query';

import type {components} from '../schema';
import {api, requireApiData} from '../client';

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

export const participationEntryQuery = (slug: string) => queryOptions({
  queryKey: ['participation-entry', slug],
  queryFn: async () => (
    await requireApiData(api.GET('/conversations/{slug}/participation-entry', {
      params: {path: {slug}},
    }))
  ).data,
  staleTime: 0,
});

export async function getPseudonymSuggestions(slug: string) {
  return (
    await requireApiData(api.GET('/conversations/{slug}/pseudonym-suggestions', {
      params: {path: {slug}},
    }))
  ).data;
}

export const pseudonymSuggestionsQuery = (slug: string) => queryOptions({
  queryKey: ['pseudonym-suggestions', slug],
  queryFn: () => getPseudonymSuggestions(slug),
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

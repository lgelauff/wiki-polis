import {queryOptions} from '@tanstack/react-query';

import type {components} from '../schema';
import {api, requireApiData} from '../client';

export const informedVotingQuery = (slug: string) => queryOptions({
  queryKey: ['informed-voting', slug],
  queryFn: async () => (
    await requireApiData(api.GET('/conversations/{slug}/informed-voting', {
      params: {path: {slug}},
    }))
  ).data,
  staleTime: 0,
});

export const intermediateResultsQuery = (slug: string) => queryOptions({
  queryKey: ['intermediate-results', slug],
  queryFn: async () => (
    await requireApiData(api.GET('/conversations/{slug}/intermediate-results', {
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

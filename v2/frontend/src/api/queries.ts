import {queryOptions} from '@tanstack/react-query';

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

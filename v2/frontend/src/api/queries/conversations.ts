import {queryOptions} from '@tanstack/react-query';

import type {components} from '../schema';
import {api, requireApiData} from '../client';

export type ConversationSpace = 'real' | 'demo';

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

export const conversationWorkspaceQuery = (slug: string) => queryOptions({
  queryKey: ['conversation-workspace', slug],
  queryFn: async () => (
    await requireApiData(api.GET('/conversations/{slug}/workspace', {
      params: {path: {slug}},
    }))
  ).data,
  staleTime: 0,
});

export const moderationLogQuery = (slug: string) => queryOptions({
  queryKey: ['moderation-log', slug],
  queryFn: async () => (
    await requireApiData(api.GET('/conversations/{slug}/moderation-log', {
      params: {path: {slug}},
    }))
  ).data,
  staleTime: 15_000,
});

export const conversationOutputQuery = (
  slug: string,
  outputKey: components['schemas']['ConversationOutputDetail']['key'],
) => queryOptions({
  queryKey: ['conversation-output', slug, outputKey],
  queryFn: async () => (
    await requireApiData(api.GET('/conversations/{slug}/outputs/{outputKey}', {
      params: {path: {slug, outputKey}},
    }))
  ).data,
  staleTime: 15_000,
});

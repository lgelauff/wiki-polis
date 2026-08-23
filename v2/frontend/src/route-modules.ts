export const loadAdminRoutes = () => import('./features/admin/admin-routes');
export const loadConversationReadPages = () => import('./features/legacy/conversation-read-pages');
export const loadGuidancePages = () => import('./features/legacy/guidance-pages');
export const loadIdentityRevealPage = () => import('./features/legacy/identity-reveal-page');
export const loadParticipationEntryPage = () => import('./features/legacy/participation-entry-page');
export const loadResultsPage = () => import('./features/results/results-page');

export type RouteChunk =
  | 'admin'
  | 'conversation-read'
  | 'guidance'
  | 'identity-reveal'
  | 'participation-entry'
  | 'results';

const chunkLoaders: Record<RouteChunk, () => Promise<unknown>> = {
  admin: loadAdminRoutes,
  'conversation-read': loadConversationReadPages,
  guidance: loadGuidancePages,
  'identity-reveal': loadIdentityRevealPage,
  'participation-entry': loadParticipationEntryPage,
  results: loadResultsPage,
};

export function routeChunkForPath(clientPath: string): RouteChunk | null {
  const pathname = clientPath.split(/[?#]/, 1)[0] ?? '';
  if (pathname === '/admin' || pathname.startsWith('/admin/')) return 'admin';
  if (pathname === '/help/statements' || pathname === '/help/arguments') return 'guidance';
  if (/^\/accept\/[^/]+$/.test(pathname)) return 'participation-entry';
  if (/^\/c\/[^/]+\/report$/.test(pathname)) return 'results';
  if (/^\/c\/[^/]+\/reveal$/.test(pathname)) return 'identity-reveal';
  if (/^\/c\/[^/]+\/(?:about|moderation-log|outputs\/[^/]+)$/.test(pathname)) {
    return 'conversation-read';
  }
  return null;
}

export function prefetchClientRoute(clientPath: string): void {
  const chunk = routeChunkForPath(clientPath);
  if (chunk) void chunkLoaders[chunk]().catch(() => undefined);
}

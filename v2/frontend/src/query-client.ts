import {MutationCache, QueryCache, QueryClient} from '@tanstack/react-query';

/** The server logs a single-consultation (voucher) account out where it finds that the
 *  account's code was withdrawn (#514). Any request that reports it makes the shell ask
 *  for the session again, which then carries the one-time logout note. */
function endsTheSession(error: unknown): boolean {
  if (!(error instanceof Error) || !('code' in error) || error.code !== 'access_required') return false;
  const details = (error as {details?: unknown}).details as {reason?: unknown} | undefined;
  return details?.reason === 'access-voucher-revoked';
}

export function createQueryClient(): QueryClient {
  const onError = (error: unknown) => {
    if (endsTheSession(error)) void client.invalidateQueries({queryKey: ['session']});
  };
  const client: QueryClient = new QueryClient({
    queryCache: new QueryCache({onError}),
    mutationCache: new MutationCache({onError}),
    defaultOptions: {
      queries: {
        retry: (failureCount, error) => {
          if ('code' in error && typeof error.code === 'string') {
            return !['unauthorized', 'forbidden', 'invite_only', 'access_required', 'not_found'].includes(error.code)
              && failureCount < 2;
          }
          return failureCount < 2;
        },
        refetchOnWindowFocus: false,
      },
    },
  });
  return client;
}

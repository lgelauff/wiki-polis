import {QueryClient} from '@tanstack/react-query';

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: (failureCount, error) => {
          if ('code' in error && typeof error.code === 'string') {
            return !['unauthorized', 'forbidden', 'not_found'].includes(error.code)
              && failureCount < 2;
          }
          return failureCount < 2;
        },
        refetchOnWindowFocus: false,
      },
    },
  });
}

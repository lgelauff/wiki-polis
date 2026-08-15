import {queryOptions} from '@tanstack/react-query';

import {api, requireApiData} from '../client';

export const sessionQuery = () => queryOptions({
  queryKey: ['session'],
  queryFn: async () => (await requireApiData(api.GET('/session'))).data,
  staleTime: 30_000,
});

import {queryOptions} from '@tanstack/react-query';

import {MAINTENANCE_RECHECK_MS} from '../../maintenance';
import {api, requireApiData} from '../client';

export const sessionQuery = () => queryOptions({
  queryKey: ['session'],
  queryFn: async () => (await requireApiData(api.GET('/session'))).data,
  staleTime: 30_000,
  // While maintenance mode is on (#619), look again every half minute, so a site admin's
  // banner goes away by itself when the switch is turned off.
  refetchInterval: (query) => query.state.data?.maintenance ? MAINTENANCE_RECHECK_MS : false,
});

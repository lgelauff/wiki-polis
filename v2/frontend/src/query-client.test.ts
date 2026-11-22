import {QueryObserver} from '@tanstack/react-query';
import {afterEach, beforeEach, expect, test, vi} from 'vitest';

import {ApiContractError} from './api/client';
import {MAINTENANCE_RECHECK_MS} from './maintenance';
import {createQueryClient} from './query-client';

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

/** Watches one query the way a mounted screen does, and returns how it ends up. */
function watch(queryFn: () => Promise<string>) {
  const client = createQueryClient();
  const observer = new QueryObserver(client, {queryKey: ['screen'], queryFn});
  const unsubscribe = observer.subscribe(() => {});
  return {observer, stop: () => { unsubscribe(); client.clear(); }};
}

test('a screen refused for maintenance comes back by itself once the switch is off (#619)', async () => {
  let maintenance = true;
  const queryFn = vi.fn(async () => {
    if (maintenance) throw new ApiContractError('paused', 'maintenance');
    return 'ok';
  });
  const {observer, stop} = watch(queryFn);
  await vi.advanceTimersByTimeAsync(0);
  expect(observer.getCurrentResult().status).toBe('error');
  expect(queryFn).toHaveBeenCalledTimes(1);

  maintenance = false;
  await vi.advanceTimersByTimeAsync(MAINTENANCE_RECHECK_MS);
  expect(observer.getCurrentResult().data).toBe('ok');
  expect(queryFn).toHaveBeenCalledTimes(2);
  stop();
});

test('other errors are not polled', async () => {
  const queryFn = vi.fn(async (): Promise<string> => {
    throw new ApiContractError('gone', 'not_found');
  });
  const {observer, stop} = watch(queryFn);
  await vi.advanceTimersByTimeAsync(0);
  expect(observer.getCurrentResult().status).toBe('error');
  await vi.advanceTimersByTimeAsync(MAINTENANCE_RECHECK_MS * 3);
  expect(queryFn).toHaveBeenCalledTimes(1);
  stop();
});

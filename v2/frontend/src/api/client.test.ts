import {expect, test} from 'vitest';

import {api} from './client';

test('typed client reads the mocked conversation contract', async () => {
  const result = await api.GET('/conversations', {
    params: {query: {space: 'real'}},
  });

  expect(result.error).toBeUndefined();
  expect(result.data?.data.groups.needsAttention[0]?.slug)
    .toBe('community-strategy');
});

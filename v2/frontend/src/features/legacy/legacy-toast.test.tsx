import {Suspense} from 'react';
import {QueryClientProvider} from '@tanstack/react-query';
import {act, fireEvent, render, screen} from '@testing-library/react';
import {afterEach, expect, test, vi} from 'vitest';

import {LegacyToast, type LegacyToastMessage} from './legacy-toast';
import {MessageProvider} from '../../i18n/messages';
import {createQueryClient} from '../../query-client';
import {testMessages} from '../../test/handlers';

/** pr-check #540 (accessibility-3, owner decision): an error or a warning floats in the far
 *  corner of the admin console, where a screen-magnifier user is likely to miss it, so it
 *  stays until dismissed. A success or an info toast still goes by itself. */

afterEach(() => {
  vi.useRealTimers();
});

async function showToast(category: LegacyToastMessage['category']) {
  const onDismiss = vi.fn();
  // Fake timers before the render, so the toast's own timer (if any) is a fake one.
  vi.useFakeTimers({shouldAdvanceTime: true});
  const view = render(
    <QueryClientProvider client={createQueryClient()}>
      <Suspense fallback={null}>
        <MessageProvider locale="en">
          <LegacyToast toast={{id: 1, category, message: `A ${category} message.`}} onDismiss={onDismiss} />
        </MessageProvider>
      </Suspense>
    </QueryClientProvider>,
  );
  await screen.findByText(`A ${category} message.`, {}, {timeout: 10_000});
  return {onDismiss, view};
}

test.each(['error', 'warning'] as const)('a %s toast stays until it is dismissed', async (category) => {
  const {onDismiss} = await showToast(category);

  act(() => { vi.advanceTimersByTime(10 * 60_000); });
  expect(onDismiss).not.toHaveBeenCalled();

  fireEvent.click(screen.getByRole('button', {name: testMessages['base-dismiss']!}));
  expect(onDismiss).toHaveBeenCalledTimes(1);
});

test.each([['success', 4_000], ['info', 5_000]] as const)(
  'a %s toast goes by itself after %i ms', async (category, duration) => {
    const {onDismiss} = await showToast(category);

    act(() => { vi.advanceTimersByTime(duration - 1_500); });
    expect(onDismiss).not.toHaveBeenCalled();
    act(() => { vi.advanceTimersByTime(1_500); });
    expect(onDismiss).toHaveBeenCalledTimes(1);
  },
);

import {QueryClientProvider} from '@tanstack/react-query';
import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {expect, test, vi} from 'vitest';

import {App} from './app';
import {createQueryClient} from './query-client';

function renderApp(entry: string) {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={[entry]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

test('blocks a Jinja navigation and identifies the missing React coverage', async () => {
  const warning = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
  renderApp('/app/admin?spa_only=1');

  expect(await screen.findByLabelText('SPA-only testing mode')).toBeVisible();
  fireEvent.click(await screen.findByRole('link', {name: 'Community strategy'}));

  const gap = screen.getByRole('alertdialog', {name: 'Not implemented in the React SPA'});
  expect(gap).toHaveTextContent('/c/community-strategy');
  expect(warning).toHaveBeenCalledWith(
    '[SPA-only] Blocked legacy navigation to /c/community-strategy',
  );
});

test('persists SPA-only mode for later navigation in the same tab', async () => {
  const first = renderApp('/app/real?spa_only=1');
  expect(await screen.findByLabelText('SPA-only testing mode')).toBeVisible();
  expect(globalThis.sessionStorage.getItem('wiki-polis:spa-only')).toBe('1');
  first.unmount();

  renderApp('/app/real');
  expect(await screen.findByLabelText('SPA-only testing mode')).toBeVisible();
});

test('allows the tester to turn Jinja fallbacks back on', async () => {
  renderApp('/app/real?spa_only=1');
  const banner = await screen.findByLabelText('SPA-only testing mode');

  fireEvent.click(screen.getByRole('button', {name: 'Allow Jinja fallbacks'}));

  expect(banner).not.toBeInTheDocument();
  expect(globalThis.sessionStorage.getItem('wiki-polis:spa-only')).toBeNull();
});

test('supports an explicit URL switch to disable persisted strict mode', async () => {
  globalThis.sessionStorage.setItem('wiki-polis:spa-only', '1');
  renderApp('/app/real?spa_only=0');

  await waitFor(() => {
    expect(screen.queryByLabelText('SPA-only testing mode')).not.toBeInTheDocument();
    expect(globalThis.sessionStorage.getItem('wiki-polis:spa-only')).toBeNull();
  });
});

test('shows an explicit gap for an unknown SPA route instead of redirecting', () => {
  renderApp('/app/not-covered?spa_only=1');

  expect(screen.getByRole('heading', {name: 'Not implemented in the React SPA'})).toBeVisible();
  expect(screen.getByText('/app/not-covered?spa_only=1')).toBeVisible();
});

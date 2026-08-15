import {QueryClientProvider} from '@tanstack/react-query';
import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {expect, test, vi} from 'vitest';

import {App} from './app';
import {createQueryClient} from './query-client';
import {SpaModeToggle, StrictSpaBoundary} from './strict-spa-mode';

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
  render(
    <MemoryRouter initialEntries={['/app/real?spa_only=1']}>
      <StrictSpaBoundary><a href="/legacy-only">Legacy-only page</a></StrictSpaBoundary>
    </MemoryRouter>,
  );

  expect(globalThis.localStorage.getItem('wiki-polis:spa-only')).toBe('1');
  fireEvent.click(screen.getByRole('link', {name: 'Legacy-only page'}));

  const gap = screen.getByRole('alertdialog', {name: 'Not implemented in the React SPA'});
  expect(gap).toHaveTextContent('/legacy-only');
  expect(warning).toHaveBeenCalledWith(
    '[SPA-only] Blocked legacy navigation to /legacy-only',
  );
});

test('persists SPA-only mode for later navigation in the same tab', async () => {
  const first = renderApp('/app/real?spa_only=1');
  expect(await screen.findByRole('switch', {name: /SPA only on/})).toBeVisible();
  expect(globalThis.localStorage.getItem('wiki-polis:spa-only')).toBe('1');
  first.unmount();

  renderApp('/app/real');
  expect(await screen.findByRole('switch', {name: /SPA only on/})).toBeVisible();
});

test('allows the tester to turn Jinja fallbacks back on', async () => {
  renderApp('/app/real?spa_only=1');
  const toggle = await screen.findByRole('switch', {name: /SPA only on/});

  fireEvent.click(toggle);

  expect(await screen.findByRole('switch', {name: /SPA only off/})).toBeVisible();
  expect(globalThis.localStorage.getItem('wiki-polis:spa-only')).toBeNull();
});

test('supports an explicit URL switch to disable persisted strict mode', async () => {
  globalThis.localStorage.setItem('wiki-polis:spa-only', '1');
  renderApp('/app/real?spa_only=0');

  await waitFor(() => {
    expect(screen.getByRole('switch', {name: /SPA only off/})).toBeVisible();
    expect(globalThis.localStorage.getItem('wiki-polis:spa-only')).toBeNull();
  });
});

test('offers a persistent header toggle only in development', () => {
  render(
    <MemoryRouter>
      <StrictSpaBoundary>
        <SpaModeToggle developerMode />
      </StrictSpaBoundary>
    </MemoryRouter>,
  );

  fireEvent.click(screen.getByRole('switch', {name: /SPA only off/}));

  expect(screen.getByRole('switch', {name: /SPA only on/})).toBeVisible();
  expect(globalThis.localStorage.getItem('wiki-polis:spa-only')).toBe('1');
  expect(document.cookie).toContain('wiki-polis-spa-only=1');
});

test('hides the header toggle outside development', () => {
  render(
    <MemoryRouter>
      <StrictSpaBoundary>
        <SpaModeToggle developerMode={false} />
      </StrictSpaBoundary>
    </MemoryRouter>,
  );

  expect(screen.queryByRole('switch')).not.toBeInTheDocument();
});

test('shows an explicit gap for an unknown SPA route instead of redirecting', () => {
  renderApp('/app/not-covered?spa_only=1');

  expect(screen.getByRole('heading', {name: 'Not implemented in the React SPA'})).toBeVisible();
  expect(screen.getByText('/app/not-covered?spa_only=1')).toBeVisible();
});

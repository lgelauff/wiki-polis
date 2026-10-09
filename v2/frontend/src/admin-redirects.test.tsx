import {QueryClientProvider} from '@tanstack/react-query';
import {render, screen} from '@testing-library/react';
import {MemoryRouter, useLocation} from 'react-router-dom';
import {expect, test} from 'vitest';

import {App} from './app';
import {createQueryClient} from './query-client';

/** The console's client-side redirects carry the query string (a `?uselang=`) and the
 *  fragment along, as a server redirect would. */

/** Where the router is, as text, so a redirect's target can be asserted whole. */
function WhereAmI() {
  const {pathname, search, hash} = useLocation();
  return <output data-testid="where">{`${pathname}${search}${hash}`}</output>;
}

function renderAt(path: string) {
  return render(<QueryClientProvider client={createQueryClient()}><MemoryRouter initialEntries={[path]}><App /><WhereAmI /></MemoryRouter></QueryClientProvider>);
}

test('the bare settings path keeps its query string and fragment on the way to Basics', async () => {
  renderAt('/app/admin/conversations/7/settings?uselang=en#settings-guidance');

  expect(await screen.findByRole('heading', {name: 'Settings', level: 1})).toBeVisible();
  expect(screen.getByTestId('where')).toHaveTextContent(
    '/app/admin/conversations/7/settings/basics?uselang=en#settings-guidance',
  );
});

test('an old admin path keeps its query string and fragment on the way to its Settings tab', async () => {
  renderAt('/admin/conversations/7/invites?uselang=en#top');

  expect(await screen.findByRole('heading', {name: 'Settings', level: 1})).toBeVisible();
  expect(screen.getByTestId('where')).toHaveTextContent(
    '/admin/conversations/7/settings/invitations?uselang=en#top',
  );
});

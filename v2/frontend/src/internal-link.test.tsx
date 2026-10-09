import {fireEvent, render, screen} from '@testing-library/react';
import {MemoryRouter, useLocation} from 'react-router-dom';
import {expect, test, vi} from 'vitest';

import {canonicalClientPath} from './client-routes';
import {InternalLink} from './internal-link';
import * as routeModules from './route-modules';

function LocationProbe() {
  const location = useLocation();
  return <output aria-label="client location">{`${location.pathname}${location.hash}`}</output>;
}

test.each([
  ['/app/real', '/consultations'],
  ['/app/conversations/topic/arguments', '/c/topic#tab-arguments'],
  ['/app/admin/conversations/7/invitations', '/admin/conversations/7/invites'],
  ['/app/admin/conversations/7/settings/basics', '/admin/conversations/7/settings/basics'],
  ['/app/admin/conversations/7/moderation/queue', '/admin/conversations/7/moderation/queue'],
  ['/c/topic/report', '/c/topic/report'],
])('maps %s to canonical client route %s', (source, expected) => {
  expect(canonicalClientPath(source)).toBe(expected);
});

test.each([
  '/admin/conversations/7/settings',
  '/admin/conversations/7/settings/basics',
  '/admin/conversations/7/settings/access',
])('%s is a client route, so the Settings strip links stay in the SPA', (path) => {
  // The strip's tabs are `<a href>` built from the conversation id; an unregistered path
  // would make InternalLink render a plain anchor and cost a full page load.
  expect(canonicalClientPath(path)).toBe(path);
});

test.each([
  '/admin/conversations/7/moderation/queue',
  '/admin/conversations/7/moderation/flags',
  '/admin/conversations/7/moderation/featured',
  '/admin/conversations/7/moderation/people',
])('%s is a client route, so the Moderation strip links stay in the SPA', (path) => {
  expect(canonicalClientPath(path)).toBe(path);
});

test('prevents a document navigation and updates React Router location', () => {
  render(
    <MemoryRouter initialEntries={['/']}>
      <InternalLink href="/app/real">Consultations</InternalLink>
      <LocationProbe />
    </MemoryRouter>,
  );

  const link = screen.getByRole('link', {name: 'Consultations'});
  expect(link).toHaveAttribute('href', '/consultations');
  expect(fireEvent.click(link)).toBe(false);
  expect(screen.getByLabelText('client location')).toHaveTextContent('/consultations');
});

test('prefetches a lazy route on hover and keyboard focus', () => {
  const prefetch = vi.spyOn(routeModules, 'prefetchClientRoute').mockImplementation(() => undefined);
  render(<MemoryRouter><InternalLink href="/c/topic/report">Report</InternalLink></MemoryRouter>);

  const link = screen.getByRole('link', {name: 'Report'});
  fireEvent.mouseEnter(link);
  fireEvent.focus(link);

  expect(prefetch).toHaveBeenNthCalledWith(1, '/c/topic/report');
  expect(prefetch).toHaveBeenNthCalledWith(2, '/c/topic/report');
});

test.each([
  ['/login?next=%2Fadmin', '/login?next=%2Fadmin'],
  ['https://meta.wikimedia.org/', 'https://meta.wikimedia.org/'],
])('keeps server or external destination %s as a native anchor', (href, expected) => {
  render(<MemoryRouter><InternalLink href={href}>Leave SPA</InternalLink></MemoryRouter>);
  expect(screen.getByRole('link', {name: 'Leave SPA'})).toHaveAttribute('href', expected);
  expect(canonicalClientPath(href)).toBeNull();
});

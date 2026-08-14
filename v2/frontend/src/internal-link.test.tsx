import {fireEvent, render, screen} from '@testing-library/react';
import {MemoryRouter, useLocation} from 'react-router-dom';
import {expect, test} from 'vitest';

import {canonicalClientPath} from './client-routes';
import {InternalLink} from './internal-link';

function LocationProbe() {
  const location = useLocation();
  return <output aria-label="client location">{`${location.pathname}${location.hash}`}</output>;
}

test.each([
  ['/app/real', '/consultations'],
  ['/app/conversations/topic/arguments', '/c/topic#tab-arguments'],
  ['/app/admin/conversations/7/invitations', '/admin/conversations/7/invites'],
  ['/c/topic/report', '/c/topic/report'],
])('maps %s to canonical client route %s', (source, expected) => {
  expect(canonicalClientPath(source)).toBe(expected);
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

test.each([
  ['/login?next=%2Fadmin', '/login?next=%2Fadmin'],
  ['https://meta.wikimedia.org/', 'https://meta.wikimedia.org/'],
])('keeps server or external destination %s as a native anchor', (href, expected) => {
  render(<MemoryRouter><InternalLink href={href}>Leave SPA</InternalLink></MemoryRouter>);
  expect(screen.getByRole('link', {name: 'Leave SPA'})).toHaveAttribute('href', expected);
  expect(canonicalClientPath(href)).toBeNull();
});

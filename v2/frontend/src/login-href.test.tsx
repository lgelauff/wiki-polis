import {render, screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {expect, test} from 'vitest';

import {loginHref, useLoginHref} from './login-href';

test('the login link names the page to come back to', () => {
  expect(loginHref('/login', {pathname: '/accept/community-strategy', search: ''}))
    .toBe('/login?next=%2Faccept%2Fcommunity-strategy');
});

test('other parameters come along, a voucher code never does', () => {
  expect(loginHref('/login', {pathname: '/c/community-strategy', search: '?v=X7F3K9M2ABCD&uselang=nl'}))
    .toBe('/login?next=%2Fc%2Fcommunity-strategy%3Fuselang%3Dnl');
});

test('a login link that already has a query gets next as one more parameter', () => {
  expect(loginHref('/login?x=1', {pathname: '/admin', search: ''})).toBe('/login?x=1&next=%2Fadmin');
});

function Probe() {
  return <a href={useLoginHref('/login')}>Log in</a>;
}

test('the hook reads the page the router is on', () => {
  render(<MemoryRouter initialEntries={['/c/community-strategy/report?uselang=qqx']}><Probe /></MemoryRouter>);
  expect(screen.getByRole('link', {name: 'Log in'}))
    .toHaveAttribute('href', '/login?next=%2Fc%2Fcommunity-strategy%2Freport%3Fuselang%3Dqqx');
});

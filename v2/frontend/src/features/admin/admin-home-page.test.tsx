import {QueryClientProvider} from '@tanstack/react-query';
import {render, screen, waitFor, within} from '@testing-library/react';
import {http, HttpResponse} from 'msw';
import {MemoryRouter, useLocation} from 'react-router-dom';
import {afterEach, expect, test, vi} from 'vitest';

import type {components} from '../../api/schema';
import {adminHomeQuery} from '../../api/queries';
import {App} from '../../app';
import {createQueryClient} from '../../query-client';
import {server} from '../../test/server';

/** Admin home (#538), and the site admin dashboard at its own address, through the app at
 *  the literal URLs a browser would open. */

type Home = components['schemas']['AdminHome'];
type Row = Home['conversations'][number];
type Session = components['schemas']['Session'];

const HOME_URL = new URL('/api/v1/admin/home', globalThis.location.origin).toString();
const CATALOG_URL = new URL('/api/v1/admin', globalThis.location.origin).toString();
const LIFECYCLE_URL = new URL('/api/v1/admin/conversations/7', globalThis.location.origin).toString();
const SESSION_URL = new URL('/api/v1/session', globalThis.location.origin).toString();

const FORBIDDEN = {error: {code: 'forbidden', message: 'You do not have access to this resource.'}};
const UNAUTHORIZED = {error: {code: 'unauthorized', message: 'Authentication required.'}};

afterEach(() => {
  vi.unstubAllGlobals();
});

/** The login is the server's, so the boundary leaves the app with `location.assign`; jsdom
 *  cannot navigate, so the call itself is what is asserted. */
function stubAssign() {
  const assign = vi.fn();
  vi.stubGlobal('location', {...globalThis.location, assign});
  return assign;
}

function row(id: number, overrides: Partial<Row> = {}): Row {
  return {
    id, title: `Consultation ${id}`, role: 'Organizer', status: 'active', openFlags: 0, pendingStatements: 0,
    links: {overview: `/admin/conversations/${id}`},
    ...overrides,
  };
}

function serveHome(conversations: Row[], siteAdmin = false) {
  server.use(http.get(HOME_URL, () => HttpResponse.json({data: {
    conversations,
    links: {self: '/api/v1/admin/home', siteAdminDashboard: siteAdmin ? '/site-admin' : null},
  } satisfies Home})));
}

function serveSession(administerSite: boolean) {
  const data: Session = {
    state: 'authenticated',
    user: {username: 'Example editor', emailable: true},
    capabilities: {administerSite},
    csrfToken: 'test-csrf-token',
    developerLogins: [],
    gitVersion: 'test-version',
    locales: {current: 'en', available: [{code: 'en', name: 'English'}]},
    links: {login: '/login', logout: '/logout'},
  };
  server.use(http.get(SESSION_URL, () => HttpResponse.json({data})));
}

/** Where the router is, as text, so a redirect's target can be asserted whole. */
function WhereAmI() {
  const {pathname, search, hash} = useLocation();
  return <output data-testid="where">{`${pathname}${search}${hash}`}</output>;
}

function renderAt(path: string) {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={[path]}><App /><WhereAmI /></MemoryRouter>
    </QueryClientProvider>,
  );
}

async function homeList() {
  await screen.findByRole('heading', {name: 'Admin home', level: 1});
  return document.querySelector<HTMLElement>('.admin-page .admin-rows')!;
}

test('an organizer sees their consultations: title to its Overview, role, status, open flags', async () => {
  serveSession(false);
  serveHome([
    row(7, {title: 'Community strategy', openFlags: 2}),
    row(8, {title: 'Paused talk', status: 'paused'}),
  ]);
  renderAt('/admin');

  const list = await homeList();
  const rows = within(list).getAllByRole('listitem');
  expect(rows).toHaveLength(2);
  expect(within(rows[0]!).getByRole('link', {name: 'Community strategy'}))
    .toHaveAttribute('href', '/admin/conversations/7');
  expect(rows[0]!).toHaveTextContent('Organizer · Active · 2 open flags');
  // A zero is left out: an empty counter is noise, not information.
  expect(rows[1]!).toHaveTextContent('Organizer · Paused');
  expect(rows[1]!).not.toHaveTextContent('open flag');
  // A list, not a table: there are no columns to compare.
  expect(screen.queryByRole('table')).toBeNull();
  // Inside the console frame, at site level: one crumb, no consultation sections.
  expect(screen.getByRole('main')).toHaveClass('admin-shell__main');
  expect(within(screen.getByRole('navigation', {name: 'Admin breadcrumb'})).getAllByRole('listitem'))
    .toHaveLength(1);
  expect(document.title).toBe('Admin home — Proto');
  // Not a site admin: no way to the dashboard.
  expect(screen.queryByRole('link', {name: 'Site admin dashboard'})).toBeNull();
  // Admin home is built, so the frame no longer says it is coming.
  expect(screen.queryByText(/Also coming: Admin home/)).toBeNull();
});

test('a moderator sees their role as Moderator, and the closed status in words', async () => {
  serveSession(false);
  serveHome([row(9, {title: 'Closed consultation', role: 'Moderator', status: 'closed', openFlags: 1})]);
  renderAt('/admin');

  const list = await homeList();
  const only = within(list).getByRole('listitem');
  expect(within(only).getByRole('link', {name: 'Closed consultation'}))
    .toHaveAttribute('href', '/admin/conversations/9');
  expect(only).toHaveTextContent('Moderator · Closed · 1 open flag');
});

test('a site admin with no role sees the empty state and the way to the dashboard', async () => {
  serveSession(true);
  serveHome([], true);
  renderAt('/admin');

  expect(await screen.findByText('You have no role in any consultation yet.')).toBeVisible();
  const nav = screen.getByRole('navigation', {name: 'Admin sections'});
  expect(within(nav).getByRole('link', {name: 'Site admin dashboard'})).toHaveAttribute('href', '/site-admin');
  // The mark goes to Admin home, which is where this is: plain text here.
  expect(within(nav).queryByRole('link', {name: 'Admin home'})).toBeNull();
});

test('/site-admin is the site admin dashboard', async () => {
  serveSession(true);
  renderAt('/site-admin');

  expect(await screen.findByRole('heading', {name: 'Site admin dashboard', level: 1})).toBeVisible();
  const nav = screen.getByRole('navigation', {name: 'Admin sections'});
  expect(within(nav).getByRole('link', {name: 'Site admin dashboard'})).toHaveAttribute('aria-current', 'page');
  expect(within(nav).getByRole('link', {name: 'Admin home'})).toHaveAttribute('href', '/admin');
  expect(screen.getByTestId('where')).toHaveTextContent('/site-admin');
});

test('the old dashboard address under /app lands on /site-admin', async () => {
  serveSession(true);
  renderAt('/app/admin');

  expect(await screen.findByRole('heading', {name: 'Site admin dashboard', level: 1})).toBeVisible();
  expect(screen.getByTestId('where')).toHaveTextContent(/^\/site-admin$/);
});

test.each([
  ['/admin', HOME_URL],
  ['/site-admin', CATALOG_URL],
  ['/admin/conversations/7', LIFECYCLE_URL],
])('someone without a role who opens %s gets the app\'s access page', async (path, api) => {
  serveSession(false);
  server.use(http.get(api, () => HttpResponse.json(FORBIDDEN, {status: 403})));
  renderAt(path);

  expect(await screen.findByRole('heading', {name: 'Not allowed', level: 1})).toBeVisible();
  expect(screen.getByText('You do not have access to this page.')).toBeVisible();
  expect(screen.getByRole('link', {name: '← back to home'})).toHaveAttribute('href', '/');
  // The site's own frame, not Werkzeug's bare document.
  expect(screen.queryByRole('heading', {name: 'Forbidden'})).toBeNull();
  expect(document.title).toBe('403 Not allowed — Proto');
});

test('statements awaiting moderation are a plain count after the flags, left out at zero or unknown', async () => {
  serveSession(false);
  serveHome([
    row(7, {title: 'With both', openFlags: 2, pendingStatements: 5}),
    row(8, {title: 'Pending only', pendingStatements: 1}),
    row(9, {title: 'Nothing pending', pendingStatements: 0}),
    row(10, {title: 'Unknown', status: 'closed', pendingStatements: null}),
  ]);
  renderAt('/admin');

  const rows = within(await homeList()).getAllByRole('listitem');
  expect(rows[0]!).toHaveTextContent(/^With bothOrganizer · Active · 2 open flags · 5 statements to moderate$/);
  expect(rows[1]!).toHaveTextContent(/^Pending onlyOrganizer · Active · 1 statement to moderate$/);
  expect(rows[2]!).toHaveTextContent(/^Nothing pendingOrganizer · Active$/);
  expect(rows[3]!).toHaveTextContent(/^UnknownOrganizer · Closed$/);
});

test.each([
  ['/admin', HOME_URL, '/login?next=%2Fadmin'],
  // The query string rides along; a voucher code (`v`) never does.
  ['/admin/conversations/7?x=1&v=SECRET', LIFECYCLE_URL, '/login?next=%2Fadmin%2Fconversations%2F7%3Fx%3D1'],
])('signed out on %s: one navigation to the login, with the way back', async (path, api, login) => {
  serveSession(false);
  server.use(http.get(api, () => HttpResponse.json(UNAUTHORIZED, {status: 401})));
  const assign = stubAssign();
  renderAt(path);

  await waitFor(() => expect(assign).toHaveBeenCalled());
  expect(assign).toHaveBeenCalledTimes(1);
  expect(assign).toHaveBeenCalledWith(login);
  expect(screen.queryByRole('heading', {name: 'Not allowed'})).toBeNull();
});

test('a refusal (403) shows the access page and goes nowhere', async () => {
  serveSession(false);
  server.use(http.get(HOME_URL, () => HttpResponse.json(FORBIDDEN, {status: 403})));
  const assign = stubAssign();
  renderAt('/admin');

  expect(await screen.findByRole('heading', {name: 'Not allowed', level: 1})).toBeVisible();
  expect(assign).not.toHaveBeenCalled();
  expect(screen.getByTestId('where')).toHaveTextContent(/^\/admin$/);
});

test('Admin home is fetched afresh on every visit, since changes elsewhere do not invalidate it', () => {
  expect(adminHomeQuery().staleTime).toBe(0);
});

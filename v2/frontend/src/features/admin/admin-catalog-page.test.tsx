import {Suspense} from 'react';
import {QueryClientProvider} from '@tanstack/react-query';
import {fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {http, HttpResponse} from 'msw';
import {MemoryRouter} from 'react-router-dom';
import {expect, test} from 'vitest';

import type {components} from '../../api/schema';
import {App} from '../../app';
import {AdminCatalogPage} from './admin-catalog-page';
import {MessageProvider} from '../../i18n/messages';
import {createQueryClient} from '../../query-client';
import {adminCatalogFixture} from '../../test/handlers';
import {renderAsQqx, untranslatedCopy} from '../../test/i18n';
import {server} from '../../test/server';

type Row = components['schemas']['AdminCatalog']['conversations'][number];

const CATALOG_URL = new URL('/api/v1/admin', globalThis.location.origin).toString();

function row(id: number, overrides: Partial<Row> = {}): Row {
  return {
    id, slug: `consultation-${id}`, title: `Consultation ${id}`,
    accessPolicy: 'public', status: 'active', createdAt: '2026-08-01T10:00:00Z',
    links: {participant: `/c/consultation-${id}`, manage: `/admin/conversations/${id}`},
    ...overrides,
  };
}

/** One of every status the dashboard has to tell apart, plus one practice item. */
const mixed = [
  row(1),
  row(2, {status: 'paused'}),
  row(3, {status: 'closed'}),
  row(4, {status: 'archived'}),
  row(5, {accessPolicy: 'demo', status: 'active'}),
];

function serve(conversations: Row[]) {
  const fixture = adminCatalogFixture();
  server.use(http.get(CATALOG_URL, () => HttpResponse.json({data: {...fixture, conversations}})));
}

/** `locale` is left to the provider by default so that `renderAsQqx()` can take effect. */
function renderPage(locale: 'en' | 'provider' = 'en') {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={['/admin']}>
        <Suspense fallback={null}>
          <MessageProvider {...(locale === 'provider' ? {} : {locale})}><AdminCatalogPage csrfToken="test-csrf-token" /></MessageProvider>
        </Suspense>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

/** The consultations table, as opposed to the site-admin one below it. */
function conversationsTable() {
  return screen.getAllByRole('table')[0]!;
}

test('the page is the site admin dashboard, with the columns it decides on', async () => {
  serve(mixed);
  renderPage();

  expect(await screen.findByRole('heading', {name: 'Site admin dashboard', level: 2}))
    .toBeVisible();
  expect(document.title).toContain('Site admin dashboard');
  expect(screen.getByRole('navigation', {name: 'Admin breadcrumb'}))
    .toHaveTextContent('Site admin dashboard');
  // The caption is the table's own name; the heading above it is sr-only so it is not
  // read twice.
  expect(within(conversationsTable()).getByText('All consultations')).toBeVisible();

  const table = conversationsTable();
  // Title · Access · Status · links. The slug is not a column: it is in the link.
  expect(within(table).getAllByRole('columnheader').map((cell) => cell.textContent))
    .toEqual(['Title', 'Access', 'Status', '']);
  expect(within(table).queryByRole('columnheader', {name: 'Slug'})).toBeNull();

  // Three main rows: the archived one is not among them, and neither is the practice one.
  const rows = within(table).getAllByRole('row').slice(1);
  expect(rows.map((item) => item.querySelector('td')?.textContent))
    .toEqual(['Consultation 1', 'Consultation 2', 'Consultation 3']);
});

test('each status says the server’s word, archived included', async () => {
  serve(mixed);
  renderPage();

  await screen.findByRole('heading', {name: 'Site admin dashboard', level: 2});
  const table = conversationsTable();
  expect(within(screen.getByText('Practice Environment (1)').closest('details')!)
    .getByRole('row')).toHaveTextContent('active');
  expect(within(screen.getByText('Other (1)').closest('details')!).getByRole('row'))
    .toHaveTextContent('archived');
  // The closed consultation is closed, and not called archived.
  const closed = within(table).getByRole('row', {name: /Consultation 3/});
  expect(closed).toHaveTextContent('closed');
  expect(closed).not.toHaveTextContent('archived');
  // Badge classes stay as they were: active green, paused, everything else quiet.
  expect(within(table).getByText('active')).toHaveClass('badge-active-inline');
  expect(within(table).getByText('paused')).toHaveClass('badge-paused-inline');
  expect(within(table).getByText('closed')).toHaveClass('badge-inactive');
});

test('the practice item and the archived one sit in collapsed groups, not in the table', async () => {
  serve(mixed);
  renderPage();

  await screen.findByRole('heading', {name: 'Site admin dashboard', level: 2});
  const practice = screen.getByText('Practice Environment (1)').closest('details')!;
  const other = screen.getByText('Other (1)').closest('details')!;
  expect(practice).not.toHaveAttribute('open');
  expect(other).not.toHaveAttribute('open');
  // A practice item is never listed as a consultation.
  const table = conversationsTable();
  expect(within(table).queryByText('Consultation 5')).toBeNull();
  // Closed by default, so the rows are in the document but not on screen until it is opened.
  expect(within(practice).getByText('Consultation 5')).toBeInTheDocument();
  expect(within(other).getByText('Consultation 4')).toBeInTheDocument();
  expect(within(practice).getByText('Consultation 5')).not.toBeVisible();
  fireEvent.click(within(practice).getByText('Practice Environment (1)'));
  expect(within(practice).getByText('Consultation 5')).toBeVisible();
});

test('a practice item that is also archived goes under the Practice Environment', async () => {
  // Which space an item sits in decides where it is listed, not how far it got (#472).
  serve([row(5, {accessPolicy: 'demo', status: 'archived'})]);
  renderPage();

  await screen.findByRole('heading', {name: 'Site admin dashboard', level: 2});
  expect(screen.getByText('Practice Environment (1)')).toBeVisible();
  expect(screen.queryByText(/^Other \(/)).toBeNull();
});

test('with neither a practice item nor an archived one there is no group at all', async () => {
  serve([row(1), row(2, {status: 'paused'})]);
  renderPage();

  await screen.findByRole('heading', {name: 'Site admin dashboard', level: 2});
  expect(document.querySelectorAll('details')).toHaveLength(0);
});

test('a title opens the participant view and "manage" the console, on one request', async () => {
  // "Exactly one request on render" counts GET /api/v1/admin and nothing else: the page is
  // presentation, so it fetches what it draws and asks for nothing more.
  let catalogRequests = 0;
  server.use(http.get(CATALOG_URL, () => {
    catalogRequests += 1;
    return HttpResponse.json({data: adminCatalogFixture()});
  }));
  renderPage();
  await screen.findByRole('heading', {name: 'Site admin dashboard', level: 2});

  expect(screen.getByRole('link', {name: 'Community strategy'}))
    .toHaveAttribute('href', '/c/community-strategy');
  expect(screen.getByRole('link', {name: 'manage'}))
    .toHaveAttribute('href', '/admin/conversations/7');
  expect(screen.getByRole('link', {name: 'settings'}))
    .toHaveAttribute('href', '/admin/conversations/7/settings');
  expect(catalogRequests).toBe(1);
});

test('granting site admin posts the username and says so when nobody has signed in', async () => {
  const sent: unknown[] = [];
  server.use(http.post(
    new URL('/api/v1/admin/global-admin-grants', globalThis.location.origin).toString(),
    async ({request}) => {
      const body = await request.json() as unknown;
      sent.push(body);
      return HttpResponse.json({data: {participantId: 23, username: 'Example editor', granted: true, changed: true, catalog: adminCatalogFixture(true)}}, {status: 201});
    },
  ));
  renderPage();
  await screen.findByRole('heading', {name: 'Site admin dashboard', level: 2});

  fireEvent.change(screen.getByLabelText('Wikimedia username'), {target: {value: 'Example editor'}});
  fireEvent.click(screen.getByRole('button', {name: 'Grant'}));

  await waitFor(() => expect(sent).toEqual([{username: 'Example editor'}]));
  await waitFor(() => expect(screen.getAllByText('Example editor').length).toBeGreaterThan(0));

  // The refusal for a name nobody has signed in with, worded as it always has been.
  server.use(http.post(
    new URL('/api/v1/admin/global-admin-grants', globalThis.location.origin).toString(),
    () => HttpResponse.json({error: {
      code: 'participant_not_found',
      message: 'That account must sign in once before it can be granted access.',
    }}, {status: 404}),
  ));
  fireEvent.change(screen.getByLabelText('Wikimedia username'), {target: {value: 'MissingEditor'}});
  fireEvent.click(screen.getByRole('button', {name: 'Grant'}));

  expect(await screen.findByRole('alert')).toHaveTextContent(
    'No account found for "MissingEditor". They must log in at least once first.',
  );
});

test('retiring a site admin puts granted:false, and a 403 shows the boundary', async () => {
  const sent: unknown[] = [];
  server.use(http.put(
    new URL('/api/v1/admin/global-admins/:participantId', globalThis.location.origin).toString(),
    async ({params, request}) => {
      const body = await request.json() as unknown;
      sent.push({participantId: Number(params.participantId), body});
      return HttpResponse.json({data: {participantId: Number(params.participantId), username: 'Example editor', granted: false, changed: true, catalog: adminCatalogFixture(false)}});
    },
  ));
  renderPage();
  await screen.findByRole('heading', {name: 'Site admin dashboard', level: 2});

  fireEvent.click(screen.getByRole('button', {name: 'remove'}));
  await waitFor(() => expect(sent).toEqual([{participantId: 1, body: {granted: false}}]));
});

test('a 403 on the catalogue shows the boundary, not the page', async () => {
  // The boundary is the router's (`AdminAccessBoundary`), so this goes through the app.
  server.use(http.get(CATALOG_URL, () => HttpResponse.json({
    error: {code: 'forbidden', message: 'You do not have access to this resource.'},
  }, {status: 403})));
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={['/app/admin']}><App /></MemoryRouter>
    </QueryClientProvider>,
  );
  expect(await screen.findByRole('heading', {name: 'Forbidden'})).toBeVisible();
  expect(screen.queryByRole('heading', {name: 'Site admin dashboard'})).toBeNull();
});

test('the three "Also coming" lines are muted English and nothing else', async () => {
  serve([row(1)]);
  renderPage();
  await screen.findByRole('heading', {name: 'Site admin dashboard', level: 2});

  const lines = screen.getAllByText(/^Also coming:/);
  expect(lines).toHaveLength(3);
  expect(lines.map((line) => line.textContent)).toEqual([
    'Also coming: Admin home, one table of the consultations you have a role in'
    + ' — not available yet (#473)',
    'Also coming: phase, participation counts, organizers, last action, and following or hiding'
    + ' a consultation — not available yet (#473)',
    'Also coming: voucher use, correct and wrong codes per consultation — not available yet (#473)',
  ]);
  for (const line of lines) {
    // `<main tabindex="-1">` is the frame's skip target, not a control these lines live in.
    expect(line.closest('a, button')).toBeNull();
    expect(line).not.toHaveAttribute('tabindex');
    expect(line.parentElement?.closest('a, button, [tabindex]:not(main)')).toBeNull();
  }
});

test('under a key-id catalogue the page is all keys and the three coming lines', async () => {
  renderAsQqx();
  serve([row(1)]);
  const {container} = renderPage('provider');
  await screen.findByRole('heading', {name: '(admin-site-dashboard)', level: 2});

  // Scoped to the page's own content: the legacy frame carries the site header and the
  // footer licence line, which are not this page's copy.
  const page = container.querySelector('.container')!;
  expect(untranslatedCopy([page], [
    // The fixture's own words: participant data is never keyed.
    'Consultation 1', 'consultation-1', 'adminuser', 'Full consultation',
    'Also coming: Admin home, one table of the consultations you have a role in'
    + ' — not available yet (#473)',
    'Also coming: phase, participation counts, organizers, last action, and following or hiding'
    + ' a consultation — not available yet (#473)',
    'Also coming: voucher use, correct and wrong codes per consultation — not available yet (#473)',
  ])).toEqual([]);
});
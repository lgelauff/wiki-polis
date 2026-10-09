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

  expect(await screen.findByRole('heading', {name: 'Site admin dashboard', level: 1}))
    .toBeVisible();
  expect(document.title).toContain('Site admin dashboard');
  expect(screen.getByRole('navigation', {name: 'Admin breadcrumb'}))
    .toHaveTextContent('Site admin dashboard');
  // The heading above the table names it, and is the only copy of those words, so a
  // screen reader does not hear them twice.
  expect(screen.getByRole('table', {name: 'All consultations'})).toBe(conversationsTable());
  expect(screen.getAllByText('All consultations')).toHaveLength(1);
  // At 320px the table is wider than the screen; it scrolls in its own box, not the page.
  expect(conversationsTable().parentElement).toHaveClass('admin-table-wrap');

  const table = conversationsTable();
  // Title · Access · Status · links. The slug is not a column: it is in the link.
  expect(within(table).getAllByRole('columnheader').map((cell) => cell.textContent))
    .toEqual(['Title', 'Access', 'Status', 'Actions']);
  expect(within(table).queryByRole('columnheader', {name: 'Slug'})).toBeNull();

  // Three main rows: the archived one is not among them, and neither is the practice one.
  const rows = within(table).getAllByRole('row').slice(1);
  expect(rows.map((item) => item.querySelector('td')?.textContent))
    .toEqual(['Consultation 1', 'Consultation 2', 'Consultation 3']);
});

test('each status says the server’s word, archived included', async () => {
  serve(mixed);
  renderPage();

  await screen.findByRole('heading', {name: 'Site admin dashboard', level: 1});
  const table = conversationsTable();
  expect(within(screen.getByText('Practice Environment', {selector: 'summary'}).closest('details')!)
    .getByRole('row', {name: /Consultation 5/})).toHaveTextContent('Active');
  expect(within(screen.getByText('Other', {selector: 'summary'}).closest('details')!)
    .getByRole('row', {name: /Consultation 4/})).toHaveTextContent('Archived');
  // The closed consultation is closed, and not called archived.
  const closed = within(table).getByRole('row', {name: /Consultation 3/});
  expect(closed).toHaveTextContent('Closed');
  expect(closed).not.toHaveTextContent('Archived');
  // Statuses are plain words in their cell: no badge, no box, no colour of their own.
  for (const word of ['Active', 'Paused', 'Closed']) {
    const cell = within(table).getByRole('cell', {name: word});
    expect(cell.children).toHaveLength(0);
    expect(cell.className).toBe('');
  }
  // A group's count is a bare number beside its name, not in brackets.
  expect(screen.getByText('Practice Environment', {selector: 'summary'}).querySelector('.admin-count'))
    .toHaveTextContent(/^1$/);
});

test('the practice item and the archived one sit in collapsed groups, not in the table', async () => {
  serve(mixed);
  renderPage();

  await screen.findByRole('heading', {name: 'Site admin dashboard', level: 1});
  const practice = screen.getByText('Practice Environment', {selector: 'summary'}).closest('details')!;
  const other = screen.getByText('Other', {selector: 'summary'}).closest('details')!;
  expect(practice).not.toHaveAttribute('open');
  expect(other).not.toHaveAttribute('open');
  // A practice item is never listed as a consultation.
  const table = conversationsTable();
  expect(within(table).queryByText('Consultation 5')).toBeNull();
  // Closed by default, so the rows are in the document but not on screen until it is opened.
  expect(within(practice).getByText('Consultation 5')).toBeInTheDocument();
  expect(within(other).getByText('Consultation 4')).toBeInTheDocument();
  expect(within(practice).getByText('Consultation 5')).not.toBeVisible();
  fireEvent.click(within(practice).getByText('Practice Environment', {selector: 'summary'}));
  expect(within(practice).getByText('Consultation 5')).toBeVisible();
  // Each group's table names its columns the way the main table does, so a cell in it has
  // a column name too.
  for (const group of [practice, other]) {
    expect(within(group).getAllByRole('columnheader').map((cell) => cell.textContent))
      .toEqual(['Title', 'Access', 'Status', 'Actions']);
  }
});

test('a practice item that is also archived goes under the Practice Environment', async () => {
  // Which space an item sits in decides where it is listed, not how far it got (#472).
  serve([row(5, {accessPolicy: 'demo', status: 'archived'})]);
  renderPage();

  await screen.findByRole('heading', {name: 'Site admin dashboard', level: 1});
  expect(screen.getByText('Practice Environment', {selector: 'summary'})).toBeVisible();
  expect(screen.queryByText('Other', {selector: 'summary'})).toBeNull();
});

test('with neither a practice item nor an archived one there is no group at all', async () => {
  serve([row(1), row(2, {status: 'paused'})]);
  renderPage();

  await screen.findByRole('heading', {name: 'Site admin dashboard', level: 1});
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
  await screen.findByRole('heading', {name: 'Site admin dashboard', level: 1});

  expect(screen.getByRole('link', {name: 'Community strategy'}))
    .toHaveAttribute('href', '/c/community-strategy');
  expect(screen.getByRole('link', {name: 'Manage'}))
    .toHaveAttribute('href', '/admin/conversations/7');
  expect(screen.getByRole('link', {name: 'Settings'}))
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
  await screen.findByRole('heading', {name: 'Site admin dashboard', level: 1});

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

test('retiring a site admin puts granted:false', async () => {
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
  await screen.findByRole('heading', {name: 'Site admin dashboard', level: 1});

  // The button carries whose role it removes after its visible word, so two rows' Removes
  // are told apart by name.
  fireEvent.click(screen.getByRole('button', {name: 'Remove — adminuser'}));
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
  await screen.findByRole('heading', {name: 'Site admin dashboard', level: 1});

  // The page's own lines; the console frame carries one of its own in the sidebar.
  const lines = within(document.querySelector<HTMLElement>('.admin-page')!).getAllByText(/^Also coming:/);
  expect(lines).toHaveLength(3);
  expect(lines.map((line) => line.textContent)).toEqual([
    'Also coming: Admin home, one table of the consultations you have a role in'
    + ' — not available yet (#473)',
    'Also coming: phase, participation counts, organizers, last action, and following or hiding'
    + ' a consultation — not available yet (#473)',
    'Also coming: voucher use, correct and wrong codes per consultation — not available yet (#473)',
  ]);
  for (const line of lines) {
    // The one "Also coming" component and class of the whole console, outside its frame too.
    expect(line).toHaveClass('admin-shell__coming');
    expect(line).toHaveAttribute('lang', 'en');
    // `<main tabindex="-1">` is the frame's skip target, not a control these lines live in.
    expect(line.closest('a, button')).toBeNull();
    expect(line).not.toHaveAttribute('tabindex');
    expect(line.parentElement?.closest('a, button, [tabindex]:not(main)')).toBeNull();
  }
  // Last on the page, after everything that works.
  const page = lines[0]!.parentElement!;
  expect(Array.from(page.children).slice(-3)).toEqual(lines);
});

test('under a key-id catalogue the page is all keys and the three coming lines', async () => {
  renderAsQqx();
  serve([row(1)]);
  const {container} = renderPage('provider');
  await screen.findByRole('heading', {name: '(admin-site-dashboard)', level: 1});

  // Scoped to the page's own content: the console frame carries its own top bar, sidebar
  // and footer licence line, which are not this page's copy.
  const page = container.querySelector('.admin-page')!;
  expect(untranslatedCopy([page], [
    // The fixture's own words: participant data is never keyed.
    'Consultation 1', 'consultation-1', 'adminuser', '— adminuser', 'Full consultation',
    'Also coming: Admin home, one table of the consultations you have a role in'
    + ' — not available yet (#473)',
    'Also coming: phase, participation counts, organizers, last action, and following or hiding'
    + ' a consultation — not available yet (#473)',
    'Also coming: voucher use, correct and wrong codes per consultation — not available yet (#473)',
  ])).toEqual([]);
});
test('the dashboard sits in the console frame, with no consultation sections in it', async () => {
  serve([row(1)]);
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={['/app/admin']}><App /></MemoryRouter>
    </QueryClientProvider>,
  );

  expect(await screen.findByRole('heading', {name: 'Site admin dashboard', level: 1})).toBeVisible();
  // The console's frame and page, not the participant site's header and container.
  const main = screen.getByRole('main');
  expect(main).toHaveClass('admin-shell__main');
  expect(main.querySelector(':scope > .admin-page > h1')).toHaveTextContent('Site admin dashboard');
  expect(document.querySelector('.site-header, .container')).toBeNull();
  // One crumb: the page itself.
  expect(within(screen.getByRole('navigation', {name: 'Admin breadcrumb'})).getAllByRole('listitem')
    .map((item) => item.textContent)).toEqual(['Site admin dashboard']);
  // A site-level page is about no consultation, so the sidebar lists none of its sections.
  const side = screen.getByRole('navigation', {name: 'Admin sections'});
  for (const name of ['Overview', 'Settings', 'Moderation', 'Content']) {
    expect(within(side).queryByRole('link', {name})).toBeNull();
  }
  expect(within(side).queryByRole('button', {name: 'Sections'})).toBeNull();
  // The participant side of a site-level page is the list of consultations.
  expect(screen.getByRole('link', {name: 'Participant'})).toHaveAttribute('href', '/consultations');
});

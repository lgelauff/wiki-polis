import {useSuspenseQuery} from '@tanstack/react-query';
import {Navigate, useLocation, useParams} from 'react-router-dom';
import type {ReactNode} from 'react';

import {sessionQuery} from '../../api/queries';
import {InternalLink} from '../../internal-link';
import {useMessage} from '../../i18n/messages';
import {AdminAccessBoundary} from './admin-access-boundary';
import {AdminCatalogPage} from './admin-catalog-page';
import {AdminFeaturedPage} from './admin-featured-page';
import {AdminInvitationsPage} from './admin-invitations-page';
import {AdminLifecyclePage} from './admin-lifecycle-page';
import {AdminModerationFlagsPage} from './admin-moderation-flags-page';
import {AdminModerationPeoplePage} from './admin-moderation-people-page';
import {AdminModerationQueuePage} from './admin-moderation-queue-page';
import {AdminParticipantsPage} from './admin-participants-page';
import {AdminRolesPage} from './admin-roles-page';
import {AdminSettingsPage, AdminSettingsVouchersPage} from './admin-settings-page';
import {AdminStatementsPage} from './admin-statements-page';
import {AdminTerminationPage} from './admin-termination-page';
import {useLoginHref} from '../../login-href';

function OrbitMark() {
  return (
    <svg className="brand__orbit" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.2" aria-hidden="true">
      <circle cx="12" cy="12" r="9" />
      <ellipse cx="12" cy="12" rx="9" ry="3.5" />
      <ellipse cx="12" cy="12" rx="3.5" ry="9" />
    </svg>
  );
}

function AdminHeader() {
  const msg = useMessage();
  const {data: session} = useSuspenseQuery(sessionQuery());
  const login = useLoginHref(session.links.login);
  return (
    <header className="app-header">
      <div className="app-header__inner">
        <InternalLink className="brand" href="/">
          <OrbitMark />
          <span>Wiki Polis</span>
          <span className="brand__beta">prototype</span>
        </InternalLink>
        <nav className="admin-mode" aria-label="Workspace">
          <strong><InternalLink href="/admin">Admin workspace</InternalLink></strong>
          <InternalLink href="/consultations">Participant view</InternalLink>
        </nav>
        {session.state === 'anonymous' ? (
          <InternalLink className="account-link" href={login}>Log in</InternalLink>
        ) : (
          <form method="post" action={session.links.logout} className="account-form">
            <span>{session.state === 'voucher' ? msg('base-single-consultation-account') : session.user?.username ?? 'Demo session'}</span>
            <input type="hidden" name="csrf_token" value={session.csrfToken} />
            <button type="submit">Log out</button>
          </form>
        )}
      </div>
    </header>
  );
}

function requiredConversationId(value: string | undefined): number {
  if (!value) throw new Error('Missing route parameter: conversationId');
  return Number(value);
}

function Protected({children}: {children: ReactNode}) {
  return <AdminAccessBoundary>{children}</AdminAccessBoundary>;
}

type AdminRouteKind =
  | 'catalog'
  | 'lifecycle'
  | 'moderation-featured'
  | 'moderation-flags'
  | 'moderation-people'
  | 'moderation-queue'
  | 'participants'
  | 'settings-access'
  | 'settings-basics'
  | 'settings-invitations'
  | 'settings-roles'
  | 'settings-vouchers'
  | 'statements'
  | 'termination';

function AdminRouteContent({kind}: {kind: AdminRouteKind}) {
  const {conversationId: rawConversationId} = useParams();
  const {data: session} = useSuspenseQuery(sessionQuery());
  if (kind === 'catalog') return <AdminCatalogPage csrfToken={session.csrfToken} />;

  const conversationId = requiredConversationId(rawConversationId);
  switch (kind) {
    case 'lifecycle':
      return <AdminLifecyclePage conversationId={conversationId} csrfToken={session.csrfToken} />;
    case 'settings-basics':
      return <AdminSettingsPage conversationId={conversationId} csrfToken={session.csrfToken} tab="basics" />;
    case 'settings-access':
      return <AdminSettingsPage conversationId={conversationId} csrfToken={session.csrfToken} tab="access" />;
    case 'termination':
      return <><AdminHeader /><AdminTerminationPage conversationId={conversationId} csrfToken={session.csrfToken} /></>;
    case 'statements':
      return <AdminStatementsPage conversationId={conversationId} csrfToken={session.csrfToken} />;
    case 'participants':
      return <AdminParticipantsPage conversationId={conversationId} csrfToken={session.csrfToken} />;
    case 'moderation-queue':
      return <AdminModerationQueuePage conversationId={conversationId} csrfToken={session.csrfToken} />;
    case 'moderation-flags':
      return <AdminModerationFlagsPage conversationId={conversationId} csrfToken={session.csrfToken} />;
    case 'moderation-featured':
      return <AdminFeaturedPage conversationId={conversationId} csrfToken={session.csrfToken} />;
    case 'moderation-people':
      return <AdminModerationPeoplePage conversationId={conversationId} csrfToken={session.csrfToken} />;
    case 'settings-invitations':
      return <AdminInvitationsPage conversationId={conversationId} csrfToken={session.csrfToken} />;
    case 'settings-vouchers':
      return <AdminSettingsVouchersPage conversationId={conversationId} />;
    case 'settings-roles':
      return <AdminRolesPage conversationId={conversationId} csrfToken={session.csrfToken} />;
  }
}

function AdminRoute({kind}: {kind: AdminRouteKind}) {
  return <Protected><AdminRouteContent kind={kind} /></Protected>;
}

export const AdminCatalogRoute = () => <AdminRoute kind="catalog" />;
export const AdminLifecycleRoute = () => <AdminRoute kind="lifecycle" />;
export const AdminSettingsBasicsRoute = () => <AdminRoute kind="settings-basics" />;
export const AdminSettingsAccessRoute = () => <AdminRoute kind="settings-access" />;
export const AdminSettingsInvitationsRoute = () => <AdminRoute kind="settings-invitations" />;
export const AdminSettingsVouchersRoute = () => <AdminRoute kind="settings-vouchers" />;
export const AdminSettingsRolesRoute = () => <AdminRoute kind="settings-roles" />;

/** An old admin path that now lives under a section: `<Navigate replace>` to the new one,
 *  so the links the server still builds keep working without a second copy of every path
 *  in `v2/app.py`. */
export function AdminRedirectRoute({to}: {to: (conversationId: string) => string}) {
  const {conversationId} = useParams();
  const {search, hash} = useLocation();
  if (!conversationId) throw new Error('Missing route parameter: conversationId');
  // The query string and fragment go along, as with the settings index below.
  return <Navigate replace to={{pathname: to(conversationId), search, hash}} />;
}

/** `…/settings` is the URL the lifecycle page and the sidebar still link to; Settings has
 *  tabs, so the bare path lands on Basics. `<Navigate replace>` keeps the old path out of the
 *  history: Back returns to wherever the organizer came from, not to this hop. The target is
 *  relative, so `/app/admin/…` stays in its own route group; the query string (a
 *  `?uselang=`) and the fragment go along, as they would through a server redirect. */
export function AdminSettingsIndexRoute() {
  return <AdminSectionIndexRoute firstTab="basics" />;
}

/** The bare path of a tabbed section lands on the first tab of its strip, the way
 *  `…/settings` lands on Basics: `…/moderation` on Queue (`moderationTabs`) and `…/content`
 *  on Statements (`contentTabs`). Relative, so `/app/admin/…` stays in its own group, and
 *  the query string and fragment go along. */
export function AdminSectionIndexRoute({firstTab}: {firstTab: string}) {
  const {search, hash} = useLocation();
  return <Navigate replace to={{pathname: firstTab, search, hash}} />;
}
export const AdminTerminationRoute = () => <AdminRoute kind="termination" />;
export const AdminStatementsRoute = () => <AdminRoute kind="statements" />;
export const AdminParticipantsRoute = () => <AdminRoute kind="participants" />;
export const AdminModerationQueueRoute = () => <AdminRoute kind="moderation-queue" />;
export const AdminModerationFlagsRoute = () => <AdminRoute kind="moderation-flags" />;
export const AdminModerationFeaturedRoute = () => <AdminRoute kind="moderation-featured" />;
export const AdminModerationPeopleRoute = () => <AdminRoute kind="moderation-people" />;

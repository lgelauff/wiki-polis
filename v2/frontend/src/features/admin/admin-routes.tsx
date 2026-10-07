import {useSuspenseQuery} from '@tanstack/react-query';
import {Navigate, useParams} from 'react-router-dom';
import type {ReactNode} from 'react';

import {sessionQuery} from '../../api/queries';
import {InternalLink} from '../../internal-link';
import {AdminAccessBoundary} from './admin-access-boundary';
import {AdminCatalogPage} from './admin-catalog-page';
import {AdminFeaturedPage} from './admin-featured-page';
import {AdminInvitationsPage} from './admin-invitations-page';
import {AdminLifecyclePage} from './admin-lifecycle-page';
import {AdminModerationPage} from './admin-moderation-page';
import {AdminParticipantsPage} from './admin-participants-page';
import {AdminRolesPage} from './admin-roles-page';
import {AdminSettingsPage} from './admin-settings-page';
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
            <span>{session.user?.username ?? 'Demo session'}</span>
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
  | 'featured'
  | 'invitations'
  | 'lifecycle'
  | 'moderation'
  | 'participants'
  | 'roles'
  | 'settings-access'
  | 'settings-basics'
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
    case 'featured':
      return <AdminFeaturedPage conversationId={conversationId} csrfToken={session.csrfToken} />;
    case 'participants':
      return <AdminParticipantsPage conversationId={conversationId} csrfToken={session.csrfToken} />;
    case 'moderation':
      return <AdminModerationPage conversationId={conversationId} csrfToken={session.csrfToken} />;
    case 'invitations':
      return <AdminInvitationsPage conversationId={conversationId} csrfToken={session.csrfToken} />;
    case 'roles':
      return <><AdminHeader /><AdminRolesPage conversationId={conversationId} csrfToken={session.csrfToken} /></>;
  }
}

function AdminRoute({kind}: {kind: AdminRouteKind}) {
  return <Protected><AdminRouteContent kind={kind} /></Protected>;
}

export const AdminCatalogRoute = () => <AdminRoute kind="catalog" />;
export const AdminLifecycleRoute = () => <AdminRoute kind="lifecycle" />;
export const AdminSettingsBasicsRoute = () => <AdminRoute kind="settings-basics" />;
export const AdminSettingsAccessRoute = () => <AdminRoute kind="settings-access" />;

/** `…/settings` is the URL the lifecycle page and the sidebar still link to; Settings has
 *  tabs, so the bare path lands on Basics. `<Navigate replace>` keeps the old path out of the
 *  history: Back returns to wherever the organizer came from, not to this hop. The target is
 *  relative, so `/app/admin/…` stays in its own route group. */
export const AdminSettingsIndexRoute = () => <Navigate replace to="basics" />;
export const AdminTerminationRoute = () => <AdminRoute kind="termination" />;
export const AdminStatementsRoute = () => <AdminRoute kind="statements" />;
export const AdminFeaturedRoute = () => <AdminRoute kind="featured" />;
export const AdminParticipantsRoute = () => <AdminRoute kind="participants" />;
export const AdminModerationRoute = () => <AdminRoute kind="moderation" />;
export const AdminInvitationsRoute = () => <AdminRoute kind="invitations" />;
export const AdminRolesRoute = () => <AdminRoute kind="roles" />;

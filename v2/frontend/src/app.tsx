import {Suspense} from 'react';
import {useSuspenseQuery} from '@tanstack/react-query';
import {Link, Navigate, NavLink, Route, Routes, useParams} from 'react-router-dom';

import {
  sessionQuery,
  type ConversationSpace,
} from './api/queries';
import {ResultsAccessBoundary, ResultsPage} from './features/results/results-page';
import {AdminParticipantsPage} from './features/admin/admin-participants-page';
import {AdminModerationPage} from './features/admin/admin-moderation-page';
import {AdminInvitationsPage} from './features/admin/admin-invitations-page';
import {AdminRolesPage} from './features/admin/admin-roles-page';
import {AdminLifecyclePage} from './features/admin/admin-lifecycle-page';
import {AdminSettingsPage} from './features/admin/admin-settings-page';
import {AdminTerminationPage} from './features/admin/admin-termination-page';
import {AdminStatementsPage} from './features/admin/admin-statements-page';
import {AdminFeaturedPage} from './features/admin/admin-featured-page';
import {AdminCatalogPage} from './features/admin/admin-catalog-page';
import {AdminAccessBoundary} from './features/admin/admin-access-boundary';
import {
  MissingSpaRoute,
  StrictSpaBoundary,
  useStrictSpaMode,
} from './strict-spa-mode';
import {
  ArgumentGuidancePage,
  ForkPage,
  StatementGuidancePage,
} from './features/legacy/public-pages';
import {
  ConversationAboutLegacyPage,
  ConversationOutputPage,
  ModerationLogPage,
} from './features/legacy/conversation-read-pages';
import {ParticipationEntryLegacyPage} from './features/legacy/participation-entry-page';
import {IdentityRevealLegacyPage} from './features/legacy/identity-reveal-page';
import {ConversationLanePage} from './features/legacy/conversation-lane-page';
import {ConversationWorkspacePage} from './features/legacy/conversation-workspace-page';
import {InternalLink} from './internal-link';

function OrbitMark() {
  return (
    <svg className="brand__orbit" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.2" aria-hidden="true">
      <circle cx="12" cy="12" r="9" />
      <ellipse cx="12" cy="12" rx="9" ry="3.5" />
      <ellipse cx="12" cy="12" rx="3.5" ry="9" />
    </svg>
  );
}

function Header({space, admin = false}: {space?: ConversationSpace; admin?: boolean}) {
  const {data: session} = useSuspenseQuery(sessionQuery());
  return (
    <header className="app-header">
      <div className="app-header__inner">
        <InternalLink className="brand" href="/">
          <OrbitMark />
          <span>Wiki Polis</span>
          <span className="brand__beta">prototype</span>
        </InternalLink>
        {admin ? (
          <nav className="admin-mode" aria-label="Workspace">
            <strong><Link to="/admin">Admin workspace</Link></strong>
            <Link to="/consultations">Participant view</Link>
          </nav>
        ) : (
          <nav className="space-switch" aria-label="Conversation space">
            <NavLink to="/demo" aria-current={space === 'demo' ? 'page' : undefined}>Try it out</NavLink>
            <NavLink to="/consultations" aria-current={space === 'real' ? 'page' : undefined}>Real</NavLink>
          </nav>
        )}
        {session.state === 'anonymous' ? (
          <InternalLink className="account-link" href={session.links.login}>Log in</InternalLink>
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

function ResultsRoute() {
  const {slug = ''} = useParams();
  return <ResultsAccessBoundary slug={slug}>
    <ResultsPage slug={slug} />
  </ResultsAccessBoundary>;
}

function AdminParticipantsRoute() {
  const {conversationId = ''} = useParams();
  const {data: session} = useSuspenseQuery(sessionQuery());
  return <AdminParticipantsPage
    conversationId={Number(conversationId)}
    csrfToken={session.csrfToken}
  />;
}

function AdminLifecycleRoute() {
  const {conversationId = ''} = useParams();
  const {data: session} = useSuspenseQuery(sessionQuery());
  return <AdminLifecyclePage conversationId={Number(conversationId)} csrfToken={session.csrfToken} />;
}

function AdminSettingsRoute() {
  const {conversationId = ''} = useParams();
  const {data: session} = useSuspenseQuery(sessionQuery());
  return <><Header admin /><AdminSettingsPage conversationId={Number(conversationId)} csrfToken={session.csrfToken} /></>;
}

function AdminTerminationRoute() {
  const {conversationId = ''} = useParams();
  const {data: session} = useSuspenseQuery(sessionQuery());
  return <><Header admin /><AdminTerminationPage conversationId={Number(conversationId)} csrfToken={session.csrfToken} /></>;
}

function AdminStatementsRoute() {
  const {conversationId = ''} = useParams();
  const {data: session} = useSuspenseQuery(sessionQuery());
  return <AdminStatementsPage conversationId={Number(conversationId)} csrfToken={session.csrfToken} />;
}

function AdminCatalogRoute() {
  const {data: session} = useSuspenseQuery(sessionQuery());
  return <AdminCatalogPage csrfToken={session.csrfToken} />;
}

function AdminFeaturedRoute() {
  const {conversationId = ''} = useParams();
  const {data: session} = useSuspenseQuery(sessionQuery());
  return <AdminFeaturedPage conversationId={Number(conversationId)} csrfToken={session.csrfToken} />;
}

function AdminModerationRoute() {
  const {conversationId = ''} = useParams();
  const {data: session} = useSuspenseQuery(sessionQuery());
  return <AdminModerationPage
    conversationId={Number(conversationId)}
    csrfToken={session.csrfToken}
  />;
}

function AdminInvitationsRoute() {
  const {conversationId = ''} = useParams();
  const {data: session} = useSuspenseQuery(sessionQuery());
  return <AdminInvitationsPage conversationId={Number(conversationId)} csrfToken={session.csrfToken} />;
}

function AdminRolesRoute() {
  const {conversationId = ''} = useParams();
  const {data: session} = useSuspenseQuery(sessionQuery());
  return <><Header admin /><AdminRolesPage conversationId={Number(conversationId)} csrfToken={session.csrfToken} /></>;
}

function UnmatchedRoute() {
  const {enabled} = useStrictSpaMode();
  return enabled ? <MissingSpaRoute /> : <Navigate to="/consultations" replace />;
}

export function App() {
  return (
    <StrictSpaBoundary>
      <a className="skip-link" href="#main">Skip to main content</a>
      <Suspense fallback={<p className="loading-state" role="status">Loading conversations…</p>}>
        <Routes>
          <Route path="/" element={<ForkPage />} />
          <Route path="/demo" element={<ConversationLanePage space="demo" />} />
          <Route path="/consultations" element={<ConversationLanePage space="real" />} />
          <Route path="/help/statements" element={<StatementGuidancePage />} />
          <Route path="/help/arguments" element={<ArgumentGuidancePage />} />
          <Route path="/accept/:slug" element={<ParticipationEntryLegacyPage />} />
          <Route path="/c/:slug" element={<ConversationWorkspacePage />} />
          <Route path="/c/:slug/about" element={<ConversationAboutLegacyPage />} />
          <Route path="/c/:slug/moderation-log" element={<ModerationLogPage />} />
          <Route path="/c/:slug/outputs/:outputKey" element={<ConversationOutputPage />} />
          <Route path="/c/:slug/report" element={<ResultsRoute />} />
          <Route path="/c/:slug/reveal" element={<IdentityRevealLegacyPage />} />
          <Route path="/admin" element={<AdminAccessBoundary><AdminCatalogRoute /></AdminAccessBoundary>} />
          <Route path="/admin/conversations/:conversationId" element={<AdminAccessBoundary><AdminLifecycleRoute /></AdminAccessBoundary>} />
          <Route path="/admin/conversations/:conversationId/settings" element={<AdminAccessBoundary><AdminSettingsRoute /></AdminAccessBoundary>} />
          <Route path="/admin/conversations/:conversationId/termination" element={<AdminAccessBoundary><AdminTerminationRoute /></AdminAccessBoundary>} />
          <Route path="/admin/conversations/:conversationId/statements" element={<AdminAccessBoundary><AdminStatementsRoute /></AdminAccessBoundary>} />
          <Route path="/admin/conversations/:conversationId/featured" element={<AdminAccessBoundary><AdminFeaturedRoute /></AdminAccessBoundary>} />
          <Route path="/admin/conversations/:conversationId/participants" element={<AdminAccessBoundary><AdminParticipantsRoute /></AdminAccessBoundary>} />
          <Route path="/admin/conversations/:conversationId/flags" element={<AdminAccessBoundary><AdminModerationRoute /></AdminAccessBoundary>} />
          <Route path="/admin/conversations/:conversationId/invites" element={<AdminAccessBoundary><AdminInvitationsRoute /></AdminAccessBoundary>} />
          <Route path="/admin/conversations/:conversationId/roles" element={<AdminAccessBoundary><AdminRolesRoute /></AdminAccessBoundary>} />
          <Route path="/app/parity/fork" element={<ForkPage />} />
          <Route path="/app/parity/help/statements" element={<StatementGuidancePage />} />
          <Route path="/app/parity/help/arguments" element={<ArgumentGuidancePage />} />
          <Route path="/app/parity/conversations/:slug/moderation-log" element={<ModerationLogPage />} />
          <Route path="/app/parity/conversations/:slug/outputs/:outputKey" element={<ConversationOutputPage />} />
          <Route path="/app/demo" element={<ConversationLanePage space="demo" />} />
          <Route path="/app/real" element={<ConversationLanePage space="real" />} />
          <Route path="/app/conversations/:slug/about" element={<ConversationAboutLegacyPage />} />
          <Route path="/app/conversations/:slug/join" element={<ParticipationEntryLegacyPage />} />
          <Route path="/app/conversations/:slug/explore" element={<ConversationWorkspacePage />} />
          <Route path="/app/conversations/:slug/arguments" element={<ConversationWorkspacePage />} />
          <Route path="/app/conversations/:slug/informed-voting" element={<ConversationWorkspacePage />} />
          <Route path="/app/conversations/:slug/results" element={<ResultsRoute />} />
          <Route path="/app/conversations/:slug/identity-reveal" element={<IdentityRevealLegacyPage />} />
          <Route path="/app/admin" element={<AdminAccessBoundary><AdminCatalogRoute /></AdminAccessBoundary>} />
          <Route path="/app/admin/conversations/:conversationId" element={<AdminAccessBoundary><AdminLifecycleRoute /></AdminAccessBoundary>} />
          <Route path="/app/admin/conversations/:conversationId/settings" element={<AdminAccessBoundary><AdminSettingsRoute /></AdminAccessBoundary>} />
          <Route path="/app/admin/conversations/:conversationId/termination" element={<AdminAccessBoundary><AdminTerminationRoute /></AdminAccessBoundary>} />
          <Route path="/app/admin/conversations/:conversationId/statements" element={<AdminAccessBoundary><AdminStatementsRoute /></AdminAccessBoundary>} />
          <Route path="/app/admin/conversations/:conversationId/featured" element={<AdminAccessBoundary><AdminFeaturedRoute /></AdminAccessBoundary>} />
          <Route path="/app/admin/conversations/:conversationId/participants" element={<AdminAccessBoundary><AdminParticipantsRoute /></AdminAccessBoundary>} />
          <Route path="/app/admin/conversations/:conversationId/moderation" element={<AdminAccessBoundary><AdminModerationRoute /></AdminAccessBoundary>} />
          <Route path="/app/admin/conversations/:conversationId/invitations" element={<AdminAccessBoundary><AdminInvitationsRoute /></AdminAccessBoundary>} />
          <Route path="/app/admin/conversations/:conversationId/roles" element={<AdminAccessBoundary><AdminRolesRoute /></AdminAccessBoundary>} />
          <Route path="*" element={<UnmatchedRoute />} />
        </Routes>
      </Suspense>
    </StrictSpaBoundary>
  );
}

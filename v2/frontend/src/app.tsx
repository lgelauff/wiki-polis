import {lazy, Suspense, useDeferredValue} from 'react';

import {MessageProvider} from './i18n/messages';
import {Navigate, Route, Routes, useLocation} from 'react-router-dom';

import {ForkPage} from './features/legacy/public-pages';
import {LogoutNoticeProvider} from './features/legacy/logout-notice';
import {ConversationLanePage} from './features/legacy/conversation-lane-page';
import {ConversationWorkspacePage} from './features/legacy/conversation-workspace-page';
import {
  loadAdminRoutes,
  loadConversationReadPages,
  loadGuidancePages,
  loadIdentityRevealPage,
  loadParticipationEntryPage,
  loadResultsPage,
} from './route-modules';

const ArgumentGuidancePage = lazy(() => loadGuidancePages().then((module) => ({default: module.ArgumentGuidancePage})));
const StatementGuidancePage = lazy(() => loadGuidancePages().then((module) => ({default: module.StatementGuidancePage})));
const ParticipationEntryLegacyPage = lazy(() => loadParticipationEntryPage().then((module) => ({default: module.ParticipationEntryLegacyPage})));
const IdentityRevealLegacyPage = lazy(() => loadIdentityRevealPage().then((module) => ({default: module.IdentityRevealLegacyPage})));
const ConversationAboutLegacyPage = lazy(() => loadConversationReadPages().then((module) => ({default: module.ConversationAboutLegacyPage})));
const ConversationOutputPage = lazy(() => loadConversationReadPages().then((module) => ({default: module.ConversationOutputPage})));
const ModerationLogPage = lazy(() => loadConversationReadPages().then((module) => ({default: module.ModerationLogPage})));
const ResultsRoute = lazy(() => loadResultsPage().then((module) => ({default: module.ResultsRoute})));

const AdminCatalogRoute = lazy(() => loadAdminRoutes().then((module) => ({default: module.AdminCatalogRoute})));
const AdminHomeRoute = lazy(() => loadAdminRoutes().then((module) => ({default: module.AdminHomeRoute})));
const AdminLifecycleRoute = lazy(() => loadAdminRoutes().then((module) => ({default: module.AdminLifecycleRoute})));
const AdminSettingsIndexRoute = lazy(() => loadAdminRoutes().then((module) => ({default: module.AdminSettingsIndexRoute})));
const AdminSectionIndexRoute = lazy(() => loadAdminRoutes().then((module) => ({default: module.AdminSectionIndexRoute})));
const AdminSettingsBasicsRoute = lazy(() => loadAdminRoutes().then((module) => ({default: module.AdminSettingsBasicsRoute})));
const AdminSettingsAccessRoute = lazy(() => loadAdminRoutes().then((module) => ({default: module.AdminSettingsAccessRoute})));
const AdminSettingsInvitationsRoute = lazy(() => loadAdminRoutes().then((module) => ({default: module.AdminSettingsInvitationsRoute})));
const AdminSettingsVouchersRoute = lazy(() => loadAdminRoutes().then((module) => ({default: module.AdminSettingsVouchersRoute})));
const AdminSettingsRolesRoute = lazy(() => loadAdminRoutes().then((module) => ({default: module.AdminSettingsRolesRoute})));
const AdminRedirectRoute = lazy(() => loadAdminRoutes().then((module) => ({default: module.AdminRedirectRoute})));
const AdminTerminationRoute = lazy(() => loadAdminRoutes().then((module) => ({default: module.AdminTerminationRoute})));
const AdminStatementsRoute = lazy(() => loadAdminRoutes().then((module) => ({default: module.AdminStatementsRoute})));
const AdminParticipantsRoute = lazy(() => loadAdminRoutes().then((module) => ({default: module.AdminParticipantsRoute})));
const AdminModerationQueueRoute = lazy(() => loadAdminRoutes().then((module) => ({default: module.AdminModerationQueueRoute})));
const AdminModerationFlagsRoute = lazy(() => loadAdminRoutes().then((module) => ({default: module.AdminModerationFlagsRoute})));
const AdminModerationFeaturedRoute = lazy(() => loadAdminRoutes().then((module) => ({default: module.AdminModerationFeaturedRoute})));
const AdminModerationPeopleRoute = lazy(() => loadAdminRoutes().then((module) => ({default: module.AdminModerationPeopleRoute})));

/** Where the old invites and roles paths went (#478): both pages are tabs of Settings now.
 *  One place, so the two route groups cannot drift apart. */
const settingsInvitationsPath = (conversationId: string) =>
  `/admin/conversations/${conversationId}/settings/invitations`;
const settingsRolesPath = (conversationId: string) =>
  `/admin/conversations/${conversationId}/settings/roles`;

/** Where the old flags and featured paths went (#473): both are pages of Moderation now. */
const moderationFlagsPath = (conversationId: string) =>
  `/admin/conversations/${conversationId}/moderation/flags`;
const moderationFeaturedPath = (conversationId: string) =>
  `/admin/conversations/${conversationId}/moderation/featured`;

/** Where the old statements and participants paths went (#473): both are pages of the
 *  Content section now. One place, so the two route groups cannot drift apart. */
const contentStatementsPath = (conversationId: string) =>
  `/admin/conversations/${conversationId}/content/statements`;
const contentParticipantsPath = (conversationId: string) =>
  `/admin/conversations/${conversationId}/content/participants`;

function UnmatchedRoute() {
  // The server 404s any path outside its SPA route table, so this only fires for
  // a client-side path the router does not know (e.g. under /app/*).
  return <Navigate to="/consultations" replace />;
}

function DeferredRoutes() {
  const location = useLocation();
  const deferredLocation = useDeferredValue(location);

  return (
    <Routes location={deferredLocation}>
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
      <Route path="/admin" element={<AdminHomeRoute />} />
      <Route path="/site-admin" element={<AdminCatalogRoute />} />
      <Route path="/admin/conversations/:conversationId" element={<AdminLifecycleRoute />} />
      <Route path="/admin/conversations/:conversationId/settings" element={<AdminSettingsIndexRoute />} />
      <Route path="/admin/conversations/:conversationId/settings/basics" element={<AdminSettingsBasicsRoute />} />
      <Route path="/admin/conversations/:conversationId/settings/access" element={<AdminSettingsAccessRoute />} />
      <Route path="/admin/conversations/:conversationId/settings/invitations" element={<AdminSettingsInvitationsRoute />} />
      <Route path="/admin/conversations/:conversationId/settings/vouchers" element={<AdminSettingsVouchersRoute />} />
      <Route path="/admin/conversations/:conversationId/settings/roles" element={<AdminSettingsRolesRoute />} />
      <Route path="/admin/conversations/:conversationId/termination" element={<AdminTerminationRoute />} />
      <Route path="/admin/conversations/:conversationId/content" element={<AdminSectionIndexRoute firstTab="statements" />} />
      <Route path="/admin/conversations/:conversationId/content/statements" element={<AdminStatementsRoute />} />
      <Route path="/admin/conversations/:conversationId/content/participants" element={<AdminParticipantsRoute />} />
      <Route path="/admin/conversations/:conversationId/statements" element={<AdminRedirectRoute to={contentStatementsPath} />} />
      <Route path="/admin/conversations/:conversationId/featured" element={<AdminRedirectRoute to={moderationFeaturedPath} />} />
      <Route path="/admin/conversations/:conversationId/participants" element={<AdminRedirectRoute to={contentParticipantsPath} />} />
      <Route path="/admin/conversations/:conversationId/flags" element={<AdminRedirectRoute to={moderationFlagsPath} />} />
      <Route path="/admin/conversations/:conversationId/moderation" element={<AdminSectionIndexRoute firstTab="queue" />} />
      <Route path="/admin/conversations/:conversationId/moderation/queue" element={<AdminModerationQueueRoute />} />
      <Route path="/admin/conversations/:conversationId/moderation/flags" element={<AdminModerationFlagsRoute />} />
      <Route path="/admin/conversations/:conversationId/moderation/featured" element={<AdminModerationFeaturedRoute />} />
      <Route path="/admin/conversations/:conversationId/moderation/people" element={<AdminModerationPeopleRoute />} />
      <Route path="/admin/conversations/:conversationId/invites" element={<AdminRedirectRoute to={settingsInvitationsPath} />} />
      <Route path="/admin/conversations/:conversationId/roles" element={<AdminRedirectRoute to={settingsRolesPath} />} />
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
      {/* The old dashboard address: the dashboard lives at /site-admin now (#538). */}
      <Route path="/app/admin" element={<Navigate replace to="/site-admin" />} />
      <Route path="/app/admin/conversations/:conversationId" element={<AdminLifecycleRoute />} />
      <Route path="/app/admin/conversations/:conversationId/settings" element={<AdminSettingsIndexRoute />} />
      <Route path="/app/admin/conversations/:conversationId/settings/basics" element={<AdminSettingsBasicsRoute />} />
      <Route path="/app/admin/conversations/:conversationId/settings/access" element={<AdminSettingsAccessRoute />} />
      <Route path="/app/admin/conversations/:conversationId/settings/invitations" element={<AdminSettingsInvitationsRoute />} />
      <Route path="/app/admin/conversations/:conversationId/settings/vouchers" element={<AdminSettingsVouchersRoute />} />
      <Route path="/app/admin/conversations/:conversationId/settings/roles" element={<AdminSettingsRolesRoute />} />
      <Route path="/app/admin/conversations/:conversationId/termination" element={<AdminTerminationRoute />} />
      <Route path="/app/admin/conversations/:conversationId/content" element={<AdminSectionIndexRoute firstTab="statements" />} />
      <Route path="/app/admin/conversations/:conversationId/content/statements" element={<AdminStatementsRoute />} />
      <Route path="/app/admin/conversations/:conversationId/content/participants" element={<AdminParticipantsRoute />} />
      <Route path="/app/admin/conversations/:conversationId/statements" element={<AdminRedirectRoute to={contentStatementsPath} />} />
      <Route path="/app/admin/conversations/:conversationId/featured" element={<AdminRedirectRoute to={moderationFeaturedPath} />} />
      <Route path="/app/admin/conversations/:conversationId/participants" element={<AdminRedirectRoute to={contentParticipantsPath} />} />
      <Route path="/app/admin/conversations/:conversationId/moderation" element={<AdminRedirectRoute to={moderationFlagsPath} />} />
      <Route path="/app/admin/conversations/:conversationId/moderation/queue" element={<AdminModerationQueueRoute />} />
      <Route path="/app/admin/conversations/:conversationId/moderation/flags" element={<AdminModerationFlagsRoute />} />
      <Route path="/app/admin/conversations/:conversationId/moderation/featured" element={<AdminModerationFeaturedRoute />} />
      <Route path="/app/admin/conversations/:conversationId/moderation/people" element={<AdminModerationPeopleRoute />} />
      <Route path="/app/admin/conversations/:conversationId/invitations" element={<AdminRedirectRoute to={settingsInvitationsPath} />} />
      <Route path="/app/admin/conversations/:conversationId/roles" element={<AdminRedirectRoute to={settingsRolesPath} />} />
      <Route path="*" element={<UnmatchedRoute />} />
    </Routes>
  );
}

/** Messages that render before <MessageProvider> exists.
 *
 *  The provider suspends on the session query and then waits on the catalogue fetch, so
 *  anything above it — the skip link, and the fallback shown while it suspends — cannot call
 *  msg(). The server stamps them onto <html> as data-msg-* while serving the shell, because
 *  it already knows the negotiated locale. English here is the last resort for a shell served
 *  from somewhere that does not stamp them, e.g. a bare static preview of the build. */
function bootstrapMessage(name: 'skip' | 'loading', fallback: string) {
  if (typeof document === 'undefined') return fallback;
  return document.documentElement.dataset[name === 'skip' ? 'msgSkip' : 'msgLoading'] || fallback;
}

export function App() {
  return (
    <>
      <a className="skip-link" href="#main">{bootstrapMessage('skip', 'Jump to content')}</a>
      <Suspense fallback={<p className="loading-state" role="status">{bootstrapMessage('loading', 'Loading…')}</p>}>
        {/* Inside the existing boundary on purpose: the catalogue fetch reuses this
            fallback instead of adding a second async gate in front of every route. */}
        <MessageProvider>
          <LogoutNoticeProvider>
            <DeferredRoutes />
          </LogoutNoticeProvider>
        </MessageProvider>
      </Suspense>
    </>
  );
}

import {lazy, Suspense, useDeferredValue} from 'react';
import {Navigate, Route, Routes, useLocation} from 'react-router-dom';

import {
  MissingSpaRoute,
  StrictSpaBoundary,
  useStrictSpaMode,
} from './strict-spa-mode';
import {ForkPage} from './features/legacy/public-pages';
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
const AdminLifecycleRoute = lazy(() => loadAdminRoutes().then((module) => ({default: module.AdminLifecycleRoute})));
const AdminSettingsRoute = lazy(() => loadAdminRoutes().then((module) => ({default: module.AdminSettingsRoute})));
const AdminTerminationRoute = lazy(() => loadAdminRoutes().then((module) => ({default: module.AdminTerminationRoute})));
const AdminStatementsRoute = lazy(() => loadAdminRoutes().then((module) => ({default: module.AdminStatementsRoute})));
const AdminFeaturedRoute = lazy(() => loadAdminRoutes().then((module) => ({default: module.AdminFeaturedRoute})));
const AdminParticipantsRoute = lazy(() => loadAdminRoutes().then((module) => ({default: module.AdminParticipantsRoute})));
const AdminModerationRoute = lazy(() => loadAdminRoutes().then((module) => ({default: module.AdminModerationRoute})));
const AdminInvitationsRoute = lazy(() => loadAdminRoutes().then((module) => ({default: module.AdminInvitationsRoute})));
const AdminRolesRoute = lazy(() => loadAdminRoutes().then((module) => ({default: module.AdminRolesRoute})));

function UnmatchedRoute() {
  const {enabled} = useStrictSpaMode();
  return enabled ? <MissingSpaRoute /> : <Navigate to="/consultations" replace />;
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
      <Route path="/admin" element={<AdminCatalogRoute />} />
      <Route path="/admin/conversations/:conversationId" element={<AdminLifecycleRoute />} />
      <Route path="/admin/conversations/:conversationId/settings" element={<AdminSettingsRoute />} />
      <Route path="/admin/conversations/:conversationId/termination" element={<AdminTerminationRoute />} />
      <Route path="/admin/conversations/:conversationId/statements" element={<AdminStatementsRoute />} />
      <Route path="/admin/conversations/:conversationId/featured" element={<AdminFeaturedRoute />} />
      <Route path="/admin/conversations/:conversationId/participants" element={<AdminParticipantsRoute />} />
      <Route path="/admin/conversations/:conversationId/flags" element={<AdminModerationRoute />} />
      <Route path="/admin/conversations/:conversationId/invites" element={<AdminInvitationsRoute />} />
      <Route path="/admin/conversations/:conversationId/roles" element={<AdminRolesRoute />} />
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
      <Route path="/app/admin" element={<AdminCatalogRoute />} />
      <Route path="/app/admin/conversations/:conversationId" element={<AdminLifecycleRoute />} />
      <Route path="/app/admin/conversations/:conversationId/settings" element={<AdminSettingsRoute />} />
      <Route path="/app/admin/conversations/:conversationId/termination" element={<AdminTerminationRoute />} />
      <Route path="/app/admin/conversations/:conversationId/statements" element={<AdminStatementsRoute />} />
      <Route path="/app/admin/conversations/:conversationId/featured" element={<AdminFeaturedRoute />} />
      <Route path="/app/admin/conversations/:conversationId/participants" element={<AdminParticipantsRoute />} />
      <Route path="/app/admin/conversations/:conversationId/moderation" element={<AdminModerationRoute />} />
      <Route path="/app/admin/conversations/:conversationId/invitations" element={<AdminInvitationsRoute />} />
      <Route path="/app/admin/conversations/:conversationId/roles" element={<AdminRolesRoute />} />
      <Route path="*" element={<UnmatchedRoute />} />
    </Routes>
  );
}

export function App() {
  return (
    <StrictSpaBoundary>
      <a className="skip-link" href="#main">Skip to main content</a>
      <Suspense fallback={<p className="loading-state" role="status">Loading conversations…</p>}>
        <DeferredRoutes />
      </Suspense>
    </StrictSpaBoundary>
  );
}

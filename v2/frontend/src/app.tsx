import {Suspense, useState} from 'react';
import {useMutation, useSuspenseQuery} from '@tanstack/react-query';
import {Link, Navigate, NavLink, Route, Routes, useParams} from 'react-router-dom';

import type {components} from './api/schema';
import {
  exploreStateQuery,
  putExploreVote,
  sessionQuery,
  type ConversationSpace,
} from './api/queries';
import {StatementComposer} from './features/explore/statement-composer';
import {ArgumentMappingPage} from './features/arguments/argument-mapping-page';
import {ContentFlagControl} from './features/flags/content-flag-control';
import {InformedVotingPage} from './features/informed-voting/informed-voting-page';
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
        <a className="brand" href="/">
          <OrbitMark />
          <span>Wiki Polis</span>
          <span className="brand__beta">prototype</span>
        </a>
        {admin ? (
          <nav className="admin-mode" aria-label="Workspace">
            <strong><Link to="/app/admin">Admin workspace</Link></strong>
            <Link to="/app/real">Participant view</Link>
          </nav>
        ) : (
          <nav className="space-switch" aria-label="Conversation space">
            <NavLink to="/app/demo" aria-current={space === 'demo' ? 'page' : undefined}>Try it out</NavLink>
            <NavLink to="/app/real" aria-current={space === 'real' ? 'page' : undefined}>Real</NavLink>
          </nav>
        )}
        {session.state === 'anonymous' ? (
          <a className="account-link" href={session.links.login}>Log in</a>
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

type ExploreChoice = components['schemas']['ExploreVoteRequest']['choice'];
type ExploreVoteRequest = components['schemas']['ExploreVoteRequest'];
type PassReason = NonNullable<ExploreVoteRequest['passReason']>;

function ExploreVoteButtons({onVote, disabled}: {
  onVote: (choice: ExploreChoice) => void;
  disabled: boolean;
}) {
  return (
    <div className="explore-choices" aria-label="Your position">
      <button type="button" data-choice="agree" disabled={disabled} onClick={() => onVote('agree')}>
        <span className="choice-dot choice-dot--agree" />Agree
      </button>
      <button type="button" data-choice="pass" disabled={disabled} onClick={() => onVote('pass')}>
        <span className="choice-dot choice-dot--pass" />Pass
      </button>
      <button type="button" data-choice="disagree" disabled={disabled} onClick={() => onVote('disagree')}>
        <span className="choice-dot choice-dot--disagree" />Disagree
      </button>
    </div>
  );
}

function PassReasonControl({selected, onSelect, disabled}: {
  selected: PassReason | null;
  onSelect: (reason: PassReason) => void;
  disabled: boolean;
}) {
  return (
    <fieldset className="pass-reason">
      <legend>Why did you pass?</legend>
      <p>This stays within Wiki-Polis and helps distinguish uncertainty from unclear wording.</p>
      <div className="pass-reason__choices">
        <button
          type="button"
          aria-pressed={selected === 'unsure'}
          disabled={disabled}
          onClick={() => onSelect('unsure')}
        >
          I’m unsure
        </button>
        <button
          type="button"
          aria-pressed={selected === 'confusing'}
          disabled={disabled}
          onClick={() => onSelect('confusing')}
        >
          The wording is confusing
        </button>
      </div>
    </fieldset>
  );
}

function ExplorePage() {
  const {slug = ''} = useParams();
  const {data: session} = useSuspenseQuery(sessionQuery());
  const {data, refetch, isFetching} = useSuspenseQuery(exploreStateQuery(slug));
  const [receipt, setReceipt] = useState<components['schemas']['ExploreVoteReceipt'] | null>(null);
  const [composerMode, setComposerMode] = useState<'derivative' | 'new' | null>(null);
  const vote = useMutation({
    mutationFn: (request: ExploreVoteRequest) => {
      if (!data.currentStatement) throw new Error('There is no statement to vote on.');
      return putExploreVote(
        slug, data.currentStatement.id, request, session.csrfToken,
      );
    },
    onMutate: () => setComposerMode(null),
    onSuccess: setReceipt,
  });

  async function nextStatement() {
    setReceipt(null);
    setComposerMode(null);
    await refetch();
  }

  return (
    <>
      <Header />
      <main className="explore-shell" id="main">
        <header className="explore-heading">
          <div>
            <p className="eyebrow">Explore · private vote</p>
            <h1>{data.title}</h1>
          </div>
          <nav className="activity-nav" aria-label="Conversation activity">
            <span aria-current="page">Explore</span>
            {data.links.arguments && <Link to={data.links.arguments}>Arguments</Link>}
            <Link to={`/app/conversations/${slug}/about`}>About</Link>
          </nav>
        </header>

        <div className="explore-progress">
          <div><strong>{data.progress.completed}</strong> of {data.progress.total} statements covered</div>
          <progress value={data.progress.completed} max={Math.max(1, data.progress.total)}>
            {data.progress.completed} of {data.progress.total}
          </progress>
        </div>

        {data.progress.allDone ? (
          <section className="explore-complete" role="status">
            <p className="eyebrow">Queue complete</p>
            <h2>You’ve covered every available statement.</h2>
            <p>Your votes are recorded as <code>{data.pseudonym}</code>. New statements may appear while Explore remains open.</p>
            <button type="button" className="explore-refresh" onClick={() => refetch()} disabled={isFetching}>
              {isFetching ? 'Checking…' : 'Check for new statements'}
            </button>
            {data.newStatement.unlocked && composerMode !== 'new' && (
              <button type="button" className="composer-link" onClick={() => setComposerMode('new')}>
                Add a new statement
              </button>
            )}
            {composerMode === 'new' && (
              <StatementComposer
                slug={slug}
                csrfToken={session.csrfToken}
                onCancel={() => setComposerMode(null)}
                onCreated={() => nextStatement()}
              />
            )}
          </section>
        ) : data.currentStatement && (
          <section className={`explore-card${receipt ? ' explore-card--voted' : ''}`}>
            <div className="explore-card__meta">
              <span>{data.currentStatement.isMeta ? 'Process' : data.currentStatement.isSeed ? 'Starting statement' : 'Community statement'}</span>
              <span className="explore-card__tools">
                <span>Statement {data.progress.completed + 1}</span>
                <ContentFlagControl
                  slug={slug}
                  csrfToken={session.csrfToken}
                  target={{contentType: 'statement', targetId: data.currentStatement.id}}
                  targetLabel={data.currentStatement.text}
                />
              </span>
            </div>
            <p className="explore-statement">{data.currentStatement.text}</p>
            {receipt ? (
              <div className="vote-receipt" role="status">
                <p>You voted <strong>{receipt.choice}</strong>.</p>
                <ExploreVoteButtons onVote={(choice) => vote.mutate({choice})} disabled={vote.isPending} />
                {receipt.choice === 'pass' && (
                  <PassReasonControl
                    selected={receipt.passReason}
                    disabled={vote.isPending}
                    onSelect={(passReason) => vote.mutate({choice: 'pass', passReason})}
                  />
                )}
                <div className="post-vote-actions">
                  <button type="button" className="next-statement" onClick={nextStatement} disabled={isFetching}>
                    {isFetching ? 'Loading…' : 'Next statement'}
                  </button>
                  <button type="button" className="composer-link" onClick={() => setComposerMode('derivative')}>
                    Suggest clearer wording
                  </button>
                  {data.newStatement.unlocked && (
                    <button type="button" className="composer-link" onClick={() => setComposerMode('new')}>
                      Add a new statement
                    </button>
                  )}
                </div>
                {composerMode && (
                  <StatementComposer
                    key={`${composerMode}-${data.currentStatement.id}`}
                    slug={slug}
                    csrfToken={session.csrfToken}
                    {...(composerMode === 'derivative'
                      ? {parentStatement: data.currentStatement}
                      : {})}
                    onCancel={() => setComposerMode(null)}
                    onCreated={() => nextStatement()}
                  />
                )}
              </div>
            ) : (
              <ExploreVoteButtons onVote={(choice) => vote.mutate({choice})} disabled={vote.isPending} />
            )}
            {vote.error && <p className="command-error" role="alert">{vote.error.message}</p>}
          </section>
        )}

        <footer className="explore-footer">
          <span>Participating as <code>{data.pseudonym}</code></span>
          <a href={data.links.conversation}>Open legacy conversation view</a>
        </footer>
      </main>
    </>
  );
}

function ArgumentMappingRoute() {
  const {slug = ''} = useParams();
  const {data: session} = useSuspenseQuery(sessionQuery());
  return (
    <>
      <Header />
      <ArgumentMappingPage slug={slug} csrfToken={session.csrfToken} />
    </>
  );
}

function InformedVotingRoute() {
  const {slug = ''} = useParams();
  const {data: session} = useSuspenseQuery(sessionQuery());
  return (
    <>
      <Header />
      <InformedVotingPage slug={slug} csrfToken={session.csrfToken} />
    </>
  );
}

function ResultsRoute() {
  const {slug = ''} = useParams();
  return <ResultsAccessBoundary slug={slug}>
    <ResultsPage slug={slug} preliminaryHeader={<Header />} />
  </ResultsAccessBoundary>;
}

function AdminParticipantsRoute() {
  const {conversationId = ''} = useParams();
  const {data: session} = useSuspenseQuery(sessionQuery());
  return (
    <>
      <Header admin />
      <AdminParticipantsPage
        conversationId={Number(conversationId)}
        csrfToken={session.csrfToken}
      />
    </>
  );
}

function AdminLifecycleRoute() {
  const {conversationId = ''} = useParams();
  const {data: session} = useSuspenseQuery(sessionQuery());
  return <><Header admin /><AdminLifecyclePage conversationId={Number(conversationId)} csrfToken={session.csrfToken} /></>;
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
  return <><Header admin /><AdminStatementsPage conversationId={Number(conversationId)} csrfToken={session.csrfToken} /></>;
}

function AdminCatalogRoute() {
  const {data: session} = useSuspenseQuery(sessionQuery());
  return <><Header admin /><AdminCatalogPage csrfToken={session.csrfToken} /></>;
}

function AdminFeaturedRoute() {
  const {conversationId = ''} = useParams();
  const {data: session} = useSuspenseQuery(sessionQuery());
  return <><Header admin /><AdminFeaturedPage conversationId={Number(conversationId)} csrfToken={session.csrfToken} /></>;
}

function AdminModerationRoute() {
  const {conversationId = ''} = useParams();
  const {data: session} = useSuspenseQuery(sessionQuery());
  return (
    <>
      <Header admin />
      <AdminModerationPage
        conversationId={Number(conversationId)}
        csrfToken={session.csrfToken}
      />
    </>
  );
}

function AdminInvitationsRoute() {
  const {conversationId = ''} = useParams();
  const {data: session} = useSuspenseQuery(sessionQuery());
  return (
    <>
      <Header admin />
      <AdminInvitationsPage conversationId={Number(conversationId)} csrfToken={session.csrfToken} />
    </>
  );
}

function AdminRolesRoute() {
  const {conversationId = ''} = useParams();
  const {data: session} = useSuspenseQuery(sessionQuery());
  return <><Header admin /><AdminRolesPage conversationId={Number(conversationId)} csrfToken={session.csrfToken} /></>;
}

function UnmatchedRoute() {
  const {enabled} = useStrictSpaMode();
  return enabled ? <MissingSpaRoute /> : <Navigate to="/app/real" replace />;
}

export function App() {
  return (
    <StrictSpaBoundary>
      <a className="skip-link" href="#main">Skip to main content</a>
      <Suspense fallback={<p className="loading-state" role="status">Loading conversations…</p>}>
        <Routes>
          <Route path="/app/parity/fork" element={<ForkPage />} />
          <Route path="/app/parity/help/statements" element={<StatementGuidancePage />} />
          <Route path="/app/parity/help/arguments" element={<ArgumentGuidancePage />} />
          <Route path="/app/parity/conversations/:slug/moderation-log" element={<ModerationLogPage />} />
          <Route path="/app/parity/conversations/:slug/outputs/:outputKey" element={<ConversationOutputPage />} />
          <Route path="/app/demo" element={<ConversationLanePage space="demo" />} />
          <Route path="/app/real" element={<ConversationLanePage space="real" />} />
          <Route path="/app/conversations/:slug/about" element={<ConversationAboutLegacyPage />} />
          <Route path="/app/conversations/:slug/join" element={<ParticipationEntryLegacyPage />} />
          <Route path="/app/conversations/:slug/explore" element={<ExplorePage />} />
          <Route path="/app/conversations/:slug/arguments" element={<ArgumentMappingRoute />} />
          <Route path="/app/conversations/:slug/informed-voting" element={<InformedVotingRoute />} />
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
      </Suspense>
    </StrictSpaBoundary>
  );
}

import {Suspense, useState, type CSSProperties, type FormEvent} from 'react';
import {useMutation, useSuspenseQuery} from '@tanstack/react-query';
import {Link, Navigate, NavLink, Route, Routes, useParams} from 'react-router-dom';

import type {components} from './api/schema';
import {
  createParticipation,
  createIdentityReveal,
  conversationAboutQuery,
  conversationLaneQuery,
  exploreStateQuery,
  identityRevealQuery,
  pseudonymSuggestionsQuery,
  putExploreVote,
  sessionQuery,
  type ConversationSpace,
} from './api/queries';
import {StatementComposer} from './features/explore/statement-composer';
import {ArgumentMappingPage} from './features/arguments/argument-mapping-page';
import {ContentFlagControl} from './features/flags/content-flag-control';
import {InformedVotingPage} from './features/informed-voting/informed-voting-page';
import {ResultsPage} from './features/results/results-page';
import {AdminParticipantsPage} from './features/admin/admin-participants-page';
import {AdminModerationPage} from './features/admin/admin-moderation-page';
import {AdminInvitationsPage} from './features/admin/admin-invitations-page';
import {AdminRolesPage} from './features/admin/admin-roles-page';
import {AdminLifecyclePage} from './features/admin/admin-lifecycle-page';

type ConversationCard = components['schemas']['ConversationCard'];
type ConversationGroups = components['schemas']['ConversationGroups'];
type ConversationAbout = components['schemas']['ConversationAbout'];

const groupDefinitions: ReadonlyArray<{
  key: keyof ConversationGroups;
  label: string;
  state: ConversationCard['participantState'];
}> = [
  {key: 'needsAttention', label: 'Needs attention', state: 'needs_attention'},
  {key: 'caughtUp', label: 'Caught up', state: 'caught_up'},
  {key: 'inactive', label: 'Waiting', state: 'inactive'},
  {key: 'available', label: 'Open to you', state: null},
  {key: 'archived', label: 'Closed', state: 'archived'},
  {key: 'moderating', label: 'You moderate', state: null},
];

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
            <strong>Admin workspace</strong>
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

function phaseLabel(conversation: ConversationCard): string {
  const labels: Record<string, string> = {
    submission: 'Explore',
    argument_mapping: 'Arguments',
    informed_voting: 'Informed vote',
    public_results: 'Report',
    preparation: 'Preparing',
    cleanup: 'Reviewing',
    cleanup_window: 'Reviewing',
    closed: 'Closed',
  };
  const phase = conversation.phases.at(-1);
  return phase ? labels[phase] ?? phase.replaceAll('_', ' ') : 'Preparing';
}

function deadlineLabel(transition: ConversationCard['scheduledTransition']): string | null {
  if (!transition) return null;
  const date = new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(transition.at));
  return `${transition.targetLabel} ${date}`;
}

function ConversationRow({conversation, index}: {conversation: ConversationCard; index: number}) {
  const state = conversation.participantState ?? (
    conversation.relationship === 'available' ? 'needs_attention' : 'inactive'
  );
  const action = conversation.capabilities.join ? 'Join' : (
    conversation.capabilities.participate ? 'Continue' : 'View'
  );
  const deadline = deadlineLabel(conversation.scheduledTransition);
  return (
    <li className="conversation-row" data-state={state} style={{'--row-index': index} as CSSProperties}>
      <span className="phase-mark">{phaseLabel(conversation)}</span>
      <div className="conversation-row__body">
        <a className="conversation-row__title" href={conversation.links.self}>{conversation.title}</a>
        <div className="conversation-row__meta">
          {conversation.pseudonym && <span>as <code>{conversation.pseudonym}</code></span>}
          {conversation.statementsRemaining !== null && conversation.statementsRemaining > 0 && (
            <span><code>{conversation.statementsRemaining}</code> statements left</span>
          )}
          {deadline && <span>Next: {deadline}</span>}
          {conversation.outputs.some((output) => output.ready) && (
            <span><code>{conversation.outputs.filter((output) => output.ready).length}</code> outputs ready</span>
          )}
          <Link to={`/app/conversations/${conversation.slug}/about`}>About</Link>
          {conversation.links.informedVoting && (
            <Link to={conversation.links.informedVoting}>Informed vote</Link>
          )}
          {conversation.links.results && (
            <Link to={conversation.links.results}>Results</Link>
          )}
          {conversation.links.identityReveal && (
            <Link to={conversation.links.identityReveal}>Identity reveal</Link>
          )}
        </div>
      </div>
      {conversation.capabilities.join ? (
        <Link className="conversation-row__action" to={`/app/conversations/${conversation.slug}/join`}>{action}</Link>
      ) : conversation.links.explore ? (
        <Link className="conversation-row__action" to={conversation.links.explore}>{action}</Link>
      ) : (
        <a className="conversation-row__action" href={conversation.links.self}>{action}</a>
      )}
    </li>
  );
}

function Metric({value, label}: {value: number | null; label: string}) {
  return (
    <div className="record-metric">
      <strong>{value ?? '—'}</strong>
      <span>{label}</span>
    </div>
  );
}

function RichText({html, className}: {html: string | null; className?: string}) {
  if (!html) return null;
  return <div className={className} dangerouslySetInnerHTML={{__html: html}} />;
}

function PersonalRecord({personal}: {personal: NonNullable<ConversationAbout['personal']>}) {
  return (
    <section className="record-section" aria-labelledby="personal-record-heading">
      <div className="record-section__number">03</div>
      <div>
        <h2 id="personal-record-heading">Your contribution</h2>
        <dl className="contribution-list">
          <div><dt>Statements suggested</dt><dd>{personal.statementsSuggested}</dd></div>
          <div><dt>Statement votes</dt><dd>{personal.statementVotesAvailable ? personal.statementVotes : '—'}</dd></div>
          <div><dt>Arguments added</dt><dd>{personal.argumentsAdded}</dd></div>
          <div><dt>Arguments rated</dt><dd>{personal.argumentsRated}</dd></div>
        </dl>
        {!personal.statementVotesAvailable && (
          <p className="record-note">Your statement-vote count is temporarily unavailable.</p>
        )}
      </div>
    </section>
  );
}

function ConversationAboutPage() {
  const {slug = ''} = useParams();
  const {data} = useSuspenseQuery(conversationAboutQuery(slug));
  const transition = deadlineLabel(data.scheduledTransition);

  return (
    <>
      <Header />
      <main className="record-shell" id="main">
        <nav className="record-breadcrumb" aria-label="Breadcrumb">
          <Link to="/app/real">Conversations</Link><span>/</span><span>About</span>
        </nav>
        <header className="record-title">
          <div>
            <p className="eyebrow">Conversation record</p>
            <h1>{data.title}</h1>
          </div>
          <div className="record-stamp" data-status={data.status}>
            <span>{data.status}</span>
            <strong>{data.phases.map((phase) => phase.label).join(' + ')}</strong>
          </div>
        </header>

        <RichText html={data.descriptionHtml} className="record-prose record-prose--lead" />

        <section className="record-section" aria-labelledby="standing-heading">
          <div className="record-section__number">01</div>
          <div>
            <h2 id="standing-heading">Where it stands</h2>
            <dl className="record-facts">
              <div><dt>Status</dt><dd>{data.status}</dd></div>
              <div><dt>Current phase</dt><dd>{data.phases.map((phase) => phase.label).join(', ')}</dd></div>
              {transition && <div><dt>Next transition</dt><dd>{transition}</dd></div>}
              {data.pseudonym && <div><dt>Your pseudonym</dt><dd><code>{data.pseudonym}</code></dd></div>}
            </dl>
          </div>
        </section>

        <section className="record-section" aria-labelledby="statistics-heading">
          <div className="record-section__number">02</div>
          <div>
            <h2 id="statistics-heading">Conversation statistics</h2>
            <div className="record-metrics">
              <Metric value={data.statistics.participants} label="participants" />
              <Metric value={data.statistics.statementVotes} label="statement votes" />
              <Metric value={data.statistics.statements} label="statements" />
              <Metric value={data.statistics.arguments} label="arguments" />
              <Metric value={data.statistics.argumentContributors} label="argument contributors" />
            </div>
            {data.statistics.participants === null && (
              <p className="record-note">Live Polis totals are temporarily unavailable. Local argument totals remain current.</p>
            )}
          </div>
        </section>

        {data.personal && <PersonalRecord personal={data.personal} />}

        <section className="record-section" aria-labelledby="outputs-heading">
          <div className="record-section__number">{data.personal ? '04' : '03'}</div>
          <div>
            <h2 id="outputs-heading">Published outputs</h2>
            <ul className="output-ledger">
              {data.outputs.map((output) => (
                <li key={output.key}>
                  <span>{output.label}</span>
                  {output.ready && output.href
                    ? <a href={output.href}>Open <span aria-hidden="true">↗</span></a>
                    : <span className="output-ledger__pending">Pending</span>}
                </li>
              ))}
            </ul>
          </div>
        </section>

        <RichText html={data.outroHtml} className="record-prose record-prose--outro" />
        <footer className="record-actions">
          <a className="record-actions__primary" href={data.links.conversation}>
            {data.capabilities.participate ? 'Continue participating' : 'View conversation'}
          </a>
          <a href={data.moderation.href}>Moderation log ({data.moderation.eventCount})</a>
        </footer>
      </main>
    </>
  );
}

function revealDate(value: string): string {
  return new Intl.DateTimeFormat(undefined, {dateStyle: 'long'}).format(
    new Date(value),
  );
}

function IdentityRevealPage() {
  const {slug = ''} = useParams();
  const {data: session} = useSuspenseQuery(sessionQuery());
  const {data: initialData} = useSuspenseQuery(identityRevealQuery(slug));
  const [confirmed, setConfirmed] = useState(false);
  const mutation = useMutation({
    mutationFn: () => createIdentityReveal(slug, session.csrfToken),
  });
  const data = mutation.data ?? initialData;

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (confirmed) mutation.mutate();
  }

  return (
    <>
      <Header />
      <main className="reveal-shell" id="main">
        <nav className="record-breadcrumb" aria-label="Breadcrumb">
          <Link to="/app/real">Conversations</Link><span>/</span>
          <Link to={data.links.about}>{data.title}</Link><span>/</span>
          <span>Identity reveal</span>
        </nav>
        <header className="reveal-title">
          <p className="eyebrow">Optional public identity link</p>
          <h1>
            {data.state === 'revealed' ? 'Identity linked' :
              data.state === 'expired' ? 'Reveal window closed' :
                data.state === 'pending' ? 'Reveal window not yet open' :
                  'Choose whether to link your identity'}
          </h1>
          <p>This choice affects only your participation in <strong>{data.title}</strong>.</p>
        </header>

        <ol className="reveal-timeline" aria-label="Identity reveal timeline">
          <li><time dateTime={data.timeline.closedAt}>{revealDate(data.timeline.closedAt)}</time><span>Conversation closed</span></li>
          <li><time dateTime={data.timeline.opensAt}>{revealDate(data.timeline.opensAt)}</time><span>Optional link opens</span></li>
          <li><time dateTime={data.timeline.closesAt}>{revealDate(data.timeline.closesAt)}</time><span>Link window closes</span></li>
        </ol>

        <section className="reveal-decision" aria-live="polite">
          {data.state === 'revealed' ? (
            <>
              <p className="eyebrow">Permanent public link</p>
              <h2><code>{data.pseudonym}</code> ↔ <strong>{data.publicUsername}</strong></h2>
              <p>This public association is permanent and is not removed by the platform.</p>
            </>
          ) : data.state === 'expired' ? (
            <>
              <h2>Your participation remains pseudonymous.</h2>
              <p>The optional window has closed. Your Wikimedia username can no longer be linked through this workflow.</p>
            </>
          ) : data.state === 'pending' ? (
            <>
              <h2>Nothing to decide yet.</h2>
              <p>The optional window opens on <strong>{revealDate(data.timeline.opensAt)}</strong>. Your participation remains under <code>{data.pseudonym}</code>.</p>
            </>
          ) : (
            <form onSubmit={submit}>
              <h2>Link <code>{data.pseudonym}</code> to {data.wikimediaUsername}?</h2>
              <p>Publishing this link identifies which pseudonym you used in this conversation. Other conversation pseudonyms are unaffected.</p>
              <div className="reveal-warning">
                <strong>Irreversible</strong>
                <p>You cannot undo this link or re-anonymise this participation after confirming.</p>
              </div>
              <label className="reveal-confirm">
                <input
                  type="checkbox"
                  checked={confirmed}
                  onChange={(event) => setConfirmed(event.target.checked)}
                />
                <span>I understand that <strong>{data.wikimediaUsername}</strong> will be permanently associated with <code>{data.pseudonym}</code>.</span>
              </label>
              {mutation.error && <p className="command-error" role="alert">{mutation.error.message}</p>}
              <button className="reveal-submit" type="submit" disabled={!confirmed || mutation.isPending}>
                {mutation.isPending ? 'Linking…' : 'Permanently link my identity'}
              </button>
            </form>
          )}
        </section>
        <footer className="reveal-footer">
          <Link to={data.links.about}>Back to conversation record</Link>
          <a href={data.links.conversation}>Open legacy conversation view</a>
        </footer>
      </main>
    </>
  );
}

function JoinForm({slug, csrfToken, emailable}: {
  slug: string;
  csrfToken: string;
  emailable: boolean;
}) {
  const {data} = useSuspenseQuery(pseudonymSuggestionsQuery(slug));
  const [pseudonym, setPseudonym] = useState(data.pseudonyms[0] ?? '');
  const [notifyEmail, setNotifyEmail] = useState(false);
  const [notifyTalkPage, setNotifyTalkPage] = useState(false);
  const mutation = useMutation({
    mutationFn: () => createParticipation(slug, {
      pseudonym,
      notifyEmail,
      notifyTalkPage,
    }, csrfToken),
  });

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    mutation.mutate();
  }

  if (mutation.data) {
    return (
      <div className="join-success" role="status">
        <p className="eyebrow">You're in</p>
        <h2>You’ll participate as <code>{mutation.data.pseudonym}</code>.</h2>
        <a className="record-actions__primary" href={mutation.data.links.conversation}>Enter the conversation</a>
      </div>
    );
  }

  return (
    <form className="join-form" onSubmit={submit}>
      <fieldset>
        <legend>Choose your pseudonym</legend>
        <p>Your contributions use this name throughout the conversation.</p>
        <div className="pseudonym-options">
          {data.pseudonyms.map((suggestion) => (
            <label key={suggestion}>
              <input
                type="radio"
                name="pseudonym"
                value={suggestion}
                checked={pseudonym === suggestion}
                onChange={() => setPseudonym(suggestion)}
              />
              <code>{suggestion}</code>
            </label>
          ))}
        </div>
      </fieldset>
      <fieldset>
        <legend>Updates</legend>
        {emailable && (
          <label className="join-check">
            <input type="checkbox" checked={notifyEmail} onChange={(event) => setNotifyEmail(event.target.checked)} />
            Email me when this conversation needs my attention
          </label>
        )}
        <label className="join-check">
          <input type="checkbox" checked={notifyTalkPage} onChange={(event) => setNotifyTalkPage(event.target.checked)} />
          Notify me on my Wikimedia talk page
        </label>
      </fieldset>
      {mutation.error && (
        <p className="command-error" role="alert">{mutation.error.message}</p>
      )}
      <button className="join-submit" type="submit" disabled={mutation.isPending || !pseudonym}>
        {mutation.isPending ? 'Joining…' : 'Join conversation'}
      </button>
      <p className="record-note">Joining records your chosen pseudonym and notification preferences. Your private identity is not shown to other participants.</p>
    </form>
  );
}

function ConversationJoinPage() {
  const {slug = ''} = useParams();
  const {data: session} = useSuspenseQuery(sessionQuery());
  const {data: conversation} = useSuspenseQuery(conversationAboutQuery(slug));

  return (
    <>
      <Header />
      <main className="join-shell" id="main">
        <nav className="record-breadcrumb" aria-label="Breadcrumb">
          <Link to="/app/real">Conversations</Link><span>/</span><span>Join</span>
        </nav>
        <header className="join-title">
          <p className="eyebrow">Join a conversation</p>
          <h1>{conversation.title}</h1>
          <RichText html={conversation.descriptionHtml} className="record-prose" />
        </header>
        {session.state === 'authenticated' ? (
          <JoinForm
            slug={slug}
            csrfToken={session.csrfToken}
            emailable={Boolean(session.user?.emailable)}
          />
        ) : (
          <div className="join-login">
            <h2>Log in to participate</h2>
            <p>A Wikimedia account is required for real conversations.</p>
            <a className="record-actions__primary" href={session.links.login}>Log in</a>
          </div>
        )}
      </main>
    </>
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
  return (
    <>
      <Header />
      <ResultsPage slug={slug} />
    </>
  );
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

function ConversationGroup({definition, conversations, primary}: {
  definition: (typeof groupDefinitions)[number];
  conversations: ConversationCard[];
  primary: boolean;
}) {
  if (conversations.length === 0) return null;
  const headingId = `group-${definition.key}`;
  return (
    <section className={`lane-group${primary ? ' lane-group--primary' : ''}`} aria-labelledby={headingId}>
      <div className="lane-group__heading">
        <h2 id={headingId}>{definition.label}</h2>
        <span>{conversations.length}</span>
      </div>
      <ul className="conversation-ledger">
        {conversations.map((conversation, index) => (
          <ConversationRow key={conversation.slug} conversation={conversation} index={index} />
        ))}
      </ul>
    </section>
  );
}

function ConversationLanePage() {
  const {space: rawSpace} = useParams();
  const space: ConversationSpace = rawSpace === 'demo' ? 'demo' : 'real';
  const {data} = useSuspenseQuery(conversationLaneQuery(space));
  const attentionCount = data.groups.needsAttention.length;
  const isEmpty = groupDefinitions.every(({key}) => data.groups[key].length === 0);

  return (
    <>
      <Header space={space} />
      <main className="lane-shell" id="main">
        <div className="lane-intro">
          <div>
            <p className="eyebrow">{space === 'demo' ? 'Practice space' : 'Your deliberation record'}</p>
            <h1>{space === 'demo' ? 'Try the conversation.' : 'See where you stand.'}</h1>
            <p className="lane-intro__copy">
              {space === 'demo'
                ? 'Explore the full process with demonstration conversations. Your actions stay in this practice space.'
                : 'Pick up the conversations that need you now. Everything else stays here as a record you can return to.'}
            </p>
          </div>
          {data.authenticated && (
            <div className="attention-count" aria-label={`${attentionCount} conversations need attention`}>
              <strong>{attentionCount}</strong>
              <span>{attentionCount === 1 ? 'conversation needs you' : 'conversations need you'}</span>
            </div>
          )}
        </div>
        {isEmpty ? (
          <p className="empty-ledger">No conversations are available in this space right now.</p>
        ) : groupDefinitions.map((definition, index) => (
          <ConversationGroup
            key={definition.key}
            definition={definition}
            conversations={data.groups[definition.key]}
            primary={index === 0}
          />
        ))}
      </main>
    </>
  );
}

export function App() {
  return (
    <>
      <a className="skip-link" href="#main">Skip to main content</a>
      <Suspense fallback={<p className="loading-state" role="status">Loading conversations…</p>}>
        <Routes>
          <Route path="/app/:space" element={<ConversationLanePage />} />
          <Route path="/app/conversations/:slug/about" element={<ConversationAboutPage />} />
          <Route path="/app/conversations/:slug/join" element={<ConversationJoinPage />} />
          <Route path="/app/conversations/:slug/explore" element={<ExplorePage />} />
          <Route path="/app/conversations/:slug/arguments" element={<ArgumentMappingRoute />} />
          <Route path="/app/conversations/:slug/informed-voting" element={<InformedVotingRoute />} />
          <Route path="/app/conversations/:slug/results" element={<ResultsRoute />} />
          <Route path="/app/conversations/:slug/identity-reveal" element={<IdentityRevealPage />} />
          <Route path="/app/admin/conversations/:conversationId" element={<AdminLifecycleRoute />} />
          <Route path="/app/admin/conversations/:conversationId/participants" element={<AdminParticipantsRoute />} />
          <Route path="/app/admin/conversations/:conversationId/moderation" element={<AdminModerationRoute />} />
          <Route path="/app/admin/conversations/:conversationId/invitations" element={<AdminInvitationsRoute />} />
          <Route path="/app/admin/conversations/:conversationId/roles" element={<AdminRolesRoute />} />
          <Route path="*" element={<Navigate to="/app/real" replace />} />
        </Routes>
      </Suspense>
    </>
  );
}

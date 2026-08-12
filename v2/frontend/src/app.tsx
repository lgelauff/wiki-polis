import {Suspense, type CSSProperties} from 'react';
import {useSuspenseQuery} from '@tanstack/react-query';
import {Link, Navigate, NavLink, Route, Routes, useParams} from 'react-router-dom';

import type {components} from './api/schema';
import {
  conversationAboutQuery,
  conversationLaneQuery,
  sessionQuery,
  type ConversationSpace,
} from './api/queries';

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

function Header({space}: {space?: ConversationSpace}) {
  const {data: session} = useSuspenseQuery(sessionQuery());
  return (
    <header className="app-header">
      <div className="app-header__inner">
        <a className="brand" href="/">
          <OrbitMark />
          <span>Wiki Polis</span>
          <span className="brand__beta">prototype</span>
        </a>
        <nav className="space-switch" aria-label="Conversation space">
          <NavLink to="/app/demo" aria-current={space === 'demo' ? 'page' : undefined}>Try it out</NavLink>
          <NavLink to="/app/real" aria-current={space === 'real' ? 'page' : undefined}>Real</NavLink>
        </nav>
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
        </div>
      </div>
      <a className="conversation-row__action" href={conversation.links.self}>{action}</a>
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
          <Route path="*" element={<Navigate to="/app/real" replace />} />
        </Routes>
      </Suspense>
    </>
  );
}

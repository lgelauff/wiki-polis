import {useEffect, useRef, useState} from 'react';
import {useSuspenseQuery} from '@tanstack/react-query';

import type {components} from '../../api/schema';
import {
  conversationLaneQuery,
  sessionQuery,
  type ConversationSpace,
} from '../../api/queries';
import {LegacyShell} from './legacy-shell';
import {InternalLink} from '../../internal-link';
import {ConversationFlow} from './conversation-flow';

type ConversationCard = components['schemas']['ConversationCard'];
type ConversationOutput = components['schemas']['ConversationOutput'];

const monthNames = [
  'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
] as const;

function archivedMonth(value: string): string {
  const date = new Date(value);
  return `${monthNames[date.getUTCMonth()]} ${date.getUTCFullYear()}`;
}

function timelinePosition(phases: string[]): number {
  if (phases.some((phase) => ['closed', 'cleanup_window', 'public_results'].includes(phase))) return 4;
  if (phases.includes('informed_voting')) return 3;
  if (phases.some((phase) => ['argument_mapping', 'cleanup'].includes(phase))) return 2;
  if (phases.some((phase) => ['submission', 'featured_selection'].includes(phase))) return 1;
  return 0;
}

function InputTimeline({phases}: {phases: string[]}) {
  const position = timelinePosition(phases);
  const badgeClass = (step: number) => (
    `conv-input-badge${position === step ? ' conv-input-badge--current' : ''}${position > step ? ' conv-input-badge--done' : ''}`
  );
  return (
    <div className="conv-input-timeline" aria-label="Input phase progress">
      <span className={badgeClass(1)} dangerouslySetInnerHTML={{__html: `${position > 1 ? '<span aria-hidden="true">✓</span> ' : ''}Explore`}} />
      {position >= 2 && <>
        <span className="conv-input-rail" aria-hidden="true" />
        <span className="conv-input-clock" aria-hidden="true" />
        <span className="conv-input-rail" aria-hidden="true" />
        <span className={badgeClass(2)} dangerouslySetInnerHTML={{__html: `${position > 2 ? '<span aria-hidden="true">✓</span> ' : ''}Arguments`}} />
      </>}
      {position >= 3 && <>
        <span className="conv-input-rail" aria-hidden="true" />
        <span className="conv-input-clock" aria-hidden="true" />
        <span className="conv-input-rail" aria-hidden="true" />
        <span className={badgeClass(3)} dangerouslySetInnerHTML={{__html: `${position > 3 ? '<span aria-hidden="true">✓</span> ' : ''}Informed vote`}} />
      </>}
      {phases.includes('closed') && <>
        <span className="conv-input-rail" aria-hidden="true" />
        <span className="conv-input-clock" aria-hidden="true" />
        <span className="conv-input-rail" aria-hidden="true" />
        <span className="conv-input-badge conv-input-badge--todo" dangerouslySetInnerHTML={{__html: 'Opt-in identification'}} />
      </>}
    </div>
  );
}

function OutputSymbols({
  outputs,
  onPending,
}: {
  outputs: ConversationOutput[];
  onPending: (output: ConversationOutput, trigger: HTMLButtonElement) => void;
}) {
  return (
    <div className="conv-output-grid" aria-label="Consultation outputs">
      {outputs.map((output) => output.ready ? (
        <InternalLink
          key={output.key}
          className="conv-output-symbol conv-output-symbol--ready"
          href={output.href ?? undefined}
          data-state="ready"
          data-href={output.href ?? ''}
          aria-label={output.tooltip}
          title={output.tooltip}
        >
          <span className={`phase-symbol phase-symbol--${output.symbol}`} aria-hidden="true" />
          <span className="sr-only">{output.label}</span>
        </InternalLink>
      ) : (
        <button
          key={output.key}
          className="conv-output-symbol conv-output-symbol--pending"
          type="button"
          data-state="pending"
          data-title={output.label}
          data-detail={output.pending}
          aria-label={output.tooltip}
          title={output.tooltip}
          onClick={(event) => onPending(output, event.currentTarget)}
        >
          <span className={`phase-symbol phase-symbol--${output.symbol}`} aria-hidden="true" />
          <span className="sr-only">{output.label}</span>
        </button>
      ))}
    </div>
  );
}

function localDateTime(at: string): string {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(at));
}

function escapeHtml(value: string): string {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function ConversationChips({conversation}: {conversation: ConversationCard}) {
  const chips = [];
  if (conversation.scheduledTransition) {
    const transition = conversation.scheduledTransition;
    chips.push(
      <span
        className="conv-chip"
        key="transition"
        dangerouslySetInnerHTML={{
          __html: `Next: ${escapeHtml(transition.targetLabel)} <time datetime="${escapeHtml(transition.at)}" data-local-datetime title="Shown in your local timezone">${escapeHtml(localDateTime(transition.at))}</time>`,
        }}
      />,
    );
  }
  if (conversation.statementsRemaining !== null && conversation.statementsRemaining > 0) {
    chips.push(<span className="conv-chip" key="remaining" dangerouslySetInnerHTML={{__html: `${conversation.statementsRemaining} to vote`}} />);
  }
  if (conversation.reveal?.state === 'open') {
    chips.push(
      <span
        className="conv-chip conv-chip--alert"
        key="reveal"
        dangerouslySetInnerHTML={{__html: `<span aria-hidden="true">! </span>Reveal window: ${conversation.reveal.daysRemaining <= 0 ? 'today' : `${conversation.reveal.daysRemaining}d left`}`}}
      />,
    );
  } else if (conversation.reveal?.state === 'pending') {
    chips.push(<span className="conv-chip" key="reveal" dangerouslySetInnerHTML={{__html: `Reveal opens in ${conversation.reveal.daysRemaining}d`}} />);
  }
  return chips.length > 0 ? <div className="conv-chips">{chips}</div> : null;
}

type JoinedState = 'needs_attention' | 'caught_up' | 'inactive' | 'archived';

function joinedAriaLabel(conversation: ConversationCard, state: JoinedState): string {
  const pseudonym = conversation.pseudonym ? ` — your pseudonym: ${conversation.pseudonym}` : '';
  const remaining = conversation.statementsRemaining ? ` — ${conversation.statementsRemaining} statements to vote` : '';
  const action = state === 'needs_attention' ? 'continue' : state.replace('_', ' ');
  return `${conversation.title}${pseudonym}${remaining} — ${action}`;
}

function JoinedSection({
  conversations,
  label,
  sectionId,
  state,
  onPending,
}: {
  conversations: ConversationCard[];
  label: string;
  sectionId: string;
  state: JoinedState;
  onPending: (output: ConversationOutput, trigger: HTMLButtonElement) => void;
}) {
  if (conversations.length === 0) return null;
  return (
    <section aria-labelledby={sectionId}>
      <div className="home-section">
        <div className="home-section-header">
          <h2 className="home-section-label" id={sectionId}>{label}</h2>
          <span className="home-section-count" aria-hidden="true" dangerouslySetInnerHTML={{__html: String(conversations.length)}} />
        </div>
        <ul className="conv-list">
          {conversations.map((conversation) => <li key={conversation.slug}>
            <div className="conv-card conv-card--phase conv-card--outputs">
              <InternalLink href={conversation.links.self} className="conv-card-main" aria-label={joinedAriaLabel(conversation, state)}>
                <div className="conv-card-left conv-card-left--col">
                  <div className="conv-card-title-row">
                    <h3 className="conv-card-title">{conversation.title}</h3>
                    {conversation.pseudonym && <span className="conv-card-badge" aria-hidden="true">{conversation.pseudonym}</span>}
                    {state === 'caught_up' && <span className="conv-card-badge conv-card-badge--muted">caught up</span>}
                    {state === 'inactive' && <span className="conv-card-badge conv-card-badge--muted">{conversation.status === 'paused' ? 'paused' : 'waiting'}</span>}
                    {state === 'archived' && conversation.closedAt && <span className="conv-card-badge conv-card-badge--muted" aria-hidden="true">{archivedMonth(conversation.closedAt)}</span>}
                  </div>
                  <InputTimeline phases={conversation.phases} />
                  <ConversationChips conversation={conversation} />
                </div>
                <span
                  className={`conv-card-action${state !== 'needs_attention' ? ' conv-card-action--muted' : ''}`}
                  aria-hidden="true"
                  dangerouslySetInnerHTML={{__html: `${state === 'needs_attention' ? 'CONTINUE' : 'VIEW'} →`}}
                />
              </InternalLink>
              <span className="conv-card-output-divider" aria-hidden="true" />
              <OutputSymbols outputs={conversation.outputs} onPending={onPending} />
            </div>
          </li>)}
        </ul>
      </div>
    </section>
  );
}

function PhaseLegend() {
  return (
    <div
      className="phase-legend"
      role="img"
      aria-label="Consultation phases: Explore, Arguments, Informed vote, Report"
      dangerouslySetInnerHTML={{__html: `
        <div class="phase-legend-node">
          <span class="phase-legend-icon" aria-hidden="true"><span class="phase-symbol phase-symbol--explore"></span></span>
          <span class="phase-legend-label" aria-hidden="true">Explore</span>
        </div>
        <div class="phase-legend-connector" aria-hidden="true"><span class="phase-legend-line"></span><span class="phase-legend-mid-dot"></span><span class="phase-legend-line"></span></div>
        <div class="phase-legend-node">
          <span class="phase-legend-icon" aria-hidden="true"><span class="phase-symbol phase-symbol--arguments"></span></span>
          <span class="phase-legend-label" aria-hidden="true">Arguments</span>
        </div>
        <div class="phase-legend-connector" aria-hidden="true"><span class="phase-legend-line"></span><span class="phase-legend-mid-dot"></span><span class="phase-legend-line"></span></div>
        <div class="phase-legend-node">
          <span class="phase-legend-icon" aria-hidden="true"><span class="phase-symbol phase-symbol--informed-vote"></span></span>
          <span class="phase-legend-label" aria-hidden="true">Informed vote</span>
        </div>
        <div class="phase-legend-connector" aria-hidden="true"><span class="phase-legend-line"></span><span class="phase-legend-mid-dot"></span><span class="phase-legend-line"></span></div>
        <div class="phase-legend-node">
          <span class="phase-legend-icon" aria-hidden="true"><span class="phase-symbol phase-symbol--report"></span></span>
          <span class="phase-legend-label" aria-hidden="true">Report</span>
        </div>`}}
    />
  );
}

function AvailableSection({
  conversations,
  onPending,
}: {
  conversations: ConversationCard[];
  onPending: (output: ConversationOutput, trigger: HTMLButtonElement) => void;
}) {
  if (conversations.length === 0) {
    return <div className="home-empty"><p className="muted">No consultations open to you right now.</p></div>;
  }
  return (
    <section aria-labelledby="sec-available">
      <div className="home-section">
        <div className="home-section-header">
          <h2 className="home-section-label" id="sec-available">Open to you</h2>
          <span className="home-section-count" aria-hidden="true" dangerouslySetInnerHTML={{__html: String(conversations.length)}} />
        </div>
        <ul className="conv-list">
          {conversations.map((conversation) => <li key={conversation.slug}>
            <div className="conv-card conv-card--phase conv-card--outputs">
              <InternalLink href={conversation.links.self} className="conv-card-main" aria-label={`${conversation.title} — join consultation`}>
                <div className="conv-card-left conv-card-left--col">
                  <div className="conv-card-title-row"><h3 className="conv-card-title">{conversation.title}</h3></div>
                  <InputTimeline phases={conversation.phases} />
                </div>
                <span className="conv-card-action" aria-hidden="true" dangerouslySetInnerHTML={{__html: 'JOIN →'}} />
              </InternalLink>
              <span className="conv-card-output-divider" aria-hidden="true" />
              <OutputSymbols outputs={conversation.outputs} onPending={onPending} />
            </div>
          </li>)}
        </ul>
      </div>
    </section>
  );
}

function ModeratingSection({conversations}: {conversations: ConversationCard[]}) {
  if (conversations.length === 0) return null;
  return (
    <section aria-labelledby="sec-moderate">
      <div className="home-section">
        <div className="home-section-header">
          <h2 className="home-section-label" id="sec-moderate">You moderate</h2>
          <span className="home-section-count" aria-hidden="true" dangerouslySetInnerHTML={{__html: String(conversations.length)}} />
        </div>
        <ul className="conv-list">
          {conversations.map((conversation) => <li key={conversation.slug}>
            <div className="conv-card conv-card--split">
              <div className="conv-card-left">
                <span className={`conv-dot ${conversation.status === 'archived' ? 'conv-dot--closed' : 'conv-dot--active'}`} aria-hidden="true" />
                <h3 className="conv-card-title-wrap"><InternalLink href={conversation.links.self} className="conv-card-title" aria-label={`${conversation.title} — open consultation`}>{conversation.title}</InternalLink></h3>
                {conversation.status === 'archived' && <span className="conv-card-badge">closed</span>}
              </div>
              <span className="conv-card-divider" aria-hidden="true" />
              <InternalLink href={conversation.links.admin} className="admin-action-btn" aria-label={`Open admin panel for ${conversation.title}`}>Admin →</InternalLink>
            </div>
          </li>)}
        </ul>
      </div>
    </section>
  );
}

function AnonymousLane({
  conversations,
  developerLogins,
  loginHref,
}: {
  conversations: ConversationCard[];
  developerLogins: components['schemas']['DeveloperLogin'][];
  loginHref: string;
}) {
  return <>
    <div className="landing-section">
      <h1 className="sr-only">Consultations</h1>
      <h2 style={{fontSize: 26, fontWeight: 600, letterSpacing: '-0.02em', lineHeight: 1.15, marginBottom: 12}}>Where the community actually stands.</h2>
      <p style={{fontSize: 15, lineHeight: 1.6, color: 'var(--body)', maxWidth: 520}}>
        Vote on short statements, and suggest improvements. Learn how your views
        compare to other community members — which statements already have
        consensus, and what topics are divisive, and why.
      </p>
      <InternalLink href={loginHref} className="login-btn" style={{marginTop: 18}}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeDasharray="1.4 1.6" aria-hidden="true">
          <circle cx="12" cy="12" r="9" />
          <ellipse cx="12" cy="12" rx="9" ry="3.5" />
          <ellipse cx="12" cy="12" rx="3.5" ry="9" />
        </svg>
        Login with Wikimedia
      </InternalLink>
      {developerLogins.length > 0 && <div style={{marginTop: '1.25rem', padding: '10px 14px', border: '1px dashed var(--spot)', borderRadius: 8, background: 'rgba(245,158,11,0.05)', display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap'}}>
        <span style={{fontFamily: 'var(--mono)', fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--spot)'}}>Dev</span>
        {developerLogins.map((login) => <InternalLink
          key={login.username}
          href={login.href}
          style={{fontFamily: 'var(--mono)', fontSize: 11, padding: '2px 8px', borderRadius: 4, background: 'var(--surface2)', border: '1px solid var(--hairline)', color: 'var(--ink)', textDecoration: 'none'}}
          title={`Log in as ${login.username}`}
        >{login.username}</InternalLink>)}
      </div>}
    </div>
    {conversations.length > 0 && <section aria-labelledby="sec-open">
      <div className="home-section">
        <div className="home-section-header">
          <h2 className="home-section-label" id="sec-open">Open consultations</h2>
          <span className="home-section-count" aria-hidden="true" dangerouslySetInnerHTML={{__html: `${conversations.length} total`}} />
        </div>
        <ul className="conv-list">
          {conversations.map((conversation) => <li key={conversation.slug}>
            <InternalLink href={conversation.links.self} className="conv-card" aria-label={`${conversation.title} — open consultation`}>
              <div className="conv-card-left">
                <span className="conv-dot conv-dot--available" aria-hidden="true" />
                <h3 className="conv-card-title">{conversation.title}</h3>
              </div>
              <span className="conv-card-action" aria-hidden="true" dangerouslySetInnerHTML={{__html: 'JOIN →'}} />
            </InternalLink>
          </li>)}
        </ul>
      </div>
    </section>}
  </>;
}

export function ConversationLanePage({space}: {space: ConversationSpace}) {
  const {data} = useSuspenseQuery(conversationLaneQuery(space));
  const {data: session} = useSuspenseQuery(sessionQuery());
  const [mode, setMode] = useState<'yours' | 'browse'>(() => {
    try {
      return localStorage.getItem('home-mode') === 'browse' ? 'browse' : 'yours';
    } catch {
      return 'yours';
    }
  });
  const lastFocus = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    if (space !== 'demo') return;
    const meta = document.createElement('meta');
    meta.name = 'robots';
    meta.content = 'noindex,nofollow';
    meta.dataset.reactLegacyRobots = 'true';
    document.head.appendChild(meta);
    return () => meta.remove();
  }, [space]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const dialog = document.getElementById('output-dialog');
      if (event.key === 'Escape' && dialog && !dialog.hidden) closeDialog();
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, []);

  function changeMode(next: 'yours' | 'browse') {
    try { localStorage.setItem('home-mode', next); } catch { /* Storage can be unavailable. */ }
    setMode(next);
  }

  function openPending(output: ConversationOutput, trigger: HTMLButtonElement) {
    lastFocus.current = trigger;
    const dialog = document.getElementById('output-dialog');
    const title = document.getElementById('output-dialog-title');
    const body = document.getElementById('output-dialog-body');
    if (!dialog || !title || !body) return;
    title.textContent = output.label;
    body.textContent = output.pending;
    dialog.hidden = false;
    dialog.querySelector<HTMLButtonElement>('.output-dialog-close')?.focus();
  }

  function closeDialog() {
    const dialog = document.getElementById('output-dialog');
    if (dialog) dialog.hidden = true;
    lastFocus.current?.focus();
  }

  const groups = data.groups;
  const joinedEmpty = groups.needsAttention.length === 0
    && groups.caughtUp.length === 0
    && groups.inactive.length === 0
    && groups.archived.length === 0;

  return (
    <LegacyShell headerMode={space}>
      <div className="container home-container">
        {!data.authenticated ? (
          <AnonymousLane conversations={groups.available} developerLogins={session.developerLogins} loginHref={session.links.login} />
        ) : <>
          <h1 className="sr-only">Consultations</h1>
          <ConversationFlow />
          <PhaseLegend />
          <div className="home-mode-toggle" role="group" aria-label="View mode">
            <button className={`home-mode-btn${mode === 'yours' ? ' home-mode-btn--active' : ''}`} data-target="yours" type="button" aria-pressed={mode === 'yours'} onClick={() => changeMode('yours')}>Your conversations</button>
            <button className={`home-mode-btn${mode === 'browse' ? ' home-mode-btn--active' : ''}`} data-target="browse" type="button" aria-pressed={mode === 'browse'} onClick={() => changeMode('browse')}>Browse</button>
          </div>
          <div id="home-yours" hidden={mode !== 'yours'}>
            <JoinedSection conversations={groups.needsAttention} label="Needs attention" sectionId="sec-attention" state="needs_attention" onPending={openPending} />
            <JoinedSection conversations={groups.caughtUp} label="Caught up" sectionId="sec-caught-up" state="caught_up" onPending={openPending} />
            <JoinedSection conversations={groups.inactive} label="Inactive / paused" sectionId="sec-inactive" state="inactive" onPending={openPending} />
            <JoinedSection conversations={groups.archived} label="Closed" sectionId="sec-closed" state="archived" onPending={openPending} />
            {joinedEmpty && <div className="home-empty"><p className="muted">You haven&apos;t joined any consultations yet. Use Browse to find one.</p></div>}
          </div>
          <div id="home-browse" hidden={mode !== 'browse'}>
            <AvailableSection conversations={groups.available} onPending={openPending} />
          </div>
          <ModeratingSection conversations={groups.moderating} />
        </>}
      </div>

      {data.authenticated && <div
        className="output-dialog"
        id="output-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="output-dialog-title"
        hidden
        onClick={(event) => {
          const target = event.target;
          if (
            target === event.currentTarget
            || (target instanceof Element && target.closest('.output-dialog-close'))
          ) closeDialog();
        }}
      >
        <div
          className="output-dialog-panel"
          dangerouslySetInnerHTML={{
            __html: '<button type="button" class="output-dialog-close" aria-label="Close output details"></button><h2 id="output-dialog-title">Output pending</h2><p id="output-dialog-body" class="muted"></p>',
          }}
        />
      </div>}
    </LegacyShell>
  );
}

import {Fragment, useEffect, useRef, useState} from 'react';
import {useSuspenseQuery} from '@tanstack/react-query';

import type {components} from '../../api/schema';
import {
  conversationLaneQuery,
  sessionQuery,
  type ConversationSpace,
} from '../../api/queries';
import {LegacyShell} from './legacy-shell';
import {InternalLink} from '../../internal-link';
import {useMessage, type Message} from '../../i18n/messages';
import {escapeHtml, richHtml} from '../../i18n/rich-html';
import {outputLabel, outputPending, outputTooltip, phaseLabel} from '../../i18n/server-labels';
import {useDateFormat} from '../../i18n/dates';

type ConversationCard = components['schemas']['ConversationCard'];
type ConversationOutput = components['schemas']['ConversationOutput'];


function timelinePosition(phases: string[]): number {
  if (phases.some((phase) => ['closed', 'cleanup_window', 'public_results'].includes(phase))) return 4;
  if (phases.includes('informed_voting')) return 3;
  if (phases.some((phase) => ['argument_mapping', 'cleanup'].includes(phase))) return 2;
  if (phases.some((phase) => ['submission', 'featured_selection'].includes(phase))) return 1;
  return 0;
}

function InputTimeline({phases}: {phases: string[]}) {
  const msg = useMessage();
  const position = timelinePosition(phases);
  const done = (step: number) => position > step && <><span aria-hidden="true">✓</span> </>;
  const badgeClass = (step: number) => (
    `conv-input-badge${position === step ? ' conv-input-badge--current' : ''}${position > step ? ' conv-input-badge--done' : ''}`
  );
  return (
    <div className="conv-input-timeline" aria-label={msg('home-timeline-aria')}>
      <span className={badgeClass(1)}>{done(1)}{msg('home-phase-explore')}</span>
      {position >= 2 && <>
        <span className="conv-input-rail" aria-hidden="true" />
        <span className="conv-input-clock" aria-hidden="true" />
        <span className="conv-input-rail" aria-hidden="true" />
        <span className={badgeClass(2)}>{done(2)}{msg('home-phase-arguments')}</span>
      </>}
      {position >= 3 && <>
        <span className="conv-input-rail" aria-hidden="true" />
        <span className="conv-input-clock" aria-hidden="true" />
        <span className="conv-input-rail" aria-hidden="true" />
        <span className={badgeClass(3)}>{done(3)}{msg('home-phase-informed-vote')}</span>
      </>}
      {phases.includes('closed') && <>
        <span className="conv-input-rail" aria-hidden="true" />
        <span className="conv-input-clock" aria-hidden="true" />
        <span className="conv-input-rail" aria-hidden="true" />
        <span className="conv-input-badge conv-input-badge--todo">{msg('home-phase-optin-id')}</span>
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
  const msg = useMessage();
  return (
    <div className="conv-output-grid" aria-label={msg('home-outputs-aria')}>
      {outputs.map((output) => output.ready ? (
        <InternalLink
          key={output.key}
          className="conv-output-symbol conv-output-symbol--ready"
          href={output.href ?? undefined}
          data-state="ready"
          data-href={output.href ?? ''}
          aria-label={outputTooltip(msg, output.key, output.tooltip)}
          title={outputTooltip(msg, output.key, output.tooltip)}
        >
          <span className={`phase-symbol phase-symbol--${output.symbol}`} aria-hidden="true" />
          <span className="sr-only">{outputLabel(msg, output.key, output.label)}</span>
        </InternalLink>
      ) : (
        <button
          key={output.key}
          className="conv-output-symbol conv-output-symbol--pending"
          type="button"
          data-state="pending"
          data-title={outputLabel(msg, output.key, output.label)}
          data-detail={outputPending(msg, output.key, output.pending)}
          aria-label={outputTooltip(msg, output.key, output.tooltip)}
          title={outputTooltip(msg, output.key, output.tooltip)}
          onClick={(event) => onPending(output, event.currentTarget)}
        >
          <span className={`phase-symbol phase-symbol--${output.symbol}`} aria-hidden="true" />
          <span className="sr-only">{outputLabel(msg, output.key, output.label)}</span>
        </button>
      ))}
    </div>
  );
}

function ConversationChips({conversation}: {conversation: ConversationCard}) {
  const msg = useMessage();
  const dates = useDateFormat();
  const chips = [];
  if (conversation.scheduledTransition) {
    const transition = conversation.scheduledTransition;
    chips.push(
      <span
        className="conv-chip"
        key="transition"
        dangerouslySetInnerHTML={richHtml(msg('home-chip-next',
          escapeHtml(phaseLabel(msg, transition.target, transition.targetLabel)),
          `<time datetime="${escapeHtml(transition.at)}" data-local-datetime title="${escapeHtml(msg('conv-scheduled-tz-title'))}">${escapeHtml(dates.dateTime(transition.at))}</time>`,
        ))}
      />,
    );
  }
  if (conversation.statementsRemaining !== null && conversation.statementsRemaining > 0) {
    chips.push(<span className="conv-chip" key="remaining">{msg('home-chip-to-vote', conversation.statementsRemaining)}</span>);
  }
  if (conversation.reveal?.state === 'open') {
    chips.push(
      <span className="conv-chip conv-chip--alert" key="reveal"><span aria-hidden="true">! </span>{conversation.reveal.daysRemaining <= 0
        ? msg('home-chip-reveal-today')
        : msg('home-chip-reveal-days', conversation.reveal.daysRemaining)}</span>,
    );
  } else if (conversation.reveal?.state === 'pending') {
    chips.push(<span className="conv-chip" key="reveal">{msg('home-chip-reveal-opens', conversation.reveal.daysRemaining)}</span>);
  }
  return chips.length > 0 ? <div className="conv-chips">{chips}</div> : null;
}

type JoinedState = 'needs_attention' | 'caught_up' | 'inactive' | 'archived';

/** The card link's accessible name: title, then whichever of pseudonym, remaining count
 *  and state apply, each its own dash-led message. They are independent clauses in a
 *  list rather than one sentence, so a translator never needs to reorder across them. */
function joinedAriaLabel(msg: Message, conversation: ConversationCard, state: JoinedState): string {
  const parts = [conversation.title];
  if (conversation.pseudonym) parts.push(msg('home-card-aria-pseudonym', conversation.pseudonym));
  if (conversation.statementsRemaining) parts.push(msg('home-card-aria-remaining', conversation.statementsRemaining));
  parts.push(
    state === 'needs_attention' ? msg('home-card-aria-continue')
      : state === 'caught_up' ? msg('home-card-aria-caught-up')
        : state === 'inactive' ? msg('home-card-aria-inactive')
          : msg('home-card-aria-closed'),
  );
  return parts.join(' ');
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
  const msg = useMessage();
  const dates = useDateFormat();
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
              <InternalLink href={conversation.links.self} className="conv-card-main" aria-label={joinedAriaLabel(msg, conversation, state)}>
                <div className="conv-card-left conv-card-left--col">
                  <div className="conv-card-title-row">
                    <h3 className="conv-card-title">{conversation.title}</h3>
                    {conversation.pseudonym && <span className="conv-card-badge" aria-hidden="true">{conversation.pseudonym}</span>}
                    {state === 'caught_up' && <span className="conv-card-badge conv-card-badge--muted">{msg('home-card-badge-caught-up')}</span>}
                    {state === 'inactive' && <span className="conv-card-badge conv-card-badge--muted">{conversation.status === 'paused' ? msg('home-card-badge-paused') : msg('home-card-badge-waiting')}</span>}
                    {state === 'archived' && conversation.closedAt && <span className="conv-card-badge conv-card-badge--muted" aria-hidden="true">{dates.monthYear(conversation.closedAt)}</span>}
                  </div>
                  <InputTimeline phases={conversation.phases} />
                  <ConversationChips conversation={conversation} />
                </div>
                <span
                  className={`conv-card-action${state !== 'needs_attention' ? ' conv-card-action--muted' : ''}`}
                  aria-hidden="true"
                >{state === 'needs_attention' ? msg('home-action-continue') : msg('home-action-view')}</span>
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
  const msg = useMessage();
  const nodes = [
    {symbol: 'explore', label: msg('home-phase-explore')},
    {symbol: 'arguments', label: msg('home-phase-arguments')},
    {symbol: 'informed-vote', label: msg('home-phase-informed-vote')},
    {symbol: 'report', label: msg('home-phase-report')},
  ];
  return (
    <div className="phase-legend" role="img" aria-label={msg('home-phase-legend-aria')}>
      {nodes.map((node, index) => <Fragment key={node.symbol}>
        {index > 0 && <div className="phase-legend-connector" aria-hidden="true"><span className="phase-legend-line" /><span className="phase-legend-mid-dot" /><span className="phase-legend-line" /></div>}
        <div className="phase-legend-node">
          <span className="phase-legend-icon" aria-hidden="true"><span className={`phase-symbol phase-symbol--${node.symbol}`} /></span>
          <span className="phase-legend-label" aria-hidden="true">{node.label}</span>
        </div>
      </Fragment>)}
    </div>
  );
}

function AvailableSection({
  conversations,
  onPending,
}: {
  conversations: ConversationCard[];
  onPending: (output: ConversationOutput, trigger: HTMLButtonElement) => void;
}) {
  const msg = useMessage();
  if (conversations.length === 0) {
    return <div className="home-empty"><p className="muted">{msg('home-empty-none-open')}</p></div>;
  }
  return (
    <section aria-labelledby="sec-available">
      <div className="home-section">
        <div className="home-section-header">
          <h2 className="home-section-label" id="sec-available">{msg('home-section-open-to-you')}</h2>
          <span className="home-section-count" aria-hidden="true" dangerouslySetInnerHTML={{__html: String(conversations.length)}} />
        </div>
        <ul className="conv-list">
          {conversations.map((conversation) => <li key={conversation.slug}>
            <div className="conv-card conv-card--phase conv-card--outputs">
              <InternalLink href={conversation.links.self} className="conv-card-main" aria-label={msg('home-card-join-aria', conversation.title)}>
                <div className="conv-card-left conv-card-left--col">
                  <div className="conv-card-title-row"><h3 className="conv-card-title">{conversation.title}</h3></div>
                  <InputTimeline phases={conversation.phases} />
                </div>
                <span className="conv-card-action" aria-hidden="true">{msg('home-action-join')}</span>
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
  const msg = useMessage();
  if (conversations.length === 0) return null;
  return (
    <section aria-labelledby="sec-moderate">
      <div className="home-section">
        <div className="home-section-header">
          <h2 className="home-section-label" id="sec-moderate">{msg('home-section-moderate')}</h2>
          <span className="home-section-count" aria-hidden="true" dangerouslySetInnerHTML={{__html: String(conversations.length)}} />
        </div>
        <ul className="conv-list">
          {conversations.map((conversation) => <li key={conversation.slug}>
            <div className="conv-card conv-card--split">
              <div className="conv-card-left">
                <span className={`conv-dot ${conversation.status === 'archived' ? 'conv-dot--closed' : 'conv-dot--active'}`} aria-hidden="true" />
                <h3 className="conv-card-title-wrap"><InternalLink href={conversation.links.self} className="conv-card-title" aria-label={msg('home-card-view-aria', conversation.title)}>{conversation.title}</InternalLink></h3>
                {conversation.status === 'archived' && <span className="conv-card-badge">{msg('home-card-badge-closed')}</span>}
              </div>
              <span className="conv-card-divider" aria-hidden="true" />
              <InternalLink href={conversation.links.admin} className="admin-action-btn" aria-label={msg('home-card-admin-aria', conversation.title)}>{msg('home-action-admin')}</InternalLink>
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
  const msg = useMessage();
  return <>
    <div className="landing-section">
      <h1 className="sr-only">{msg('home-heading')}</h1>
      <h2 style={{fontSize: 26, fontWeight: 600, letterSpacing: '-0.02em', lineHeight: 1.15, marginBottom: 12}}>{msg('home-hero-heading')}</h2>
      <p style={{fontSize: 15, lineHeight: 1.6, color: 'var(--body)', maxWidth: 520}}>{msg('home-hero-body')}</p>
      <p style={{fontSize: 15, lineHeight: 1.6, color: 'var(--body)', maxWidth: 520}}>{msg('home-hero-detail')}</p>
      <InternalLink href={loginHref} className="login-btn" style={{marginTop: 18}}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeDasharray="1.4 1.6" aria-hidden="true">
          <circle cx="12" cy="12" r="9" />
          <ellipse cx="12" cy="12" rx="9" ry="3.5" />
          <ellipse cx="12" cy="12" rx="3.5" ry="9" />
        </svg>
        {msg('home-login-wikimedia')}
      </InternalLink>
      {developerLogins.length > 0 && <div style={{marginTop: '1.25rem', padding: '10px 14px', border: '1px dashed var(--spot)', borderRadius: 8, background: 'rgba(245,158,11,0.05)', display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap'}}>
        <span style={{fontFamily: 'var(--mono)', fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--spot)'}}>{msg('home-dev-badge')}</span>
        {developerLogins.map((login) => <InternalLink
          key={login.username}
          href={login.href}
          style={{fontFamily: 'var(--mono)', fontSize: 11, padding: '2px 8px', borderRadius: 4, background: 'var(--surface2)', border: '1px solid var(--hairline)', color: 'var(--ink)', textDecoration: 'none'}}
          title={msg('home-dev-login-as', login.username)}
        >{login.username}</InternalLink>)}
      </div>}
    </div>
    {conversations.length > 0 && <section aria-labelledby="sec-open">
      <div className="home-section">
        <div className="home-section-header">
          <h2 className="home-section-label" id="sec-open">{msg('home-open-consultations')}</h2>
          <span className="home-section-count" aria-hidden="true">{msg('home-count-total', conversations.length)}</span>
        </div>
        <ul className="conv-list">
          {conversations.map((conversation) => <li key={conversation.slug}>
            <InternalLink href={conversation.links.self} className="conv-card" aria-label={msg('home-card-view-aria', conversation.title)}>
              <div className="conv-card-left">
                <span className="conv-dot conv-dot--available" aria-hidden="true" />
                <h3 className="conv-card-title">{conversation.title}</h3>
              </div>
              <span className="conv-card-action" aria-hidden="true">{msg('home-action-join')}</span>
            </InternalLink>
          </li>)}
        </ul>
      </div>
    </section>}
  </>;
}

export function ConversationLanePage({space}: {space: ConversationSpace}) {
  const msg = useMessage();
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
    title.textContent = outputLabel(msg, output.key, output.label);
    body.textContent = outputPending(msg, output.key, output.pending);
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
        <div className="home-banner" dangerouslySetInnerHTML={richHtml(msg('home-banner-prototype',
          `<a href="https://github.com/lgelauff/wiki-polis/issues/new" target="_blank" rel="noopener">`
          + `${escapeHtml(msg('home-banner-open-issue'))}<span class="sr-only">${escapeHtml(msg('common-opens-in-new-tab'))}</span></a>`))} />

        {!data.authenticated ? (
          <AnonymousLane conversations={groups.available} developerLogins={session.developerLogins} loginHref={session.links.login} />
        ) : <>
          <h1 className="sr-only">{msg('home-heading')}</h1>
          <img src="/static/wiki-polis-flow.svg" alt={msg('home-flow-alt')} style={{width: '100%', maxWidth: 900, display: 'block', margin: '0 auto 1.5rem'}} />
          <PhaseLegend />
          <div className="home-mode-toggle" role="group" aria-label={msg('home-view-mode-aria')}>
            <button className={`home-mode-btn${mode === 'yours' ? ' home-mode-btn--active' : ''}`} data-target="yours" type="button" aria-pressed={mode === 'yours'} onClick={() => changeMode('yours')}>{msg('home-mode-yours')}</button>
            <button className={`home-mode-btn${mode === 'browse' ? ' home-mode-btn--active' : ''}`} data-target="browse" type="button" aria-pressed={mode === 'browse'} onClick={() => changeMode('browse')}>{msg('home-mode-browse')}</button>
          </div>
          <div id="home-yours" hidden={mode !== 'yours'}>
            <JoinedSection conversations={groups.needsAttention} label={msg('home-section-needs-attention')} sectionId="sec-attention" state="needs_attention" onPending={openPending} />
            <JoinedSection conversations={groups.caughtUp} label={msg('home-section-caught-up')} sectionId="sec-caught-up" state="caught_up" onPending={openPending} />
            <JoinedSection conversations={groups.inactive} label={msg('home-section-inactive')} sectionId="sec-inactive" state="inactive" onPending={openPending} />
            <JoinedSection conversations={groups.archived} label={msg('home-section-closed')} sectionId="sec-closed" state="archived" onPending={openPending} />
            {joinedEmpty && <div className="home-empty"><p className="muted">{msg('home-empty-none-joined')}</p></div>}
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
            // Left as markup rather than JSX: openPending() writes the title and body
            // imperatively, which React would fight over if it owned these children.
            __html: `<button type="button" class="output-dialog-close" aria-label="${escapeHtml(msg('home-output-dialog-close'))}"></button><h2 id="output-dialog-title">${escapeHtml(msg('home-output-dialog-title'))}</h2><p id="output-dialog-body" class="muted"></p>`,
          }}
        />
      </div>}
    </LegacyShell>
  );
}

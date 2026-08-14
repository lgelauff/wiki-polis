import {useEffect, useRef, useState, type FormEvent, type MouseEvent} from 'react';
import {useMutation, useQueryClient, useSuspenseQuery} from '@tanstack/react-query';

import type {components} from '../../api/schema';
import {
  argumentMappingQuery,
  createArgument,
  putAdminFeaturedArgument,
  putArgumentPriority,
  skipArgumentContribution,
} from '../../api/queries';
import {LegacyContentFlag} from './legacy-content-flag';

type Mapping = components['schemas']['ArgumentMapping'];
type Featured = components['schemas']['ArgumentFeaturedStatement'];
type Side = components['schemas']['ArgumentSide'];
type ArgumentItem = components['schemas']['ArgumentItem'];
type SideName = 'pro' | 'con';

const sideCopy = {
  pro: {label: 'For', adjective: 'for', sign: '+', className: 'for'},
  con: {label: 'Against', adjective: 'against', sign: '−', className: 'against'},
} as const;

function Contribution({slug, csrfToken, featuredId, side, value}: {
  slug: string;
  csrfToken: string;
  featuredId: number;
  side: SideName;
  value: Side['contribution'];
}) {
  const queryClient = useQueryClient();
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [state, setState] = useState<'idle' | 'composing' | 'submitted' | 'skipped'>(
    value.status === 'pending' ? 'idle' : value.status,
  );
  const [body, setBody] = useState('');
  const copy = sideCopy[side];
  useEffect(() => {
    if (value.status !== 'pending') setState(value.status);
  }, [value.status]);
  const refresh = () => queryClient.invalidateQueries(argumentMappingQuery(slug));
  const submit = useMutation({
    mutationFn: () => createArgument(
      slug, featuredId, {side, body: body.trim()}, csrfToken,
    ),
    onSuccess: async () => {
      setState('submitted');
      await refresh();
    },
  });
  const skip = useMutation({
    mutationFn: () => skipArgumentContribution(slug, featuredId, side, csrfToken),
    onSuccess: async () => {
      setState('skipped');
      await refresh();
    },
  });

  function compose() {
    setState('composing');
    queueMicrotask(() => textareaRef.current?.focus());
  }

  function submitForm(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (body.trim()) submit.mutate();
  }

  return (
    <div className="contribute-wrapper" data-state={state} data-side={side} data-fs={featuredId}>
      <button className={`at-contribute at-contribute--idle contribute-affordance contribute-affordance--${side}`} type="button" onClick={compose}>
        <span className="at-contribute-glyph" style={{background: side === 'pro' ? 'rgba(21,115,74,.15)' : 'rgba(178,58,58,.15)', color: side === 'pro' ? 'var(--agree)' : 'var(--disagree)', fontWeight: 700}} aria-hidden="true">{copy.sign}</span>
        Add one {copy.adjective}-argument
      </button>
      <button className="at-direct-skip contribute-direct-skip" type="button" disabled={skip.isPending} onClick={() => skip.mutate()}>Nothing to add</button>
      <form className="contribute-composer" onSubmit={submitForm}>
        <div className="contribute-composer-header">
          <span className="contribute-glyph filled">{copy.sign}</span>
          <span className="contribute-composer-label" id={`contribute-label-${featuredId}-${side}`}>Your {copy.adjective}-argument · one sentence, one claim</span>
          <a className="contribute-help-link" href="/help/arguments">Argument tips</a>
          <span className="contribute-charcount"><span className="cc-len">{body.length}</span> / 280</span>
        </div>
        <textarea ref={textareaRef} className="contribute-textarea" maxLength={280} rows={3} aria-labelledby={`contribute-label-${featuredId}-${side}`} placeholder={`Add a short ${copy.adjective}-argument (one sentence, max 280 characters)…`} value={body} onChange={(event) => setBody(event.target.value)} />
        <div className="contribute-actions">
          <button type="button" className="btn-secondary contribute-skip-btn" disabled={skip.isPending} onClick={() => skip.mutate()}>Nothing to add</button>
          <button type="submit" className="btn-primary contribute-submit-btn" disabled={!body.length || submit.isPending}>Submit argument</button>
        </div>
      </form>
      <div className={`at-contribute at-contribute--done contribute-submitted contribute-submitted--${side}`}>
        <span className="at-contribute-glyph"><svg width="11" height="9" viewBox="0 0 13 10" fill="none" aria-hidden="true"><path d="M1 5L4.5 8.5L12 1" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg></span>
        You added one argument {copy.adjective}
      </div>
      <div className="at-contribute at-contribute--skipped contribute-skipped">
        <span className="at-contribute-glyph" aria-hidden="true">↷</span>
        Nothing to add
        <button type="button" className="at-link contribute-changemind" onClick={compose}>change my mind</button>
      </div>
      {(submit.error || skip.error) && <p className="muted" role="alert">Could not save your response. Please try again.</p>}
    </div>
  );
}

function PickMark() {
  return <svg width="10" height="8" viewBox="0 0 10 8" fill="none" aria-hidden="true"><path d="M1 4L3.5 6.5L9 1" stroke="white" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" /></svg>;
}

function ArgumentCard({mapping, slug, csrfToken, side, item, prioritization}: {
  mapping: Mapping;
  slug: string;
  csrfToken: string;
  side: SideName;
  item: ArgumentItem;
  prioritization: Side['prioritization'];
}) {
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState(item.selected);
  const [importance, setImportance] = useState(item.importanceVoteCount);
  useEffect(() => {
    setSelected(item.selected);
    setImportance(item.importanceVoteCount);
  }, [item.importanceVoteCount, item.selected]);
  const priority = useMutation({
    mutationFn: (next: boolean) => putArgumentPriority(slug, item.id, next, csrfToken),
    onMutate: (next) => {
      setSelected(next);
      setImportance((count) => Math.max(0, count + (next ? 1 : -1)));
    },
    onError: (_error, next) => {
      setSelected(!next);
      setImportance((count) => Math.max(0, count + (next ? -1 : 1)));
    },
    onSuccess: () => queryClient.invalidateQueries(argumentMappingQuery(slug)),
  });
  const moderate = useMutation({
    mutationFn: () => putAdminFeaturedArgument(
      mapping.conversationId, item.id, {hidden: !item.hidden}, csrfToken,
    ),
    onSuccess: () => queryClient.invalidateQueries(argumentMappingQuery(slug)),
  });
  const limitReached = item.capabilities.prioritize
    && prioritization.selectedCount >= prioritization.selectionBudget
    && !selected;
  const volumeLocked = !item.hidden
    && !item.capabilities.prioritize
    && prioritization.argumentCount < prioritization.requiredArgumentCount;

  function toggle(event: MouseEvent<HTMLElement>) {
    if ((event.target as HTMLElement).closest('form, .btn-small, .content-flag')) return;
    if (!item.capabilities.prioritize || limitReached || priority.isPending) return;
    priority.mutate(!selected);
  }

  return (
    <div className="at-card argument-card" data-side={side} data-arg-id={item.id} data-picked={selected} data-own={item.own} data-can-vote={item.capabilities.prioritize} data-limit-reached={limitReached} data-hidden={item.hidden} onClick={toggle}>
      <button className="at-pick argument-checkbox" type="button" aria-pressed={selected} aria-label={selected ? 'Unmark as most important' : 'Mark as most important'} aria-hidden={item.hidden || undefined} aria-disabled={volumeLocked || undefined} tabIndex={item.hidden ? -1 : item.capabilities.prioritize || volumeLocked ? 0 : -1}>
        {selected && <PickMark />}
      </button>
      <div className="at-card-body argument-body">
        <p className="at-card-text argument-text">{item.body}</p>
        <div className="at-card-meta argument-meta">
          <span className="at-star argument-importance">
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>
            <strong className="importance-count">{importance}</strong><span className="sr-only"> importance votes</span>
          </span>
          {item.own && <span className="at-yours argument-yours">YOURS</span>}
          {item.hidden && <span className="at-hidden-badge argument-hidden-badge">HIDDEN</span>}
          {item.capabilities.flag && <LegacyContentFlag slug={slug} target={{contentType: 'argument', targetId: item.id}} label="argument" csrfToken={csrfToken} />}
          {item.capabilities.moderate && <span style={{display: 'inline-flex', gap: 4, marginLeft: 'auto'}}><button type="button" className={`btn-small${item.hidden ? '' : ' btn-warn'}`} disabled={moderate.isPending} onClick={(event) => { event.stopPropagation(); moderate.mutate(); }}>{item.hidden ? 'unhide' : 'hide'}</button></span>}
        </div>
      </div>
    </div>
  );
}

function ArgumentColumn({mapping, slug, csrfToken, card, side}: {
  mapping: Mapping;
  slug: string;
  csrfToken: string;
  card: Featured;
  side: SideName;
}) {
  const value = card.sides[side];
  const copy = sideCopy[side];
  const gate = value.contribution.status !== 'pending';
  const voteReady = value.prioritization.available;
  return (
    <div className={`at-col at-col--${copy.className}`}>
      <div className="at-col-head"><span className="at-col-sign" aria-hidden="true">{copy.sign}</span><span className="at-col-label">{copy.label}</span><span className="at-col-count">{value.arguments.length}</span></div>
      <Contribution slug={slug} csrfToken={csrfToken} featuredId={card.id} side={side} value={value.contribution} />
      {!gate && value.arguments.length === 0 && <p className="at-col-note">Other arguments appear here once you've added yours or skipped — so you form your own view first.</p>}
      {value.arguments.map((item) => <ArgumentCard key={item.id} mapping={mapping} slug={slug} csrfToken={csrfToken} side={side} item={item} prioritization={value.prioritization} />)}
      {card.contributionsComplete && !voteReady && <div className="at-volnote" id={`volnote-${side}-${card.id}`}><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 9v4M12 17h.01" /><path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" /></svg><span>Prioritising unlocks once there are more than {value.prioritization.selectionBudget} {copy.adjective}-arguments ({value.arguments.length} so far).</span></div>}
    </div>
  );
}

function Circle({state, number, current, onClick}: {state: 'none' | 'half' | 'complete'; number: number; current: boolean; onClick: () => void}) {
  return (
    <svg className="at-circle" viewBox="0 0 36 36" role="img" aria-label={`Statement ${number}: ${state}`} onClick={onClick}>
      <circle cx="18" cy="18" r="15" fill={state === 'complete' ? 'var(--spot, #fef3c7)' : 'var(--surface, #fff)'} stroke={current ? 'var(--ink, #2c3e6b)' : state === 'none' ? 'var(--muted, #9ca3af)' : 'var(--pass, #3b5bdb)'} strokeWidth={current ? 3 : 2} />
      {state === 'half' && <path d="M18 3 A15 15 0 0 0 18 33 Z" fill="var(--spot, #fef3c7)" opacity=".75" />}
      <text x="18" y="22" textAnchor="middle" className="at-circle-label" fill={state === 'complete' ? 'var(--blue-dark, #1e3a8a)' : 'var(--pass, #3b5bdb)'} aria-hidden="true">{number}</text>
    </svg>
  );
}

function panelState(card: Featured): 'none' | 'half' | 'complete' {
  return card.complete ? 'complete' : card.contributionsComplete ? 'half' : 'none';
}

function FeaturedPanel({mapping, slug, csrfToken, card, index, currentIndex, setIndex}: {
  mapping: Mapping;
  slug: string;
  csrfToken: string;
  card: Featured;
  index: number;
  currentIndex: number;
  setIndex: (index: number) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const complete = mapping.progress.allDone;
  const pro = card.sides.pro.prioritization;
  const con = card.sides.con.prioritization;
  const stepOneSub = card.contributionsComplete ? 'for ✓ · against ✓' : `${card.sides.pro.contribution.status === 'pending' ? 'for' : 'for ✓'} · ${card.sides.con.contribution.status === 'pending' ? 'against' : 'against ✓'}`;
  return (
    <div className={`at-panel arg-block${index !== currentIndex ? ' arg-block--hidden' : ''}${complete ? ' at-panel--done' : ''}${expanded ? ' at-panel--expanded' : ''}`} id={`fs-${card.id}`} tabIndex={-1} data-index={index} aria-hidden={index !== currentIndex || undefined}>
      <div className="at-head" {...(complete ? {role: 'button', tabIndex: 0, 'aria-expanded': expanded, 'aria-label': expanded ? 'Collapse this statement panel' : 'Expand this statement panel', onClick: () => setExpanded(!expanded)} : {})}>
        <div className="at-head-main">
          <LegacyContentFlag slug={slug} target={{contentType: 'statement', targetId: card.statement.id}} label={`statement-${card.id}`} csrfToken={csrfToken} corner />
          <div className="at-featured-label" aria-hidden="true"><svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><path d="m12 2 3 7 7 .5-5.5 4.5 2 7-6.5-4-6.5 4 2-7L2 9.5 9 9z" /></svg>Featured statement</div>
          <p className="at-stmt">{card.statement.text}</p>
        </div>
        <div className="at-steps" id={`steps-${card.id}`}>
          <div className={`at-step ${card.contributionsComplete ? 'at-step--done' : 'at-step--active'}`} id={`step1-${card.id}`}><span className="at-step-num">{card.contributionsComplete ? '✓' : '1'}</span><div><div className="at-step-name">1 · Add arguments</div><div className="at-step-sub" id={`step1-sub-${card.id}`}>{stepOneSub}</div></div></div>
          <div className={`at-step ${card.contributionsComplete ? 'at-step--active' : 'at-step--locked'}`} id={`step2-${card.id}`}><span className="at-step-num">{card.contributionsComplete ? '2' : '🔒'}</span><div><div className="at-step-name">2 · Prioritise</div><div className="at-step-sub" id={`step2-sub-${card.id}`}>{card.contributionsComplete ? `Mark the most important — ${pro.selectedCount} of ${pro.selectionBudget} for, ${con.selectedCount} of ${con.selectionBudget} against · you can still change these` : 'Unlocks after step 1'}</div></div></div>
        </div>
        <span className="at-collapse-chevron" aria-hidden="true" hidden={!complete}>{expanded ? '▲' : '▼'}</span>
      </div>
      <div className="at-cols"><ArgumentColumn mapping={mapping} slug={slug} csrfToken={csrfToken} card={card} side="pro" /><div className="at-rule" aria-hidden="true" /><ArgumentColumn mapping={mapping} slug={slug} csrfToken={csrfToken} card={card} side="con" /></div>
      <div className="at-nav">
        <button className="at-navbtn at-navbtn--prev" type="button" disabled={index === 0} aria-label="Previous statement" onClick={() => setIndex(index - 1)}>← Previous</button>
        <div className="at-circles" role="group" aria-label="Statement progress">{mapping.featuredStatements.map((item, circleIndex) => <Circle key={item.id} state={panelState(item)} number={circleIndex + 1} current={circleIndex === index} onClick={() => setIndex(circleIndex)} />)}</div>
        <button className="at-navbtn at-navbtn--next" type="button" disabled={index === mapping.featuredStatements.length - 1} aria-label="Next statement" onClick={() => setIndex(index + 1)}>Next →</button>
      </div>
    </div>
  );
}

export function LegacyArgumentMappingPanel({slug, csrfToken}: {slug: string; csrfToken: string}) {
  const {data} = useSuspenseQuery(argumentMappingQuery(slug));
  const [collapsed, setCollapsed] = useState(false);
  const [index, setIndex] = useState(() => {
    const match = globalThis.location.hash.match(/^#fs-(\d+)$/);
    if (!match) return 0;
    const target = Number(match[1]);
    const found = data.featuredStatements.findIndex((item) => item.id === target);
    return Math.max(0, found);
  });
  useEffect(() => {
    try {
      setCollapsed(globalThis.localStorage.getItem(`at-orient-${slug}`) === 'collapsed');
    } catch { /* storage can be unavailable without changing the default */ }
  }, [slug]);
  function toggleOrientation() {
    const next = !collapsed;
    setCollapsed(next);
    try { globalThis.localStorage.setItem(`at-orient-${slug}`, next ? 'collapsed' : 'open'); } catch { /* presentation still updates */ }
  }
  if (data.featuredStatements.length === 0) return <div className="landing-section"><p className="muted">No statements have been selected for argument mapping yet.</p></div>;
  return (
    <>
      <p className="sr-only" id="arg-alert" role="alert" />
      <div className={`at-orient${collapsed ? ' at-collapsed' : ''}`} id={`at-orient-${slug}`}>
        <span className="at-orient-icon" aria-hidden="true">?</span>
        <div className="at-orient-body" id={`at-orient-body-${slug}`}>
          <div className="at-orient-full"><strong>This isn't another vote — it's a short writing task.</strong>{' '}These are the statements that divided people most. For each one, add one argument <em>for</em> and one <em>against</em> (or skip a side), then mark the arguments — from anyone — you find most important.</div>
          <div className="at-orient-mini">What is this tab? <strong>A two-step task on the most divisive statements.</strong></div>
        </div>
        <button className="at-orient-toggle" type="button" aria-expanded={!collapsed} aria-controls={`at-orient-body-${slug}`} onClick={toggleOrientation}>{collapsed ? <>what is this? <span aria-hidden="true">▼</span></> : <>collapse <span aria-hidden="true">▲</span></>}</button>
      </div>
      <div className="at-complete" id="at-complete" hidden={!data.progress.allDone}><div className="interlude"><span className="interlude-glyph"><svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M20 6 9 17l-5-5" /></svg></span><h2 className="interlude-title">You've been through all of them</h2><p className="interlude-sub">Nice work. Review the importance choices below where they are available.</p></div></div>
      <div className="arg-panels">{data.featuredStatements.map((card, cardIndex) => <FeaturedPanel key={card.id} mapping={data} slug={slug} csrfToken={csrfToken} card={card} index={cardIndex} currentIndex={index} setIndex={setIndex} />)}</div>
    </>
  );
}

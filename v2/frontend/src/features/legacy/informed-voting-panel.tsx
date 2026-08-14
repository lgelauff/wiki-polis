import {useEffect, useRef, useState} from 'react';
import {useMutation, useSuspenseQuery} from '@tanstack/react-query';

import type {components} from '../../api/schema';
import {informedVotingQuery, putInformedVote} from '../../api/queries';

type Workspace = components['schemas']['ConversationWorkspace'];
type Card = components['schemas']['InformedVotingCard'];
type Choice = components['schemas']['InformedVoteRequest']['choice'];

const voteValues: Array<{choice: Choice; value: number; label: string}> = [
  {choice: 'agree', value: 1, label: 'Agree'},
  {choice: 'pass', value: 0, label: 'Pass'},
  {choice: 'disagree', value: -1, label: 'Disagree'},
];

function ArgumentSide({side, items}: {
  side: 'pro' | 'con';
  items: Card['arguments']['for'];
}) {
  const visible = items.slice(0, 3);
  const more = items.slice(3);
  return (
    <div className={`p6-args-side p6-args-side--${side}`}>
      <h3 className="p6-args-side-header">{side === 'pro' ? 'For' : 'Against'}</h3>
      {items.length === 0 ? <p className="p6-args-empty">No arguments yet.</p> : <>
        {visible.map((argument) => <p className="p6-arg-item" key={argument.id}>{argument.body}</p>)}
        {more.length > 0 && <details className="p6-args-more">
          <summary>{more.length} more</summary>
          {more.map((argument) => <p className="p6-arg-item" key={argument.id}>{argument.body}</p>)}
        </details>}
      </>}
    </div>
  );
}

function Completion({workspace, onSelectPreliminary}: {
  workspace: Workspace;
  onSelectPreliminary: () => void;
}) {
  const hasPreliminaryResults = workspace.tabs.some((tab) => tab.key === 'p6-results');
  const deliberationOpen = workspace.tabs.some((tab) => tab.key === 'vote' || tab.key === 'arguments');
  return (
    <div className="p6-done">
      <h2 className="p6-done-heading">You've completed informed voting.</h2>
      {hasPreliminaryResults ? (
        <p className="p6-done-text">See the <a href="#" onClick={(event) => { event.preventDefault(); onSelectPreliminary(); }}>Preliminary results</a> tab for the full comparison.</p>
      ) : deliberationOpen ? (
        <p className="p6-done-text">The deliberation is still open — come back if new arguments are added.</p>
      ) : workspace.status === 'open' ? (
        <p className="p6-done-text">The results report will be published here once this consultation closes.</p>
      ) : (
        <p className="p6-done-text">This consultation is now closed. <a href={workspace.links.results}>Read the final report <span aria-hidden="true">→</span></a></p>
      )}
      {workspace.reveal?.state === 'open' ? (
        <p className="p6-done-reveal p6-done-reveal--open">Your votes are recorded under pseudonym <strong>{workspace.viewer.pseudonym}</strong>. The identity reveal window is open — <a href={`/app/conversations/${workspace.slug}/identity-reveal`}>optionally link your username <span aria-hidden="true">→</span></a></p>
      ) : workspace.reveal?.state !== 'revealed' && workspace.reveal?.state !== 'expired' ? (
        <p className="p6-done-reveal">Your votes are recorded under pseudonym <strong>{workspace.viewer.pseudonym}</strong>. Once this consultation closes, you will have a limited window to optionally link your Wikimedia username. You cannot make that decision yet.</p>
      ) : null}
    </div>
  );
}

export function LegacyInformedVotingPanel({workspace, csrfToken, onSelectPreliminary}: {
  workspace: Workspace;
  csrfToken: string;
  onSelectPreliminary: () => void;
}) {
  const {data} = useSuspenseQuery(informedVotingQuery(workspace.slug));
  const [currentIndex, setCurrentIndex] = useState(0);
  const [votes, setVotes] = useState<Record<number, Choice>>({});
  const [terminalIds, setTerminalIds] = useState<Set<number>>(() => new Set());
  const [networkErrorId, setNetworkErrorId] = useState<number | null>(null);
  const [done, setDone] = useState(false);
  const advanceTimer = useRef<number | null>(null);
  const current = data.cards[currentIndex];

  useEffect(() => () => {
    if (advanceTimer.current !== null) globalThis.clearTimeout(advanceTimer.current);
  }, []);

  function showCard(index: number) {
    setCurrentIndex(index);
    globalThis.requestAnimationFrame(() => {
      const card = document.querySelector<HTMLElement>(`.p6-card[data-fs-id="${data.cards[index]?.featuredStatementId}"]`);
      card?.scrollIntoView({behavior: globalThis.matchMedia?.('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start'});
      card?.querySelector<HTMLElement>('[data-focus-anchor]')?.focus({preventScroll: true});
    });
  }

  const vote = useMutation({
    mutationFn: ({card, choice}: {card: Card; choice: Choice}) => (
      putInformedVote(workspace.slug, card.featuredStatementId, {choice}, csrfToken)
    ),
    onSuccess: (receipt) => {
      const nextTerminal = new Set(terminalIds).add(receipt.featuredStatementId);
      setVotes((existing) => ({...existing, [receipt.featuredStatementId]: receipt.choice}));
      setTerminalIds(nextTerminal);
      setNetworkErrorId(null);
      if (nextTerminal.size === data.cards.length) setDone(true);
      const forward = data.cards.findIndex((card, index) => index > currentIndex && !nextTerminal.has(card.featuredStatementId));
      const wrapped = forward < 0 ? data.cards.findIndex((card) => !nextTerminal.has(card.featuredStatementId)) : forward;
      if (wrapped >= 0) {
        advanceTimer.current = globalThis.setTimeout(() => showCard(wrapped), 400);
      } else {
        advanceTimer.current = globalThis.setTimeout(() => {
          document.querySelector<HTMLElement>('.p6-done')?.scrollIntoView({behavior: globalThis.matchMedia?.('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start'});
        }, 400);
      }
    },
    onError: (_error, variables) => setNetworkErrorId(variables.card.featuredStatementId),
  });

  if (data.cards.length === 0) return <div className="landing-section"><p className="muted">No statements are available for informed voting yet.</p></div>;

  return <>
    {data.cards.map((card, index) => {
      const selected = votes[card.featuredStatementId];
      const error = networkErrorId === card.featuredStatementId;
      return <div className={`p6-card${index !== currentIndex ? ' p6-card--hidden' : ''}${selected ? ' p6-card--voted' : ''}${terminalIds.has(card.featuredStatementId) ? ' p6-card--done' : ''}`} data-fs-id={card.featuredStatementId} key={card.featuredStatementId}>
        <div tabIndex={-1} data-focus-anchor className="sr-only" />
        <div className="p6-card-header">
          <span className="stmt-meta-left"><span className="stmt-dot" />INFORMED VOTE · {index + 1} of {data.cards.length}</span>
          <span className={`p6-voted-badge${selected ? ` p6-voted-badge--${selected}` : ''}`} role="alert" hidden={!selected && !error}>{selected ? <><span aria-hidden="true">✓</span> {selected === 'agree' ? 'Agreed' : selected === 'disagree' ? 'Disagreed' : 'Passed'}</> : 'Network error — try again'}</span>
        </div>
        <div className="p6-card-inner">
          <div className="p6-statement-col">
            <p className="p6-statement-text">{card.statement}</p>
            {card.canVote && <div className="vote-choice-row p6-vote-row">
              {voteValues.map((item) => <button type="button" className={`vote-choice btn-p6-vote${selected === item.choice ? ' p6-voted' : ''}`} data-vote={item.value} disabled={vote.isPending && vote.variables?.card.featuredStatementId === card.featuredStatementId} onClick={() => vote.mutate({card, choice: item.choice})} key={item.choice}><span className={`vote-dot vote-dot--${item.choice}`} />{item.label}</button>)}
            </div>}
          </div>
          <div className="p6-args-panel">
            <ArgumentSide side="pro" items={card.arguments.for} />
            <ArgumentSide side="con" items={card.arguments.against} />
          </div>
        </div>
        <div className="p6-nav">
          <button type="button" className="p6-navbtn p6-navbtn--prev" disabled={currentIndex === 0} onClick={() => showCard(currentIndex - 1)}>← Previous</button>
          <span className="p6-nav-counter" aria-live="polite">{currentIndex + 1} of {data.cards.length}</span>
          <button type="button" className="p6-navbtn p6-navbtn--next" disabled={currentIndex === data.cards.length - 1} onClick={() => showCard(currentIndex + 1)}>Next →</button>
        </div>
      </div>;
    })}
    {done && <Completion workspace={workspace} onSelectPreliminary={onSelectPreliminary} />}
  </>;
}

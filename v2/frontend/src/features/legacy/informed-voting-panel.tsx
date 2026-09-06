import {useEffect, useRef, useState} from 'react';
import {useMutation, useSuspenseQuery} from '@tanstack/react-query';

import type {components} from '../../api/schema';
import {informedVotingQuery, putInformedVote} from '../../api/queries';
import {InternalLink} from '../../internal-link';

type Workspace = components['schemas']['ConversationWorkspace'];
type Card = components['schemas']['InformedVotingCard'];
type Choice = components['schemas']['InformedVoteRequest']['choice'];

// `value` is only the rendered data-vote attribute — the wire payload is the
// `choice` string, mapped server-side. It still follows the Polis convention
// (-1 = agree) so the SPA and the legacy template emit identical DOM.
const voteValues: Array<{choice: Choice; value: number; label: string}> = [
  {choice: 'agree', value: -1, label: 'Agree'},
  {choice: 'pass', value: 0, label: 'Pass'},
  {choice: 'disagree', value: 1, label: 'Disagree'},
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
        <p className="p6-done-text">See the <InternalLink href="#" onClick={(event) => { event.preventDefault(); onSelectPreliminary(); }}>Preliminary results</InternalLink> tab for the full comparison.</p>
      ) : deliberationOpen ? (
        <p className="p6-done-text">The deliberation is still open — come back if new arguments are added.</p>
      ) : workspace.status === 'open' ? (
        <p className="p6-done-text">The results report will be published here once this consultation closes.</p>
      ) : (
        <p className="p6-done-text">This consultation is now closed. <InternalLink href={workspace.links.results}>Read the final report <span aria-hidden="true">→</span></InternalLink></p>
      )}
      {workspace.reveal?.state === 'open' ? (
        <p className="p6-done-reveal p6-done-reveal--open">Your votes are recorded under pseudonym <strong>{workspace.viewer.pseudonym}</strong>. The identity reveal window is open — <InternalLink href={`/c/${workspace.slug}/reveal`}>optionally link your username <span aria-hidden="true">→</span></InternalLink></p>
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
  // Seed the recorded choice, so a returning participant sees what they chose rather
  // than only that they chose. Cards answered before choices were stored carry
  // choice: null and fall back to the neutral "Answered" state below.
  const [votes, setVotes] = useState<Record<number, Choice>>(
    () => Object.fromEntries(
      data.cards.filter((card) => card.choice).map((card) => [card.featuredStatementId, card.choice as Choice]),
    ),
  );
  // Seed from the server, not from an empty set. The API already reports which cards
  // this participant has answered; starting empty threw that away and rendered an
  // answered deck as untouched, which is how a returning participant ends up voting
  // twice. The choice itself is not seeded because the read contract cannot carry it
  // (#327) -- Particiapi's /participant returns vote ids only, not their values.
  const [terminalIds, setTerminalIds] = useState<Set<number>>(
    () => new Set(data.cards.filter((card) => card.voted).map((card) => card.featuredStatementId)),
  );
  const [networkErrorId, setNetworkErrorId] = useState<number | null>(null);
  // Likewise: a deck the participant already finished should open on its completion
  // panel rather than on card 1 of 3 with no sign anything happened.
  const [done, setDone] = useState(() => data.cards.length > 0 && data.cards.every((card) => card.voted));
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
    // Clear any previous failure before the new attempt, so a retry that succeeds
    // does not leave the error badge standing.
    onMutate: () => setNetworkErrorId(null),
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
          {/* Error branch first. `selected` survives a failed re-vote, so testing it
              first makes the error unreachable once a card has been voted — and a
              rejected re-vote (a 409 on a paused round, which is the state the repair
              runbook puts the tool in) would silently keep showing the old choice. */}
          <span className={`p6-voted-badge${!error && selected ? ` p6-voted-badge--${selected}` : ''}`} role="alert" hidden={!selected && !error}>{error ? 'Vote not recorded — try again' : <><span aria-hidden="true">✓</span> {selected === 'agree' ? 'Agreed' : selected === 'disagree' ? 'Disagreed' : 'Passed'}</>}</span>
          {/* Answered before this visit. The badge above needs a known choice; this one
              only claims that a vote exists, which is all the read contract supports. */}
          <span className="p6-answered-note" hidden={!!selected || error}><span aria-hidden="true">✓</span> Answered</span>
        </div>
        <div className="p6-card-inner">
          <div className="p6-statement-col">
            <p className="p6-statement-text">{card.statement}</p>
            {card.canVote && <div className="vote-choice-row p6-vote-row">
              {/* aria-pressed carries the recorded choice: without it the selection is
                  conveyed only by opacity, which no assistive technology reports. */}
              {voteValues.map((item) => <button type="button" className={`vote-choice btn-p6-vote${selected === item.choice ? ' p6-voted' : ''}`} data-vote={item.value} aria-pressed={selected === item.choice} disabled={vote.isPending && vote.variables?.card.featuredStatementId === card.featuredStatementId} onClick={() => vote.mutate({card, choice: item.choice})} key={item.choice}><span className={`vote-dot vote-dot--${item.choice}`} />{item.label}</button>)}
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

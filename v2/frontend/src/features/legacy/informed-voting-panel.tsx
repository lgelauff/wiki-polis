import {useEffect, useRef, useState} from 'react';
import {useMutation, useQueryClient, useSuspenseQuery} from '@tanstack/react-query';

import type {components} from '../../api/schema';
import {informedVotingQuery, putInformedVote} from '../../api/queries';
import {InternalLink} from '../../internal-link';
import {useMessage, type Message} from '../../i18n/messages';
import {nodeSlot, withNodes} from '../../i18n/message-nodes';

type Workspace = components['schemas']['ConversationWorkspace'];
type Card = components['schemas']['InformedVotingCard'];
type Choice = components['schemas']['InformedVoteRequest']['choice'];

// `value` is only the rendered data-vote attribute — the wire payload is the
// `choice` string, mapped server-side. It still follows the Polis convention
// (-1 = agree) so the SPA and the legacy template emit identical DOM.
const voteValues: Array<{choice: Choice; value: number}> = [
  {choice: 'agree', value: -1},
  {choice: 'pass', value: 0},
  {choice: 'disagree', value: 1},
];

/** Button labels: the same present-tense messages as the Explore tab's buttons. */
function choiceLabel(msg: Message, choice: Choice): string {
  return choice === 'agree' ? msg('conv-vote-agree')
    : choice === 'disagree' ? msg('conv-vote-disagree')
      : msg('conv-vote-pass');
}

/** The confirmation once a vote is saved reports it, so it is past tense: "Agreed", not the
 *  button's "Agree". Separate messages, because the tense is the point of the difference. */
function recordedLabel(msg: Message, choice: Choice): string {
  return choice === 'agree' ? msg('conv-p6-voted-agree')
    : choice === 'disagree' ? msg('conv-p6-voted-disagree')
      : msg('conv-p6-voted-pass');
}

/** A card the participant can still answer. A card without vote controls (`canVote` false:
 *  its phase-6 statement does not exist yet) can never be answered, so no seek may stop on
 *  it and it does not count towards completion (#319). */
function stillToAnswer(card: Card, answered: Set<number>): boolean {
  return card.canVote && !answered.has(card.featuredStatementId);
}

function ArgumentSide({side, items}: {
  side: 'pro' | 'con';
  items: Card['arguments']['for'];
}) {
  const msg = useMessage();
  const visible = items.slice(0, 3);
  const more = items.slice(3);
  return (
    <div className={`p6-args-side p6-args-side--${side}`}>
      <h3 className="p6-args-side-header">{side === 'pro' ? msg('conv-arg-col-for') : msg('conv-arg-col-against')}</h3>
      {items.length === 0 ? <p className="p6-args-empty">{msg('conv-p6-no-args')}</p> : <>
        {visible.map((argument) => <p className="p6-arg-item" key={argument.id}>{argument.body}</p>)}
        {more.length > 0 && <details className="p6-args-more">
          <summary>{msg('conv-p6-more', more.length)}</summary>
          {more.map((argument) => <p className="p6-arg-item" key={argument.id}>{argument.body}</p>)}
        </details>}
      </>}
    </div>
  );
}

// No pointer to preliminary results: they open with the Report phase, after this round
// (owner, 2026-10-13), so a participant finishing it never has a results tab beside it.
function Completion({workspace}: {workspace: Workspace}) {
  const msg = useMessage();
  const deliberationOpen = workspace.tabs.some((tab) => tab.key === 'vote' || tab.key === 'arguments');
  return (
    <div className="p6-done">
      {/* Focusable so that finishing the deck can move focus here: the vote button that
          had it is gone with the deck. */}
      <h2 className="p6-done-heading" tabIndex={-1}>{msg('conv-p6-done-heading')}</h2>
      {/* The tabs, and so this panel, exist only while the consultation is open; a closed
          one renders ClosedWorkspace instead (#402). */}
      <p className="p6-done-text">{deliberationOpen ? msg('conv-p6-done-open') : msg('conv-p6-done-willpublish')}</p>
      {workspace.reveal?.state === 'open' ? (
        <p className="p6-done-reveal p6-done-reveal--open">{withNodes(msg('conv-p6-reveal-recorded', nodeSlot(0)), <strong>{workspace.viewer.pseudonym}</strong>)} {withNodes(msg('conv-p6-reveal-open', nodeSlot(0)), <InternalLink href={`/c/${workspace.slug}/reveal`}>{msg('conv-p6-reveal-link')} <span className="dir-glyph" aria-hidden="true">→</span></InternalLink>)}</p>
      ) : workspace.reveal?.state !== 'revealed' && workspace.reveal?.state !== 'expired' ? (
        <p className="p6-done-reveal">{withNodes(msg('conv-p6-reveal-recorded', nodeSlot(0)), <strong>{workspace.viewer.pseudonym}</strong>)} {msg('conv-p6-reveal-pending')}</p>
      ) : null}
    </div>
  );
}

export function LegacyInformedVotingPanel({workspace, csrfToken}: {
  workspace: Workspace;
  csrfToken: string;
}) {
  const msg = useMessage();
  const {data} = useSuspenseQuery(informedVotingQuery(workspace.slug));
  const queryClient = useQueryClient();
  // The current card is held by its id, not its position: a refetch can add, remove or
  // reorder cards, and a position then points at a different card (#319). Open on the
  // first card still to answer, so a participant who comes back mid-deck is not put back
  // on a card they already answered (#317). With every card answered this is null; the
  // completion panel is what shows then.
  const [currentId, setCurrentId] = useState<number | null>(
    () => data.cards.find((card) => card.canVote && !card.voted)?.featuredStatementId ?? null,
  );
  const [votes, setVotes] = useState<Record<number, Choice>>({});
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
  // panel rather than on card 1 of 3 with no sign anything happened. Worked out from the
  // deck on every render, not stored, so a refetch that brings a newly votable card
  // (a statement initialised mid-round) shows that card again.
  const done = data.cards.some((card) => card.canVote) && data.cards.every((card) => (
    !card.canVote || card.voted || terminalIds.has(card.featuredStatementId)
  ));
  // True only in the pause after the last answer, so its confirmation is seen before the
  // deck gives way to the completion panel.
  const [finishing, setFinishing] = useState(false);
  const advanceTimer = useRef<number | null>(null);
  const firstOpenId = data.cards.find((card) => (
    card.canVote && !card.voted && !terminalIds.has(card.featuredStatementId)
  ))?.featuredStatementId ?? null;
  // A finished deck that a refetch reopens (a statement initialised mid-round) goes to the
  // card that reopened it, not to whichever card was current when it finished (#319).
  // Adjusted during render, as React advises for state derived from a change in props.
  const [wasDone, setWasDone] = useState(done);
  if (wasDone !== done) {
    setWasDone(done);
    if (!done && firstOpenId !== null) setCurrentId(firstOpenId);
  }
  // A current card the deck no longer holds (a statement unfeatured mid-session) gives way
  // to the first card still to answer, then to the first card: never to no card at all,
  // which would hide the navigation too (#319).
  const held = data.cards.findIndex((card) => card.featuredStatementId === currentId);
  const index = held >= 0 ? held : Math.max(0, data.cards.findIndex((card) => card.featuredStatementId === firstOpenId));

  useEffect(() => () => {
    if (advanceTimer.current !== null) globalThis.clearTimeout(advanceTimer.current);
  }, []);

  function showCard(id: number) {
    setCurrentId(id);
    globalThis.requestAnimationFrame(() => {
      const card = document.querySelector<HTMLElement>(`.p6-card[data-fs-id="${id}"]`);
      card?.scrollIntoView({behavior: globalThis.matchMedia?.('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start'});
      card?.querySelector<HTMLElement>('[data-focus-anchor]')?.focus({preventScroll: true});
    });
  }

  const vote = useMutation({
    mutationFn: ({card, choice}: {card: Card; choice: Choice}) => (
      putInformedVote(workspace.slug, card.featuredStatementId, {choice}, csrfToken)
    ),
    onSuccess: (receipt) => {
      if (advanceTimer.current !== null) globalThis.clearTimeout(advanceTimer.current);
      const nextTerminal = new Set(terminalIds).add(receipt.featuredStatementId);
      setVotes((existing) => ({...existing, [receipt.featuredStatementId]: receipt.choice}));
      setTerminalIds(nextTerminal);
      setNetworkErrorId(null);
      // The cached deck still says this card is unvoted. Leaving the tab and coming back
      // re-seeds the panel from that cache on its first render, which put the participant
      // back on the card they had just answered (#317). Mark it answered in the cache at
      // once, so no tab switch can race a refetch, then let the server have the last word.
      const {queryKey} = informedVotingQuery(workspace.slug);
      queryClient.setQueryData(queryKey, (deck) => {
        if (!deck) return deck;
        const cards = deck.cards.map((card) => (
          card.featuredStatementId === receipt.featuredStatementId ? {...card, voted: true} : card
        ));
        // Counted as the server counts: only the cards that can be answered.
        const votable = cards.filter((card) => card.canVote);
        const completed = votable.filter((card) => card.voted).length;
        return {...deck, cards, progress: {
          ...deck.progress, completed, total: votable.length, remaining: votable.length - completed,
          allDone: votable.length > 0 && completed === votable.length,
        }};
      });
      void queryClient.invalidateQueries({queryKey});
      const from = receipt.featuredStatementId;
      const at = data.cards.findIndex((card) => card.featuredStatementId === from);
      const forward = data.cards.find((card, position) => position > at && stillToAnswer(card, nextTerminal));
      const wrapped = forward ?? data.cards.find((card) => stillToAnswer(card, nextTerminal));
      if (wrapped) {
        const target = wrapped.featuredStatementId;
        advanceTimer.current = globalThis.setTimeout(() => showCard(target), 400);
      } else {
        // The last answer: the deck gives way to the completion panel, after the same pause
        // as an advance so the confirmation badge is seen first.
        setFinishing(true);
        advanceTimer.current = globalThis.setTimeout(() => {
          setFinishing(false);
          globalThis.requestAnimationFrame(() => {
            document.querySelector<HTMLElement>('.p6-done')?.scrollIntoView({behavior: globalThis.matchMedia?.('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start'});
            document.querySelector<HTMLElement>('.p6-done-heading')?.focus({preventScroll: true});
          });
        }, 400);
      }
    },
    // Clear any previous failure before the new attempt, so a retry that succeeds
    // does not leave the error badge standing.
    onMutate: () => setNetworkErrorId(null),
    onError: (_error, variables) => setNetworkErrorId(variables.card.featuredStatementId),
  });

  if (data.cards.length === 0) return <div className="landing-section"><p className="muted">{msg('conv-p6-none')}</p></div>;

  // A finished deck shows only its completion panel: card 1 with live vote buttons above
  // "You've given your informed opinion" invited overwriting a recorded vote (#319).
  return <>
    {(!done || finishing) && data.cards.map((card, position) => {
      const selected = votes[card.featuredStatementId];
      const error = networkErrorId === card.featuredStatementId;
      // Answered in an earlier visit: the server says there is a vote, but the read
      // contract cannot say which (#327). Distinct from `selected`, which is this
      // session's own choice and does carry a value.
      const answeredEarlier = !selected && !error && terminalIds.has(card.featuredStatementId);
      return <div className={`p6-card${position !== index ? ' p6-card--hidden' : ''}${selected ? ' p6-card--voted' : ''}${terminalIds.has(card.featuredStatementId) ? ' p6-card--done' : ''}`} data-fs-id={card.featuredStatementId} key={card.featuredStatementId}>
        <div tabIndex={-1} data-focus-anchor className="sr-only" />
        <div className="p6-card-header">
          <span className="stmt-meta-left"><span className="stmt-dot" />{msg('conv-p6-label')} · {msg('conv-of', position + 1, data.cards.length)}</span>
          {/* Error branch first. `selected` survives a failed re-vote, so testing it
              first makes the error unreachable once a card has been voted — and a
              rejected re-vote (a 409 on a paused round, which is the state the repair
              runbook puts the tool in) would silently keep showing the old choice. */}
          <span className={`p6-voted-badge${!error && selected ? ` p6-voted-badge--${selected}` : ''}`} role="alert" hidden={!selected && !error}>{error ? msg('conv-p6-vote-failed') : <><span aria-hidden="true">✓</span> {selected ? recordedLabel(msg, selected) : null}</>}</span>
          {/* Answered before this visit. The badge above needs a known choice; this one
              only claims that a vote exists, which is all the read contract supports.
              Gated here rather than in CSS: the stylesheet is not loaded under test, so a
              CSS-only gate is both untestable and one typo away from claiming every
              untouched card is answered. */}
          <span className="p6-answered-note" id={`answered-${card.featuredStatementId}`}
                hidden={!answeredEarlier}><span aria-hidden="true">✓</span> {msg('conv-p6-already-voted')}</span>
        </div>
        <div className="p6-card-inner">
          <div className="p6-statement-col">
            {/* The statement heads its card: page <h1>, then this <h2>, then the "In favour"
                and "Against" <h3>s below it, so the outline skips no level (#157). */}
            <h2 className="p6-statement-text">{card.statement}</h2>
            {answeredEarlier && <p className="p6-answered-hint">
              {msg('conv-p6-already-voted-hint')}
            </p>}
            {card.canVote && <div className="vote-choice-row p6-vote-row"
                 aria-describedby={answeredEarlier ? `answered-${card.featuredStatementId}` : undefined}>
              {/* aria-pressed carries the recorded choice: without it the selection is
                  conveyed only by opacity, which no assistive technology reports. */}
              {voteValues.map((item) => <button type="button" className={`vote-choice btn-p6-vote${selected === item.choice ? ' p6-voted' : ''}`} data-vote={item.value} aria-pressed={selected ? selected === item.choice : undefined} disabled={vote.isPending && vote.variables?.card.featuredStatementId === card.featuredStatementId} onClick={() => vote.mutate({card, choice: item.choice})} key={item.choice}><span className={`vote-dot vote-dot--${item.choice}`} />{choiceLabel(msg, item.choice)}</button>)}
            </div>}
          </div>
          <div className="p6-args-panel">
            <ArgumentSide side="pro" items={card.arguments.for} />
            <ArgumentSide side="con" items={card.arguments.against} />
          </div>
        </div>
        <div className="p6-nav">
          <button type="button" className="p6-navbtn p6-navbtn--prev" disabled={index === 0} aria-label={msg('conv-nav-prev-aria')} onClick={() => showCard(data.cards[index - 1]!.featuredStatementId)}><span className="dir-glyph" aria-hidden="true">←</span> {msg('conv-nav-prev')}</button>
          <span className="p6-nav-counter" aria-live="polite">{msg('conv-of', index + 1, data.cards.length)}</span>
          <button type="button" className="p6-navbtn p6-navbtn--next" disabled={index === data.cards.length - 1} aria-label={msg('conv-nav-next-aria')} onClick={() => showCard(data.cards[index + 1]!.featuredStatementId)}>{msg('conv-nav-next')} <span className="dir-glyph" aria-hidden="true">→</span></button>
        </div>
      </div>;
    })}
    {done && !finishing && <Completion workspace={workspace} />}
  </>;
}

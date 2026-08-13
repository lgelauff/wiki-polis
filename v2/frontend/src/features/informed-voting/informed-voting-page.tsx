import {useMemo, useState} from 'react';
import {useMutation, useSuspenseQuery} from '@tanstack/react-query';
import {Link} from 'react-router-dom';

import type {components} from '../../api/schema';
import {informedVotingQuery, putInformedVote} from '../../api/queries';

type Choice = components['schemas']['InformedVoteRequest']['choice'];
type Card = components['schemas']['InformedVotingCard'];

function ArgumentSide({label, items}: {
  label: string;
  items: components['schemas']['InformedVotingArgument'][];
}) {
  return (
    <section className="informed-arguments__side">
      <h3>{label}</h3>
      {items.length === 0 ? (
        <p className="informed-arguments__empty">No arguments were added.</p>
      ) : (
        <ol>
          {items.map((argument) => (
            <li key={argument.id}>
              <p>{argument.body}</p>
              <span>{argument.helpfulVotes} helpful {argument.helpfulVotes === 1 ? 'vote' : 'votes'}</span>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

function VoteButtons({onVote, disabled, selected}: {
  onVote: (choice: Choice) => void;
  disabled: boolean;
  selected: Choice | null;
}) {
  return (
    <div className="informed-choices" aria-label="Your informed position">
      {(['agree', 'pass', 'disagree'] as const).map((choice) => (
        <button
          key={choice}
          type="button"
          aria-pressed={selected === choice}
          disabled={disabled}
          onClick={() => onVote(choice)}
        >
          <span className={`choice-dot choice-dot--${choice}`} />
          {choice.charAt(0).toUpperCase() + choice.slice(1)}
        </button>
      ))}
    </div>
  );
}

export function InformedVotingPage({slug, csrfToken}: {
  slug: string;
  csrfToken: string;
}) {
  const {data} = useSuspenseQuery(informedVotingQuery(slug));
  const firstPending = data.cards.findIndex((card) => !card.voted);
  const [currentIndex, setCurrentIndex] = useState(firstPending < 0 ? 0 : firstPending);
  const [reviewing, setReviewing] = useState(false);
  const [receipts, setReceipts] = useState<Record<number, Choice>>({});
  const completedIds = useMemo(() => new Set([
    ...data.cards.filter((card) => card.voted).map((card) => card.featuredStatementId),
    ...Object.keys(receipts).map(Number),
  ]), [data.cards, receipts]);
  const current = data.cards[currentIndex];
  const allDone = data.cards.length > 0 && completedIds.size === data.cards.length;
  const mutation = useMutation({
    mutationFn: ({card, choice}: {card: Card; choice: Choice}) => (
      putInformedVote(slug, card.featuredStatementId, {choice}, csrfToken)
    ),
    onSuccess: (receipt) => {
      setReceipts((existing) => ({
        ...existing,
        [receipt.featuredStatementId]: receipt.choice,
      }));
      const next = data.cards.findIndex((card, index) => (
        index > currentIndex && !card.voted &&
        card.featuredStatementId !== receipt.featuredStatementId &&
        receipts[card.featuredStatementId] === undefined
      ));
      if (next >= 0) setCurrentIndex(next);
    },
  });

  return (
    <main className="informed-shell" id="main">
      <header className="informed-heading">
        <div>
          <p className="eyebrow">Informed vote · private</p>
          <h1>{data.title}</h1>
          <p>Reconsider the featured statements alongside the strongest arguments participants added.</p>
        </div>
        <nav className="activity-nav" aria-label="Conversation activity">
          {data.links.explore && <Link to={data.links.explore}>Explore</Link>}
          {data.links.arguments && <Link to={data.links.arguments}>Arguments</Link>}
          <span aria-current="page">Informed vote</span>
          <Link to={data.links.about}>About</Link>
        </nav>
      </header>

      <div className="explore-progress">
        <div><strong>{completedIds.size}</strong> of {data.cards.length} statements covered</div>
        <progress value={completedIds.size} max={Math.max(1, data.cards.length)}>
          {completedIds.size} of {data.cards.length}
        </progress>
      </div>

      {data.cards.length === 0 ? (
        <section className="informed-empty">
          <h2>No statements are available yet.</h2>
          <p>The round is open, but organizers have not provided usable featured statements.</p>
        </section>
      ) : allDone && !reviewing ? (
        <section className="informed-done" role="status">
          <p className="eyebrow">Round complete</p>
          <h2>You’ve completed informed voting.</h2>
          <p>Your votes are recorded privately under <code>{data.pseudonym}</code>. You may still review a card and change its vote while the round remains open.</p>
          <button type="button" onClick={() => { setCurrentIndex(0); setReviewing(true); }}>Review statements</button>
        </section>
      ) : current && (
        <article className="informed-card">
          <header className="informed-card__header">
            <span>Featured statement</span>
            <span>{currentIndex + 1} of {data.cards.length}</span>
          </header>
          <div className="informed-card__grid">
            <section className="informed-position">
              <h2>{current.statement}</h2>
              {(current.voted || receipts[current.featuredStatementId]) && (
                <p className="informed-receipt" role="status">
                  {receipts[current.featuredStatementId]
                    ? <>You voted <strong>{receipts[current.featuredStatementId]}</strong>.</>
                    : <>You voted previously. Choose again to change your vote.</>}
                </p>
              )}
              <VoteButtons
                selected={receipts[current.featuredStatementId] ?? null}
                disabled={mutation.isPending}
                onVote={(choice) => mutation.mutate({card: current, choice})}
              />
              {mutation.error && <p className="command-error" role="alert">{mutation.error.message}</p>}
            </section>
            <div className="informed-arguments">
              <ArgumentSide label="For" items={current.arguments.for} />
              <ArgumentSide label="Against" items={current.arguments.against} />
            </div>
          </div>
          <footer className="informed-nav">
            <button type="button" disabled={currentIndex === 0} onClick={() => setCurrentIndex((index) => index - 1)}>← Previous</button>
            <button type="button" disabled={currentIndex === data.cards.length - 1} onClick={() => setCurrentIndex((index) => index + 1)}>Next →</button>
          </footer>
        </article>
      )}

      {allDone && data.cards.length > 0 && (
        <ol className="informed-review-list" aria-label="Review informed statements">
          {data.cards.map((card, index) => (
            <li key={card.featuredStatementId}>
              <button type="button" onClick={() => { setCurrentIndex(index); setReviewing(true); }}>{card.statement}</button>
            </li>
          ))}
        </ol>
      )}
      <footer className="explore-footer">
        <span>Participating as <code>{data.pseudonym}</code></span>
        <a href={data.links.conversation}>Open legacy conversation view</a>
      </footer>
    </main>
  );
}

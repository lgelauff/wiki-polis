import {useState, type FormEvent} from 'react';
import {useMutation, useQueryClient, useSuspenseQuery} from '@tanstack/react-query';
import {Link} from 'react-router-dom';

import {
  argumentMappingQuery,
  createArgument,
  putArgumentPriority,
  skipArgumentContribution,
} from '../../api/queries';
import type {components} from '../../api/schema';

type ArgumentMapping = components['schemas']['ArgumentMapping'];
type FeaturedStatement = components['schemas']['ArgumentFeaturedStatement'];
type ArgumentSide = components['schemas']['ArgumentSide'];
type SideName = 'pro' | 'con';

const sideLabels: Record<SideName, string> = {pro: 'For', con: 'Against'};

function ContributionControl({
  slug,
  csrfToken,
  featuredStatementId,
  side,
  contribution,
}: {
  slug: string;
  csrfToken: string;
  featuredStatementId: number;
  side: SideName;
  contribution: ArgumentSide['contribution'];
}) {
  const queryClient = useQueryClient();
  const [composing, setComposing] = useState(false);
  const [body, setBody] = useState('');
  const submit = useMutation({
    mutationFn: () => createArgument(
      slug, featuredStatementId, {side, body: body.trim()}, csrfToken,
    ),
    onSuccess: () => queryClient.invalidateQueries(argumentMappingQuery(slug)),
  });
  const skip = useMutation({
    mutationFn: () => skipArgumentContribution(
      slug, featuredStatementId, side, csrfToken,
    ),
    onSuccess: () => queryClient.invalidateQueries(argumentMappingQuery(slug)),
  });
  const effectiveStatus = submit.data ? 'submitted' : skip.data ? 'skipped' : contribution.status;
  const label = sideLabels[side];

  function submitForm(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    submit.mutate();
  }

  return (
    <div className="argument-contribution" data-status={effectiveStatus}>
      <p className="argument-contribution__status">
        <strong>{label}:</strong>{' '}
        {effectiveStatus === 'submitted'
          ? 'your argument is submitted.'
          : effectiveStatus === 'skipped'
            ? 'you chose nothing to add.'
            : 'response needed — add one argument or choose nothing to add.'}
      </p>
      {effectiveStatus === 'pending' && !composing && (
        <div className="argument-contribution__actions">
          <button type="button" onClick={() => setComposing(true)}>Add a {label.toLowerCase()} argument</button>
          <button type="button" className="composer-link" onClick={() => skip.mutate()} disabled={skip.isPending}>
            {skip.isPending ? 'Saving…' : 'Nothing to add'}
          </button>
        </div>
      )}
      {effectiveStatus === 'pending' && composing && (
        <form onSubmit={submitForm} className="argument-composer">
          <label htmlFor={`argument-${featuredStatementId}-${side}`}>
            Your {label.toLowerCase()} argument
          </label>
          <textarea
            id={`argument-${featuredStatementId}-${side}`}
            value={body}
            rows={4}
            maxLength={280}
            onChange={(event) => setBody(event.target.value)}
            disabled={submit.isPending}
            autoFocus
          />
          <div className="argument-composer__footer">
            <span>{body.trim().length}/280 · one sentence, one claim</span>
            <button type="button" className="composer-link" onClick={() => setComposing(false)}>Cancel</button>
            <button type="submit" disabled={!body.trim() || submit.isPending}>
              {submit.isPending ? 'Submitting…' : 'Submit argument'}
            </button>
          </div>
        </form>
      )}
      {(submit.error || skip.error) && (
        <p className="command-error" role="alert">{(submit.error ?? skip.error)?.message}</p>
      )}
      {(submit.data || skip.data) && (
        <p className="command-success" role="status">
          {submit.data ? `Your ${label.toLowerCase()} argument was saved.` : `${label} marked as nothing to add.`}
        </p>
      )}
    </div>
  );
}

function PriorityArguments({
  slug,
  csrfToken,
  sideName,
  side,
}: {
  slug: string;
  csrfToken: string;
  sideName: SideName;
  side: ArgumentSide;
}) {
  const queryClient = useQueryClient();
  const [notice, setNotice] = useState<string | null>(null);
  const priority = useMutation({
    mutationFn: ({argumentId, selected}: {argumentId: number; selected: boolean}) => (
      putArgumentPriority(slug, argumentId, selected, csrfToken)
    ),
    onSuccess: (receipt) => {
      setNotice(`Priority saved. ${receipt.selectedCount} of ${receipt.selectionBudget} selected.`);
      void queryClient.invalidateQueries(argumentMappingQuery(slug));
    },
  });

  return (
    <section className="argument-side" data-side={sideName} aria-labelledby={`side-${sideName}`}>
      <header className="argument-side__header">
        <h3 id={`side-${sideName}`}>{sideLabels[sideName]}</h3>
        <span>{side.arguments.length} arguments</span>
      </header>
      {side.prioritization.available ? (
        <p className="argument-side__instruction">
          Choose up to {side.prioritization.selectionBudget} most important.{' '}
          {side.prioritization.selectedCount} selected.
        </p>
      ) : (
        <p className="argument-side__instruction">
          Prioritization opens at {side.prioritization.requiredArgumentCount} arguments;{' '}
          {side.prioritization.argumentCount} available now.
        </p>
      )}
      <ul className="argument-list">
        {side.arguments.map((argument) => (
          <li key={argument.id} data-selected={argument.selected}>
            <button
              type="button"
              className="argument-priority"
              aria-pressed={argument.selected}
              aria-label={`${argument.selected ? 'Unmark' : 'Mark'} as most important: ${argument.body}`}
              disabled={!argument.capabilities.prioritize || priority.isPending}
              onClick={() => priority.mutate({
                argumentId: argument.id,
                selected: !argument.selected,
              })}
            >
              <span aria-hidden="true">{argument.selected ? '✓' : '○'}</span>
            </button>
            <p>{argument.body}</p>
            {argument.own && <span className="argument-own">Your argument</span>}
          </li>
        ))}
      </ul>
      {notice && <p className="command-success" role="status">{notice}</p>}
      {priority.error && <p className="command-error" role="alert">{priority.error.message}</p>}
    </section>
  );
}

function FeaturedTask({slug, csrfToken, card}: {
  slug: string;
  csrfToken: string;
  card: FeaturedStatement;
}) {
  return (
    <article className="argument-task">
      <header className="argument-task__statement">
        <p className="eyebrow">Featured statement</p>
        <h2>{card.statement.text}</h2>
      </header>
      <section className="argument-step" aria-labelledby="contribute-heading">
        <div className="argument-step__heading">
          <span>01</span>
          <div>
            <h2 id="contribute-heading">Contribute your own view</h2>
            <p>Respond once on each side. “Nothing to add” is an explicit, complete response.</p>
          </div>
        </div>
        <div className="argument-contribution-grid">
          {(['pro', 'con'] as const).map((side) => (
            <ContributionControl
              key={side}
              slug={slug}
              csrfToken={csrfToken}
              featuredStatementId={card.id}
              side={side}
              contribution={card.sides[side].contribution}
            />
          ))}
        </div>
      </section>
      <section className="argument-step" aria-labelledby="prioritize-heading">
        <div className="argument-step__heading">
          <span>02</span>
          <div>
            <h2 id="prioritize-heading">Prioritize what matters most</h2>
            <p>
              {card.contributionsComplete
                ? 'Review both sides and mark the arguments that should carry the most weight.'
                : 'This step unlocks after you respond on both sides.'}
            </p>
          </div>
        </div>
        {card.contributionsComplete ? (
          <div className="argument-side-grid">
            <PriorityArguments slug={slug} csrfToken={csrfToken} sideName="pro" side={card.sides.pro} />
            <PriorityArguments slug={slug} csrfToken={csrfToken} sideName="con" side={card.sides.con} />
          </div>
        ) : (
          <p className="argument-step__locked">Complete both responses above to see community arguments.</p>
        )}
      </section>
    </article>
  );
}

export function ArgumentMappingPage({slug, csrfToken}: {slug: string; csrfToken: string}) {
  const {data} = useSuspenseQuery(argumentMappingQuery(slug));
  const initialIndex = Math.max(0, data.featuredStatements.findIndex(
    (item) => item.id === data.progress.currentFeaturedStatementId,
  ));
  const [index, setIndex] = useState(initialIndex);
  const card = data.featuredStatements[index];

  return (
    <main className="arguments-shell" id="main">
      <header className="arguments-heading">
        <div>
          <p className="eyebrow">Arguments · two-step task</p>
          <h1>{data.title}</h1>
        </div>
        <nav className="activity-nav" aria-label="Conversation activity">
          {data.links.explore && <Link to={data.links.explore}>Explore</Link>}
          <span aria-current="page">Arguments</span>
          <Link to={`/app/conversations/${slug}/about`}>About</Link>
        </nav>
      </header>
      <div className="explore-progress">
        <div><strong>{data.progress.completed}</strong> of {data.progress.total} tasks complete</div>
        <progress value={data.progress.completed} max={Math.max(1, data.progress.total)}>
          {data.progress.completed} of {data.progress.total}
        </progress>
      </div>
      {card ? (
        <>
          <FeaturedTask slug={slug} csrfToken={csrfToken} card={card} />
          <nav className="argument-task-nav" aria-label="Featured statements">
            <button type="button" disabled={index === 0} onClick={() => setIndex(index - 1)}>← Previous</button>
            <span>{index + 1} / {data.featuredStatements.length}</span>
            <button type="button" disabled={index === data.featuredStatements.length - 1} onClick={() => setIndex(index + 1)}>Next →</button>
          </nav>
        </>
      ) : (
        <section className="explore-complete">
          <h2>No featured statements are ready yet.</h2>
          <p>Check back after organizers select statements for argument mapping.</p>
        </section>
      )}
      <footer className="explore-footer">
        <span>Participating as <code>{data.pseudonym}</code></span>
        <a href={data.links.conversation}>Open legacy conversation view</a>
      </footer>
    </main>
  );
}

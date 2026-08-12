import {useState, type FormEvent} from 'react';
import {useMutation} from '@tanstack/react-query';

import {ApiContractError} from '../../api/client';
import {createStatement} from '../../api/queries';
import type {components} from '../../api/schema';

type ExploreStatement = components['schemas']['ExploreStatement'];
type StatementReceipt = components['schemas']['StatementCreationReceipt'];

type StatementComposerProps = {
  slug: string;
  csrfToken: string;
  parentStatement?: ExploreStatement;
  onCancel: () => void;
  onCreated: (receipt: StatementReceipt) => void;
};

export function StatementComposer({
  slug,
  csrfToken,
  parentStatement,
  onCancel,
  onCreated,
}: StatementComposerProps) {
  const [text, setText] = useState(parentStatement?.text ?? '');
  const [idempotencyKey] = useState(() => globalThis.crypto.randomUUID());
  const mutation = useMutation({
    mutationFn: () => createStatement(slug, {
      text: text.trim(),
      ...(parentStatement ? {derivedFromStatementId: parentStatement.id} : {}),
    }, csrfToken, idempotencyKey),
  });
  const trimmedLength = text.trim().length;
  const outcomeUnknown = mutation.error instanceof ApiContractError
    && mutation.error.code === 'command_outcome_unknown';

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    mutation.mutate();
  }

  if (mutation.data) {
    return (
      <section className="statement-composer statement-composer--complete" role="status">
        <p className="eyebrow">Statement received</p>
        <h2>
          {mutation.data.kind === 'derivative'
            ? 'Your clearer wording is now available to participants.'
            : 'Your statement is now available to participants.'}
        </h2>
        <p>
          Statement <code>#{mutation.data.statementId}</code>
          {mutation.data.kind === 'new'
            ? ` · ${mutation.data.newStatementQuotaRemaining} new-statement slots remaining`
            : ' · linked to the original wording'}
        </p>
        <button type="button" className="next-statement" onClick={() => onCreated(mutation.data!)}>
          Continue voting
        </button>
      </section>
    );
  }

  return (
    <form className="statement-composer" onSubmit={submit}>
      <div className="statement-composer__heading">
        <div>
          <p className="eyebrow">
            {parentStatement ? 'Suggest clearer wording' : 'Add a new statement'}
          </p>
          <h2>{parentStatement ? 'Keep the same claim, make it clearer.' : 'Introduce one idea at a time.'}</h2>
        </div>
        <button type="button" className="composer-cancel" onClick={onCancel}>Cancel</button>
      </div>
      {parentStatement && (
        <blockquote className="statement-composer__original">
          <span>Original</span>
          {parentStatement.text}
        </blockquote>
      )}
      <label htmlFor="statement-text">Statement text</label>
      <textarea
        id="statement-text"
        value={text}
        maxLength={280}
        rows={5}
        onChange={(event) => {
          setText(event.target.value);
          if (mutation.error && !outcomeUnknown) mutation.reset();
        }}
        aria-describedby="statement-guidance statement-length"
        disabled={mutation.isPending || outcomeUnknown}
        autoFocus
      />
      <div className="statement-composer__guidance">
        <span id="statement-guidance">
          {parentStatement
            ? 'Preserve the original meaning. Substantially different claims belong in a new statement.'
            : 'Be specific, understandable on its own, and avoid combining separate claims.'}
        </span>
        <output id="statement-length" aria-live="polite">{trimmedLength}/280</output>
      </div>
      {mutation.error && (
        <p className={`command-error${outcomeUnknown ? ' command-error--uncertain' : ''}`} role="alert">
          {mutation.error.message}
          {outcomeUnknown && ' Contact a moderator before trying again.'}
        </p>
      )}
      <button
        className="statement-submit"
        type="submit"
        disabled={mutation.isPending || outcomeUnknown || trimmedLength === 0 || trimmedLength > 280}
      >
        {mutation.isPending ? 'Submitting…' : parentStatement ? 'Submit clearer wording' : 'Submit statement'}
      </button>
    </form>
  );
}

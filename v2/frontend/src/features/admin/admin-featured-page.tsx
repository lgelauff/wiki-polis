import {useState, type FormEvent} from 'react';
import {useMutation, useQueryClient, useSuspenseQuery} from '@tanstack/react-query';
import {Link} from 'react-router-dom';

import type {components} from '../../api/schema';
import {ApiContractError} from '../../api/client';
import {
  adminFeaturedWorkspaceQuery,
  deleteAdminFeaturedArgument,
  deleteAdminFeaturedSelection,
  putAdminFeaturedArgument,
  putAdminFeaturedStatement,
} from '../../api/queries';

type Workspace = components['schemas']['AdminFeaturedWorkspace'];
type Selected = components['schemas']['AdminFeaturedSelection'];
type Candidate = components['schemas']['AdminFeaturedCandidate'];

function commandError(error: Error | null, fallback: string) {
  if (!error) return null;
  return error instanceof ApiContractError ? error.message : fallback;
}

function SelectedCard({selection, conversationId, csrfToken, refresh, receipt}: {
  selection: Selected; conversationId: number; csrfToken: string;
  refresh: () => void; receipt: (message: string) => void;
}) {
  const remove = useMutation({
    mutationFn: () => deleteAdminFeaturedSelection(
      conversationId, selection.featuredId, csrfToken,
    ),
    onSuccess: () => { receipt(`Statement #${selection.statementId} removed.`); refresh(); },
  });
  const visibility = useMutation({
    mutationFn: ({id, hidden}: {id: number; hidden: boolean}) => (
      putAdminFeaturedArgument(conversationId, id, {hidden}, csrfToken)
    ),
    onSuccess: (result) => { receipt(`Argument ${result.hidden ? 'hidden' : 'restored'}.`); refresh(); },
  });
  const deletion = useMutation({
    mutationFn: (id: number) => deleteAdminFeaturedArgument(
      conversationId, id, csrfToken,
    ),
    onSuccess: () => { receipt('Argument deleted.'); refresh(); },
  });
  const activeError = remove.error ?? visibility.error ?? deletion.error;
  return (
    <article className="featured-selection">
      <header>
        <div><code>#{selection.statementId}</code>{selection.systemSuggested && <span>system candidate</span>}</div>
        <button type="button" disabled={remove.isPending} onClick={() => {
          if (globalThis.confirm('Remove this statement from the featured set?')) remove.mutate();
        }}>Remove</button>
      </header>
      <h3>{selection.text ?? 'Statement text unavailable'}</h3>
      {selection.provenance && <p className="featured-provenance">Derived from #{selection.provenance.derivedFromId}</p>}
      <section aria-label={`Arguments for statement ${selection.statementId}`}>
        <h4>Arguments <span>{selection.arguments.length}</span></h4>
        {selection.arguments.length ? <ul>{selection.arguments.map((argument) => (
          <li key={argument.id} data-hidden={argument.hidden}>
            <span>{argument.side}</span>
            <p>{argument.body}</p>
            <small>{argument.proposerPseudonym ?? 'Seeded argument'}</small>
            <div>
              <button type="button" onClick={() => visibility.mutate({id: argument.id, hidden: !argument.hidden})}>{argument.hidden ? 'Restore' : 'Hide'}</button>
              <button type="button" onClick={() => {
                if (globalThis.confirm('Delete this argument and its votes?')) deletion.mutate(argument.id);
              }}>Delete</button>
            </div>
          </li>
        ))}</ul> : <p className="featured-empty">No arguments yet.</p>}
      </section>
      {activeError && <p className="statement-admin-error" role="alert">{commandError(activeError, 'The featured selection could not be updated.')}</p>}
    </article>
  );
}

function CandidateRow({candidate, pending, onSelect}: {
  candidate: Candidate; pending: boolean; onSelect: (candidate: Candidate) => void;
}) {
  return (
    <li>
      <div className="featured-candidate__text">
        <div><code>#{candidate.statementId}</code>{candidate.seed && <span>seed</span>}</div>
        <p>{candidate.text}</p>
      </div>
      <dl>
        <div><dt>Agree</dt><dd>{candidate.votes.agree}</dd></div>
        <div><dt>Pass</dt><dd>{candidate.votes.pass}</dd></div>
        <div><dt>Disagree</dt><dd>{candidate.votes.disagree}</dd></div>
        <div><dt>Agreement</dt><dd>{candidate.votes.agreementPercent === null ? '—' : `${candidate.votes.agreementPercent}%`}</dd></div>
      </dl>
      <button type="button" disabled={pending} onClick={() => onSelect(candidate)}>Select</button>
    </li>
  );
}

export function AdminFeaturedPage({conversationId, csrfToken}: {
  conversationId: number; csrfToken: string;
}) {
  const queryClient = useQueryClient();
  const options = adminFeaturedWorkspaceQuery(conversationId);
  const {data} = useSuspenseQuery(options);
  const [manualId, setManualId] = useState('');
  const [receipt, setReceipt] = useState<string | null>(null);
  function refresh() { void queryClient.invalidateQueries({queryKey: options.queryKey}); }
  const selection = useMutation({
    mutationFn: ({id, source}: {id: number; source: 'system' | 'manual'}) => (
      putAdminFeaturedStatement(conversationId, id, {source}, csrfToken)
    ),
    onSuccess: (result) => {
      setReceipt(result.changed ? `Statement #${result.statementId} selected.` : 'Statement was already selected.');
      setManualId('');
      refresh();
    },
  });
  function submitManual(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const id = Number(manualId);
    if (Number.isInteger(id) && id >= 0) selection.mutate({id, source: 'manual'});
  }
  return (
    <main className="featured-shell" id="main">
      <nav className="record-breadcrumb" aria-label="Breadcrumb">
        <a href="/admin">Admin panel</a><span>/</span>
        <Link to={data.links.lifecycle}>{data.conversation.title}</Link><span>/</span><span>Featured</span>
      </nav>
      <header className="featured-heading">
        <div><p className="eyebrow">Argument mapping set</p><h1>Featured statements</h1><p>Select a viewpoint-preserving set to carry into argument mapping and informed voting.</p></div>
        <div><strong>{data.selected.length}</strong><span>of {data.guidance.recommendedCount} recommended</span></div>
      </header>
      <p className="featured-guidance">{data.guidance.note}</p>
      {receipt && <p className="lifecycle-receipt" role="status">{receipt}</p>}
      {selection.error && <p className="lifecycle-receipt" data-error="true" role="alert">{commandError(selection.error, 'The statement could not be selected.')}</p>}

      <section className="featured-selected" aria-labelledby="featured-selected-heading">
        <div className="lifecycle-section-heading"><div><p className="eyebrow">Selected set</p><h2 id="featured-selected-heading">Confirmed</h2></div><span>{data.selected.length}</span></div>
        {data.selected.length ? data.selected.map((row) => <SelectedCard key={row.featuredId} selection={row} conversationId={conversationId} csrfToken={csrfToken} refresh={refresh} receipt={setReceipt} />) : <p className="featured-empty">No featured statements yet.</p>}
      </section>

      <section className="featured-candidates" aria-labelledby="featured-candidates-heading">
        <div className="lifecycle-section-heading"><div><p className="eyebrow">Descriptive signals</p><h2 id="featured-candidates-heading">System candidates</h2></div></div>
        {!data.dataAvailability.candidates ? <p className="statement-admin-notice" role="status">Candidate metrics are temporarily unavailable. You can still add a verified statement ID below.</p> : data.candidates.length ? <ul>{data.candidates.map((candidate) => <CandidateRow key={candidate.statementId} candidate={candidate} pending={selection.isPending} onSelect={(row) => selection.mutate({id: row.statementId, source: 'system'})} />)}</ul> : <p className="featured-empty">No unselected candidates.</p>}
      </section>

      <section className="featured-manual" aria-labelledby="featured-manual-heading">
        <div><p className="eyebrow">Known statement</p><h2 id="featured-manual-heading">Add by statement ID</h2><p>The server verifies that the ID belongs to this conversation.</p></div>
        <form onSubmit={submitManual}><label htmlFor="featured-statement-id">Statement ID</label><input id="featured-statement-id" type="number" min="0" value={manualId} onChange={(event) => setManualId(event.target.value)} /><button type="submit" disabled={!manualId || selection.isPending}>Add verified statement</button></form>
      </section>
    </main>
  );
}

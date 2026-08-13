import {useState, type FormEvent} from 'react';
import {useMutation, useQueryClient, useSuspenseQuery} from '@tanstack/react-query';
import {Link} from 'react-router-dom';

import type {components} from '../../api/schema';
import {ApiContractError} from '../../api/client';
import {
  adminLifecycleQuery,
  createAdminPublication,
  putAdminPause,
  putAdminPhase,
  putAdminPhases,
  putAdminSchedule,
} from '../../api/queries';

type Lifecycle = components['schemas']['AdminLifecycle'];
type Readiness = Lifecycle['publicationReadiness']['preconditions'][number];

function formatStatus(value: string) {
  return value.replaceAll('_', ' ');
}

function commandError(error: Error | null) {
  if (!error) return null;
  return error instanceof ApiContractError ? error.message : 'The command could not be completed.';
}

function ReadinessList({rows, confirmed, onToggle}: {
  rows: Readiness[];
  confirmed: string[];
  onToggle: (id: string) => void;
}) {
  return (
    <ul className="lifecycle-readiness">
      {rows.map((row) => {
        const machineChecked = row.met !== null;
        return (
          <li key={row.id} data-state={row.met === false ? 'blocked' : row.met === true ? 'met' : 'confirm'}>
            <label>
              <input
                type="checkbox"
                checked={machineChecked ? row.met === true : confirmed.includes(row.id)}
                disabled={machineChecked}
                onChange={() => onToggle(row.id)}
              />
              <span>{row.label}</span>
            </label>
            {machineChecked && <strong>{row.met ? 'Verified' : 'Blocked'}</strong>}
            {row.note && <p>{row.note}</p>}
          </li>
        );
      })}
    </ul>
  );
}

function allHumanChecksConfirmed(rows: Readiness[], confirmed: string[]) {
  return rows.every((row) => row.met === true || (row.met === null && confirmed.includes(row.id)));
}

function localDateTime(value: string | null) {
  if (!value) return '';
  const date = new Date(value);
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
}

function ScheduleControl({conversationId, csrfToken, data, onChange, onReceipt}: {
  conversationId: number; csrfToken: string; data: Lifecycle;
  onChange: (lifecycle: Lifecycle) => void; onReceipt: (message: string) => void;
}) {
  const [scheduledAt, setScheduledAt] = useState(localDateTime(data.schedule.scheduledAt));
  const mutation = useMutation({
    mutationFn: (body: components['schemas']['AdminScheduleRequest']) => (
      putAdminSchedule(conversationId, body, csrfToken)
    ),
    onSuccess: (result) => {
      onChange(result.lifecycle);
      onReceipt(result.changed ? 'Schedule updated.' : 'Schedule already up to date.');
    },
  });
  const error = commandError(mutation.error);
  if (!data.schedule.canSchedule && !data.schedule.scheduledAt) return null;
  return (
    <div className="lifecycle-scheduler">
      <label htmlFor="phase-scheduled-at">Move to {data.schedule.targetLabel ?? 'next phase'} at</label>
      <input id="phase-scheduled-at" type="datetime-local" value={scheduledAt} onChange={(event) => setScheduledAt(event.target.value)} />
      <div>
        <button type="button" disabled={!scheduledAt || mutation.isPending} onClick={() => mutation.mutate({scheduledAt: new Date(scheduledAt).toISOString(), frozen: false})}>Schedule</button>
        {data.schedule.scheduledAt && <>
          <button type="button" disabled={mutation.isPending} onClick={() => mutation.mutate({scheduledAt: data.schedule.scheduledAt, frozen: !data.schedule.frozen})}>{data.schedule.frozen ? 'Unfreeze' : 'Freeze'}</button>
          <button type="button" disabled={mutation.isPending} onClick={() => mutation.mutate({scheduledAt: null, frozen: false})}>Cancel</button>
        </>}
      </div>
      {error && <p role="alert">{error}</p>}
    </div>
  );
}

function AdvancedPhaseControl({conversationId, csrfToken, data, onChange, onReceipt}: {
  conversationId: number; csrfToken: string; data: Lifecycle;
  onChange: (lifecycle: Lifecycle) => void; onReceipt: (message: string) => void;
}) {
  const [activeKeys, setActiveKeys] = useState(
    data.phase.advancedControls.filter((row) => row.active).map((row) => row.key),
  );
  const mutation = useMutation({
    mutationFn: () => putAdminPhases(conversationId, {activeKeys}, csrfToken),
    onSuccess: (result) => {
      onChange(result.lifecycle);
      onReceipt(result.changed
        ? `Advanced phases saved${result.visibilitySynced ? '.' : '; results visibility could not be synchronized.'}`
        : 'Advanced phases already up to date.');
    },
  });
  function togglePhase(key: string) {
    setActiveKeys((keys) => keys.includes(key)
      ? keys.filter((value) => value !== key)
      : [...keys, key]);
  }
  return (
    <details className="lifecycle-advanced">
      <summary>Advanced phase repair</summary>
      <div className="lifecycle-advanced__warning"><strong>Recovery control.</strong> These phases act independently, out of order, and without readiness checks.</div>
      <ul>{data.phase.advancedControls.map((row) => (
        <li key={row.key}>
          <label><input type="checkbox" checked={activeKeys.includes(row.key)} onChange={() => togglePhase(row.key)} /><span><strong>{row.label}</strong>{row.effect}</span></label>
          {row.requiresInitialization && activeKeys.includes(row.key) && !row.initialized && <p>Enabled but not initialized. Complete informed-voting setup before participants enter.</p>}
        </li>
      ))}</ul>
      <button type="button" disabled={mutation.isPending} onClick={() => mutation.mutate()}>{mutation.isPending ? 'Saving…' : 'Save advanced phases'}</button>
      {mutation.error && <p role="alert">{commandError(mutation.error)}</p>}
    </details>
  );
}

export function AdminLifecyclePage({conversationId, csrfToken}: {
  conversationId: number;
  csrfToken: string;
}) {
  const queryClient = useQueryClient();
  const options = adminLifecycleQuery(conversationId);
  const {data} = useSuspenseQuery(options);
  const [phaseConfirmed, setPhaseConfirmed] = useState<string[]>([]);
  const [publicationConfirmed, setPublicationConfirmed] = useState<string[]>([]);
  const [receipt, setReceipt] = useState<string | null>(null);

  function replaceLifecycle(lifecycle: Lifecycle) {
    queryClient.setQueryData<Lifecycle>(options.queryKey, lifecycle);
  }
  function toggle(setter: React.Dispatch<React.SetStateAction<string[]>>, id: string) {
    setter((values) => values.includes(id)
      ? values.filter((value) => value !== id)
      : [...values, id]);
  }

  const phaseMutation = useMutation({
    mutationFn: () => putAdminPhase(
      conversationId,
      {confirmedPreconditionIds: phaseConfirmed},
      csrfToken,
    ),
    onSuccess: (result) => {
      replaceLifecycle(result.lifecycle);
      setPhaseConfirmed([]);
      setReceipt(`Moved to ${result.transition.targetLabel}.`);
    },
  });
  const pauseMutation = useMutation({
    mutationFn: (paused: boolean) => putAdminPause(conversationId, {paused}, csrfToken),
    onSuccess: (result) => {
      replaceLifecycle(result.lifecycle);
      setReceipt(result.changed
        ? (result.paused ? 'Conversation paused.' : 'Conversation resumed.')
        : 'Conversation already had that status.');
    },
  });
  const publicationMutation = useMutation({
    mutationFn: () => createAdminPublication(
      conversationId,
      {confirmedPreconditionIds: publicationConfirmed},
      csrfToken,
    ),
    onSuccess: (result) => {
      replaceLifecycle(result.lifecycle);
      setPublicationConfirmed([]);
      setReceipt('Final report published.');
    },
  });

  const transition = data.phase.transition;
  const transitionReady = transition
    ? allHumanChecksConfirmed(transition.preconditions, phaseConfirmed)
    : false;
  const publicationReady = allHumanChecksConfirmed(
    data.publicationReadiness.preconditions,
    publicationConfirmed,
  );
  const activeError = phaseMutation.error ?? pauseMutation.error ?? publicationMutation.error;

  function submitPublication(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (globalThis.confirm(
      'Publish the final report? This freezes exclusions, closes participation, and starts identity reveal.',
    )) publicationMutation.mutate();
  }

  const management = [
    {label: 'Settings', count: null, href: data.links.settings, detail: 'Description, access, guidance'},
    {label: 'Participants', count: data.counts.participants, href: data.links.participants, detail: 'Participation and access'},
    {label: 'Moderation', count: data.counts.openFlags, href: data.links.moderation, detail: 'Open content flags'},
    {label: 'Invitations', count: data.counts.invitations, href: data.links.invitations, detail: 'Pending invitations'},
    {label: 'Roles', count: null, href: data.links.roles, detail: 'Moderators and organizers'},
    {label: 'Statements', count: null, href: data.links.statements, detail: 'Review and import'},
    {label: 'Featured', count: data.counts.featuredStatements, href: data.links.featuredStatements, detail: 'Confirmed statements'},
  ];

  return (
    <main className="lifecycle-shell" id="main">
      <nav className="record-breadcrumb" aria-label="Breadcrumb">
        <a href="/admin">Admin panel</a><span>/</span><span>{data.conversation.title}</span>
      </nav>

      <header className="lifecycle-heading">
        <div>
          <p className="eyebrow">{data.operator.roleLabel} · {data.conversation.accessPolicy}</p>
          <h1>{data.conversation.title}</h1>
          <p>Guide the conversation through its phases and keep operational work in one place.</p>
        </div>
        <div className="lifecycle-heading__state">
          <span data-tone={data.conversation.status}>{formatStatus(data.conversation.status)}</span>
          <span data-tone={data.conversation.publication}>{formatStatus(data.conversation.publication)}</span>
          <a href={data.links.participantView}>Participant view ↗</a>
        </div>
      </header>

      {(receipt || activeError) && (
        <p className="lifecycle-receipt" data-error={Boolean(activeError)} role="status">
          {commandError(activeError) ?? receipt}
        </p>
      )}

      <section className="lifecycle-phases" aria-labelledby="phase-heading">
        <div className="lifecycle-section-heading">
          <div><p className="eyebrow">Conversation route</p><h2 id="phase-heading">Phase progression</h2></div>
          {!data.phase.linear && <span>Advanced phase state</span>}
        </div>
        <ol>
          {data.phase.steps.map((step, index) => (
            <li key={step.key} data-state={step.state}>
              <span>{String(index + 1).padStart(2, '0')}</span>
              <strong>{step.label}</strong>
              <p>{step.effect}</p>
            </li>
          ))}
        </ol>
      </section>

      <div className="lifecycle-command-grid">
        <section className="lifecycle-transition" aria-labelledby="transition-heading">
          {transition ? (
            <>
              <header>
                <p className="eyebrow">Guided change</p>
                <h2 id="transition-heading">{transition.source.label} → {transition.target.label}</h2>
                <p><strong>Opens:</strong> {transition.consequence.opens}</p>
                {transition.consequence.closes && <p><strong>Closes:</strong> {transition.consequence.closes}</p>}
              </header>
              <ReadinessList
                rows={transition.preconditions}
                confirmed={phaseConfirmed}
                onToggle={(id) => toggle(setPhaseConfirmed, id)}
              />
              {data.capabilities.advancePhase ? (
                <button
                  type="button"
                  disabled={!transitionReady || phaseMutation.isPending}
                  onClick={() => phaseMutation.mutate()}
                >
                  {phaseMutation.isPending ? 'Moving…' : `Move to ${transition.target.label}`}
                </button>
              ) : <p className="lifecycle-readonly">Your role can inspect this transition but cannot execute it.</p>}
            </>
          ) : (
            <div className="lifecycle-no-transition">
              <p className="eyebrow">Phase control</p>
              <h2 id="transition-heading">No guided transition</h2>
              <p>{data.phase.linear
                ? 'This route has reached its final guided phase.'
                : 'This conversation uses an advanced phase combination.'}</p>
            </div>
          )}
        </section>

        <aside className="lifecycle-operations" aria-labelledby="operations-heading">
          <p className="eyebrow">Live operation</p><h2 id="operations-heading">Availability</h2>
          <p>Pause temporarily stops participant activity without changing the current phase.</p>
          {data.schedule.scheduledAt && (
            <p className="lifecycle-schedule">
              Scheduled: <strong>{data.schedule.targetLabel}</strong>{' '}
              <time dateTime={data.schedule.scheduledAt}>{new Date(data.schedule.scheduledAt).toLocaleString()}</time>
            </p>
          )}
          <ScheduleControl
            key={`${data.schedule.scheduledAt}-${data.schedule.frozen}-${data.schedule.targetKey}`}
            conversationId={conversationId} csrfToken={csrfToken} data={data}
            onChange={replaceLifecycle} onReceipt={setReceipt}
          />
          {data.capabilities.pause ? (
            <button
              type="button"
              disabled={pauseMutation.isPending}
              onClick={() => pauseMutation.mutate(data.conversation.status !== 'paused')}
            >
              {pauseMutation.isPending ? 'Updating…' : data.conversation.status === 'paused' ? 'Resume conversation' : 'Pause conversation'}
            </button>
          ) : <p className="lifecycle-readonly">Only a global admin can change availability.</p>}
        </aside>
      </div>

      {data.capabilities.useAdvancedPhases && (
        <AdvancedPhaseControl
          key={data.phase.advancedControls.map((row) => `${row.key}:${row.active}`).join('|')}
          conversationId={conversationId} csrfToken={csrfToken} data={data}
          onChange={replaceLifecycle} onReceipt={setReceipt}
        />
      )}

      {data.conversation.publication === 'pending' && (
        <section className="lifecycle-publication" aria-labelledby="publication-heading">
          <header>
            <div><p className="eyebrow">Irreversible publication</p><h2 id="publication-heading">Publish the final report</h2></div>
            <p>Freezes report exclusions, closes participation, and starts the identity-reveal window.</p>
          </header>
          {data.publicationReadiness.windowOpen ? (
            <form onSubmit={submitPublication}>
              <ReadinessList
                rows={data.publicationReadiness.preconditions}
                confirmed={publicationConfirmed}
                onToggle={(id) => toggle(setPublicationConfirmed, id)}
              />
              <button type="submit" disabled={!data.capabilities.publish || !publicationReady || publicationMutation.isPending}>
                {publicationMutation.isPending ? 'Publishing…' : 'Publish final report'}
              </button>
            </form>
          ) : <p className="lifecycle-readonly">Available after informed voting ends and cleanup begins.</p>}
        </section>
      )}

      <section className="lifecycle-management" aria-labelledby="management-heading">
        <div className="lifecycle-section-heading"><div><p className="eyebrow">Workspace</p><h2 id="management-heading">Manage the record</h2></div></div>
        <ul>{management.map((item) => (
          <li key={item.label}>
            {item.href.startsWith('/app/')
              ? <Link to={item.href}><strong>{item.label}</strong><span>{item.detail}</span>{item.count !== null && <b>{item.count}</b>}</Link>
              : <a href={item.href}><strong>{item.label}</strong><span>{item.detail}</span>{item.count !== null && <b>{item.count}</b>}</a>}
          </li>
        ))}</ul>
      </section>
    </main>
  );
}

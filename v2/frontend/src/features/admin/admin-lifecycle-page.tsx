import {Fragment, useCallback, useLayoutEffect, useState, type FormEvent} from 'react';
import {useMutation, useQueryClient, useSuspenseQuery} from '@tanstack/react-query';
import {Link} from 'react-router-dom';

import type {components} from '../../api/schema';
import {ApiContractError} from '../../api/client';
import {
  adminLifecycleQuery,
  adminRoleRosterQuery,
  adminSettingsQuery,
  adminTerminationQuery,
  createAdminPhase6Initialization,
  createAdminPublication,
  deleteAdminConversation,
  putAdminPause,
  putAdminPhase,
  putAdminPhases,
  putAdminRecommendationTier,
  putAdminRoles,
  putAdminSchedule,
  putAdminSettings,
} from '../../api/queries';
import {LegacyShell} from '../legacy/legacy-shell';
import {LegacyToast, type LegacyToastMessage} from '../legacy/legacy-toast';
import {InternalLink} from '../../internal-link';

type Lifecycle = components['schemas']['AdminLifecycle'];
type PhaseTransitionReceipt = components['schemas']['AdminPhaseAdvanceReceipt']['transition'];

/** Message shown when Polis rejected the results-visibility update after a phase move.
 *
 * This is a data-integrity signal, not a cosmetic confirmation: the local phase moved
 * but upstream Polis still gates ``GET /results/`` on the old vis_type, so results can
 * silently fail to appear. It must never be folded into a plain success. */
const VISIBILITY_DESYNC_ADVANCE =
  'Phase moved, but updating results visibility in Polis failed.';
const VISIBILITY_DESYNC_PHASES =
  'Phases saved, but updating results visibility in Polis failed — '
  + 'results may not appear until you save phases again.';

/** Collapse a phase-advance receipt into one toast, keeping the worst severity.
 *
 * The receipt can carry up to three independent notices (visibility desync, a Phase 6
 * re-seed message, and the move confirmation). The toast surface shows one message at a
 * time, so they are concatenated in server order and the category is the most severe of
 * them — a partial failure must never render as a green success. */
export function phaseTransitionToast(
  transition: PhaseTransitionReceipt,
): {category: LegacyToastMessage['category']; message: string} {
  const parts: string[] = [];
  let category: LegacyToastMessage['category'] = 'success';
  if (!transition.visibilitySynced) {
    category = 'error';
    parts.push(VISIBILITY_DESYNC_ADVANCE);
  }
  if (transition.phase6SyncMessage) {
    if (category !== 'error' && transition.phase6SyncMessage.includes('check manually')) {
      category = 'warning';
    }
    parts.push(transition.phase6SyncMessage);
  }
  parts.push(`Moved to: ${transition.targetLabel}.`);
  return {category, message: parts.join(' ')};
}
type Settings = components['schemas']['AdminSettings'];
type RoleRoster = components['schemas']['AdminRoleRoster'];
type Role = 'moderator' | 'organizer';

function legacyTruncate(value: string, length = 34, leeway = 5): string {
  return value.length <= length + leeway ? value : `${value.slice(0, length - 1)}…`;
}

function message(error: Error, fallback = 'The command could not be completed.'): string {
  return error instanceof ApiContractError ? error.message : fallback;
}

function useRedesignStyles() {
  useLayoutEffect(() => {
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = '/static/redesign.css';
    link.dataset.reactLegacyRedesign = 'true';
    document.head.appendChild(link);
    return () => link.remove();
  }, []);
}

function countdown(value: string): string {
  let seconds = Math.max(0, Math.floor((new Date(value).getTime() - Date.now()) / 1000));
  if (!seconds) return 'due now';
  const days = Math.floor(seconds / 86400); seconds -= days * 86400;
  const hours = Math.floor(seconds / 3600); seconds -= hours * 3600;
  const minutes = Math.floor(seconds / 60);
  return [days && `${days}d`, hours && `${hours}h`, minutes && `${minutes}m`].filter(Boolean).join(' ') || '<1m';
}

function shortDate(value: string): string {
  return new Date(value).toLocaleDateString('en-GB', {
    day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC',
  });
}

function advancedPhaseLabel(key: string, fallback: string): string {
  const labels: Record<string, string> = {
    submission: 'Statement submission (Explore)',
    featured_selection: 'Personal results',
    argument_mapping: 'Argument mapping',
    cleanup: 'Cleanup',
    informed_voting: 'Informed voting',
    public_results: 'Public results',
  };
  return labels[key] ?? fallback;
}

function utcInput(value: string | null): string {
  return value ? new Date(value).toISOString().slice(0, 16) : new Date().toISOString().slice(0, 16);
}

function PhaseStatistics({data}: {data: Lifecycle}) {
  const shown = data.statistics.groups.filter((group) => group.tiles.length);
  const summary = data.statistics.informedVoting;
  return <>
    {data.statistics.upstreamUnavailable && <div className="phase-stats-warning" role="status">
      <span aria-hidden="true">⚠️</span>
      <span><strong>Live statistics unavailable.</strong> Vote and participant counts may be
        {' '}missing or stale — the Polis statistics database may be unreachable, or this
        {' '}conversation may not yet be registered in Polis. Check the server logs.</span>
    </div>}
    {shown.map((group, groupIndex) => <Fragment key={group.key}>
      {!data.phase.linear && <div id={`psg-${groupIndex + 1}`} className="phase-stats-group-label">{group.label}</div>}
      <dl className={`phase-stats${data.phase.linear ? '' : ' phase-stats--grouped'}`} aria-labelledby={data.phase.linear ? undefined : `psg-${groupIndex + 1}`}>
        {group.tiles.map((tile) => <div key={`${tile.label}-${String(tile.value)}`}>
          <dt className="phase-stat-value">{tile.value}{tile.unit && <span className="unit">{tile.unit}</span>}</dt>
          <dd className="phase-stat-label">{tile.label}{tile.note && <div className="phase-stat-note">{tile.note}</div>}</dd>
        </div>)}
      </dl>
    </Fragment>)}
    {summary && <div className="phase-stats phase-stats--p6" style={{marginTop: '.75rem', paddingTop: '.75rem', borderTop: '1px solid var(--hairline)'}}>
      <div><div className="phase-stat-label" style={{marginBottom: 3}}>Informed voting</div>
        {summary.participants !== null ? <div><div className="phase-stat-value">{summary.participants}</div><div className="phase-stat-label">participants in round 6</div></div> : <div className="muted" style={{fontSize: 12}}>participant count unavailable</div>}
      </div>
      {summary.statementCount > 0 && <><div><div className="phase-stat-value">{summary.statementCount}</div><div className="phase-stat-label">statements voted on</div></div>
        {summary.largestShift && <div style={{gridColumn: '1/-1', marginTop: '.25rem'}}><div className="phase-stat-label" style={{marginBottom: 3}}>Largest shift</div><span style={{fontSize: 13}}>“{summary.largestShift.text.length > 65 ? `${summary.largestShift.text.slice(0, 59)}…` : summary.largestShift.text}”</span><span className={`p6-shift ${summary.largestShift.shift > 0 ? 'p6-shift--up' : summary.largestShift.shift < 0 ? 'p6-shift--down' : ''}`} style={{marginLeft: '.4rem'}}>{summary.largestShift.shift > 0 && '+'}{summary.largestShift.shift}%</span></div>}
      </>}
      {(summary.excludedStatementCount > 0 || summary.excludedParticipantCount > 0) && <div style={{gridColumn: '1/-1', fontSize: 11, color: 'var(--muted)'}}>Moderation: {summary.excludedStatementCount > 0 && `${summary.excludedStatementCount} stmt excluded`} {summary.excludedParticipantCount > 0 && `· ${summary.excludedParticipantCount} participant excluded`}</div>}
    </div>}
  </>;
}

function RoleSection({conversationId, csrfToken, roster, refresh, fail}: {
  conversationId: number; csrfToken: string; roster: RoleRoster;
  refresh: () => void; fail: (error: Error) => void;
}) {
  const [participantId, setParticipantId] = useState('');
  const [role, setRole] = useState<Role>('moderator');
  const mutation = useMutation({
    mutationFn: ({id, roles}: {id: number; roles: Role[]}) => putAdminRoles(conversationId, id, {roles}, csrfToken),
    onSuccess: refresh,
    onError: fail,
  });
  const roleCount = roster.assignments.reduce((total, row) => total + row.roles.length, 0);
  return <div className="console-section">
    <div className="console-section-label">Conversation roles</div>
    <details className="phase-advanced">
      <summary>Roles{roleCount > 0 && ` (${roleCount})`}</summary>
      {roleCount > 0 ? <table className="admin-table" style={{marginTop: '.75rem'}}><thead><tr><th>Participant</th><th>Role</th><th /></tr></thead><tbody>
        {roster.assignments.flatMap((assignment) => assignment.roles.map((assignedRole) => <tr key={`${assignment.participantId}-${assignedRole}`}>
          <td>{assignment.username}</td><td>{assignedRole}</td><td>{roster.capabilities.manageRoles && <form style={{display: 'inline'}} onSubmit={(event) => {event.preventDefault(); mutation.mutate({id: assignment.participantId, roles: assignment.roles.filter((item) => item !== assignedRole) as Role[]});}}><input type="hidden" name="csrf_token" value={csrfToken} /><button type="submit" className="btn-small btn-danger">remove</button></form>}</td>
        </tr>))}
      </tbody></table> : <p className="muted" style={{margin: '.75rem 0', fontSize: 14}}>No conversation roles assigned.</p>}
      {roster.capabilities.manageRoles && <form style={{marginTop: '.5rem'}} onSubmit={(event) => {event.preventDefault(); const id = Number(participantId); if (!id) return; const current = roster.assignments.find((item) => item.participantId === id)?.roles ?? []; mutation.mutate({id, roles: [...new Set([...current, role])] as Role[]});}}>
        <input type="hidden" name="csrf_token" value={csrfToken} />
        <div className="edit-row-fields"><label>Participant<select required value={participantId} onChange={(event) => setParticipantId(event.target.value)}><option value="">— select —</option>{roster.candidates.map((candidate) => <option key={candidate.participantId} value={candidate.participantId}>{candidate.username}</option>)}</select></label><label>Role<select value={role} onChange={(event) => setRole(event.target.value as Role)}>{roster.availableRoles.map((item) => <option key={item} value={item}>{item}</option>)}</select></label></div>
        <button type="submit">Add role</button>
      </form>}
    </details>
  </div>;
}

function ConfigurationSection({conversationId, csrfToken, settings, refresh, fail}: {
  conversationId: number; csrfToken: string; settings: Settings;
  refresh: () => void; fail: (error: Error) => void;
}) {
  const [title, setTitle] = useState(settings.conversation.title);
  const [introHtml, setIntroHtml] = useState(settings.conversation.introHtml);
  const [outroHtml, setOutroHtml] = useState(settings.conversation.outroHtml);
  const [accessPolicy, setAccessPolicy] = useState(settings.conversation.accessPolicy);
  const [eventId, setEventId] = useState(settings.eligibility.eventId);
  const [eligibilityLabel, setEligibilityLabel] = useState(settings.eligibility.label ?? '');
  const [tier, setTier] = useState(settings.recommendations.tier);
  const settingsMutation = useMutation({
    mutationFn: () => putAdminSettings(conversationId, {title, introHtml, outroHtml, accessPolicy, eligibilityEventId: eventId, eligibilityLabel, recommendationTier: settings.recommendations.tier}, csrfToken),
    onSuccess: refresh,
    onError: fail,
  });
  const recommendationMutation = useMutation({
    mutationFn: () => putAdminRecommendationTier(conversationId, {tier}, csrfToken),
    onSuccess: refresh,
    onError: fail,
  });
  return <div className="console-section">
    <div className="console-section-label">Configuration</div>
    <details className="phase-advanced"><summary>Settings — title, intro/outro, access policy</summary>
      <form className="panel" style={{marginTop: '.75rem'}} onSubmit={(event) => {event.preventDefault(); settingsMutation.mutate();}}><input type="hidden" name="csrf_token" value={csrfToken} />
        <div className="edit-row-fields">
          <label>Title<input type="text" required value={title} onChange={(event) => setTitle(event.target.value)} /></label>
          <label>Route (locked after launch)<input type="text" readOnly value={settings.conversation.phaseRouteLabel} style={{background: '#f5f5f5', color: '#666'}} /></label>
          <label>Polis ID (zinvite, read-only)<input type="text" readOnly value={settings.conversation.polisId} style={{background: '#f5f5f5', color: '#666'}} /></label>
          <label>Access policy<select value={accessPolicy} onChange={(event) => setAccessPolicy(event.target.value as typeof accessPolicy)}><option value="public">public</option><option value="invite_only">invite_only</option><option value="demo">demo</option></select></label>
          <label>Eligibility event ID<input type="text" maxLength={80} value={eventId} onChange={(event) => setEventId(event.target.value)} /></label>
          <label>Eligibility label<input type="text" maxLength={255} value={eligibilityLabel} onChange={(event) => setEligibilityLabel(event.target.value)} /></label>
        </div>
        <div className="edit-row-texts"><label>Intro text (HTML, optional)<textarea rows={4} value={introHtml} onChange={(event) => setIntroHtml(event.target.value)} /></label><label>Outro text (HTML, optional)<textarea rows={4} value={outroHtml} onChange={(event) => setOutroHtml(event.target.value)} /></label></div>
        <button type="submit">Save settings</button>
      </form>
    </details>
    <details className="phase-advanced"><summary>Recommended quantities</summary>
      <form className="panel" style={{marginTop: '.75rem'}} onSubmit={(event) => {event.preventDefault(); recommendationMutation.mutate();}}><input type="hidden" name="csrf_token" value={csrfToken} /><p className="section-help">These numbers are advisory. They appear in readiness checks and stats so organizers can judge whether the consultation has enough material to move on.</p>
        <div className="edit-row-fields"><label>Complexity tier<select value={tier} onChange={(event) => setTier(event.target.value as typeof tier)}>{settings.recommendations.tiers.map((item) => <option key={item.key} value={item.key}>{item.label}</option>)}</select></label>{Object.entries(settings.recommendations.tiers.find((item) => item.key === tier)?.quantities ?? {}).map(([key, value]) => <div className="recommendation-value" key={key}><span>{key.replaceAll('_', ' ')}</span><strong>{value}</strong></div>)}</div>
        <button type="submit">Save recommendations</button>
      </form>
    </details>
  </div>;
}

function ClosedDescription({lifecycle}: {lifecycle: Lifecycle}) {
  const reveal = lifecycle.conversation.identityReveal;
  const closedAt = lifecycle.conversation.closedAt
    ? shortDate(lifecycle.conversation.closedAt) : null;
  if (reveal?.state === 'pending' && reveal.opensAt) {
    return <>Closed {closedAt}. The identity-reveal window opens on {shortDate(reveal.opensAt)} ({reveal.daysLeft} day{reveal.daysLeft === 1 ? '' : 's'} away) — nothing to do until then.</>;
  }
  if (reveal?.state === 'open' && reveal.closesAt) {
    return <>Closed {closedAt}. The identity-reveal window is open until {shortDate(reveal.closesAt)}.</>;
  }
  if (reveal?.state === 'expired') {
    return <>Closed {closedAt}. The identity-reveal window has ended — records are permanently pseudonymous.</>;
  }
  return <>Closed{closedAt && ` ${closedAt}`}. Cannot be reopened.</>;
}

function DangerSection({conversationId, csrfToken, lifecycle, fail}: {
  conversationId: number; csrfToken: string; lifecycle: Lifecycle; fail: (error: Error) => void;
}) {
  const {data} = useSuspenseQuery(adminTerminationQuery(conversationId));
  const deletion = useMutation({mutationFn: () => deleteAdminConversation(conversationId, csrfToken), onError: fail});
  const publication = useMutation({
    mutationFn: (confirmedPreconditionIds: string[]) => createAdminPublication(conversationId, {confirmedPreconditionIds}, csrfToken),
    onError: fail,
  });
  const [confirmed, setConfirmed] = useState<string[]>([]);
  const closed = lifecycle.conversation.status === 'closed';
  const cleanup = lifecycle.publicationReadiness.windowOpen;
  return <div className="console-section"><div className="console-section-label" style={{color: 'var(--disagree)'}}>Ending the consultation</div><div className="danger-zone">
    {closed ? <div className="danger-row"><div className="danger-row-main"><div className="danger-row-title">Permanently closed · <InternalLink href={`/c/${lifecycle.conversation.slug}/report`} style={{fontWeight: 400, fontSize: 13}}>View final report <span aria-hidden="true">→</span></InternalLink></div><div className="danger-row-desc"><ClosedDescription lifecycle={lifecycle} /></div></div></div> : <div className="danger-row"><div className="danger-row-main"><div className="danger-row-title">Publish final report</div><div className="danger-row-desc">{cleanup ? <>Irreversible. Publishes <code>/c/{lifecycle.conversation.slug}/report</code>, freezes moderation exclusions, and starts the identity-reveal window.</> : 'Available after informed voting has ended and the consultation is in the cleanup window.'}</div></div>{cleanup ? <form className="cleanup-publish-form" onSubmit={(event) => {event.preventDefault(); if (globalThis.confirm('Publish the final report?\n\nThis freezes report exclusions, closes the consultation, and starts the identity reveal timeline.')) publication.mutate(confirmed);}}><input type="hidden" name="csrf_token" value={csrfToken} /><ul className="readiness cleanup-readiness">{lifecycle.publicationReadiness.preconditions.map((row) => <li key={row.id}>{row.met === null ? <label><input type="checkbox" checked={confirmed.includes(row.id)} onChange={() => setConfirmed((items) => items.includes(row.id) ? items.filter((item) => item !== row.id) : [...items, row.id])} /> <span className="readiness-label">{row.label}</span></label> : <span className="readiness-label">{row.label} {row.met ? <span className="readiness-note">(met)</span> : <span className="phase-check-unmet">not met yet</span>}</span>}</li>)}</ul><button type="submit" className="btn-small btn-danger">Publish final report</button></form> : <button type="button" className="btn-small btn-danger" disabled>Publish final report</button>}</div>}
    <div className="danger-row"><div className="danger-row-main"><div className="danger-row-title">Delete empty consultation</div><div className="danger-row-desc">Deletes the local consultation after deactivating and hiding it in Polis. {data.deletion.state === 'unavailable' ? 'Disabled because Polis vote data could not be verified.' : data.deletion.validVoteCount === 0 ? 'Available because Polis has no valid votes for this consultation.' : `Disabled because Polis has ${data.deletion.validVoteCount} valid vote${data.deletion.validVoteCount === 1 ? '' : 's'}.`}</div></div><form style={{display: 'inline'}} onSubmit={(event) => {event.preventDefault(); if (globalThis.confirm('Delete this consultation?\n\nThis removes local ProtoWiki records after hiding the Polis conversation. This cannot be undone.')) deletion.mutate();}}><input type="hidden" name="csrf_token" value={csrfToken} /><button type="submit" className="btn-small btn-danger" disabled={data.deletion.state !== 'eligible'} aria-disabled={data.deletion.state !== 'eligible'}>Delete consultation</button></form></div>
  </div></div>;
}

export function AdminLifecyclePage({conversationId, csrfToken}: {conversationId: number; csrfToken: string}) {
  useRedesignStyles();
  const queryClient = useQueryClient();
  const lifecycleOptions = adminLifecycleQuery(conversationId);
  const settingsOptions = adminSettingsQuery(conversationId);
  const rolesOptions = adminRoleRosterQuery(conversationId);
  const {data} = useSuspenseQuery(lifecycleOptions);
  const {data: settings} = useSuspenseQuery(settingsOptions);
  const {data: roles} = useSuspenseQuery(rolesOptions);
  const [advanced, setAdvanced] = useState(false);
  const [phaseChecks, setPhaseChecks] = useState<string[]>([]);
  const [scheduleAt, setScheduleAt] = useState(utcInput(data.schedule.scheduledAt));
  const [advancedKeys, setAdvancedKeys] = useState(data.phase.advancedControls.filter((row) => row.active).map((row) => row.key));
  const [toast, setToast] = useState<LegacyToastMessage | null>(null);
  const dismissToast = useCallback(() => setToast(null), []);
  function notify(category: LegacyToastMessage['category'], text: string) {setToast({id: Date.now(), category, message: text});}
  function fail(error: Error) {notify('error', message(error));}
  function setLifecycle(lifecycle: Lifecycle) {queryClient.setQueryData(lifecycleOptions.queryKey, lifecycle);}
  function refreshSupporting() {void queryClient.invalidateQueries({queryKey: settingsOptions.queryKey}); void queryClient.invalidateQueries({queryKey: rolesOptions.queryKey}); void queryClient.invalidateQueries({queryKey: lifecycleOptions.queryKey});}

  const phaseMutation = useMutation({mutationFn: () => putAdminPhase(conversationId, {confirmedPreconditionIds: phaseChecks}, csrfToken), onSuccess: (result) => {setLifecycle(result.lifecycle); setPhaseChecks([]); const receipt = phaseTransitionToast(result.transition); notify(receipt.category, receipt.message);}, onError: fail});
  const pauseMutation = useMutation({mutationFn: () => putAdminPause(conversationId, {paused: data.conversation.status !== 'paused'}, csrfToken), onSuccess: (result) => setLifecycle(result.lifecycle), onError: fail});
  const scheduleMutation = useMutation({mutationFn: (body: components['schemas']['AdminScheduleRequest']) => putAdminSchedule(conversationId, body, csrfToken), onSuccess: (result) => setLifecycle(result.lifecycle), onError: fail});
  const phasesMutation = useMutation({mutationFn: () => putAdminPhases(conversationId, {activeKeys: advancedKeys}, csrfToken), onSuccess: (result) => {setLifecycle(result.lifecycle); if (!result.visibilitySynced) notify('error', VISIBILITY_DESYNC_PHASES);}, onError: fail});
  const initialization = useMutation({mutationFn: () => createAdminPhase6Initialization(conversationId, csrfToken), onSuccess: (result) => setLifecycle(result.lifecycle), onError: fail});

  const isAdmin = data.capabilities.useAdvancedPhases;
  const canOrganize = data.capabilities.editSettings;
  const isActive = data.conversation.status !== 'archived' && data.conversation.status !== 'closed';
  const current = data.phase.steps[data.phase.currentIndex]!;
  const transition = data.phase.transition;
  const unmet = transition?.preconditions.filter((row) => row.met === false).length ?? 0;
  const allChecked = Boolean(transition) && transition!.preconditions.every((row) => phaseChecks.includes(row.id));
  const roleCount = roles.assignments.reduce((total, row) => total + row.roles.length, 0);

  return <LegacyShell headerMode="admin" title={`Manage ${data.conversation.title} — ProtoWiki`} headerCrumb={<nav className="header-crumb" aria-label="Admin breadcrumb"><span className="header-crumb-sep">/</span><Link to="/admin">Admin panel</Link><span className="header-crumb-sep">/</span><span>{legacyTruncate(data.conversation.title)}</span></nav>} toast={<LegacyToast toast={toast} onDismiss={dismissToast} />}>
    <div className="role-bar"><div className="role-bar-inner"><span className={`role-chip${isAdmin ? ' role-chip--admin' : ''}`} title="Your assigned role on this platform"><span className="role-chip-dot" />{data.operator.roleLabel}</span><span className="role-bar-context">managing&nbsp;<strong>{data.conversation.title}</strong></span><span className="role-bar-spacer" /><InternalLink className="view-as-btn" href={data.links.participantView}>View as participant →</InternalLink></div></div>
    <div className="console">
      <div className="console-head"><h1 className="console-title">{data.conversation.title}</h1><span className={`status-pill status-pill--${!isActive ? 'closed' : data.conversation.status === 'paused' ? 'paused' : data.conversation.status === 'scheduled' ? 'scheduled' : 'active'}`}><span className="status-pill-dot" />{!isActive ? 'Closed' : data.conversation.status === 'paused' ? 'Paused' : data.conversation.status === 'scheduled' ? 'Scheduled' : 'Active'}</span></div>
      <p className="console-sub"><code>/c/{data.conversation.slug}</code> &nbsp;·&nbsp; {data.conversation.accessPolicy} &nbsp;·&nbsp; {data.counts.participants} joined</p>

      <div className="console-section" id="phaseControl" data-mode={advanced ? 'advanced' : 'simple'}><div className="phase-hero"><div className="phase-hero-top"><span className="phase-now-kicker">Phase control</span></div>
        <ol className="journey phase-stepper" aria-label="Consultation phase progress">{data.phase.steps.map((step, index) => {const active = step.state === 'current'; const done = data.phase.linear && step.state === 'completed'; return <li key={step.key} className={`journey-step${active ? ' journey-step--current' : done ? ' journey-step--done' : ''}`} aria-current={active ? 'step' : undefined}><span className="journey-dot">{done ? '✓' : index + 1}</span><span className="journey-label">{step.label}</span><span className="sr-only">({active ? 'current phase' : done ? 'completed' : 'upcoming'})</span></li>;})}</ol>
        {isAdmin && <div className="mode-switch-row"><span className="mode-switch" role="group" aria-label="Phase control mode"><button type="button" className="pc-guided" aria-pressed={!advanced} aria-controls="phaseControl" onClick={() => setAdvanced(false)}>Simple</button><button type="button" className="pc-advanced mode-adv" aria-pressed={advanced} aria-controls="phaseControl" onClick={() => setAdvanced(true)}>Advanced</button></span></div>}
        <div className="phase-hero-body">{data.phase.linear ? <><div className="phase-now-head"><span className="phase-now-kicker">You are in phase {data.phase.currentIndex + 1} of {data.phase.steps.length}</span></div><div className="phase-now-head" style={{marginTop: 2}}><span className="phase-now-name">{current.label}</span>{current.key === 'public_results' && <span className={`status-pill status-pill--${data.conversation.closedAt ? 'closed' : 'paused'}`}><span className="status-pill-dot" />{data.conversation.closedAt ? 'Published' : 'Not yet published'}</span>}</div><p className="phase-now-desc">{current.key === 'public_results' && data.conversation.closedAt ? 'The final aggregate report is published and participant activity is closed.' : current.effect}</p></> : <><div className="phase-now-head"><span className="phase-now-kicker">Multiple phases active</span></div><div className="phase-now-head" style={{marginTop: 2}}><span className="phase-now-name">{data.statistics.groups.map((group) => group.label).join(' + ')}</span></div><p className="phase-now-desc">Several phases are open at once (advanced mode).{data.statistics.groups.some((group) => group.tiles.length) && ' Statistics for the phases with available data are shown below.'}</p></>}<PhaseStatistics data={data} /></div>
        {isAdmin && isActive && <div className="phase-foot phase-pause-row"><form style={{display: 'inline'}} onSubmit={(event) => {event.preventDefault(); pauseMutation.mutate();}}><input type="hidden" name="csrf_token" value={csrfToken} /><button type="submit" className={`btn-small ${data.conversation.status === 'paused' ? 'btn-approve' : 'btn-pause'}`}>{data.conversation.status === 'paused' ? 'Resume' : 'Pause'}</button></form><span className="muted" style={{fontSize: 13}}>{data.conversation.status === 'paused' ? <>Paused — participants cannot vote. The identity-reveal clock has <strong>not</strong> started; resuming is possible.</> : 'Pause temporarily disables voting without starting the reveal timeline.'}</span></div>}
      </div>

      <div className="mode-guided-part">{transition ? canOrganize ? <><div className="phase-foot"><div className={`phase-foot-ready ${unmet ? 'phase-foot-ready--wait' : 'phase-foot-ready--go'}`}><span className="phase-foot-ready-icon" aria-hidden="true">{unmet ? '!' : '✓'}</span><span>{unmet ? `${unmet} readiness check${unmet === 1 ? '' : 's'} still need resolving before ${transition.target.label}` : `No blocking checks — confirm each item below to move on to ${transition.target.label}`}</span></div></div><div className="moveon phase-move-box"><div className="moveon-head"><span className="moveon-from">{transition.source.label}</span><span className="moveon-arrow" aria-hidden="true">→</span><span>{transition.target.label}</span></div><div className="moveon-body"><ul className="consequence"><li><span className="consequence-tag consequence-tag--opens">Opens</span><span>{transition.consequence.opens}</span></li>{transition.consequence.closes && <li><span className="consequence-tag consequence-tag--closes">Closes</span><span>{transition.consequence.closes}</span></li>}<li><span className="consequence-tag" style={{background: 'var(--surface2)', color: 'var(--muted)'}}>Undo</span><span>Reversible only by a site admin via advanced controls.</span></li></ul><div className="console-section-label" style={{marginBottom: 8}}>Readiness</div><form className="phase-move-form" onSubmit={(event) => {event.preventDefault(); phaseMutation.mutate();}}><input type="hidden" name="csrf_token" value={csrfToken} /><ul className="readiness">{transition.preconditions.map((row) => <li key={row.id}><label><input type="checkbox" className="phase-move-check moveon-check" checked={phaseChecks.includes(row.id)} onChange={() => setPhaseChecks((items) => items.includes(row.id) ? items.filter((item) => item !== row.id) : [...items, row.id])} /><span className="readiness-label">{row.label} {row.met === true && <span className="readiness-note">({row.note || 'met'})</span>}{row.met === false && <><span className="phase-check-unmet"><span aria-hidden="true">✗</span> not met yet</span>{row.note && <span className="readiness-note">({row.note})</span>}</>}</span></label></li>)}</ul><p className="phase-move-hint moveon-hint muted">Confirm every item above to enable “Move on”. Anything marked “not met yet” must be resolved first.</p><button type="submit" className="rd-btn-primary phase-move-submit" disabled={unmet > 0 || !allChecked}>Move on to {transition.target.label} →</button></form>{transition.showPauseGuidance && <p className="muted" style={{fontSize: 12, marginTop: 10}}>Need time to coordinate inviting people back? You can pause first.</p>}</div></div></> : <><p className="muted" style={{fontSize: 13, marginTop: 14}}>Only an organizer or site admin can change phases.</p><button type="button" className="btn-small" disabled title="Only an organizer or site admin can change phases">Move on to {transition.target.label} →</button></> : !data.phase.linear ? <p className="muted" style={{marginTop: 14, fontSize: 13}}><span aria-hidden="true">⚠️</span> Phases are in a custom state (more than one active). {isAdmin ? 'Use Advanced below to adjust.' : 'A site admin can adjust this.'}</p> : <p className="muted" style={{marginTop: 14, fontSize: 13}}>{data.conversation.closedAt ? <><strong>Final report published.</strong> The frozen aggregate results are open.</> : <><strong>Report phase reached — not yet published.</strong> Complete cleanup and use “Publish final report” below to open the frozen results.</>}</p>}
        {isAdmin && data.schedule.canSchedule && <div className="schedule-card" style={{marginTop: 14}}><div className="schedule-main"><div className="schedule-title">Schedule wind-down to {data.schedule.targetLabel}</div><div className="schedule-when">{data.schedule.scheduledAt ? <>{new Date(data.schedule.scheduledAt).toISOString().slice(0, 16).replace('T', ' ')} <span className="schedule-utc">UTC</span> · <span className="countdown-mini">{countdown(data.schedule.scheduledAt)}</span>{data.schedule.frozen && ' · frozen'}</> : 'No scheduled transition set.'}</div></div><form className="schedule-actions" onSubmit={(event) => {event.preventDefault(); scheduleMutation.mutate({scheduledAt: new Date(`${scheduleAt}:00Z`).toISOString(), frozen: false});}}><input type="hidden" name="csrf_token" value={csrfToken} /><label className="sr-only" htmlFor="scheduled-at">UTC timestamp</label><input id="scheduled-at" type="datetime-local" aria-label="Scheduled transition time in UTC" value={scheduleAt} onChange={(event) => setScheduleAt(event.target.value)} /><span className="schedule-utc" aria-hidden="true">UTC</span><button type="submit" className="btn-ghost">{data.schedule.scheduledAt ? 'Edit' : 'Set'}</button></form>{data.schedule.scheduledAt && <><form className="schedule-actions" onSubmit={(event) => {event.preventDefault(); scheduleMutation.mutate({scheduledAt: data.schedule.scheduledAt, frozen: !data.schedule.frozen});}}><button type="submit" className="btn-ghost">{data.schedule.frozen ? 'Unfreeze' : 'Freeze'}</button></form><form className="schedule-actions" onSubmit={(event) => {event.preventDefault(); scheduleMutation.mutate({scheduledAt: null, frozen: false});}}><button type="submit" className="btn-ghost">Cancel</button></form></>}</div>}
        {isAdmin && transition && !data.schedule.canSchedule && <div className="locked-control" style={{marginTop: 14}}><strong>Scheduling unavailable.</strong><span className="locked-why">Opening an active participant phase still requires the full manual checklist.</span></div>}
      </div>

      {isAdmin && <div className="mode-advanced-part"><div className="box-adv-note"><span aria-hidden="true">⚠️</span><span><strong>Advanced.</strong> These toggles act independently and out of order, with no readiness checks — for demos and recovery, not routine runs.</span></div><form className="phases-form" style={{flexWrap: 'wrap', gap: '.75rem', marginTop: '.75rem'}} onSubmit={(event) => {event.preventDefault(); phasesMutation.mutate();}}><input type="hidden" name="csrf_token" value={csrfToken} />{data.phase.advancedControls.map((row) => <label key={row.key}><input type="checkbox" checked={advancedKeys.includes(row.key)} onChange={() => setAdvancedKeys((items) => items.includes(row.key) ? items.filter((item) => item !== row.key) : [...items, row.key])} /> {advancedPhaseLabel(row.key, row.label)}</label>)}<button type="submit" className="btn-small phases-save">Save phases</button></form>{data.phase.activeKeys.includes('informed_voting') && <div style={{marginTop: '1rem'}}><div className="console-section-label">Informed voting — setup</div>{data.phase.phase6Setup?.polisConversationId ? <p style={{fontSize: 13}}>Phase 6 Polis conversation: <code>{data.phase.phase6Setup.polisConversationId}</code> · {data.phase.phase6Setup.seededStatementCount} of {data.phase.phase6Setup.confirmedStatementCount} statements seeded.</p> : <><p style={{fontSize: 13, marginBottom: '.5rem'}}>Enabled but not initialised. Initialising creates a dedicated Polis conversation and seeds all confirmed featured statements.</p><form onSubmit={(event) => {event.preventDefault(); initialization.mutate();}}><button type="submit" className="btn-small">Initialise Phase 6</button></form></>}</div>}</div>}
      </div>

      <div className="console-section"><div className="console-section-label">Content &amp; access</div><div className="manage-grid">
        <Link className="manage-card" to={data.links.statements}><div className="manage-card-title">Statements</div><div className="manage-card-desc">Review, approve or hide statements; add seed statements</div></Link>
        <Link className="manage-card" to={data.links.invitations}><div className="manage-card-top"><span className="manage-card-count">{data.counts.invitations} invite{data.counts.invitations === 1 ? '' : 's'}</span></div><div className="manage-card-title">Invites &amp; access</div><div className="manage-card-desc">Who can join this consultation</div></Link>
        <Link className="manage-card" to={data.links.featuredStatements}><div className="manage-card-top"><span className="manage-card-count">{data.counts.featuredStatements} featured</span></div><div className="manage-card-title">Featured statements</div><div className="manage-card-desc">Curate the set for arguments &amp; informed voting</div></Link>
        <Link className="manage-card" to={data.links.participants}><div className="manage-card-top"><span className="manage-card-count">{data.counts.participants} joined</span></div><div className="manage-card-title">Participants</div><div className="manage-card-desc">Review per-participant engagement and drop-off signals</div></Link>
        <Link className="manage-card" to={data.links.moderation}><div className="manage-card-top"><span className="manage-card-count">{data.counts.openFlags} open</span></div><div className="manage-card-title">Moderation queue</div><div className="manage-card-desc">Review participant flags for statements and arguments</div></Link>
        <Link className="manage-card" to={data.links.roles}><div className="manage-card-top"><span className="manage-card-count">{roleCount} assigned</span></div><div className="manage-card-title">Conversation roles</div><div className="manage-card-desc">Review moderator and organizer access</div></Link>
      </div></div>
      <RoleSection conversationId={conversationId} csrfToken={csrfToken} roster={roles} refresh={refreshSupporting} fail={fail} />
      {canOrganize && <ConfigurationSection conversationId={conversationId} csrfToken={csrfToken} settings={settings} refresh={refreshSupporting} fail={fail} />}
      {isAdmin && <DangerSection conversationId={conversationId} csrfToken={csrfToken} lifecycle={data} fail={fail} />}
    </div>
  </LegacyShell>;
}

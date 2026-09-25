import {Fragment, useCallback, useLayoutEffect, useState} from 'react';
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
  putAdminRoles,
  putAdminSchedule,
} from '../../api/queries';
import {LegacyShell} from '../legacy/legacy-shell';
import {LegacyToast, type LegacyToastMessage} from '../legacy/legacy-toast';
import {InternalLink} from '../../internal-link';
import {useMessage, type Message} from '../../i18n/messages';
import {accessPolicyLabel, phaseLabel, routeLabel} from '../../i18n/server-labels';
import {escapeHtml, richHtml} from '../../i18n/rich-html';
import {useDateFormat} from '../../i18n/dates';

type Lifecycle = components['schemas']['AdminLifecycle'];
type PhaseTransitionReceipt = components['schemas']['AdminPhaseAdvanceReceipt']['transition'];

/** Collapse a phase-advance receipt into one toast, keeping the worst severity.
 *
 * The receipt can carry up to three independent notices (visibility desync, a Phase 6
 * re-seed message, and the move confirmation). The toast surface shows one message at a
 * time, so they are concatenated in server order and the category is the most severe of
 * them — a partial failure must never render as a green success.
 *
 * Severity is decided by `visibilitySynced` and by the server's own `phase6SyncMessage`,
 * never by the localised copy: translating `flash-move-sync-failed` cannot turn a partial
 * failure green. */
export function phaseTransitionToast(
  msg: Message,
  transition: PhaseTransitionReceipt,
): {category: LegacyToastMessage['category']; message: string} {
  const parts: string[] = [];
  let category: LegacyToastMessage['category'] = 'success';
  if (!transition.visibilitySynced) {
    category = 'error';
    parts.push(msg('flash-move-sync-failed'));
  }
  if (transition.phase6SyncMessage) {
    if (category !== 'error' && transition.phase6SyncMessage.includes('check manually')) {
      category = 'warning';
    }
    parts.push(transition.phase6SyncMessage);
  }
  parts.push(msg('flash-moved-to', phaseLabel(msg, transition.targetKey, transition.targetLabel)));
  return {category, message: parts.join(' ')};
}
type Settings = components['schemas']['AdminSettings'];
type RoleRoster = components['schemas']['AdminRoleRoster'];
type Role = 'moderator' | 'organizer';

function legacyTruncate(value: string, length = 34, leeway = 5): string {
  return value.length <= length + leeway ? value : `${value.slice(0, length - 1)}…`;
}

/** The server's own error copy is deliberately not keyed (see v2/i18n/README.md), so a
 *  contract error is shown verbatim; only the fallback comes from the catalogue. */
function message(msg: Message, error: Error): string {
  return error instanceof ApiContractError ? error.message : msg('adminconv-command-failed');
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

function countdown(msg: Message, value: string): string {
  let seconds = Math.max(0, Math.floor((new Date(value).getTime() - Date.now()) / 1000));
  if (!seconds) return msg('adminconv-due-now');
  const days = Math.floor(seconds / 86400); seconds -= days * 86400;
  const hours = Math.floor(seconds / 3600); seconds -= hours * 3600;
  const minutes = Math.floor(seconds / 60);
  return [
    days && msg('adminconv-countdown-days', days),
    hours && msg('adminconv-countdown-hours', hours),
    minutes && msg('adminconv-countdown-minutes', minutes),
  ].filter(Boolean).join(' ') || msg('adminconv-countdown-lt1m');
}

/** Advanced-toggle names, which are deliberately more explicit than the phase labels the
 *  server sends for the guided stepper. A literal map rather than an interpolated key, so
 *  every message name stays greppable from the catalogue. */
const ADVANCED_PHASE_KEY: Record<string, string> = {
  submission: 'adminconv-phase-submission',
  featured_selection: 'adminconv-phase-personal',
  argument_mapping: 'adminconv-phase-argmap',
  cleanup: 'adminconv-phase-cleanup',
  informed_voting: 'adminconv-phase-informed',
  public_results: 'adminconv-phase-public',
};

function advancedPhaseLabel(msg: Message, key: string, fallback: string): string {
  const messageKey = ADVANCED_PHASE_KEY[key];
  return messageKey ? msg(messageKey) : fallback;
}

function utcInput(value: string | null): string {
  return value ? new Date(value).toISOString().slice(0, 16) : new Date().toISOString().slice(0, 16);
}

function PhaseStatistics({data}: {data: Lifecycle}) {
  const shown = data.statistics.groups.filter((group) => group.tiles.length);
  const summary = data.statistics.informedVoting;
  const msg = useMessage();
  return <>
    {data.statistics.upstreamUnavailable && <div className="phase-stats-warning" role="status">
      <span aria-hidden="true">⚠️</span>
      <span dangerouslySetInnerHTML={richHtml(msg('adminconv-stats-warning'))} />
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
      <div><div className="phase-stat-label" style={{marginBottom: 3}}>{msg('adminconv-informed-voting-label')}</div>
        {summary.participants !== null ? <div><div className="phase-stat-value">{summary.participants}</div><div className="phase-stat-label">{msg('adminconv-participants-round6')}</div></div> : <div className="muted" style={{fontSize: 12}}>{msg('adminconv-participant-count-unavailable')}</div>}
      </div>
      {summary.statementCount > 0 && <><div><div className="phase-stat-value">{summary.statementCount}</div><div className="phase-stat-label">{msg('adminconv-statements-voted-on')}</div></div>
        {summary.largestShift && <div style={{gridColumn: '1/-1', marginTop: '.25rem'}}><div className="phase-stat-label" style={{marginBottom: 3}}>{msg('adminconv-largest-shift')}</div><span style={{fontSize: 13}}>“{summary.largestShift.text.length > 65 ? `${summary.largestShift.text.slice(0, 59)}…` : summary.largestShift.text}”</span><span className={`p6-shift ${summary.largestShift.shift > 0 ? 'p6-shift--up' : summary.largestShift.shift < 0 ? 'p6-shift--down' : ''}`} style={{marginLeft: '.4rem'}}>{summary.largestShift.shift > 0 && '+'}{summary.largestShift.shift}%</span></div>}
      </>}
      {(summary.excludedStatementCount > 0 || summary.excludedParticipantCount > 0) && <div style={{gridColumn: '1/-1', fontSize: 11, color: 'var(--muted)'}}>{msg('adminconv-moderation')} {summary.excludedStatementCount > 0 && msg('adminconv-stmt-excluded', summary.excludedStatementCount)} {summary.excludedParticipantCount > 0 && msg('adminconv-participant-excluded', summary.excludedParticipantCount)}</div>}
    </div>}
  </>;
}

function RoleSection({conversationId, csrfToken, roster, refresh, fail}: {
  conversationId: number; csrfToken: string; roster: RoleRoster;
  refresh: () => void; fail: (error: Error) => void;
}) {
  const msg = useMessage();
  const [participantId, setParticipantId] = useState('');
  const [role, setRole] = useState<Role>('moderator');
  const mutation = useMutation({
    mutationFn: ({id, roles}: {id: number; roles: Role[]}) => putAdminRoles(conversationId, id, {roles}, csrfToken),
    onSuccess: refresh,
    onError: fail,
  });
  const roleCount = roster.assignments.reduce((total, row) => total + row.roles.length, 0);
  return <div className="console-section">
    <div className="console-section-label">{msg('adminconv-roles-label')}</div>
    <details className="phase-advanced">
      <summary>{roleCount > 0 ? msg('adminconv-roles-summary-count', roleCount) : msg('adminconv-roles-summary')}</summary>
      {roleCount > 0 ? <table className="admin-table" style={{marginTop: '.75rem'}}><thead><tr><th>{msg('admin-th-participant')}</th><th>{msg('adminconv-th-role')}</th><th /></tr></thead><tbody>
        {roster.assignments.flatMap((assignment) => assignment.roles.map((assignedRole) => <tr key={`${assignment.participantId}-${assignedRole}`}>
          <td>{assignment.username}</td><td>{assignedRole}</td><td>{roster.capabilities.manageRoles && <form style={{display: 'inline'}} onSubmit={(event) => {event.preventDefault(); mutation.mutate({id: assignment.participantId, roles: assignment.roles.filter((item) => item !== assignedRole) as Role[]});}}><input type="hidden" name="csrf_token" value={csrfToken} /><button type="submit" className="btn-small btn-danger">{msg('admin-btn-remove')}</button></form>}</td>
        </tr>))}
      </tbody></table> : <p className="muted" style={{margin: '.75rem 0', fontSize: 14}}>{msg('adminconv-no-roles')}</p>}
      {roster.capabilities.manageRoles && <form style={{marginTop: '.5rem'}} onSubmit={(event) => {event.preventDefault(); const id = Number(participantId); if (!id) return; const current = roster.assignments.find((item) => item.participantId === id)?.roles ?? []; mutation.mutate({id, roles: [...new Set([...current, role])] as Role[]});}}>
        <input type="hidden" name="csrf_token" value={csrfToken} />
        <div className="edit-row-fields"><label>{msg('adminconv-label-participant')}<select required value={participantId} onChange={(event) => setParticipantId(event.target.value)}><option value="">{msg('adminconv-select-placeholder')}</option>{roster.candidates.map((candidate) => <option key={candidate.participantId} value={candidate.participantId}>{candidate.username}</option>)}</select></label><label>{msg('adminconv-label-role')}<select value={role} onChange={(event) => setRole(event.target.value as Role)}>{roster.availableRoles.map((item) => <option key={item} value={item}>{item}</option>)}</select></label></div>
        <button type="submit">{msg('adminconv-add-role')}</button>
      </form>}
    </details>
  </div>;
}

/** What the console knows about the consultation's configuration but does not own.
 *
 * Until this change the section carried a second copy of the settings form: title,
 * introduction, closing text, the eligibility event and label, and the complexity tier --
 * every one of them a field the settings page edits too. One setting with two editors is
 * how a change made on one screen gets silently written back by a stale copy held on the
 * other: the settings endpoint takes the whole representation at once, so each form had to
 * echo the other's fields untouched to avoid clobbering them. Editing now lives on the
 * settings page alone, which the management grid above links to.
 *
 * What is left is read-only, and is deliberately what the settings page does *not* show:
 * the phase route and the Polis conversation id, neither of them writable after launch,
 * and the quantities the chosen tier recommends, which the readiness checks further up
 * this page are measured against. The tier is named here but chosen on the settings
 * page. */
function ConfigurationSection({settings}: {settings: Settings}) {
  const msg = useMessage();
  const tier = settings.recommendations.tiers.find(
    (item) => item.key === settings.recommendations.tier,
  );
  const factStyle = {fontSize: 13, margin: '.25rem 0'};
  return <div className="console-section">
    <div className="console-section-label">{msg('adminconv-config-label')}</div>
    <p className="muted" style={factStyle}>{msg('adminconv-label-route-locked')}: <strong>{routeLabel(msg, settings.conversation.phaseRoute, settings.conversation.phaseRouteLabel)}</strong></p>
    <p className="muted" style={factStyle}>{msg('adminconv-label-polis-id')}: <code>{settings.conversation.polisId}</code></p>
    <p className="muted" style={factStyle}>{msg('adminconv-label-tier')}: <strong>{tier?.label ?? settings.recommendations.tier}</strong></p>
    <details className="phase-advanced"><summary>{msg('adminconv-rec-summary')}</summary>
      <div className="panel" style={{marginTop: '.75rem'}}><p className="section-help">{msg('adminconv-rec-help')}</p>
        <div className="edit-row-fields">{Object.entries(tier?.quantities ?? {}).map(([key, value]) => <div className="recommendation-value" key={key}><span>{key.replaceAll('_', ' ')}</span><strong>{value}</strong></div>)}</div>
      </div>
    </details>
  </div>;
}

function ClosedDescription({lifecycle}: {lifecycle: Lifecycle}) {
  const msg = useMessage();
  const dates = useDateFormat();
  const reveal = lifecycle.conversation.identityReveal;
  const closedAt = lifecycle.conversation.closedAt
    ? dates.date(lifecycle.conversation.closedAt) : null;
  // The reveal-window sentences carry their own dates and counts as parameters rather
  // than being assembled around them, so a translation can reorder inside each sentence.
  const closed = msg('adminconv-closed-on', closedAt ?? '');
  if (reveal?.state === 'pending' && reveal.opensAt) {
    return <>{closed} {msg('adminconv-reveal-pending', dates.date(reveal.opensAt), reveal.daysLeft ?? 0)}</>;
  }
  if (reveal?.state === 'open' && reveal.closesAt) {
    return <>{closed} {msg('adminconv-reveal-open-date', dates.date(reveal.closesAt))}</>;
  }
  if (reveal?.state === 'expired') {
    return <>{closed} {msg('adminconv-reveal-ended')}</>;
  }
  return <>{closedAt ? closed : msg('adminconv-closed-undated')} {msg('adminconv-closed-cannot-reopen')}</>;
}

function DangerSection({conversationId, csrfToken, lifecycle, fail}: {
  conversationId: number; csrfToken: string; lifecycle: Lifecycle; fail: (error: Error) => void;
}) {
  const msg = useMessage();
  const {data} = useSuspenseQuery(adminTerminationQuery(conversationId));
  const deletion = useMutation({mutationFn: () => deleteAdminConversation(conversationId, csrfToken), onError: fail});
  const publication = useMutation({
    mutationFn: (confirmedPreconditionIds: string[]) => createAdminPublication(conversationId, {confirmedPreconditionIds}, csrfToken),
    onError: fail,
  });
  const [confirmed, setConfirmed] = useState<string[]>([]);
  const closed = lifecycle.conversation.status === 'closed';
  const cleanup = lifecycle.publicationReadiness.windowOpen;
  return <div className="console-section"><div className="console-section-label" style={{color: 'var(--disagree)'}}>{msg('adminconv-danger-label')}</div><div className="danger-zone">
    {closed ? <div className="danger-row"><div className="danger-row-main"><div className="danger-row-title">{msg('adminconv-perm-closed')} · <InternalLink href={`/c/${lifecycle.conversation.slug}/report`} style={{fontWeight: 400, fontSize: 13}}>{msg('adminconv-view-report')} <span className="dir-glyph" aria-hidden="true">→</span></InternalLink></div><div className="danger-row-desc"><ClosedDescription lifecycle={lifecycle} /></div></div></div> : <div className="danger-row"><div className="danger-row-main"><div className="danger-row-title">{msg('adminconv-publish-report')}</div>{cleanup ? <div className="danger-row-desc" dangerouslySetInnerHTML={richHtml(msg('adminconv-publish-irrev', escapeHtml(`/c/${lifecycle.conversation.slug}/report`)))} /> : <div className="danger-row-desc">{msg('adminconv-publish-unavailable')}</div>}</div>{cleanup ? <form className="cleanup-publish-form" onSubmit={(event) => {event.preventDefault(); if (globalThis.confirm(msg('adminconv-confirm-publish'))) publication.mutate(confirmed);}}><input type="hidden" name="csrf_token" value={csrfToken} /><ul className="readiness cleanup-readiness">{lifecycle.publicationReadiness.preconditions.map((row) => <li key={row.id}>{row.met === null ? <label><input type="checkbox" checked={confirmed.includes(row.id)} onChange={() => setConfirmed((items) => items.includes(row.id) ? items.filter((item) => item !== row.id) : [...items, row.id])} /> <span className="readiness-label">{row.label}</span></label> : <span className="readiness-label">{row.label} {row.met ? <span className="readiness-note">({msg('adminconv-met')})</span> : <span className="phase-check-unmet">{msg('adminconv-not-met')}</span>}</span>}</li>)}</ul><button type="submit" className="btn-small btn-danger">{msg('adminconv-publish-report')}</button></form> : <button type="button" className="btn-small btn-danger" disabled>{msg('adminconv-publish-report')}</button>}</div>}
    <div className="danger-row"><div className="danger-row-main"><div className="danger-row-title">{msg('adminconv-delete-title')}</div><div className="danger-row-desc">{msg('adminconv-delete-desc')} {data.deletion.state === 'unavailable' ? msg('adminconv-delete-unverified') : data.deletion.validVoteCount === 0 ? msg('adminconv-delete-available') : msg('adminconv-delete-hasvotes', data.deletion.validVoteCount ?? 0)}</div></div><form style={{display: 'inline'}} onSubmit={(event) => {event.preventDefault(); if (globalThis.confirm(msg('adminconv-confirm-delete'))) deletion.mutate();}}><input type="hidden" name="csrf_token" value={csrfToken} /><button type="submit" className="btn-small btn-danger" disabled={data.deletion.state !== 'eligible'} aria-disabled={data.deletion.state !== 'eligible'}>{msg('adminconv-delete-btn')}</button></form></div>
  </div></div>;
}

export function AdminLifecyclePage({conversationId, csrfToken}: {conversationId: number; csrfToken: string}) {
  useRedesignStyles();
  const msg = useMessage();
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
  function fail(error: Error) {notify('error', message(msg, error));}
  function setLifecycle(lifecycle: Lifecycle) {queryClient.setQueryData(lifecycleOptions.queryKey, lifecycle);}
  function refreshSupporting() {void queryClient.invalidateQueries({queryKey: settingsOptions.queryKey}); void queryClient.invalidateQueries({queryKey: rolesOptions.queryKey}); void queryClient.invalidateQueries({queryKey: lifecycleOptions.queryKey});}

  const phaseMutation = useMutation({mutationFn: () => putAdminPhase(conversationId, {confirmedPreconditionIds: phaseChecks}, csrfToken), onSuccess: (result) => {setLifecycle(result.lifecycle); setPhaseChecks([]); const receipt = phaseTransitionToast(msg, result.transition); notify(receipt.category, receipt.message);}, onError: fail});
  const pauseMutation = useMutation({mutationFn: () => putAdminPause(conversationId, {paused: data.conversation.status !== 'paused'}, csrfToken), onSuccess: (result) => setLifecycle(result.lifecycle), onError: fail});
  const scheduleMutation = useMutation({mutationFn: (body: components['schemas']['AdminScheduleRequest']) => putAdminSchedule(conversationId, body, csrfToken), onSuccess: (result) => setLifecycle(result.lifecycle), onError: fail});
  const phasesMutation = useMutation({mutationFn: () => putAdminPhases(conversationId, {activeKeys: advancedKeys}, csrfToken), onSuccess: (result) => {setLifecycle(result.lifecycle); if (!result.visibilitySynced) notify('error', msg('flash-phases-saved-sync-failed'));}, onError: fail});
  const initialization = useMutation({mutationFn: () => createAdminPhase6Initialization(conversationId, csrfToken), onSuccess: (result) => setLifecycle(result.lifecycle), onError: fail});

  const isAdmin = data.capabilities.useAdvancedPhases;
  const canOrganize = data.capabilities.editSettings;
  const isActive = data.conversation.status !== 'archived' && data.conversation.status !== 'closed';
  const current = data.phase.steps[data.phase.currentIndex]!;
  const transition = data.phase.transition;
  const unmet = transition?.preconditions.filter((row) => row.met === false).length ?? 0;
  const allChecked = Boolean(transition) && transition!.preconditions.every((row) => phaseChecks.includes(row.id));
  const roleCount = roles.assignments.reduce((total, row) => total + row.roles.length, 0);

  return <LegacyShell headerMode="admin" title={msg('adminconv-doc-title', data.conversation.title)} headerCrumb={<nav className="header-crumb" aria-label={msg('admin-crumb-aria')}><span className="header-crumb-sep">/</span><Link to="/admin">{msg('admin-nav-panel')}</Link><span className="header-crumb-sep">/</span><span>{legacyTruncate(data.conversation.title)}</span></nav>} toast={<LegacyToast toast={toast} onDismiss={dismissToast} />}>
    <div className="role-bar"><div className="role-bar-inner"><span className={`role-chip${isAdmin ? ' role-chip--admin' : ''}`} title={msg('adminconv-role-title')}><span className="role-chip-dot" />{data.operator.roleLabel}</span><span className="role-bar-context">{msg('adminconv-managing')}&nbsp;<strong>{data.conversation.title}</strong></span><span className="role-bar-spacer" /><InternalLink className="view-as-btn" href={data.links.participantView}>{msg('adminconv-view-as')}</InternalLink></div></div>
    <div className="console">
      <div className="console-head"><h1 className="console-title">{data.conversation.title}</h1><span className={`status-pill status-pill--${!isActive ? 'closed' : data.conversation.status === 'paused' ? 'paused' : data.conversation.status === 'scheduled' ? 'scheduled' : 'active'}`}><span className="status-pill-dot" />{!isActive ? msg('adminconv-status-closed') : data.conversation.status === 'paused' ? msg('adminconv-status-paused') : data.conversation.status === 'scheduled' ? msg('adminconv-status-scheduled') : msg('adminconv-status-active')}</span></div>
      <p className="console-sub"><code>/c/{data.conversation.slug}</code> &nbsp;·&nbsp; {accessPolicyLabel(msg, data.conversation.accessPolicy)} &nbsp;·&nbsp; {msg('adminconv-joined', data.counts.participants)}</p>

      <div className="console-section" id="phaseControl" data-mode={advanced ? 'advanced' : 'simple'}><div className="phase-hero"><div className="phase-hero-top"><span className="phase-now-kicker">{msg('adminconv-phase-control')}</span></div>
        <ol className="journey phase-stepper" aria-label={msg('adminconv-journey-aria')}>{data.phase.steps.map((step, index) => {const active = step.state === 'current'; const done = data.phase.linear && step.state === 'completed'; return <li key={step.key} className={`journey-step${active ? ' journey-step--current' : done ? ' journey-step--done' : ''}`} aria-current={active ? 'step' : undefined}><span className="journey-dot">{done ? '✓' : index + 1}</span><span className="journey-label">{phaseLabel(msg, step.key, step.label)}</span><span className="sr-only">{active ? msg('adminconv-step-current') : done ? msg('adminconv-step-completed') : msg('adminconv-step-upcoming')}</span></li>;})}</ol>
        {isAdmin && <div className="mode-switch-row"><span className="mode-switch" role="group" aria-label={msg('adminconv-mode-aria')}><button type="button" className="pc-guided" aria-pressed={!advanced} aria-controls="phaseControl" onClick={() => setAdvanced(false)}>{msg('adminconv-mode-simple')}</button><button type="button" className="pc-advanced mode-adv" aria-pressed={advanced} aria-controls="phaseControl" onClick={() => setAdvanced(true)}>{msg('adminconv-mode-advanced')}</button></span></div>}
        <div className="phase-hero-body">{data.phase.linear ? <><div className="phase-now-head"><span className="phase-now-kicker">{msg('adminconv-you-are-in-phase', data.phase.currentIndex + 1, data.phase.steps.length)}</span></div><div className="phase-now-head" style={{marginTop: 2}}><span className="phase-now-name">{phaseLabel(msg, current.key, current.label)}</span>{current.key === 'public_results' && <span className={`status-pill status-pill--${data.conversation.closedAt ? 'closed' : 'paused'}`}><span className="status-pill-dot" />{data.conversation.closedAt ? msg('adminconv-status-published') : msg('adminconv-status-unpublished')}</span>}</div><p className="phase-now-desc">{current.key === 'public_results' && data.conversation.closedAt ? msg('adminconv-phase-desc-published') : current.effect}</p></> : <><div className="phase-now-head"><span className="phase-now-kicker">{msg('adminconv-multiple-active')}</span></div><div className="phase-now-head" style={{marginTop: 2}}><span className="phase-now-name">{data.statistics.groups.map((group) => group.label).join(' + ')}</span></div><p className="phase-now-desc">{msg('adminconv-several-open')}{data.statistics.groups.some((group) => group.tiles.length) && ` ${msg('adminconv-stats-below')}`}</p></>}<PhaseStatistics data={data} /></div>
        {isAdmin && isActive && <div className="phase-foot phase-pause-row"><form style={{display: 'inline'}} onSubmit={(event) => {event.preventDefault(); pauseMutation.mutate();}}><input type="hidden" name="csrf_token" value={csrfToken} /><button type="submit" className={`btn-small ${data.conversation.status === 'paused' ? 'btn-approve' : 'btn-pause'}`}>{data.conversation.status === 'paused' ? msg('adminconv-resume') : msg('adminconv-pause')}</button></form>{data.conversation.status === 'paused' ? <span className="muted" style={{fontSize: 13}} dangerouslySetInnerHTML={richHtml(msg('adminconv-paused-note'))} /> : <span className="muted" style={{fontSize: 13}}>{msg('adminconv-pause-note')}</span>}</div>}
      </div>

      <div className="mode-guided-part">{transition ? canOrganize ? <><div className="phase-foot"><div className={`phase-foot-ready ${unmet ? 'phase-foot-ready--wait' : 'phase-foot-ready--go'}`}><span className="phase-foot-ready-icon" aria-hidden="true">{unmet ? '!' : '✓'}</span><span>{unmet ? msg('adminconv-readiness-unmet', unmet, phaseLabel(msg, transition.target.key, transition.target.label)) : msg('adminconv-no-blocking', phaseLabel(msg, transition.target.key, transition.target.label))}</span></div></div><div className="moveon phase-move-box"><div className="moveon-head"><span className="moveon-from">{phaseLabel(msg, transition.source.key, transition.source.label)}</span><span className="moveon-arrow dir-glyph" aria-hidden="true">→</span><span>{phaseLabel(msg, transition.target.key, transition.target.label)}</span></div><div className="moveon-body"><ul className="consequence"><li><span className="consequence-tag consequence-tag--opens">{msg('adminconv-tag-opens')}</span><span>{transition.consequence.opens}</span></li>{transition.consequence.closes && <li><span className="consequence-tag consequence-tag--closes">{msg('adminconv-tag-closes')}</span><span>{transition.consequence.closes}</span></li>}<li><span className="consequence-tag" style={{background: 'var(--surface2)', color: 'var(--muted)'}}>{msg('adminconv-tag-undo')}</span><span>{msg('adminconv-undo-text')}</span></li></ul><div className="console-section-label" style={{marginBottom: 8}}>{msg('adminconv-readiness-label')}</div><form className="phase-move-form" onSubmit={(event) => {event.preventDefault(); phaseMutation.mutate();}}><input type="hidden" name="csrf_token" value={csrfToken} /><ul className="readiness">{transition.preconditions.map((row) => <li key={row.id}><label><input type="checkbox" className="phase-move-check moveon-check" checked={phaseChecks.includes(row.id)} onChange={() => setPhaseChecks((items) => items.includes(row.id) ? items.filter((item) => item !== row.id) : [...items, row.id])} /><span className="readiness-label">{row.label} {row.met === true && <span className="readiness-note">({row.note || msg('adminconv-met')})</span>}{row.met === false && <><span className="phase-check-unmet"><span aria-hidden="true">✗</span> {msg('adminconv-not-met')}</span>{row.note && <span className="readiness-note">({row.note})</span>}</>}</span></label></li>)}</ul><p className="phase-move-hint moveon-hint muted">{msg('adminconv-move-hint')}</p><button type="submit" className="rd-btn-primary phase-move-submit" disabled={unmet > 0 || !allChecked}>{msg('adminconv-move-on-to', phaseLabel(msg, transition.target.key, transition.target.label))}</button></form>{transition.showPauseGuidance && <p className="muted" style={{fontSize: 12, marginTop: 10}}>{msg('adminconv-need-time')}</p>}</div></div></> : <><p className="muted" style={{fontSize: 13, marginTop: 14}}>{msg('adminconv-only-organizer')}</p><button type="button" className="btn-small" disabled title={msg('adminconv-only-organizer')}>{msg('adminconv-move-on-to', phaseLabel(msg, transition.target.key, transition.target.label))}</button></> : !data.phase.linear ? <p className="muted" style={{marginTop: 14, fontSize: 13}}><span aria-hidden="true">⚠️</span> {msg('adminconv-custom-state')} {isAdmin ? msg('adminconv-use-advanced') : msg('adminconv-admin-can-adjust')}</p> : <p className="muted" style={{marginTop: 14, fontSize: 13}} dangerouslySetInnerHTML={richHtml(msg(data.conversation.closedAt ? 'adminconv-report-published-note' : 'adminconv-report-unpublished-note'))} />}
        {isAdmin && data.schedule.canSchedule && <div className="schedule-card" style={{marginTop: 14}}><div className="schedule-main"><div className="schedule-title">{msg('adminconv-schedule-title', phaseLabel(msg, data.schedule.targetKey, data.schedule.targetLabel))}</div><div className="schedule-when">{data.schedule.scheduledAt ? <>{new Date(data.schedule.scheduledAt).toISOString().slice(0, 16).replace('T', ' ')} <span className="schedule-utc">UTC</span> · <span className="countdown-mini">{countdown(msg, data.schedule.scheduledAt)}</span>{data.schedule.frozen && ` · ${msg('adminconv-frozen')}`}</> : msg('adminconv-no-schedule')}</div></div><form className="schedule-actions" onSubmit={(event) => {event.preventDefault(); scheduleMutation.mutate({scheduledAt: new Date(`${scheduleAt}:00Z`).toISOString(), frozen: false});}}><input type="hidden" name="csrf_token" value={csrfToken} /><label className="sr-only" htmlFor="scheduled-at">{msg('adminconv-utc-timestamp')}</label><input id="scheduled-at" type="datetime-local" aria-label={msg('adminconv-scheduled-aria')} value={scheduleAt} onChange={(event) => setScheduleAt(event.target.value)} /><span className="schedule-utc" aria-hidden="true">UTC</span><button type="submit" className="btn-ghost">{data.schedule.scheduledAt ? msg('adminconv-edit') : msg('adminconv-set')}</button></form>{data.schedule.scheduledAt && <><form className="schedule-actions" onSubmit={(event) => {event.preventDefault(); scheduleMutation.mutate({scheduledAt: data.schedule.scheduledAt, frozen: !data.schedule.frozen});}}><button type="submit" className="btn-ghost">{data.schedule.frozen ? msg('adminconv-unfreeze') : msg('adminconv-freeze')}</button></form><form className="schedule-actions" onSubmit={(event) => {event.preventDefault(); scheduleMutation.mutate({scheduledAt: null, frozen: false});}}><button type="submit" className="btn-ghost">{msg('common-cancel')}</button></form></>}</div>}
        {isAdmin && transition && !data.schedule.canSchedule && <div className="locked-control" style={{marginTop: 14}}><strong>{msg('adminconv-scheduling-unavailable')}</strong><span className="locked-why">{msg('adminconv-scheduling-why')}</span></div>}
      </div>

      {isAdmin && <div className="mode-advanced-part"><div className="box-adv-note"><span aria-hidden="true">⚠️</span><span dangerouslySetInnerHTML={richHtml(msg('adminconv-advanced-note'))} /></div><form className="phases-form" style={{flexWrap: 'wrap', gap: '.75rem', marginTop: '.75rem'}} onSubmit={(event) => {event.preventDefault(); phasesMutation.mutate();}}><input type="hidden" name="csrf_token" value={csrfToken} />{data.phase.advancedControls.map((row) => <label key={row.key}><input type="checkbox" checked={advancedKeys.includes(row.key)} onChange={() => setAdvancedKeys((items) => items.includes(row.key) ? items.filter((item) => item !== row.key) : [...items, row.key])} /> {advancedPhaseLabel(msg, row.key, row.label)}</label>)}<button type="submit" className="btn-small phases-save">{msg('adminconv-save-phases')}</button></form>{data.phase.activeKeys.includes('informed_voting') && <div style={{marginTop: '1rem'}}><div className="console-section-label">{msg('adminconv-p6-setup-label')}</div>{data.phase.phase6Setup?.polisConversationId ? <p style={{fontSize: 13}}>{msg('adminconv-p6-conv')} <code>{data.phase.phase6Setup.polisConversationId}</code> · {msg('adminconv-p6-seeded', data.phase.phase6Setup.seededStatementCount, data.phase.phase6Setup.confirmedStatementCount)}</p> : <><p style={{fontSize: 13, marginBottom: '.5rem'}}>{msg('adminconv-p6-not-init')}</p><form onSubmit={(event) => {event.preventDefault(); initialization.mutate();}}><button type="submit" className="btn-small">{msg('adminconv-p6-init-btn')}</button></form></>}</div>}</div>}
      </div>

      <div className="console-section"><div className="console-section-label">{msg('adminconv-content-access')}</div><div className="manage-grid">
        <Link className="manage-card" to={data.links.statements}><div className="manage-card-title">{msg('adminconv-card-statements')}</div><div className="manage-card-desc">{msg('adminconv-card-statements-desc')}</div></Link>
        <Link className="manage-card" to={data.links.invitations}><div className="manage-card-top"><span className="manage-card-count">{msg('adminconv-invite-count', data.counts.invitations)}</span></div><div className="manage-card-title">{msg('adminconv-card-invites')}</div><div className="manage-card-desc">{msg('adminconv-card-invites-desc')}</div></Link>
        <Link className="manage-card" to={data.links.featuredStatements}><div className="manage-card-top"><span className="manage-card-count">{msg('adminconv-featured-count', data.counts.featuredStatements)}</span></div><div className="manage-card-title">{msg('adminconv-card-featured')}</div><div className="manage-card-desc">{msg('adminconv-card-featured-desc')}</div></Link>
        <Link className="manage-card" to={data.links.participants}><div className="manage-card-top"><span className="manage-card-count">{msg('adminconv-joined', data.counts.participants)}</span></div><div className="manage-card-title">{msg('adminconv-card-participants')}</div><div className="manage-card-desc">{msg('adminconv-card-participants-desc')}</div></Link>
        <Link className="manage-card" to={data.links.moderation}><div className="manage-card-top"><span className="manage-card-count">{msg('adminconv-open-count', data.counts.openFlags)}</span></div><div className="manage-card-title">{msg('adminconv-card-modqueue')}</div><div className="manage-card-desc">{msg('adminconv-card-modqueue-desc')}</div></Link>
        <Link className="manage-card" to={data.links.roles}><div className="manage-card-top"><span className="manage-card-count">{msg('adminconv-assigned-count', roleCount)}</span></div><div className="manage-card-title">{msg('adminconv-roles-label')}</div><div className="manage-card-desc">{msg('adminconv-card-roles-desc')}</div></Link>
        <Link className="manage-card" to={data.links.settings}><div className="manage-card-title">{msg('admin-overview-card-settings')}</div><div className="manage-card-desc">{msg('admin-overview-card-settings-desc')}</div></Link>
      </div></div>
      <RoleSection conversationId={conversationId} csrfToken={csrfToken} roster={roles} refresh={refreshSupporting} fail={fail} />
      {canOrganize && <ConfigurationSection settings={settings} />}
      {isAdmin && <DangerSection conversationId={conversationId} csrfToken={csrfToken} lifecycle={data} fail={fail} />}
    </div>
  </LegacyShell>;
}

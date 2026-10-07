import {useEffect, useId, useRef, useState, type FormEvent} from 'react';
import {useMutation, useQueryClient, useSuspenseQuery} from '@tanstack/react-query';

import type {components} from '../../api/schema';
import {ApiContractError} from '../../api/client';
import {
  adminLifecycleQuery,
  adminSettingsQuery,
  adminStatementWorkspaceQuery,
  putAdminSettings,
  putAdminStatementModerationPolicy,
} from '../../api/queries';
import {AdminShell} from './admin-shell';
import {InternalLink} from '../../internal-link';
import {escapeHtml, richHtml} from '../../i18n/rich-html';
import {useMessage, type Message} from '../../i18n/messages';

type Settings = components['schemas']['AdminSettings'];
type Policy = Settings['conversation']['accessPolicy'];
type GatingType = Settings['conversation']['gatingType'];
type Tier = Settings['recommendations']['tier'];
type Workspace = components['schemas']['AdminStatementWorkspace'];

/** Which Settings tab a page is. The route decides; the page never reads the URL. */
export type SettingsTab = 'basics' | 'access';

/** The answers to "who can take part" that this page offers, as one value.
 *
 * `gated` and `gatingType` travel separately on the wire, but only four of their
 * combinations are ones the server accepts from a new write today: not gated (no type),
 * gated with `invite_only`, with `voucher`, or with `wiki_based`. Keeping the answer as a
 * single radio value is what makes the impossible fifth combination -- gated with no type
 * -- unreachable from the page: the server refuses it for any row that is not already
 * gated ("a gated conversation needs a gating type", `services/admin_settings.py`).
 *
 * Two of the five are carried but never offered. `unset` is the read-back of a legacy row
 * that is gated with no stored type; such a row may be saved unchanged (the server's own
 * exception for it), so the page carries that state rather than silently rewriting it.
 * `wiki_based` is stored and accepted but admits nobody (`services/access.py` answers
 * `unknown` for every account), so it is not a thing anyone should be able to choose.
 *
 * Neither appears as a greyed control: a control that cannot be operated is still a tab
 * stop, is still announced as a radio, and invites a click that does nothing. What is
 * genuinely missing is said once in prose at the foot of the group instead (`COMING_*`
 * below -- inside the fieldset, so it closes its own question rather than running into the
 * next legend), so the group contains only answers that work. A row already storing one of the two keeps
 * it -- nothing here rewrites it -- but it shows as no answer selected, the same as today
 * for `unset`. */
type Admission = 'anyone' | 'invite_only' | 'voucher' | 'wiki_based' | 'unset';

/** What does not exist yet, said in prose rather than mimed with a dead control.
 *
 * A control that saves a value nothing reads is the same bug as a control the server
 * silently ignores: the organizer is told their answer took effect and no page ever acts
 * on it. `announce`, `information`, `results_shared`, `show_usernames` and
 * `access_request_text` are written and read back by the settings endpoint and by nothing
 * else -- no participant-facing page, lane query, about payload, results report or
 * identity-reveal step consults them -- so what they promise is named here instead of
 * offered. The stored values still travel out and back untouched (see the mutation below):
 * the page stops asking about them, it does not clear them.
 *
 * Hardcoded English on purpose: a placeholder for unshipped functionality gets no message
 * key and no qqq entry, so translators are not asked to carry a string that leaves again
 * when the functionality lands (`.claude/admin-review/message-key-convention.md`). */
const COMING_ADMISSION
  = 'Also coming: a policy based on wiki activity — not available yet (#406)';
const COMING_VISIBILITY
  = 'Also coming: choosing what people without access can see, and what to tell them'
    + ' — not available yet';
const COMING_REVEAL
  = 'Also coming: participants choosing to show their username — not available yet';

function admissionOf(conversation: Settings['conversation']): Admission {
  if (!conversation.gated) return 'anyone';
  return conversation.gatingType ?? 'unset';
}

function admissionWire(admission: Admission): {gated: boolean; gatingType: GatingType} {
  if (admission === 'anyone') return {gated: false, gatingType: null};
  if (admission === 'unset') return {gated: true, gatingType: null};
  return {gated: true, gatingType: admission};
}

function admissionLabel(msg: Message, admission: Admission): string {
  switch (admission) {
    case 'anyone': return msg('admin-access-admission-anyone');
    case 'invite_only': return msg('admin-access-admission-invited');
    case 'voucher': return msg('admin-access-admission-voucher');
    case 'wiki_based': return msg('admin-access-admission-wiki');
    default: return '—';
  }
}

/** The per-field messages of a 400 `validation_failed`, keyed by the request field. */
function fieldErrors(error: unknown): Record<string, string[]> {
  if (!(error instanceof ApiContractError) || error.code !== 'validation_failed') return {};
  const details = error.details as {fields?: Record<string, string[]>} | undefined;
  return details?.fields ?? {};
}

/** The field named by a 409 `access_settings_locked` (`gated`, `gating_type` or
 *  `show_usernames`), so the refusal can be shown beside the row it is about. */
function lockedField(error: unknown): string | null {
  if (!(error instanceof ApiContractError)
      || error.code !== 'access_settings_locked') return null;
  const details = error.details as {field?: string} | undefined;
  return details?.field ?? null;
}

function LockGlyph({label}: {label: string}) {
  return (
    <span className="access-lock" title={label} role="img" aria-label={label}>
      <svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor"
        strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <rect x="3" y="7" width="10" height="7" rx="1.5" />
        <path d="M5.5 7V4.8a2.5 2.5 0 0 1 5 0V7" />
      </svg>
    </span>
  );
}

/** The four Settings tabs, in the order the strip shows them.
 *
 * The third is named by the answer to "who gets in": a consultation gated on voucher codes
 * has vouchers to manage, everything else has an invitation list. Both point at the page
 * that exists today (#473 moves them under this strip in the next step). */
function SettingsTabs({conversationId, gatingType, current}: {
  conversationId: number;
  gatingType: GatingType;
  current: SettingsTab;
}) {
  const msg = useMessage();
  const base = `/admin/conversations/${conversationId}`;
  const tabs = [
    {id: 'basics', label: msg('admin-settings-tab-basics'), href: `${base}/settings/basics`},
    {id: 'access', label: msg('admin-access-heading'), href: `${base}/settings/access`},
    {id: 'membership', label: gatingType === 'voucher'
      ? msg('admin-settings-tab-vouchers')
      : msg('admin-settings-tab-invitations'), href: `${base}/invites`},
    {id: 'roles', label: msg('admin-settings-tab-roles'), href: `${base}/roles`},
  ];
  return (
    <nav className="settings-tabs" aria-label={msg('admin-settings-tabs-aria')}>
      {tabs.map((tab) => (
        <InternalLink
          key={tab.id}
          href={tab.href}
          className="settings-tabs__tab"
          aria-current={tab.id === current ? 'page' : undefined}
        >
          {tab.label}
        </InternalLink>
      ))}
    </nav>
  );
}

/** The Approval control, moved here from the statements page (#478, decision a).
 *
 * It keeps its own endpoint and its own body -- `{mode}` on
 * `PUT …/statement-moderation-policy` -- because the moderation policy is not one of the
 * fields the settings endpoint takes. It reads its state from the statements workspace
 * (`moderationPolicy.mode`), which is why this tab runs that query, and the receipt writes
 * the returned workspace back into it, so the checkbox and the statements list never
 * disagree. Its form is rendered after the settings form, never inside it: a nested form's
 * submit would also reach the settings form and send a settings PUT. */
function ApprovalControl({conversationId, csrfToken, number}: {
  conversationId: number;
  csrfToken: string;
  number: string;
}) {
  const msg = useMessage();
  const queryClient = useQueryClient();
  const options = adminStatementWorkspaceQuery(conversationId);
  const {data} = useSuspenseQuery(options);
  const [strictModeration, setStrictModeration] = useState(data.moderationPolicy.mode === 'moderate');
  const [error, setError] = useState<string | null>(null);
  const mutation = useMutation({
    mutationFn: () => putAdminStatementModerationPolicy(
      conversationId,
      {mode: strictModeration ? 'moderate' : 'auto_approve'},
      csrfToken,
    ),
    onSuccess: (receipt) => {
      queryClient.setQueryData<Workspace>(options.queryKey, receipt.workspace);
      setStrictModeration(receipt.mode === 'moderate');
      setError(null);
    },
    onError: (failure: Error) => {
      if (failure instanceof ApiContractError && failure.code === 'verification_unavailable') {
        setError('Could not verify the current moderation state. Try again later.');
      } else if (failure instanceof ApiContractError && failure.code === 'upstream_unavailable') {
        setError('Could not update moderation settings. Check server logs for details.');
      } else if (failure instanceof ApiContractError && failure.code === 'command_outcome_unknown') {
        setError('The voting service may have been updated, but the local policy could not be saved. Do not retry until a site admin checks it.');
      } else {
        setError('Could not save the moderation policy. Try again later.');
      }
    },
  });
  return (
    // `settings-approval` gives this section, outside `.settings-form`, the same header
    // grid and spacing as the numbered sections inside it (styles.css).
    <section className="settings-approval" aria-labelledby="settings-approval">
      <header><span>{number}</span><div><h3 id="settings-approval">{msg('stmts-modsettings-heading')}</h3></div></header>
      <form onSubmit={(event) => { event.preventDefault(); mutation.mutate(); }}>
        <input type="hidden" name="csrf_token" value={csrfToken} />
        <label className="checkbox-label" style={{fontWeight: 'normal', color: 'var(--text)'}}>
          <input
            type="checkbox"
            name="strict_moderation"
            value="1"
            checked={strictModeration}
            onChange={(event) => setStrictModeration(event.target.checked)}
          />
          {msg('stmts-strict-label')}
        </label>
        <div style={{marginTop: '.75rem'}}>
          <button type="submit" className="btn-small" disabled={mutation.isPending}>{msg('stmts-save')}</button>
        </div>
        {error && <p role="alert" className="command-error">{error}</p>}
      </form>
    </section>
  );
}

export function AdminSettingsPage({conversationId, csrfToken, tab = 'basics'}: {
  conversationId: number; csrfToken: string; tab?: SettingsTab | undefined;
}) {
  const msg = useMessage();
  const queryClient = useQueryClient();
  const options = adminSettingsQuery(conversationId);
  const {data} = useSuspenseQuery(options);
  // The console shell frames the page, and the frame is built from the lifecycle DTO.
  const {data: lifecycle} = useSuspenseQuery(adminLifecycleQuery(conversationId));
  const [title, setTitle] = useState(data.conversation.title);
  const [introHtml, setIntroHtml] = useState(data.conversation.introHtml);
  const [outroHtml, setOutroHtml] = useState(data.conversation.outroHtml);
  const [accessPolicy, setAccessPolicy] = useState<Policy>(data.conversation.accessPolicy);
  const [admission, setAdmission] = useState<Admission>(admissionOf(data.conversation));
  const [eligibilityEventId, setEligibilityEventId] = useState(data.eligibility.eventId);
  const [eligibilityLabel, setEligibilityLabel] = useState(data.eligibility.label ?? '');
  const [tier, setTier] = useState<Tier>(data.recommendations.tier);
  const [confirming, setConfirming] = useState(false);
  const confirmRef = useRef<HTMLDivElement>(null);
  const saveRef = useRef<HTMLButtonElement>(null);
  const wasConfirming = useRef(false);
  const summaryRef = useRef<HTMLDivElement>(null);
  const ids = useId();
  const canEdit = data.capabilities.edit;
  // Only a site admin moves a consultation into or out of the Practice Environment (#472);
  // everyone else sees whether it is in it, as a fact, never as a choice.
  const canSwitchDemo = data.capabilities.switchDemo;
  const practice = accessPolicy === 'demo';
  // Both flags carry the same server predicate (the Explore phase flag); either one being
  // true means the stored admission answer cannot change, so the row renders as text --
  // which is what today's page does by disabling both of its access controls.
  const admissionLocked = Boolean(data.locks?.gated || data.locks?.gatingType);
  const stored = admissionOf(data.conversation);
  // The five settings nothing reads are sent back exactly as they were read, so none of
  // them can ever be the field a 409 names, and a save cannot quietly rewrite a value the
  // page no longer shows. They are kept out of component state for that reason. The
  // endpoint takes one of three complete key sets and refuses anything else
  // ("Provide the complete settings representation.", `api/admin_routes.py`), so dropping
  // the keys from the body is not an option: the whole save would 400. Every tab sends the
  // whole representation, so a save on one tab writes the other tab's fields back as they
  // were loaded; last write wins.
  const {
    announce, information, resultsShared, showUsernames, accessRequestText,
  } = data.conversation;
  const gated = admission !== 'anyone';

  const mutation = useMutation({
    mutationFn: () => putAdminSettings(conversationId, {
      title, introHtml, outroHtml, accessPolicy, eligibilityEventId,
      eligibilityLabel, recommendationTier: tier, ...admissionWire(admission),
      announce, information, resultsShared, showUsernames, accessRequestText,
    }, csrfToken),
    onSuccess: (receipt) => {
      queryClient.setQueryData<Settings>(options.queryKey, receipt.settings);
      // The server clears the eligibility pair when the invitation list is chosen; show
      // what it stored, not what was typed, or the inputs keep an event ID that is gone.
      setEligibilityEventId(receipt.settings.eligibility.eventId);
      setEligibilityLabel(receipt.settings.eligibility.label ?? '');
    },
  });

  // Narrowing is measured against what the server last told us, not against the first
  // render: after a save the stored answers are the new baseline. Every move to a different
  // gated answer counts, not only anyone -> gated: invitation list -> voucher, and the
  // legacy `unset` row -> a real gate, both take access away from people who have it today.
  // Only a move *to* "anyone" widens. The admission answer is the only thing left that can
  // narrow: the visibility settings are no longer editable here, so a save cannot take
  // visibility away from anybody.
  const narrowing = stored !== admission && admission !== 'anyone';

  const fields = fieldErrors(mutation.error);
  const fieldMessages = Object.values(fields).flat();
  // The admission radio group answers both wire fields, so a refusal of either is shown
  // once, under the group, and linked from every live choice in it.
  const admissionMessages = [...(fields.gated ?? []), ...(fields.gatingType ?? [])];
  const admissionInvalid = admissionMessages.length
    ? {'aria-invalid': true, 'aria-describedby': `${ids}-gated-error`}
    : {};
  const locked = lockedField(mutation.error);
  const serverMessage = mutation.error instanceof ApiContractError
    ? mutation.error.message : null;
  const generalError = mutation.error instanceof ApiContractError
    ? (fieldMessages.length || locked ? null : serverMessage)
    : mutation.error ? 'Settings could not be saved.' : null;

  // The question takes focus when it opens; when it closes, by Cancel or by Continue, the
  // buttons that held focus are gone, so focus goes back to the Save button.
  useEffect(() => {
    if (confirming) confirmRef.current?.focus();
    else if (wasConfirming.current) saveRef.current?.focus();
    wasConfirming.current = confirming;
  }, [confirming]);
  // The question is about a change that is on screen: put the widest answer back and it has
  // nothing left to ask about, so it goes away with the narrowing it was asking about.
  useEffect(() => {
    if (!narrowing) setConfirming(false);
  }, [narrowing]);
  // Keyed on the attempt, not on the message count, so a second refusal naming the same
  // number of fields still moves focus to the summary.
  useEffect(() => {
    if (fieldMessages.length) summaryRef.current?.focus();
  }, [mutation.failureCount, fieldMessages.length]);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    // Widening saves at once; narrowing asks once, inside the page, keeping every input.
    if (narrowing && !confirming) {
      setConfirming(true);
      return;
    }
    setConfirming(false);
    mutation.mutate();
  }

  /** `aria-invalid` plus the link to the message, for a field the server refused. */
  function invalid(field: string) {
    return fields[field]
      ? {'aria-invalid': true, 'aria-describedby': `${ids}-${field}-error`} : {};
  }

  function FieldError({field}: {field: string}) {
    const messages = fields[field];
    if (!messages) return null;
    return <p className="access-field-error" id={`${ids}-${field}-error`}>{messages.join(' ')}</p>;
  }

  // The Practice switch is shown only to a site admin, and not while Explore locks access.
  const canSwitchPractice = !gated && canSwitchDemo && !admissionLocked;
  const practiceSection = practice || canSwitchPractice;
  const tabName = tab === 'basics'
    ? msg('admin-settings-tab-basics')
    : msg('admin-access-heading');

  return (
    <AdminShell
      title={msg('adminconv-doc-title', lifecycle.conversation.title)}
      data={lifecycle}
      gatingType={data.conversation.gatingType}
      section="settings"
      subPage={tabName}
    >
      <div className="settings-shell">
        <h1>{msg('admin-settings-heading')}</h1>
        <SettingsTabs conversationId={conversationId} gatingType={data.conversation.gatingType} current={tab} />
        <h2>{tabName}</h2>
        {!canEdit && <p className="settings-readonly" role="note">
          Your role can inspect but not change these settings.
        </p>}
        <form className="settings-form" onSubmit={submit}>
          {fieldMessages.length > 0 && <div className="access-summary" role="alert" tabIndex={-1} ref={summaryRef}>
            <ul>{Object.entries(fields).map(([field, messages]) => (
              <li key={field}>{messages.join(' ')}</li>
            ))}</ul>
          </div>}
          {tab === 'basics' ? <>
            <section aria-labelledby="settings-description">
              <header><span>01</span><div><h3 id="settings-description">Description</h3></div></header>
              <label>{msg('admin-label-title')}<input value={title} maxLength={255} required {...invalid('title')} onChange={(event) => setTitle(event.target.value)} /></label>
              <FieldError field="title" />
              <label>Introduction HTML<textarea value={introHtml} rows={7} onChange={(event) => setIntroHtml(event.target.value)} /></label>
              <label>Closing HTML<textarea value={outroHtml} rows={5} onChange={(event) => setOutroHtml(event.target.value)} /></label>
              <p className="settings-hint">Allowed HTML is sanitized by the server when saved.</p>
              {/* Admin-written texts meant for publication are CC0, like participants'
                  contributions; the deed link is built as on the join screen. */}
              <p className="settings-hint" dangerouslySetInnerHTML={richHtml(msg('admin-settings-basics-licence', '<a href="https://creativecommons.org/publicdomain/zero/1.0/" target="_blank" rel="noopener">' + `${escapeHtml(msg('accept-licence-link'))}<span class="sr-only"> ${escapeHtml(msg('common-opens-in-new-tab'))}</span></a>`))} />
            </section>
            <section aria-labelledby="settings-guidance">
              <header><span>02</span><div><h3 id="settings-guidance">Guidance scope</h3></div></header>
              <fieldset><legend>Complexity tier</legend>{data.recommendations.tiers.map((option) => (
                <label className="settings-tier" key={option.key}>
                  <input type="radio" name="tier" value={option.key} checked={tier === option.key} onChange={() => setTier(option.key)} />
                  <strong>{option.label}</strong>
                  <span>{Object.values(option.quantities).join(' · ')}</span>
                </label>
              ))}</fieldset>
            </section>
            {/* The Practice Environment section: the fixed answer a practice item has, and the
                switch that moves one in or out of it. Nothing at all when neither applies, so
                there is no heading without content under it. Hidden while Explore locks access:
                moving into or out of Practice rewrites the locked settings, which the server
                refuses then. */}
            {practiceSection && <section aria-labelledby="settings-practice">
              <header><span>03</span><div><h3 id="settings-practice">{msg('admin-access-practice')}</h3></div></header>
              {practice && <div className="access-answer" role="group" aria-labelledby={`${ids}-practice-legend`}>
                {/* One fixed answer, stored by the server whatever is sent, so it is stated
                    rather than offered: a gate here would only be refused. */}
                <p className="access-answer-legend" id={`${ids}-practice-legend`}>{msg('admin-access-admission-legend')}</p>
                <p className="access-answer-value">{msg('admin-access-admission-practice')}</p>
              </div>}
              {canSwitchPractice && <label>Legacy access mode<select value={accessPolicy} onChange={(event) => setAccessPolicy(event.target.value as Policy)}>
                <option value="public">Not gated</option><option value="demo">Practice</option>
              </select></label>}
            </section>}
          </> : <section aria-label={msg('admin-access-heading')}>
            {/* A practice item has no admission choice: the server stores one fixed answer
                whatever is sent, and the Practice Environment section on Basics states it.
                Only the admission group is left out; the eligibility fields stay. The tab has
                one section, so it carries no number. */}
            {!practice && <>
              {admissionLocked ? <div className="access-answer">
                <p className="access-answer-legend">{msg('admin-access-admission-legend')}</p>
                <p className="access-answer-value">
                  {admissionLabel(msg, stored)} <LockGlyph label={msg('admin-access-locked-note')} />
                </p>
              </div> : <fieldset className="access-choices">
                <legend>{msg('admin-access-admission-legend')}</legend>
                <label className="access-choice">
                  <input type="radio" name="admission" value="anyone" checked={admission === 'anyone'} {...admissionInvalid} onChange={() => setAdmission('anyone')} />
                  <span>{msg('admin-access-admission-anyone')}</span>
                </label>
                <label className="access-choice">
                  <input type="radio" name="admission" value="invite_only" checked={admission === 'invite_only'} {...admissionInvalid} onChange={() => setAdmission('invite_only')} />
                  <span>{msg('admin-access-admission-invited')}</span>
                </label>
                <label className="access-choice">
                  <input type="radio" name="admission" value="voucher" checked={admission === 'voucher'} {...admissionInvalid} onChange={() => setAdmission('voucher')} />
                  <span>{msg('admin-access-admission-voucher')}</span>
                </label>
                <p className="settings-hint">{COMING_ADMISSION}</p>
              </fieldset>}
              {gated && <>
                <p className="settings-hint">{COMING_VISIBILITY}</p>
                <p className="settings-hint">{COMING_REVEAL}</p>
              </>}
            </>}
            {admissionMessages.length > 0 &&<p className="access-field-error" id={`${ids}-gated-error`}>{admissionMessages.join(' ')}</p>}
            {locked && <p className="access-field-error" role="alert">{serverMessage}</p>}
            <label>{msg('admin-label-elig-event')}<input value={eligibilityEventId} maxLength={80} placeholder={msg('admin-elig-event-ph')} {...invalid('eligibilityEventId')} onChange={(event) => setEligibilityEventId(event.target.value)} /></label>
            <FieldError field="eligibilityEventId" />
            <label>{msg('admin-label-elig-label')}<input value={eligibilityLabel} maxLength={255} placeholder={msg('admin-elig-label-ph')} {...invalid('eligibilityLabel')} onChange={(event) => setEligibilityLabel(event.target.value)} /></label>
            <FieldError field="eligibilityLabel" />
            <div className="settings-eligibility" data-configured={data.eligibility.configured}>
              <strong>Eligibility {data.eligibility.configured ? 'configured' : 'not configured'}</strong>
              {data.eligibility.label && <span>{data.eligibility.label}</span>}
              <p>{data.eligibility.note}</p>
            </div>
          </section>}
          {canEdit && <footer>
            {confirming ? <div className="access-confirm" role="group" aria-labelledby={`${ids}-confirm`} tabIndex={-1} ref={confirmRef}>
              <p id={`${ids}-confirm`}>{msg('admin-access-narrowing-confirm')}</p>
              <button type="submit" disabled={mutation.isPending}>{msg('admin-access-narrowing-continue')}</button>
              <button type="button" onClick={() => setConfirming(false)}>{msg('common-cancel')}</button>
            </div> : <button type="submit" disabled={mutation.isPending} ref={saveRef}>
              {mutation.isPending ? 'Saving…' : msg('adminconv-save-settings')}
            </button>}
            {mutation.data && <p role="status">{mutation.data.changed ? 'Settings saved.' : 'Settings already up to date.'}</p>}
            {generalError && <p role="alert">{generalError}</p>}
          </footer>}
        </form>
        {tab === 'basics' && <>
          {/* Outside the settings form: the Approval control has a form of its own. */}
          <ApprovalControl conversationId={conversationId} csrfToken={csrfToken} number={practiceSection ? '04' : '03'} />
          <p className="admin-shell__coming" lang="en">Also coming: the language the consultation is written in — not available yet (#473)</p>
          <p className="admin-shell__coming" lang="en">Also coming: keeping the submission form open while new statements are no longer shown — not available yet (#473)</p>
          <p className="admin-shell__coming" lang="en">Also coming: publishing the moderation log — not available yet (#473)</p>
        </>}
      </div>
    </AdminShell>
  );
}

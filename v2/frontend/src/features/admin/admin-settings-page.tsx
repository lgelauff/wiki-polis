import {useEffect, useId, useRef, useState, type FormEvent} from 'react';
import {useMutation, useQueryClient, useSuspenseQuery} from '@tanstack/react-query';
import {Link} from 'react-router-dom';

import type {components} from '../../api/schema';
import {ApiContractError} from '../../api/client';
import {adminSettingsQuery, putAdminSettings} from '../../api/queries';
import {useMessage, type Message} from '../../i18n/messages';

type Settings = components['schemas']['AdminSettings'];
type Policy = Settings['conversation']['accessPolicy'];
type GatingType = Settings['conversation']['gatingType'];
type Tier = Settings['recommendations']['tier'];

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
 * Hardcoded English on purpose: a placeholder for unshipped functionality gets no message
 * key and no qqq entry, so translators are not asked to carry a string that leaves again
 * when the functionality lands (`.claude/admin-review/message-key-convention.md`). */
const COMING_ADMISSION
  = 'Also coming: a policy based on wiki activity — not available yet (#406)';
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
    case 'wiki_based': return 'Wiki policy';
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

export function AdminSettingsPage({conversationId, csrfToken}: {
  conversationId: number; csrfToken: string;
}) {
  const msg = useMessage();
  const queryClient = useQueryClient();
  const options = adminSettingsQuery(conversationId);
  const {data} = useSuspenseQuery(options);
  const [title, setTitle] = useState(data.conversation.title);
  const [introHtml, setIntroHtml] = useState(data.conversation.introHtml);
  const [outroHtml, setOutroHtml] = useState(data.conversation.outroHtml);
  const [accessPolicy, setAccessPolicy] = useState<Policy>(data.conversation.accessPolicy);
  const [admission, setAdmission] = useState<Admission>(admissionOf(data.conversation));
  const [announce, setAnnounce] = useState(data.conversation.announce);
  const [information, setInformation] = useState(data.conversation.information);
  const [resultsShared, setResultsShared] = useState(data.conversation.resultsShared);
  const [accessRequestText, setAccessRequestText] = useState(
    data.conversation.accessRequestText ?? '',
  );
  const [eligibilityEventId, setEligibilityEventId] = useState(data.eligibility.eventId);
  const [eligibilityLabel, setEligibilityLabel] = useState(data.eligibility.label ?? '');
  const [tier, setTier] = useState<Tier>(data.recommendations.tier);
  const [confirming, setConfirming] = useState(false);
  const confirmRef = useRef<HTMLDivElement>(null);
  const summaryRef = useRef<HTMLDivElement>(null);
  const ids = useId();
  const canEdit = data.capabilities.edit;
  // Both flags carry the same server predicate (the Explore phase flag); either one being
  // true means the stored admission answer cannot change, so the row renders as text --
  // which is what today's page does by disabling both of its access controls.
  const admissionLocked = Boolean(data.locks?.gated || data.locks?.gatingType);
  const stored = admissionOf(data.conversation);
  // The username-reveal option is sent back exactly as it was read, so it can never be the
  // field a 409 names; it is kept out of component state for that reason.
  const showUsernames = data.conversation.showUsernames;
  const gated = admission !== 'anyone';

  const mutation = useMutation({
    mutationFn: () => putAdminSettings(conversationId, {
      title, introHtml, outroHtml, accessPolicy, eligibilityEventId,
      eligibilityLabel, recommendationTier: tier, ...admissionWire(admission),
      announce, information, resultsShared, showUsernames, accessRequestText,
    }, csrfToken),
    onSuccess: (receipt) => queryClient.setQueryData<Settings>(
      options.queryKey, receipt.settings,
    ),
  });

  // Narrowing is measured against what the server last told us, not against the first
  // render: after a save the stored answers are the new baseline. Every move to a different
  // gated answer counts, not only anyone -> gated: invitation list -> voucher, and the
  // legacy `unset` row -> a real gate, both take access away from people who have it today.
  // Only a move *to* "anyone" widens.
  const narrowing = (stored !== admission && admission !== 'anyone')
    || (data.conversation.announce && !announce)
    || (data.conversation.information && !information)
    || (data.conversation.resultsShared && !resultsShared);

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

  useEffect(() => {
    if (confirming) confirmRef.current?.focus();
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

  return (
    <main className="settings-shell" id="main">
      <nav className="record-breadcrumb" aria-label={msg('admin-crumb-aria')}>
        <Link to="/admin">{msg('admin-nav-panel')}</Link><span>/</span>
        <Link to={data.links.lifecycle}>{data.conversation.title}</Link><span>/</span>
        <span>{msg('admin-access-heading')}</span>
      </nav>
      <header className="settings-heading">
        <p className="eyebrow">Configuration &middot; {data.conversation.slug}</p>
        <h1>{msg('admin-access-heading')}</h1>
        <p>Describe the consultation, control access, and choose the scope used for tool guidance.</p>
      </header>
      {!canEdit && <p className="settings-readonly" role="note">
        Your role can inspect but not change these settings.
      </p>}
      <form className="settings-form" onSubmit={submit}>
        {fieldMessages.length > 0 && <div className="access-summary" role="alert" tabIndex={-1} ref={summaryRef}>
          <ul>{Object.entries(fields).map(([field, messages]) => (
            <li key={field}>{messages.join(' ')}</li>
          ))}</ul>
        </div>}
        <section aria-labelledby="settings-description">
          <header><span>01</span><div><h2 id="settings-description">Description</h2><p>Participant-facing title and rich-text context.</p></div></header>
          <label>{msg('admin-label-title')}<input value={title} maxLength={255} required {...invalid('title')} onChange={(event) => setTitle(event.target.value)} /></label>
          <FieldError field="title" />
          <label>Introduction HTML<textarea value={introHtml} rows={7} onChange={(event) => setIntroHtml(event.target.value)} /></label>
          <label>Closing HTML<textarea value={outroHtml} rows={5} onChange={(event) => setOutroHtml(event.target.value)} /></label>
          <p className="settings-hint">Allowed HTML is sanitized by the server when saved.</p>
        </section>
        <section aria-label={msg('admin-access-heading')}>
          <header><span>02</span><div><p>Who can discover and join this consultation.</p></div></header>
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
          {admissionMessages.length > 0 &&<p className="access-field-error" id={`${ids}-gated-error`}>{admissionMessages.join(' ')}</p>}
          {locked && <p className="access-field-error" role="alert">{serverMessage}</p>}
          {!gated && <label>Legacy access mode<select value={accessPolicy} onChange={(event) => setAccessPolicy(event.target.value as Policy)}>
            <option value="public">Not gated</option><option value="demo">Demo</option>
          </select></label>}
          {gated && <fieldset className="access-choices">
            <legend>{msg('admin-access-visibility-legend')}</legend>
            <label className="access-choice">
              <input type="checkbox" checked={announce} onChange={(event) => setAnnounce(event.target.checked)} />
              <span>{msg('admin-access-visibility-announce')}</span>
            </label>
            <label className="access-choice">
              <input type="checkbox" checked={information} onChange={(event) => setInformation(event.target.checked)} />
              <span>{msg('admin-access-visibility-information')}</span>
            </label>
            <label className="access-choice">
              <input type="checkbox" checked={resultsShared} onChange={(event) => setResultsShared(event.target.checked)} />
              <span>{msg('admin-access-visibility-results')}</span>
            </label>
            <p className="settings-hint">{COMING_REVEAL}</p>
          </fieldset>}
          {gated && <label>{msg('admin-access-request-label')}<textarea value={accessRequestText} rows={3} onChange={(event) => setAccessRequestText(event.target.value)} /></label>}
          <label>{msg('admin-label-elig-event')}<input value={eligibilityEventId} maxLength={80} placeholder={msg('admin-elig-event-ph')} {...invalid('eligibilityEventId')} onChange={(event) => setEligibilityEventId(event.target.value)} /></label>
          <FieldError field="eligibilityEventId" />
          <label>{msg('admin-label-elig-label')}<input value={eligibilityLabel} maxLength={255} placeholder={msg('admin-elig-label-ph')} {...invalid('eligibilityLabel')} onChange={(event) => setEligibilityLabel(event.target.value)} /></label>
          <FieldError field="eligibilityLabel" />
          <div className="settings-eligibility" data-configured={data.eligibility.configured}>
            <strong>Eligibility {data.eligibility.configured ? 'configured' : 'not configured'}</strong>
            {data.eligibility.label && <span>{data.eligibility.label}</span>}
            <p>{data.eligibility.note}</p>
          </div>
        </section>
        <section aria-labelledby="settings-guidance">
          <header><span>03</span><div><h2 id="settings-guidance">Guidance scope</h2><p>The tool owns the recommended quantities for each tier.</p></div></header>
          <fieldset><legend>Complexity tier</legend>{data.recommendations.tiers.map((option) => (
            <label className="settings-tier" key={option.key}>
              <input type="radio" name="tier" value={option.key} checked={tier === option.key} onChange={() => setTier(option.key)} />
              <strong>{option.label}</strong>
              <span>{Object.values(option.quantities).join(' · ')}</span>
            </label>
          ))}</fieldset>
        </section>
        {canEdit && <footer>
          {confirming ? <div className="access-confirm" tabIndex={-1} ref={confirmRef}>
            <p>{msg('admin-access-narrowing-confirm')}</p>
            <button type="submit" disabled={mutation.isPending}>{msg('admin-access-narrowing-continue')}</button>
            <button type="button" onClick={() => setConfirming(false)}>{msg('common-cancel')}</button>
          </div> : <button type="submit" disabled={mutation.isPending}>
            {mutation.isPending ? 'Saving…' : msg('adminconv-save-settings')}
          </button>}
          {mutation.data && <p role="status">{mutation.data.changed ? 'Settings saved.' : 'Settings already up to date.'}</p>}
          {generalError && <p role="alert">{generalError}</p>}
        </footer>}
      </form>
    </main>
  );
}

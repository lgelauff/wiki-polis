import {useEffect, useRef, useState, type FormEvent} from 'react';
import {useMutation, useSuspenseQuery} from '@tanstack/react-query';
import {useParams} from 'react-router-dom';

import {ApiContractError} from '../../api/client';
import type {components} from '../../api/schema';
import {
  createParticipation,
  getPseudonymSuggestions,
  participationEntryQuery,
  sessionQuery,
} from '../../api/queries';
import {NavigationRedirect} from './external-redirect';
import {LegacyShell} from './legacy-shell';
import {InternalLink} from '../../internal-link';
import {useMessage} from '../../i18n/messages';
import {joinErrorCopy} from '../../i18n/server-labels';
import {escapeHtml, richHtml} from '../../i18n/rich-html';

function requiredSlug(value: string | undefined) {
  if (!value) throw new Error('Missing route parameter: slug');
  return value;
}

export function ParticipationEntryLegacyPage() {
  const slug = requiredSlug(useParams().slug);
  const {data: session} = useSuspenseQuery(sessionQuery());
  if (session.state !== 'authenticated' && session.state !== 'voucher') {
    return <NavigationRedirect href={session.links.login} />;
  }
  return <AuthenticatedParticipationEntry slug={slug} csrfToken={session.csrfToken} voucher={session.state === 'voucher'} />;
}

function AuthenticatedParticipationEntry({slug, csrfToken, voucher}: {
  slug: string;
  csrfToken: string;
  voucher: boolean;
}) {
  const {data} = useSuspenseQuery(participationEntryQuery(slug));
  switch (data.state) {
    case 'redirect':
      return <NavigationRedirect href={data.href} />;
    case 'join':
      return <JoinPage data={data} csrfToken={csrfToken} voucher={voucher} />;
    case 'invite_denied':
    case 'access_lost':
      return <InviteDeniedPage data={data} />;
  }
}

type ParticipationEntry = components['schemas']['ParticipationEntryResponse']['data'];
type InviteDeniedEntry = Extract<ParticipationEntry, {state: 'invite_denied' | 'access_lost'}>;
type JoinEntry = Extract<ParticipationEntry, {state: 'join'}>;

// The server sends why access was refused and how sure it is; the page says that, rather than
// reading every refusal as a missing invitation. A check that could not decide comes first:
// telling someone they are not invited, when nobody knows, would be wrong in either direction.
function refusalCopy(data: InviteDeniedEntry, msg: ReturnType<typeof useMessage>) {
  const title = escapeHtml(data.conversation.title);
  if (data.certainty === 'temporary') {
    return {heading: msg('forbidden-unconfirmed-heading'), body: msg('forbidden-unconfirmed-temporary', title), invite: false};
  }
  if (data.certainty === 'inconclusive') {
    return {heading: msg('forbidden-unconfirmed-heading'), body: msg('forbidden-unconfirmed-inconclusive', title), invite: false};
  }
  if (data.reason === 'access-voucher-other') {
    return {heading: msg('forbidden-voucher-other-heading'), body: msg('forbidden-voucher-other-body', title), invite: false};
  }
  if (data.reason === 'access-voucher-revoked') {
    return {heading: msg('forbidden-lost-voucher-heading'), body: msg('forbidden-lost-voucher-body', title), invite: false};
  }
  const invite = data.reason === 'access-invite-required';
  if (data.state === 'access_lost') {
    return invite
      ? {heading: msg('forbidden-lost-invite-heading'), body: msg('forbidden-lost-invite-body', title), invite}
      : {heading: msg('forbidden-lost-heading'), body: msg('forbidden-lost-body', title), invite};
  }
  return invite
    ? {heading: msg('forbidden-invite-heading'), body: msg('forbidden-invite-body', title), invite}
    : {heading: msg('forbidden-access-heading'), body: msg('forbidden-access-body', title), invite};
}

function InviteDeniedPage({data}: {data: InviteDeniedEntry}) {
  const msg = useMessage();
  const copy = refusalCopy(data, msg);
  return (
    <LegacyShell title={msg('forbidden-invite-doc-title')}>
      <div className="container" style={{maxWidth: 700, paddingTop: '3rem'}}>
        <h1 style={{fontSize: 24, fontWeight: 600, color: 'var(--ink)', margin: '0 0 .75rem'}}>
          {copy.heading}
        </h1>
        <p style={{color: 'var(--body)', fontSize: 15, lineHeight: 1.6, margin: '0 0 1.5rem'}}>
          <span dangerouslySetInnerHTML={richHtml(copy.body)} />
        </p>
        {copy.invite && data.canModerate && data.links.manageInvites && (
          <div style={{background: '#f0f4ff', border: '1px solid #c7d3f5', borderRadius: 8, padding: '1rem 1.25rem', fontSize: 14, color: 'var(--ink)', lineHeight: 1.6, marginBottom: '1.5rem'}}>
            <strong>{msg('forbidden-invite-mod-lead')}</strong>
            {` ${msg('forbidden-invite-mod-body')} `}
            <InternalLink href={data.links.manageInvites} style={{color: 'var(--accent)'}}>{msg('forbidden-invite-mod-link')}</InternalLink>
          </div>
        )}
        <InternalLink href={data.links.home} style={{fontSize: 13, color: 'var(--muted)', textDecoration: 'none'}}>{msg('forbidden-invite-back-home')}</InternalLink>
      </div>
    </LegacyShell>
  );
}

function JoinPage({data, csrfToken, voucher}: {data: JoinEntry; csrfToken: string; voucher: boolean}) {
  const msg = useMessage();
  const [pseudonyms, setPseudonyms] = useState(data.pseudonyms);
  const [pseudonym, setPseudonym] = useState(data.pseudonyms[0] ?? '');
  const [notifyEmail, setNotifyEmail] = useState(false);
  const [notifyTalkPage, setNotifyTalkPage] = useState(false);
  const [consent, setConsent] = useState(false);
  const [status, setStatus] = useState('');
  const reroll = useMutation({
    mutationFn: () => getPseudonymSuggestions(data.conversation.slug),
    onMutate: () => setStatus(msg('accept-js-generating')),
    onSuccess: (result) => {
      setPseudonyms(result.pseudonyms);
      setPseudonym(result.pseudonyms[0] ?? '');
      setStatus(result.pseudonyms.length
        ? msg('accept-js-regenerated', result.pseudonyms[0] ?? '')
        : msg('accept-js-error'));
    },
    onError: () => setStatus(msg('accept-js-error')),
  });
  const join = useMutation({
    mutationFn: () => createParticipation(data.conversation.slug, {
      pseudonym,
      notifyEmail,
      notifyTalkPage,
    }, csrfToken),
    onError: (error) => {
      if (error instanceof ApiContractError && error.code === 'pseudonym_unavailable') {
        setNotifyEmail(false);
        setNotifyTalkPage(false);
        setConsent(false);
        reroll.mutate();
      }
    },
  });

  if (join.data) return <NavigationRedirect href={join.data.links.conversation} />;
  if (join.error instanceof ApiContractError
      && ['eligibility_denied', 'eligibility_unavailable'].includes(join.error.code)) {
    return <EligibilityDeniedPage data={data} error={join.error} />;
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    join.mutate();
  }

  const formError = join.error ? joinErrorCopy(msg, join.error) : null;

  return (
    <LegacyShell headerCrumb={(
      <span className="header-crumb">
        <span className="header-crumb-sep">/</span>
        <span>{msg('accept-crumb')}</span>
      </span>
    )}>
      <div className="container" style={{maxWidth: 700}}>
        <div className="accept-crumb">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeDasharray="1.4 1.6" aria-hidden="true">
            <circle cx="12" cy="12" r="9" />
            <ellipse cx="12" cy="12" rx="9" ry="3.5" />
            <ellipse cx="12" cy="12" rx="3.5" ry="9" />
          </svg>
          {msg('accept-joining')}
        </div>

        <h1 id="accept-title" style={{fontSize: 30, fontWeight: 600, color: 'var(--ink)', letterSpacing: '-0.02em', lineHeight: 1.2, margin: 0}}>
          {data.conversation.title}
        </h1>
        {data.conversation.descriptionHtml && (
          <div style={{fontSize: 15, lineHeight: 1.6, color: 'var(--body)', marginTop: 14}} dangerouslySetInnerHTML={{__html: data.conversation.descriptionHtml}} />
        )}
        <p style={{fontSize: 14, color: 'var(--muted)', marginTop: 18, marginBottom: 0}}>
          {msg('accept-pick-name')}
        </p>

        <form id="accept-form" aria-labelledby="accept-title" aria-describedby={`pseudonym-help accept-privacy-note accept-licence-note${formError ? ' accept-error' : ''}`} onSubmit={submit}>
          <input type="hidden" name="csrf_token" value={csrfToken} />
          <div className="pseudonym-card" role="radiogroup" aria-labelledby="pseudonym-title" aria-describedby="pseudonym-help pseudonym-status">
            <div className="pseudonym-card-header">
              <div className="pseudonym-card-title" id="pseudonym-title">{msg('accept-choose-pseudonym')}</div>
              <button type="button" className="reroll-btn" aria-controls="pseudonym-options" aria-label={msg('accept-reroll-aria')} disabled={reroll.isPending} onClick={() => reroll.mutate()}>
                {reroll.isPending ? msg('accept-reroll-loading') : msg('accept-reroll')}
              </button>
            </div>
            <div className="pseudonym-card-sub" id="pseudonym-help">
              {msg('accept-pseudonym-help')}
            </div>
            <p className="sr-only" id="pseudonym-status" role="status" aria-live="polite">{status}</p>
            <div className="pseudonym-options" id="pseudonym-options" aria-busy={reroll.isPending ? 'true' : 'false'}>
              {pseudonyms.map((name, index) => (
                <label className="pseudonym-label" htmlFor={`pseudonym-${index + 1}`} key={name}>
                  <input type="radio" id={`pseudonym-${index + 1}`} name="pseudonym" value={name} checked={pseudonym === name} onChange={() => {
                    setPseudonym(name);
                    setStatus(msg('accept-js-selected', name));
                  }} />
                  <span className="pseudonym-name">{name}</span>
                </label>
              ))}
            </div>
          </div>

          {/* A voucher account has no Wikimedia email or talk page to notify (#368). */}
          {!voucher && <div className="accept-section" role="group" aria-labelledby="notification-title" aria-describedby="notification-help">
            <h2 id="notification-title">{msg('accept-notify-heading')}</h2>
            <p id="notification-help" style={{color: 'var(--muted)', fontSize: 13, marginBottom: '.75rem'}}>
              {msg('accept-notify-help')}
            </p>
            {data.emailable ? (
              <label className="checkbox-label">
                <input type="checkbox" name="notify_email" value="1" checked={notifyEmail} onChange={(event) => setNotifyEmail(event.target.checked)} />
                <span>{msg('accept-notify-email')}</span>
              </label>
            ) : (
              <p className="muted" style={{marginTop: '.25rem'}} dangerouslySetInnerHTML={richHtml(
                  msg('accept-notify-email-unavailable',
                    `<a href="https://meta.wikimedia.org/wiki/Special:Preferences#mw-prefsection-personal" target="_blank" rel="noopener">`
                    + `${escapeHtml(msg('accept-notify-add-email'))}<span class="sr-only">${escapeHtml(msg('common-opens-in-new-tab'))}</span></a>`))} />
            )}
            <label className="checkbox-label" style={{marginTop: '.5rem'}}>
              <input type="checkbox" name="notify_talk_page" value="1" checked={notifyTalkPage} onChange={(event) => setNotifyTalkPage(event.target.checked)} />
              <span>{msg('accept-notify-talk')}</span>
            </label>
          </div>}

          <div className="accept-section" id="accept-privacy-note">
            <h2>{msg('accept-privacy-heading')}</h2>
            <p>{msg('accept-privacy-summary')}</p>
            <details className="privacy-details">
              <summary className="privacy-summary" aria-controls="privacy-details-body">{msg('accept-privacy-details-summary')}</summary>
              <div className="privacy-body" id="privacy-details-body">
                <p>{msg('accept-privacy-body1')}</p>
                <p>{msg('accept-privacy-body2')}</p>
                <p dangerouslySetInnerHTML={richHtml(msg('accept-privacy-reveal-window',
                  data.reveal.cooldownDays, data.reveal.windowEndDays))} />
              </div>
            </details>
          </div>

          <div className="accept-section" id="accept-licence-note">
            <h2>{msg('accept-licence-heading')}</h2>
            <p dangerouslySetInnerHTML={richHtml(msg('accept-licence-intro',
              `<a href="https://creativecommons.org/publicdomain/zero/1.0/" target="_blank" rel="noopener">`
              + `${escapeHtml(msg('accept-licence-link'))}<span class="sr-only">${escapeHtml(msg('common-opens-in-new-tab'))}</span></a>`))} />
            <p className="muted">
              {msg('accept-licence-scope')}
            </p>
          </div>

          <label className="consent-label" id="consent-label" htmlFor="consent-check" style={{marginTop: '1.25rem'}}>
            <input type="checkbox" name="consent" id="consent-check" value="1" required aria-required="true" checked={consent} onChange={(event) => setConsent(event.target.checked)} />
            <span>{msg('accept-consent')}</span>
          </label>
          {formError && <p className="error" id="accept-error" role="alert">{formError}</p>}
          <div style={{display: 'flex', alignItems: 'center', gap: 16, marginTop: 22}}>
            <button type="submit" className="participate-btn" id="submit-btn" disabled={join.isPending}
              dangerouslySetInnerHTML={richHtml(msg('accept-submit', `<span id="chosen-name">${escapeHtml(pseudonym)}</span>`))} />
            <InternalLink href={data.links.home} style={{color: 'var(--muted)', fontSize: 13, textDecoration: 'none'}}>{msg('accept-not-now')}</InternalLink>
          </div>
        </form>
      </div>
    </LegacyShell>
  );
}

function EligibilityDeniedPage({data, error}: {data: JoinEntry; error: ApiContractError}) {
  const msg = useMessage();
  // The error's `details.displayMessage` is Proto's own English diagnostic about the checker,
  // not a reason written for the participant, so the reason comes from the code alone.
  const message = error.code === 'eligibility_unavailable'
    ? msg('forbidden-elig-unavailable')
    : msg('forbidden-elig-criteria');
  // This page replaces the form the participant just submitted, so focus would otherwise fall
  // to the document body and a screen reader would announce nothing.
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => heading.current?.focus(), []);
  return (
    <LegacyShell title={msg('forbidden-elig-doc-title', data.conversation.title)}>
      <div className="container">
        <div className="landing-section">
          <h1 ref={heading} tabIndex={-1}>{msg('forbidden-elig-heading')}</h1>
          <p className="muted">
            {data.conversation.eligibilityLabel
              ? <span dangerouslySetInnerHTML={richHtml(msg('forbidden-elig-requirement-named',
                  `<strong>${escapeHtml(data.conversation.eligibilityLabel)}</strong>`))} />
              : msg('forbidden-elig-requirement')}
          </p>
          <p className="muted">{message}</p>
          <p style={{marginTop: '1rem'}}><InternalLink href={data.links.home}>{msg('common-return-home')} <span aria-hidden="true">→</span></InternalLink></p>
        </div>
      </div>
    </LegacyShell>
  );
}

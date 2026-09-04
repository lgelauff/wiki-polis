import {useState, type FormEvent} from 'react';
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

function requiredSlug(value: string | undefined) {
  if (!value) throw new Error('Missing route parameter: slug');
  return value;
}

export function ParticipationEntryLegacyPage() {
  const slug = requiredSlug(useParams().slug);
  const {data: session} = useSuspenseQuery(sessionQuery());
  if (session.state !== 'authenticated') {
    return <NavigationRedirect href={session.links.login} />;
  }
  return <AuthenticatedParticipationEntry slug={slug} csrfToken={session.csrfToken} />;
}

function AuthenticatedParticipationEntry({slug, csrfToken}: {
  slug: string;
  csrfToken: string;
}) {
  const {data} = useSuspenseQuery(participationEntryQuery(slug));
  if (data.state === 'redirect') return <NavigationRedirect href={data.href} />;
  if (data.state === 'invite_denied') return <InviteDeniedPage data={data} />;
  return <JoinPage data={data} csrfToken={csrfToken} />;
}

type ParticipationEntry = components['schemas']['ParticipationEntryResponse']['data'];
type InviteDeniedEntry = Extract<ParticipationEntry, {state: 'invite_denied'}>;
type JoinEntry = Extract<ParticipationEntry, {state: 'join'}>;

function InviteDeniedPage({data}: {data: InviteDeniedEntry}) {
  return (
    <LegacyShell title="Access restricted — ProtoWiki">
      <div className="container" style={{maxWidth: 700, paddingTop: '3rem'}}>
        <h1 style={{fontSize: 24, fontWeight: 600, color: 'var(--ink)', margin: '0 0 .75rem'}}>
          This consultation is invite-only
        </h1>
        <p style={{color: 'var(--body)', fontSize: 15, lineHeight: 1.6, margin: '0 0 1.5rem'}}>
          <strong>{data.conversation.title}</strong>
          {' is restricted to invited participants. You have not been added to the invite list for this consultation.'}
        </p>
        {data.canModerate && data.links.manageInvites && (
          <div style={{background: '#f0f4ff', border: '1px solid #c7d3f5', borderRadius: 8, padding: '1rem 1.25rem', fontSize: 14, color: 'var(--ink)', lineHeight: 1.6, marginBottom: '1.5rem'}}>
            <strong>You can moderate this consultation.</strong>
            {' To participate as a voter, add yourself to the invite list first: '}
            <InternalLink href={data.links.manageInvites} style={{color: 'var(--accent)'}}>Manage invites →</InternalLink>
          </div>
        )}
        <InternalLink href={data.links.home} style={{fontSize: 13, color: 'var(--muted)', textDecoration: 'none'}}>← back to home</InternalLink>
      </div>
    </LegacyShell>
  );
}

function JoinPage({data, csrfToken}: {data: JoinEntry; csrfToken: string}) {
  const [pseudonyms, setPseudonyms] = useState(data.pseudonyms);
  const [pseudonym, setPseudonym] = useState(data.pseudonyms[0] ?? '');
  const [notifyEmail, setNotifyEmail] = useState(false);
  const [notifyTalkPage, setNotifyTalkPage] = useState(false);
  const [consent, setConsent] = useState(false);
  const [status, setStatus] = useState('');
  const reroll = useMutation({
    mutationFn: () => getPseudonymSuggestions(data.conversation.slug),
    onMutate: () => setStatus('Generating new pseudonym options.'),
    onSuccess: (result) => {
      setPseudonyms(result.pseudonyms);
      setPseudonym(result.pseudonyms[0] ?? '');
      setStatus(result.pseudonyms.length
        ? `New pseudonym options generated. Selected ${result.pseudonyms[0]}.`
        : 'Could not generate new pseudonym options. Try again.');
    },
    onError: () => setStatus('Could not generate new pseudonym options. Try again.'),
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

  const formError = join.error instanceof ApiContractError
    ? (join.error.code === 'pseudonym_unavailable'
      ? 'That pseudonym was just taken — please choose another.'
      : join.error.message)
    : null;

  return (
    <LegacyShell headerCrumb={(
      <span className="header-crumb">
        <span className="header-crumb-sep">/</span>
        <span>join</span>
      </span>
    )}>
      <div className="container" style={{maxWidth: 700}}>
        <div className="accept-crumb">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeDasharray="1.4 1.6" aria-hidden="true">
            <circle cx="12" cy="12" r="9" />
            <ellipse cx="12" cy="12" rx="9" ry="3.5" />
            <ellipse cx="12" cy="12" rx="3.5" ry="9" />
          </svg>
          joining consultation
        </div>

        <h1 id="accept-title" style={{fontSize: 30, fontWeight: 600, color: 'var(--ink)', letterSpacing: '-0.02em', lineHeight: 1.2, margin: 0}}>
          {data.conversation.title}
        </h1>
        {data.conversation.descriptionHtml && (
          <div style={{fontSize: 15, lineHeight: 1.6, color: 'var(--body)', marginTop: 14}} dangerouslySetInnerHTML={{__html: data.conversation.descriptionHtml}} />
        )}
        <p style={{fontSize: 14, color: 'var(--muted)', marginTop: 18, marginBottom: 0}}>
          Pick the name you will use in this consultation.
        </p>

        <form id="accept-form" aria-labelledby="accept-title" aria-describedby={`pseudonym-help accept-privacy-note${formError ? ' accept-error' : ''}`} onSubmit={submit}>
          <input type="hidden" name="csrf_token" value={csrfToken} />
          <div className="pseudonym-card" role="radiogroup" aria-labelledby="pseudonym-title" aria-describedby="pseudonym-help pseudonym-status">
            <div className="pseudonym-card-header">
              <div className="pseudonym-card-title" id="pseudonym-title">Choose a pseudonym</div>
              <button type="button" className="reroll-btn" aria-controls="pseudonym-options" aria-label="Generate new pseudonym options" disabled={reroll.isPending} onClick={() => reroll.mutate()}>
                {reroll.isPending ? '↻ loading…' : '↻ reroll'}
              </button>
            </div>
            <div className="pseudonym-card-sub" id="pseudonym-help">
              Other participants see this name next to your votes and arguments. Your Wikimedia username stays internal unless you reveal it after the consultation closes.
            </div>
            <p className="sr-only" id="pseudonym-status" role="status" aria-live="polite">{status}</p>
            <div className="pseudonym-options" id="pseudonym-options" aria-busy={reroll.isPending ? 'true' : 'false'}>
              {pseudonyms.map((name, index) => (
                <label className="pseudonym-label" htmlFor={`pseudonym-${index + 1}`} key={name}>
                  <input type="radio" id={`pseudonym-${index + 1}`} name="pseudonym" value={name} checked={pseudonym === name} onChange={() => {
                    setPseudonym(name);
                    setStatus(`Selected pseudonym ${name}.`);
                  }} />
                  <span className="pseudonym-name">{name}</span>
                </label>
              ))}
            </div>
          </div>

          <div className="accept-section" role="group" aria-labelledby="notification-title" aria-describedby="notification-help">
            <h2 id="notification-title">Stay informed</h2>
            <p id="notification-help" style={{color: 'var(--muted)', fontSize: 13, marginBottom: '.75rem'}}>
              Optional best-effort updates when the consultation closes or results are published.
            </p>
            {data.emailable ? (
              <label className="checkbox-label">
                <input type="checkbox" name="notify_email" value="1" checked={notifyEmail} onChange={(event) => setNotifyEmail(event.target.checked)} />
                <span>Email me if we send updates (via your confirmed wiki email address)</span>
              </label>
            ) : (
              <p className="muted" style={{marginTop: '.25rem'}}>
                {'Email notifications unavailable — no confirmed email on your wiki account. '}
                <InternalLink href="https://meta.wikimedia.org/wiki/Special:Preferences#mw-prefsection-personal" target="_blank" rel="noopener">Add one on Meta-Wiki<span className="sr-only"> (opens in a new tab)</span></InternalLink> and return to enable this.
              </p>
            )}
            <label className="checkbox-label" style={{marginTop: '.5rem'}}>
              <input type="checkbox" name="notify_talk_page" value="1" checked={notifyTalkPage} onChange={(event) => setNotifyTalkPage(event.target.checked)} />
              <span>Post to my talk page if we send updates</span>
            </label>
          </div>

          <div className="accept-section" id="accept-licence-note">
            <h2>What you write</h2>
            <p>
              {'Statements and arguments you write here are released under '}
              <InternalLink href="https://creativecommons.org/publicdomain/zero/1.0/" target="_blank" rel="noopener">CC0<span className="sr-only"> (opens in a new tab)</span></InternalLink>
              {', which places them in the public domain, the same as a wiki edit. That is what lets the results be published as a report, quoted in a discussion, and reused by anyone.'}
            </p>
            <p className="muted">
              This covers what you write, not who wrote it: contributions are published under your pseudonym, and CC0 does not require anyone to credit you. Your votes are not covered — a vote is a fact, not a work. CC0 cannot be withdrawn once given, the same as any wiki edit.
            </p>
          </div>

          <div className="accept-section" id="accept-privacy-note">
            <h2>Privacy summary</h2>
            <p>Public records use your pseudonym. ProtoWiki keeps the username link internally for login, access checks, notifications, moderation, and privacy controls.</p>
            <details className="privacy-details">
              <summary className="privacy-summary" aria-controls="privacy-details-body">Privacy &amp; data handling</summary>
              <div className="privacy-body" id="privacy-details-body">
                <p>Your pseudonym is used for consultation records and participant-facing displays. Your Wikimedia username is used internally for login, access checks, moderation, and notification preferences.</p>
                <p>Public results may include aggregate votes, clusters, and pseudonyms. They do not show your Wikimedia username unless you explicitly reveal it after the consultation closes.</p>
                <p>Between <strong>{data.reveal.cooldownDays}</strong> and <strong>{`${data.reveal.windowEndDays} days`}</strong> after close, you may optionally and permanently link your username to your pseudonym in the public record. This is irreversible during that window.</p>
              </div>
            </details>
          </div>

          <label className="consent-label" id="consent-label" htmlFor="consent-check" style={{marginTop: '1.25rem'}}>
            <input type="checkbox" name="consent" id="consent-check" value="1" required aria-required="true" checked={consent} onChange={(event) => setConsent(event.target.checked)} />
            <span>I understand my votes and arguments are recorded with this pseudonym, ProtoWiki keeps an internal username link while this consultation runs, and what I write is released under CC0.</span>
          </label>
          {formError && <p className="error" id="accept-error" role="alert">{formError}</p>}
          <div style={{display: 'flex', alignItems: 'center', gap: 16, marginTop: 22}}>
            <button type="submit" className="participate-btn" id="submit-btn" disabled={join.isPending}>
              Join consultation as <span id="chosen-name">{pseudonym}</span> →
            </button>
            <InternalLink href={data.links.home} style={{color: 'var(--muted)', fontSize: 13, textDecoration: 'none'}}>Not now</InternalLink>
          </div>
        </form>
      </div>
    </LegacyShell>
  );
}

function EligibilityDeniedPage({data, error}: {data: JoinEntry; error: ApiContractError}) {
  const details = error.details as {status?: string; displayMessage?: string | null} | undefined;
  const message = details?.displayMessage
    ?? (details?.status === 'unavailable'
      ? 'The eligibility checker is unavailable right now. Try again later.'
      : 'Your account did not meet the configured criteria.');
  return (
    <LegacyShell title={`Not eligible — ${data.conversation.title} — ProtoWiki`}>
      <div className="container">
        <div className="landing-section">
          <h1>Not eligible for this consultation</h1>
          <p className="muted">
            {data.conversation.eligibilityLabel
              ? 'This consultation has an eligibility requirement: '
              : 'This consultation has an eligibility requirement.'}
            {data.conversation.eligibilityLabel && <><strong>{data.conversation.eligibilityLabel}</strong>.</>}
          </p>
          <p className="muted">{message}</p>
          <p style={{marginTop: '1rem'}}><InternalLink href={data.links.home}>Return home <span aria-hidden="true">→</span></InternalLink></p>
        </div>
      </div>
    </LegacyShell>
  );
}

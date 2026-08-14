import {useEffect, useState, type FormEvent} from 'react';
import {useMutation, useSuspenseQuery} from '@tanstack/react-query';
import {useParams} from 'react-router-dom';

import type {components} from '../../api/schema';
import {createIdentityReveal, identityRevealQuery, sessionQuery} from '../../api/queries';
import {NavigationRedirect} from './external-redirect';
import {LegacyShell} from './legacy-shell';
import {InternalLink} from '../../internal-link';

type RevealData = components['schemas']['IdentityReveal'];

function requiredSlug(value: string | undefined) {
  if (!value) throw new Error('Missing route parameter: slug');
  return value;
}

function shortDate(value: string) {
  const date = new Date(value);
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  return `${date.getUTCDate()} ${months[date.getUTCMonth()]} ${date.getUTCFullYear()}`;
}

function daysBetween(start: string, end: string) {
  return Math.round((new Date(end).getTime() - new Date(start).getTime()) / 86_400_000);
}

function countdown(target: string) {
  const remaining = new Date(target).getTime() - Date.now();
  if (remaining <= 0) return 'now';
  const seconds = Math.floor(remaining / 1000);
  const pad = (value: number) => String(value).padStart(2, '0');
  return `${Math.floor(seconds / 86400)}d ${pad(Math.floor(seconds % 86400 / 3600))}:${pad(Math.floor(seconds % 3600 / 60))}:${pad(seconds % 60)}`;
}

function RevealCountdown({target}: {target: string}) {
  const [value, setValue] = useState(() => countdown(target));
  useEffect(() => {
    const timer = globalThis.setInterval(() => setValue(countdown(target)), 1000);
    return () => globalThis.clearInterval(timer);
  }, [target]);
  return <>{value}</>;
}

function RevealTimeline({data}: {data: RevealData}) {
  const state = data.state;
  const cooldownDays = daysBetween(data.timeline.closedAt, data.timeline.opensAt);
  const windowDays = daysBetween(data.timeline.opensAt, data.timeline.closesAt);
  return (
    <div className="reveal-timeline">
      <ol className="reveal-track" aria-label="Identity reveal timeline">
        <li className={`reveal-node reveal-node--done${state === 'pending' ? ' reveal-node--now' : ''}`} aria-current={state === 'pending' ? 'step' : undefined}>
          <span className="reveal-pip" aria-hidden="true" />
          <div className="reveal-when">{shortDate(data.timeline.closedAt)}</div>
          <div className="reveal-what">{`Closed — linking stays sealed for ${cooldownDays} days `}
            <span className="sr-only">{state === 'pending' ? '(in progress — cooldown)' : '(completed)'}</span>
          </div>
        </li>
        <li className={`reveal-node${['open', 'revealed'].includes(state) ? ' reveal-node--now' : state === 'expired' ? ' reveal-node--done' : ''}`} aria-current={['open', 'revealed'].includes(state) ? 'step' : undefined}>
          <span className="reveal-pip" aria-hidden="true" />
          <div className="reveal-when">{shortDate(data.timeline.opensAt)}</div>
          <div className="reveal-what">{`Window opens — ${windowDays} days to optionally link your Wikimedia username `}
            <span className="sr-only">{['open', 'revealed'].includes(state) ? '(current)' : state === 'expired' ? '(completed)' : '(upcoming)'}</span>
          </div>
        </li>
        <li className={`reveal-node${state === 'expired' ? ' reveal-node--now' : ''}`} aria-current={state === 'expired' ? 'step' : undefined}>
          <span className="reveal-pip" aria-hidden="true" />
          <div className="reveal-when">{shortDate(data.timeline.closesAt)}</div>
          <div className="reveal-what">Window closes — records stay pseudonymous permanently <span className="sr-only">{state === 'expired' ? '(current)' : '(upcoming)'}</span></div>
        </li>
      </ol>
      {data.timeline.nextBoundaryAt && (
        <p className="reveal-deadline">
          {state === 'pending' ? 'Reveal window opens in ' : <><strong>Window closes in</strong>{' '}</>}
          <strong className="reveal-countdown" data-reveal-countdown={data.timeline.nextBoundaryAt}><RevealCountdown target={data.timeline.nextBoundaryAt} /></strong>
          {state === 'open' ? <> — linking is <strong>permanent and cannot be undone</strong>.</> : '.'}
        </p>
      )}
    </div>
  );
}

export function IdentityRevealLegacyPage() {
  const slug = requiredSlug(useParams().slug);
  const {data: session} = useSuspenseQuery(sessionQuery());
  if (session.state !== 'authenticated') return <NavigationRedirect href={session.links.login} />;
  return <AuthenticatedIdentityReveal slug={slug} csrfToken={session.csrfToken} />;
}

function AuthenticatedIdentityReveal({slug, csrfToken}: {slug: string; csrfToken: string}) {
  const {data} = useSuspenseQuery(identityRevealQuery(slug));
  const [confirmed, setConfirmed] = useState(false);
  const mutation = useMutation({mutationFn: () => createIdentityReveal(slug, csrfToken)});

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (confirmed) mutation.mutate();
  }

  if (mutation.data) return <NavigationRedirect href={mutation.data.links.conversation} />;

  return (
    <LegacyShell headerCrumb={(
      <span className="header-crumb">
        <span className="header-crumb-sep">/</span>
        <span>{data.title.length > 40 ? `${data.title.slice(0, 39)}…` : data.title}</span>
        <span className="header-crumb-sep">/</span>
        <span>reveal</span>
      </span>
    )}>
      <div className="container" style={{maxWidth: 660}}>
        <p style={{marginBottom: '1.25rem'}}>
          <InternalLink href={data.links.conversation} style={{fontSize: 13, color: 'var(--muted)', textDecoration: 'none'}}>{`← ${data.title}`}</InternalLink>
        </p>

        {data.state === 'revealed' ? (
          <>
            <div className="reveal-banner">Identity reveal</div>
            <h1 style={{fontSize: 26, fontWeight: 600, color: 'var(--ink)', letterSpacing: '-0.02em', lineHeight: 1.2, margin: 0}}>Identity linked</h1>
            <IdentityCard pseudonym={data.pseudonym} username={data.publicUsername ?? data.wikimediaUsername} marginTop={18} />
            <p className="muted" style={{marginTop: 14}}>This public link is permanent and is not removed by the platform.</p>
          </>
        ) : data.state === 'expired' ? (
          <>
            <div className="reveal-banner">Identity reveal</div>
            <h1 style={{fontSize: 26, fontWeight: 600, color: 'var(--ink)', letterSpacing: '-0.02em', margin: 0}}>Reveal window closed</h1>
            <p style={{fontSize: 15, lineHeight: 1.6, color: 'var(--body)', marginTop: 14}}>The identity reveal window for this consultation has closed. Participation data is now pseudonymous only.</p>
          </>
        ) : data.state === 'pending' ? (
          <>
            <div className="reveal-banner">Identity reveal</div>
            <h1 style={{fontSize: 26, fontWeight: 600, color: 'var(--ink)', letterSpacing: '-0.02em', margin: 0}}>Reveal window not yet open</h1>
            <p style={{fontSize: 15, lineHeight: 1.6, color: 'var(--body)', marginTop: 14}}>{'The identity reveal window has not opened yet. It will open on '}<strong>{shortDate(data.timeline.opensAt)}</strong>.</p>
            <p className="muted" style={{marginTop: 8}}>After that date you may optionally and <strong>permanently</strong> link your Wikimedia username to your pseudonym in this consultation's public record. You're never required to.</p>
            <RevealTimeline data={data} />
          </>
        ) : (
          <>
            <div className="reveal-banner">
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeDasharray="1.4 1.6" aria-hidden="true">
                <circle cx="12" cy="12" r="9" />
                <ellipse cx="12" cy="12" rx="9" ry="3.5" />
                <ellipse cx="12" cy="12" rx="3.5" ry="9" />
              </svg>
              identity reveal window
            </div>
            <h1 style={{fontSize: 28, fontWeight: 600, color: 'var(--ink)', letterSpacing: '-0.02em', lineHeight: 1.2, margin: 0}}>
              {'Permanently link '}<span style={{fontFamily: 'var(--mono)', color: 'var(--spot)', fontWeight: 500}}>{data.pseudonym}</span>{' to your wiki name?'}
            </h1>
            <p style={{fontSize: 15, lineHeight: 1.6, color: 'var(--body)', marginTop: 14}}>
              {'You may optionally publish that '}<span style={{fontFamily: 'var(--mono)', color: 'var(--ink)'}}>{data.wikimediaUsername}</span>{' voted as '}<span style={{fontFamily: 'var(--mono)', color: 'var(--ink)'}}>{data.pseudonym}</span>{' in this conversation. Other pseudonyms you used elsewhere are unaffected.'}
            </p>
            <RevealTimeline data={data} />
            <div className="close-warning" style={{margin: '1.25rem 0'}}>
              <p style={{fontWeight: 600, marginBottom: '.5rem', color: '#9a3412'}}>Irreversible</p>
              <ul style={{fontSize: 13, margin: '.25rem 0 0 1.25rem', lineHeight: 1.7, color: '#7c2d12'}}>
                <li>{'Your Wikimedia username ('}<strong>{data.wikimediaUsername}</strong>{') will be permanently associated with your pseudonym '}<strong>{data.pseudonym}</strong>{' in exported records for this consultation.'}</li>
                <li>You cannot undo this or re-anonymise your participation.</li>
                <li>Separate internal identity links may be retained for moderation and process review according to the platform retention policy.</li>
              </ul>
            </div>
            <IdentityCard pseudonym={data.pseudonym} username={data.wikimediaUsername} />
            <form method="post" action={`/c/${data.slug}/reveal`} style={{marginTop: 22}} onSubmit={submit}>
              <input type="hidden" name="csrf_token" value={csrfToken} />
              <label className="checkbox-label" style={{marginBottom: 16}}>
                <input type="checkbox" name="confirm" value="1" required checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />
                <span>{'I understand this is irreversible. Link my Wikimedia username ('}<strong>{data.wikimediaUsername}</strong>{') to my pseudonym ('}<strong>{data.pseudonym}</strong>).</span>
              </label>
              <div style={{display: 'flex', alignItems: 'center', gap: 16}}>
                <button type="submit" className="participate-btn" style={{background: 'var(--ink)'}} disabled={mutation.isPending}>Yes, link my identity</button>
                <InternalLink href={data.links.conversation} style={{color: 'var(--muted)', fontSize: 13, textDecoration: 'none'}}>Cancel</InternalLink>
              </div>
            </form>
          </>
        )}
      </div>
    </LegacyShell>
  );
}

function IdentityCard({pseudonym, username, marginTop}: {pseudonym: string; username: string; marginTop?: number}) {
  return (
    <div className="reveal-identity-card" style={marginTop === undefined ? undefined : {marginTop}}>
      <div className="reveal-identity-row">
        <div className="reveal-identity-col"><div className="reveal-identity-label">pseudonym</div><div className="reveal-identity-value">{pseudonym}</div></div>
        <div className="reveal-identity-sep" aria-hidden="true">↔</div>
        <div className="reveal-identity-col"><div className="reveal-identity-label">wikimedia username</div><div className="reveal-identity-value">{username}</div></div>
      </div>
    </div>
  );
}

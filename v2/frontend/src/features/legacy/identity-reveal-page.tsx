import {useState, type FormEvent} from 'react';
import {useMutation, useQueryClient, useSuspenseQuery} from '@tanstack/react-query';
import {useParams} from 'react-router-dom';

import {ApiContractError} from '../../api/client';
import {createIdentityReveal, identityRevealQuery, sessionQuery} from '../../api/queries';
import {NavigationRedirect} from './external-redirect';
import {LegacyShell} from './legacy-shell';
import {InternalLink} from '../../internal-link';
import {useDateFormat} from '../../i18n/dates';
import {useMessage} from '../../i18n/messages';
import {nodeSlot, withNodes} from '../../i18n/message-nodes';
import {richHtml} from '../../i18n/rich-html';
import {RevealTimeline} from './reveal-timeline';
import {useLoginHref} from '../../login-href';

function requiredSlug(value: string | undefined) {
  if (!value) throw new Error('Missing route parameter: slug');
  return value;
}

function daysBetween(start: string, end: string) {
  return Math.round((new Date(end).getTime() - new Date(start).getTime()) / 86_400_000);
}

export function IdentityRevealLegacyPage() {
  const slug = requiredSlug(useParams().slug);
  const {data: session} = useSuspenseQuery(sessionQuery());
  const login = useLoginHref(session.links.login);
  if (session.state !== 'authenticated') return <NavigationRedirect href={login} />;
  return <AuthenticatedIdentityReveal slug={slug} csrfToken={session.csrfToken} />;
}

function AuthenticatedIdentityReveal({slug, csrfToken}: {slug: string; csrfToken: string}) {
  const msg = useMessage();
  const dates = useDateFormat();
  const queryClient = useQueryClient();
  const {data} = useSuspenseQuery(identityRevealQuery(slug));
  const [confirmed, setConfirmed] = useState(false);
  const refresh = () => void queryClient.invalidateQueries({queryKey: identityRevealQuery(slug).queryKey});
  // A failed request may still have linked the identity: the server commits before it
  // responds. Refetching shows whichever state is true; linking again is a no-op.
  const mutation = useMutation({mutationFn: () => createIdentityReveal(slug, csrfToken), onError: refresh});
  // Only the server's refusal is known not to have linked anything. After any other failure
  // (a network error, a 5xx) the page must not claim the identity is unlinked.
  const refused = mutation.error instanceof ApiContractError && mutation.error.code === 'identity_reveal_unavailable';

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (confirmed) mutation.mutate();
  }

  if (mutation.data) return <NavigationRedirect href={mutation.data.links.conversation} />;

  const timeline = <RevealTimeline state={data.state} closedAt={data.timeline.closedAt} opensAt={data.timeline.opensAt} closesAt={data.timeline.closesAt}
    cooldownDays={daysBetween(data.timeline.closedAt, data.timeline.opensAt)} windowDays={daysBetween(data.timeline.opensAt, data.timeline.closesAt)}
    countdownTargetAt={data.timeline.nextBoundaryAt} onBoundary={refresh} />;
  // Participant data inside sentences, styled as on the card below.
  const pseudonym = <span style={{fontFamily: 'var(--mono)', color: 'var(--ink)'}}>{data.pseudonym}</span>;
  const username = <span style={{fontFamily: 'var(--mono)', color: 'var(--ink)'}}>{data.wikimediaUsername}</span>;

  return (
    <LegacyShell headerCrumb={(
      <span className="header-crumb">
        <span className="header-crumb-sep">/</span>
        <span>{data.title.length > 40 ? `${data.title.slice(0, 39)}…` : data.title}</span>
        <span className="header-crumb-sep">/</span>
        <span>{msg('reveal-crumb')}</span>
      </span>
    )}>
      <div className="container" style={{maxWidth: 660}}>
        <p style={{marginBottom: '1.25rem'}}>
          <InternalLink href={data.links.conversation} style={{fontSize: 13, color: 'var(--muted)', textDecoration: 'none'}}><><span className="dir-glyph" aria-hidden="true">←</span> {data.title}</></InternalLink>
        </p>

        {data.state === 'revealed' ? (
          <>
            <div className="reveal-banner">{msg('reveal-banner-identity')}</div>
            <h1 style={{fontSize: 26, fontWeight: 600, color: 'var(--ink)', letterSpacing: '-0.02em', lineHeight: 1.2, margin: 0}}>{msg('reveal-linked-heading')}</h1>
            <IdentityCard pseudonym={data.pseudonym} username={data.publicUsername ?? data.wikimediaUsername} marginTop={18} />
            <p className="muted" style={{marginTop: 14}}>{msg('reveal-permanent-note')}</p>
          </>
        ) : data.state === 'expired' ? (
          <>
            <div className="reveal-banner">{msg('reveal-banner-identity')}</div>
            <h1 style={{fontSize: 26, fontWeight: 600, color: 'var(--ink)', letterSpacing: '-0.02em', margin: 0}}>{msg('reveal-closed-heading')}</h1>
            <p style={{fontSize: 15, lineHeight: 1.6, color: 'var(--body)', marginTop: 14}}>{msg('reveal-closed-body')}</p>
          </>
        ) : data.state === 'pending' ? (
          <>
            <div className="reveal-banner">{msg('reveal-banner-identity')}</div>
            <h1 style={{fontSize: 26, fontWeight: 600, color: 'var(--ink)', letterSpacing: '-0.02em', margin: 0}}>{msg('reveal-notyet-heading')}</h1>
            <p style={{fontSize: 15, lineHeight: 1.6, color: 'var(--body)', marginTop: 14}}>{withNodes(msg('reveal-notyet-body', nodeSlot(0)), <strong>{dates.date(data.timeline.opensAt)}</strong>)}</p>
            <p className="muted" style={{marginTop: 8}} dangerouslySetInnerHTML={richHtml(msg('reveal-notyet-after'))} />
            {timeline}
          </>
        ) : (
          <>
            <div className="reveal-banner">
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeDasharray="1.4 1.6" aria-hidden="true">
                <circle cx="12" cy="12" r="9" />
                <ellipse cx="12" cy="12" rx="9" ry="3.5" />
                <ellipse cx="12" cy="12" rx="3.5" ry="9" />
              </svg>
              {msg('reveal-banner-window')}
            </div>
            <h1 style={{fontSize: 28, fontWeight: 600, color: 'var(--ink)', letterSpacing: '-0.02em', lineHeight: 1.2, margin: 0}}>
              {withNodes(msg('reveal-open-heading', nodeSlot(0)), <span style={{fontFamily: 'var(--mono)', color: 'var(--spot)', fontWeight: 500}}>{data.pseudonym}</span>)}
            </h1>
            <p style={{fontSize: 15, lineHeight: 1.6, color: 'var(--body)', marginTop: 14}}>
              {withNodes(msg('reveal-open-body', nodeSlot(0), nodeSlot(1)), username, pseudonym)}
            </p>
            {timeline}
            <div className="close-warning" style={{margin: '1.25rem 0'}}>
              <p style={{fontWeight: 600, marginBottom: '.5rem', color: '#9a3412'}}>{msg('reveal-irreversible-label')}</p>
              <ul style={{fontSize: 13, margin: '.25rem 0 0 1.25rem', lineHeight: 1.7, color: '#7c2d12'}}>
                <li>{withNodes(msg('reveal-irreversible-li1', nodeSlot(0), nodeSlot(1)), <strong>{data.wikimediaUsername}</strong>, <strong>{data.pseudonym}</strong>)}</li>
                <li>{msg('reveal-irreversible-li2')}</li>
                <li>{msg('reveal-irreversible-li3')}</li>
              </ul>
            </div>
            <IdentityCard pseudonym={data.pseudonym} username={data.wikimediaUsername} />
            <form style={{marginTop: 22}} onSubmit={submit}>
              <input type="hidden" name="csrf_token" value={csrfToken} />
              <label className="checkbox-label" style={{marginBottom: 16}}>
                <input type="checkbox" name="confirm" value="1" required checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />
                <span>{withNodes(msg('reveal-consent', nodeSlot(0), nodeSlot(1)), <strong>{data.wikimediaUsername}</strong>, <strong>{data.pseudonym}</strong>)}</span>
              </label>
              {mutation.error && <p className="error" role="alert">{refused ? msg('reveal-submit-unavailable') : msg('reveal-submit-unknown')}</p>}
              <div style={{display: 'flex', alignItems: 'center', gap: 16}}>
                <button type="submit" className="participate-btn" style={{background: 'var(--ink)'}} disabled={mutation.isPending}>{msg('reveal-submit')}</button>
                <InternalLink href={data.links.conversation} style={{color: 'var(--muted)', fontSize: 13, textDecoration: 'none'}}>{msg('common-cancel')}</InternalLink>
              </div>
            </form>
          </>
        )}
      </div>
    </LegacyShell>
  );
}

function IdentityCard({pseudonym, username, marginTop}: {pseudonym: string; username: string; marginTop?: number}) {
  const msg = useMessage();
  return (
    <div className="reveal-identity-card" style={marginTop === undefined ? undefined : {marginTop}}>
      <div className="reveal-identity-row">
        <div className="reveal-identity-col"><div className="reveal-identity-label">{msg('reveal-label-pseudonym')}</div><div className="reveal-identity-value">{pseudonym}</div></div>
        <div className="reveal-identity-sep" aria-hidden="true">↔</div>
        <div className="reveal-identity-col"><div className="reveal-identity-label">{msg('reveal-label-username')}</div><div className="reveal-identity-value">{username}</div></div>
      </div>
    </div>
  );
}

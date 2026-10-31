import {useEffect, useRef} from 'react';
import {useQuery, useSuspenseQuery} from '@tanstack/react-query';
import {useParams} from 'react-router-dom';

import {ApiContractError} from '../../api/client';
import {conversationAboutQuery, sessionQuery} from '../../api/queries';
import {InternalLink} from '../../internal-link';
import {useMessage} from '../../i18n/messages';
import {useLoginHref} from '../../login-href';
import {LegacyShell} from './legacy-shell';

/** The dotted globe on the "Log in with your Wikimedia account" button. Decorative. */
export function LoginGlobe() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeDasharray="1.4 1.6" aria-hidden="true">
      <circle cx="12" cy="12" r="9" />
      <ellipse cx="12" cy="12" rx="9" ry="3.5" />
      <ellipse cx="12" cy="12" rx="3.5" ry="9" />
    </svg>
  );
}

/** Plain text of the first paragraph of an introduction (sanitised HTML from the server),
 *  cut at a word near `limit` characters. Rendered as text, never as HTML. */
export function introExcerpt(html: string | null | undefined, limit = 300): string {
  if (!html) return '';
  const doc = new DOMParser().parseFromString(html, 'text/html');
  const first = doc.querySelector('p') ?? doc.body;
  const text = (first.textContent ?? '').replace(/\s+/g, ' ').trim();
  if (text.length <= limit) return text;
  const cut = text.slice(0, limit);
  const atWord = cut.lastIndexOf(' ') > 0 ? cut.slice(0, cut.lastIndexOf(' ')) : cut;
  return `${atWord.replace(/[\s,.;:]+$/, '')}…`;
}

/** Focus a page's heading when it replaces the page the visitor asked for, so a screen
 *  reader announces it (as the eligibility refusal does). */
export function useFocusOnArrival<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  useEffect(() => ref.current?.focus(), []);
  return ref;
}

function voucherGated(error: unknown): boolean {
  if (!(error instanceof ApiContractError) || error.code !== 'access_required') return false;
  const details = error.details as {gatingType?: unknown} | undefined;
  return details?.gatingType === 'voucher';
}

/** Shown in place of a page that needs a login (#510). A visitor is never sent to the
 *  Wikimedia login without a click: they read what is needed, and the button carries `?next=`
 *  so the login returns them to this page (#441).
 *
 *  On a consultation's page it also says which consultation this is, from the public About
 *  endpoint. Only what that endpoint serves is shown: a consultation it refuses (gated,
 *  invite-only, missing) gets the generic prompt, so a closed consultation's name never
 *  appears. A voucher-only consultation is the exception in kind, not in content: a
 *  Wikimedia login cannot open it, so the prompt points to the page where a code is typed. */
export function LoginPrompt() {
  const msg = useMessage();
  const {slug} = useParams();
  const about = useQuery({...conversationAboutQuery(slug ?? ''), enabled: Boolean(slug)});
  if (about.isLoading) {
    return <LegacyShell title={msg('login-prompt-doc-title')}><p className="loading-state" role="status">{msg('common-loading')}</p></LegacyShell>;
  }
  if (slug && voucherGated(about.error)) return <VoucherCodePrompt slug={slug} />;
  const consultation = about.data && slug
    ? {title: about.data.title, excerpt: introExcerpt(about.data.descriptionHtml), about: `/c/${encodeURIComponent(slug)}/about`}
    : null;
  return <WikimediaLoginPrompt consultation={consultation} />;
}

function WikimediaLoginPrompt({consultation}: {consultation: {title: string; excerpt: string; about: string} | null}) {
  const msg = useMessage();
  const {data: session} = useSuspenseQuery(sessionQuery());
  const login = useLoginHref(session.links.login);
  const heading = useFocusOnArrival<HTMLHeadingElement>();
  return (
    <LegacyShell title={msg('login-prompt-doc-title')}>
      <div className="container" style={{maxWidth: 700, paddingTop: '3rem'}}>
        <h1 ref={heading} tabIndex={-1} style={{fontSize: 24, fontWeight: 600, color: 'var(--ink)', margin: '0 0 .75rem'}}>{msg('login-prompt-heading')}</h1>
        {consultation && (
          <div style={{margin: '0 0 1.25rem', maxWidth: 520}}>
            <p style={{fontSize: 17, fontWeight: 600, color: 'var(--ink)', margin: '0 0 .25rem'}}>{consultation.title}</p>
            {consultation.excerpt && <p style={{color: 'var(--body)', fontSize: 15, lineHeight: 1.6, margin: '0 0 .25rem'}}>{consultation.excerpt}</p>}
            <InternalLink href={consultation.about} style={{fontSize: 14}}>{msg('login-prompt-about')}</InternalLink>
          </div>
        )}
        <p style={{color: 'var(--body)', fontSize: 15, lineHeight: 1.6, margin: 0, maxWidth: 520}}>{msg('login-prompt-body')}</p>
        <p style={{margin: '0 0 1.5rem'}}>
          <InternalLink href={login} className="login-btn" style={{marginTop: 18}}>
            <LoginGlobe />
            {msg('home-login-wikimedia')}
          </InternalLink>
        </p>
        <InternalLink href="/consultations" style={{fontSize: 13, color: 'var(--muted)', textDecoration: 'none'}}>{msg('login-prompt-back')}</InternalLink>
      </div>
    </LegacyShell>
  );
}

/** A voucher-only consultation, for someone not signed in (or whose voucher session has
 *  expired): the way in is the code, not a Wikimedia login. No title: the refusal is all
 *  the SPA knows, and the code page itself names the consultation. */
function VoucherCodePrompt({slug}: {slug: string}) {
  const msg = useMessage();
  const heading = useFocusOnArrival<HTMLHeadingElement>();
  return (
    <LegacyShell title={msg('forbidden-invite-doc-title')}>
      <div className="container" style={{maxWidth: 700, paddingTop: '3rem'}}>
        <h1 ref={heading} tabIndex={-1} style={{fontSize: 24, fontWeight: 600, color: 'var(--ink)', margin: '0 0 .75rem'}}>{msg('forbidden-voucher-heading')}</h1>
        <p style={{color: 'var(--body)', fontSize: 15, lineHeight: 1.6, margin: '0 0 1.5rem', maxWidth: 520}}>{msg('login-prompt-voucher-body')}</p>
        <p style={{margin: '0 0 1.5rem'}}>
          {/* Served by Flask; InternalLink renders a full-page link for it. */}
          <InternalLink className="btn-primary" href={`/c/${encodeURIComponent(slug)}/v`}>{msg('forbidden-voucher-link')}</InternalLink>
        </p>
        <InternalLink href="/consultations" style={{fontSize: 13, color: 'var(--muted)', textDecoration: 'none'}}>{msg('login-prompt-back')}</InternalLink>
      </div>
    </LegacyShell>
  );
}

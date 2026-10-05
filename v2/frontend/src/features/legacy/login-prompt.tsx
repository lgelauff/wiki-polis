import {useSuspenseQuery} from '@tanstack/react-query';

import {sessionQuery} from '../../api/queries';
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

/** Shown in place of a page that needs a login (#510). A visitor is never sent to the
 *  Wikimedia login without a click: they read what is needed, and the button carries `?next=`
 *  so the login returns them to this page (#441). */
export function LoginPrompt() {
  const msg = useMessage();
  const {data: session} = useSuspenseQuery(sessionQuery());
  const login = useLoginHref(session.links.login);
  return (
    <LegacyShell title={msg('login-prompt-doc-title')}>
      <div className="container" style={{maxWidth: 700, paddingTop: '3rem'}}>
        <h1 style={{fontSize: 24, fontWeight: 600, color: 'var(--ink)', margin: '0 0 .75rem'}}>{msg('login-prompt-heading')}</h1>
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

import {useSuspenseQuery} from '@tanstack/react-query';
import {useLocation} from 'react-router-dom';

import {sessionQuery} from '../../api/queries';
import {InternalLink} from '../../internal-link';
import {useMessage} from '../../i18n/messages';
import {returnPath} from '../../login-href';
import {LegacyShell} from './legacy-shell';
import {useFocusOnArrival} from './login-prompt';

/** Shown to a single-consultation (voucher) account in place of a page that needs another
 *  kind of login (#514). Nothing happens without a click: "Log out and continue" posts to
 *  /logout (CSRF token included) with this page as `next`, so the visitor lands back here,
 *  where the usual login prompt asks for a login if one is needed (#510), with the one-time
 *  logout note. "Back" keeps the account and names the consultation it BELONGS to, from the
 *  session, since the visitor may have arrived from anywhere. */
export function LogoutChoice() {
  const msg = useMessage();
  const location = useLocation();
  const {data: session} = useSuspenseQuery(sessionQuery());
  const heading = useFocusOnArrival<HTMLHeadingElement>();
  const own = session.voucherConsultation ?? null;
  const ownHref = own ? `/c/${encodeURIComponent(own.slug)}` : '/consultations';
  return (
    <LegacyShell title={msg('logout-choice-heading')}>
      <div className="container" style={{maxWidth: 700, paddingTop: '3rem'}}>
        <h1 ref={heading} tabIndex={-1} style={{fontSize: 24, fontWeight: 600, color: 'var(--ink)', margin: '0 0 .75rem'}}>{msg('logout-choice-heading')}</h1>
        <p style={{color: 'var(--body)', fontSize: 15, lineHeight: 1.6, margin: 0, maxWidth: 520}}>{msg('logout-choice-body')}</p>
        <form method="post" action={session.links.logout} style={{margin: '18px 0 1.5rem'}}>
          <input type="hidden" name="csrf_token" value={session.csrfToken} />
          <input type="hidden" name="next" value={returnPath(location)} />
          <button type="submit" className="btn-primary">{msg('logout-choice-confirm')}</button>
        </form>
        <InternalLink href={ownHref} style={{fontSize: 13, color: 'var(--muted)', textDecoration: 'none'}}>
          {own ? msg('logout-choice-back', own.title) : msg('login-prompt-back')}
        </InternalLink>
      </div>
    </LegacyShell>
  );
}

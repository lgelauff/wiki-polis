import {useMessage} from '../../i18n/messages';
import {InternalLink} from '../../internal-link';
import {LegacyShell} from './legacy-shell';

/**
 * The app's own page for "you may not open this" (#538): what a page the server refuses
 * with 403 shows, in the site's frame, instead of a bare "Forbidden" document.
 *
 * Its words are the server's branded 403 page's (`error_pages.py`), so the refusal reads
 * the same whether the server or the app says it. It lives with the participant pages on
 * purpose: someone who reaches it has no role in the console, so its copy is offered for
 * translation with theirs (see `tests/test_i18n_audience.py`).
 */
export function AccessDeniedPage() {
  const msg = useMessage();
  return (
    <LegacyShell title={`403 ${msg('errorpage-403-title')} — Proto`}>
      <div className="container" style={{maxWidth: 700, paddingTop: '3rem'}}>
        <h1 style={{fontSize: 24, fontWeight: 600, color: 'var(--ink)', margin: '0 0 .75rem'}}>{msg('errorpage-403-title')}</h1>
        <p style={{color: 'var(--body)', fontSize: 15, lineHeight: 1.6, margin: '0 0 .5rem'}}>{msg('errorpage-403-message')}</p>
        <p style={{color: 'var(--body)', fontSize: 15, lineHeight: 1.6, margin: '0 0 1.5rem'}}>{msg('errorpage-403-hint')}</p>
        <InternalLink href="/" style={{fontSize: 13, color: 'var(--muted)', textDecoration: 'none'}}>{msg('forbidden-invite-back-home')}</InternalLink>
      </div>
    </LegacyShell>
  );
}

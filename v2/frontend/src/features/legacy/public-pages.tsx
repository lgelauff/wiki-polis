import {useSuspenseQuery} from '@tanstack/react-query';

import {sessionQuery} from '../../api/queries';
import {InternalLink} from '../../internal-link';
import {LegacyShell} from './legacy-shell';
import {useMessage} from '../../i18n/messages';
import {escapeHtml, richHtml} from '../../i18n/rich-html';

export function ForkPage() {
  const msg = useMessage();
  const {data: session} = useSuspenseQuery(sessionQuery());

  return (
    <LegacyShell headerMode="fork">
      <div className="container home-container">
        <div className="home-banner" dangerouslySetInnerHTML={richHtml(msg('home-banner-prototype',
          `<a href="https://github.com/lgelauff/wiki-polis/issues/new" target="_blank" rel="noopener">`
          + `${escapeHtml(msg('home-banner-open-issue'))}<span class="sr-only">${escapeHtml(msg('common-opens-in-new-tab'))}</span></a>`))} />

        <div className="landing-section">
          <h1 style={{fontSize: 26, fontWeight: 600, letterSpacing: '-0.02em', lineHeight: 1.15, marginBottom: 12}}>{msg('home-hero-heading')}</h1>
          <p style={{fontSize: 15, lineHeight: 1.6, color: 'var(--body)', maxWidth: 520}}>{msg('home-hero-body')}</p>
        </div>

        <div className="fork-grid">
          <InternalLink href="/demo" className="fork-card fork-card--demo" aria-label={msg('fork-demo-aria')}>
            <svg className="fork-card-icon" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M9 3h6M10 3v6l-5 8a2 2 0 0 0 1.7 3h10.6a2 2 0 0 0 1.7-3l-5-8V3" />
            </svg>
            <h2 className="fork-card-title">{msg('fork-demo-title')}</h2>
            <div className="fork-card-sub">{msg('fork-demo-sub')}</div>
            <span className="fork-card-cta">{msg('fork-demo-cta')}</span>
          </InternalLink>

          <InternalLink href="/consultations" className="fork-card fork-card--real" aria-label={msg('fork-real-aria')}>
            <svg className="fork-card-icon" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <circle cx="9" cy="8" r="3" /><path d="M3 20a6 6 0 0 1 12 0" />
              <circle cx="17" cy="9" r="2.4" /><path d="M15.5 20a5.5 5.5 0 0 1 6.5-5.4" />
            </svg>
            <h2 className="fork-card-title">{msg('fork-real-title')}</h2>
            <div className="fork-card-sub">{msg('fork-real-sub')}</div>
            <span className="fork-card-cta">{msg('fork-real-cta')}</span>
          </InternalLink>
        </div>

        {session.developerLogins.length > 0 && (
          <div style={{marginTop: '1.25rem', padding: '10px 14px', border: '1px dashed var(--spot)', borderRadius: 8, background: 'rgba(245,158,11,0.05)', display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap'}}>
            <span style={{fontFamily: 'var(--mono)', fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--spot)'}}>Dev</span>
            {session.developerLogins.map((login) => (
              <InternalLink
                key={login.username}
                href={login.href}
                style={{fontFamily: 'var(--mono)', fontSize: 11, padding: '2px 8px', borderRadius: 4, background: 'var(--surface2)', border: '1px solid var(--hairline)', color: 'var(--ink)', textDecoration: 'none'}}
                title={`Log in as ${login.username}`}
              >{login.username}</InternalLink>
            ))}
          </div>
        )}
      </div>
    </LegacyShell>
  );
}

import {useLayoutEffect, useState, type ReactNode} from 'react';
import {useSuspenseQuery} from '@tanstack/react-query';

import {sessionQuery} from '../../api/queries';
import {InternalLink} from '../../internal-link';
import {SpaModeToggle} from '../../strict-spa-mode';

type HeaderMode = 'fork' | 'demo' | 'real' | 'conversation-demo' | 'conversation-real' | 'admin' | 'plain';

const SITE_NOTICE_STORAGE_KEY = 'proto-wiki.site-notice.development.v1';

function SiteNotice() {
  const [visible, setVisible] = useState(() => {
    try { return localStorage.getItem(SITE_NOTICE_STORAGE_KEY) !== 'dismissed'; }
    catch { return true; }
  });

  if (!visible) return null;

  function dismiss() {
    try { localStorage.setItem(SITE_NOTICE_STORAGE_KEY, 'dismissed'); }
    catch { /* Dismiss for this view even when browser storage is unavailable. */ }
    setVisible(false);
  }

  return (
    <aside className="site-notice" aria-label="Prototype notice">
      <div className="site-notice__inner">
        <p>
          Prototype in active development. Things may change.{' '}
          <InternalLink href="https://github.com/lgelauff/wiki-polis/issues/new" target="_blank" rel="noopener">
            Open an issue<span className="sr-only"> (opens in a new tab)</span>
          </InternalLink>{' '}if you find a bug.
        </p>
        <button className="site-notice__dismiss" type="button" aria-label="Dismiss site notice" onClick={dismiss}>
          <span aria-hidden="true">×</span>
        </button>
      </div>
    </aside>
  );
}

function OrbitMark() {
  return (
    <svg
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1"
      strokeLinecap="round"
      strokeDasharray="1.4 1.6"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="9" />
      <ellipse cx="12" cy="12" rx="9" ry="3.5" />
      <ellipse cx="12" cy="12" rx="3.5" ry="9" />
    </svg>
  );
}

function useLegacyDocument({demo, title}: {demo: boolean; title: string}) {
  useLayoutEffect(() => {
    const previousTitle = document.title;
    const previousDemo = document.body.getAttribute('data-demo');
    const initialDemo = document.body.dataset.spaInitialDemo === 'true';
    const root = document.documentElement;
    const previousBackground = root.style.getPropertyValue('background');
    const previousFontSynthesis = root.style.getPropertyValue('font-synthesis');
    const previousTextRendering = root.style.getPropertyValue('text-rendering');
    document.title = title;
    root.style.setProperty('font-synthesis', 'weight style small-caps');
    root.style.setProperty('text-rendering', 'auto');
    root.style.setProperty('background', demo ? 'transparent' : 'var(--bg)');
    if (demo) document.body.dataset.demo = 'true';
    else document.body.removeAttribute('data-demo');

    return () => {
      document.title = previousTitle;
      if (previousBackground) root.style.setProperty('background', previousBackground);
      else root.style.removeProperty('background');
      if (previousFontSynthesis) root.style.setProperty('font-synthesis', previousFontSynthesis);
      else root.style.removeProperty('font-synthesis');
      if (previousTextRendering) root.style.setProperty('text-rendering', previousTextRendering);
      else root.style.removeProperty('text-rendering');
      if (initialDemo) {
        document.body.removeAttribute('data-demo');
        document.body.removeAttribute('data-spa-initial-demo');
      } else if (previousDemo === null) document.body.removeAttribute('data-demo');
      else document.body.setAttribute('data-demo', previousDemo);
    };
  }, [demo, title]);
}

export function LegacyShell({
  children,
  crumb,
  headerCrumb,
  headerMode = 'plain',
  toast,
  title = 'ProtoWiki',
}: {
  children: ReactNode;
  crumb?: string;
  headerCrumb?: ReactNode;
  headerMode?: HeaderMode;
  toast?: ReactNode;
  title?: string;
}) {
  const {data: session} = useSuspenseQuery(sessionQuery());
  const authenticated = session.state === 'authenticated';
  useLegacyDocument({demo: headerMode === 'demo' || headerMode === 'conversation-demo', title});

  return (
    <>
      <SiteNotice />

      <header className={`site-header ${headerMode === 'admin' ? 'site-header--admin' : 'site-header--participant'}`}>
        <div className="header-inner">
          <div className="header-left">
            <InternalLink href="/" className="header-logo">
              <OrbitMark />
              <span className="header-title">ProtoWiki</span>
            </InternalLink>
            {headerMode === 'admin' && <span className="header-mode-badge">Admin</span>}
            {headerCrumb}
            {!headerCrumb && crumb && (
              <span className="header-crumb">
                <span className="header-crumb-sep">/</span>
                <span>{crumb}</span>
              </span>
            )}
          </div>

          <div className="header-right">
            <SpaModeToggle developerMode={session.developerMode} />
            {headerMode !== 'plain' && headerMode !== 'admin' && (
              headerMode === 'conversation-demo' ? (
                <span className="mode-lock mode-lock--demo">
                  <span className="mode-lock-dot" aria-hidden="true" />Demo
                </span>
              ) : headerMode === 'conversation-real' ? (
                <span className="mode-lock mode-lock--real">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
                    <rect x="5" y="11" width="14" height="10" rx="2" />
                    <path d="M8 11V7a4 4 0 0 1 8 0v4" />
                  </svg>Real consultation
                </span>
              ) : <div className="mode-switch" role="group" aria-label="Choose demo or real mode">
                <InternalLink
                  href="/demo"
                  className={`mode-switch-opt mode-switch-opt--demo${headerMode === 'demo' ? ' is-active' : ''}`}
                  aria-current={headerMode === 'demo' ? 'true' : undefined}
                >Try it out</InternalLink>
                <InternalLink
                  href="/consultations"
                  className={`mode-switch-opt mode-switch-opt--real${headerMode === 'real' ? ' is-active' : ''}`}
                  aria-current={headerMode === 'real' ? 'true' : undefined}
                >Real</InternalLink>
              </div>
            )}
            {authenticated ? (
              <>
                <span className="header-user-chip">
                  <span className="header-user-chip-dot" />
                  {session.user?.username}
                </span>
                <form method="post" action={session.links.logout} style={{display: 'inline'}}>
                  <input type="hidden" name="csrf_token" value={session.csrfToken} />
                  <button type="submit" className="header-logout">log out</button>
                </form>
                {session.capabilities.administerSite && (
                  <InternalLink href="/admin" className="header-admin-link">admin</InternalLink>
                )}
              </>
            ) : (
              <InternalLink href={session.links.login} style={{color: 'var(--muted)', fontSize: 13, textDecoration: 'none'}}>log in</InternalLink>
            )}
          </div>
        </div>
      </header>

      <main className="legacy-main" id="main" tabIndex={-1}>{children}</main>
      <div id="toast-container">{toast}</div>
      <footer style={{textAlign: 'right', padding: '.5rem 1rem', fontSize: 11, color: 'var(--muted)'}}>
        <code>{session.gitVersion}</code>
      </footer>
    </>
  );
}

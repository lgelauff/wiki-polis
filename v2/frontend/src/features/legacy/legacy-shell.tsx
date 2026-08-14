import {useEffect, type ReactNode} from 'react';
import {useSuspenseQuery} from '@tanstack/react-query';

import {sessionQuery} from '../../api/queries';

type HeaderMode = 'fork' | 'demo' | 'real' | 'plain';

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
  useEffect(() => {
    const previousTitle = document.title;
    const previousDemo = document.body.getAttribute('data-demo');
    const stylesheet = document.createElement('link');
    stylesheet.rel = 'stylesheet';
    stylesheet.href = '/static/style.css';
    stylesheet.dataset.reactLegacyStyles = 'true';
    document.head.appendChild(stylesheet);
    document.title = title;
    if (demo) document.body.dataset.demo = 'true';
    else document.body.removeAttribute('data-demo');

    return () => {
      stylesheet.remove();
      document.title = previousTitle;
      if (previousDemo === null) document.body.removeAttribute('data-demo');
      else document.body.setAttribute('data-demo', previousDemo);
    };
  }, [demo, title]);
}

export function LegacyShell({
  children,
  crumb,
  headerMode = 'plain',
  title = 'ProtoWiki',
}: {
  children: ReactNode;
  crumb?: string;
  headerMode?: HeaderMode;
  title?: string;
}) {
  const {data: session} = useSuspenseQuery(sessionQuery());
  const authenticated = session.state === 'authenticated';
  useLegacyDocument({demo: headerMode === 'demo', title});

  return (
    <>
      <header className="site-header site-header--participant">
        <div className="header-inner">
          <div className="header-left">
            <a href="/app/parity/fork" className="header-logo">
              <OrbitMark />
              <span className="header-title">ProtoWiki</span>
            </a>
            {crumb && (
              <span className="header-crumb">
                <span className="header-crumb-sep">/</span>
                <span>{crumb}</span>
              </span>
            )}
          </div>

          <div className="header-right">
            {headerMode !== 'plain' && (
              <div className="mode-switch" role="group" aria-label="Choose demo or real mode">
                <a
                  href="/app/demo"
                  className={`mode-switch-opt mode-switch-opt--demo${headerMode === 'demo' ? ' is-active' : ''}`}
                  aria-current={headerMode === 'demo' ? 'true' : undefined}
                >Try it out</a>
                <a
                  href="/app/real"
                  className={`mode-switch-opt mode-switch-opt--real${headerMode === 'real' ? ' is-active' : ''}`}
                  aria-current={headerMode === 'real' ? 'true' : undefined}
                >Real</a>
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
                  <a href="/app/admin" className="header-admin-link">admin</a>
                )}
              </>
            ) : (
              <a href={session.links.login} style={{color: 'var(--muted)', fontSize: 13, textDecoration: 'none'}}>log in</a>
            )}
          </div>
        </div>
      </header>

      <main id="main" tabIndex={-1}>{children}</main>
      <div id="toast-container" />
      <footer style={{textAlign: 'right', padding: '.5rem 1rem', fontSize: 11, color: 'var(--muted)'}}>
        <code>react</code>
      </footer>
    </>
  );
}

import {useLayoutEffect, type ReactNode} from 'react';
import {useSuspenseQuery} from '@tanstack/react-query';

import {sessionQuery} from '../../api/queries';
import {InternalLink} from '../../internal-link';
import {useMessage, type Message} from '../../i18n/messages';
import {escapeHtml, richHtml} from '../../i18n/rich-html';

type HeaderMode = 'fork' | 'demo' | 'real' | 'conversation-demo' | 'conversation-real' | 'admin' | 'plain';

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


/** Language switcher.
 *
 *  Links carrying `?uselang=`, not a <select> with an onChange: the parameter is the
 *  interface, so a link is shareable, works without JavaScript, survives a middle-click, and
 *  needs no state. The server persists the choice to the `uselang` cookie, so it outlives the
 *  query string.
 *
 *  `reloadDocument` because a language change has to be a full navigation, not a client-side
 *  route change. The server re-negotiates, sets the cookie, and re-stamps <html lang> and the
 *  pre-catalogue strings; MessageProvider reads the locale once at mount, so a soft navigation
 *  would leave the document claiming the old language while the content changed underneath.
 *
 *  Option labels are autonyms and are deliberately NOT translated — someone looking for Dutch
 *  is scanning for "Nederlands". Only the group's accessible name is a message.
 *
 *  Rendered even with one language, so the control exists and is testable before a second
 *  locale is delivered; `aria-current` marks the active one rather than styling alone. */
function LanguageSwitcher({locales, msg}: {
  locales: {current: string; available: {code: string; name: string}[]};
  msg: Message;
}) {
  if (!locales.available.length) return null;
  return (
    <nav className="lang-switch" aria-label={msg('base-language-label')}>
      {locales.available.map((locale) => (
        <InternalLink
          key={locale.code}
          className={`lang-switch-opt${locale.code === locales.current ? ' is-active' : ''}`}
          href={`?uselang=${encodeURIComponent(locale.code)}`}
          hrefLang={locale.code}
          lang={locale.code}
          aria-current={locale.code === locales.current ? 'true' : undefined}
          reloadDocument
        >{locale.name}</InternalLink>
      ))}
    </nav>
  );
}

export function LegacyShell({
  children,
  crumb,
  headerCrumb,
  headerMode = 'plain',
  toast,
  title = 'Proto',
}: {
  children: ReactNode;
  crumb?: string;
  headerCrumb?: ReactNode;
  headerMode?: HeaderMode;
  toast?: ReactNode;
  title?: string;
}) {
  const msg = useMessage();
  const {data: session} = useSuspenseQuery(sessionQuery());
  const authenticated = session.state === 'authenticated';
  useLegacyDocument({demo: headerMode === 'demo' || headerMode === 'conversation-demo', title});

  return (
    <>
      <header className={`site-header ${headerMode === 'admin' ? 'site-header--admin' : 'site-header--participant'}`}>
        <div className="header-inner">
          <div className="header-left">
            <InternalLink href="/" className="header-logo">
              <OrbitMark />
              <span className="header-title">Proto</span>
            </InternalLink>
            {headerMode === 'admin' && <span className="header-mode-badge">{msg('base-admin-badge')}</span>}
            {headerCrumb}
            {!headerCrumb && crumb && (
              <span className="header-crumb">
                <span className="header-crumb-sep">/</span>
                <span>{crumb}</span>
              </span>
            )}
          </div>

          <div className="header-right">
            {headerMode !== 'plain' && headerMode !== 'admin' && (
              headerMode === 'conversation-demo' ? (
                <span className="mode-lock mode-lock--demo">
                  <span className="mode-lock-dot" aria-hidden="true" />{msg('conv-demo-label')}
                </span>
              ) : headerMode === 'conversation-real' ? (
                <span className="mode-lock mode-lock--real">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
                    <rect x="5" y="11" width="14" height="10" rx="2" />
                    <path d="M8 11V7a4 4 0 0 1 8 0v4" />
                  </svg>{msg('base-lock-real')}
                </span>
              ) : <div className="mode-switch" role="group" aria-label={msg('base-mode-switch-aria')}>
                <InternalLink
                  href="/demo"
                  className={`mode-switch-opt mode-switch-opt--demo${headerMode === 'demo' ? ' is-active' : ''}`}
                  aria-current={headerMode === 'demo' ? 'true' : undefined}
                >{msg('base-mode-demo')}</InternalLink>
                <InternalLink
                  href="/consultations"
                  className={`mode-switch-opt mode-switch-opt--real${headerMode === 'real' ? ' is-active' : ''}`}
                  aria-current={headerMode === 'real' ? 'true' : undefined}
                >{msg('base-mode-real')}</InternalLink>
              </div>
            )}
            <LanguageSwitcher locales={session.locales} msg={msg} />
            {authenticated ? (
              <>
                <span className="header-user-chip">
                  <span className="header-user-chip-dot" />
                  {session.user?.username}
                </span>
                <form method="post" action={session.links.logout} style={{display: 'inline'}}>
                  <input type="hidden" name="csrf_token" value={session.csrfToken} />
                  <button type="submit" className="header-logout">{msg('base-log-out')}</button>
                </form>
                {session.capabilities.administerSite && (
                  <InternalLink href="/admin" className="header-admin-link">{msg('base-admin-link')}</InternalLink>
                )}
              </>
            ) : (
              <InternalLink href={session.links.login} style={{color: 'var(--muted)', fontSize: 13, textDecoration: 'none'}}>{msg('base-log-in')}</InternalLink>
            )}
          </div>
        </div>
      </header>

      <main className="legacy-main" id="main" tabIndex={-1}>{children}</main>
      <div id="toast-container">{toast}</div>
      <footer style={{display: 'flex', justifyContent: 'space-between', gap: '1rem', padding: '.5rem 1rem', fontSize: 11, color: 'var(--muted)'}}>
        <span dangerouslySetInnerHTML={richHtml(msg('base-footer-licence',
          `<a href="https://creativecommons.org/publicdomain/zero/1.0/" target="_blank" rel="noopener" style="color:inherit">`
          + `${escapeHtml(msg('accept-licence-link'))}<span class="sr-only">${escapeHtml(msg('common-opens-in-new-tab'))}</span></a>`))} />
        <code>{session.gitVersion}</code>
      </footer>
    </>
  );
}

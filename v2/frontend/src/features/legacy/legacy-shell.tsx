import {useLayoutEffect, type ReactNode} from 'react';
import {useSuspenseQuery} from '@tanstack/react-query';
import {useLocation} from 'react-router-dom';

import {sessionQuery} from '../../api/queries';
import {InternalLink} from '../../internal-link';
import {useLocale, useMessage, type Message} from '../../i18n/messages';
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


/** Language switcher — compact <select> that performs a full navigation on change.
 *
 *  Autonyms as option text — a Dutch speaker scanning for "Nederlands" recognises it
 *  immediately.  The <select> shows the current choice, so no extra label is needed.
 *
 *  `reloadDocument`-equivalent: setting `window.location.href` forces a full page load
 *  so the server re-negotiates the locale, stamps `<html lang>`, and persists the
 *  `uselang` cookie.
 *
 *  The <form> wrapper provides a no-JS fallback: a hidden submit button inside
 *  `<noscript>` makes the GET request work when JavaScript is disabled.  JS
 *  auto-submits on change, so the visible control is just the <select>.
 *
 *  Hidden until a second language exists, so it is not a dead control on every page. */

function localeHref(location: {pathname: string; search: string; hash: string}, code: string) {
  const params = new URLSearchParams(location.search);
  params.set('uselang', code);
  return `${location.pathname}?${params.toString()}${location.hash}`;
}

function preserveParams(location: {search: string}) {
  const params = new URLSearchParams(location.search);
  params.delete('uselang');
  return [...params.entries()].map(([k, v]) => (
    <input key={k} type="hidden" name={k} value={v} />
  ));
}

function LanguageSwitcher({locales, active, msg}: {
  locales: {current: string; available: {code: string; name: string}[]};
  active: string;
  msg: Message;
}) {
  const location = useLocation();
  if (locales.available.length < 2) return null;
  return (
    <form method="GET" action={location.pathname} className="lang-select-form">
      {preserveParams(location)}
      <select
        className="lang-select"
        name="uselang"
        value={active}
        aria-label={msg('base-language-label')}
        onChange={(e) => { window.location.href = localeHref(location, e.target.value); }}
      >
        {locales.available.map((locale) => (
          <option key={locale.code} value={locale.code} lang={locale.code}>
            {locale.name}
          </option>
        ))}
      </select>
      <noscript><button type="submit" className="lang-select-submit">{msg('base-language-label')}</button></noscript>
    </form>
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
  const activeLocale = useLocale();
  const {data: session} = useSuspenseQuery(sessionQuery());
  const authenticated = session.state === 'authenticated';
  // A voucher account is signed in but has no username to show (#368).
  const signedIn = authenticated || session.state === 'voucher';
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

          <div className="header-controls">
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
            <LanguageSwitcher locales={session.locales} active={activeLocale} msg={msg} />
            {authenticated && session.capabilities.administerSite && (
              <InternalLink href="/admin" className="header-admin-link">{msg('base-admin-link')}</InternalLink>
            )}
          </div>
          <div className="header-identity">
            {signedIn ? (
              <>
                <span className="header-user-chip">
                  <span className="header-user-chip-dot" />
                  {authenticated ? session.user?.username : msg('base-voucher-account')}
                </span>
                <form method="post" action={session.links.logout} style={{display: 'inline'}}>
                  <input type="hidden" name="csrf_token" value={session.csrfToken} />
                  <button type="submit" className="header-logout">{msg('base-log-out')}</button>
                </form>
              </>
            ) : (
              <InternalLink href={session.links.login} className="header-login-link">{msg('base-log-in')}</InternalLink>
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

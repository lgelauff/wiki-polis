import {useEffect, useLayoutEffect, useState, type ReactNode} from 'react';
import {useSuspenseQuery} from '@tanstack/react-query';
import {useLocation} from 'react-router-dom';

import type {components} from '../../api/schema';
import {sessionQuery} from '../../api/queries';
import {InternalLink} from '../../internal-link';
import {useLocale, useMessage, type Message} from '../../i18n/messages';
import {escapeHtml, richHtml} from '../../i18n/rich-html';
import {roleLabel} from '../../i18n/server-labels';
import {AnnounceProvider, AnnouncerRegions, useAnnouncer, type Announcer} from './admin-announcer';
import './console.css';

type Lifecycle = components['schemas']['AdminLifecycle'];
type GatingType = components['schemas']['AdminSettings']['conversation']['gatingType'];

const SECTIONS_ID = 'admin-shell-sections';

/** The product mark: one outline glyph for the whole console, drawn with currentColor so
 *  it takes the colour of whatever it sits on. */
function ConsoleMark() {
  return (
    <svg className="admin-shell__mark-glyph" width="22" height="22" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" aria-hidden="true" focusable="false">
      <circle cx="12" cy="12" r="8" />
      <ellipse cx="12" cy="12" rx="8" ry="3.25" />
    </svg>
  );
}

/** The role glyph. It stands beside the role word and says what that word is -- the
 *  operator's role -- so it explains itself on hover (the <title>) and carries the same
 *  words as its accessible name, read just before the role word. */
function RoleGlyph({label}: {label: string}) {
  return (
    <svg className="admin-shell__role-glyph" width="14" height="14" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" role="img" aria-label={label} focusable="false">
      <title>{label}</title>
      <circle cx="12" cy="8.5" r="3.75" />
      <path d="M4.75 20a7.25 7.25 0 0 1 14.5 0" />
    </svg>
  );
}

/** The document-title effect the legacy shell carries, kept because a console page is a page
 *  frame: without the restore the title and the root's font settings would leak into the
 *  next route. The demo branch is gone — an admin page is never the Practice Environment.
 *
 *  Copied rather than imported because `legacy-shell.tsx` is outside this issue's file list;
 *  it is deleted with the last page that still uses it. */
function useAdminDocument(title: string) {
  useLayoutEffect(() => {
    const previousTitle = document.title;
    const root = document.documentElement;
    const previousBackground = root.style.getPropertyValue('background');
    const previousFontSynthesis = root.style.getPropertyValue('font-synthesis');
    const previousTextRendering = root.style.getPropertyValue('text-rendering');
    document.title = title;
    root.style.setProperty('font-synthesis', 'weight style small-caps');
    root.style.setProperty('text-rendering', 'auto');
    root.style.setProperty('background', 'var(--bg)');

    return () => {
      document.title = previousTitle;
      if (previousBackground) root.style.setProperty('background', previousBackground);
      else root.style.removeProperty('background');
      if (previousFontSynthesis) root.style.setProperty('font-synthesis', previousFontSynthesis);
      else root.style.removeProperty('font-synthesis');
      if (previousTextRendering) root.style.setProperty('text-rendering', previousTextRendering);
      else root.style.removeProperty('text-rendering');
    };
  }, [title]);
}

/** The 1024px breakpoint, decided in JS as well as in `console.css`.
 *
 *  A disclosure whose links are only hidden by CSS leaves them in the accessibility tree
 *  and in the tab order, and `aria-expanded` needs state somewhere anyway — so the
 *  collapsed state is the absence of the links, not their opacity. */
const NARROW_VIEWPORT = '(max-width: 1023px)';

function useNarrowViewport() {
  const [narrow, setNarrow] = useState(
    () => globalThis.matchMedia?.(NARROW_VIEWPORT).matches ?? false,
  );
  useEffect(() => {
    const list = globalThis.matchMedia?.(NARROW_VIEWPORT);
    if (!list) return undefined;
    const follow = () => setNarrow(list.matches);
    follow();
    list.addEventListener('change', follow);
    return () => list.removeEventListener('change', follow);
  }, []);
  return narrow;
}

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

/** Language switcher — compact <select> that performs a full navigation on change.
 *
 *  Autonyms as option text — a Dutch speaker scanning for "Nederlands" recognises it
 *  immediately, which is also why the options are not translatable copy.
 *
 *  Setting `window.location.href` forces a full page load so the server re-negotiates the
 *  locale, stamps `<html lang>`, and persists the `uselang` cookie. The <form> wrapper is
 *  the no-JS fallback: the hidden submit button inside `<noscript>` makes the GET request
 *  work without JavaScript. JS auto-submits on change, so the visible control is the
 *  <select> alone.
 *
 *  Hidden until a second language exists, so it is not a dead control on every page. */
function LanguageSwitcher({locales, active, msg}: {
  locales: {current: string; available: {code: string; name: string}[]};
  active: string;
  msg: Message;
}) {
  const location = useLocation();
  if (locales.available.length < 2) return null;
  return (
    <form method="GET" action={location.pathname} className="admin-shell__lang">
      {preserveParams(location)}
      <select
        className="admin-shell__lang-select"
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
      <noscript><button type="submit" className="admin-shell__lang-submit">{msg('base-language-label')}</button></noscript>
    </form>
  );
}

/** The four sections of the console. The page inside the frame names the one it is on;
 *  the frame is what marks it, and what builds the sidebar and the breadcrumb from it. */
export type AdminSection = 'overview' | 'settings' | 'moderation' | 'content';

/** The frame every admin page sits in: sidebar, top bar, one main, one announcement region
 *  and one notification slot. It renders only what the lifecycle DTO already carries, so a
 *  page inside it needs no new server field to get a complete frame.
 *
 *  `title` is the document title, assembled by the page because the wording is that page's.
 *  `section` is the section the page belongs to: the sidebar marks it and the breadcrumb
 *  names it. `subPage` is the page's own name within that section, added to the breadcrumb
 *  when the page has one.
 *  `gatingType` comes from the settings query the page already runs, and only decides
 *  whether the participant view is a preview. */
export function AdminShell({announcer, children, data, gatingType, section, subPage, title, toast}: {
  announcer?: Announcer | undefined;
  children: ReactNode;
  data: Lifecycle;
  gatingType: GatingType;
  section: AdminSection;
  subPage?: string | undefined;
  title: string;
  toast?: ReactNode;
}) {
  const msg = useMessage();
  // A page that announces from its own code hands its announcer in; otherwise the frame
  // keeps one for whatever is rendered inside it.
  const ownAnnouncer = useAnnouncer();
  const {announcement, announce} = announcer ?? ownAnnouncer;
  const activeLocale = useLocale();
  const {data: session} = useSuspenseQuery(sessionQuery());
  const narrow = useNarrowViewport();
  const [sectionsOpen, setSectionsOpen] = useState(false);
  useAdminDocument(title);

  const authenticated = session.state === 'authenticated';
  // A voucher account is signed in but has no username to show (#368).
  const signedIn = authenticated || session.state === 'voucher';
  // Overview is the one section `links.*` does not cover -- the DTO links the other
  // sections and the participant view, not the page this frame is built around -- so the
  // client builds it from the conversation the lifecycle DTO names. It is an ordinary
  // client path, rendered through InternalLink like the other sidebar links.
  const overviewHref = `/admin/conversations/${data.conversation.id}`;
  const openFlags = data.counts.openFlags;
  const sections: {id: AdminSection; label: string; href: string; badge?: string | null}[] = [
    {id: 'overview', label: msg('admin-shell-overview'), href: overviewHref},
    {id: 'settings', label: msg('admin-overview-card-settings'), href: data.links.settings},
    {id: 'moderation', label: msg('admin-shell-moderation'), href: data.links.moderation,
      // A zero is not worth a badge: an empty counter is noise, not information.
      badge: openFlags > 0 ? msg('adminconv-open-count', openFlags) : null},
    {id: 'content', label: msg('admin-shell-content'), href: data.links.statements},
  ];
  const current = sections.find((item) => item.id === section);
  // The breadcrumb is title / section / sub-page, and the last crumb is the page itself:
  // the trail a screen reader reads back is the one that ends where the reader is.
  const crumbs = [data.conversation.title, current?.label ?? null, subPage ?? null]
    .filter((crumb): crumb is string => Boolean(crumb));

  return (
    <div className="admin-shell">
      <header className="admin-shell__topbar">
        <p className="admin-shell__coming" lang="en">Also coming: Admin home — not available yet (#473)</p>
        <nav className="admin-shell__crumbs" aria-label={msg('admin-crumb-aria')}>
          <ol>
            {crumbs.map((crumb, index) => (
              <li
                className="admin-shell__crumb"
                // By position: a consultation may be titled like a section ("Settings").
                key={index}
                aria-current={index === crumbs.length - 1 ? 'page' : undefined}
              >
                {crumb}
              </li>
            ))}
          </ol>
        </nav>
        <div className="admin-shell__tools">
          <LanguageSwitcher locales={session.locales} active={activeLocale} msg={msg} />
          <div className="admin-shell__switch" role="group" aria-label={msg('admin-shell-switch-aria')}>
            <InternalLink href={data.links.participantView} className="admin-shell__switch-option">
              {gatingType === 'voucher' ? msg('admin-shell-participant-preview') : msg('admin-shell-participant')}
            </InternalLink>
            {/* Text, not a link: the DTO carries no link to the console's own page, and a
                link to where you already are is an action that goes nowhere. */}
            <span className="admin-shell__switch-option is-current" aria-current="true">{msg('base-admin-badge')}</span>
          </div>
          <div className="admin-shell__identity">
            {/* The name is cut off with an ellipsis when long, so the whole of it is the hover title. */}
            <span className="admin-shell__user" title={authenticated ? session.user?.username : undefined}>{authenticated ? session.user?.username : msg('base-voucher-account')}</span>
            <span className="admin-shell__role"><RoleGlyph label={msg('adminconv-role-title')} /><span>{roleLabel(msg, data.operator.roleLabel)}</span></span>
            {signedIn && (
              <form method="post" action={session.links.logout} className="admin-shell__logout">
                <input type="hidden" name="csrf_token" value={session.csrfToken} />
                <button type="submit">{msg('base-log-out')}</button>
              </form>
            )}
          </div>
        </div>
      </header>

      <div className="admin-shell__body">
        <nav className="admin-shell__side" aria-label={msg('admin-shell-nav-aria')}>
          <div className="admin-shell__brand">
            {/* Admin home only for a site administrator: today's crumb sends an organizer
                to a 403, and a link to a page you may not open is information as an action. */}
            {session.capabilities.administerSite ? (
              <InternalLink href="/admin" className="admin-shell__mark">
                <ConsoleMark />
                <span className="admin-shell__mark-word">{msg('base-admin-badge')}</span>
              </InternalLink>
            ) : (
              <span className="admin-shell__mark">
                <ConsoleMark />
                <span className="admin-shell__mark-word">{msg('base-admin-badge')}</span>
              </span>
            )}
          </div>
          <p className="admin-shell__coming" lang="en">Also coming: switching between consultations — not available yet (#473)</p>
          {narrow && (
            <button
              type="button"
              className="admin-shell__sections-toggle"
              aria-expanded={sectionsOpen}
              aria-controls={SECTIONS_ID}
              onClick={() => setSectionsOpen((open) => !open)}
            >
              {msg('admin-shell-sections')}
            </button>
          )}
          <ul className="admin-shell__sections" id={SECTIONS_ID} hidden={narrow && !sectionsOpen}>
            {sections.map((section) => (
              <li className="admin-shell__section" key={section.id}>
                <InternalLink
                  href={section.href}
                  className="admin-shell__section-link"
                  aria-current={section.id === current?.id ? 'page' : undefined}
                >
                  <span>{section.label}</span>
                  {section.badge && <span className="admin-shell__badge">{section.badge}</span>}
                </InternalLink>
              </li>
            ))}
          </ul>
        </nav>

        <main id="main" tabIndex={-1} className="admin-shell__main">
          {/* The notification slot is an area at the top of the content, not an overlay:
              a fixed toast covers what it sits on (WCAG 2.4.11). */}
          <div className="admin-shell__notices"><AnnounceProvider value={announce}>{toast}</AnnounceProvider></div>
          {/* The one place that announces a result: a toast, a save, a row action. Always
              mounted, and the only live regions in the frame -- the toast inside the shell
              reads out through it rather than carrying a role of its own. */}
          <AnnouncerRegions announcement={announcement} />
          <AnnounceProvider value={announce}>{children}</AnnounceProvider>
        </main>
      </div>

      {/* Licence line for the people who write here: admin-written texts meant for publication are
          CC0 as well (epic #473 decisions). Quiet text, the git version left out. */}
      <footer className="admin-shell__footer">
        <span dangerouslySetInnerHTML={richHtml(msg('admin-shell-licence',
          '<a href="https://creativecommons.org/publicdomain/zero/1.0/" target="_blank" rel="noopener">'
          + `${escapeHtml(msg('accept-licence-link'))}<span class="sr-only"> ${escapeHtml(msg('common-opens-in-new-tab'))}</span></a>`))} />
      </footer>
    </div>
  );
}

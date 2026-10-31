import {createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode} from 'react';
import {useSuspenseQuery} from '@tanstack/react-query';
import {useLocation, useNavigationType} from 'react-router-dom';

import {sessionQuery} from '../../api/queries';
import {useMessage} from '../../i18n/messages';
import {LegacyToast} from './legacy-toast';

export type LogoutNoticeKind = 'logged-out' | 'voucher' | 'revoked';

const LogoutNoticeContext = createContext<{kind: LogoutNoticeKind | null; dismiss: () => void}>({kind: null, dismiss: () => {}});

/** Holds the one-time logout note (#514) for the page it arrived on.
 *
 *  The server hands the note out once, in the session response of the first page after a
 *  logout, and forgets it. It lives above the routes so that a page swapping its own shell
 *  (a loading state, then the page) keeps it, and it follows a redirect; it is dropped as
 *  soon as the visitor moves to another page, and a reload does not bring it back. */
export function LogoutNoticeProvider({children}: {children: ReactNode}) {
  const {data: session, dataUpdatedAt} = useSuspenseQuery(sessionQuery());
  const {pathname} = useLocation();
  const navigationType = useNavigationType();
  const [seenAt, setSeenAt] = useState<number | null>(null);
  const [held, setHeld] = useState<{kind: LogoutNoticeKind; path: string} | null>(null);
  const incoming = session.logoutNotice ?? null;
  if (incoming && seenAt !== dataUpdatedAt) {
    // Adjusting state while rendering, React's pattern for state derived from new data.
    setSeenAt(dataUpdatedAt);
    setHeld({kind: incoming, path: pathname});
  }
  useEffect(() => {
    if (!held || held.path === pathname) return;
    // A redirect (the consultation sending a newcomer on to its join page) is still the
    // page the logout landed on; a click or Back is not.
    setHeld(navigationType === 'REPLACE' ? {...held, path: pathname} : null);
  }, [held, pathname, navigationType]);
  const kind = held && (held.path === pathname || navigationType === 'REPLACE') ? held.kind : null;
  const dismiss = useCallback(() => setHeld(null), []);
  const value = useMemo(() => ({kind, dismiss}), [kind, dismiss]);
  return <LogoutNoticeContext.Provider value={value}>{children}</LogoutNoticeContext.Provider>;
}

/** The note for the page on screen, as the shell's small pop-up (LegacyToast, top right).
 *  "You are logged out." closes itself like any info toast; the code-account reminder and
 *  the withdrawn-code note may be the only word on how to come back or what happened, so
 *  they stay until closed with × or the visitor moves on. */
export function LogoutNotice() {
  const msg = useMessage();
  const {kind, dismiss} = useContext(LogoutNoticeContext);
  const text = kind === 'revoked'
    ? msg('logout-notice-revoked')
    : kind === 'voucher'
      ? `${msg('logout-notice')} ${msg('logout-notice-voucher')}`
      : msg('logout-notice');
  // Stable while shown, so the toast's timer is not restarted by a re-render.
  const toast = useMemo(() => (kind ? {id: 1, category: 'info' as const, message: text} : null), [kind, text]);
  if (!toast) return null;
  return <LegacyToast toast={toast} onDismiss={dismiss} sticky={kind !== 'logged-out'} />;
}

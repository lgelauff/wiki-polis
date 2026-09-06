import Banana from 'banana-i18n';
import {queryOptions, useSuspenseQuery} from '@tanstack/react-query';
import {createContext, useContext, useMemo, type ReactNode} from 'react';

import {sessionQuery} from '../api/queries';

const SOURCE_LOCALE = 'en';

/** Mirrors the server's own precedence in `_negotiate_locale`: ?uselang= wins, then the
 *  `uselang` cookie (deliberately not HttpOnly so the client can read it), then English.
 *
 *  The query parameter is not optional. `qqx` -- the QA locale that renders message keys,
 *  and the only way to see which strings are still unwrapped -- bypasses ENABLED_LOCALES
 *  and is deliberately never written to the cookie. Reading the cookie alone would leave
 *  the SPA in English for the one locale whose entire purpose is to inspect the SPA. */
export function readLocale(): string {
  const requested = new URLSearchParams(window.location.search).get('uselang');
  if (requested) return requested;
  const match = document.cookie.match(/(?:^|;\s*)uselang=([^;]+)/);
  return match?.[1] ? decodeURIComponent(match[1]) : SOURCE_LOCALE;
}

/** The catalogue is a bare `{key: text}` map, not the `{data: ...}` envelope the rest of
 *  API v1 uses, because that is exactly what banana-i18n takes as a message store. It
 *  therefore cannot go through `requireApiData`, and this is the one deliberate exception
 *  to the "no direct fetch" rule in the frontend README.
 *
 *  `version` pins the response so it is cacheable for a week; without it the server sends
 *  no-store. It comes from the session payload, which every page already loads. */
export function messagesQuery(locale: string, version: string) {
  return queryOptions({
    queryKey: ['i18n', locale, version],
    queryFn: async (): Promise<Record<string, string>> => {
      const url = `/api/v1/i18n/${encodeURIComponent(locale)}`
        + (version ? `?v=${encodeURIComponent(version)}` : '');
      const response = await fetch(url, {headers: {Accept: 'application/json'}});
      if (!response.ok) {
        throw new Error(`Message catalogue unavailable (HTTP ${response.status}).`);
      }
      return response.json() as Promise<Record<string, string>>;
    },
    staleTime: Infinity,   // pinned by version; a new deploy changes the key
  });
}

export type Message = (key: string, ...params: (string | number)[]) => string;

const MessageContext = createContext<Message | null>(null);

export function MessageProvider({children, locale = readLocale()}: {children: ReactNode; locale?: string}) {
  const {data: session} = useSuspenseQuery(sessionQuery());
  const {data: messages} = useSuspenseQuery(messagesQuery(locale, session.gitVersion ?? ''));

  const msg = useMemo<Message>(() => {
    const banana = new Banana(locale, {messages: {[locale]: messages}});
    return (key, ...params) => banana.i18n(key, ...params);
  }, [locale, messages]);

  return <MessageContext.Provider value={msg}>{children}</MessageContext.Provider>;
}

/** `msg('conv-col-shift')`, or `msg('conv-participant-count', 3)` for parameters.
 *  Throws outside a provider rather than silently rendering keys to users. */
export function useMessage(): Message {
  const msg = useContext(MessageContext);
  if (!msg) {
    throw new Error('useMessage() used outside a <MessageProvider>.');
  }
  return msg;
}

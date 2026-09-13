import Banana from 'banana-i18n';
import {queryOptions, useQuery, useSuspenseQuery} from '@tanstack/react-query';
import {createContext, useContext, useEffect, useMemo, type ReactNode} from 'react';

import {sessionQuery} from '../api/queries';

const SOURCE_LOCALE = 'en';

/** Mirrors `i18n.py`'s `_RTL_LANGS` / `text_direction()`. Kept in the SPA as well as on the
 *  server because the SPA owns the <html> attributes: the server renders one shell for every
 *  locale, and `?uselang=` can change the locale without a new document. */
const RTL_LANGS = new Set([
  'ar', 'arc', 'ary', 'arz', 'azb', 'ckb', 'dv', 'fa', 'ha', 'he', 'khw', 'ks',
  'ku', 'mzn', 'nqo', 'pnb', 'ps', 'sd', 'ug', 'ur', 'yi',
]);

export function textDirection(locale: string): 'rtl' | 'ltr' {
  const base = (locale || '').split('-')[0] ?? '';
  return RTL_LANGS.has(base.toLowerCase()) ? 'rtl' : 'ltr';
}

/** Mirrors the server's own precedence in `_negotiate_locale`: ?uselang= wins, then the
 *  `uselang` cookie (deliberately not HttpOnly so the client can read it), then English.
 *
 *  Both ends must reach the same answer — the server stamps <html lang> and the pre-catalogue
 *  strings, the client picks which catalogue to fetch — so neither may consult anything the
 *  other cannot see. That is why the server has no Accept-Language step: the browser's header
 *  is not something the SPA can match against ENABLED_LOCALES, and a locale only one end can
 *  derive shows up as a document that says one language while its content is another.
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
  // Deliberately not useSuspenseQuery. The catalogue wraps every route, and a suspense
  // query that exhausts its retries with no error boundary above it leaves the whole app
  // stuck on the loading fallback forever -- observed on staging by failing this endpoint.
  // The interface must survive a missing catalogue: banana returns the key for an unknown
  // message, so a failure degrades to visible keys on the wired surfaces rather than
  // taking the product down.
  const {data: messages, isPending} = useQuery(messagesQuery(locale, session.gitVersion ?? ''));

  const msg = useMemo<Message>(() => {
    const banana = new Banana(locale, {messages: {[locale]: messages ?? {}}});
    return (key, ...params) => banana.i18n(key, ...params);
  }, [locale, messages]);

  // spec_accessibility.md: "Set `lang` (and `dir` where relevant) so screen readers pick the
  // right voice." index.html hard-codes lang="en" for the shell, and ?uselang= can change the
  // locale without a new document, so the attributes have to follow the negotiated locale
  // here. Without this a translated interface -- including every aria-label and sr-only
  // string -- is announced by an English synthesiser, which is worse than untranslated.
  useEffect(() => {
    const root = document.documentElement;
    root.lang = locale;
    root.dir = textDirection(locale);
  }, [locale]);

  // Hold the first paint until the catalogue resolves one way or the other, so wired
  // strings never flash as keys on the happy path.
  if (isPending) {
    // Not translatable by construction: the catalogue this waits for is the thing that
    // would translate it. lang is already set by the effect above, so a screen reader at
    // least announces this one English word in the right voice.
    return <p className="loading-state" role="status">Loading…</p>;
  }
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

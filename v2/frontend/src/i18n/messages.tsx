import Banana from 'banana-i18n';
import {queryOptions, useQuery, useSuspenseQuery} from '@tanstack/react-query';
import {createContext, useContext, useEffect, useMemo, type ReactNode} from 'react';

import {sessionQuery} from '../api/queries';

const SOURCE_LOCALE = 'en';
const DEBUG_LOCALE = 'qqx';   // mirrors i18n.DEBUG_LOCALE

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

/** What the reader asked for, and whether they asked explicitly.
 *
 *  This is a *request*, not the effective locale. The distinction between the two sources is
 *  load-bearing: `effectiveLocale` honours `?uselang=` verbatim but drops a remembered cookie
 *  whose locale is no longer offered, exactly as `_negotiate_locale` does.
 *
 *  It mirrors `_negotiate_locale` on the server, and must keep mirroring it: the server
 *  stamps <html lang> and the pre-catalogue strings while the client picks which catalogue to
 *  fetch, so neither end may consult anything the other cannot see. That is why the server
 *  has no Accept-Language step — the header is not something the SPA can match against
 *  ENABLED_LOCALES, and a locale only one end can derive shows up as a document that says
 *  one language while its content is another. A reader who wants a different language uses
 *  the switcher in the header, which sets both the parameter and the cookie.
 *
 *  The query parameter is not optional. `qqx` -- the QA locale that renders message keys,
 *  and the only way to see which strings are still unwrapped -- bypasses ENABLED_LOCALES
 *  and is deliberately never written to the cookie. Reading the cookie alone would leave
 *  the SPA in English for the one locale whose entire purpose is to inspect the SPA. */
/** The locale actually used: the reader's request, clamped to what the site offers.
 *
 *  `readLocale()` takes ?uselang verbatim and the server ignores a code outside
 *  ENABLED_LOCALES, so without this the two ends disagree — see MessageProvider. */
export function effectiveLocale(
  request: {code: string; explicit: boolean},
  locales: {current: string; available: {code: string}[]},
): string {
  // ?uselang= wins outright, including for a locale ENABLED_LOCALES does not list. That is
  // the inspection door — how qqx has always worked, and what lets a translator see their
  // language, or an RTL layout, before it is switched on. Untranslated messages fall back to
  // English per key, so the page renders in the requested language's direction with English
  // text, which is the familiar MediaWiki behaviour. The server honours it identically and
  // stamps the same locale, and deliberately does not remember it.
  if (request.explicit || request.code === DEBUG_LOCALE) return request.code;
  // A remembered cookie only while that locale is still offered — otherwise withdrawing one
  // leaves returning readers on it while the server, applying the same rule, stamps another.
  return locales.available.some((entry) => entry.code === request.code)
    ? request.code
    : locales.current;
}

export function localeRequest(): {code: string; explicit: boolean} {
  const requested = new URLSearchParams(window.location.search).get('uselang');
  if (requested) return {code: requested, explicit: true};
  const match = document.cookie.match(/(?:^|;\s*)uselang=([^;]+)/);
  if (match?.[1]) return {code: decodeURIComponent(match[1]), explicit: false};
  return {code: SOURCE_LOCALE, explicit: false};
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

export function MessageProvider({children, locale: override}: {children: ReactNode; locale?: string}) {
  const {data: session} = useSuspenseQuery(sessionQuery());

  // Clamp to what this site actually offers. readLocale() takes ?uselang verbatim, and the
  // server ignores a code outside ENABLED_LOCALES — so without this the two ends disagree:
  // ?uselang=he on an English-only site had the server stamp lang="en" dir="ltr" while the
  // client fetched a (fully English) "he" catalogue and set dir="rtl", mirroring the layout
  // around English text. The offered list arrives in the session payload precisely so this
  // check can be made here rather than guessed. qqx is exempt: it is the QA locale and is
  // deliberately never in ENABLED_LOCALES.
  const locale = override ?? effectiveLocale(localeRequest(), session.locales);
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

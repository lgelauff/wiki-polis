import {afterEach, expect, test} from 'vitest';

import {effectiveLocale, localeRequest} from './messages';

function setSearch(search: string) {
  window.history.replaceState({}, '', `/${search}`);
}

afterEach(() => {
  setSearch('');
  document.cookie = 'uselang=; Max-Age=0; path=/';
});

test('asks for nothing when the reader has not chosen', () => {
  // Deliberately empty rather than 'en': the resolution belongs to effectiveLocale, which
  // knows what the server negotiated. Guessing English here disagrees with a site whose
  // DEFAULT_LOCALE is something else.
  expect(localeRequest()).toEqual({code: '', explicit: false});
});

test('reads the uselang cookie the server sets', () => {
  document.cookie = 'uselang=nl; path=/';
  expect(localeRequest().code).toBe('nl');
});

test('?uselang wins over the cookie, mirroring _negotiate_locale', () => {
  document.cookie = 'uselang=nl; path=/';
  setSearch('?uselang=fr');
  expect(localeRequest().code).toBe('fr');
});

test('?uselang=qqx is honoured even though the server never persists it', () => {
  // qqx bypasses ENABLED_LOCALES and is deliberately never written to the cookie, so a
  // cookie-only read would leave the SPA in English for the one locale whose whole
  // purpose is to reveal which strings are still unwrapped.
  setSearch('?uselang=qqx');
  expect(localeRequest().code).toBe('qqx');
});

test('consults nothing only the server can see', () => {
  // Both ends must reach the same locale: the server stamps <html lang> and the
  // pre-catalogue strings, the client picks which catalogue to fetch. So this must depend on
  // nothing the server alone knows -- no Accept-Language, and nothing stamped onto the
  // document. A reader who wants another language uses the switcher, which sets ?uselang and
  // the cookie, both of which this function can see.
  document.documentElement.dataset.locale = 'nl';
  document.documentElement.lang = 'nl';
  try {
    expect(localeRequest()).toEqual({code: '', explicit: false});
  } finally {
    delete document.documentElement.dataset.locale;
    document.documentElement.lang = 'en';
  }
});

test('an explicit choice still wins, whatever the document says', () => {
  document.documentElement.lang = 'nl';
  document.cookie = 'uselang=fr; path=/';
  try {
    expect(localeRequest().code).toBe('fr');
    setSearch('?uselang=qqx');
    expect(localeRequest().code).toBe('qqx');
  } finally {
    document.documentElement.lang = 'en';
  }
});

const ENGLISH_ONLY = {current: 'en', available: [{code: 'en', name: 'English'}]};
const TWO = {
  current: 'en',
  available: [{code: 'en', name: 'English'}, {code: 'nl', name: 'Nederlands'}],
};

test('an explicit ?uselang reaches a locale the switcher does not offer', () => {
  // The inspection door. This is how qqx has always worked, and it is what lets a translator
  // see their language -- or an RTL layout -- before it is switched on. Untranslated messages
  // fall back to English per key, so the page renders in the requested direction with English
  // text, and the server stamps the same locale onto <html>.
  expect(effectiveLocale({code: 'he', explicit: true}, ENGLISH_ONLY)).toBe('he');
  expect(effectiveLocale({code: 'qqx', explicit: true}, ENGLISH_ONLY)).toBe('qqx');
});

test('a qqx cookie is not honoured, because the server refuses one', () => {
  // ?uselang=qqx works through `explicit`. A qqx *cookie* is something the server never
  // writes and would not accept, so honouring one guarantees the two ends disagree — the
  // page saying one language while every string renders as (message-key).
  expect(effectiveLocale({code: 'qqx', explicit: false}, ENGLISH_ONLY)).toBe('en');
});

test('nothing requested resolves to what the server negotiated, not to English', () => {
  // DEFAULT_LOCALE is configured independently of ENABLED_LOCALES, so guessing 'en' here
  // disagrees with a server whose default is Dutch.
  const dutchDefault = {current: 'nl', available: [{code: 'en', name: 'English'}, {code: 'nl', name: 'Nederlands'}]};
  expect(effectiveLocale({code: '', explicit: false}, dutchDefault)).toBe('nl');
});

test('a malformed locale never reaches banana, which throws on one', () => {
  // new Banana('en_US') raises, inside the provider that wraps every route and with no error
  // boundary above it — so an unfiltered ?uselang would blank the page.
  setSearch('?uselang=en_US');
  expect(localeRequest()).toEqual({code: '', explicit: false});
  setSearch('?uselang=he-IL');
  expect(localeRequest()).toEqual({code: 'he-IL', explicit: true});
});

test('an undecodable uselang cookie is treated as absent, not thrown', () => {
  // The cookie is not HttpOnly and the host shares a domain with other tools, so it may hold
  // something this app never wrote. decodeURIComponent('%') throws during render.
  document.cookie = 'uselang=%; path=/';
  expect(() => localeRequest()).not.toThrow();
  expect(localeRequest()).toEqual({code: '', explicit: false});
});

test('a remembered locale is dropped once it stops being offered', () => {
  // Otherwise withdrawing a locale strands returning readers on it, while the server --
  // applying the same rule -- stamps something else.
  expect(effectiveLocale({code: 'nl', explicit: false}, TWO)).toBe('nl');
  expect(effectiveLocale({code: 'nl', explicit: false}, ENGLISH_ONLY)).toBe('en');
});

test('localeRequest distinguishes an explicit choice from a remembered one', () => {
  document.cookie = 'uselang=nl; path=/';
  expect(localeRequest()).toEqual({code: 'nl', explicit: false});
  setSearch('?uselang=he');
  expect(localeRequest()).toEqual({code: 'he', explicit: true});
});

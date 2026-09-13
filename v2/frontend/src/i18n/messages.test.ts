import {afterEach, expect, test} from 'vitest';

import {effectiveLocale, localeRequest} from './messages';

function setSearch(search: string) {
  window.history.replaceState({}, '', `/${search}`);
}

afterEach(() => {
  setSearch('');
  document.cookie = 'uselang=; Max-Age=0; path=/';
});

test('falls back to English with no cookie and no query parameter', () => {
  expect(localeRequest().code).toBe('en');
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

test('falls back to English without consulting anything only the server can see', () => {
  // Both ends must reach the same locale: the server stamps <html lang> and the
  // pre-catalogue strings, the client picks which catalogue to fetch. So readLocale() must
  // depend on nothing the server alone knows -- no Accept-Language, and no locale stamped
  // onto the document. A reader who wants another language uses the switcher, which sets
  // ?uselang and the cookie, both of which this function can see.
  document.documentElement.dataset.locale = 'nl';
  document.documentElement.lang = 'nl';
  try {
    expect(localeRequest().code).toBe('en');
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
  expect(effectiveLocale({code: 'qqx', explicit: false}, ENGLISH_ONLY)).toBe('qqx');
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

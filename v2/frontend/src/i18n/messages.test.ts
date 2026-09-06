import {afterEach, expect, test} from 'vitest';

import {readLocale} from './messages';

function setSearch(search: string) {
  window.history.replaceState({}, '', `/${search}`);
}

afterEach(() => {
  setSearch('');
  document.cookie = 'uselang=; Max-Age=0; path=/';
});

test('falls back to English with no cookie and no query parameter', () => {
  expect(readLocale()).toBe('en');
});

test('reads the uselang cookie the server sets', () => {
  document.cookie = 'uselang=nl; path=/';
  expect(readLocale()).toBe('nl');
});

test('?uselang wins over the cookie, mirroring _negotiate_locale', () => {
  document.cookie = 'uselang=nl; path=/';
  setSearch('?uselang=fr');
  expect(readLocale()).toBe('fr');
});

test('?uselang=qqx is honoured even though the server never persists it', () => {
  // qqx bypasses ENABLED_LOCALES and is deliberately never written to the cookie, so a
  // cookie-only read would leave the SPA in English for the one locale whose whole
  // purpose is to reveal which strings are still unwrapped.
  setSearch('?uselang=qqx');
  expect(readLocale()).toBe('qqx');
});

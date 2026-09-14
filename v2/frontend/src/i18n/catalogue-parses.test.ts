/// <reference types="vite/client" />
import Banana from 'banana-i18n';
import {expect, test} from 'vitest';

/** Every catalogue file in v2/i18n, as the SPA would receive it. qqq.json is documentation. */
const files = import.meta.glob<Record<string, unknown>>('../../../i18n/*.json', {eager: true, import: 'default'});

test('every message in every catalogue file parses in banana-i18n', () => {
  // Catches a message banana cannot parse -- a stray "<", crossed tags, an unclosed {{ --
  // which shows readers the key instead of text. The server's markup check refuses such a
  // translation; this checks the renderer itself, and English, which nothing refuses.
  const failures: string[] = [];
  const locales = Object.entries(files).filter(([path]) => !path.endsWith('/qqq.json'));
  expect(locales.map(([path]) => path)).toContain('../../../i18n/en.json');
  for (const [path, messages] of locales) {
    const locale = path.split('/').pop()!.replace('.json', '');
    const strings = Object.fromEntries(Object.entries(messages).filter(([key, value]) => key !== '@metadata' && typeof value === 'string')) as Record<string, string>;
    const banana = new Banana(locale, {messages: {[locale]: strings}});
    for (const key of Object.keys(strings)) {
      try {
        banana.i18n(key, 1, 2, 3, 4, 5);
      } catch (error) {
        failures.push(`${path}: ${key}: ${(error as Error).message}`);
      }
    }
  }
  expect(failures).toEqual([]);
});

/// <reference types="vite/client" />
import Banana from 'banana-i18n';
import {expect, test} from 'vitest';

import {createMessage} from './messages';

/** Every catalogue file in v2/i18n, as the SPA would receive it. qqq.json is documentation. */
const files = import.meta.glob<Record<string, unknown>>('../../../i18n/*.json', {eager: true, import: 'default'});

test('every message in every catalogue file renders in banana-i18n', () => {
  // Catches a message banana cannot parse (a stray "<", an unclosed {{, a "$" that is not a
  // placeholder), which shows readers the key instead of text, and one it renders as
  // "undefined" (an empty or explicit-only plural branch). Rendered with counts 0, 1 and 2 so
  // each plural path runs, as strings, which is how msg() passes them. The server's markup
  // check refuses such a translation; this checks the renderer itself, and English, which
  // nothing refuses.
  const failures: string[] = [];
  const locales = Object.entries(files).filter(([path]) => !path.endsWith('/qqq.json'));
  expect(locales.map(([path]) => path)).toContain('../../../i18n/en.json');
  for (const [path, messages] of locales) {
    const locale = path.split('/').pop()!.replace('.json', '');
    const strings = Object.fromEntries(Object.entries(messages).filter(([key, value]) => key !== '@metadata' && typeof value === 'string')) as Record<string, string>;
    let banana: Banana;
    try {
      banana = new Banana(locale, {messages: {[locale]: strings}, wikilinks: false});
    } catch (error) {
      failures.push(`${path}: locale rejected: ${(error as Error).message}`);
      continue;
    }
    for (const [key, text] of Object.entries(strings)) {
      for (const count of ['0', '1', '2']) {
        try {
          const rendered = banana.i18n(key, count, 'p2', 'p3', 'p4', 'p5');
          if (rendered.includes('undefined') && !text.includes('undefined')) failures.push(`${path}: ${key}: renders "undefined"`);
        } catch (error) {
          failures.push(`${path}: ${key}: ${(error as Error).message}`);
          break;
        }
      }
    }
  }
  expect(failures).toEqual([]);
});

test('link syntax in a message stays text, inside a plural branch too', () => {
  // Catches wikilinks being switched on in msg(): the server's markup check does not model
  // link syntax, so it would be the one way to turn a translation into an <a>.
  const render = createMessage('nl', {
    bare: '[https://evil.example x]',
    plural: '{{PLURAL:$1|[javascript:alert(1) x]|[[Special:Foo|y]]}}',
  });
  expect(render('bare')).not.toContain('<a');
  expect(render('plural', 1)).not.toContain('<a');
  expect(render('plural', 2)).not.toContain('<a');
});

test('a plural form that is only a placeholder shows 0 for a count of 0', () => {
  // Catches msg() passing numbers to banana, which renders "undefined" for this form at 0.
  // Counts reach msg() as numbers from most call sites.
  expect(createMessage('nl', {k: '{{PLURAL:$1|1=een stem|$1}}'})('k', 0)).toBe('0');
});

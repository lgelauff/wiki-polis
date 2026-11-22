import {expect, test, vi} from 'vitest';
import fixture from './text-rules-cases.json';
import {cleanText, countCharacters, fitsLimit} from './text-rules';

type Case = {name: string; input: string; clean: string; characters: number; fits: boolean;
  repeat?: number; append?: string};

// The same file drives tests/test_text_rules.py, so browser and server agree (#616).
const cases = fixture.cases as Case[];

function expand(item: Case, value: string) {
  if (item.append !== undefined) return value + item.append.repeat(item.repeat ?? 1);
  return value.repeat(item.repeat ?? 1);
}

test.each(cases.map((item) => [item.name, item] as const))('%s', (_name, item) => {
  const input = expand(item, item.input);
  expect(cleanText(input)).toBe(expand(item, item.clean));
  expect(countCharacters(input)).toBe(item.characters);
  expect(fitsLimit(input)).toBe(item.fits);
});

test('text is never HTML-escaped', () => {
  expect(cleanText('<a href="x">&amp;</a>')).toBe('<a href="x">&amp;</a>');
});

test('without Intl.Segmenter the module still loads and counts code points (Firefox < 125)', async () => {
  vi.resetModules();
  vi.stubGlobal('Intl', {...Intl, Segmenter: undefined});
  try {
    const rules = await import('./text-rules');
    expect(rules.countCharacters('caf\u00e9 \u{1F1F3}\u{1F1F1}')).toBe(7);
    expect(rules.fitsLimit('x'.repeat(280))).toBe(true);
  } finally {
    vi.unstubAllGlobals();
    vi.resetModules();
  }
});

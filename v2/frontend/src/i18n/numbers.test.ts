import {expect, test} from 'vitest';

import {formatPercent} from './numbers';

test('a percentage follows the chosen interface language, not the runtime default', () => {
  expect(formatPercent('nl', 62.5)).toBe('62,5%');
  expect(formatPercent('en', 62.5)).toBe('62.5%');
  // Where the sign goes, and the space before it, is the locale's to decide. Which
  // no-break space French uses depends on the ICU version, so any will do.
  expect(formatPercent('fr', 62.5)).toMatch(/^62,5\s%$/);
  expect(formatPercent('tr', 62.5)).toBe('%62,5');
});

test('one decimal by default, fixed, so a column of them lines up', () => {
  expect(formatPercent('en', 60)).toBe('60.0%');
  expect(formatPercent('en', 82, {digits: 0})).toBe('82%');
});

test('a shift carries its sign, and no change carries none', () => {
  expect(formatPercent('nl', 7.5, {signed: true})).toBe('+7,5%');
  expect(formatPercent('nl', -2.5, {signed: true})).toBe('-2,5%');
  expect(formatPercent('nl', 0, {signed: true})).toBe('0,0%');
});

test('qqx formats like the source language rather than like the machine running it', () => {
  expect(formatPercent('qqx', 62.5)).toBe(formatPercent('en', 62.5));
});

test('a tag Intl rejects degrades to the source language instead of throwing in render', () => {
  expect(formatPercent('not a locale!', 62.5)).toBe('62.5%');
});

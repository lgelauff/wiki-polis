import {expect, test} from 'vitest';

import {formatDate, formatDateTime, formatMonthYear} from './dates';

test('dates follow the chosen interface language, not the runtime default', () => {
  // The runtime here is en-US; neither of these may come out US-shaped.
  expect(formatDate('nl', '2026-09-01T10:00:00Z')).toBe('1 sep 2026');
  expect(formatMonthYear('de', '2026-03-15T10:00:00Z')).toBe('März 2026');
});

test('English is the source language, and it is written day-first', () => {
  expect(formatDate('en', '2026-09-01T10:00:00Z')).toBe('1 Sept 2026');
  expect(formatDateTime('en', '2026-08-02T09:30:00Z')).toBe('2 Aug 2026, 09:30');
});

test('qqx formats like the source language rather than like the machine running it', () => {
  expect(formatDate('qqx', '2026-09-01T10:00:00Z')).toBe(formatDate('en', '2026-09-01T10:00:00Z'));
});

test('a calendar date is taken in UTC, so a late close stays on its own day', () => {
  expect(formatDate('en', '2026-08-31T23:30:00Z')).toBe('31 Aug 2026');
  expect(formatMonthYear('en', '2026-08-31T23:30:00Z')).toBe('Aug 2026');
});

test('a tag Intl rejects degrades to the source language instead of throwing in render', () => {
  expect(formatDate('not a locale!', '2026-09-01T10:00:00Z')).toBe('1 Sept 2026');
});

test('a value that is not a date is shown as it came, not thrown on in render', () => {
  expect(formatDate('en', 'not-a-date')).toBe('not-a-date');
  expect(formatDateTime('nl', '')).toBe('');
});

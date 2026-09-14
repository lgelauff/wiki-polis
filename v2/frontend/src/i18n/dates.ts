import {useMemo} from 'react';

import {useLocale} from './messages';

/** Dates follow the interface language the reader chose, not their browser.
 *
 *  `Intl.DateTimeFormat(undefined, …)` would format with the browser's locale. Formatting
 *  with the chosen locale keeps dates consistent with the words around them — a date is often
 *  a parameter inside a translated sentence.
 *
 *  Locales that are not what Intl should be handed:
 *  - `en` is Proto's source language, written to British conventions ("licence",
 *    "catalogue"), and formats dates day-first. Plain `en` in Intl is US English.
 *  - `qqx` is the QA locale. It has no CLDR data, so Intl would silently use the runtime's
 *    default and the page would vary by machine; pin it to the source language instead. */
const INTL_LOCALE: Record<string, string> = {
  en: 'en-GB',
  qqx: 'en-GB',
};

/** A value that is not a date is shown as it came rather than thrown on: formatting runs in
 *  render, and a RangeError there blanks the page for one malformed timestamp. */
function format(locale: string, options: Intl.DateTimeFormatOptions, value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : formatter(locale, options).format(date);
}

function formatter(locale: string, options: Intl.DateTimeFormatOptions) {
  const tag = Object.hasOwn(INTL_LOCALE, locale) ? INTL_LOCALE[locale] : locale;
  try {
    return new Intl.DateTimeFormat(tag || 'en-GB', options);
  } catch {
    // A tag Intl rejects must not blank the page: this runs in render. The gate in
    // messages.tsx makes it unlikely, as it does for banana; this makes it unreachable.
    return new Intl.DateTimeFormat('en-GB', options);
  }
}

/** A calendar date, "1 Sept 2026". In UTC: these mark the day a consultation closed or a
 *  window opens, which must not move a day depending on where the reader is. */
export function formatDate(locale: string, value: string): string {
  return format(locale, {day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC'}, value);
}

/** Month and year, "Aug 2026". In UTC, for the same reason as formatDate. */
export function formatMonthYear(locale: string, value: string): string {
  return format(locale, {month: 'short', year: 'numeric', timeZone: 'UTC'}, value);
}

/** A moment, "2 Aug 2026, 09:30", in the reader's own timezone: a scheduled phase change
 *  happens at a time of day, and the reader needs it where they are. */
export function formatDateTime(locale: string, value: string): string {
  return format(locale, {dateStyle: 'medium', timeStyle: 'short'}, value);
}

export function useDateFormat() {
  const locale = useLocale();
  return useMemo(() => ({
    date: (value: string) => formatDate(locale, value),
    monthYear: (value: string) => formatMonthYear(locale, value),
    dateTime: (value: string) => formatDateTime(locale, value),
  }), [locale]);
}

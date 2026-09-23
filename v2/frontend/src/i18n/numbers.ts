import {useMemo} from 'react';

import {intlLocale} from './dates';
import {useLocale} from './messages';

/** Percentages follow the interface language the reader chose, as dates do (see dates.ts for
 *  why `en` and `qqx` are pinned). `toFixed` always writes an English decimal point, so Dutch
 *  would read "62.5%" where it writes "62,5%".
 *
 *  The formatted number carries its own `%` sign: where it goes, and whether a space comes
 *  before it, is the locale's to decide ("62,5 %" in French, "%62,5" in Turkish), so the
 *  messages these are passed into leave it out. */
function formatter(locale: string, options: Intl.NumberFormatOptions) {
  try {
    return new Intl.NumberFormat(intlLocale(locale), options);
  } catch {
    // A tag Intl rejects must not blank the page: this runs in render.
    return new Intl.NumberFormat('en-GB', options);
  }
}

/** A percentage given out of 100: "62.5%" in English, "62,5%" in Dutch. `digits` is the fixed
 *  number of decimals, one by default. `signed` writes a plus on a gain, for a shift. */
export function formatPercent(locale: string, value: number, {digits = 1, signed = false} = {}): string {
  return formatter(locale, {
    style: 'percent',
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
    signDisplay: signed ? 'exceptZero' : 'auto',
  }).format(value / 100);
}

export function usePercentFormat() {
  const locale = useLocale();
  return useMemo(() => (value: number, options?: {digits?: number; signed?: boolean}) =>
    formatPercent(locale, value, options), [locale]);
}

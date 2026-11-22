/** The browser half of the text rule in v2/services/text_rules.py (#616).
 *
 *  A character is what a reader sees as one (an extended grapheme cluster), counted after
 *  the same cleaning the server does, so the counter beside a text box agrees with the
 *  server's check. The server has the final say; this only advises. Both sides are tested
 *  against text-rules-cases.json. Text is never escaped here: React escapes it when it
 *  renders it. */

export const MAX_CHARACTERS = 280;
export const STORAGE_CODE_POINTS = 1000;
export const MAX_CLUSTER_CODE_POINTS = 30;

// CRLF, CR, VT, FF, NEL and U+2028/2029 become a newline, as on the server.
const LINE_BREAK = /\r\n|[\r\u000b\u000c\u0085\u2028\u2029]/g;
// C0 except tab and line breaks, DEL, C1 except NEL, U+FEFF, bidi embeddings/overrides/
// isolates, lone surrogates and noncharacters: the same set as _REMOVED on the server.
const REMOVED = /[\u0000-\u0008\u000e-\u001f\u007f-\u0084\u0086-\u009f\ufeff\u202a-\u202e\u2066-\u2069\ufdd0-\ufdef\ufffe\uffff]|[\ud800-\udbff](?![\udc00-\udfff])|(?<![\ud800-\udbff])[\udc00-\udfff]|[\ud83f\ud87f\ud8bf\ud8ff\ud93f\ud97f\ud9bf\ud9ff\uda3f\uda7f\udabf\udaff\udb3f\udb7f\udbbf\udbff][\udffe\udfff]/g;

// Firefox before 125 has no Intl.Segmenter: count code points there. That only over-counts
// (the server stays the judge), and the page still loads.
const segmenter = typeof Intl.Segmenter === 'function'
  ? new Intl.Segmenter(undefined, {granularity: 'grapheme'})
  : null;

/** The text as the server stores it: line breaks unified, invisible and disguising
 *  characters removed, NFC, outer whitespace stripped. */
export function cleanText(value: string): string {
  return value.replace(LINE_BREAK, '\n').replace(REMOVED, '').normalize('NFC').trim();
}

function clusters(text: string): string[] {
  if (!segmenter) return Array.from(text);
  return Array.from(segmenter.segment(text), (part) => part.segment);
}

/** Characters as displayed in what the server would store for `value`. */
export function countCharacters(value: string): number {
  return clusters(cleanText(value)).length;
}

/** True when the server would accept `value` under a `maxCharacters` limit. */
export function fitsLimit(value: string, maxCharacters = MAX_CHARACTERS): boolean {
  const text = cleanText(value);
  if (!text || Array.from(text).length > STORAGE_CODE_POINTS) return false;
  const parts = clusters(text);
  return parts.length <= maxCharacters
    && parts.every((part) => Array.from(part).length <= MAX_CLUSTER_CODE_POINTS);
}

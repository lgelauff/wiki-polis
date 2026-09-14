import {testMessages} from './handlers';

/** Test support for proving a surface is wired to the catalogue.
 *
 *  Asserting English text cannot prove that: the test catalogue is the real en.json, so a
 *  hardcoded literal and msg() of the same words render identically and the test passes
 *  either way. Under `?uselang=qqx` every message renders as `(key)`, or `(key: a, b)` with
 *  the values passed into it, and whatever English is left on screen was never wired —
 *  including English passed into a message as a parameter. This is the README's manual
 *  coverage check, made into an assertion. */

/** An opening `(key` or `(key:`, for a key the catalogue has; the values after it stay in the
 *  text and are checked like any other. */
const KEY_OPENING = /\(([a-z0-9][a-z0-9._-]*)(?::|(?=\)))/g;
const KNOWN_KEYS = new Set(Object.keys(testMessages));

/** The attributes a reader meets: announced by a screen reader, or shown on hover. */
const READABLE_ATTRIBUTES = ['aria-label', 'aria-valuetext', 'alt', 'title', 'placeholder'];

/** Serve the page as `?uselang=qqx`. MemoryRouter never touches window.location, which is
 *  what the message provider reads. setup.ts resets it after every test. */
export function renderAsQqx() {
  globalThis.history.replaceState(null, '', '/?uselang=qqx');
}

/** Text and readable attributes under `root` that still contain a word once every message key
 *  and every piece of `content` is removed. `content` is what the fixture supplied — titles,
 *  pseudonyms, statements — which is participant data and must never be keyed.
 *
 *  Hidden elements are included on purpose: text behind `hidden` or a closed <details> is
 *  still copy a participant reaches. */
export function untranslatedCopy(roots: Array<Element | null>, content: readonly string[] = []): string[] {
  const found: string[] = [];
  const check = (raw: string | null, where: string) => {
    if (!raw) return;
    let rest = raw.replace(KEY_OPENING, (match, key: string) => (KNOWN_KEYS.has(key) ? ' ' : match));
    // Longest first, so a title is not half-consumed by a shorter value inside it.
    for (const value of [...content].sort((a, b) => b.length - a.length)) rest = rest.split(value).join(' ');
    if (/\p{L}{2,}/u.test(rest)) found.push(`${where}: ${JSON.stringify(raw.trim())}`);
  };
  for (const root of roots) {
    if (!root) throw new Error('untranslatedCopy: a root element was not found');
    const walker = root.ownerDocument.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      check(node.nodeValue, `text in <${node.parentElement?.tagName.toLowerCase()}>`);
    }
    for (const element of [root, ...root.querySelectorAll('*')]) {
      for (const name of READABLE_ATTRIBUTES) check(element.getAttribute(name), `${name} on <${element.tagName.toLowerCase()}>`);
    }
  }
  return found;
}

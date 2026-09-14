/** Some catalogue messages carry inline markup that is part of the sentence — a bolded
 *  lead-in, an <em> contrast, a <code> path. Splitting them into fragments at the tag
 *  would leave translators with pieces they cannot reorder, so they are rendered as HTML
 *  instead.
 *
 *  The source is v2/i18n/*.json. English is ours; translations are typed by translatewiki
 *  volunteers and are not trusted markup. banana-i18n does not sanitise them — it lets a
 *  self-closing tag keep its attributes and passes anything inside {{PLURAL:}} through.
 *  What makes this sink safe is the server: i18n.load() refuses any translation using
 *  markup its English does not, and tests/test_i18n.py fails CI on one. Do not render
 *  catalogue text that did not come through GET /api/v1/i18n/<locale>. */
export function richHtml(text: string) {
  return {__html: text};
}

/** Parameters substituted into those messages are *not* catalogue-controlled: they are
 *  consultation titles, pseudonyms and dates. banana-i18n interpolates them verbatim, so
 *  they are escaped before reaching innerHTML. */
export function escapeHtml(value: string) {
  return value.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;');
}

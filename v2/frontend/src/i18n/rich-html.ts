/** Some catalogue messages carry inline markup that is part of the sentence — a bolded
 *  lead-in, an <em> contrast, a <code> path. Splitting them into fragments at the tag
 *  would leave translators with pieces they cannot reorder, so they are rendered as HTML
 *  instead. The source is v2/i18n/*.json — repo- and translatewiki-controlled, never
 *  participant input. */
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

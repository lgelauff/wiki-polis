/**
 * One "Also coming" line: functionality that is planned but not built, said once in prose
 * instead of mimed with a control that does nothing.
 *
 * Every console page writes these lines through this one component, so they all read
 * "Also coming: … — not available yet (#N)", carry the same muted class, and are marked as
 * English. A page puts them last, after everything that works.
 *
 * Hardcoded English on purpose: a placeholder for unshipped functionality gets no message
 * key and no qqq entry, so translators are not asked to carry a string that leaves again
 * when the functionality lands.
 */
export function AdminComing({what, issue}: {what: string; issue?: number}) {
  const text = `Also coming: ${what} — not available yet${issue ? ` (#${issue})` : ''}`;
  return <p className="admin-shell__coming" lang="en">{text}</p>;
}

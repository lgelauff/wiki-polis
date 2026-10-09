/** The rows a "Based on" sort orders: a statement, and the statement it was derived from. */
type Lineage = {id: number; provenance: {derivedFromId: number} | null};

/**
 * "Based on" is lineage: a derived statement sits directly under the statement it
 * corrects, and a correction of that correction under it in turn, so a whole line of
 * corrections is read together. Roots keep the order they arrived in. The Moderation
 * queue and the Content statement list both sort with this one function, so the option
 * means the same on both pages; it sorts what is already loaded and refetches nothing.
 *
 * A derived statement whose source is not in the same list is treated as a root: the
 * grouping has nothing to attach it to, and hiding it would take a statement off the list.
 */
export function sortByBasedOn<Row extends Lineage>(rows: readonly Row[]): Row[] {
  const byId = [...rows].sort((left, right) => left.id - right.id);
  const shown = new Set(byId.map((row) => row.id));
  const children = new Map<number, Row[]>();
  const roots: Row[] = [];
  for (const row of byId) {
    const source = row.provenance?.derivedFromId;
    if (source !== undefined && source !== row.id && shown.has(source)) {
      children.set(source, [...(children.get(source) ?? []), row]);
    } else {
      roots.push(row);
    }
  }
  const placed = new Set<number>();
  const out: Row[] = [];
  const place = (row: Row) => {
    if (placed.has(row.id)) return;
    placed.add(row.id);
    out.push(row);
    for (const child of children.get(row.id) ?? []) place(child);
  };
  roots.forEach(place);
  // Statements that derive from each other in a circle have no root to hang from; they
  // still belong on the list.
  byId.forEach(place);
  return out;
}

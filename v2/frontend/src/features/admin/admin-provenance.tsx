import type {components} from '../../api/schema';
import {useMessage} from '../../i18n/messages';

type Provenance = NonNullable<components['schemas']['AdminStatement']['provenance']>;

/** Where a derived statement came from, the same on Content › Statements and Moderation ›
 *  Featured: "↳ #N", then each similarity score, as muted text with what it means on hover.
 *  `linked` makes "↳ #N" a jump to the source's row (`#statement-N`) when that row is on
 *  screen; otherwise there is nothing to jump to and it is text. */
export function StatementProvenance({provenance, linked = false}: {provenance: Provenance; linked?: boolean}) {
  const msg = useMessage();
  const id = provenance.derivedFromId;
  // The model names and scores are data, not copy.
  const title = msg('admin-provenance-title', id)
    + provenance.scores.map((score) => ` ${score.model} ${score.value.toFixed(2)}.`).join('');
  const marker = (
    <>
      <span className="sr-only">{msg('admin-provenance-aria', id)}</span>
      <span aria-hidden="true">{`↳ #${id}`}</span>
    </>
  );
  return (
    <span className="admin-row__source" title={title}>
      {' '}
      {linked ? <a href={`#statement-${id}`}>{marker}</a> : marker}
      {provenance.scores.map((score) => (
        <span key={score.model}> · {score.model}&nbsp;{score.value.toFixed(2)}</span>
      ))}
    </span>
  );
}

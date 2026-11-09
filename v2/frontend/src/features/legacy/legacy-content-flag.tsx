import {useEffect, useId, useLayoutEffect, useRef, useState, type CSSProperties} from 'react';
import {useMutation} from '@tanstack/react-query';

import type {components} from '../../api/schema';
import {createContentFlag} from '../../api/queries';
import {useMessage} from '../../i18n/messages';

type ContentType = components['schemas']['CreateContentFlagRequest']['contentType'];

// Matches the panel's width in static/style.css (.content-flag form, .content-flag-thanks).
const PANEL_WIDTH = 220;
const EDGE_GAP = 8;

// The edges the panel must stay inside: the nearest ancestor that clips its overflow
// (the arguments tab's panel does), or else the viewport.
function clipBounds(from: HTMLElement): {left: number; right: number} {
  for (let el = from.parentElement; el; el = el.parentElement) {
    const {overflow, overflowX} = getComputedStyle(el);
    // The shorthand's first value is the x axis; read both, as jsdom fills in only one.
    if ([overflowX, overflow.split(' ')[0]].some((value) => value && value !== 'visible')) {
      const rect = el.getBoundingClientRect();
      return {left: rect.left, right: rect.right};
    }
  }
  return {left: 0, right: document.documentElement.clientWidth};
}

type Placement = {opensRight: boolean; width?: number};

// The panel opens leftward from the trigger. A trigger near the left of its card (an
// argument's flag) would push it past the card's edge, where it is cut off (#254): open
// toward the side with more room, and narrow the panel when neither side has its width.
// Measured on the trigger, so it works in either text direction.
function placement(details: HTMLElement): Placement {
  const trigger = details.getBoundingClientRect();
  const bounds = clipBounds(details);
  const roomLeftward = trigger.right - bounds.left;
  const roomRightward = bounds.right - trigger.left;
  if (roomLeftward >= PANEL_WIDTH) return {opensRight: false};
  const opensRight = roomRightward > roomLeftward;
  const room = opensRight ? roomRightward : roomLeftward;
  return room >= PANEL_WIDTH ? {opensRight} : {opensRight, width: Math.max(room - EDGE_GAP, 0)};
}

export function LegacyContentFlag({slug, target, csrfToken, corner = false}: {
  slug: string;
  target: Pick<components['schemas']['CreateContentFlagRequest'], 'contentType' | 'targetId'>;
  csrfToken: string;
  corner?: boolean;
}) {
  const msg = useMessage();
  const detailsRef = useRef<HTMLDetailsElement>(null);
  const fieldId = useId().replaceAll(':', '');
  const [category, setCategory] = useState<'personal_attack' | 'privacy' | 'off_topic' | 'other'>('personal_attack');
  const [detail, setDetail] = useState('');
  const [open, setOpen] = useState(false);
  const [place, setPlace] = useState<Placement>({opensRight: false});
  useLayoutEffect(() => {
    const details = detailsRef.current;
    setPlace(open && details ? placement(details) : {opensRight: false});
  }, [open]);
  // Keyed by every content type, so a new one fails to compile until it has its own label.
  const triggerLabel: Record<ContentType, string> = {
    statement: msg('conv-flag-aria-statement'),
    argument: msg('conv-flag-aria-argument'),
  };
  const mutation = useMutation({
    mutationFn: () => createContentFlag(slug, {
      ...target, category,
      ...(detail.trim() ? {detail: detail.trim()} : {}),
    }, csrfToken),
  });
  useEffect(() => {
    if (!mutation.data) return;
    const timeout = globalThis.setTimeout(() => {
      if (detailsRef.current) detailsRef.current.open = false;
      setDetail('');
      mutation.reset();
    }, 2200);
    return () => globalThis.clearTimeout(timeout);
  }, [mutation.data, mutation.reset]);
  return (
    <details ref={detailsRef} className={`content-flag${corner ? ' content-flag--corner' : ''}${place.opensRight ? ' content-flag--opens-right' : ''}`} style={place.width === undefined ? undefined : {'--content-flag-width': `${place.width}px`} as CSSProperties} onToggle={(event) => setOpen(event.currentTarget.open)}>
      <summary className="content-flag-trigger" aria-label={triggerLabel[target.contentType]} title={triggerLabel[target.contentType]}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M4 21V4a1 1 0 0 1 1-1h11.5a1 1 0 0 1 .8 1.6L14 9l3.3 4.4a1 1 0 0 1-.8 1.6H5" /></svg>
      </summary>
      <form hidden={Boolean(mutation.data)} onSubmit={(event) => { event.preventDefault(); mutation.mutate(); }}>
        <label className="sr-only" htmlFor={`${fieldId}-category`}>{msg('conv-flag-reason-label')}</label>
        <select id={`${fieldId}-category`} name="category" required value={category} onChange={(event) => setCategory(event.target.value as typeof category)}>
          <option value="personal_attack">{msg('conv-flag-cat-personal')}</option><option value="privacy">{msg('conv-flag-cat-privacy')}</option><option value="off_topic">{msg('conv-flag-cat-offtopic')}</option><option value="other">{msg('conv-flag-cat-other')}</option>
        </select>
        <label className="sr-only" htmlFor={`${fieldId}-detail`}>{msg('conv-flag-details-label')}</label>
        <textarea id={`${fieldId}-detail`} name="detail" rows={2} maxLength={1000} required={category === 'other'} placeholder={category === 'other' ? msg('conv-flag-details-required-placeholder') : msg('conv-flag-details-placeholder')} value={detail} onChange={(event) => setDetail(event.target.value)} />
        <button type="submit" className="btn-small" disabled={mutation.isPending}>{msg('conv-flag-send')}</button>
      </form>
      {mutation.data && <p className="content-flag-thanks" role="status">{msg('conv-flag-thanks')}</p>}
    </details>
  );
}

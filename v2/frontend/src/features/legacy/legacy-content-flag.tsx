import {useEffect, useId, useRef, useState} from 'react';
import {useMutation} from '@tanstack/react-query';

import type {components} from '../../api/schema';
import {createContentFlag} from '../../api/queries';

export function LegacyContentFlag({slug, target, label, csrfToken, corner = false}: {
  slug: string;
  target: Pick<components['schemas']['CreateContentFlagRequest'], 'contentType' | 'targetId'>;
  label: string;
  csrfToken: string;
  corner?: boolean;
}) {
  const detailsRef = useRef<HTMLDetailsElement>(null);
  const fieldId = useId().replaceAll(':', '');
  const [category, setCategory] = useState<'personal_attack' | 'privacy' | 'off_topic' | 'other'>('personal_attack');
  const [detail, setDetail] = useState('');
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
    <details ref={detailsRef} className={`content-flag${corner ? ' content-flag--corner' : ''}`}>
      <summary className="content-flag-trigger" aria-label={`Flag ${label} for moderator review`}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M4 21V4a1 1 0 0 1 1-1h11.5a1 1 0 0 1 .8 1.6L14 9l3.3 4.4a1 1 0 0 1-.8 1.6H5" /></svg>
      </summary>
      <form hidden={Boolean(mutation.data)} onSubmit={(event) => { event.preventDefault(); mutation.mutate(); }}>
        <label className="sr-only" htmlFor={`${fieldId}-category`}>Reason</label>
        <select id={`${fieldId}-category`} name="category" required value={category} onChange={(event) => setCategory(event.target.value as typeof category)}>
          <option value="personal_attack">Personal attack</option><option value="privacy">Privacy violation</option><option value="off_topic">Off-topic</option><option value="other">Other</option>
        </select>
        <label className="sr-only" htmlFor={`${fieldId}-detail`}>Details</label>
        <textarea id={`${fieldId}-detail`} name="detail" rows={2} maxLength={1000} required={category === 'other'} placeholder={category === 'other' ? 'Please explain this reason' : 'Optional details'} value={detail} onChange={(event) => setDetail(event.target.value)} />
        <button type="submit" className="btn-small" disabled={mutation.isPending}>Send</button>
      </form>
      {mutation.data && <p className="content-flag-thanks" role="status">Thanks for reporting — we'll take a look.</p>}
    </details>
  );
}

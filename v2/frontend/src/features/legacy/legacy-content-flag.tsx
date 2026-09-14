import {useEffect, useId, useRef, useState} from 'react';
import {useMutation} from '@tanstack/react-query';

import type {components} from '../../api/schema';
import {createContentFlag} from '../../api/queries';
import {useMessage} from '../../i18n/messages';

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
      <summary className="content-flag-trigger" aria-label={target.contentType === 'argument' ? msg('conv-flag-aria-argument') : msg('conv-flag-aria-statement')}>
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

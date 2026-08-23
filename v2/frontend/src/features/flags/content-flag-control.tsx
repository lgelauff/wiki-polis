import {useEffect, useRef, useState, type FormEvent} from 'react';
import {useMutation} from '@tanstack/react-query';

import {createContentFlag} from '../../api/queries';
import type {components} from '../../api/schema';

type FlagTarget = Pick<
  components['schemas']['CreateContentFlagRequest'],
  'contentType' | 'targetId'
>;
type FlagCategory = components['schemas']['CreateContentFlagRequest']['category'];

const reasons: ReadonlyArray<{value: FlagCategory; label: string}> = [
  {value: 'personal_attack', label: 'Personal attack'},
  {value: 'privacy', label: 'Privacy violation'},
  {value: 'off_topic', label: 'Off-topic'},
  {value: 'other', label: 'Other'},
];

export function ContentFlagControl({
  slug,
  csrfToken,
  target,
  targetLabel,
}: {
  slug: string;
  csrfToken: string;
  target: FlagTarget;
  targetLabel: string;
}) {
  const [open, setOpen] = useState(false);
  const [category, setCategory] = useState<FlagCategory>('personal_attack');
  const [detail, setDetail] = useState('');
  const triggerRef = useRef<HTMLButtonElement>(null);
  const dialogRef = useRef<HTMLDialogElement>(null);
  const supportsModalDialog = (
    typeof globalThis.HTMLDialogElement !== 'undefined'
    && typeof globalThis.HTMLDialogElement.prototype.showModal === 'function'
  );
  const mutation = useMutation({
    mutationFn: () => createContentFlag(slug, {
      ...target,
      category,
      ...(detail.trim() ? {detail: detail.trim()} : {}),
    }, csrfToken),
  });

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!open || !dialog || dialog.open) return;
    if (typeof dialog.showModal === 'function') dialog.showModal();
  }, [open]);

  function close() {
    const dialog = dialogRef.current;
    if (dialog?.open && typeof dialog.close === 'function') dialog.close();
    setOpen(false);
    mutation.reset();
    queueMicrotask(() => triggerRef.current?.focus());
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    mutation.mutate();
  }

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        className="flag-trigger"
        onClick={() => setOpen(true)}
        aria-haspopup="dialog"
      >
        Report concern
      </button>
      {open && (
        <dialog
          ref={dialogRef}
          className="flag-dialog"
          aria-labelledby="flag-dialog-title"
          aria-modal="true"
          open={supportsModalDialog ? undefined : true}
          onCancel={(event) => {
            event.preventDefault();
            close();
          }}
        >
          {mutation.data ? (
            <div className="flag-dialog__receipt" role="status">
              <p className="eyebrow">Sent for review</p>
              <h2 id="flag-dialog-title">Thank you for raising this concern.</h2>
              <p>
                {mutation.data.created
                  ? 'A moderator can now review it.'
                  : 'Your matching concern was already waiting for review.'}
              </p>
              <button type="button" className="flag-submit" onClick={close}>Done</button>
            </div>
          ) : (
            <form onSubmit={submit}>
              <div className="flag-dialog__heading">
                <div>
                  <p className="eyebrow">Moderator review</p>
                  <h2 id="flag-dialog-title">Report a concern</h2>
                </div>
                <button type="button" className="flag-close" onClick={close} aria-label="Close report dialog">×</button>
              </div>
              <blockquote>{targetLabel}</blockquote>
              <label htmlFor="flag-category">Reason</label>
              <select
                id="flag-category"
                value={category}
                onChange={(event) => {
                  setCategory(event.target.value as FlagCategory);
                  mutation.reset();
                }}
              >
                {reasons.map((reason) => (
                  <option key={reason.value} value={reason.value}>{reason.label}</option>
                ))}
              </select>
              <label htmlFor="flag-detail">
                Details {category === 'other' ? '(required)' : '(optional)'}
              </label>
              <textarea
                id="flag-detail"
                value={detail}
                rows={4}
                maxLength={1000}
                required={category === 'other'}
                onChange={(event) => {
                  setDetail(event.target.value);
                  mutation.reset();
                }}
                placeholder="Describe what a moderator should review"
              />
              <p className="flag-dialog__privacy">
                This sends a private review request. It does not remove the content immediately.
              </p>
              {mutation.error && <p className="command-error" role="alert">{mutation.error.message}</p>}
              <div className="flag-dialog__actions">
                <button type="button" className="composer-link" onClick={close}>Cancel</button>
                <button
                  type="submit"
                  className="flag-submit"
                  disabled={mutation.isPending || (category === 'other' && !detail.trim())}
                >
                  {mutation.isPending ? 'Sending…' : 'Send for review'}
                </button>
              </div>
            </form>
          )}
        </dialog>
      )}
    </>
  );
}

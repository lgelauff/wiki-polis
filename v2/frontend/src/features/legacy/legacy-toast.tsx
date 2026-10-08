import {useEffect} from 'react';

import {useMessage} from '../../i18n/messages';
import {useAnnounce} from '../admin/admin-announcer';

export type LegacyToastMessage = {
  id: number;
  category: 'error' | 'import_result' | 'import_row_error' | 'info' | 'success' | 'warning';
  message: string;
};

const durations = {
  error: 8_000,
  warning: 6_000,
  success: 4_000,
  info: 5_000,
  import_result: 6_000,
  import_row_error: 6_000,
} as const;

export function LegacyToast({
  toast,
  onDismiss,
}: {
  toast: LegacyToastMessage | null;
  onDismiss: () => void;
}) {
  const msg = useMessage();
  // Inside the admin console the shell's always-mounted region reads the toast out, once per
  // toast id -- so a second identical message is read again, which a role on an element
  // created together with its text does not reliably do. Elsewhere the toast keeps its role.
  const announce = useAnnounce();
  useEffect(() => {
    if (!toast) return undefined;
    const timer = window.setTimeout(onDismiss, durations[toast.category]);
    return () => window.clearTimeout(timer);
  }, [onDismiss, toast]);
  const urgent = toast ? toast.category === 'error' || toast.category === 'warning' : false;
  const toastId = toast?.id;
  const toastText = toast?.message;
  useEffect(() => {
    if (announce && toastId !== undefined && toastText) announce(toastText, urgent ? 'assertive' : 'polite');
  }, [announce, toastId, toastText, urgent]);

  if (!toast) return null;
  const role = announce ? undefined : urgent ? 'alert' : 'status';
  return (
    <div className={`toast toast--${toast.category}`} role={role}>
      <span className="toast__msg">{toast.message}</span>
      <button className="toast__close" type="button" aria-label={msg('base-dismiss')} onClick={onDismiss}>×</button>
    </div>
  );
}

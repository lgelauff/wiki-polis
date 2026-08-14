import {useEffect} from 'react';

export type LegacyToastMessage = {
  id: number;
  category: 'error' | 'info' | 'success' | 'warning';
  message: string;
};

const durations = {
  error: 8_000,
  warning: 6_000,
  success: 4_000,
  info: 5_000,
} as const;

export function LegacyToast({
  toast,
  onDismiss,
}: {
  toast: LegacyToastMessage | null;
  onDismiss: () => void;
}) {
  useEffect(() => {
    if (!toast) return undefined;
    const timer = window.setTimeout(onDismiss, durations[toast.category]);
    return () => window.clearTimeout(timer);
  }, [onDismiss, toast]);

  if (!toast) return null;
  const role = toast.category === 'error' || toast.category === 'warning'
    ? 'alert'
    : 'status';
  return (
    <div className={`toast toast--${toast.category}`} role={role}>
      <span className="toast__msg">{toast.message}</span>
      <button className="toast__close" type="button" aria-label="Dismiss" onClick={onDismiss}>×</button>
    </div>
  );
}

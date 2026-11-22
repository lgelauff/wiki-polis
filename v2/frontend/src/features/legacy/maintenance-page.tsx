import {useEffect, useState} from 'react';
import {useSuspenseQuery} from '@tanstack/react-query';

import {sessionQuery} from '../../api/queries';
import {useMessage} from '../../i18n/messages';
import {MAINTENANCE_RECHECK_MS} from '../../maintenance';
import {LegacyShell} from './legacy-shell';

/**
 * The app's own page for a screen the server refused because maintenance mode is on (#619):
 * a console screen whose reads are paused for organizers and moderators. Its words are the
 * server's branded 503 page's (`error_pages.py`), as `AccessDeniedPage` mirrors the 403 one.
 *
 * It asks for the session every half minute while it shows, and calls `onOver` once a session
 * read after it appeared says maintenance is off, so the screen comes back without a reload.
 */
export function MaintenancePage({onOver}: {onOver: () => void}) {
  const msg = useMessage();
  const [shownAt] = useState(() => Date.now());
  const {data: session, dataUpdatedAt} = useSuspenseQuery({
    ...sessionQuery(),
    refetchInterval: MAINTENANCE_RECHECK_MS,
  });
  // A session read from before the refusal may still say "off"; only a newer one counts.
  const over = !session.maintenance && dataUpdatedAt > shownAt;
  useEffect(() => {
    if (over) onOver();
  }, [over, onOver]);
  return (
    <LegacyShell title={`503 ${msg('errorpage-503-title')} — Proto`}>
      <div className="container" style={{maxWidth: 700, paddingTop: '3rem'}}>
        <h1 style={{fontSize: 24, fontWeight: 600, color: 'var(--ink)', margin: '0 0 .75rem'}}>{msg('errorpage-503-title')}</h1>
        <p style={{color: 'var(--body)', fontSize: 15, lineHeight: 1.6, margin: '0 0 .5rem'}}>{msg('errorpage-503-message')}</p>
        <p style={{color: 'var(--body)', fontSize: 15, lineHeight: 1.6, margin: 0}}>{msg('errorpage-503-hint')}</p>
      </div>
    </LegacyShell>
  );
}

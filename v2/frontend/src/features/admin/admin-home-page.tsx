import {useSuspenseQuery} from '@tanstack/react-query';

import type {components} from '../../api/schema';
import {adminHomeQuery} from '../../api/queries';
import {InternalLink} from '../../internal-link';
import {useMessage, type Message} from '../../i18n/messages';
import {roleLabel} from '../../i18n/server-labels';
import {AdminShell} from './admin-shell';

type Row = components['schemas']['AdminHome']['conversations'][number];

/** The status word, in the dashboard's words (`admin-catalog-page.tsx`). */
function statusLabel(msg: Message, status: Row['status']): string {
  switch (status) {
    case 'active': return msg('admin-status-active');
    case 'paused': return msg('admin-status-paused');
    case 'closed': return msg('admin-status-closed');
    case 'archived': return msg('admin-status-archived');
  }
}

/**
 * Admin home (#538): the consultations the viewer is an organizer or moderator of.
 *
 * One list, one row per consultation: the title goes to its Overview, and the viewer's
 * role, the status and the open flags are plain text beside it. A zero is left out, as in
 * the sidebar badge: an empty counter is noise, not information. Pending statements live
 * in the voting service, not here, so they are not counted on this page.
 *
 * A site admin reaches the dashboard from the sidebar (`AdminShell`); someone with no role
 * who is not a site admin never gets here -- the server refuses, and the access boundary
 * shows the access page instead.
 */
export function AdminHomePage() {
  const msg = useMessage();
  const {data} = useSuspenseQuery(adminHomeQuery());
  const heading = msg('admin-home-heading');

  return (
    <AdminShell site={heading} home title={`${heading} — Proto`}>
      <div className="admin-page">
        <h1>{heading}</h1>
        {data.conversations.length ? (
          <ul className="admin-rows">
            {data.conversations.map((row) => (
              <li className="admin-row" key={row.id}>
                <div className="admin-row__text">
                  <InternalLink href={row.links.overview}>{row.title}</InternalLink>
                </div>
                <div className="admin-row__counts">
                  {roleLabel(msg, row.role)}
                  {' · '}
                  {statusLabel(msg, row.status)}
                  {row.openFlags > 0 && <>{' · '}{msg('adminconv-open-count', row.openFlags)}</>}
                </div>
              </li>
            ))}
          </ul>
        ) : <p className="admin-empty">{msg('admin-home-empty')}</p>}
      </div>
    </AdminShell>
  );
}

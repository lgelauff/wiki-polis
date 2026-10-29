import {useEffect} from 'react';
import {useSuspenseQuery} from '@tanstack/react-query';

import {adminReportPreviewQuery} from '../../api/queries';
import {FinalReportLegacyPage} from '../legacy/final-report-page';

/** A site admin's preview of the results report, in any phase. It renders the report page
 *  itself; the server marks the data `publication: 'preview'`, which puts the banner and
 *  the Preview badge on it. Opening it publishes nothing. */
export function AdminReportPreviewPage({conversationId}: {conversationId: number}) {
  const {data} = useSuspenseQuery(adminReportPreviewQuery(conversationId));

  useEffect(() => {
    const meta = document.createElement('meta');
    meta.name = 'robots';
    meta.content = 'noindex,nofollow';
    document.head.appendChild(meta);
    return () => meta.remove();
  }, []);

  return <FinalReportLegacyPage report={data} />;
}

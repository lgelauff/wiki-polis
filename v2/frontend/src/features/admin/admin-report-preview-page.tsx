import {useQuery} from '@tanstack/react-query';
import {Navigate} from 'react-router-dom';

import {adminReportPreviewQuery} from '../../api/queries';
import {FinalReportLegacyPage} from '../legacy/final-report-page';

/** A site admin's preview of the results report, in any phase until publication. It renders
 *  the report page itself; the server marks the data `publication: 'preview'`, which puts the
 *  banner and the Preview badge on it. Opening it publishes nothing. Like the report, it has
 *  the participant-facing header, not the admin console's. Once the report is published there
 *  is nothing to preview, so the page goes to the published report. */
export function AdminReportPreviewPage({conversationId}: {conversationId: number}) {
  // Not suspense: see adminReportPreviewQuery. Errors (401, 403) still reach the admin
  // access boundary; while loading, the page shows nothing, as a suspended page does.
  const {data} = useQuery({...adminReportPreviewQuery(conversationId), throwOnError: true});
  if (!data) return null;
  if (data.state === 'published') return <Navigate replace to={data.reportPath} />;
  return <FinalReportLegacyPage report={data.report} />;
}

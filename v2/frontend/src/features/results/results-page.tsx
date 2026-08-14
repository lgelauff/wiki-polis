import {Component, type ReactNode} from 'react';
import {useSuspenseQuery} from '@tanstack/react-query';

import {ApiContractError} from '../../api/client';
import {resultsReportQuery} from '../../api/queries';
import {ConversationWorkspacePage} from '../legacy/conversation-workspace-page';
import {NavigationRedirect} from '../legacy/external-redirect';
import {FinalReportLegacyPage} from '../legacy/final-report-page';

export class ResultsAccessBoundary extends Component<
  {children: ReactNode; slug: string},
  {error: unknown | null}
> {
  state: {error: unknown | null} = {error: null};

  static getDerivedStateFromError(error: unknown) {
    return {error};
  }

  render() {
    if (this.state.error instanceof ApiContractError && this.state.error.code === 'unauthorized') {
      return <NavigationRedirect href={`/login?next=${encodeURIComponent(`/c/${this.props.slug}/report`)}`} />;
    }
    if (this.state.error) throw this.state.error;
    return this.props.children;
  }
}

export function ResultsPage({slug}: {slug: string}) {
  const {data} = useSuspenseQuery(resultsReportQuery(slug));
  return data.publication === 'preliminary'
    ? <ConversationWorkspacePage />
    : <FinalReportLegacyPage report={data} />;
}

import {Component, type ReactNode} from 'react';
import {useSuspenseQuery} from '@tanstack/react-query';
import {useParams} from 'react-router-dom';

import {ApiContractError} from '../../api/client';
import {resultsReportQuery} from '../../api/queries';
import {ConversationWorkspacePage} from '../legacy/conversation-workspace-page';
import {LoginPrompt} from '../legacy/login-prompt';
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
      return <LoginPrompt />;
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

export function ResultsRoute() {
  const {slug = ''} = useParams();
  return <ResultsAccessBoundary slug={slug}>
    <ResultsPage slug={slug} />
  </ResultsAccessBoundary>;
}

import {useSuspenseQuery} from '@tanstack/react-query';

import type {components} from '../../api/schema';
import {resultsReportQuery} from '../../api/queries';

type Tally = components['schemas']['VoteTally'];

function percentage(value: number) {
  return value.toFixed(1);
}

function VoteBar({tally}: {tally: Tally}) {
  const {percentages} = tally;
  const title = `Agree ${percentage(percentages.agree)}% · Disagree ${percentage(percentages.disagree)}% · Pass ${percentage(percentages.pass)}%`;
  return <>
    <div className="p6-vote-bar" title={title}>
      <div className="p6-bar-agree" style={{width: `${percentages.agree}%`}} />
      <div className="p6-bar-disagree" style={{width: `${percentages.disagree}%`}} />
      <div className="p6-bar-pass" style={{width: `${percentages.pass}%`}} />
    </div>
    <span className="p6-bar-label">{percentage(percentages.agree)}% agree · {percentage(percentages.pass)}% pass</span>
  </>;
}

export function LegacyPreliminaryResultsPanel({slug}: {slug: string}) {
  const {data} = useSuspenseQuery(resultsReportQuery(slug));
  return <div className="landing-section results-section">
    <div className="results-block p6-results-block">
      <div className="p6-results-header">
        <p className="results-label">Preliminary results</p>
        {data.publication === 'preliminary' && <span className="p6-results-badge p6-results-badge--preliminary">Preliminary</span>}
        {!!data.participation.informedRound && <span className="muted" style={{fontSize: 12}}>{data.participation.informedRound} participant{data.participation.informedRound === 1 ? '' : 's'}</span>}
      </div>
      {!data.dataAvailability.detailedCounts ? (
        <p className="muted" style={{fontSize: 13}}>Detailed vote counts are not available right now.</p>
      ) : (
        <table className="p6-results-table" aria-label="Preliminary informed voting results by statement">
          <thead><tr>
            <th className="p6-col-stmt">Statement</th>
            <th className="p6-col-phase" title="Phase 2 — initial voting">Initial vote</th>
            <th className="p6-col-phase" title="Phase 6 — informed voting">Informed vote</th>
            <th className="p6-col-shift" title="Change in agree rate">Shift</th>
            {data.viewer.participating && <th className="p6-col-mine">Yours</th>}
          </tr></thead>
          <tbody>{data.statements.map((statement) => <tr className="p6-results-row" key={statement.featuredStatementId}>
            <td className="p6-col-stmt">{statement.statement}</td>
            <td className="p6-col-phase">{statement.initial ? <VoteBar tally={statement.initial} /> : <span className="muted">—</span>}</td>
            <td className="p6-col-phase">{statement.informed ? <VoteBar tally={statement.informed} /> : <span className="muted">—</span>}</td>
            <td className="p6-col-shift">{statement.agreementShift === null
              ? <span className="muted">—</span>
              : <span className={`p6-shift${statement.agreementShift > 0 ? ' p6-shift--up' : statement.agreementShift < 0 ? ' p6-shift--down' : ''}`}>{statement.agreementShift > 0 ? '+' : ''}{percentage(statement.agreementShift)}%</span>}
            </td>
            {data.viewer.participating && <td className="p6-col-mine">{statement.viewerChoice
              ? <span className={`p6-my-vote p6-my-vote--${statement.viewerChoice}`}>{statement.viewerChoice.charAt(0).toUpperCase() + statement.viewerChoice.slice(1)}</span>
              : <span className="muted">—</span>}
            </td>}
          </tr>)}</tbody>
        </table>
      )}
    </div>
  </div>;
}

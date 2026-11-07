import {useSuspenseQuery} from '@tanstack/react-query';

import type {components} from '../../api/schema';
import {resultsReportQuery} from '../../api/queries';
import {useMessage, type Message} from '../../i18n/messages';
import {usePercentFormat} from '../../i18n/numbers';
import {rankOpinionStatements} from './statement-rankings';

type Statement = components['schemas']['ResultsStatement'];
type Tally = components['schemas']['VoteTally'];

// Only ranked rows reach this bar, and the ranking skips tallies the server withheld (#233).
function VoteBar({tally, msg}: {tally: Tally; msg: Message}) {
  const {percentages} = tally;
  const format = usePercentFormat();
  if (!percentages) return null;
  const percentage = (value: number) => format(value, {digits: 0});
  const title = msg('conv-bar-title', percentage(percentages.agree), percentage(percentages.disagree), percentage(percentages.pass));
  return <>
    <div className="p6-vote-bar" title={title}>
      <div className="p6-bar-agree" style={{width: `${percentages.agree}%`}} />
      <div className="p6-bar-disagree" style={{width: `${percentages.disagree}%`}} />
      <div className="p6-bar-pass" style={{width: `${percentages.pass}%`}} />
    </div>
    <span className="p6-bar-label">{msg('conv-bar-label', percentage(percentages.agree), percentage(percentages.pass))}</span>
  </>;
}

// No "Yours" line: a participant's own choice in the results waits for the personal lens
// (owner, 2026-10-17).
function OpinionRows({statements, msg}: {statements: Statement[]; msg: Message}) {
  return statements.map((statement) => statement.informed && <div className="report-stmt-row" key={statement.featuredStatementId}>
    <p className="report-stmt-text">{statement.statement}</p>
    <VoteBar tally={statement.informed} msg={msg} />
  </div>);
}

export function LegacyPreliminaryResultsPanel({slug}: {slug: string}) {
  const {data} = useSuspenseQuery(resultsReportQuery(slug));
  const msg = useMessage();
  const {consensus, divisive} = rankOpinionStatements(data.statements, 'informed');
  const hasRankedResults = consensus.length > 0 || divisive.length > 0;
  // Responses exist but every statement is still below the floor: say so, not "no votes".
  const allBelowFloor = data.statements.some((statement) => statement.informed?.belowFloor);
  return <div className="landing-section results-section">
    <div className="results-block p6-results-block">
      <div className="p6-results-header">
        <p className="results-label">{msg('conv-tab-preliminary')}</p>
        {data.publication === 'preliminary' && <span className="p6-results-badge p6-results-badge--preliminary">{msg('conv-p6-badge-prelim')}</span>}
        {!!data.participation.informedRound && <span className="muted" style={{fontSize: 12}}>{msg('conv-participant-count', data.participation.informedRound)}</span>}
      </div>
      <p className="muted" style={{fontSize: 13, marginBottom: '1rem'}}>{msg('conv-preliminary-results-intro')}</p>
      {!data.dataAvailability.detailedCounts ? (
        <p className="muted" style={{fontSize: 13}}>{msg('conv-p6-counts-unavailable')}</p>
      ) : !hasRankedResults ? (
        <p className="muted" style={{fontSize: 13}}>{allBelowFloor
          ? msg('results-tally-few', data.dataAvailability.responseFloor)
          : msg('conv-preliminary-no-votes')}</p>
      ) : (
        <>
          {consensus.length > 0 && <section className="report-section">
            <h3 className="report-section-sub-heading">{msg('report-highest-agreement')}</h3>
            <OpinionRows statements={consensus} msg={msg} />
          </section>}
          {divisive.length > 0 && <section className="report-section">
            <h3 className="report-section-sub-heading">{msg('report-most-divisive')}</h3>
            <p className="muted" style={{fontSize: 13, marginBottom: '.75rem'}}>{msg('report-divisive-intro')}</p>
            <OpinionRows statements={divisive} msg={msg} />
          </section>}
        </>
      )}
    </div>
  </div>;
}

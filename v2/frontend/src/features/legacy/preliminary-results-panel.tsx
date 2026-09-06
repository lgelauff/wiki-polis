import {useSuspenseQuery} from '@tanstack/react-query';

import type {components} from '../../api/schema';
import {resultsReportQuery} from '../../api/queries';
import {useMessage, type Message} from '../../i18n/messages';

type Tally = components['schemas']['VoteTally'];

/** The 'Yours' column. Written as a literal map rather than an interpolated key so the
 *  key-existence guard in tests/test_i18n.py can see all three, and because the message
 *  names are past tense where the API values are not. */
const MY_VOTE_KEY: Record<'agree' | 'disagree' | 'pass', string> = {
  agree: 'conv-p6-mine-agreed',
  disagree: 'conv-p6-mine-disagreed',
  pass: 'conv-p6-mine-passed',
};

function percentage(value: number) {
  return value.toFixed(1);
}

function VoteBar({tally, msg}: {tally: Tally; msg: Message}) {
  const {percentages} = tally;
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

export function LegacyPreliminaryResultsPanel({slug}: {slug: string}) {
  const {data} = useSuspenseQuery(resultsReportQuery(slug));
  const msg = useMessage();
  return <div className="landing-section results-section">
    <div className="results-block p6-results-block">
      <div className="p6-results-header">
        <p className="results-label">{msg('conv-tab-preliminary')}</p>
        {data.publication === 'preliminary' && <span className="p6-results-badge p6-results-badge--preliminary">{msg('conv-p6-badge-prelim')}</span>}
        {!!data.participation.informedRound && <span className="muted" style={{fontSize: 12}}>{msg('conv-participant-count', data.participation.informedRound)}</span>}
      </div>
      {!data.dataAvailability.detailedCounts ? (
        <p className="muted" style={{fontSize: 13}}>{msg('conv-p6-counts-unavailable')}</p>
      ) : (
        <table className="p6-results-table" aria-label={msg('conv-p6-table-aria')}>
          <thead><tr>
            <th className="p6-col-stmt">{msg('conv-col-statement')}</th>
            <th className="p6-col-phase" title={msg('conv-col-initial-title')}>{msg('conv-col-initial-vote')}</th>
            <th className="p6-col-phase" title={msg('conv-col-informed-title')}>{msg('conv-col-informed-vote')}</th>
            <th className="p6-col-shift" title={msg('conv-col-shift-title')}>{msg('conv-col-shift')}</th>
            {data.viewer.participating && <th className="p6-col-mine">{msg('conv-col-yours')}</th>}
          </tr></thead>
          <tbody>{data.statements.map((statement) => <tr className="p6-results-row" key={statement.featuredStatementId}>
            <td className="p6-col-stmt">{statement.statement}</td>
            <td className="p6-col-phase">{statement.initial ? <VoteBar tally={statement.initial} msg={msg} /> : <span className="muted">—</span>}</td>
            <td className="p6-col-phase">{statement.informed ? <VoteBar tally={statement.informed} msg={msg} /> : <span className="muted">—</span>}</td>
            <td className="p6-col-shift">{statement.agreementShift === null
              ? <span className="muted">—</span>
              : <span className={`p6-shift${statement.agreementShift > 0 ? ' p6-shift--up' : statement.agreementShift < 0 ? ' p6-shift--down' : ''}`}>{statement.agreementShift > 0 ? '+' : ''}{percentage(statement.agreementShift)}%</span>}
            </td>
            {data.viewer.participating && <td className="p6-col-mine">{statement.viewerChoice
              ? <span className={`p6-my-vote p6-my-vote--${statement.viewerChoice}`}>{msg(MY_VOTE_KEY[statement.viewerChoice])}</span>
              : <span className="muted">—</span>}
            </td>}
          </tr>)}</tbody>
        </table>
      )}
    </div>
  </div>;
}

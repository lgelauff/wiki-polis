import {useSuspenseQuery} from '@tanstack/react-query';

import type {components} from '../../api/schema';
import {intermediateResultsQuery} from '../../api/queries';
import {useMessage} from '../../i18n/messages';
import {richHtml} from '../../i18n/rich-html';

type Position = components['schemas']['IntermediateResultPosition'];

function ResultRow({position}: {position: Position}) {
  const msg = useMessage();
  return <div className="results-row">
    <span className={`results-badge results-${position.choice}`}>{position.choice === 'agree' ? msg('conv-badge-agree') : msg('conv-badge-disagree')}</span>
    <span className="results-pct">{position.percentage}%</span>
    <span className="results-text">{msg('conv-results-quoted', position.statement)}</span>
  </div>;
}

export function LegacyIntermediateResultsPanel({slug}: {slug: string}) {
  const msg = useMessage();
  const {data} = useSuspenseQuery(intermediateResultsQuery(slug));
  return <div className="landing-section results-section">
    <h2>{msg('conv-results-heading')}{!!data.participantCount && <>{' '}<span className="muted" style={{fontSize: 13, fontWeight: 400, marginLeft: '.75rem'}}>{msg('conv-participant-count', data.participantCount)}</span></>}</h2>
    {data.state === 'ready' ? <>
      {data.smallSample && data.participantCount !== null && <div className="notice-low-n" dangerouslySetInnerHTML={richHtml(msg('conv-small-sample', data.participantCount))} />}
      {data.consensus.length > 0 && <div className="results-block">
        <p className="results-label">{msg('conv-consensus-label')}</p>
        {data.consensus.map((position, index) => <ResultRow position={position} key={`${position.choice}-${index}`} />)}
      </div>}
      {data.groups.length > 0 && <div className="results-block">
        <p className="results-label">{msg('conv-groups-found', data.groups.length)}</p>
        {/* The server labels groups "Group 1", "Group 2" by position; the number is what
            carries meaning, so the label is rebuilt from it in the reader's language. */}
        {data.groups.map((group, groupIndex) => <div key={group.label}>
          <p className="results-group-heading">{msg('report-group-label', groupIndex + 1)}</p>
          {group.positions.map((position, index) => <ResultRow position={position} key={`${position.choice}-${index}`} />)}
        </div>)}
      </div>}
    </> : <p className="muted">{data.state === 'recomputing' ? msg('conv-results-computing') : msg('conv-results-pending')}</p>}
  </div>;
}

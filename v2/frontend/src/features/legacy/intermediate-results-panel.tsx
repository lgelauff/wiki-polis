import {useSuspenseQuery} from '@tanstack/react-query';

import type {components} from '../../api/schema';
import {intermediateResultsQuery} from '../../api/queries';

type Position = components['schemas']['IntermediateResultPosition'];

function ResultRow({position}: {position: Position}) {
  return <div className="results-row">
    <span className={`results-badge results-${position.choice}`}>{position.choice}</span>
    <span className="results-text">"{position.statement}"</span>
    <span className="results-pct">{position.percentage}%</span>
  </div>;
}

export function LegacyIntermediateResultsPanel({slug}: {slug: string}) {
  const {data} = useSuspenseQuery(intermediateResultsQuery(slug));
  return <div className="landing-section results-section">
    <h2>Results{!!data.participantCount && <span className="muted" style={{fontSize: 13, fontWeight: 400, marginLeft: '.75rem'}}>{data.participantCount} participant{data.participantCount === 1 ? '' : 's'}</span>}</h2>
    {data.state === 'ready' ? <>
      {data.smallSample && <div className="notice-low-n"><strong>Small sample:</strong> these results are based on {data.participantCount} participant{data.participantCount === 1 ? '' : 's'}. Opinion groups detected from small samples can shift substantially as more people participate — treat group boundaries with caution.</div>}
      {data.consensus.length > 0 && <div className="results-block">
        <p className="results-label">Areas of broad consensus</p>
        {data.consensus.map((position, index) => <ResultRow position={position} key={`${position.choice}-${index}`} />)}
      </div>}
      {data.groups.length > 0 && <div className="results-block">
        <p className="results-label">{data.groups.length} opinion group{data.groups.length === 1 ? '' : 's'} found</p>
        {data.groups.map((group) => <div key={group.label}>
          <p className="results-group-heading">{group.label}</p>
          {group.positions.map((position, index) => <ResultRow position={position} key={`${position.choice}-${index}`} />)}
        </div>)}
      </div>}
    </> : <p className="muted">{data.state === 'recomputing' ? 'Results are being computed — check back in a moment.' : 'Results will appear here once enough votes have been cast.'}</p>}
  </div>;
}

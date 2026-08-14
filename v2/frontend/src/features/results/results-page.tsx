import {useSuspenseQuery} from '@tanstack/react-query';
import {Link} from 'react-router-dom';
import {Component, type ReactNode} from 'react';

import type {components} from '../../api/schema';
import {ApiContractError} from '../../api/client';
import {resultsReportQuery} from '../../api/queries';
import {ExternalRedirect} from '../legacy/external-redirect';
import {FinalReportLegacyPage} from '../legacy/final-report-page';

type Tally = components['schemas']['VoteTally'];

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
      return <ExternalRedirect href={`/login?next=${encodeURIComponent(`/c/${this.props.slug}/report`)}`} />;
    }
    if (this.state.error) throw this.state.error;
    return this.props.children;
  }
}

function VoteBar({tally, label}: {tally: Tally; label: string}) {
  const {percentages, counts} = tally;
  return (
    <div className="result-tally">
      <div
        className="result-bar"
        role="img"
        aria-label={`${label}: ${percentages.agree}% agree, ${percentages.pass}% pass, ${percentages.disagree}% disagree`}
      >
        <span className="result-bar__agree" style={{width: `${percentages.agree}%`}} />
        <span className="result-bar__pass" style={{width: `${percentages.pass}%`}} />
        <span className="result-bar__disagree" style={{width: `${percentages.disagree}%`}} />
      </div>
      <dl className="result-tally__legend">
        <div><dt>Agree</dt><dd>{percentages.agree}% <span>({counts.agree})</span></dd></div>
        <div><dt>Pass</dt><dd>{percentages.pass}% <span>({counts.pass})</span></dd></div>
        <div><dt>Disagree</dt><dd>{percentages.disagree}% <span>({counts.disagree})</span></dd></div>
      </dl>
    </div>
  );
}

function ResultStatement({item}: {
  item: components['schemas']['ResultsStatement'];
}) {
  return (
    <article className="result-statement">
      <header>
        <h3>{item.statement}</h3>
        {item.agreementShift !== null && (
          <span className="result-shift" data-direction={
            item.agreementShift > 0 ? 'up' : item.agreementShift < 0 ? 'down' : 'same'
          }>
            {item.agreementShift > 0 ? '+' : ''}{item.agreementShift}% agreement
          </span>
        )}
      </header>
      <div className="result-rounds">
        <section>
          <h4>Initial vote</h4>
          {item.initial ? <VoteBar tally={item.initial} label="Initial vote" /> : <p>Not available</p>}
        </section>
        <section>
          <h4>Informed vote</h4>
          {item.informed ? <VoteBar tally={item.informed} label="Informed vote" /> : <p>Not available</p>}
        </section>
      </div>
    </article>
  );
}

export function ResultsPage({slug, preliminaryHeader}: {slug: string; preliminaryHeader?: ReactNode}) {
  const {data} = useSuspenseQuery(resultsReportQuery(slug));
  if (data.publication === 'final') return <FinalReportLegacyPage report={data} />;
  const excluded = data.moderation.excludedStatements + data.moderation.excludedParticipants;

  return (<>
    {preliminaryHeader}
    <main className="results-shell" id="main">
      <nav className="record-breadcrumb" aria-label="Breadcrumb">
        <Link to="/app/real">Conversations</Link><span>/</span>
        <Link to={data.links.about}>{data.title}</Link><span>/</span><span>Results</span>
      </nav>
      <header className="results-heading">
        <div>
          <p className="eyebrow">{data.publication} consultation output</p>
          <h1>{data.title}</h1>
          <p>{data.context.method}</p>
        </div>
        <span className="results-publication" data-publication={data.publication}>
          {data.publication}
        </span>
      </header>

      <section className="results-provenance" aria-labelledby="results-context-heading">
        <div>
          <h2 id="results-context-heading">How to read this output</h2>
          <p>Produced from <strong>{data.context.phase}</strong>. These results can still change while participation remains open.</p>
        </div>
        <dl>
          <div><dt>Initial round</dt><dd>{data.participation.initialRound ?? '—'}</dd></div>
          <div><dt>Informed round</dt><dd>{data.participation.informedRound ?? '—'}</dd></div>
          <div><dt>Excluded records</dt><dd>{excluded}</dd></div>
        </dl>
      </section>

      <section className="results-section" aria-labelledby="statement-results-heading">
        <div className="results-section__heading">
          <p className="eyebrow">Round comparison</p>
          <h2 id="statement-results-heading">What changed after argument mapping?</h2>
          <p>Agreement shift compares aggregate populations across rounds; it is not a matched individual before-and-after measure.</p>
        </div>
        {!data.dataAvailability.detailedCounts && (
          <p className="results-unavailable" role="status">Detailed counts are temporarily unavailable. No missing value is shown as zero.</p>
        )}
        <div className="result-statement-list">
          {data.statements.map((item) => (
            <ResultStatement key={item.featuredStatementId} item={item} />
          ))}
        </div>
      </section>

      {data.opinionGroups.length > 0 && (
        <section className="results-section" aria-labelledby="opinion-groups-heading">
          <div className="results-section__heading">
            <p className="eyebrow">Aggregate clusters</p>
            <h2 id="opinion-groups-heading">Opinion groups</h2>
            <p>Groups summarize participants with similar informed-voting patterns.</p>
          </div>
          <div className="opinion-groups">
            {data.opinionGroups.map((group) => (
              <article key={group.label}>
                <header><h3>{group.label}</h3><span>{group.memberCount ?? '—'} participants</span></header>
                <ul>
                  {group.positions.map((position, index) => (
                    <li key={`${position.choice}-${index}`} data-choice={position.choice}>
                      <span>{position.choice}</span>
                      <p>{position.statement}</p>
                      <strong>{position.percentage === null ? '—' : `${position.percentage}%`}</strong>
                    </li>
                  ))}
                </ul>
              </article>
            ))}
          </div>
        </section>
      )}

      <footer className="results-footer">
        <Link to={data.links.about}>Back to conversation record</Link>
        {data.links.identityReveal && <Link to={data.links.identityReveal}>Identity reveal</Link>}
        <a href={data.links.conversation}>Open legacy conversation view</a>
      </footer>
    </main>
  </>);
}

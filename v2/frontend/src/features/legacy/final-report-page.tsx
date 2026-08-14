import type {components} from '../../api/schema';
import {LegacyShell} from './legacy-shell';
import {InternalLink} from '../../internal-link';

type Report = components['schemas']['ResultsReport'];
type Statement = components['schemas']['ResultsStatement'];
type Tally = components['schemas']['VoteTally'];

function truncated(value: string, length: number) {
  return value.length > length ? `${value.slice(0, length - 1)}…` : value;
}

function shortDate(value: string) {
  const date = new Date(value);
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  return `${date.getUTCDate()} ${months[date.getUTCMonth()]} ${date.getUTCFullYear()}`;
}

function percentage(value: number) {
  return value.toFixed(1);
}

function LegacyVoteBar({tally}: {tally: Tally}) {
  const {percentages, counts} = tally;
  const title = `Agree ${percentage(percentages.agree)}% · Disagree ${percentage(percentages.disagree)}% · Pass ${percentage(percentages.pass)}%`;
  return <>
    <div className="p6-vote-bar" title={title}>
      <div className="p6-bar-agree" style={{width: `${percentages.agree}%`}} />
      <div className="p6-bar-disagree" style={{width: `${percentages.disagree}%`}} />
      <div className="p6-bar-pass" style={{width: `${percentages.pass}%`}} />
    </div>
    <span className="p6-bar-label">{`${percentage(percentages.agree)}% agree · ${percentage(percentages.pass)}% pass · ${counts.voters} votes`}</span>
  </>;
}

function initialOpinionRows(statements: Statement[]) {
  const available = statements.filter((statement) => statement.initial && statement.initial.counts.voters > 0);
  const consensus = [...available].sort((left, right) =>
    (right.initial?.percentages.agree ?? 0) - (left.initial?.percentages.agree ?? 0)).slice(0, 3);
  const divisive = [...available].sort((left, right) => {
    const leftGap = Math.abs((left.initial?.percentages.agree ?? 0) - (left.initial?.percentages.disagree ?? 0));
    const rightGap = Math.abs((right.initial?.percentages.agree ?? 0) - (right.initial?.percentages.disagree ?? 0));
    return leftGap - rightGap;
  }).slice(0, 3);
  return {consensus, divisive};
}

function PlaceholderSections() {
  return <>
    <div className="report-section">
      <h2 className="report-section-heading">Introduction</h2>
      <p className="report-placeholder"><em>Organizer introduction not yet added. This section should explain what the consultation was about, who organised it, and how the results will be used.</em></p>
    </div>
  </>;
}

function ProcessTimeline({report}: {report: Report}) {
  return <div className="report-section">
    <h2 className="report-section-heading">Process</h2>
    <div className="report-timeline">
      <div className="report-timeline-item">
        <span className="report-timeline-label">Consultation opened</span>
        <span className="report-timeline-value">{shortDate(report.openedAt)}</span>
      </div>
      {['Submission phase', 'Argument mapping', 'Informed voting'].map((label) => (
        <div className="report-timeline-item report-timeline-item--placeholder" key={label}>
          <span className="report-timeline-label">{label}</span>
          <span className="report-timeline-value report-placeholder-inline">dates not stored yet</span>
        </div>
      ))}
      {report.closedAt && <div className="report-timeline-item">
        <span className="report-timeline-label">Consultation closed</span>
        <span className="report-timeline-value">{shortDate(report.closedAt)}</span>
      </div>}
    </div>
  </div>;
}

function ParticipationSummary({report}: {report: Report}) {
  const statements = report.moderation.excludedStatements;
  const participants = report.moderation.excludedParticipants;
  const moderationSummary = `Moderation applied: ${statements > 0 ? `${statements} statement${statements === 1 ? '' : 's'} excluded` : ''}${participants > 0 ? ` · ${participants} participant${participants === 1 ? '' : 's'} excluded` : ''}`;
  return <div className="report-section">
    <h2 className="report-section-heading">Participation</h2>
    <div className="report-stats-row">
      {!!report.participation.initialRound && <div className="report-stat">
        <span className="report-stat-value">{report.participation.initialRound}</span>
        <span className="report-stat-label">Initial voting (Phase 2)</span>
      </div>}
      {!!report.participation.informedRound && <div className="report-stat">
        <span className="report-stat-value">{report.participation.informedRound}</span>
        <span className="report-stat-label">Informed voting (Phase 6)</span>
      </div>}
      <div className="report-stat report-stat--placeholder">
        <span className="report-stat-value">—</span>
        <span className="report-stat-label">Voted in both rounds</span>
      </div>
    </div>
    {(statements > 0 || participants > 0) && <p className="report-moderation-note muted">{moderationSummary}</p>}
    {!report.dataAvailability.detailedCounts && <p className="muted" style={{fontSize: 13, marginTop: '.5rem'}}>Detailed vote counts are not available — the results database is unreachable.</p>}
  </div>;
}

function InitialOpinions({statements}: {statements: Statement[]}) {
  const {consensus, divisive} = initialOpinionRows(statements);
  if (consensus.length === 0 && divisive.length === 0) return null;
  return <div className="report-section">
    <h2 className="report-section-heading">Initial opinions <span className="report-section-sub">Phase 2 — before argument mapping</span></h2>
    <p className="muted" style={{fontSize: 13, marginBottom: '1rem'}}>Based on votes cast during the initial submission phase, before participants saw any arguments.</p>
    {consensus.length > 0 && <>
      <h3 className="report-section-sub-heading">Highest agreement</h3>
      {consensus.map((statement) => <div className="report-stmt-row" key={`consensus-${statement.featuredStatementId}`}>
        <p className="report-stmt-text">{statement.statement}</p>
        <LegacyVoteBar tally={statement.initial!} />
      </div>)}
    </>}
    {divisive.length > 0 && <>
      <h3 className="report-section-sub-heading" style={{marginTop: '1.25rem'}}>Most divisive</h3>
      <p className="muted" style={{fontSize: 13, marginBottom: '.75rem'}}>Statements with the most evenly split agree/disagree response.</p>
      {divisive.map((statement) => <div className="report-stmt-row" key={`divisive-${statement.featuredStatementId}`}>
        <p className="report-stmt-text">{statement.statement}</p>
        <LegacyVoteBar tally={statement.initial!} />
      </div>)}
    </>}
  </div>;
}

function OpinionShift({statements}: {statements: Statement[]}) {
  if (statements.length === 0) return null;
  return <div className="report-section">
    <h2 className="report-section-heading">Opinion shift <span className="report-section-sub">Did argument exposure change views?</span></h2>
    <p className="muted" style={{fontSize: 13, marginBottom: '1rem'}}>Each row compares the initial vote (Phase 2, before arguments) with the informed vote (Phase 6, after argument mapping). <strong>Shift</strong> is the change in population-level agree rate — a cross-round comparison of separate populations, not a matched individual delta (see <InternalLink href="#methodology" className="report-anchor">Methodology</InternalLink> below). Sorted by size of shift.</p>
    <table className="p6-results-table report-table" aria-label="Aggregate opinion shift per statement">
      <thead><tr>
        <th className="p6-col-stmt">Statement</th>
        <th className="p6-col-phase">Initial</th>
        <th className="p6-col-phase">Informed</th>
        <th className="p6-col-shift">Shift <span className="report-col-note">(aggregate)</span></th>
      </tr></thead>
      <tbody>{statements.map((statement) => <tr className="p6-results-row" key={statement.featuredStatementId}>
        <td className="p6-col-stmt">{statement.statement}</td>
        <td className="p6-col-phase">{statement.initial ? <LegacyVoteBar tally={statement.initial} /> : <span className="muted">—</span>}</td>
        <td className="p6-col-phase">{statement.informed && <LegacyVoteBar tally={statement.informed} />}</td>
        <td className="p6-col-shift">{statement.agreementShift === null
          ? <span className="muted">—</span>
          : <span className={`p6-shift${statement.agreementShift > 0 ? ' p6-shift--up' : statement.agreementShift < 0 ? ' p6-shift--down' : ''}`}>{`${statement.agreementShift > 0 ? '+' : ''}${percentage(statement.agreementShift)}%`}</span>}
        </td>
      </tr>)}</tbody>
    </table>
  </div>;
}

function OpinionGroups({report}: {report: Report}) {
  if (report.opinionGroups.length === 0) return null;
  return <div className="report-section">
    <h2 className="report-section-heading">Opinion groups <span className="report-section-sub">{`${report.opinionGroups.length} group${report.opinionGroups.length === 1 ? '' : 's'} identified in the informed voting round`}</span></h2>
    <p className="muted" style={{fontSize: 13, marginBottom: '1rem'}}>Groups represent clusters of participants with similar voting patterns, identified by PCA + k-means on the informed voting matrix. Statements listed here were most characteristic of each group.</p>
    {report.opinionGroups.map((group) => <div className="results-block" style={{marginBottom: '1rem'}} key={group.label}>
      <p className="results-group-heading">{`\n        ${group.label}\n        `}{!!group.memberCount && <span className="muted" style={{fontWeight: 400, fontSize: 12}}>{`· ${group.memberCount} participant${group.memberCount === 1 ? '' : 's'}`}</span>}{'\n      '}</p>
      {group.positions.map((position, index) => <div className="results-row" key={`${position.choice}-${index}`}>
        <span className={`results-badge results-${position.choice}`}>{position.choice}</span>
        <span className="results-text">{`"${position.statement}"`}</span>
        {!!position.percentage && <span className="results-pct">{`${Math.trunc(position.percentage)}%`}</span>}
      </div>)}
    </div>)}
  </div>;
}

function Methodology() {
  return <div className="report-section" id="methodology">
    <h2 className="report-section-heading">Methodology</h2>
    <h3 className="report-section-sub-heading">Data sources</h3>
    <p className="muted" style={{fontSize: 13, marginBottom: '1rem'}}>Vote counts are drawn from the Polis Postgres database (<code>votes_latest_unique</code> view), which holds one vote per participant per statement. Opinion groups (clusters) are computed by the Polis math service and retrieved via the Particiapi results API. Where the two participant counts diverge by more than 5%, a warning is logged. Moderation exclusions (hidden statements, banned participants) are applied before any aggregation.</p>
    <h3 className="report-section-sub-heading">Aggregate opinion shift</h3>
    <p className="muted" style={{fontSize: 13, marginBottom: '1rem'}}>The shift column in the opinion-shift table is computed as <em>Phase 6 agree% − Phase 2 agree%</em>. This is a cross-round <strong>population comparison</strong>, not a paired before/after measurement: Phase 2 and Phase 6 participants are overlapping but not identical sets. A positive shift means the informed-voting cohort agreed at a higher rate, but this may partly reflect differences in who participated rather than genuine attitude change.</p>
    <h3 className="report-section-sub-heading">Individual delta and extrapolation</h3>
    <p className="muted" style={{fontSize: 13, marginBottom: '1rem'}}>Individual-level delta — the change in a specific participant's vote between rounds — is only observable for participants who voted in both Phase 2 and Phase 6. Extrapolating from this matched subset to the full initial-voting population requires statistical adjustment for the non-random selection of who returned for Phase 6.</p>
    <p className="report-placeholder" style={{fontSize: 13}}><em>Confidence interval methodology for the extrapolated delta is pending literature review. This section will describe the statistical method used once the approach is finalised.</em></p>
    <h3 className="report-section-sub-heading">Clustering</h3>
    <p className="muted" style={{fontSize: 13}}>Opinion groups are produced by the Polis algorithm: PCA reduces the participant × statement vote matrix to two dimensions, then k-means clustering groups participants by voting similarity. The number of groups is chosen by silhouette score. Consensus and representative statements for each group are selected by the Polis math service.</p>
  </div>;
}

function ResultsBody({report}: {report: Report}) {
  if (!report.resultsAvailable) return <div className="landing-section"><p className="muted">Informed voting results are not available for this consultation yet.</p></div>;
  return <>
    <ParticipationSummary report={report} />
    <div className="report-section">
      <h2 className="report-section-heading">Statements</h2>
      <p className="report-placeholder"><em>Statement inventory not yet available. This section will show: total statements submitted, how many were seed statements vs participant-proposed, and moderation outcomes.</em></p>
      <p className="muted" style={{fontSize: 13}}>Featured statements used in informed voting: {report.statements.length}</p>
    </div>
    <InitialOpinions statements={report.statements} />
    <div className="report-section">
      <h2 className="report-section-heading">Argument mapping</h2>
      <p className="report-placeholder"><em>Argument mapping summary not yet available. This section will show: arguments submitted per statement, most-upvoted pro/con arguments, and participation in argument voting.</em></p>
    </div>
    {report.dataAvailability.detailedCounts && <OpinionShift statements={report.statements} />}
    <div className="report-section">
      <h2 className="report-section-heading">Matched participant analysis</h2>
      <p className="report-placeholder"><em>Matched participant analysis not yet available. This section will show the individual-level opinion change for participants who voted in both rounds, and a population-level extrapolation with confidence intervals.</em></p>
      <p className="muted" style={{fontSize: 13}}>Note: delta is only directly observable for participants who cast a vote in both Phase 2 and Phase 6. Extrapolation to the full initial-voting cohort requires statistical adjustment; confidence intervals for this extrapolation are under development (pending methodology review).</p>
    </div>
    <OpinionGroups report={report} />
    {report.viewer.participating && report.opinionGroups.length > 0 && <div className="report-section report-section--explore">
      <h2 className="report-section-heading">Where did you land?</h2>
      <p className="muted" style={{fontSize: 13}}>Personalised group comparison — coming soon. This will show how your informed votes compare to each opinion group and where your views sit in the overall distribution.</p>
    </div>}
    <Methodology />
  </>;
}

export function FinalReportLegacyPage({report}: {report: Report}) {
  return <LegacyShell headerCrumb={<span className="header-crumb">
    <span className="header-crumb-sep">/</span>
    <span>{truncated(report.title, 40)}</span>
    <span className="header-crumb-sep">/</span>
    <span>report</span>
  </span>}>
    <div className="container" style={{maxWidth: 800}}>
      <p style={{marginBottom: '1.25rem'}}><InternalLink href={report.links.conversation} style={{fontSize: 13, color: 'var(--muted)', textDecoration: 'none'}}><span aria-hidden="true">←</span> {report.title}</InternalLink></p>
      <div className="report-header">
        <div>
          <h1 className="report-title">{report.title}</h1>
          <p className="report-subtitle">{`Final results report${report.closedAt ? ` · closed ${shortDate(report.closedAt)}` : ''}`}</p>
        </div>
        <span className="report-badge">Final</span>
      </div>
      <div className="report-section output-context">
        <h2 className="report-section-heading">How to read this output</h2>
        <dl className="output-context-grid">
          <div><dt>Produced from</dt><dd>{report.context.phase}</dd></div>
          <div><dt>Status</dt><dd>Final · frozen at publication</dd></div>
          <div><dt>Method</dt><dd>{report.context.method}</dd></div>
        </dl>
      </div>
      <PlaceholderSections />
      <ProcessTimeline report={report} />
      <ResultsBody report={report} />
      {report.viewer.revealState === 'open' && report.viewer.participating && <div className="reveal-callout" style={{marginTop: '2rem'}}>
        <p className="reveal-callout-text">The identity reveal window is open. Your participation is recorded under pseudonym <strong>{report.viewer.pseudonym}</strong>.</p>
        <InternalLink className="reveal-callout-link" href={report.links.identityReveal}>Optionally link your Wikimedia username <span aria-hidden="true">→</span></InternalLink>
      </div>}
    </div>
  </LegacyShell>;
}

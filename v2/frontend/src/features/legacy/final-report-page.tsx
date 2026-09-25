import type {components} from '../../api/schema';
import {LegacyShell} from './legacy-shell';
import {InternalLink} from '../../internal-link';
import {useMessage, type Message} from '../../i18n/messages';
import {escapeHtml, richHtml} from '../../i18n/rich-html';
import {useDateFormat} from '../../i18n/dates';
import {usePercentFormat} from '../../i18n/numbers';
import {outputMethod, outputPhase} from '../../i18n/server-labels';

type Report = components['schemas']['ResultsReport'];
type Statement = components['schemas']['ResultsStatement'];
type Tally = components['schemas']['VoteTally'];

function truncated(value: string, length: number) {
  return value.length > length ? `${value.slice(0, length - 1)}…` : value;
}

function LegacyVoteBar({tally}: {tally: Tally}) {
  const {percentages, counts} = tally;
  const msg = useMessage();
  const percentage = usePercentFormat();
  const title = msg('report-bar-title', percentage(percentages.agree), percentage(percentages.disagree), percentage(percentages.pass));
  return <>
    <div className="p6-vote-bar" title={title}>
      <div className="p6-bar-agree" style={{width: `${percentages.agree}%`}} />
      <div className="p6-bar-disagree" style={{width: `${percentages.disagree}%`}} />
      <div className="p6-bar-pass" style={{width: `${percentages.pass}%`}} />
    </div>
    <span className="p6-bar-label">{msg('report-bar-label', percentage(percentages.agree), percentage(percentages.pass), counts.voters)}</span>
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
  const msg = useMessage();
  return <>
    <div className="report-section">
      <h2 className="report-section-heading">{msg('report-intro-heading')}</h2>
      <p className="report-placeholder"><em>{msg('report-intro-placeholder')}</em></p>
    </div>
  </>;
}

function ProcessTimeline({report}: {report: Report}) {
  const dates = useDateFormat();
  const msg = useMessage();
  return <div className="report-section">
    <h2 className="report-section-heading">{msg('report-process-heading')}</h2>
    <div className="report-timeline">
      <div className="report-timeline-item">
        <span className="report-timeline-label">{msg('report-process-opened')}</span>
        <span className="report-timeline-value">{dates.date(report.openedAt)}</span>
      </div>
      {[msg('report-process-submission'), msg('report-process-argmap'), msg('report-process-informed')].map((label) => (
        <div className="report-timeline-item report-timeline-item--placeholder" key={label}>
          <span className="report-timeline-label">{label}</span>
          <span className="report-timeline-value report-placeholder-inline">{msg('report-process-dates-tbd')}</span>
        </div>
      ))}
      {report.closedAt && <div className="report-timeline-item">
        <span className="report-timeline-label">{msg('report-process-closed')}</span>
        <span className="report-timeline-value">{dates.date(report.closedAt)}</span>
      </div>}
    </div>
  </div>;
}

function ParticipationSummary({report}: {report: Report}) {
  const msg = useMessage();
  const statements = report.moderation.excludedStatements;
  const participants = report.moderation.excludedParticipants;
  const moderationSummary = `${msg('report-moderation-applied')} ${statements > 0 ? msg('report-moderation-stmts', statements) : ''}${participants > 0 ? ` ${msg('report-moderation-parts', participants)}` : ''}`;
  return <div className="report-section">
    <h2 className="report-section-heading">{msg('report-participation-heading')}</h2>
    <div className="report-stats-row">
      {!!report.participation.initialRound && <div className="report-stat">
        <span className="report-stat-value">{report.participation.initialRound}</span>
        <span className="report-stat-label">{msg('report-participation-p2')}</span>
      </div>}
      {!!report.participation.informedRound && <div className="report-stat">
        <span className="report-stat-value">{report.participation.informedRound}</span>
        <span className="report-stat-label">{msg('report-participation-p6')}</span>
      </div>}
      <div className="report-stat report-stat--placeholder">
        <span className="report-stat-value">—</span>
        <span className="report-stat-label">{msg('report-participation-both')}</span>
      </div>
    </div>
    {(statements > 0 || participants > 0) && <p className="report-moderation-note muted">{moderationSummary}</p>}
    {!report.dataAvailability.detailedCounts && <p className="muted" style={{fontSize: 13, marginTop: '.5rem'}}>{msg('report-participation-unavailable')}</p>}
  </div>;
}

function InitialOpinions({statements}: {statements: Statement[]}) {
  const msg = useMessage();
  const {consensus, divisive} = initialOpinionRows(statements);
  if (consensus.length === 0 && divisive.length === 0) return null;
  return <div className="report-section">
    <h2 className="report-section-heading">{msg('report-initial-heading')} <span className="report-section-sub">{msg('report-initial-sub')}</span></h2>
    <p className="muted" style={{fontSize: 13, marginBottom: '1rem'}}>{msg('report-initial-intro')}</p>
    {consensus.length > 0 && <>
      <h3 className="report-section-sub-heading">{msg('report-highest-agreement')}</h3>
      {consensus.map((statement) => <div className="report-stmt-row" key={`consensus-${statement.featuredStatementId}`}>
        <p className="report-stmt-text">{statement.statement}</p>
        <LegacyVoteBar tally={statement.initial!} />
      </div>)}
    </>}
    {divisive.length > 0 && <>
      <h3 className="report-section-sub-heading" style={{marginTop: '1.25rem'}}>{msg('report-most-divisive')}</h3>
      <p className="muted" style={{fontSize: 13, marginBottom: '.75rem'}}>{msg('report-divisive-intro')}</p>
      {divisive.map((statement) => <div className="report-stmt-row" key={`divisive-${statement.featuredStatementId}`}>
        <p className="report-stmt-text">{statement.statement}</p>
        <LegacyVoteBar tally={statement.initial!} />
      </div>)}
    </>}
  </div>;
}

function OpinionShift({statements}: {statements: Statement[]}) {
  const msg = useMessage();
  const percentage = usePercentFormat();
  if (statements.length === 0) return null;
  return <div className="report-section">
    <h2 className="report-section-heading">{msg('report-shift-heading')} <span className="report-section-sub">{msg('report-shift-sub')}</span></h2>
    <p className="muted" style={{fontSize: 13, marginBottom: '1rem'}}><span dangerouslySetInnerHTML={richHtml(msg('report-shift-intro', `<a href="#methodology" class="report-anchor">${escapeHtml(msg('report-methodology-link'))}</a>`))} /> {msg('report-shift-sorted')}</p>
    <table className="p6-results-table report-table" aria-label={msg('report-table-aria')}>
      <thead><tr>
        <th className="p6-col-stmt">{msg('report-col-statement')}</th>
        <th className="p6-col-phase">{msg('report-col-initial')}</th>
        <th className="p6-col-phase">{msg('report-col-informed')}</th>
        <th className="p6-col-shift">{msg('report-col-shift')} <span className="report-col-note">{msg('report-col-shift-note')}</span></th>
      </tr></thead>
      <tbody>{statements.map((statement) => <tr className="p6-results-row" key={statement.featuredStatementId}>
        <td className="p6-col-stmt">{statement.statement}</td>
        <td className="p6-col-phase">{statement.initial ? <LegacyVoteBar tally={statement.initial} /> : <span className="muted">—</span>}</td>
        <td className="p6-col-phase">{statement.informed && <LegacyVoteBar tally={statement.informed} />}</td>
        <td className="p6-col-shift">{statement.agreementShift === null
          ? <span className="muted">—</span>
          : <span className={`p6-shift${statement.agreementShift > 0 ? ' p6-shift--up' : statement.agreementShift < 0 ? ' p6-shift--down' : ''}`}>{percentage(statement.agreementShift, {signed: true})}</span>}
        </td>
      </tr>)}</tbody>
    </table>
  </div>;
}

function OpinionGroups({report}: {report: Report}) {
  const msg = useMessage();
  const percentage = usePercentFormat();
  if (report.opinionGroups.length === 0) return null;
  return <div className="report-section">
    <h2 className="report-section-heading">{msg('report-groups-heading')} <span className="report-section-sub">{msg('report-groups-sub', report.opinionGroups.length)}</span></h2>
    <p className="muted" style={{fontSize: 13, marginBottom: '1rem'}}>{msg('report-groups-intro')}</p>
    {report.opinionGroups.map((group, groupIndex) => <div className="results-block" style={{marginBottom: '1rem'}} key={group.label}>
      <p className="results-group-heading">{`\n        ${msg('report-group-label', groupIndex + 1)}\n        `}{!!group.memberCount && <span className="muted" style={{fontWeight: 400, fontSize: 12}}>{msg('report-group-members', group.memberCount)}</span>}{'\n      '}</p>
      {group.positions.map((position, index) => <div className="results-row" key={`${position.choice}-${index}`}>
        <span className={`results-badge results-${position.choice}`}>{position.choice === 'agree' ? msg('report-badge-agree') : msg('report-badge-disagree')}</span>
        {!!position.percentage && <span className="results-pct">{percentage(Math.trunc(position.percentage), {digits: 0})}</span>}
        <span className="results-text">{msg('conv-results-quoted', position.statement)}</span>
      </div>)}
    </div>)}
  </div>;
}

function Methodology() {
  const msg = useMessage();
  return <div className="report-section" id="methodology">
    <h2 className="report-section-heading">{msg('report-methodology-heading')}</h2>
    <h3 className="report-section-sub-heading">{msg('report-methodology-sources-heading')}</h3>
    <p className="muted" style={{fontSize: 13, marginBottom: '1rem'}} dangerouslySetInnerHTML={richHtml(msg('report-methodology-sources-body'))} />
    <h3 className="report-section-sub-heading">{msg('report-methodology-shift-heading')}</h3>
    <p className="muted" style={{fontSize: 13, marginBottom: '1rem'}} dangerouslySetInnerHTML={richHtml(msg('report-methodology-shift-body'))} />
    <h3 className="report-section-sub-heading">{msg('report-methodology-delta-heading')}</h3>
    <p className="muted" style={{fontSize: 13, marginBottom: '1rem'}}>{msg('report-methodology-delta-body')}</p>
    <p className="report-placeholder" style={{fontSize: 13}}><em>{msg('report-methodology-delta-placeholder')}</em></p>
    <h3 className="report-section-sub-heading">{msg('report-methodology-clustering-heading')}</h3>
    <p className="muted" style={{fontSize: 13}}>{msg('report-methodology-clustering-body')}</p>
  </div>;
}

function ResultsBody({report}: {report: Report}) {
  const msg = useMessage();
  if (!report.resultsAvailable) return <div className="landing-section"><p className="muted">{msg('report-no-results')}</p></div>;
  return <>
    <ParticipationSummary report={report} />
    <div className="report-section">
      <h2 className="report-section-heading">{msg('report-statements-heading')}</h2>
      <p className="report-placeholder"><em>{msg('report-statements-placeholder')}</em></p>
      <p className="muted" style={{fontSize: 13}}>{msg('report-featured-count', report.statements.length)}</p>
    </div>
    <InitialOpinions statements={report.statements} />
    <div className="report-section">
      <h2 className="report-section-heading">{msg('report-argmap-heading')}</h2>
      <p className="report-placeholder"><em>{msg('report-argmap-placeholder')}</em></p>
    </div>
    {report.dataAvailability.detailedCounts && <OpinionShift statements={report.statements} />}
    <div className="report-section">
      <h2 className="report-section-heading">{msg('report-matched-heading')}</h2>
      <p className="report-placeholder"><em>{msg('report-matched-placeholder')}</em></p>
      <p className="muted" style={{fontSize: 13}}>{msg('report-matched-note')}</p>
    </div>
    <OpinionGroups report={report} />
    {report.viewer.participating && report.opinionGroups.length > 0 && <div className="report-section report-section--explore">
      <h2 className="report-section-heading">{msg('report-landed-heading')}</h2>
      <p className="muted" style={{fontSize: 13}}>{msg('report-landed-body')}</p>
    </div>}
    <Methodology />
  </>;
}

export function FinalReportLegacyPage({report}: {report: Report}) {
  const dates = useDateFormat();
  const msg: Message = useMessage();
  const contextOutput = report.publication === 'final' ? 'report' : 'preliminary-results';
  return <LegacyShell headerCrumb={<span className="header-crumb">
    <span className="header-crumb-sep">/</span>
    <span>{truncated(report.title, 40)}</span>
    <span className="header-crumb-sep">/</span>
    <span>{msg('report-crumb')}</span>
  </span>}>
    <div className="container" style={{maxWidth: 800}}>
      <p style={{marginBottom: '1.25rem'}}><InternalLink href={report.links.conversation} style={{fontSize: 13, color: 'var(--muted)', textDecoration: 'none'}}><span className="dir-glyph" aria-hidden="true">←</span> {report.title}</InternalLink></p>
      <div className="report-header">
        <div>
          <h1 className="report-title">{report.title}</h1>
          <p className="report-subtitle">{`${msg('report-subtitle')}${report.closedAt ? ` ${msg('report-closed-suffix')} ${dates.date(report.closedAt)}` : ''}`}</p>
        </div>
        <span className="report-badge">{msg('report-badge-final')}</span>
      </div>
      <div className="report-section output-context">
        <h2 className="report-section-heading">{msg('output-howto-heading')}</h2>
        <dl className="output-context-grid">
          {/* The server takes this context from the output definition: "report" once the
              consultation is closed, "preliminary-results" before. */}
          <div><dt>{msg('output-produced-from')}</dt><dd>{outputPhase(msg, contextOutput, report.context.phase)}</dd></div>
          <div><dt>{msg('output-status-label')}</dt><dd>{msg('report-status-final')}</dd></div>
          <div><dt>{msg('output-method-label')}</dt><dd>{outputMethod(msg, contextOutput, report.context.method)}</dd></div>
        </dl>
      </div>
      <PlaceholderSections />
      <ProcessTimeline report={report} />
      <ResultsBody report={report} />
      {report.viewer.revealState === 'open' && report.viewer.participating && <div className="reveal-callout" style={{marginTop: '2rem'}}>
        <p className="reveal-callout-text" dangerouslySetInnerHTML={richHtml(msg('reveal-callout-open-text', escapeHtml(report.viewer.pseudonym ?? '')))} />
        <InternalLink className="reveal-callout-link" href={report.links.identityReveal}>{msg('reveal-callout-link')} <span className="dir-glyph" aria-hidden="true">→</span></InternalLink>
      </div>}
    </div>
  </LegacyShell>;
}

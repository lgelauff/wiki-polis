import {useSuspenseQuery} from '@tanstack/react-query';
import {useParams} from 'react-router-dom';

import type {components} from '../../api/schema';
import {
  conversationAboutQuery,
  conversationOutputQuery,
  moderationLogQuery,
} from '../../api/queries';
import {LegacyShell} from './legacy-shell';
import {InternalLink} from '../../internal-link';
import {useDateFormat} from '../../i18n/dates';
import {useLocale, useMessage} from '../../i18n/messages';
import {escapeHtml, richHtml} from '../../i18n/rich-html';
import {outputLabel, outputMethod, outputPending, outputPhase, outputStatus, phaseLabel} from '../../i18n/server-labels';

type OutputKey = components['schemas']['ConversationOutputDetail']['key'];

function requiredParam(name: string, value: string | undefined): string {
  if (!value) throw new Error(`Missing route parameter: ${name}`);
  return value;
}

function outputKey(value: string | undefined): OutputKey {
  const key = requiredParam('outputKey', value);
  if (!['initial-clustering', 'argument-map', 'preliminary-results', 'report', 'dataset'].includes(key)) {
    throw new Error(`Unknown output: ${key}`);
  }
  return key as OutputKey;
}

function truncated(value: string, length: number) {
  return value.length > length ? `${value.slice(0, length - 1)}…` : value;
}

/** A short list in the reader's language, e.g. "Explore, Arguments". */
function listOf(locale: string, items: string[]): string {
  try {
    return new Intl.ListFormat(locale === 'qqx' ? 'en' : locale, {type: 'unit', style: 'short'}).format(items);
  } catch {
    return items.join(', ');
  }
}

export function ConversationAboutLegacyPage() {
  const msg = useMessage();
  const locale = useLocale();
  const dates = useDateFormat();
  const slug = requiredParam('slug', useParams().slug);
  const {data} = useSuspenseQuery(conversationAboutQuery(slug));
  const transition = data.scheduledTransition;

  return (
    <LegacyShell
      headerMode={data.space === 'demo' ? 'conversation-demo' : 'conversation-real'}
      title={msg('about-doc-title', data.title)}
      headerCrumb={(
        <nav className="header-crumb" aria-label={msg('conv-crumb-aria')}>
          <span className="header-crumb-sep">/</span>
          <InternalLink href={`/c/${data.slug}`}>{truncated(data.title, 32)}</InternalLink>
          <span className="header-crumb-sep">/</span>
          <span>{msg('conv-crumb-about')}</span>
        </nav>
      )}
    >
      <div className="container">
        <p className="muted" style={{fontFamily: 'var(--mono)', fontSize: 11, textTransform: 'uppercase', letterSpacing: '.08em', marginBottom: '.5rem'}}>{msg('about-eyebrow')}</p>
        <h1>{msg('about-heading', data.title)}</h1>

        {data.descriptionHtml && <div className="intro-text" style={{marginTop: '1rem'}} dangerouslySetInnerHTML={{__html: data.descriptionHtml}} />}
        {data.outroHtml && <div className="outro-text" style={{marginTop: '1rem'}} dangerouslySetInnerHTML={{__html: data.outroHtml}} />}

        <div className="landing-section" style={{marginTop: '1.5rem'}}>
          <h2 className="section-heading">{msg('about-status-heading')}</h2>
          <p><strong>{msg('about-status-label')}</strong> {data.status === 'archived' ? msg('about-status-closed') : data.status === 'paused' ? msg('about-status-paused') : msg('about-status-open')}</p>
          <p><strong>{msg('about-phase-label')}</strong> {listOf(locale, data.phases.map((phase) => phaseLabel(msg, phase.key, phase.label)))}</p>
          {transition && (
            <p dangerouslySetInnerHTML={richHtml(msg('conv-scheduled-transition',
              escapeHtml(phaseLabel(msg, transition.target, transition.targetLabel)),
              `<time datetime="${escapeHtml(transition.at)}" title="${escapeHtml(msg('conv-scheduled-tz-title'))}">${escapeHtml(dates.dateTime(transition.at))}</time>`))} />
          )}
          {data.pseudonym && <p><strong>{msg('about-pseudonym-label')}</strong> <code>{data.pseudonym}</code></p>}
        </div>

        <div className="landing-section" style={{marginTop: '1rem'}}>
          <h2 className="section-heading">{msg('about-stats-heading')}</h2>
          <div className="stat-row" style={{display: 'flex', gap: '2rem', flexWrap: 'wrap'}}>
            {/* The unit follows the number's plural form; an unknown count takes the plural. */}
            <AboutStatistic value={data.statistics.participants} label={msg('about-stat-participants', data.statistics.participants ?? 2)} />
            <AboutStatistic value={data.statistics.statementVotes} label={msg('about-stat-statement-votes', data.statistics.statementVotes ?? 2)} />
            <AboutStatistic value={data.statistics.statements} label={msg('about-stat-statements', data.statistics.statements ?? 2)} />
            <AboutStatistic value={data.statistics.arguments} label={msg('about-stat-arguments', data.statistics.arguments ?? 2)} />
            <AboutStatistic value={data.statistics.argumentContributors} label={msg('about-stat-argument-contributors', data.statistics.argumentContributors ?? 2)} />
          </div>
          {data.statistics.participants === null && <p className="muted" style={{fontSize: 12, marginTop: '.8rem'}}>{msg('about-stats-unavailable')}</p>}
        </div>

        {data.personal && (
          <div className="landing-section" style={{marginTop: '1rem'}}>
            <h2 className="section-heading">{msg('about-contrib-heading')}</h2>
            <ul>
              <li>{msg('about-contrib-suggested', data.personal.statementsSuggested)}</li>
              <li>{data.personal.statementVotesAvailable
                ? msg('about-contrib-votes', data.personal.statementVotes ?? 0)
                : msg('about-contrib-votes-unavailable')}</li>
              <li>{msg('about-contrib-arguments-added', data.personal.argumentsAdded)}</li>
              <li>{msg('about-contrib-arguments-rated', data.personal.argumentsRated)}</li>
            </ul>
          </div>
        )}

        <div className="landing-section" style={{marginTop: '1rem'}}>
          <h2 className="section-heading">{msg('about-outputs-heading')}</h2>
          <ul>
            {data.outputs.map((output) => <li key={output.key}>
              {output.ready && output.href
                ? <InternalLink href={output.href}>{outputLabel(msg, output.key, output.label)}</InternalLink>
                : <>{outputLabel(msg, output.key, output.label)} <span className="muted">{msg('about-output-pending')}</span></>}
            </li>)}
          </ul>
        </div>

        <p style={{marginTop: '1.25rem'}}>
          <InternalLink href={`/c/${data.slug}/moderation-log`}>{data.moderation.eventCount > 0 ? msg('about-modlog-link-count', data.moderation.eventCount) : msg('conv-moderation-log')}</InternalLink>
          {' · '}<InternalLink href={`/c/${data.slug}`}>{msg('about-return')}</InternalLink>
        </p>
      </div>
    </LegacyShell>
  );
}

function AboutStatistic({value, label}: {value: number | null; label: string}) {
  return <span><strong>{value ?? '—'}</strong><br /><span className="muted">{label}</span></span>;
}

export function ModerationLogPage() {
  const msg = useMessage();
  const slug = requiredParam('slug', useParams().slug);
  const {data} = useSuspenseQuery(moderationLogQuery(slug));

  return (
    <LegacyShell
      title={msg('modlog-doc-title', data.title)}
      headerCrumb={(
        <nav className="header-crumb" aria-label={msg('conv-crumb-aria')}>
          <span className="header-crumb-sep">/</span>
          <InternalLink href={`/c/${data.slug}/moderation-log`}>{msg('conv-moderation-log')}</InternalLink>
        </nav>
      )}
    >
      <div className="container">
        <h1>{msg('modlog-heading', data.title)}</h1>
        <p className="muted" style={{fontSize: 13, marginBottom: '1.5rem'}}>{msg('modlog-intro')}</p>

        {data.events.length > 0 ? (
          <table className="admin-table">
            <thead><tr><th>{msg('modlog-th-when')}</th><th>{msg('modlog-th-action')}</th><th>{msg('modlog-th-pseudonym')}</th><th>{msg('modlog-th-scope')}</th><th>{msg('modlog-th-moderator')}</th></tr></thead>
            <tbody>
              {data.events.map((event, index) => (
                <tr key={`${event.occurredAt}-${event.pseudonym}-${index}`}>
                  <td className="muted">{event.occurredAt?.slice(0, 16).replace('T', ' ') ?? ''}</td>
                  <td>{event.action === 'Banned' ? msg('modlog-action-banned') : msg('modlog-action-unbanned')}</td>
                  <td>{event.pseudonym}</td>
                  <td>{msg('modlog-scope-conversation')}</td>
                  <td>{event.actor}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="muted">{msg('modlog-empty')}</p>
        )}
      </div>
    </LegacyShell>
  );
}

export function ConversationOutputPage() {
  const msg = useMessage();
  const params = useParams();
  const slug = requiredParam('slug', params.slug);
  const key = outputKey(params.outputKey);
  const {data} = useSuspenseQuery(conversationOutputQuery(slug, key));
  const output = data.output;

  return (
    <LegacyShell headerCrumb={(
      <span className="header-crumb">
        <span className="header-crumb-sep">/</span>
        <span>{data.title.length > 40 ? `${data.title.slice(0, 39)}…` : data.title}</span>
        <span className="header-crumb-sep">/</span>
        <span>{outputLabel(msg, output.key, output.label)}</span>
      </span>
    )}>
      <div className="container" style={{maxWidth: 800}}>
        <p style={{marginBottom: '1.25rem'}}>
          <InternalLink href={`/c/${data.slug}`} style={{fontSize: 13, color: 'var(--muted)', textDecoration: 'none'}}>
            <span aria-hidden="true">←</span> {data.title}
          </InternalLink>
        </p>

        <div className="output-page-header">
          <div>
            <p className="results-label">{msg('output-eyebrow', outputPhase(msg, output.key, output.phase))}</p>
            <h1 className="report-title">{outputLabel(msg, output.key, output.label)}</h1>
          </div>
          <span className="report-badge">{outputStatus(msg, output.status)}</span>
        </div>

        <div className="report-section output-context">
          <h2 className="report-section-heading">{msg('output-howto-heading')}</h2>
          <dl className="output-context-grid">
            <div><dt>{msg('output-produced-from')}</dt><dd>{outputPhase(msg, output.key, output.phase)}</dd></div>
            <div><dt>{msg('output-status-label')}</dt><dd className="output-status-value">{output.ready ? outputStatus(msg, output.status) : msg('output-status-pending', outputStatus(msg, output.status))}</dd></div>
            <div><dt>{msg('output-method-label')}</dt><dd>{outputMethod(msg, output.key, output.method)}</dd></div>
          </dl>
        </div>

        <div className="report-section">
          <OutputBody slug={data.slug} output={output} />
        </div>
      </div>
    </LegacyShell>
  );
}

function OutputBody({slug, output}: {
  slug: string;
  output: components['schemas']['ConversationOutputDetail'];
}) {
  const msg = useMessage();
  if (output.key === 'initial-clustering') return <>
    <h2 className="report-section-heading">{msg('output-initial-clustering-heading')}</h2>
    <p className="muted">{msg('output-initial-clustering-body')}</p>
    <p className="report-placeholder"><em>{msg('output-initial-clustering-note')}</em></p>
  </>;
  if (output.key === 'argument-map') return <>
    <h2 className="report-section-heading">{msg('output-argument-map-heading')}</h2>
    <p className="muted">{msg('output-argument-map-body')}</p>
    <p><InternalLink href={`/c/${slug}#tab-arguments`}>{msg('output-argument-map-link')} <span aria-hidden="true">→</span></InternalLink></p>
  </>;
  if (output.key === 'preliminary-results') return <>
    <h2 className="report-section-heading">{msg('output-preliminary-heading')}</h2>
    <p className="muted">{msg('output-preliminary-body')}</p>
    <p><InternalLink href={`/c/${slug}#tab-p6-results`}>{msg('output-preliminary-link')} <span aria-hidden="true">→</span></InternalLink></p>
  </>;
  if (output.key === 'dataset') return <>
    <h2 className="report-section-heading">{msg('output-dataset-heading')}</h2>
    <p className="muted">{msg('output-dataset-body')}</p>
    <p className="report-placeholder"><em>{msg('output-dataset-note')}</em></p>
  </>;
  return <>
    <h2 className="report-section-heading">{msg('output-tbd-heading')}</h2>
    <p className="muted">{outputPending(msg, output.key, output.pending)}</p>
  </>;
}

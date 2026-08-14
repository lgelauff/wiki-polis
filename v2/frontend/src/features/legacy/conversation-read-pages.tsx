import {useSuspenseQuery} from '@tanstack/react-query';
import {useParams} from 'react-router-dom';

import type {components} from '../../api/schema';
import {conversationOutputQuery, moderationLogQuery} from '../../api/queries';
import {LegacyShell} from './legacy-shell';

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

function capitalize(value: string) {
  return `${value.charAt(0).toUpperCase()}${value.slice(1)}`;
}

export function ModerationLogPage() {
  const slug = requiredParam('slug', useParams().slug);
  const {data} = useSuspenseQuery(moderationLogQuery(slug));

  return (
    <LegacyShell
      title={`Moderation log — ${data.title} — ProtoWiki`}
      headerCrumb={(
        <nav className="header-crumb" aria-label="Conversation context">
          <span className="header-crumb-sep">/</span>
          <a href={`/c/${data.slug}/moderation-log`}>Moderation log</a>
        </nav>
      )}
    >
      <div className="container">
        <h1>Moderation log — {data.title}</h1>
        <p className="muted" style={{fontSize: 13, marginBottom: '1.5rem'}}>
          Conversation-level bans and unbans are listed for accountability. Private moderator
          notes are not public.
        </p>

        {data.events.length > 0 ? (
          <table className="admin-table">
            <thead><tr><th>When</th><th>Action</th><th>Pseudonym</th><th>Scope</th><th>Moderator</th></tr></thead>
            <tbody>
              {data.events.map((event, index) => (
                <tr key={`${event.occurredAt}-${event.pseudonym}-${index}`}>
                  <td className="muted">{event.occurredAt?.slice(0, 16).replace('T', ' ') ?? ''}</td>
                  <td>{event.action}</td>
                  <td>{event.pseudonym}</td>
                  <td>{event.scope}</td>
                  <td>{event.actor}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="muted">No bans or unbans have been recorded for this conversation.</p>
        )}
      </div>
    </LegacyShell>
  );
}

export function ConversationOutputPage() {
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
        <span>{output.label}</span>
      </span>
    )}>
      <div className="container" style={{maxWidth: 800}}>
        <p style={{marginBottom: '1.25rem'}}>
          <a href={`/c/${data.slug}`} style={{fontSize: 13, color: 'var(--muted)', textDecoration: 'none'}}>
            <span aria-hidden="true">←</span> {data.title}
          </a>
        </p>

        <div className="output-page-header">
          <div>
            <p className="results-label">{output.phase} output</p>
            <h1 className="report-title">{output.label}</h1>
          </div>
          <span className="report-badge">{capitalize(output.status)}</span>
        </div>

        <div className="report-section output-context">
          <h2 className="report-section-heading">How to read this output</h2>
          <dl className="output-context-grid">
            <div><dt>Produced from</dt><dd>{output.phase}</dd></div>
            <div><dt>Status</dt><dd>{`${capitalize(output.status)}${output.ready ? '' : ' · pending'}`}</dd></div>
            <div><dt>Method</dt><dd>{output.method}</dd></div>
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
  if (output.key === 'initial-clustering') return <>
    <h2 className="report-section-heading">Consensus and breaking points</h2>
    <p className="muted">This page will summarize the Explore-phase statements that were broadly agreed on and the statements that divided participants. When clustering is stable enough, it will explain the opinion groups in plain language.</p>
    <p className="report-placeholder"><em>Detailed clustering visuals are still to be developed.</em></p>
  </>;
  if (output.key === 'argument-map') return <>
    <h2 className="report-section-heading">Featured statements and arguments</h2>
    <p className="muted">This page will collect the pro and con arguments for each featured statement and order them by participant support. Your own submitted arguments will be highlighted when you are signed in.</p>
    <p><a href={`/c/${slug}#tab-arguments`}>Open the current Arguments tab <span aria-hidden="true">→</span></a></p>
  </>;
  if (output.key === 'preliminary-results') return <>
    <h2 className="report-section-heading">Live informed-vote preview</h2>
    <p className="muted">Preliminary results are a lightweight, provisional view of the informed-voting round. They are not the official outcome and may change until the organizer publishes the final report.</p>
    <p><a href={`/c/${slug}#tab-p6-results`}>Open the preliminary results tab <span aria-hidden="true">→</span></a></p>
  </>;
  if (output.key === 'dataset') return <>
    <h2 className="report-section-heading">Raw pseudonymous export</h2>
    <p className="muted">The dataset will provide raw pseudonymous rows for independent analysis and replication. It will not expose xid, Wikimedia user IDs, or private identity links.</p>
    <p className="report-placeholder"><em>Dataset export is still to be developed.</em></p>
  </>;
  return <>
    <h2 className="report-section-heading">To be developed</h2>
    <p className="muted">{output.pending}</p>
  </>;
}

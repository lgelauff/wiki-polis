import {useCallback, useId, useState, type FormEvent, type ReactNode} from 'react';
import {useMutation, useQueryClient, useSuspenseQuery} from '@tanstack/react-query';
import {useNavigate} from 'react-router-dom';

import type {components} from '../../api/schema';
import {ApiContractError} from '../../api/client';
import {
  adminCatalogQuery,
  postAdminConversation,
  postGlobalAdminGrant,
  putGlobalAdmin,
} from '../../api/queries';
import {AdminComing} from './admin-coming';
import {AdminShell} from './admin-shell';
import {LegacyToast, type LegacyToastMessage} from '../legacy/legacy-toast';
import {InternalLink} from '../../internal-link';
import {useMessage, type Message} from '../../i18n/messages';
import {accessPolicyLabel} from '../../i18n/server-labels';

type Catalog = components['schemas']['AdminCatalog'];
type CreateRequest = components['schemas']['AdminConversationCreateRequest'];
type Row = Catalog['conversations'][number];

const emptyConversation: CreateRequest = {
  slug: '', title: '', introHtml: '', outroHtml: '', accessPolicy: 'public',
  phaseRoute: '', eligibilityEventId: '', eligibilityLabel: '', polisId: null,
};

/** The server's own status word, in the console's wording. `closed` and `archived` are two
 *  different things and the table has to say which one it is. */
function statusLabel(msg: Message, status: Row['status']): string {
  switch (status) {
    case 'active': return msg('admin-status-active');
    case 'paused': return msg('admin-status-paused');
    case 'closed': return msg('admin-status-closed');
    case 'archived': return msg('admin-status-archived');
  }
}

function errorMessage(error: Error | null) {
  if (!error) return null;
  return error instanceof ApiContractError ? error.message : null;
}

/** One row: title, who gets in, where it stands, and the three ways into it. */
function ConversationRow({conversation}: {conversation: Row}) {
  const msg = useMessage();
  return (
    <tr>
      <td><InternalLink href={conversation.links.participant}>{conversation.title}</InternalLink></td>
      <td>{accessPolicyLabel(msg, conversation.accessPolicy)}</td>
      {/* The status is a word, not a badge: plain text in the spec's words. */}
      <td>{statusLabel(msg, conversation.status)}</td>
      <td>
        <InternalLink href={conversation.links.manage} className="admin-row__link">
          {msg('admin-btn-manage')}
        </InternalLink>
        {' '}
        {/* The settings page hangs off the manage path the server itself builds
            (`_admin_client_link` in app.py), so the link is derived from that link
            rather than from a second copy of the admin route table here. */}
        <InternalLink href={`${conversation.links.manage}/settings`} className="admin-row__link">
          {msg('admin-overview-card-settings')}
        </InternalLink>
      </td>
    </tr>
  );
}

/** The column names every table of consultations on this page shares, so a cell in a
 *  group is named the same way as one in the main table. */
function ColumnHeads() {
  const msg = useMessage();
  return (
    <thead><tr><th>{msg('admin-th-title')}</th><th>{msg('admin-th-policy')}</th><th>{msg('admin-th-status')}</th><th>{msg('admin-th-actions')}</th></tr></thead>
  );
}

/**
 * A group of rows under the table, closed by default and never remembered.
 *
 * What is in the Practice Environment is not a consultation (#472), so it is not listed
 * among the consultations: it goes here instead, under its own name. A practice item that
 * is also archived or closed is still a practice item first -- the space it sits in is the
 * fact that decides where it belongs, not how far it got.
 */
function Group({label, count, children}: {label: string; count: number; children: ReactNode}) {
  return (
    <details className="admin-group">
      <summary>{label}{' '}<span className="admin-count">{count}</span></summary>
      <div className="admin-table-wrap">
        <table className="admin-table">
          <ColumnHeads />
          <tbody>{children}</tbody>
        </table>
      </div>
    </details>
  );
}

export function AdminCatalogPage({csrfToken}: {csrfToken: string}) {
  const msg = useMessage();
  const navigate = useNavigate();
  const options = adminCatalogQuery();
  const {data} = useSuspenseQuery(options);
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState<CreateRequest>({
    ...emptyConversation,
    phaseRoute: data.phaseRoutes[0]?.key ?? '',
  });
  const [username, setUsername] = useState('');
  // Each form's refusal is said at the form; the toast is for the row action (remove).
  const [createError, setCreateError] = useState<string | null>(null);
  const [grantError, setGrantError] = useState<string | null>(null);
  const [toast, setToast] = useState<LegacyToastMessage | null>(null);
  const dismissToast = useCallback(() => setToast(null), []);
  const grantErrorId = useId();

  function replaceCatalog(catalog: Catalog) {
    queryClient.setQueryData<Catalog>(options.queryKey, catalog);
  }

  const creation = useMutation({
    mutationFn: () => postAdminConversation(draft, csrfToken),
    onSuccess: (result) => { navigate(result.links.manage); },
    onError: (error: Error) => setCreateError(errorMessage(error) ?? msg('adminconv-command-failed')),
  });
  const grant = useMutation({
    mutationFn: () => postGlobalAdminGrant({username}, csrfToken),
    onSuccess: (result) => {
      replaceCatalog(result.catalog);
      setUsername('');
      setGrantError(null);
    },
    onError: (error: Error) => {
      // Said at the field, which keeps what was typed so one letter can be corrected. The
      // server's own refusal for a name nobody has signed in with is keyed, worded exactly
      // as it always has been (#479, default f).
      setGrantError(error instanceof ApiContractError && error.code === 'participant_not_found'
        ? msg('admin-site-grant-not-found', username)
        : errorMessage(error) ?? msg('adminconv-command-failed'));
    },
  });
  const membership = useMutation({
    mutationFn: ({participantId, granted}: {participantId: number; granted: boolean}) => (
      putGlobalAdmin(participantId, {granted}, csrfToken)
    ),
    onSuccess: (result) => {
      replaceCatalog(result.catalog);
    },
    onError: (error: Error) => setToast({
      id: Date.now(),
      category: 'error',
      message: errorMessage(error) ?? msg('adminconv-command-failed'),
    }),
  });

  function submitConversation(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    creation.mutate();
  }

  function submitGrant(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    grant.mutate();
  }

  const practice = data.conversations.filter((row) => row.accessPolicy === 'demo');
  const archived = data.conversations.filter(
    (row) => row.accessPolicy !== 'demo' && row.status === 'archived',
  );
  const consultations = data.conversations.filter(
    (row) => row.accessPolicy !== 'demo' && row.status !== 'archived',
  );

  return (
    <AdminShell
      site={msg('admin-site-dashboard')}
      title={`${msg('admin-site-dashboard')} — Proto`}
      toast={<LegacyToast toast={toast} onDismiss={dismissToast} />}
    >
      <div className="admin-page">
        <h1>{msg('admin-site-dashboard')}</h1>

        <h2 id="admin-convs-heading">{msg('admin-convs-heading')}</h2>
        {/* The table scrolls inside its own box when its columns cannot shrink to the
            screen (320px), so the page itself never scrolls sideways. */}
        <div className="admin-table-wrap">
          <table className="admin-table" aria-labelledby="admin-convs-heading">
            <ColumnHeads />
            <tbody>{consultations.map((conversation) => (
              <ConversationRow key={conversation.id} conversation={conversation} />
            ))}</tbody>
          </table>
        </div>

        {practice.length > 0 && <Group label={msg('base-mode-demo')} count={practice.length}>
          {practice.map((conversation) => (
            <ConversationRow key={conversation.id} conversation={conversation} />
          ))}
        </Group>}

        {archived.length > 0 && <Group label={msg('admin-site-group-other')} count={archived.length}>
          {archived.map((conversation) => (
            <ConversationRow key={conversation.id} conversation={conversation} />
          ))}
        </Group>}


        <div className="admin-form">
          <h2>{msg('admin-new-conv-heading')}</h2>
          <form onSubmit={submitConversation}>
            <label className="admin-field admin-field--medium">{msg('admin-label-slug')}<input type="text" className="admin-mono" placeholder={msg('admin-slug-ph')} required pattern="[a-z0-9]+(-[a-z0-9]+)*" title={msg('admin-slug-title')} value={draft.slug} onChange={(event) => setDraft({...draft, slug: event.target.value})} /></label>
            <label className="admin-field">{msg('admin-label-title')}<input type="text" required value={draft.title} onChange={(event) => setDraft({...draft, title: event.target.value})} /></label>
            <label className="admin-field admin-field--medium">{msg('admin-label-access')}<select value={draft.accessPolicy} onChange={(event) => setDraft({...draft, accessPolicy: event.target.value as CreateRequest['accessPolicy']})}><option value="public">{msg('admin-common-policy-open')}</option><option value="invite_only">{msg('admin-common-policy-invited')}</option><option value="demo">{msg('admin-common-policy-practice')}</option></select></label>
            <label className="admin-field admin-field--medium">{msg('admin-label-route')}<select value={draft.phaseRoute} onChange={(event) => setDraft({...draft, phaseRoute: event.target.value})}>{data.phaseRoutes.map((route) => <option key={route.key} value={route.key}>{route.label}</option>)}</select></label>
            {/* The eligibility pair stays as it was (#406 follow-up). */}
            <label className="admin-field admin-field--medium">{msg('admin-label-elig-event')}<input type="text" maxLength={80} placeholder={msg('admin-elig-event-ph')} value={draft.eligibilityEventId} onChange={(event) => setDraft({...draft, eligibilityEventId: event.target.value})} /></label>
            <label className="admin-field admin-field--medium">{msg('admin-label-elig-label')}<input type="text" maxLength={255} placeholder={msg('admin-elig-label-ph')} value={draft.eligibilityLabel} onChange={(event) => setDraft({...draft, eligibilityLabel: event.target.value})} /></label>
            <label className="admin-field">{msg('admin-label-intro')}<textarea rows={4} value={draft.introHtml} onChange={(event) => setDraft({...draft, introHtml: event.target.value})} /></label>
            <label className="admin-field">{msg('admin-label-outro')}<textarea rows={4} value={draft.outroHtml} onChange={(event) => setDraft({...draft, outroHtml: event.target.value})} /></label>
            <div className="admin-form__actions">
              <button type="submit" className="admin-button admin-button--primary" disabled={creation.isPending}>{msg('admin-btn-create-conv')}</button>
            </div>
            {createError && <p className="admin-error" role="alert">{createError}</p>}
          </form>
        </div>

        <h2>{msg('admin-globals-heading')}</h2>
        {/* One row per site admin: a list, not a table, since there is one column. */}
        {data.globalAdmins.length ? <ul className="admin-rows">
          {data.globalAdmins.map((admin) => <li className="admin-row" key={admin.participantId}>
            <div className="admin-row__text">{admin.username}</div>
            <div className="admin-row__actions">
              <button type="button" className="admin-row__text-button" disabled={membership.isPending} onClick={() => membership.mutate({participantId: admin.participantId, granted: false})}>{msg('admin-btn-remove')}{' '}<span className="sr-only">{`— ${admin.username}`}</span></button>
            </div>
          </li>)}
        </ul> : <p className="admin-empty">{msg('admin-globals-empty')}</p>}
        <div className="admin-form">
          <h2>{msg('admin-grant-heading')}</h2>
          <form onSubmit={submitGrant}>
            <label className="admin-field admin-field--medium">{msg('admin-label-wm-username')}<input type="text" required autoComplete="off" value={username}
              {...(grantError ? {'aria-invalid': true, 'aria-describedby': grantErrorId} : {})}
              onChange={(event) => setUsername(event.target.value)} /></label>
            {grantError && <p className="admin-error" id={grantErrorId} role="alert">{grantError}</p>}
            <div className="admin-form__actions">
              <button type="submit" className="admin-button admin-button--primary" disabled={grant.isPending}>{msg('admin-btn-grant')}</button>
            </div>
          </form>
        </div>

        {/* What is not built yet, last on the page (see `AdminComing`). */}
        <AdminComing what="phase, participation counts, organizers, last action, and following or hiding a consultation" issue={473} />
        <AdminComing what="voucher use, correct and wrong codes per consultation" issue={473} />
      </div>
    </AdminShell>
  );
}

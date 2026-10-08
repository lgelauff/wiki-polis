import {useCallback, useState, type FormEvent, type ReactNode} from 'react';
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
import {LegacyShell} from '../legacy/legacy-shell';
import {LegacyToast, type LegacyToastMessage} from '../legacy/legacy-toast';
import {InternalLink} from '../../internal-link';
import {useMessage, type Message} from '../../i18n/messages';
import {richHtml} from '../../i18n/rich-html';
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

/** The badge class each status has always had: the class is the styling, the word is the
 *  information. */
function statusClass(status: Row['status']): string {
  if (status === 'active') return 'badge-active-inline';
  if (status === 'paused') return 'badge-paused-inline';
  return 'badge-inactive';
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
      <td>
        <span className={statusClass(conversation.status)}>{statusLabel(msg, conversation.status)}</span>
      </td>
      <td>
        <InternalLink href={conversation.links.manage} className="btn-small">
          {msg('admin-btn-manage')}
        </InternalLink>
        {' '}
        {/* The settings page hangs off the manage path the server itself builds
            (`_admin_client_link` in app.py), so the link is derived from that link
            rather than from a second copy of the admin route table here. */}
        <InternalLink href={`${conversation.links.manage}/settings`} className="btn-small">
          {msg('admin-site-link-settings')}
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
    <thead><tr><th>{msg('admin-th-title')}</th><th>{msg('admin-th-policy')}</th><th>{msg('admin-th-status')}</th><th /></tr></thead>
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
      <summary>{label} ({count})</summary>
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
  const [toast, setToast] = useState<LegacyToastMessage | null>(null);
  const dismissToast = useCallback(() => setToast(null), []);

  function replaceCatalog(catalog: Catalog) {
    queryClient.setQueryData<Catalog>(options.queryKey, catalog);
  }

  const creation = useMutation({
    mutationFn: () => postAdminConversation(draft, csrfToken),
    onSuccess: (result) => { navigate(result.links.manage); },
    onError: (error: Error) => setToast({
      id: Date.now(),
      category: 'error',
      message: errorMessage(error) ?? msg('adminconv-command-failed'),
    }),
  });
  const grant = useMutation({
    mutationFn: () => postGlobalAdminGrant({username}, csrfToken),
    onSuccess: (result) => {
      replaceCatalog(result.catalog);
      setUsername('');
    },
    onError: (error: Error) => {
      const attempted = username;
      setUsername('');
      document.documentElement.scrollTop = 0;
      document.body.scrollTop = 0;
      setToast({
        id: Date.now(),
        category: 'error',
        // The server's own refusal for a name nobody has signed in with; keyed now, worded
        // exactly as it always has been (#479, default f).
        message: error instanceof ApiContractError && error.code === 'participant_not_found'
          ? msg('admin-site-grant-not-found', attempted)
          : errorMessage(error) ?? msg('adminconv-command-failed'),
      });
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
    <LegacyShell
      headerMode="admin"
      title={`${msg('admin-site-dashboard')} — Proto`}
      headerCrumb={<nav className="header-crumb" aria-label="Admin breadcrumb"><span className="header-crumb-sep">/</span><span>{msg('admin-site-dashboard')}</span></nav>}
      toast={<LegacyToast toast={toast} onDismiss={dismissToast} />}
    >
      <div className="container">
        <h2>{msg('admin-site-dashboard')}</h2>


        <h3 className="section-heading" id="admin-convs-heading">{msg('admin-convs-heading')}</h3>
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


        <div className="edit-form">
          <h3>{msg('admin-new-conv-heading')}</h3>
          <form onSubmit={submitConversation}>
            <div className="edit-row-fields">
              <label>{msg('admin-label-slug')}<input type="text" placeholder={msg('admin-slug-ph')} required pattern="[a-z0-9]+(-[a-z0-9]+)*" title={msg('admin-slug-title')} value={draft.slug} onChange={(event) => setDraft({...draft, slug: event.target.value})} /></label>
              <label>{msg('admin-label-title')}<input type="text" required value={draft.title} onChange={(event) => setDraft({...draft, title: event.target.value})} /></label>
              <label>{msg('admin-label-access')}<select value={draft.accessPolicy} onChange={(event) => setDraft({...draft, accessPolicy: event.target.value as CreateRequest['accessPolicy']})}><option value="public">{msg('admin-common-policy-open')}</option><option value="invite_only">{msg('admin-common-policy-invited')}</option><option value="demo">{msg('admin-common-policy-practice')}</option></select></label>
              <label>{msg('admin-label-route')}<select value={draft.phaseRoute} onChange={(event) => setDraft({...draft, phaseRoute: event.target.value})}>{data.phaseRoutes.map((route) => <option key={route.key} value={route.key}>{route.label}</option>)}</select></label>
              <label>{msg('admin-label-elig-event')}<input type="text" maxLength={80} placeholder={msg('admin-elig-event-ph')} value={draft.eligibilityEventId} onChange={(event) => setDraft({...draft, eligibilityEventId: event.target.value})} /></label>
              <label>{msg('admin-label-elig-label')}<input type="text" maxLength={255} placeholder={msg('admin-elig-label-ph')} value={draft.eligibilityLabel} onChange={(event) => setDraft({...draft, eligibilityLabel: event.target.value})} /></label>
            </div>
            <div className="edit-row-texts">
              <label>{msg('admin-label-intro')}<textarea rows={4} value={draft.introHtml} onChange={(event) => setDraft({...draft, introHtml: event.target.value})} /></label>
              <label>{msg('admin-label-outro')}<textarea rows={4} value={draft.outroHtml} onChange={(event) => setDraft({...draft, outroHtml: event.target.value})} /></label>
            </div>
            <button type="submit" disabled={creation.isPending}>{msg('admin-btn-create-conv')}</button>
          </form>
        </div>

        <h3 className="section-heading">{msg('admin-globals-heading')}</h3>
        <p
          className="muted"
          style={{fontSize: 13, marginBottom: '.75rem'}}
          dangerouslySetInnerHTML={richHtml(msg('admin-globals-intro'))}
        />
        {data.globalAdmins.length ? <table className="admin-table">
          <thead><tr><th>{msg('admin-th-username')}</th><th /></tr></thead>
          <tbody>{data.globalAdmins.map((admin) => <tr key={admin.participantId}>
            <td>{admin.username}</td>
            <td><button type="button" className="btn-small btn-danger" disabled={membership.isPending} onClick={() => membership.mutate({participantId: admin.participantId, granted: false})}>{msg('admin-btn-remove')}</button></td>
          </tr>)}</tbody>
        </table> : <p className="muted" style={{fontSize: 14, marginBottom: '1rem'}}>{msg('admin-globals-empty')}</p>}
        <div className="edit-form">
          <h3>{msg('admin-grant-heading')}</h3>
          <form onSubmit={submitGrant}>
            <div className="edit-row-fields"><label>{msg('admin-label-wm-username')}<input type="text" required autoComplete="off" placeholder={msg('admin-wm-username-ph')} style={{width: 260}} value={username} onChange={(event) => setUsername(event.target.value)} /></label></div>
            <button type="submit" disabled={grant.isPending}>{msg('admin-btn-grant')}</button>
          </form>
        </div>

        {/* What is not built yet, last on the page (see `AdminComing`). */}
        <AdminComing what="Admin home, one table of the consultations you have a role in" issue={473} />
        <AdminComing what="phase, participation counts, organizers, last action, and following or hiding a consultation" issue={473} />
        <AdminComing what="voucher use, correct and wrong codes per consultation" issue={473} />
      </div>
    </LegacyShell>
  );
}

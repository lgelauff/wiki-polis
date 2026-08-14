import {useState, type FormEvent} from 'react';
import {useMutation, useQueryClient, useSuspenseQuery} from '@tanstack/react-query';

import type {components} from '../../api/schema';
import {ApiContractError} from '../../api/client';
import {
  adminCatalogQuery,
  postAdminConversation,
  postGlobalAdminGrant,
  putGlobalAdmin,
} from '../../api/queries';
import {LegacyShell} from '../legacy/legacy-shell';

type Catalog = components['schemas']['AdminCatalog'];
type CreateRequest = components['schemas']['AdminConversationCreateRequest'];

const emptyConversation: CreateRequest = {
  slug: '', title: '', introHtml: '', outroHtml: '', accessPolicy: 'public',
  phaseRoute: '', eligibilityEventId: '', eligibilityLabel: '', polisId: null,
};

function errorMessage(error: Error | null) {
  if (!error) return null;
  return error instanceof ApiContractError
    ? error.message
    : 'The site operation could not be completed.';
}

export function AdminCatalogPage({csrfToken}: {csrfToken: string}) {
  const options = adminCatalogQuery();
  const {data} = useSuspenseQuery(options);
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState<CreateRequest>({
    ...emptyConversation,
    phaseRoute: data.phaseRoutes[0]?.key ?? '',
  });
  const [username, setUsername] = useState('');
  const [receipt, setReceipt] = useState<string | null>(null);

  function replaceCatalog(catalog: Catalog) {
    queryClient.setQueryData<Catalog>(options.queryKey, catalog);
  }

  const creation = useMutation({
    mutationFn: () => postAdminConversation(draft, csrfToken),
    onSuccess: (result) => { globalThis.location.assign(result.links.manage); },
  });
  const grant = useMutation({
    mutationFn: () => postGlobalAdminGrant({username}, csrfToken),
    onSuccess: (result) => {
      replaceCatalog(result.catalog);
      setUsername('');
      setReceipt(result.changed
        ? `${result.username} granted site-wide administration.`
        : `${result.username} already has site-wide administration.`);
    },
  });
  const membership = useMutation({
    mutationFn: ({participantId, granted}: {participantId: number; granted: boolean}) => (
      putGlobalAdmin(participantId, {granted}, csrfToken)
    ),
    onSuccess: (result) => {
      replaceCatalog(result.catalog);
      setReceipt(`${result.username} removed from site-wide administration.`);
    },
  });
  const activeError = creation.error ?? grant.error ?? membership.error;

  function submitConversation(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    creation.mutate();
  }

  function submitGrant(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    grant.mutate();
  }

  return (
    <LegacyShell
      headerMode="admin"
      title="Admin panel — ProtoWiki"
      headerCrumb={<nav className="header-crumb" aria-label="Admin breadcrumb"><span className="header-crumb-sep">/</span><span>Admin panel</span></nav>}
    >
      <div className="container">
        <h2>Admin panel</h2>

        {(receipt || activeError) && <p className="muted" role="status">{errorMessage(activeError) ?? receipt}</p>}

        <h3 className="section-heading">Conversations</h3>
        <table className="admin-table">
          <thead><tr><th>Title</th><th>Slug</th><th>Policy</th><th>Status</th><th /></tr></thead>
          <tbody>{data.conversations.map((conversation) => (
            <tr key={conversation.id}>
              <td><a href={conversation.links.participant}>{conversation.title}</a></td>
              <td><code>{conversation.slug}</code></td>
              <td>{conversation.accessPolicy}</td>
              <td>{conversation.status === 'active'
                ? <span className="badge-active-inline">active</span>
                : conversation.status === 'paused'
                  ? <span className="badge-paused-inline">paused</span>
                  : <span className="badge-inactive">closed</span>}</td>
              <td><a href={conversation.links.manage} className="btn-small">manage</a></td>
            </tr>
          ))}</tbody>
        </table>

        <div className="edit-form">
          <h3>New conversation</h3>
          <form onSubmit={submitConversation}>
            <div className="edit-row-fields">
              <label>Slug (URL-safe, immutable)<input type="text" placeholder="e.g. rfc-2024-adminship" required pattern="[a-z0-9]+(-[a-z0-9]+)*" title="Lowercase letters, numbers, and hyphens only — no spaces or special characters (e.g. climate-2026)" value={draft.slug} onChange={(event) => setDraft({...draft, slug: event.target.value})} /></label>
              <label>Title<input type="text" required value={draft.title} onChange={(event) => setDraft({...draft, title: event.target.value})} /></label>
              <label>Access policy<select value={draft.accessPolicy} onChange={(event) => setDraft({...draft, accessPolicy: event.target.value as CreateRequest['accessPolicy']})}><option value="public">public</option><option value="invite_only">invite_only</option><option value="demo">demo</option></select></label>
              <label>Route<select value={draft.phaseRoute} onChange={(event) => setDraft({...draft, phaseRoute: event.target.value})}>{data.phaseRoutes.map((route) => <option key={route.key} value={route.key}>{route.label}</option>)}</select></label>
              <label>Eligibility event ID<input type="text" maxLength={80} placeholder="optional AccountEligibility event" value={draft.eligibilityEventId} onChange={(event) => setDraft({...draft, eligibilityEventId: event.target.value})} /></label>
              <label>Eligibility label<input type="text" maxLength={255} placeholder="optional criteria summary" value={draft.eligibilityLabel} onChange={(event) => setDraft({...draft, eligibilityLabel: event.target.value})} /></label>
            </div>
            <div className="edit-row-texts">
              <label>Intro text (HTML, optional)<textarea rows={4} value={draft.introHtml} onChange={(event) => setDraft({...draft, introHtml: event.target.value})} /></label>
              <label>Outro text (HTML, optional)<textarea rows={4} value={draft.outroHtml} onChange={(event) => setDraft({...draft, outroHtml: event.target.value})} /></label>
            </div>
            <button type="submit" disabled={creation.isPending}>Create conversation</button>
          </form>
        </div>

        <h3 className="section-heading">Global admins</h3>
        <p className="muted" style={{fontSize: 13, marginBottom: '.75rem'}}>Global admins have platform-wide access to all conversations and settings. To assign a moderator or organizer to a specific conversation, use <strong>manage → conversation roles</strong> on that conversation.</p>
        {data.globalAdmins.length ? <table className="admin-table">
          <thead><tr><th>Participant</th><th /></tr></thead>
          <tbody>{data.globalAdmins.map((admin) => <tr key={admin.participantId}>
            <td>{admin.username}</td>
            <td><button type="button" className="btn-small btn-danger" disabled={membership.isPending} onClick={() => membership.mutate({participantId: admin.participantId, granted: false})}>remove</button></td>
          </tr>)}</tbody>
        </table> : <p className="muted" style={{fontSize: 14, marginBottom: '1rem'}}>No global admins assigned.</p>}
        <div className="edit-form">
          <h3>Grant global admin</h3>
          <form onSubmit={submitGrant}>
            <div className="edit-row-fields"><label>Wikimedia username<input type="text" required autoComplete="off" placeholder="Type a username…" style={{width: 260}} value={username} onChange={(event) => setUsername(event.target.value)} /></label></div>
            <button type="submit" disabled={grant.isPending}>Grant</button>
          </form>
        </div>
      </div>
    </LegacyShell>
  );
}

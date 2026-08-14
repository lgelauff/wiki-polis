import {useState, type FormEvent} from 'react';
import {useMutation, useQueryClient, useSuspenseQuery} from '@tanstack/react-query';
import {Link, useNavigate} from 'react-router-dom';

import type {components} from '../../api/schema';
import {ApiContractError} from '../../api/client';
import {
  adminCatalogQuery,
  postAdminConversation,
  postGlobalAdminGrant,
  putGlobalAdmin,
} from '../../api/queries';

type Catalog = components['schemas']['AdminCatalog'];
type CreateRequest = components['schemas']['AdminConversationCreateRequest'];

function errorMessage(error: Error | null, fallback: string) {
  if (!error) return null;
  return error instanceof ApiContractError ? error.message : fallback;
}

const emptyConversation: CreateRequest = {
  slug: '', title: '', introHtml: '', outroHtml: '', accessPolicy: 'public',
  phaseRoute: '', eligibilityEventId: '', eligibilityLabel: '', polisId: null,
};

export function AdminCatalogPage({csrfToken}: {csrfToken: string}) {
  const options = adminCatalogQuery();
  const {data} = useSuspenseQuery(options);
  const queryClient = useQueryClient();
  const navigate = useNavigate();
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
    onSuccess: (result) => navigate(result.links.manage),
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
      setReceipt(result.granted
        ? `${result.username} granted site-wide administration.`
        : `${result.username} removed from site-wide administration.`);
    },
  });

  function submitConversation(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    creation.mutate();
  }
  function submitGrant(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    grant.mutate();
  }
  const activeError = creation.error ?? grant.error ?? membership.error;

  return (
    <main className="admin-catalog" id="main">
      <header className="admin-catalog__heading">
        <div><p className="eyebrow">Site operations</p><h1>Admin panel</h1><p>Create conversations, enter their workspaces, and manage platform-wide access.</p></div>
        <strong>{data.conversations.length}<span>conversation{data.conversations.length === 1 ? '' : 's'}</span></strong>
      </header>
      {(receipt || activeError) && <p className="lifecycle-receipt" data-error={Boolean(activeError)} role="status">{errorMessage(activeError, 'The site operation could not be completed.') ?? receipt}</p>}

      <section className="admin-catalog__conversations" aria-labelledby="catalog-conversations-heading">
        <div className="lifecycle-section-heading"><div><p className="eyebrow">Portfolio</p><h2 id="catalog-conversations-heading">Conversations</h2></div></div>
        {data.conversations.length ? <ol>{data.conversations.map((conversation, index) => (
          <li key={conversation.id}>
            <span>{String(index + 1).padStart(2, '0')}</span>
            <div><h3>{conversation.title}</h3><p><code>{conversation.slug}</code> · {conversation.accessPolicy.replace('_', ' ')}</p></div>
            <strong data-state={conversation.status}>{conversation.status}</strong>
            <div><a href={conversation.links.participant}>Participant view ↗</a><Link to={conversation.links.manage}>Manage</Link></div>
          </li>
        ))}</ol> : <p className="featured-empty">No conversations have been created.</p>}
      </section>

      <section className="admin-catalog__create" aria-labelledby="create-conversation-heading">
        <header><p className="eyebrow">New record</p><h2 id="create-conversation-heading">Create conversation</h2><p>{data.creation.mode === 'managed' ? 'The linked Polis conversation will be created automatically.' : 'This environment requires an existing Polis conversation ID.'} New participant statements start pending review.</p></header>
        <form onSubmit={submitConversation}>
          <label>Title<input required maxLength={255} value={draft.title} onChange={(event) => setDraft({...draft, title: event.target.value})} /></label>
          <label>Slug<input required pattern="[a-z0-9]+(-[a-z0-9]+)*" value={draft.slug} onChange={(event) => setDraft({...draft, slug: event.target.value})} /></label>
          <label>Access policy<select value={draft.accessPolicy} onChange={(event) => setDraft({...draft, accessPolicy: event.target.value as CreateRequest['accessPolicy']})}><option value="public">Public</option><option value="invite_only">Invite only</option><option value="demo">Demo</option></select></label>
          <label>Route<select value={draft.phaseRoute} onChange={(event) => setDraft({...draft, phaseRoute: event.target.value})}>{data.phaseRoutes.map((route) => <option key={route.key} value={route.key}>{route.label}</option>)}</select></label>
          {data.creation.mode === 'manual_polis_id' && <label>Polis conversation ID<input required value={draft.polisId ?? ''} onChange={(event) => setDraft({...draft, polisId: event.target.value})} /></label>}
          <label className="admin-catalog__wide">Introduction <span>optional HTML</span><textarea rows={4} value={draft.introHtml} onChange={(event) => setDraft({...draft, introHtml: event.target.value})} /></label>
          <details className="admin-catalog__wide"><summary>Eligibility and closing text</summary><div>
            <label>Eligibility event ID<input maxLength={80} value={draft.eligibilityEventId} onChange={(event) => setDraft({...draft, eligibilityEventId: event.target.value})} /></label>
            <label>Eligibility label<input maxLength={255} value={draft.eligibilityLabel} onChange={(event) => setDraft({...draft, eligibilityLabel: event.target.value})} /></label>
            <label>Closing text<textarea rows={3} value={draft.outroHtml} onChange={(event) => setDraft({...draft, outroHtml: event.target.value})} /></label>
          </div></details>
          <button className="admin-catalog__wide" type="submit" disabled={creation.isPending}>{creation.isPending ? 'Creating…' : 'Create conversation'}</button>
        </form>
      </section>

      <section className="admin-catalog__admins" aria-labelledby="global-admins-heading">
        <header><p className="eyebrow">Platform access</p><h2 id="global-admins-heading">Global admins</h2><p>Global admins can manage every conversation. Conversation-specific roles remain inside each workspace.</p></header>
        <div>
          <ul>{data.globalAdmins.map((admin) => <li key={admin.participantId}><span>{admin.username}</span><button type="button" disabled={membership.isPending} onClick={() => {
            if (globalThis.confirm(`Remove site-wide administration from ${admin.username}?`)) membership.mutate({participantId: admin.participantId, granted: false});
          }}>Remove</button></li>)}</ul>
          <form onSubmit={submitGrant}><label htmlFor="global-admin-username">Wikimedia username</label><input id="global-admin-username" required value={username} onChange={(event) => setUsername(event.target.value)} /><button type="submit" disabled={!username.trim() || grant.isPending}>Grant access</button></form>
        </div>
      </section>
    </main>
  );
}

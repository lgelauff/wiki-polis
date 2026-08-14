import {useState, type FormEvent} from 'react';
import {useMutation, useQueryClient, useSuspenseQuery} from '@tanstack/react-query';
import {Link} from 'react-router-dom';

import type {components} from '../../api/schema';
import {ApiContractError} from '../../api/client';
import {adminSettingsQuery, putAdminSettings} from '../../api/queries';

type Settings = components['schemas']['AdminSettings'];
type Policy = Settings['conversation']['accessPolicy'];
type Tier = Settings['recommendations']['tier'];

export function AdminSettingsPage({conversationId, csrfToken}: {
  conversationId: number; csrfToken: string;
}) {
  const queryClient = useQueryClient();
  const options = adminSettingsQuery(conversationId);
  const {data} = useSuspenseQuery(options);
  const [title, setTitle] = useState(data.conversation.title);
  const [introHtml, setIntroHtml] = useState(data.conversation.introHtml);
  const [outroHtml, setOutroHtml] = useState(data.conversation.outroHtml);
  const [accessPolicy, setAccessPolicy] = useState<Policy>(data.conversation.accessPolicy);
  const [tier, setTier] = useState<Tier>(data.recommendations.tier);
  const mutation = useMutation({
    mutationFn: () => putAdminSettings(conversationId, {
      title, introHtml, outroHtml, accessPolicy, recommendationTier: tier,
    }, csrfToken),
    onSuccess: (receipt) => queryClient.setQueryData<Settings>(
      options.queryKey, receipt.settings,
    ),
  });
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    mutation.mutate();
  }
  const error = mutation.error instanceof ApiContractError
    ? mutation.error.message : mutation.error ? 'Settings could not be saved.' : null;

  return (
    <main className="settings-shell" id="main">
      <nav className="record-breadcrumb" aria-label="Breadcrumb">
        <Link to="/app/admin">Admin panel</Link><span>/</span>
        <Link to={data.links.lifecycle}>{data.conversation.title}</Link><span>/</span><span>Settings</span>
      </nav>
      <header className="settings-heading">
        <p className="eyebrow">Configuration · {data.conversation.slug}</p>
        <h1>Conversation settings</h1>
        <p>Describe the consultation, control access, and choose the scope used for tool guidance.</p>
      </header>
      <form className="settings-form" onSubmit={submit}>
        <section aria-labelledby="settings-description">
          <header><span>01</span><div><h2 id="settings-description">Description</h2><p>Participant-facing title and rich-text context.</p></div></header>
          <label>Title<input value={title} maxLength={255} required onChange={(event) => setTitle(event.target.value)} /></label>
          <label>Introduction HTML<textarea value={introHtml} rows={7} onChange={(event) => setIntroHtml(event.target.value)} /></label>
          <label>Closing HTML<textarea value={outroHtml} rows={5} onChange={(event) => setOutroHtml(event.target.value)} /></label>
          <p className="settings-hint">Allowed HTML is sanitized by the server when saved.</p>
        </section>
        <section aria-labelledby="settings-access">
          <header><span>02</span><div><h2 id="settings-access">Access</h2><p>Who can discover and join this conversation.</p></div></header>
          <label>Access policy<select value={accessPolicy} onChange={(event) => setAccessPolicy(event.target.value as Policy)}>
            <option value="public">Public</option><option value="invite_only">Invite only</option><option value="demo">Demo</option>
          </select></label>
          <div className="settings-eligibility" data-configured={data.eligibility.configured}>
            <strong>Eligibility {data.eligibility.configured ? 'configured' : 'not configured'}</strong>
            {data.eligibility.label && <span>{data.eligibility.label}</span>}
            <p>{data.eligibility.note}</p>
          </div>
        </section>
        <section aria-labelledby="settings-guidance">
          <header><span>03</span><div><h2 id="settings-guidance">Guidance scope</h2><p>The tool owns the recommended quantities for each tier.</p></div></header>
          <fieldset><legend>Complexity tier</legend>{data.recommendations.tiers.map((option) => (
            <label className="settings-tier" key={option.key}>
              <input type="radio" name="tier" value={option.key} checked={tier === option.key} onChange={() => setTier(option.key)} />
              <strong>{option.label}</strong>
              <span>{Object.values(option.quantities).join(' · ')}</span>
            </label>
          ))}</fieldset>
        </section>
        {data.capabilities.edit ? <footer>
          <button type="submit" disabled={mutation.isPending}>{mutation.isPending ? 'Saving…' : 'Save settings'}</button>
          {mutation.data && <p role="status">{mutation.data.changed ? 'Settings saved.' : 'Settings already up to date.'}</p>}
          {error && <p role="alert">{error}</p>}
        </footer> : <p className="settings-readonly">Your role can inspect but not change these settings.</p>}
      </form>
    </main>
  );
}

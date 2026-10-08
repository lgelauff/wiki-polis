import {useCallback, useEffect, useId, useRef, useState, type FormEvent, type ReactNode} from 'react';
import {useMutation, useQuery, useQueryClient, useSuspenseQuery, type QueryClient} from '@tanstack/react-query';

import type {components} from '../../api/schema';
import {ApiContractError} from '../../api/client';
import {
  adminLifecycleQuery,
  adminSettingsQuery,
  adminStatementWorkspaceQuery,
  putAdminSettings,
  putAdminStatementModerationPolicy,
} from '../../api/queries';
import {AdminComing} from './admin-coming';
import {AdminShell} from './admin-shell';
import type {Announcer} from './admin-announcer';
import {AdminTabStrip, type SectionTab} from './admin-tab-strip';
import {escapeHtml, richHtml} from '../../i18n/rich-html';
import {useMessage, type Message} from '../../i18n/messages';

type Settings = components['schemas']['AdminSettings'];
type Policy = Settings['conversation']['accessPolicy'];
type GatingType = Settings['conversation']['gatingType'];
type Tier = Settings['recommendations']['tier'];
type Workspace = components['schemas']['AdminStatementWorkspace'];

/** Which Settings tab a page is. The route decides; the page never reads the URL. */
export type SettingsTab = 'basics' | 'access' | 'invitations' | 'vouchers' | 'roles';

/** The answers to "who can take part" that this page offers, as one value.
 *
 * `gated` and `gatingType` travel separately on the wire, but only four of their
 * combinations are ones the server accepts from a new write today: not gated (no type),
 * gated with `invite_only`, with `voucher`, or with `wiki_based`. Keeping the answer as a
 * single radio value is what makes the impossible fifth combination -- gated with no type
 * -- unreachable from the page: the server refuses it for any row that is not already
 * gated ("a gated conversation needs a gating type", `services/admin_settings.py`).
 *
 * Two of the five are carried but never offered. `unset` is the read-back of a legacy row
 * that is gated with no stored type; such a row may be saved unchanged (the server's own
 * exception for it), so the page carries that state rather than silently rewriting it.
 * `wiki_based` is stored and accepted but admits nobody (`services/access.py` answers
 * `unknown` for every account), so it is not a thing anyone should be able to choose.
 *
 * Neither appears as a greyed control: a control that cannot be operated is still a tab
 * stop, is still announced as a radio, and invites a click that does nothing. What is
 * genuinely missing is said once in prose at the foot of the group instead (`COMING_*`
 * below -- inside the fieldset, so it closes its own question rather than running into the
 * next legend), so the group contains only answers that work. A row already storing one of the two keeps
 * it -- nothing here rewrites it -- but it shows as no answer selected, the same as today
 * for `unset`. */
type Admission = 'anyone' | 'invite_only' | 'voucher' | 'wiki_based' | 'unset';

/** What does not exist yet, said in prose rather than mimed with a dead control.
 *
 * A control that saves a value nothing reads is the same bug as a control the server
 * silently ignores: the organizer is told their answer took effect and no page ever acts
 * on it. `announce`, `information`, `results_shared`, `show_usernames` and
 * `access_request_text` are written and read back by the settings endpoint and by nothing
 * else -- no participant-facing page, lane query, about payload, results report or
 * identity-reveal step consults them -- so what they promise is named here instead of
 * offered. The stored values still travel out and back untouched (see the mutation below):
 * the page stops asking about them, it does not clear them.
 *
 * Hardcoded English on purpose: a placeholder for unshipped functionality gets no message
 * key and no qqq entry, so translators are not asked to carry a string that leaves again
 * when the functionality lands (`.claude/admin-review/message-key-convention.md`). */
const COMING_ADMISSION = {what: 'a policy based on wiki activity', issue: 406};
const COMING_VISIBILITY = {what: 'choosing what people without access can see, and what to tell them', issue: 405};
const COMING_REVEAL = {what: 'participants choosing to show their username', issue: 405};

function admissionOf(conversation: Settings['conversation']): Admission {
  if (!conversation.gated) return 'anyone';
  return conversation.gatingType ?? 'unset';
}

function admissionWire(admission: Admission): {gated: boolean; gatingType: GatingType} {
  if (admission === 'anyone') return {gated: false, gatingType: null};
  if (admission === 'unset') return {gated: true, gatingType: null};
  return {gated: true, gatingType: admission};
}

function admissionLabel(msg: Message, admission: Admission): string {
  switch (admission) {
    case 'anyone': return msg('admin-access-admission-anyone');
    case 'invite_only': return msg('admin-access-admission-invited');
    case 'voucher': return msg('admin-access-admission-voucher');
    case 'wiki_based': return msg('admin-access-admission-wiki');
    default: return '—';
  }
}

/** What the organizer has changed on Basics or Access and not saved yet: only the fields
 *  that were touched, so everything else is always read from the server's latest answer.
 *
 *  Each tab is its own route, so switching tabs unmounts the page. The draft is therefore
 *  kept above the routes, per query client and per consultation, and a tab picks it up
 *  again when it mounts: an edit on Basics survives a look at Access and back. A Save takes
 *  the saved tab's fields out of the draft; the other tab's unsaved edits stay. */
type Draft = {
  title?: string;
  introHtml?: string;
  outroHtml?: string;
  accessPolicy?: Policy;
  tier?: Tier;
  strictModeration?: boolean;
  admission?: Admission;
  eligibilityEventId?: string;
  eligibilityLabel?: string;
};

/** The fields each tab shows and saves. A Save sends the server's current value for every
 *  other field, never this page's copy of it. */
const TAB_FIELDS = {
  basics: ['title', 'introHtml', 'outroHtml', 'accessPolicy', 'tier'],
  access: ['admission', 'eligibilityEventId', 'eligibilityLabel'],
} as const satisfies Record<'basics' | 'access', readonly (keyof Draft)[]>;

const drafts = new WeakMap<QueryClient, Map<number, Draft>>();

function useSettingsDraft(conversationId: number) {
  const queryClient = useQueryClient();
  const [draft, setDraftState] = useState<Draft>(
    () => drafts.get(queryClient)?.get(conversationId) ?? {},
  );
  useEffect(() => {
    let store = drafts.get(queryClient);
    if (!store) drafts.set(queryClient, store = new Map());
    store.set(conversationId, draft);
  }, [queryClient, conversationId, draft]);
  const setDraft = useCallback((update: (current: Draft) => Draft) => setDraftState(update), []);
  return [draft, setDraft] as const;
}

/** The complete settings representation the endpoint takes, as the server last stored it. */
function storedBody(settings: Settings) {
  const {conversation} = settings;
  return {
    title: conversation.title,
    introHtml: conversation.introHtml,
    outroHtml: conversation.outroHtml,
    accessPolicy: conversation.accessPolicy,
    eligibilityEventId: settings.eligibility.eventId,
    eligibilityLabel: settings.eligibility.label ?? '',
    recommendationTier: settings.recommendations.tier,
    gated: conversation.gated,
    gatingType: conversation.gatingType,
    announce: conversation.announce,
    information: conversation.information,
    resultsShared: conversation.resultsShared,
    showUsernames: conversation.showUsernames,
    accessRequestText: conversation.accessRequestText,
  };
}

/** The per-field messages of a 400 `validation_failed`, keyed by the request field. */
function fieldErrors(error: unknown): Record<string, string[]> {
  if (!(error instanceof ApiContractError) || error.code !== 'validation_failed') return {};
  const details = error.details as {fields?: Record<string, string[]>} | undefined;
  return details?.fields ?? {};
}

/** The field named by a 409 `access_settings_locked` (`gated`, `gating_type` or
 *  `show_usernames`), so the refusal can be shown beside the row it is about. */
function lockedField(error: unknown): string | null {
  if (!(error instanceof ApiContractError)
      || error.code !== 'access_settings_locked') return null;
  const details = error.details as {field?: string} | undefined;
  return details?.field ?? null;
}

function LockGlyph({label}: {label: string}) {
  return (
    <span className="access-lock" title={label} role="img" aria-label={label}>
      <svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor"
        strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <rect x="3" y="7" width="10" height="7" rx="1.5" />
        <path d="M5.5 7V4.8a2.5 2.5 0 0 1 5 0V7" />
      </svg>
    </span>
  );
}

/**
 * The four Settings tabs, in the order the strip shows them.
 *
 * The third is named by the answer to "who gets in": a consultation gated on voucher codes
 * has vouchers to manage, everything else has an invitation list. Both paths stay routable
 * whichever the answer is, so a link to one of them never lands on a page that says the
 * other thing is what this consultation uses. */
function settingsTabs(conversationId: number, gatingType: GatingType, msg: Message): SectionTab[] {
  const base = `/admin/conversations/${conversationId}/settings`;
  return [
    {id: 'basics', label: msg('admin-settings-tab-basics'), href: `${base}/basics`},
    {id: 'access', label: msg('admin-access-heading'), href: `${base}/access`},
    // One id for both kinds, so a voucher consultation sent to Invitations (or the
    // reverse) still marks this tab as the current one.
    {id: 'membership',
      label: gatingType === 'voucher'
        ? msg('admin-settings-tab-vouchers')
        : msg('admin-settings-tab-invitations'),
      href: gatingType === 'voucher' ? `${base}/vouchers` : `${base}/invitations`},
    {id: 'roles', label: msg('admin-settings-tab-roles'), href: `${base}/roles`},
  ];
}

/** The message key that names a tab, so the strip and the breadcrumb say the same thing
 *  about the same page. */
function settingsTabKey(tab: SettingsTab): string {
  switch (tab) {
    case 'basics': return 'admin-settings-tab-basics';
    case 'access': return 'admin-access-heading';
    case 'invitations': return 'admin-settings-tab-invitations';
    case 'vouchers': return 'admin-settings-tab-vouchers';
    case 'roles': return 'admin-settings-tab-roles';
  }
}

/** The frame every Settings page sits in: the console shell, the section heading and the
 *  tab strip, with the page's own content under it. On every tab an h1 "Settings" and the
 *  strip; no heading repeats the tab's name, which the strip's current tab and the
 *  breadcrumb already say. */
export function AdminSettingsFrame({announcer, children, conversationId, gatingType, lifecycle, tab, toast}: {
  announcer?: Announcer | undefined;
  children: ReactNode;
  conversationId: number;
  gatingType: GatingType;
  lifecycle: components['schemas']['AdminLifecycle'];
  tab: SettingsTab;
  toast?: ReactNode;
}) {
  const msg = useMessage();
  return (
    <AdminShell
      title={msg('adminconv-doc-title', lifecycle.conversation.title)}
      data={lifecycle}
      gatingType={gatingType}
      section="settings"
      subPage={msg(settingsTabKey(tab))}
      toast={toast}
      announcer={announcer}
    >
      <div className="admin-page settings-page">
        <h1>{msg('admin-settings-heading')}</h1>
        <AdminTabStrip label={msg('admin-settings-tabs-aria')}
          tabs={settingsTabs(conversationId, gatingType, msg)}
          current={tab === 'invitations' || tab === 'vouchers' ? 'membership' : tab} />
        {children}
      </div>
    </AdminShell>
  );
}

/**
 * The Vouchers tab (#478 item 4): the strip and one line.
 *
 * Everything an organizer would do here — generate a batch, import codes, check one,
 * withdraw it — needs an endpoint the admin API does not have today; codes are managed by
 * the CLI (#368). A page of dead controls would be worse than this line, which says what
 * is coming and cites the issue it waits on. */
export function AdminSettingsVouchersPage({conversationId}: {conversationId: number}) {
  const msg = useMessage();
  const {data} = useSuspenseQuery(adminSettingsQuery(conversationId));
  const {data: lifecycle} = useSuspenseQuery(adminLifecycleQuery(conversationId));
  return (
    <AdminSettingsFrame
      conversationId={conversationId}
      gatingType={data.conversation.gatingType}
      lifecycle={lifecycle}
      tab="vouchers"
    >
      <AdminComing what="generating, importing, checking and withdrawing voucher codes here" issue={368} />
    </AdminSettingsFrame>
  );
}

/** The Approval section, moved here from the statements page (#478, decision a).
 *
 * The moderation policy is not one of the fields the settings endpoint takes, so it is
 * written by its own request -- `{mode}` on `PUT …/statement-moderation-policy` -- but
 * not by its own button: Basics has one Save, which sends this request when, and only when,
 * the checkbox differs from what is stored (see `AdminSettingsPage`). The section is part
 * of the settings form and has no form of its own; a nested form is invalid HTML, and its
 * submit would also reach the settings form.
 *
 * It reads the stored mode from the statements workspace (`moderationPolicy.mode`), which
 * is why this tab runs that query. `strict` is the page's unsaved answer, or null while it
 * is the stored one. */
function ApprovalSection({conversationId, strict, onChange}: {
  conversationId: number;
  strict: boolean | null;
  onChange: (strict: boolean) => void;
}) {
  const msg = useMessage();
  const {data} = useSuspenseQuery(adminStatementWorkspaceQuery(conversationId));
  const stored = data.moderationPolicy.mode === 'moderate';
  return (
    <section aria-labelledby="settings-approval">
      <h2 id="settings-approval">{msg('stmts-modsettings-heading')}</h2>
      {data.moderationPolicy.available ? <label className="checkbox-label">
        <input
          type="checkbox"
          name="strict_moderation"
          value="1"
          checked={strict ?? stored}
          onChange={(event) => onChange(event.target.checked)}
        />
        {msg('stmts-strict-label')}
      </label> : <SettingValue label={msg('stmts-strict-label')} value="" />}
    </section>
  );
}

/** A setting shown as its value, for a viewer who may not change it: text, not a disabled
 *  control, so nothing on the page looks as if it could be operated when it cannot. */
/** An organizer text shown to a viewer who may not change it: rendered exactly as
 *  participants see it. The HTML is the server-sanitised text the settings endpoint
 *  returns, which the participant pages render the same way, with the same class. */
function SettingHtml({label, html, className}: {label: string; html: string; className: string}) {
  return (
    <div className="access-answer">
      <p className="access-answer-legend">{label}</p>
      {html === '' ? <p className="access-answer-value">—</p>
        : <div className={`settings-value-html ${className}`} dangerouslySetInnerHTML={{__html: html}} />}
    </div>
  );
}

function SettingValue({label, value}: {label: string; value: string}) {
  return (
    <div className="access-answer">
      <p className="access-answer-legend">{label}</p>
      <p className="access-answer-value settings-value">{value === '' ? '—' : value}</p>
    </div>
  );
}

/** A refusal of the moderation-policy request, told apart from a refusal of the settings
 *  request so each is shown where it belongs. */
class PolicySaveError extends Error {
  /** `settingsChanged` is the settings receipt's answer when that request was sent and
   *  succeeded first, or null when it was not sent: a partial save says both outcomes. */
  constructor(readonly failure: unknown, readonly settingsChanged: boolean | null) {
    super('The moderation policy could not be saved.');
  }
}

/** The status-line text for a refused moderation-policy request. */
function policyErrorMessage(failure: unknown): string {
  if (failure instanceof ApiContractError && failure.code === 'verification_unavailable') {
    return 'Could not verify the current moderation state. Try again later.';
  }
  if (failure instanceof ApiContractError && failure.code === 'upstream_unavailable') {
    return 'Could not update moderation settings. Check server logs for details.';
  }
  if (failure instanceof ApiContractError && failure.code === 'command_outcome_unknown') {
    return 'Polis may have been updated, but the local policy could not be saved. Do not retry until a site admin checks it.';
  }
  return 'Could not save the moderation policy. Try again later.';
}

export function AdminSettingsPage({conversationId, csrfToken, tab = 'basics'}: {
  conversationId: number; csrfToken: string; tab?: 'basics' | 'access' | undefined;
}) {
  const msg = useMessage();
  const queryClient = useQueryClient();
  const options = adminSettingsQuery(conversationId);
  const {data} = useSuspenseQuery(options);
  // The console shell frames the page, and the frame is built from the lifecycle DTO.
  const {data: lifecycle} = useSuspenseQuery(adminLifecycleQuery(conversationId));
  // Every field shows the unsaved edit when there is one and the server's value otherwise,
  // so a field nobody touched follows whatever the server last said.
  const [draft, setDraft] = useSettingsDraft(conversationId);
  const title = draft.title ?? data.conversation.title;
  const introHtml = draft.introHtml ?? data.conversation.introHtml;
  const outroHtml = draft.outroHtml ?? data.conversation.outroHtml;
  const accessPolicy = draft.accessPolicy ?? data.conversation.accessPolicy;
  const admission = draft.admission ?? admissionOf(data.conversation);
  const eligibilityEventId = draft.eligibilityEventId ?? data.eligibility.eventId;
  const eligibilityLabel = draft.eligibilityLabel ?? (data.eligibility.label ?? '');
  const tier = draft.tier ?? data.recommendations.tier;
  // The strict-moderation answer once the checkbox has been touched; null until then, and
  // again after a save, when the checkbox shows what is stored.
  const strictModeration = draft.strictModeration ?? null;
  const workspaceOptions = adminStatementWorkspaceQuery(conversationId);
  // Basics only: whether the moderation policy can be set from here. Everyone who can open
  // Settings may moderate this consultation (the server requires it to read the page), so
  // the question is only whether the stored mode is known: when it is not, a checkbox would
  // guess. (`capabilities.moderate` in the workspace says whether the statements could be
  // read from the voting service, which is a different thing.) The Approval section
  // suspends until the workspace is loaded, so by the time the footer renders it is here.
  const {data: workspace} = useQuery({...workspaceOptions, enabled: tab === 'basics'});
  const canModerate = tab === 'basics' && Boolean(workspace?.moderationPolicy.available);
  const [confirming, setConfirming] = useState(false);
  const confirmRef = useRef<HTMLDivElement>(null);
  const saveRef = useRef<HTMLButtonElement>(null);
  const wasConfirming = useRef(false);
  const summaryRef = useRef<HTMLDivElement>(null);
  const ids = useId();
  const canEdit = data.capabilities.edit;
  // Only a site admin moves a consultation into or out of the Practice Environment (#472);
  // everyone else sees whether it is in it, as a fact, never as a choice.
  const canSwitchDemo = data.capabilities.switchDemo;
  const practice = accessPolicy === 'demo';
  // Both flags carry the same server predicate (the Explore phase flag); either one being
  // true means the stored admission answer cannot change, so the row renders as text --
  // which is what today's page does by disabling both of its access controls.
  const admissionLocked = Boolean(data.locks?.gated || data.locks?.gatingType);
  const stored = admissionOf(data.conversation);
  // The endpoint takes one of three complete key sets and refuses anything else
  // ("Provide the complete settings representation.", `api/admin_routes.py`), so dropping
  // keys from the body is not an option: the whole save would 400. A Save therefore sends
  // the whole representation -- built from a fresh read of the server, not from this
  // page's copy, with only this tab's own edits laid over it. A field the tab does not show
  // (the admission answer, from Basics) can then never be written back from a stale copy;
  // the five settings nothing reads travel back exactly as the server holds them.
  const gated = admission !== 'anyone';
  const ownFields = tab === 'access' ? TAB_FIELDS.access : TAB_FIELDS.basics;

  /** This tab's edits, as request fields. */
  function ownEdits(): Partial<ReturnType<typeof storedBody>> {
    const edits: Partial<ReturnType<typeof storedBody>> = {};
    if (tab === 'access') {
      if (draft.admission !== undefined) Object.assign(edits, admissionWire(draft.admission));
      if (draft.eligibilityEventId !== undefined) edits.eligibilityEventId = draft.eligibilityEventId;
      if (draft.eligibilityLabel !== undefined) edits.eligibilityLabel = draft.eligibilityLabel;
    } else {
      if (draft.title !== undefined) edits.title = draft.title;
      if (draft.introHtml !== undefined) edits.introHtml = draft.introHtml;
      if (draft.outroHtml !== undefined) edits.outroHtml = draft.outroHtml;
      if (draft.accessPolicy !== undefined) edits.accessPolicy = draft.accessPolicy;
      if (draft.tier !== undefined) edits.recommendationTier = draft.tier;
    }
    return edits;
  }

  /** Whether this tab's edits differ from what the server last stored. Only Basics asks:
   *  Access sends its request on every Save, as it always has. */
  function settingsChanged(): boolean {
    const stored = storedBody(data);
    return Object.entries(ownEdits()).some(
      ([key, value]) => stored[key as keyof typeof stored] !== value,
    );
  }

  /** One field edited: kept in the draft, and a "Settings saved." line from the last Save
   *  goes, because it no longer describes what is on screen. */
  function edit(patch: Draft) {
    setDraft((current) => ({...current, ...patch}));
    if (mutation.isSuccess) mutation.reset();
  }

  // One Save per tab, and everything on the tab takes effect on it (#478). On Basics that
  // can be two requests, because the moderation policy has its own endpoint: the settings
  // request when a settings field changed (or when nothing did, so the Save still answers
  // "already up to date"), then the policy request when the checkbox differs from what is
  // stored. A refused settings request stops the Save before the policy request is sent.
  // A role that may not edit the settings sends only the policy request.
  const mutation = useMutation({
    mutationFn: async (): Promise<{changed: boolean}> => {
      const current = queryClient.getQueryData<Workspace>(workspaceOptions.queryKey);
      const storedStrict = current ? current.moderationPolicy.mode === 'moderate' : null;
      const policyChanged = tab === 'basics' && strictModeration !== null
        && storedStrict !== null && strictModeration !== storedStrict;
      const sendSettings = canEdit && (tab !== 'basics' || settingsChanged() || !policyChanged);
      let changed = false;
      let settingsReceiptChanged: boolean | null = null;
      if (sendSettings) {
        // What the server holds now, not what this page loaded: another tab, another
        // organizer, or a copy older than the cache's staleTime may have changed it since.
        const fresh = await queryClient.fetchQuery({...options, staleTime: 0});
        const edits = ownEdits();
        const receipt = await putAdminSettings(conversationId, {
          ...storedBody(fresh), ...edits,
        }, csrfToken);
        queryClient.setQueryData<Settings>(options.queryKey, receipt.settings);
        // The saved fields leave the draft, so they show what the server stored (it clears
        // the eligibility pair when the invitation list is chosen) -- unless they were
        // edited again while the request was on its way.
        const sent = {...draft};
        setDraft((current) => {
          const next = {...current};
          for (const field of ownFields) if (next[field] === sent[field]) delete next[field];
          return next;
        });
        // The title is in the frame's breadcrumb and document title, both built from the
        // lifecycle DTO.
        void queryClient.invalidateQueries({queryKey: adminLifecycleQuery(conversationId).queryKey});
        changed = receipt.changed;
        settingsReceiptChanged = receipt.changed;
      }
      if (policyChanged) {
        let receipt;
        try {
          receipt = await putAdminStatementModerationPolicy(
            conversationId, {mode: strictModeration ? 'moderate' : 'auto_approve'}, csrfToken,
          );
        } catch (failure) {
          throw new PolicySaveError(failure, settingsReceiptChanged);
        }
        // The receipt carries the workspace, so the checkbox and the statements list never
        // disagree; the checkbox goes back to showing what is stored.
        queryClient.setQueryData<Workspace>(workspaceOptions.queryKey, receipt.workspace);
        setDraft((current) => {
          const next = {...current};
          delete next.strictModeration;
          return next;
        });
        changed = changed || receipt.changed;
      }
      return {changed};
    },
  });

  // Narrowing is measured against what the server last told us, not against the first
  // render: after a save the stored answers are the new baseline. Every move to a different
  // gated answer counts, not only anyone -> gated: invitation list -> voucher, and the
  // legacy `unset` row -> a real gate, both take access away from people who have it today.
  // Only a move *to* "anyone" widens. The admission answer is the only thing left that can
  // narrow: the visibility settings are no longer editable here, so a save cannot take
  // visibility away from anybody.
  // Asked on Access only: Basics does not show the answer and never sends an edit of it.
  const narrowing = tab === 'access' && stored !== admission && admission !== 'anyone';

  // A refused policy request is said on the status line; everything else below is about
  // the settings request.
  const policyFailure = mutation.error instanceof PolicySaveError ? mutation.error : null;
  const settingsError = policyFailure ? null : mutation.error;
  const fields = fieldErrors(settingsError);
  const fieldMessages = Object.values(fields).flat();
  // The admission radio group answers both wire fields, so a refusal of either is shown
  // once, under the group, and linked from every live choice in it.
  const admissionMessages = [...(fields.gated ?? []), ...(fields.gatingType ?? [])];
  const admissionInvalid = admissionMessages.length
    ? {'aria-invalid': true, 'aria-describedby': `${ids}-gated-error`}
    : {};
  const locked = lockedField(settingsError);
  const serverMessage = settingsError instanceof ApiContractError
    ? settingsError.message : null;
  const generalError = policyFailure ? policyErrorMessage(policyFailure.failure)
    : settingsError instanceof ApiContractError
      ? (fieldMessages.length || locked ? null : serverMessage)
      : settingsError ? 'Settings could not be saved.' : null;

  // The question takes focus when it opens; when it closes, by Cancel or by Continue, the
  // buttons that held focus are gone, so focus goes back to the Save button.
  useEffect(() => {
    if (confirming) confirmRef.current?.focus();
    else if (wasConfirming.current) saveRef.current?.focus();
    wasConfirming.current = confirming;
  }, [confirming]);
  // The question is about a change that is on screen: put the widest answer back and it has
  // nothing left to ask about, so it goes away with the narrowing it was asking about.
  useEffect(() => {
    if (!narrowing) setConfirming(false);
  }, [narrowing]);
  // Keyed on the attempt, not on the message count, so a second refusal naming the same
  // number of fields still moves focus to the summary.
  useEffect(() => {
    if (fieldMessages.length) summaryRef.current?.focus();
  }, [mutation.failureCount, fieldMessages.length]);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    // Widening saves at once; narrowing asks once, inside the page, keeping every input.
    if (narrowing && !confirming) {
      setConfirming(true);
      return;
    }
    setConfirming(false);
    mutation.mutate();
  }

  /** `aria-invalid` plus the link to the message, for a field the server refused. */
  function invalid(field: string) {
    return fields[field]
      ? {'aria-invalid': true, 'aria-describedby': `${ids}-${field}-error`} : {};
  }

  function FieldError({field}: {field: string}) {
    const messages = fields[field];
    if (!messages) return null;
    return <p className="access-field-error" id={`${ids}-${field}-error`}>{messages.join(' ')}</p>;
  }

  // The Practice switch is shown only to a site admin, and not while Explore locks access.
  const canSwitchPractice = !gated && canSwitchDemo && !admissionLocked;
  const practiceSection = practice || canSwitchPractice;
  // One Save per tab, shown only when something on the tab can be saved: the settings for
  // a role that may edit them, and on Basics the strict-moderation answer for a moderator.
  const canSave = canEdit || canModerate;
  // The server clears the eligibility pair whenever the invitation list is the answer
  // (`services/admin_settings.py`): the list is the whole admission check then. A field the
  // save would empty is not shown.
  const eligibilityShown = admission !== 'invite_only';
  const selectedTier = data.recommendations.tiers.find((option) => option.key === tier);
  // What is not built yet, said last on the page (see `AdminComing`).
  const coming = tab === 'basics' ? [
    {what: 'the language the consultation is written in', issue: 473},
    {what: 'keeping the submission form open while new statements are no longer shown', issue: 473},
    {what: 'publishing the moderation log', issue: 473},
  ] : practice ? [] : [
    ...(canEdit && !admissionLocked ? [COMING_ADMISSION] : []),
    ...(gated ? [COMING_VISIBILITY, COMING_REVEAL] : []),
  ];
  // A partial save -- the settings went through, the moderation policy did not -- says
  // both outcomes on the one status line.
  const saved = mutation.data ? mutation.data.changed
    : policyFailure ? policyFailure.settingsChanged : null;

  return (
    <AdminSettingsFrame
      conversationId={conversationId}
      gatingType={data.conversation.gatingType}
      lifecycle={lifecycle}
      tab={tab}
    >
        <form className="settings-form" onSubmit={submit}>
          {fieldMessages.length > 0 && <div className="access-summary" role="alert" tabIndex={-1} ref={summaryRef}>
            <ul>{Object.entries(fields).map(([field, messages]) => (
              <li key={field}>{messages.join(' ')}</li>
            ))}</ul>
          </div>}
          {tab === 'basics' ? <>
            <section aria-labelledby="settings-description">
              <h2 id="settings-description">Description</h2>
              {canEdit ? <>
                <label>{msg('admin-label-title')}<input value={title} maxLength={255} required {...invalid('title')} onChange={(event) => edit({title: event.target.value})} /></label>
                <FieldError field="title" />
                <label>{msg('admin-label-intro')}<textarea value={introHtml} rows={7} onChange={(event) => edit({introHtml: event.target.value})} /></label>
                <label>{msg('admin-label-outro')}<textarea value={outroHtml} rows={5} onChange={(event) => edit({outroHtml: event.target.value})} /></label>
                <p className="settings-hint">Allowed HTML is sanitized by the server when saved.</p>
              </> : <>
                <SettingValue label={msg('admin-label-title')} value={data.conversation.title} />
                <SettingHtml label={msg('admin-label-intro')} html={data.conversation.introHtml} className="intro-text" />
                <SettingHtml label={msg('admin-label-outro')} html={data.conversation.outroHtml} className="outro-text" />
              </>}
              {/* Admin-written texts meant for publication are CC0, like participants'
                  contributions; the deed link is built as on the join screen. */}
              <p className="settings-hint" dangerouslySetInnerHTML={richHtml(msg('admin-settings-basics-licence', '<a href="https://creativecommons.org/publicdomain/zero/1.0/" target="_blank" rel="noopener">' + `${escapeHtml(msg('accept-licence-link'))}<span class="sr-only"> ${escapeHtml(msg('common-opens-in-new-tab'))}</span></a>`))} />
            </section>
            <section aria-labelledby="settings-guidance">
              <h2 id="settings-guidance">{msg('adminconv-label-tier')}</h2>
              {canEdit ? <fieldset aria-labelledby="settings-guidance">{data.recommendations.tiers.map((option) => (
                <label className="settings-tier" key={option.key}>
                  <input type="radio" name="tier" value={option.key} checked={tier === option.key} onChange={() => edit({tier: option.key})} />
                  <strong>{option.label}</strong>
                  <span>{Object.values(option.quantities).join(' · ')}</span>
                </label>
              ))}</fieldset> : <SettingValue label={msg('adminconv-label-tier')} value={selectedTier?.label ?? tier} />}
            </section>
            {/* The Practice Environment section: the fixed answer a practice item has, and the
                switch that moves one in or out of it. Nothing at all when neither applies, so
                there is no heading without content under it. Hidden while Explore locks access:
                moving into or out of Practice rewrites the locked settings, which the server
                refuses then. */}
            {practiceSection && <section aria-labelledby="settings-practice">
              <h2 id="settings-practice">{msg('admin-access-practice')}</h2>
              {practice && <div className="access-answer" role="group" aria-labelledby={`${ids}-practice-legend`}>
                {/* One fixed answer, stored by the server whatever is sent, so it is stated
                    rather than offered: a gate here would only be refused. */}
                <p className="access-answer-legend" id={`${ids}-practice-legend`}>{msg('admin-access-admission-legend')}</p>
                <p className="access-answer-value">{msg('admin-access-admission-practice')}</p>
              </div>}
              {canSwitchPractice && <label>{msg('admin-label-access')}<select value={accessPolicy} onChange={(event) => edit({accessPolicy: event.target.value as Policy})}>
                <option value="public">{msg('admin-common-policy-open')}</option><option value="demo">{msg('admin-common-policy-practice')}</option>
              </select></label>}
            </section>}
            <ApprovalSection conversationId={conversationId}
              strict={strictModeration} onChange={(strict) => edit({strictModeration: strict})} />
          </> : <section aria-label={msg('admin-access-heading')}>
            {/* A practice item has no admission choice: the server stores one fixed answer
                whatever is sent, and the Practice Environment section on Basics states it.
                Only the admission group is left out; the eligibility fields stay. */}
            {!practice && (admissionLocked || !canEdit ? <div className="access-answer">
              <p className="access-answer-legend">{msg('admin-access-admission-legend')}</p>
              <p className="access-answer-value">
                {admissionLabel(msg, stored)}
                {admissionLocked && <> <LockGlyph label={msg('admin-access-locked-note')} /></>}
              </p>
            </div> : <fieldset className="access-choices">
              <legend>{msg('admin-access-admission-legend')}</legend>
              <label className="access-choice">
                <input type="radio" name="admission" value="anyone" checked={admission === 'anyone'} {...admissionInvalid} onChange={() => edit({admission: 'anyone'})} />
                <span>{msg('admin-access-admission-anyone')}</span>
              </label>
              <label className="access-choice">
                <input type="radio" name="admission" value="invite_only" checked={admission === 'invite_only'} {...admissionInvalid} onChange={() => edit({admission: 'invite_only'})} />
                <span>{msg('admin-access-admission-invited')}</span>
              </label>
              <label className="access-choice">
                <input type="radio" name="admission" value="voucher" checked={admission === 'voucher'} {...admissionInvalid} onChange={() => edit({admission: 'voucher'})} />
                <span>{msg('admin-access-admission-voucher')}</span>
              </label>
            </fieldset>)}
            {admissionMessages.length > 0 &&<p className="access-field-error" id={`${ids}-gated-error`}>{admissionMessages.join(' ')}</p>}
            {locked && <p className="access-field-error" role="alert">{serverMessage}</p>}
            {eligibilityShown && <>
              {canEdit ? <>
                <label>{msg('admin-label-elig-event')}<input value={eligibilityEventId} maxLength={80} placeholder={msg('admin-elig-event-ph')} {...invalid('eligibilityEventId')} onChange={(event) => edit({eligibilityEventId: event.target.value})} /></label>
                <FieldError field="eligibilityEventId" />
                <label>{msg('admin-label-elig-label')}<input value={eligibilityLabel} maxLength={255} placeholder={msg('admin-elig-label-ph')} {...invalid('eligibilityLabel')} onChange={(event) => edit({eligibilityLabel: event.target.value})} /></label>
                <FieldError field="eligibilityLabel" />
              </> : <>
                <SettingValue label={msg('admin-label-elig-event')} value={data.eligibility.eventId} />
                <SettingValue label={msg('admin-label-elig-label')} value={data.eligibility.label ?? ''} />
              </>}
              <div className="settings-eligibility" data-configured={data.eligibility.configured}>
                <strong>Eligibility {data.eligibility.configured ? 'configured' : 'not configured'}</strong>
                {data.eligibility.label && <span>{data.eligibility.label}</span>}
                <p>{data.eligibility.note}</p>
              </div>
            </>}
          </section>}
          {/* One Save, at the bottom of the tab, with one status line beside it. */}
          {canSave && <footer>
            {confirming ? <div className="access-confirm" role="group" aria-labelledby={`${ids}-confirm`} tabIndex={-1} ref={confirmRef}>
              <p id={`${ids}-confirm`}>{msg('admin-access-narrowing-confirm')}</p>
              <button type="submit" disabled={mutation.isPending}>{msg('admin-access-narrowing-continue')}</button>
              <button type="button" onClick={() => setConfirming(false)}>{msg('common-cancel')}</button>
            </div> : <button type="submit" disabled={mutation.isPending} ref={saveRef}>
              {mutation.isPending ? msg('admin-saving') : msg('admin-save')}
            </button>}
            {/* Always mounted, so the region exists before its first message; keyed on the
                attempt, so a second identical "Settings saved." is a new line, read again. */}
            <div className="settings-status" role="status">
              {saved !== null && <p key={mutation.submittedAt}>{saved ? 'Settings saved.' : 'Settings already up to date.'}</p>}
            </div>
            {generalError && <p role="alert">{generalError}</p>}
          </footer>}
        </form>
        {coming.map((line) => <AdminComing key={line.what} {...line} />)}
    </AdminSettingsFrame>
  );
}

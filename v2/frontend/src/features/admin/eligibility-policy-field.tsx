import {useId, useRef, useState, type KeyboardEvent} from 'react';
import {useQuery} from '@tanstack/react-query';

import type {components} from '../../api/schema';
import {adminEligibilityPoliciesQuery} from '../../api/queries';
import {InternalLink} from '../../internal-link';
import {useMessage, type Message} from '../../i18n/messages';

export type EligibilityPolicy = components['schemas']['EligibilityPolicy'];
type Rule = components['schemas']['EligibilityPolicyRule'];

/** The eligibility pair a form holds: the canivote policy id ('' for none) and its label. */
export type EligibilityChoice = {eventId: string; label: string};

/** A length of time from canivote (`{amount, unit}`), in words. */
function spanText(msg: Message, span: unknown): string | null {
  if (!span || typeof span !== 'object') return null;
  const {amount, unit} = span as {amount?: unknown; unit?: unknown};
  if (typeof amount !== 'number') return null;
  switch (unit) {
    case 'days': return msg('admin-policy-span-days', amount);
    case 'weeks': return msg('admin-policy-span-weeks', amount);
    case 'months': return msg('admin-policy-span-months', amount);
    case 'years': return msg('admin-policy-span-years', amount);
    default: return null;
  }
}

/** One canivote rule in plain words, or null for a rule this console has no words for. */
export function ruleText(msg: Message, rule: Rule): string | null {
  const wiki = rule.wiki ?? '';
  const {metric, operator, value} = rule;
  if (operator === 'is' && typeof value === 'boolean') {
    if (metric === 'has_global_account' && value) return msg('admin-policy-rule-global-account');
    if (metric === 'is_globally_locked' && !value) return msg('admin-policy-rule-not-globally-locked');
    if (metric === 'is_globally_blocked' && !value) return msg('admin-policy-rule-not-globally-blocked');
    if (metric === 'is_blocked' && !value && wiki) return msg('admin-policy-rule-not-blocked', wiki);
    return null;
  }
  if (metric === 'user_groups' && typeof value === 'string' && wiki) {
    if (operator === 'excludes') return msg('admin-policy-rule-not-in-group', value, wiki);
    if (operator === 'includes') return msg('admin-policy-rule-in-group', value, wiki);
    return null;
  }
  if (metric === 'edit_count' && typeof value === 'number' && wiki) {
    const article = rule.namespace === 'article';
    if (rule.namespace !== undefined && !article) return null;
    if (rule.within !== undefined) {
      const span = spanText(msg, rule.within);
      if (span === null || operator !== 'at_least') return null;
      return article
        ? msg('admin-policy-rule-recent-article-edits-at-least', value, wiki, span)
        : msg('admin-policy-rule-recent-edits-at-least', value, wiki, span);
    }
    if (operator === 'at_least') {
      return article ? msg('admin-policy-rule-article-edits-at-least', value, wiki)
        : msg('admin-policy-rule-edits-at-least', value, wiki);
    }
    if (operator === 'more_than') {
      return article ? msg('admin-policy-rule-article-edits-more-than', value, wiki)
        : msg('admin-policy-rule-edits-more-than', value, wiki);
    }
    return null;
  }
  if ((metric === 'time_since_first_edit' || metric === 'time_since_registration')
      && operator === 'at_least' && wiki) {
    const span = spanText(msg, value);
    if (span === null) return null;
    return metric === 'time_since_first_edit'
      ? msg('admin-policy-rule-first-edit', wiki, span)
      : msg('admin-policy-rule-registered', wiki, span);
  }
  return null;
}

/** canivote's rule as it is written, for a rule there are no words for yet: shown as code,
 *  so it is never hidden and never passed off as a sentence. */
function ruleCode(rule: Rule): string {
  const parts = [rule.metric, rule.operator, JSON.stringify(rule.value)];
  if (rule.namespace) parts.push(`namespace=${rule.namespace}`);
  if (rule.within) parts.push(`within=${JSON.stringify(rule.within)}`);
  if (rule.wiki) parts.push(`wiki=${rule.wiki}`);
  return parts.join(' ');
}

/** The rules of a policy in plain words, read-only, and a link to the community's page they
 *  were written from (#530; owner 2026-10-15: rules in words, not a count). */
export function PolicyRules({policy}: {policy: EligibilityPolicy}) {
  const msg = useMessage();
  const source = policy.sources[0];
  return (
    <div className="policy-rules">
      {policy.rules && policy.rules.length > 0 && <ul aria-label={policy.title}>
        {policy.rules.map((rule, index) => {
          const text = ruleText(msg, rule);
          return <li key={index}>{text ?? <code>{ruleCode(rule)}</code>}</li>;
        })}
      </ul>}
      {/* An external page: InternalLink renders it as a plain link. */}
      {source && <p><InternalLink href={source} target="_blank" rel="noopener">
        {msg('admin-access-policy-source')}
        <span className="sr-only"> {msg('common-opens-in-new-tab')}</span>
      </InternalLink></p>}
    </div>
  );
}

function matches(policy: EligibilityPolicy, query: string): boolean {
  const needle = query.trim().toLowerCase();
  if (!needle) return true;
  return [policy.id, policy.title, policy.wiki ?? ''].some(
    (text) => text.toLowerCase().includes(needle),
  );
}

/**
 * The policy field: a text box with a drop-down list (the ARIA editable combobox with list
 * autocomplete), no library.
 *
 * Typing filters canivote's policies by id, title and wiki; arrow keys move through the list,
 * Enter chooses, Escape closes it. Only a choice from the list counts (owner, 2026-10-15):
 * typed text is never saved, and leaving the field without choosing puts the last choice
 * back. "No eligibility check" is the first option, so clearing is a choice like any other.
 */
function PolicyCombobox({policies, value, onChoose, invalid, labelledBy}: {
  policies: EligibilityPolicy[];
  labelledBy: string;
  value: string;
  onChoose: (policy: EligibilityPolicy | null) => void;
  invalid: Record<string, unknown>;
}) {
  const msg = useMessage();
  const ids = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const chosen = policies.find((policy) => policy.id === value) ?? null;
  const shown = chosen ? chosen.title : value;
  // The typed text while the reader is filtering; null when the box shows the choice.
  const [query, setQuery] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);

  const filtered = policies.filter((policy) => matches(policy, query ?? ''));
  // Option 0 is "No eligibility check"; it is offered whenever nothing has been typed.
  const offerNone = !query?.trim();
  // One list, in canivote's order, is both what is shown and what the keys move through, so
  // the option that is highlighted and announced is always the one Enter chooses.
  const options: (EligibilityPolicy | null)[] = [...(offerNone ? [null] : []), ...filtered];
  const optionId = (index: number) => `${ids}-option-${index}`;

  function openList(at?: number) {
    setOpen(true);
    const current = options.findIndex((option) => (option?.id ?? '') === value);
    setActive(at ?? Math.max(current, 0));
  }

  function close() {
    setOpen(false);
    setQuery(null);
  }

  function choose(option: EligibilityPolicy | null) {
    onChoose(option);
    close();
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    switch (event.key) {
      case 'ArrowDown':
        event.preventDefault();
        if (!open) openList();
        else setActive((index) => Math.max(0, Math.min(index + 1, options.length - 1)));
        break;
      case 'ArrowUp':
        event.preventDefault();
        if (!open) openList();
        else setActive((index) => Math.max(index - 1, 0));
        break;
      case 'Enter':
        // Enter inside the list chooses; it never submits the form with half-typed text.
        if (open) {
          event.preventDefault();
          if (options[active] !== undefined) choose(options[active]);
        }
        break;
      case 'Escape':
        if (open || query !== null) {
          event.preventDefault();
          close();
        }
        break;
    }
  }

  return (
    <div className="policy-combobox">
      <div className="policy-combobox__box">
        <input
          ref={inputRef}
          id={`${ids}-input`}
          type="text"
          role="combobox"
          autoComplete="off"
          aria-labelledby={labelledBy}
          aria-autocomplete="list"
          aria-expanded={open}
          aria-controls={`${ids}-list`}
          aria-activedescendant={open && options.length ? optionId(active) : undefined}
          placeholder={msg('admin-access-policy-none')}
          value={query ?? shown}
          {...invalid}
          onChange={(event) => {
            setQuery(event.target.value);
            setOpen(true);
            setActive(0);
          }}
          onKeyDown={onKeyDown}
          onBlur={close}
        />
        {/* The pointer's way to the whole list; the keyboard has the arrow keys. */}
        <button type="button" className="policy-combobox__toggle" tabIndex={-1} aria-hidden="true"
          onMouseDown={(event) => event.preventDefault()}
          onClick={() => {
            if (open) close();
            else {
              inputRef.current?.focus();
              openList();
            }
          }}>▾</button>
      </div>
      <ul className="policy-combobox__list" id={`${ids}-list`} role="listbox"
        aria-labelledby={labelledBy} hidden={!open}>
        {options.map((option, at) => (
          <li key={option?.id ?? ''} id={optionId(at)} role="option" aria-selected={active === at}
            className="policy-combobox__option"
            onMouseDown={(event) => event.preventDefault()}
            onMouseEnter={() => setActive(at)}
            onClick={() => choose(option)}>
            {option === null ? msg('admin-access-policy-none') : <>
              {option.title}{' '}
              <span className="policy-combobox__id">{option.wiki ? `${option.id} · ${option.wiki}` : option.id}</span>
            </>}
          </li>
        ))}
        {options.length === 0 && <li role="presentation" className="policy-combobox__empty">
          {msg('admin-access-policy-no-match')}
        </li>}
      </ul>
    </div>
  );
}

/**
 * The eligibility policy and its label, as one block, for Settings › Access and the New
 * consultation form (#530).
 *
 * The policy comes from canivote's list only. Choosing one fills the label with its title
 * when the label is empty or still the previous policy's title; a label the organizer wrote
 * themselves is kept (owner, 2026-10-15). Choosing none empties the label, which only ever
 * names the policy. While canivote's list cannot be loaded no policy can be chosen, but
 * "No eligibility check" still can: removing a policy must not wait on canivote.
 */
export function EligibilityPolicyField({value, onChange, errors = {}, labelClassName}: {
  value: EligibilityChoice;
  onChange: (next: EligibilityChoice) => void;
  /** The server's refusal messages for each field, when a save was refused. */
  errors?: {eventId?: string[] | undefined; label?: string[] | undefined};
  labelClassName?: string;
}) {
  const msg = useMessage();
  const ids = useId();
  const {data, isPending} = useQuery(adminEligibilityPoliciesQuery());
  const policies = data?.policies ?? [];
  const available = data?.available ?? false;
  const chosen = policies.find((policy) => policy.id === value.eventId) ?? null;
  const unlisted = available && value.eventId !== '' && chosen === null;

  function onChoose(policy: EligibilityPolicy | null) {
    if (policy === null) {
      onChange({eventId: '', label: ''});
      return;
    }
    // Kept only when it is not the previous policy's title. A previous policy canivote no
    // longer lists has no title to compare with, so its label cannot be told apart from
    // one the organizer wrote, and it would name a policy that is no longer chosen.
    const previous = policies.find((option) => option.id === value.eventId);
    const keepLabel = previous !== undefined && value.label.trim() !== ''
      && value.label !== previous.title;
    onChange({eventId: policy.id, label: keepLabel ? value.label : policy.title});
  }

  const describedBy = [
    errors.eventId ? `${ids}-policy-error` : null,
    unlisted || (!isPending && !available) ? `${ids}-policy-note` : null,
  ].filter(Boolean).join(' ');
  const invalid = {
    ...(errors.eventId ? {'aria-invalid': true} : {}),
    ...(describedBy ? {'aria-describedby': describedBy} : {}),
  };

  return (
    <div className="policy-field">
      <p className="access-answer-legend" id={`${ids}-legend`}>{msg('admin-access-policy-label')}</p>
      {isPending ? <p className="access-answer-value">{value.eventId || msg('admin-access-policy-none')}</p>
        : <>
          <PolicyCombobox policies={available ? policies : []} value={value.eventId}
            onChoose={onChoose} invalid={invalid} labelledBy={`${ids}-legend`} />
          {!available && <p className="access-field-note" id={`${ids}-policy-note`}>{msg('admin-access-policy-unavailable')}</p>}
        </>}
      {unlisted && <p className="access-field-error" id={`${ids}-policy-note`}>
        {msg('admin-access-policy-unlisted', value.eventId)}
      </p>}
      {errors.eventId && <p className="access-field-error" id={`${ids}-policy-error`}>{errors.eventId.join(' ')}</p>}
      {chosen && <PolicyRules policy={chosen} />}
      {value.eventId !== '' && <>
        <label className={labelClassName}>{msg('admin-label-elig-label')}<input value={value.label} maxLength={255}
          {...(errors.label ? {'aria-invalid': true, 'aria-describedby': `${ids}-label-error`} : {})}
          onChange={(event) => onChange({...value, label: event.target.value})} /></label>
        {errors.label && <p className="access-field-error" id={`${ids}-label-error`}>{errors.label.join(' ')}</p>}
      </>}
    </div>
  );
}

/** The chosen policy as text, for a viewer who may not change it. */
export function EligibilityPolicyValue({eventId, label, policy}: {
  eventId: string; label: string | null; policy: EligibilityPolicy | null;
}) {
  const msg = useMessage();
  return (
    <>
      <div className="access-answer">
        <p className="access-answer-legend">{msg('admin-access-policy-label')}</p>
        <p className="access-answer-value settings-value">
          {policy ? policy.title : eventId || msg('admin-access-policy-none')}
        </p>
        {policy && <PolicyRules policy={policy} />}
      </div>
      {eventId !== '' && <div className="access-answer">
        <p className="access-answer-legend">{msg('admin-label-elig-label')}</p>
        <p className="access-answer-value settings-value">{label || '—'}</p>
      </div>}
    </>
  );
}

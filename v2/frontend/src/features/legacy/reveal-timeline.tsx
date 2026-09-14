import {useEffect, useState} from 'react';

import {useDateFormat} from '../../i18n/dates';
import {useMessage, type Message} from '../../i18n/messages';
import {escapeHtml, richHtml} from '../../i18n/rich-html';

type RevealState = 'pending' | 'open' | 'revealed' | 'expired';

function countdown(msg: Message, value: string) {
  const milliseconds = Date.parse(value) - Date.now();
  if (milliseconds <= 0) return msg('reveal-tl-now');
  const seconds = Math.floor(milliseconds / 1000);
  const pad = (part: number) => String(part).padStart(2, '0');
  return `${Math.floor(seconds / 86400)}d ${pad(Math.floor(seconds % 86400 / 3600))}:${pad(Math.floor(seconds % 3600 / 60))}:${pad(seconds % 60)}`;
}

/** The countdown is a styled element inside a sentence. Passing it in as an escaped HTML
 *  fragment keeps each sentence one translatable unit, and keeps the class name out of the
 *  message. */
function deadlineSentence(msg: Message, state: RevealState, remaining: string) {
  const clock = `<strong class="reveal-countdown">${escapeHtml(remaining)}</strong>`;
  if (state === 'pending') return msg('reveal-tl-deadline-opens', clock);
  if (state === 'open') return msg('reveal-tl-deadline-closes-permanent', clock);
  return msg('reveal-tl-deadline-closes', clock);
}

/** The identity-reveal timeline: closed, window opens, window closes. Shared by the closed
 *  consultation workspace and the identity-reveal page, which receive the same dates under
 *  different field names. */
export function RevealTimeline({state, closedAt, opensAt, closesAt, cooldownDays, windowDays, countdownTargetAt}: {
  state: RevealState;
  closedAt: string;
  opensAt: string;
  closesAt: string;
  cooldownDays: number;
  windowDays: number;
  countdownTargetAt: string | null;
}) {
  const dates = useDateFormat();
  const msg = useMessage();
  const [remaining, setRemaining] = useState(
    countdownTargetAt ? countdown(msg, countdownTargetAt) : null,
  );
  useEffect(() => {
    if (!countdownTargetAt) return;
    const update = () => setRemaining(countdown(msg, countdownTargetAt!));
    update();
    const timer = globalThis.setInterval(update, 1000);
    return () => globalThis.clearInterval(timer);
  }, [msg, countdownTargetAt]);
  const firstNow = state === 'pending';
  const secondNow = state === 'open' || state === 'revealed';
  const expired = state === 'expired';
  return <div className="reveal-timeline">
    <ol className="reveal-track" aria-label={msg('reveal-tl-aria')}>
      <li className={`reveal-node reveal-node--done${firstNow ? ' reveal-node--now' : ''}`} {...(firstNow ? {'aria-current': 'step' as const} : {})}>
        <span className="reveal-pip" aria-hidden="true" />
        <div className="reveal-when">{dates.date(closedAt)}</div>
        <div className="reveal-what">{msg('reveal-tl-closed-what', cooldownDays)}{' '}<span className="sr-only">{firstNow ? msg('reveal-tl-step-inprogress') : msg('reveal-tl-step-completed')}</span></div>
      </li>
      <li className={`reveal-node${secondNow ? ' reveal-node--now' : expired ? ' reveal-node--done' : ''}`} {...(secondNow ? {'aria-current': 'step' as const} : {})}>
        <span className="reveal-pip" aria-hidden="true" />
        <div className="reveal-when">{dates.date(opensAt)}</div>
        <div className="reveal-what">{msg('reveal-tl-opens-what', windowDays)}{' '}<span className="sr-only">{secondNow ? msg('reveal-tl-step-current') : expired ? msg('reveal-tl-step-completed') : msg('reveal-tl-step-upcoming')}</span></div>
      </li>
      <li className={`reveal-node${expired ? ' reveal-node--now' : ''}`} {...(expired ? {'aria-current': 'step' as const} : {})}>
        <span className="reveal-pip" aria-hidden="true" />
        <div className="reveal-when">{dates.date(closesAt)}</div>
        <div className="reveal-what">{msg('reveal-tl-closes-what')}{' '}<span className="sr-only">{expired ? msg('reveal-tl-step-current') : msg('reveal-tl-step-upcoming')}</span></div>
      </li>
    </ol>
    {remaining && <p className="reveal-deadline" dangerouslySetInnerHTML={richHtml(deadlineSentence(msg, state, remaining))} />}
  </div>;
}

import {useEffect, useLayoutEffect, useMemo, useRef, useState} from 'react';

import {useDateFormat} from '../../i18n/dates';
import {useMessage, type Message} from '../../i18n/messages';
import {richHtml} from '../../i18n/rich-html';

type RevealState = 'pending' | 'open' | 'revealed' | 'expired';

/** The time left until `value`, as a message; null once it has passed. */
function countdown(msg: Message, value: string) {
  const milliseconds = Date.parse(value) - Date.now();
  if (!(milliseconds > 0)) return null;
  const seconds = Math.floor(milliseconds / 1000);
  const pad = (part: number) => String(part).padStart(2, '0');
  return msg('reveal-tl-countdown', Math.floor(seconds / 86400), `${pad(Math.floor(seconds % 86400 / 3600))}:${pad(Math.floor(seconds % 3600 / 60))}:${pad(seconds % 60)}`);
}

/** The countdown is a styled element inside a sentence. It is passed in empty and its text is
 *  written each second into that element, so the sentence around it -- which says linking
 *  cannot be undone -- stays the same DOM node while the clock runs. Replacing the sentence
 *  every second resets a screen reader's reading position and any text selection. */
function deadlineSentence(msg: Message, state: RevealState) {
  const clock = '<strong class="reveal-countdown"></strong>';
  if (state === 'pending') return msg('reveal-tl-deadline-opens', clock);
  if (state === 'open') return msg('reveal-tl-deadline-closes-permanent', clock);
  return null;
}

/** The identity-reveal timeline: closed, window opens, window closes. Shared by the closed
 *  consultation workspace and the identity-reveal page, which receive the same dates under
 *  different field names.
 *
 *  The countdown runs only while the window is pending or open. When it reaches its boundary
 *  the line is removed and `onBoundary` is called, so the page can fetch the state that
 *  follows instead of counting past it. */
export function RevealTimeline({state, closedAt, opensAt, closesAt, cooldownDays, windowDays, countdownTargetAt, onBoundary}: {
  state: RevealState;
  closedAt: string;
  opensAt: string;
  closesAt: string;
  cooldownDays: number;
  windowDays: number;
  countdownTargetAt: string | null;
  onBoundary?: () => void;
}) {
  const dates = useDateFormat();
  const msg = useMessage();
  const [passedTarget, setPassedTarget] = useState<string | null>(null);
  const deadline = useRef<HTMLParagraphElement>(null);
  const boundaryHandler = useRef(onBoundary);
  useEffect(() => {
    boundaryHandler.current = onBoundary;
  }, [onBoundary]);

  const target = countdownTargetAt !== passedTarget ? countdownTargetAt : null;
  const sentence = useMemo(() => {
    const text = target === null ? null : deadlineSentence(msg, state);
    return text === null ? null : richHtml(text);
  }, [msg, state, target]);

  useLayoutEffect(() => {
    const clock = deadline.current?.querySelector('.reveal-countdown');
    if (!sentence || !target || !clock) return undefined;
    let timer: ReturnType<typeof globalThis.setInterval> | undefined;
    const update = () => {
      const remaining = countdown(msg, target);
      if (remaining === null) {
        globalThis.clearInterval(timer);
        setPassedTarget(target);
        boundaryHandler.current?.();
        return false;
      }
      clock.textContent = remaining;
      return true;
    };
    if (update()) timer = globalThis.setInterval(update, 1000);
    return () => globalThis.clearInterval(timer);
  }, [msg, sentence, target]);

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
    {sentence && <p ref={deadline} className="reveal-deadline" dangerouslySetInnerHTML={sentence} />}
  </div>;
}

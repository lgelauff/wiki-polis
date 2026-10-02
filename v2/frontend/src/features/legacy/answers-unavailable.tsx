import {Component, type ReactNode} from 'react';

import {ApiContractError} from '../../api/client';
import {useMessage} from '../../i18n/messages';

/** `answers_unavailable`: the voting service's view of this participant is missing answers
 *  Polis holds for them (typically an expired upstream session that the server could not
 *  repair by re-binding). The server shows no deck and records no vote in that state, so a
 *  stale deck cannot re-offer answered statements and a vote cannot overwrite an earlier one.
 *  The participant is told their answers are safe and to try again later. */
export function isAnswersUnavailable(error: unknown): boolean {
  return error instanceof ApiContractError && error.code === 'answers_unavailable';
}

export function AnswersUnavailableNotice() {
  const msg = useMessage();
  return <div className="landing-section" role="alert"><p className="muted">{msg('conv-err-answers-unavailable')}</p></div>;
}

/** Catches a voting panel's read failing with `answers_unavailable` and shows the notice in
 *  place of the panel. Every other error is rethrown unchanged, to whatever handled it before. */
export class AnswersUnavailableBoundary extends Component<{children: ReactNode}, {error: unknown}> {
  state: {error: unknown} = {error: null};

  static getDerivedStateFromError(error: unknown) {
    return {error};
  }

  render() {
    const {error} = this.state;
    if (error === null) return this.props.children;
    if (isAnswersUnavailable(error)) return <AnswersUnavailableNotice />;
    throw error;
  }
}

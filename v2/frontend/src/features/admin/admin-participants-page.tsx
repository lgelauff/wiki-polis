import {useCallback, useState} from 'react';
import {useSuspenseQuery} from '@tanstack/react-query';

import type {components} from '../../api/schema';
import {
  adminLifecycleQuery,
  adminParticipantRosterQuery,
  adminSettingsQuery,
} from '../../api/queries';
import {useMessage} from '../../i18n/messages';
import {AdminShell} from './admin-shell';
import {AdminTime} from './admin-time';
import {PersonAccessControl} from './admin-person-access';
import {AdminComing} from './admin-coming';
import {AdminTabStrip} from './admin-tab-strip';
import {contentTabs} from './admin-content-tabs';
import {LegacyToast, type LegacyToastMessage} from '../legacy/legacy-toast';

type Participant = components['schemas']['AdminParticipant'];

/** The person as this page names them: the Wikimedia username for an organizer or a site
 *  admin, the pseudonym for a moderator-only viewer, to whom the roster sends no username
 *  (owner decision, 2026-10-08). */
function personName(participant: Participant): string {
  return participant.username ?? participant.pseudonym;
}

export function AdminParticipantsPage({
  conversationId,
  csrfToken,
}: {
  conversationId: number;
  csrfToken: string;
}) {
  const msg = useMessage();
  const {data} = useSuspenseQuery(adminParticipantRosterQuery(conversationId));
  const {data: settings} = useSuspenseQuery(adminSettingsQuery(conversationId));
  const {data: lifecycle} = useSuspenseQuery(adminLifecycleQuery(conversationId));
  const [toast, setToast] = useState<LegacyToastMessage | null>(null);
  const dismissToast = useCallback(() => setToast(null), []);

  return (
    <AdminShell
      title={msg('adminconv-doc-title', lifecycle.conversation.title)}
      data={lifecycle}
      gatingType={settings.conversation.gatingType}
      section="content"
      subPage={msg('adminconv-card-participants')}
      toast={<LegacyToast toast={toast} onDismiss={dismissToast} />}
    >
      <div className="admin-page">
        <h1>{msg('admin-shell-content')}</h1>
        <AdminTabStrip label={msg('admin-content-tabs-aria')}
          tabs={contentTabs(conversationId, msg)} current="participants" />

        {!data.dataAvailability.statementProgress && (
          <p className="admin-note">{msg('participants-progress-unavailable')}</p>
        )}

        {data.participants.length ? (
          <ul className="admin-rows">
            {data.participants.map((participant) => {
              const progress = participant.statementProgress;
              return (
                <li className="admin-row" key={participant.participantId}>
                  <div className="admin-row__text">
                    {personName(participant)}
                    {participant.access.banned && (
                      <span className="admin-row__suffix">
                        {' · '}{msg('participants-banned')}
                        {participant.access.changedAt && <>
                          {` ${msg('participants-banned-since')} `}
                          <AdminTime value={participant.access.changedAt} />
                        </>}
                        {/* The reason, once, beside the name: as on Moderation › People. */}
                        {participant.access.summary && ` · ${participant.access.summary}`}
                      </span>
                    )}
                  </div>
                  {/* Today's columns, as facts about the person: progress and the argument
                      counts are what the roster returns, in the words the page already used. */}
                  <dl className="admin-row__facts">
                    <div>
                      <dt>{msg('participants-th-voted')}</dt>
                      <dd>{progress ? `${progress.voted} / ${progress.total}` : '—'}</dd>
                    </div>
                    <div>
                      <dt>{msg('participants-th-remaining')}</dt>
                      <dd>{progress ? progress.remaining : '—'}</dd>
                    </div>
                    <div>
                      <dt>{msg('participants-th-args-submitted')}</dt>
                      <dd>{participant.arguments.submitted}</dd>
                    </div>
                    <div>
                      <dt>{msg('participants-th-args-voted')}</dt>
                      <dd>{participant.arguments.prioritized}</dd>
                    </div>
                    <div>
                      <dt>{msg('participants-th-last-engagement')}</dt>
                      <dd>{participant.lastEngagementAt
                        ? <AdminTime value={participant.lastEngagementAt} moment />
                        : msg('participants-no-actions')}</dd>
                    </div>
                  </dl>
                  <div className="admin-row__actions">
                    <PersonAccessControl
                      conversationId={conversationId}
                      participant={participant}
                      name={personName(participant)}
                      csrfToken={csrfToken}
                      onFeedback={setToast}
                    />
                  </div>
                </li>
              );
            })}
          </ul>
        ) : (
          <p className="admin-empty">{msg('participants-empty')}</p>
        )}

        {/* The spec splits this page into a moderator's columns and an organizer's and adds
            the batch label and the joined day. The roster carries none of those fields yet. */}
        <AdminComing what="the moderator and organizer roles per person, their batch, and the day they joined" issue={473} />
      </div>
    </AdminShell>
  );
}

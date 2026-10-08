import {useCallback, useState} from 'react';
import {useSuspenseQuery} from '@tanstack/react-query';

import {
  adminLifecycleQuery,
  adminParticipantRosterQuery,
  adminSettingsQuery,
} from '../../api/queries';
import {useMessage} from '../../i18n/messages';
import {AdminComing} from './admin-coming';
import {AdminShell} from './admin-shell';
import {PersonAccessControl} from './admin-person-access';
import {AdminTabStrip} from './admin-tab-strip';
import {moderationTabs} from './admin-moderation-tabs';
import {LegacyToast, type LegacyToastMessage} from '../legacy/legacy-toast';

function formatDate(value: string): string {
  return value.slice(0, 10);
}

export function AdminModerationPeoplePage({conversationId, csrfToken}: {
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
      section="moderation"
      subPage={msg('admin-moderation-people')}
      toast={<LegacyToast toast={toast} onDismiss={dismissToast} />}
    >
      <div className="admin-page">
        <h1>{msg('admin-shell-moderation')}</h1>
        <AdminTabStrip label={msg('admin-shell-moderation')}
          tabs={moderationTabs(conversationId, msg)} current="people" />

        {data.participants.length ? (
          <ul className="admin-rows">
            {data.participants.map((participant) => (
              <li className="admin-row" key={participant.participantId}>
                <div className="admin-row__text">
                  {/* The pseudonym, never the username: moderators see people only by the
                      name they take part under (owner decision, 2026-10-08), and the roster
                      does not carry a username to a moderator-only viewer at all. */}
                  {participant.pseudonym}
                  <span className="admin-row__suffix">
                    {' · '}
                    {participant.access.banned
                      ? msg('participants-banned')
                      : msg('admin-moderation-person-active')}
                    {participant.access.banned && participant.access.changedAt
                      ? ` ${msg('participants-banned-since')} ${formatDate(participant.access.changedAt)}`
                      : ''}
                    {participant.access.banned && participant.access.summary
                      ? ` · ${participant.access.summary}`
                      : ''}
                    {participant.lastEngagementAt
                      ? ` · ${formatDate(participant.lastEngagementAt)}`
                      : ` · ${msg('participants-no-actions')}`}
                  </span>
                </div>
                <div className="admin-row__actions">
                  <PersonAccessControl conversationId={conversationId} participant={participant}
                    csrfToken={csrfToken} onFeedback={setToast} />
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <p className="admin-empty">{msg('participants-empty')}</p>
        )}

        {/* The moderator/organizer split, progress, batch label and joined day need fields
            the roster does not return yet (#473). */}
        <AdminComing what="the moderator and organizer roles per person, and when they joined" issue={473} />
      </div>
    </AdminShell>
  );
}
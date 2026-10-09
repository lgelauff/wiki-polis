import type {Message} from '../../i18n/messages';
import type {SectionTab} from './admin-tab-strip';

/** The four pages of the Moderation section, in the order the strip shows them.
 *
 * Built from the conversation id rather than from a DTO link: the moderation pages' own
 * endpoints carry a link to the consultation, not to each other, and the sidebar's
 * Moderation link is the whole section. `current` is the id of the page being shown. */
export function moderationTabs(conversationId: number, msg: Message): SectionTab[] {
  const base = `/admin/conversations/${conversationId}/moderation`;
  return [
    {id: 'queue', label: msg('admin-moderation-queue'), href: `${base}/queue`},
    {id: 'flags', label: msg('admin-moderation-flags'), href: `${base}/flags`},
    {id: 'featured', label: msg('featured-crumb'), href: `${base}/featured`},
    {id: 'people', label: msg('admin-moderation-people'), href: `${base}/people`},
  ];
}
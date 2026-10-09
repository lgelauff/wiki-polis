import type {Message} from '../../i18n/messages';
import type {SectionTab} from './admin-tab-strip';

/** The pages of the Content section, in the order the strip shows them.
 *
 * Arguments are a page in the spec and not one here: there is no admin list endpoint for
 * them yet, so the pages say so once instead of offering an empty list. */
export function contentTabs(conversationId: number, msg: Message): SectionTab[] {
  const base = `/admin/conversations/${conversationId}/content`;
  return [
    {id: 'statements', label: msg('adminconv-card-statements'), href: `${base}/statements`},
    {id: 'participants', label: msg('adminconv-card-participants'), href: `${base}/participants`},
  ];
}
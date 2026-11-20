import type {components} from './api/schema';
import type {Message} from './i18n/messages';

type Session = components['schemas']['Session'];

/** The server refused because maintenance mode is on (#619): 503 with code `maintenance`. */
export function isMaintenance(error: unknown): boolean {
  return error instanceof Error && 'code' in error && error.code === 'maintenance';
}

/** The maintenance notice in place of a screen's own error line, or null for any other error.
 *  A refused vote or statement is not a failure the participant can fix, and saying "could not
 *  save" would suggest it is lost; this says it is a short pause. */
export function maintenanceCopy(msg: Message, error: unknown): string | null {
  return isMaintenance(error) ? msg('maintenance-error') : null;
}

/** For site admins only: maintenance mode is on, so it is not left on by mistake (#619).
 *  Participants learn about the pause where something is refused, not from a banner. */
export function MaintenanceBanner({session, msg}: {session: Session; msg: Message}) {
  if (!session.maintenance || !session.capabilities.administerSite) return null;
  return <p className="maintenance-banner" role="status">{msg('maintenance-banner')}</p>;
}

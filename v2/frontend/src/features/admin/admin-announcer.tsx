import {createContext, useCallback, useContext, useState} from 'react';

/** How urgently a screen reader should read an announcement: `polite` waits for the
 *  reader to finish, `assertive` interrupts (a refusal, a failure). */
export type Politeness = 'polite' | 'assertive';

export type Announcement = {text: string; politeness: Politeness; id: number};

export type Announcer = {
  announcement: Announcement | null;
  announce: (text: string, politeness?: Politeness) => void;
};

/** The state behind the console's one announcement region.
 *
 *  Every call gets a new `id`, and the region renders the text under that id as its React
 *  key, so the text node is replaced even when the words are the same: a second "Statement
 *  12 hidden." is a new addition to the live region, and is read out again. Setting the same
 *  string twice would change nothing in the DOM, and nothing would be read.
 *
 *  A page that announces from its own code (a mutation's `onSuccess`) holds this and hands
 *  it to `AdminShell`; anything rendered inside the shell reaches it through `useAnnounce`. */
export function useAnnouncer(): Announcer {
  const [announcement, setAnnouncement] = useState<Announcement | null>(null);
  const announce = useCallback((text: string, politeness: Politeness = 'polite') => {
    setAnnouncement((previous) => ({text, politeness, id: (previous?.id ?? 0) + 1}));
  }, []);
  return {announcement, announce};
}

const AnnounceContext = createContext<Announcer['announce'] | null>(null);

export const AnnounceProvider = AnnounceContext.Provider;

/** `announce()` for anything rendered inside `AdminShell`; null outside one, so a component
 *  that is also used elsewhere (the legacy toast) can keep its own live region there. */
export function useAnnounce(): Announcer['announce'] | null {
  return useContext(AnnounceContext);
}

/** The two always-mounted live regions: present, and empty, before the first announcement,
 *  because a region created together with its text is often not read at all. Visually
 *  hidden: what they say is already on the page (a toast, a row that moved) or is the
 *  result of an action whose effect is visible. Plain `aria-live`, no role: they are not a
 *  status message or an alert of their own, only the channel that reads one out. */
export function AnnouncerRegions({announcement}: {announcement: Announcement | null}) {
  const say = (politeness: Politeness) => (announcement?.politeness === politeness
    ? <span key={announcement.id}>{announcement.text}</span> : null);
  return (
    <>
      <div className="admin-shell__announcer sr-only" aria-live="polite" aria-atomic="true">{say('polite')}</div>
      <div className="admin-shell__announcer sr-only" aria-live="assertive" aria-atomic="true">{say('assertive')}</div>
    </>
  );
}

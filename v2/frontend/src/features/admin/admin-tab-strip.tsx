import {InternalLink} from '../../internal-link';

/** One sub-navigation strip: the pages of a section, in the order they are read.
 *
 * Every page of a section carries it, so a reader who lands anywhere can reach the other
 * pages of that section in one click without going back to the sidebar. `current` is the
 * id of the page being shown; it is the only one that gets `aria-current="page"`, so the
 * strip never says "you are here" twice. */
export type SectionTab = {id: string; label: string; href: string};

export function AdminTabStrip({label, tabs, current}: {
  label: string;
  tabs: SectionTab[];
  current: string;
}) {
  return (
    <nav className="admin-tabs" aria-label={label}>
      {tabs.map((tab) => (
        <InternalLink
          key={tab.id}
          href={tab.href}
          className="admin-tabs__tab"
          aria-current={tab.id === current ? 'page' : undefined}
        >
          {tab.label}
        </InternalLink>
      ))}
    </nav>
  );
}
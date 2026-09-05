import {useSuspenseQuery} from '@tanstack/react-query';

import {sessionQuery} from '../../api/queries';
import {InternalLink} from '../../internal-link';
import {LegacyShell} from './legacy-shell';

export function ForkPage() {
  const {data: session} = useSuspenseQuery(sessionQuery());

  return (
    <LegacyShell headerMode="fork">
      <div className="container home-container fork-page">
        <div className="landing-section fork-intro">
          <h1 className="fork-intro__title">Where the community actually stands.</h1>
          <p className="fork-intro__copy">
            ProtoWiki makes agreement, disagreement, and the reasons behind both
            easier to see.<br />Choose the playground to try the platform at your own pace,
            or join a real consultation where your contribution becomes part of the
            community’s shared picture.
          </p>
        </div>

        <div className="fork-grid">
          <InternalLink href="/demo" className="fork-card fork-card--demo" aria-label="Try the platform in a playground conversation">
            <svg className="fork-card-icon" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M9 3h6M10 3v6l-5 8a2 2 0 0 0 1.7 3h10.6a2 2 0 0 0 1.7-3l-5-8V3" />
            </svg>
            <h2 className="fork-card-title">Try the playground</h2>
            <div className="fork-card-sub">Explore the full platform in a demonstration conversation.</div>
            <span className="fork-card-cta">Try it →</span>
          </InternalLink>

          <InternalLink href="/consultations" className="fork-card fork-card--real" aria-label="Participate in real consultations, where your contribution counts">
            <svg className="fork-card-icon" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <circle cx="9" cy="8" r="3" /><path d="M3 20a6 6 0 0 1 12 0" />
              <circle cx="17" cy="9" r="2.4" /><path d="M15.5 20a5.5 5.5 0 0 1 6.5-5.4" />
            </svg>
            <h2 className="fork-card-title">Participate in real consultations</h2>
            <div className="fork-card-sub">Join an active conversation. Your contribution counts.</div>
            <span className="fork-card-cta">Participate →</span>
          </InternalLink>
        </div>

        {session.developerLogins.length > 0 && (
          <div className="fork-dev-tools">
            <span className="fork-dev-label">Dev</span>
            {session.developerLogins.map((login) => (
              <InternalLink
                key={login.username}
                href={login.href}
                className="fork-dev-login"
                title={`Log in as ${login.username}`}
              >{login.username}</InternalLink>
            ))}
          </div>
        )}
      </div>
    </LegacyShell>
  );
}

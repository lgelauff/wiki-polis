import {LegacyShell} from './legacy-shell';

export function ForkPage() {
  return (
    <LegacyShell headerMode="fork">
      <div className="container home-container">
        <div className="home-banner">
          Prototype in active development — things may change.{' '}
          <a href="https://github.com/lgelauff/wiki-polis/issues/new" target="_blank" rel="noopener">
            Open an issue<span className="sr-only"> (opens in a new tab)</span>
          </a>{' '}if you find a bug.
        </div>

        <div className="landing-section">
          <h1 style={{fontSize: 26, fontWeight: 600, letterSpacing: '-0.02em', lineHeight: 1.15, marginBottom: 12}}>Where the community actually stands.</h1>
          <p style={{fontSize: 15, lineHeight: 1.6, color: 'var(--body)', maxWidth: 520}}>
            Vote on short statements, and suggest improvements. Learn how your views
            compare to other community members — which statements already have
            consensus, and what topics are divisive, and why.
          </p>
        </div>

        <div className="fork-grid">
          <a href="/app/demo" className="fork-card fork-card--demo" aria-label="Try out the platform — a demonstration conversation where you can try the full flow">
            <svg className="fork-card-icon" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M9 3h6M10 3v6l-5 8a2 2 0 0 0 1.7 3h10.6a2 2 0 0 0 1.7-3l-5-8V3" />
            </svg>
            <h2 className="fork-card-title">Try out the platform</h2>
            <div className="fork-card-sub">Demonstration conversations — try the full flow.</div>
            <span className="fork-card-cta">Try it →</span>
          </a>

          <a href="/app/real" className="fork-card fork-card--real" aria-label="Participate in real consultations — your votes count">
            <svg className="fork-card-icon" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <circle cx="9" cy="8" r="3" /><path d="M3 20a6 6 0 0 1 12 0" />
              <circle cx="17" cy="9" r="2.4" /><path d="M15.5 20a5.5 5.5 0 0 1 6.5-5.4" />
            </svg>
            <h2 className="fork-card-title">Participate in real consultations</h2>
            <div className="fork-card-sub">Your votes count.</div>
            <span className="fork-card-cta">Participate →</span>
          </a>
        </div>
      </div>
    </LegacyShell>
  );
}

export function StatementGuidancePage() {
  return (
    <LegacyShell crumb="statement guide" title="Writing good statements - ProtoWiki">
      <div className="container" style={{maxWidth: 760}}>
        <div className="landing-section">
          <h1 style={{fontSize: 28, fontWeight: 600, color: 'var(--ink)', lineHeight: 1.2, margin: '0 0 12px'}}>Writing good statements</h1>
          <p className="muted">Statements are the short claims participants vote Agree, Disagree, or Pass on. A good statement lets people answer one clear question with one clear vote.</p>
        </div>
        <div className="landing-section">
          <h2>Checklist</h2>
          <ul className="accept-summary-list">
            <li><strong>Make one claim.</strong> If you want to say two things, submit two statements.</li>
            <li><strong>Use neutral wording.</strong> Describe the claim without arguing for the answer.</li>
            <li><strong>Be specific.</strong> Avoid broad wishes that almost everyone can agree with.</li>
            <li><strong>Write a statement.</strong> Do not submit a question, slogan, or topic title.</li>
          </ul>
        </div>
        <div className="landing-section">
          <h2>Examples</h2>
          <p><strong>Split compound claims:</strong></p>
          <p className="muted">Instead of &quot;Wikipedia should require reliable sources and editors should disclose conflicts of interest&quot;, submit one statement about sources and one about conflicts of interest.</p>
          <p><strong>Turn questions into claims:</strong></p>
          <p className="muted">Instead of &quot;Shouldn&apos;t the Wikimedia Foundation be more transparent?&quot;, write &quot;The Wikimedia Foundation should make its grant decision process more transparent.&quot;</p>
        </div>
        <div className="landing-section">
          <h2>When to pass</h2>
          <p className="muted">Passing is fine when a statement is unclear, does not apply to you, or combines claims you would vote on differently. High pass rates are a signal that a statement may need to be split or rewritten next time.</p>
        </div>
      </div>
    </LegacyShell>
  );
}

export function ArgumentGuidancePage() {
  return (
    <LegacyShell crumb="argument guide" title="Writing good arguments - ProtoWiki">
      <div className="container" style={{maxWidth: 760}}>
        <div className="landing-section">
          <h1 style={{fontSize: 28, fontWeight: 600, color: 'var(--ink)', lineHeight: 1.2, margin: '0 0 12px'}}>Writing good arguments</h1>
          <p className="muted">Arguments are a ProtoWiki feature. They explain why someone might support or oppose a featured statement; they are read by people, not used by the clustering algorithm.</p>
        </div>
        <div className="landing-section">
          <h2>Checklist</h2>
          <ul className="accept-summary-list">
            <li><strong>State the direction.</strong> Make clear whether the argument is for or against the statement.</li>
            <li><strong>Add a reason.</strong> Do not just restate your vote.</li>
            <li><strong>Make one point.</strong> If you have several reasons, write separate arguments.</li>
            <li><strong>Be specific.</strong> Name a mechanism, consequence, example, or precedent.</li>
            <li><strong>Argue the claim.</strong> Do not argue about the person who wrote it.</li>
          </ul>
        </div>
        <div className="landing-section">
          <h2>Examples</h2>
          <p><strong>Weak:</strong></p>
          <p className="muted">&quot;I disagree because this would be bad for the project.&quot;</p>
          <p><strong>Stronger:</strong></p>
          <p className="muted">&quot;Against: this would disproportionately affect new editors, who are less likely to know sourcing conventions and more likely to be discouraged by rejection.&quot;</p>
        </div>
        <div className="landing-section">
          <h2>Moderation baseline</h2>
          <p className="muted">Keep the argument about the statement. Personal attacks, harassment, and content that violates Wikimedia conduct expectations may be removed.</p>
        </div>
      </div>
    </LegacyShell>
  );
}

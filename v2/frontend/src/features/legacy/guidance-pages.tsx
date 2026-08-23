import {LegacyShell} from './legacy-shell';

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

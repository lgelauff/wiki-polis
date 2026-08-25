import {useState} from 'react';

type FlowPhase = 'explore' | 'arguments' | 'informed';

const FLOW_STORAGE_KEY = 'proto-wiki.conversation-flow.collapsed.v1';

function PhaseIllustration({phase}: {phase: FlowPhase}) {
  if (phase === 'explore') {
    return (
      <svg className="flow-rebuild__illustration" viewBox="0 0 190 120" aria-hidden="true">
        <rect x="26" y="14" width="138" height="46" rx="9" className="flow-svg-surface" />
        <path d="M42 31h78M42 43h54" className="flow-svg-copy" />
        <g transform="rotate(38 150 44)">
          <rect x="120" y="38" width="40" height="12" rx="2" className="flow-svg-pencil" />
          <rect x="116" y="38" width="8" height="12" className="flow-svg-pencil-band" />
          <path d="m160 38 10 6-10 6Z" className="flow-svg-ink" />
        </g>
        <g transform="translate(58 78)">
          <rect width="30" height="30" rx="7" className="flow-svg-agree-box" />
          <path d="m9 15 4 4 8-9" className="flow-svg-agree-mark" />
        </g>
        <g transform="translate(102 78)">
          <rect width="30" height="30" rx="7" className="flow-svg-disagree-box" />
          <path d="m10 10 10 10m0-10L10 20" className="flow-svg-disagree-mark" />
        </g>
      </svg>
    );
  }

  if (phase === 'arguments') {
    return (
      <svg className="flow-rebuild__illustration" viewBox="0 0 190 120" aria-hidden="true">
        <rect x="26" y="6" width="138" height="34" rx="8" className="flow-svg-surface" />
        <path d="M40 18h78M40 28h54" className="flow-svg-copy" />
        <rect x="30" y="52" width="118" height="24" rx="7" className="flow-svg-pro-box" />
        <path d="M40 64h10m-5-5v10" className="flow-svg-pro-mark" />
        <g transform="rotate(34 150 64)">
          <rect x="120" y="59" width="30" height="9" rx="1.5" className="flow-svg-pencil" />
          <rect x="117" y="59" width="6" height="9" className="flow-svg-pencil-band" />
          <path d="m150 59 8 4.5-8 4.5Z" className="flow-svg-ink" />
        </g>
        <rect x="30" y="84" width="118" height="24" rx="7" className="flow-svg-con-box" />
        <path d="M40 96h10" className="flow-svg-con-mark" />
        <g transform="rotate(34 150 96)">
          <rect x="120" y="91" width="30" height="9" rx="1.5" className="flow-svg-pencil" />
          <rect x="117" y="91" width="6" height="9" className="flow-svg-pencil-band" />
          <path d="m150 91 8 4.5-8 4.5Z" className="flow-svg-ink" />
        </g>
      </svg>
    );
  }

  return (
    <svg className="flow-rebuild__illustration" viewBox="0 0 190 120" aria-hidden="true">
      <rect x="26" y="4" width="138" height="30" rx="8" className="flow-svg-surface" />
      <path d="M40 14h78M40 24h54" className="flow-svg-copy" />
      <g transform="translate(30 44)">
        <rect width="60" height="24" rx="6" className="flow-svg-agree-box" />
        <path d="M11 12h9m-4.5-4.5v9" className="flow-svg-agree-mark" />
        <path d="M28 8.5h22M28 15.5h14" className="flow-svg-rowcopy" />
      </g>
      <g transform="translate(100 44)">
        <rect width="60" height="24" rx="6" className="flow-svg-con-box" />
        <path d="M11 12h9" className="flow-svg-con-mark" />
        <path d="M28 8.5h22M28 15.5h14" className="flow-svg-rowcopy" />
      </g>
      <g transform="translate(58 78)">
        <rect width="30" height="30" rx="7" className="flow-svg-agree-box" />
        <path d="m9 15 4 4 8-9" className="flow-svg-agree-mark" />
      </g>
      <g transform="translate(102 78)">
        <rect width="30" height="30" rx="7" className="flow-svg-disagree-box" />
        <path d="m10 10 10 10m0-10L10 20" className="flow-svg-disagree-mark" />
      </g>
    </svg>
  );
}

function LearningIcon({phase}: {phase: FlowPhase}) {
  if (phase === 'explore') {
    return (
      <svg viewBox="0 0 40 36" aria-hidden="true">
        <circle cx="9" cy="11" r="3.2" /><circle cx="20" cy="7" r="3.2" />
        <circle cx="16" cy="19" r="3.2" /><circle cx="28" cy="15" r="3.2" opacity=".55" />
        <circle cx="11" cy="25" r="3.2" opacity=".55" /><circle cx="30" cy="26" r="3.2" opacity=".55" />
      </svg>
    );
  }
  if (phase === 'arguments') {
    return (
      <svg viewBox="0 0 40 36" aria-hidden="true">
        <rect x="4" y="5" width="14" height="10" rx="2.5" className="flow-learn-pro" />
        <path d="M8 10h6m-3-3v6" className="flow-learn-pro-mark" />
        <path d="M25 7.5h13M25 12.5h8" className="flow-learn-copy" />
        <rect x="4" y="20" width="14" height="10" rx="2.5" className="flow-learn-con" />
        <path d="M8 25h6" className="flow-learn-con-mark" />
        <path d="M25 22.5h13M25 27.5h8" className="flow-learn-copy" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 40 36" aria-hidden="true">
      <rect x="5" y="16" width="8" height="14" rx="2" />
      <rect x="16" y="8" width="8" height="22" rx="2" />
      <rect x="27" y="20" width="8" height="10" rx="2" opacity=".55" />
    </svg>
  );
}

function FlowCard({
  phase,
  title,
  instruction,
  learning,
}: {
  phase: FlowPhase;
  title: string;
  instruction: string;
  learning: string;
}) {
  return (
    <article className="flow-rebuild__card">
      <h3>{title}</h3>
      <PhaseIllustration phase={phase} />
      <p className="flow-rebuild__instruction">{instruction}</p>
      <div className="flow-rebuild__learning">
        <p className="flow-rebuild__learning-label">What we learn</p>
        <div className="flow-rebuild__learning-body">
          <LearningIcon phase={phase} />
          <p>{learning}</p>
        </div>
      </div>
    </article>
  );
}

function StepArrow() {
  return <span className="flow-rebuild__step-arrow" aria-hidden="true" />;
}

export function ConversationFlow() {
  const [collapsed, setCollapsed] = useState(() => {
    try {
      return localStorage.getItem(FLOW_STORAGE_KEY) === 'collapsed';
    } catch {
      return false;
    }
  });

  function toggleOverview() {
    const nextCollapsed = !collapsed;
    try {
      localStorage.setItem(FLOW_STORAGE_KEY, nextCollapsed ? 'collapsed' : 'expanded');
    } catch {
      // Storage can be unavailable in privacy-restricted browsers; the control
      // still works for the lifetime of the current page.
    }
    setCollapsed(nextCollapsed);
  }

  return (
    <section className={`flow-rebuild${collapsed ? ' flow-rebuild--collapsed' : ''}`} aria-labelledby="flow-rebuild-title">
      <header className="flow-rebuild__heading">
        <h2 id="flow-rebuild-title">How a ProtoWiki conversation works</h2>
        <button
          className="flow-rebuild__toggle"
          type="button"
          aria-expanded={!collapsed}
          aria-controls="flow-rebuild-content"
          aria-label={`${collapsed ? 'Show' : 'Hide'} conversation overview`}
          onClick={toggleOverview}
        >
          <span>{collapsed ? 'Show' : 'Hide'}</span>
          <span className="flow-rebuild__toggle-chevron" aria-hidden="true" />
        </button>
      </header>

      <div id="flow-rebuild-content" hidden={collapsed}>
        <p className="flow-rebuild__intro">Not a decision exercise — a shared picture of where a community agrees, disagrees, and why.</p>

        <div className="flow-rebuild__steps">
          <FlowCard
            phase="explore"
            title="Explore the questions"
            instruction="Vote yes / no — and edit or add statements"
            learning="Clusters of statements that inform the topic"
          />
          <StepArrow />
          <FlowCard
            phase="arguments"
            title="Map the arguments"
            instruction="Write the pro & con arguments that matter"
            learning="A map of the arguments that matter, pro & con"
          />
          <StepArrow />
          <FlowCard
            phase="informed"
            title="Express informed opinions"
            instruction="Vote again, with the key arguments shown"
            learning="How different parts of the community feel"
          />
        </div>

        <svg className="flow-rebuild__merge" viewBox="0 0 1104 54" preserveAspectRatio="none" aria-hidden="true">
          <path d="M174 0c0 26 378 18 378 36M552 0v36M930 0c0 26-378 18-378 36M552 36v14m-6-6 6 6 6-6" />
          <circle cx="552" cy="36" r="2.6" />
        </svg>

        <div className="flow-rebuild__outcome">
          <span className="flow-rebuild__outcome-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
              <path d="M14 2v6h6" />
              <path d="m9 14 2 2 4-4" className="flow-outcome-check" />
            </svg>
          </span>
          <strong>A more balanced policy draft</strong>
        </div>
      </div>
    </section>
  );
}

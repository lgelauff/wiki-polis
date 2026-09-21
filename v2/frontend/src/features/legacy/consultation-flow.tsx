import type {ReactNode} from 'react';

import {useMessage} from '../../i18n/messages';

// How a consultation process works: three rounds, what each one teaches, and what they add up
// to. The words come from the catalogue so the diagram reads in the page's language; the
// drawings beside them are decorative and carry no text, so there is nothing in them to
// translate. v2/figures/flowchart/ keeps an English-only SVG export for slides and papers.
// Their colours come from the .flow-svg-* classes in style.css, so they follow the tokens.

const GLYPH = {width: 190, height: 112} as const;

function ExploreGlyph() {
  return (
    <svg className="flow-glyph" viewBox={`0 0 ${GLYPH.width} ${GLYPH.height}`} aria-hidden="true" focusable="false">
      <rect x="26" y="14" width="138" height="46" rx="9" className="flow-svg-surface" strokeWidth="1.5" />
      <line x1="42" y1="31" x2="120" y2="31" className="flow-svg-copy" strokeWidth="3.2" strokeLinecap="round" />
      <line x1="42" y1="43" x2="96" y2="43" className="flow-svg-copy" strokeWidth="3.2" strokeLinecap="round" />
      <g transform="rotate(38 150 44)">
        <rect x="120" y="38" width="40" height="12" rx="2" className="flow-svg-pass" />
        <rect x="116" y="38" width="8" height="12" className="flow-svg-spot" />
        <path d="M160 38 L170 44 L160 50 Z" className="flow-svg-ink" />
      </g>
      <AgreeTile x={58} y={78} />
      <DisagreeTile x={102} y={78} />
    </svg>
  );
}

function ArgumentsGlyph() {
  return (
    <svg className="flow-glyph" viewBox={`0 0 ${GLYPH.width} ${GLYPH.height}`} aria-hidden="true" focusable="false">
      <rect x="26" y="6" width="138" height="34" rx="8" className="flow-svg-surface" strokeWidth="1.5" />
      <line x1="40" y1="18" x2="118" y2="18" className="flow-svg-copy" strokeWidth="3.2" strokeLinecap="round" />
      <line x1="40" y1="28" x2="94" y2="28" className="flow-svg-copy" strokeWidth="3.2" strokeLinecap="round" />
      <rect x="30" y="52" width="118" height="24" rx="7" className="flow-svg-pro-box" strokeWidth="1.5" strokeDasharray="4 3" />
      <path d="M40 64 h10 M45 59 v10" className="flow-svg-agree" strokeWidth="2.4" strokeLinecap="round" />
      <Pencil x={120} y={59} />
      <rect x="30" y="84" width="118" height="24" rx="7" className="flow-svg-con-box" strokeWidth="1.5" strokeDasharray="4 3" />
      <path d="M40 96 h10" className="flow-svg-con" strokeWidth="2.4" strokeLinecap="round" />
      <Pencil x={120} y={91} />
    </svg>
  );
}

function InformedGlyph() {
  return (
    <svg className="flow-glyph" viewBox={`0 0 ${GLYPH.width} ${GLYPH.height}`} aria-hidden="true" focusable="false">
      <rect x="26" y="4" width="138" height="30" rx="8" className="flow-svg-surface" strokeWidth="1.5" />
      <line x1="40" y1="14" x2="118" y2="14" className="flow-svg-copy" strokeWidth="3.2" strokeLinecap="round" />
      <line x1="40" y1="24" x2="94" y2="24" className="flow-svg-copy" strokeWidth="3.2" strokeLinecap="round" />
      <g transform="translate(34 44)">
        <rect width="56" height="20" rx="6" className="flow-svg-agree-box" strokeWidth="1.3" />
        <path d="M12 10 h9 M16.5 5.5 v9" className="flow-svg-agree" strokeWidth="2.2" strokeLinecap="round" />
        <line x1="30" y1="10" x2="48" y2="10" className="flow-svg-agree" strokeWidth="2.6" strokeLinecap="round" opacity="0.6" />
      </g>
      <g transform="translate(100 44)">
        <rect width="56" height="20" rx="6" className="flow-svg-con-box" strokeWidth="1.3" />
        <path d="M12 10 h9" className="flow-svg-con" strokeWidth="2.2" strokeLinecap="round" />
        <line x1="30" y1="10" x2="48" y2="10" className="flow-svg-con" strokeWidth="2.6" strokeLinecap="round" opacity="0.6" />
      </g>
      <AgreeTile x={58} y={78} />
      <DisagreeTile x={102} y={78} />
    </svg>
  );
}

function AgreeTile({x, y}: {x: number; y: number}) {
  return (
    <g transform={`translate(${x} ${y})`}>
      <rect width="30" height="30" rx="7" className="flow-svg-agree-box" strokeWidth="1.5" />
      <path d="M9 15 L13 19 L21 10" className="flow-svg-agree" strokeWidth="2.6" fill="none" strokeLinecap="round" strokeLinejoin="round" />
    </g>
  );
}

function DisagreeTile({x, y}: {x: number; y: number}) {
  return (
    <g transform={`translate(${x} ${y})`}>
      <rect width="30" height="30" rx="7" className="flow-svg-disagree-box" strokeWidth="1.5" />
      <path d="M10 10 L20 20 M20 10 L10 20" className="flow-svg-disagree" strokeWidth="2.6" strokeLinecap="round" />
    </g>
  );
}

function Pencil({x, y}: {x: number; y: number}) {
  return (
    <g transform={`rotate(34 ${x + 30} ${y + 5})`}>
      <rect x={x} y={y} width="30" height="9" rx="1.5" className="flow-svg-pass" />
      <rect x={x - 3} y={y} width="6" height="9" className="flow-svg-spot" />
      <path d={`M${x + 30} ${y} L${x + 38} ${y + 4.5} L${x + 30} ${y + 9} Z`} className="flow-svg-ink" />
    </g>
  );
}

function ClustersIcon() {
  return (
    <svg className="flow-learn-icon" viewBox="0 0 40 32" aria-hidden="true" focusable="false">
      <circle cx="9" cy="11" r="3.2" className="flow-svg-pass" />
      <circle cx="20" cy="7" r="3.2" className="flow-svg-pass" />
      <circle cx="16" cy="19" r="3.2" className="flow-svg-pass" />
      <circle cx="28" cy="15" r="3.2" className="flow-svg-pass" opacity="0.55" />
      <circle cx="11" cy="25" r="3.2" className="flow-svg-pass" opacity="0.55" />
      <circle cx="30" cy="26" r="3.2" className="flow-svg-pass" opacity="0.55" />
    </svg>
  );
}

function ArgumentMapIcon() {
  return (
    <svg className="flow-learn-icon" viewBox="0 0 40 32" aria-hidden="true" focusable="false">
      <rect x="4" y="5" width="14" height="10" rx="2.5" className="flow-svg-agree-box" strokeWidth="1.3" />
      <path d="M8 10 h6 M11 7 v6" className="flow-svg-agree" strokeWidth="1.6" strokeLinecap="round" />
      <rect x="22" y="6" width="14" height="8" rx="2.5" className="flow-svg-pro-fill" />
      <rect x="4" y="20" width="14" height="10" rx="2.5" className="flow-svg-con-box" strokeWidth="1.3" />
      <path d="M8 25 h6" className="flow-svg-con" strokeWidth="1.6" strokeLinecap="round" />
      <rect x="22" y="21" width="14" height="8" rx="2.5" className="flow-svg-con-fill" />
    </svg>
  );
}

function BarsIcon() {
  return (
    <svg className="flow-learn-icon" viewBox="0 0 40 32" aria-hidden="true" focusable="false">
      <rect x="5" y="16" width="8" height="14" rx="2" className="flow-svg-pass" />
      <rect x="16" y="8" width="8" height="22" rx="2" className="flow-svg-pass" />
      <rect x="27" y="20" width="8" height="10" rx="2" className="flow-svg-pass" opacity="0.55" />
    </svg>
  );
}

function OutcomeIcon() {
  return (
    <span className="flow-outcome-icon" aria-hidden="true">
      {/* The report symbol's own outline, not Feather's file-text, whose MIT notice would
          have to travel with it (#325). */}
      <svg viewBox="0 0 24 24" focusable="false" className="flow-svg-line" fill="none" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="M5 2h9l5 5v15H5z" />
        <path d="M14 2v5h5" />
        <path d="M9 14l2 2 4-4" className="flow-svg-agree" />
      </svg>
    </span>
  );
}

function FlowStep({title, body, learnLabel, learn, glyph, icon}: {
  title: string;
  body: string;
  learnLabel: string;
  learn: string;
  glyph: ReactNode;
  icon: ReactNode;
}) {
  return (
    <li className="flow-step">
      <h3 className="flow-step-title">{title}</h3>
      {glyph}
      <p className="flow-step-body">{body}</p>
      <div className="flow-learn">
        <span className="flow-learn-label">{learnLabel}</span>
        <div className="flow-learn-row">
          {icon}
          <p>{learn}</p>
        </div>
      </div>
    </li>
  );
}

export function ConsultationFlow() {
  const msg = useMessage();
  const learnLabel = msg('flow-learn-label');
  return (
    <section className="flow" aria-labelledby="flow-title">
      <h2 id="flow-title" className="flow-title">{msg('flow-title')}</h2>
      <p className="flow-subtitle">{msg('flow-subtitle')}</p>
      {/* role="list": Safari drops the list semantics of a list styled list-style: none, and
          the rounds being a list of three, in order, is what a screen reader needs from it. */}
      <ol className="flow-steps" role="list">
        <FlowStep
          title={msg('flow-explore-title')} body={msg('flow-explore-body')}
          learnLabel={learnLabel} learn={msg('flow-explore-learn')}
          glyph={<ExploreGlyph />} icon={<ClustersIcon />}
        />
        <FlowStep
          title={msg('flow-arguments-title')} body={msg('flow-arguments-body')}
          learnLabel={learnLabel} learn={msg('flow-arguments-learn')}
          glyph={<ArgumentsGlyph />} icon={<ArgumentMapIcon />}
        />
        <FlowStep
          title={msg('flow-informed-title')} body={msg('flow-informed-body')}
          learnLabel={learnLabel} learn={msg('flow-informed-learn')}
          glyph={<InformedGlyph />} icon={<BarsIcon />}
        />
      </ol>
      <svg className="flow-merge" viewBox="0 0 1104 48" preserveAspectRatio="none" aria-hidden="true" focusable="false">
        <g className="flow-svg-line" strokeWidth="1.75" fill="none" strokeLinecap="round">
          <path d="M174 0 C174 26, 552 18, 552 36" vectorEffect="non-scaling-stroke" />
          <path d="M552 0 L552 36" vectorEffect="non-scaling-stroke" />
          <path d="M930 0 C930 26, 552 18, 552 36" vectorEffect="non-scaling-stroke" />
          <path d="M552 36 L552 47" vectorEffect="non-scaling-stroke" />
          <path d="M546 41 L552 47 L558 41" vectorEffect="non-scaling-stroke" />
        </g>
      </svg>
      <p className="flow-outcome"><OutcomeIcon />{msg('flow-outcome')}</p>
    </section>
  );
}

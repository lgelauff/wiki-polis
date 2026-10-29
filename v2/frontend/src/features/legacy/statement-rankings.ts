import type {components} from '../../api/schema';

type Statement = components['schemas']['ResultsStatement'];
type VoteTally = NonNullable<Statement['initial']>;
type OpinionRound = 'initial' | 'informed';

/** Opinion data shows from 10 responses on, in every view (owner, 2026-10-15). The backend
 *  does not floor these tallies yet (#233), so the ranking applies the floor itself. */
export const RANKING_FLOOR = 10;

function tallyFor(statement: Statement, round: OpinionRound): VoteTally | null {
  return round === 'initial' ? statement.initial : statement.informed;
}

export function rankOpinionStatements(statements: Statement[], round: OpinionRound) {
  const available = statements.flatMap((statement) => {
    const tally = tallyFor(statement, round);
    return tally && tally.counts.voters >= RANKING_FLOOR ? [{statement, tally}] : [];
  });
  const consensus = [...available]
    .sort((left, right) => right.tally.percentages.agree - left.tally.percentages.agree)
    .slice(0, 3)
    .map(({statement}) => statement);
  // Divisive means many people on both sides: rank by the smaller of agree and disagree.
  // A statement nobody agreed or nobody disagreed with is not divisive, whatever its pass share.
  const split = ({tally}: {tally: VoteTally}) =>
    Math.min(tally.percentages.agree, tally.percentages.disagree);
  const divisive = available
    .filter((row) => split(row) > 0)
    .sort((left, right) => split(right) - split(left))
    .slice(0, 3)
    .map(({statement}) => statement);
  return {consensus, divisive};
}

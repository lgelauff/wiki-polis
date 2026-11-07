import type {components} from '../../api/schema';

type Statement = components['schemas']['ResultsStatement'];
type VoteTally = NonNullable<Statement['initial']>;
type Percentages = NonNullable<VoteTally['percentages']>;
type OpinionRound = 'initial' | 'informed';

function tallyFor(statement: Statement, round: OpinionRound): VoteTally | null {
  return round === 'initial' ? statement.initial : statement.informed;
}

export function rankOpinionStatements(statements: Statement[], round: OpinionRound) {
  // The server withholds a tally below the reporting floor (#233); only shown tallies rank.
  const available = statements.flatMap((statement) => {
    const percentages = tallyFor(statement, round)?.percentages;
    return percentages ? [{statement, percentages}] : [];
  });
  const consensus = [...available]
    .sort((left, right) => right.percentages.agree - left.percentages.agree)
    .slice(0, 3)
    .map(({statement}) => statement);
  // Divisive means many people on both sides: rank by the smaller of agree and disagree.
  // A statement nobody agreed or nobody disagreed with is not divisive, whatever its pass share.
  const split = ({percentages}: {percentages: Percentages}) =>
    Math.min(percentages.agree, percentages.disagree);
  const divisive = available
    .filter((row) => split(row) > 0)
    .sort((left, right) => split(right) - split(left))
    .slice(0, 3)
    .map(({statement}) => statement);
  return {consensus, divisive};
}

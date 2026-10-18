import type {components} from '../../api/schema';

type Statement = components['schemas']['ResultsStatement'];
type VoteTally = NonNullable<Statement['initial']>;
type OpinionRound = 'initial' | 'informed';

function tallyFor(statement: Statement, round: OpinionRound): VoteTally | null {
  return round === 'initial' ? statement.initial : statement.informed;
}

export function rankOpinionStatements(statements: Statement[], round: OpinionRound) {
  const available = statements.flatMap((statement) => {
    const tally = tallyFor(statement, round);
    return tally && tally.counts.voters > 0 ? [{statement, tally}] : [];
  });
  const consensus = [...available]
    .sort((left, right) => right.tally.percentages.agree - left.tally.percentages.agree)
    .slice(0, 3)
    .map(({statement}) => statement);
  const divisive = [...available]
    .sort((left, right) => {
      const leftGap = Math.abs(left.tally.percentages.agree - left.tally.percentages.disagree);
      const rightGap = Math.abs(right.tally.percentages.agree - right.tally.percentages.disagree);
      return leftGap - rightGap;
    })
    .slice(0, 3)
    .map(({statement}) => statement);
  return {consensus, divisive};
}

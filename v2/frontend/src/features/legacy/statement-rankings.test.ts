import {expect, test} from 'vitest';

import type {components} from '../../api/schema';
import {RANKING_FLOOR, rankOpinionStatements} from './statement-rankings';

type Statement = components['schemas']['ResultsStatement'];

function row(id: number, agree: number, pass: number, disagree: number): Statement {
  const voters = agree + pass + disagree;
  const share = (n: number) => (voters ? (100 * n) / voters : 0);
  const tally = {
    counts: {agree, pass, disagree, voters},
    percentages: {agree: share(agree), pass: share(pass), disagree: share(disagree)},
  };
  return {
    featuredStatementId: id, statement: `Statement ${id}`, initial: tally, informed: tally,
    agreementShift: null, viewerChoice: null, viewerGroupChoice: null, viewerMatchesGroup: null,
    personalDelta: null,
  };
}

const ids = (statements: Statement[]) => statements.map((s) => s.featuredStatementId);

test('a statement below the floor is never ranked, however one-sided', () => {
  const {consensus, divisive} = rankOpinionStatements(
    [row(1, RANKING_FLOOR - 1, 0, 0), row(2, 4, 0, 5), row(3, 7, 0, 3)],
    'informed',
  );

  expect(ids(consensus)).toEqual([3]);
  expect(ids(divisive)).toEqual([3]);
});

test('an all-pass statement is not the most divisive', () => {
  const {divisive} = rankOpinionStatements([row(1, 0, 20, 0), row(2, 12, 0, 8)], 'informed');

  expect(ids(divisive)).toEqual([2]);
});

test('a one-sided statement is not divisive', () => {
  const {divisive} = rankOpinionStatements([row(1, 20, 0, 0), row(2, 0, 2, 18)], 'informed');

  expect(divisive).toEqual([]);
});

test('divisive ranks by the smaller side, at most three', () => {
  const {divisive} = rankOpinionStatements(
    [row(1, 18, 0, 2), row(2, 10, 0, 10), row(3, 6, 10, 4), row(4, 14, 0, 6), row(5, 12, 0, 8)],
    'informed',
  );

  expect(ids(divisive)).toEqual([2, 5, 4]);
});

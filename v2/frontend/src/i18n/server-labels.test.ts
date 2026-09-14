import {describe, expect, test} from 'vitest';

import type {Message} from './messages';
import {outputLabel, outputPending, outputTooltip, phaseLabel, routeLabel, tabLabel} from './server-labels';

/** A catalogue whose values are deliberately UNLIKE the server's English. Every assertion
 *  below distinguishes "read the catalogue" from "echoed the server label" -- which the
 *  integration fixtures cannot do, because there the two sources are byte-identical. */
const CATALOGUE: Record<string, string> = {
  'conv-tab-vote': 'CATALOGUE vote tab',
  'phase-label-submission': 'CATALOGUE explore',
  'phase-label-closed': 'CATALOGUE closed',
  'phase-label-cleanup': 'CATALOGUE cleanup',
  'phase-route-default_7': 'CATALOGUE default route',
  'output-report-label': 'CATALOGUE report',
  'output-report-tooltip': 'CATALOGUE report tooltip',
  'output-report-pending': 'CATALOGUE report pending',
};

/** Stands in for banana: returns the key itself for a message it does not hold, which is
 *  the behaviour the fallback in `resolve()` has to detect. */
const msg: Message = (key, ...params) =>
  CATALOGUE[key] ?? (params.length ? `${key}(${params.join(',')})` : key);

describe('server identifier -> message', () => {
  test('the catalogue wins over the server label', () => {
    expect(tabLabel(msg, 'vote', 'Vote')).toBe('CATALOGUE vote tab');
    expect(phaseLabel(msg, 'submission', 'Explore')).toBe('CATALOGUE explore');
    expect(routeLabel(msg, 'default_7', 'Default 7-step path')).toBe('CATALOGUE default route');
  });

  test('an identifier the table does not know falls back to the server label', () => {
    expect(phaseLabel(msg, 'some_new_phase', 'Some New Phase')).toBe('Some New Phase');
    expect(tabLabel(msg, 'brand-new-tab', 'Brand New Tab')).toBe('Brand New Tab');
  });

  test('a key the catalogue does not hold falls back to the server label', () => {
    // 'informed_voting' is in the table; its message is absent from CATALOGUE above, so a
    // naive implementation returns the bare key and renders 'phase-label-informed_voting'
    // to the user -- as a tab's accessible name, in the tab-bar case.
    expect(phaseLabel(msg, 'informed_voting', 'Informed vote')).toBe('Informed vote');
    expect(tabLabel(msg, 'results', 'Intermediate results')).toBe('Intermediate results');
  });

  test('a missing key with no server label degrades to the identifier, never to a key', () => {
    expect(phaseLabel(msg, 'informed_voting')).toBe('informed_voting');
    expect(phaseLabel(msg, 'informed_voting', null)).toBe('informed_voting');
  });

  test('no identifier and no label render nothing rather than "undefined"', () => {
    expect(phaseLabel(msg, null, null)).toBe('');
    expect(phaseLabel(msg, undefined)).toBe('');
  });

  test('the cleanup window and the cleanup phase share one message', () => {
    expect(phaseLabel(msg, 'cleanup_window', 'Cleanup')).toBe('CATALOGUE cleanup');
    expect(phaseLabel(msg, 'cleanup', 'Cleanup')).toBe('CATALOGUE cleanup');
  });

  test('the terminal phase uses a phase-name key, not the admin status key', () => {
    expect(phaseLabel(msg, 'closed', 'Closed')).toBe('CATALOGUE closed');
  });

  test('an identifier colliding with Object.prototype does not reach msg()', () => {
    // A bare `table[id]` lookup would hand Object.prototype.constructor to msg().
    expect(phaseLabel(msg, 'constructor', 'Fallback')).toBe('Fallback');
    expect(tabLabel(msg, 'toString', 'Fallback')).toBe('Fallback');
    expect(routeLabel(msg, 'hasOwnProperty')).toBe('hasOwnProperty');
  });

  test('qqx stays visible: a parenthesised key is a real translation, not a miss', () => {
    // ?uselang=qqx renders '(conv-tab-vote)'. That differs from the key, so it must win --
    // this is why resolve() compares against the key rather than testing for emptiness.
    const qqx: Message = (key) => `(${key})`;
    expect(tabLabel(qqx, 'vote', 'Vote')).toBe('(conv-tab-vote)');
  });

  test('an output reads its label, tooltip and pending note from three separate tables', () => {
    // One table per field, so that a mix-up (the tooltip rendered as the label) shows here.
    expect(outputLabel(msg, 'report', 'Report')).toBe('CATALOGUE report');
    expect(outputTooltip(msg, 'report', 'After closing')).toBe('CATALOGUE report tooltip');
    expect(outputPending(msg, 'report', 'Published after cleanup')).toBe('CATALOGUE report pending');
    expect(outputLabel(msg, 'dataset', 'Dataset')).toBe('Dataset');
  });
});

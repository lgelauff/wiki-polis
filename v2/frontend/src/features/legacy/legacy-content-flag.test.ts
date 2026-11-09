import {expect, test} from 'vitest';

import {placeFlagPanel} from './legacy-content-flag';

// The trigger is 22px wide; bounds are the visible edges the panel must stay inside (#254).
const at = (left: number) => ({left, right: left + 22});

test.each([
  // room leftward = trigger.right - bounds.left; room rightward = bounds.right - trigger.left
  {name: 'leftward fits exactly', trigger: at(198), bounds: {left: 0, right: 1000}, expected: {opensRight: false}},
  {name: 'leftward 1px short, rightward fits', trigger: at(197), bounds: {left: 0, right: 1000}, expected: {opensRight: true}},
  {name: 'rightward fits exactly', trigger: at(100), bounds: {left: 0, right: 320}, expected: {opensRight: true}},
  {name: 'neither fits, left wider', trigger: at(180), bounds: {left: 0, right: 360}, expected: {opensRight: false, width: 194}},
  {name: 'neither fits, right wider', trigger: at(150), bounds: {left: 10, right: 320}, expected: {opensRight: true, width: 162}},
  {name: 'tiny space keeps a usable width', trigger: at(40), bounds: {left: 0, right: 120}, expected: {opensRight: true, width: 160}},
])('$name', ({trigger, bounds, expected}) => {
  expect(placeFlagPanel(trigger, bounds)).toEqual(expected);
});

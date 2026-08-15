import {expect, test} from 'vitest';

import {routeChunkForPath} from './route-modules';

test.each([
  ['/admin', 'admin'],
  ['/admin/conversations/7/statements', 'admin'],
  ['/help/statements', 'guidance'],
  ['/accept/topic', 'participation-entry'],
  ['/c/topic/about', 'conversation-read'],
  ['/c/topic/moderation-log', 'conversation-read'],
  ['/c/topic/outputs/map?download=0', 'conversation-read'],
  ['/c/topic/report#methodology', 'results'],
  ['/c/topic/reveal', 'identity-reveal'],
  ['/c/topic', null],
  ['/consultations', null],
])('maps %s to lazy chunk %s', (path, expected) => {
  expect(routeChunkForPath(path)).toBe(expected);
});

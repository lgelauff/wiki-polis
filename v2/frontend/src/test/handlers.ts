import {http, HttpResponse} from 'msw';

export const handlers = [
  http.get(
    new URL('/api/v1/session', globalThis.location.origin).toString(),
    () => HttpResponse.json({
      data: {
        state: 'authenticated',
        user: {username: 'Example editor', emailable: true},
        capabilities: {administerSite: false},
        csrfToken: 'test-csrf-token',
        links: {login: '/login', logout: '/logout'},
      },
    }),
  ),
  http.get(
    new URL('/api/v1/conversations', globalThis.location.origin).toString(),
    ({request}) => {
    const space = new URL(request.url).searchParams.get('space') ?? 'real';
    return HttpResponse.json({
      data: {
        space,
        authenticated: true,
        groups: {
          needsAttention: [{
            slug: 'community-strategy',
            title: 'Community strategy',
            relationship: 'joined',
            participantState: 'needs_attention',
            pseudonym: 'quiet-otter',
            status: 'open',
            phases: ['submission'],
            statementsRemaining: 4,
            scheduledTransition: null,
            outputs: [],
            capabilities: {join: false, participate: true, moderate: false},
            links: {self: '/c/community-strategy', about: '/c/community-strategy/about'},
          }],
          caughtUp: [],
          inactive: [],
          archived: [],
          available: [],
          moderating: [],
        },
      },
    });
    },
  ),
  http.get(
    new URL('/api/v1/conversations/community-strategy/about', globalThis.location.origin).toString(),
    () => HttpResponse.json({
      data: {
        slug: 'community-strategy',
        title: 'Community strategy',
        descriptionHtml: '<p>Shape the next chapter together.</p>',
        outroHtml: null,
        status: 'open',
        phases: [{key: 'submission', label: 'Explore'}],
        scheduledTransition: null,
        pseudonym: 'quiet-otter',
        statistics: {
          participants: 24,
          statementVotes: 312,
          statements: 42,
          arguments: 9,
          argumentContributors: 6,
        },
        personal: {
          statementsSuggested: 2,
          statementVotes: 18,
          statementVotesAvailable: true,
          argumentsAdded: 1,
          argumentsRated: 3,
        },
        outputs: [{
          key: 'report', label: 'Final report', status: 'final', ready: false,
          href: '/c/community-strategy/report',
        }],
        moderation: {eventCount: 1, href: '/c/community-strategy/moderation-log'},
        capabilities: {participate: true, moderate: false},
        links: {
          self: '/api/v1/conversations/community-strategy/about',
          conversation: '/c/community-strategy',
        },
      },
    }),
  ),
  http.get(
    new URL('/api/v1/conversations/community-strategy/pseudonym-suggestions', globalThis.location.origin).toString(),
    () => HttpResponse.json({
      data: {pseudonyms: ['quiet-otter', 'bright-fox', 'steady-heron']},
    }),
  ),
  http.post(
    new URL('/api/v1/conversations/community-strategy/participation', globalThis.location.origin).toString(),
    () => HttpResponse.json({
      data: {
        pseudonym: 'quiet-otter',
        notifications: {email: false, talkPage: false},
        eligibilityStatus: 'not_required',
        links: {
          conversation: '/c/community-strategy',
          about: '/c/community-strategy/about',
        },
      },
    }, {status: 201}),
  ),
];

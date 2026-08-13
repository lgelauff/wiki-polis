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
            links: {
              self: '/c/community-strategy',
              about: '/c/community-strategy/about',
              explore: '/app/conversations/community-strategy/explore',
              informedVoting: '/app/conversations/community-strategy/informed-voting',
              results: '/app/conversations/community-strategy/results',
              identityReveal: '/app/conversations/community-strategy/identity-reveal',
            },
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
    new URL('/api/v1/conversations/community-strategy/results', globalThis.location.origin).toString(),
    () => HttpResponse.json({
      data: {
        slug: 'community-strategy',
        title: 'Community strategy',
        publication: 'final',
        openedAt: '2026-05-01T12:00:00Z',
        closedAt: '2026-07-01T12:00:00Z',
        context: {
          phase: 'Publish',
          status: 'final',
          method: 'Informed-voting tallies frozen at publication.',
        },
        participation: {initialRound: 25, informedRound: 22, matchedRounds: null},
        dataAvailability: {detailedCounts: true, opinionGroups: true},
        moderation: {excludedStatements: 1, excludedParticipants: 0},
        statements: [{
          featuredStatementId: 31,
          statement: 'Regional communities should share infrastructure funding.',
          initial: {
            counts: {agree: 12, pass: 3, disagree: 5, voters: 20},
            percentages: {agree: 60, pass: 15, disagree: 25},
          },
          informed: {
            counts: {agree: 14, pass: 4, disagree: 2, voters: 20},
            percentages: {agree: 70, pass: 20, disagree: 10},
          },
          agreementShift: 10,
        }],
        opinionGroups: [{
          label: 'Group 1',
          memberCount: 11,
          positions: [{
            choice: 'agree',
            statement: 'Shared maintenance matters.',
            percentage: 82,
          }],
        }],
        links: {
          self: '/api/v1/conversations/community-strategy/results',
          conversation: '/c/community-strategy',
          about: '/app/conversations/community-strategy/about',
          identityReveal: '/app/conversations/community-strategy/identity-reveal',
        },
      },
    }),
  ),
  http.get(
    new URL('/api/v1/conversations/community-strategy/informed-voting', globalThis.location.origin).toString(),
    () => HttpResponse.json({
      data: {
        slug: 'community-strategy',
        title: 'Community strategy',
        pseudonym: 'quiet-otter',
        cards: [{
          featuredStatementId: 31,
          statement: 'Regional communities should share infrastructure funding.',
          voted: false,
          arguments: {
            for: [{id: 81, body: 'Shared funding reduces duplicated maintenance.', helpfulVotes: 7}],
            against: [{id: 82, body: 'Regional priorities may require independent budgets.', helpfulVotes: 4}],
          },
        }],
        progress: {completed: 0, total: 1, remaining: 1, allDone: false},
        capabilities: {vote: true},
        links: {
          self: '/api/v1/conversations/community-strategy/informed-voting',
          about: '/app/conversations/community-strategy/about',
          conversation: '/c/community-strategy',
          explore: '/app/conversations/community-strategy/explore',
          arguments: '/app/conversations/community-strategy/arguments',
        },
      },
    }),
  ),
  http.put(
    new URL('/api/v1/conversations/community-strategy/featured-statements/31/informed-vote', globalThis.location.origin).toString(),
    async ({request}) => {
      const body = await request.json() as {choice: 'agree' | 'pass' | 'disagree'};
      return HttpResponse.json({
        data: {
          featuredStatementId: 31,
          choice: body.choice,
          links: {informedVoting: '/api/v1/conversations/community-strategy/informed-voting'},
        },
      });
    },
  ),
  http.get(
    new URL('/api/v1/conversations/community-strategy/identity-reveal', globalThis.location.origin).toString(),
    () => HttpResponse.json({
      data: {
        slug: 'community-strategy',
        title: 'Community strategy',
        state: 'open',
        pseudonym: 'quiet-otter',
        wikimediaUsername: 'Example editor',
        publicUsername: null,
        timeline: {
          closedAt: '2026-06-01T12:00:00Z',
          opensAt: '2026-07-01T12:00:00Z',
          closesAt: '2026-07-31T12:00:00Z',
          nextBoundaryAt: '2026-07-31T12:00:00Z',
          daysRemaining: 12,
        },
        capabilities: {revealIdentity: true},
        links: {
          self: '/api/v1/conversations/community-strategy/identity-reveal',
          conversation: '/c/community-strategy',
          about: '/app/conversations/community-strategy/about',
        },
      },
    }),
  ),
  http.post(
    new URL('/api/v1/conversations/community-strategy/identity-reveal', globalThis.location.origin).toString(),
    () => HttpResponse.json({
      data: {
        slug: 'community-strategy',
        title: 'Community strategy',
        state: 'revealed',
        pseudonym: 'quiet-otter',
        wikimediaUsername: 'Example editor',
        publicUsername: 'Example editor',
        timeline: {
          closedAt: '2026-06-01T12:00:00Z',
          opensAt: '2026-07-01T12:00:00Z',
          closesAt: '2026-07-31T12:00:00Z',
          nextBoundaryAt: null,
          daysRemaining: 0,
        },
        capabilities: {revealIdentity: false},
        links: {
          self: '/api/v1/conversations/community-strategy/identity-reveal',
          conversation: '/c/community-strategy',
          about: '/app/conversations/community-strategy/about',
        },
      },
    }, {status: 201}),
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
  http.get(
    new URL('/api/v1/conversations/community-strategy/explore', globalThis.location.origin).toString(),
    () => HttpResponse.json({
      data: {
        slug: 'community-strategy',
        title: 'Community strategy',
        pseudonym: 'quiet-otter',
        currentStatement: {
          id: 12,
          text: 'Our movement should invest more in shared technical infrastructure.',
          isMeta: false,
          isSeed: true,
        },
        progress: {completed: 3, total: 12, remaining: 9, allDone: false},
        newStatement: {unlocked: true, unlockAfter: 0, quota: 3, used: 0, remaining: 3},
        capabilities: {vote: true, suggestWording: true, submitNewStatement: true},
        links: {
          self: '/api/v1/conversations/community-strategy/explore',
          about: '/c/community-strategy/about',
          conversation: '/c/community-strategy',
          arguments: '/app/conversations/community-strategy/arguments',
        },
      },
    }),
  ),
  http.put(
    new URL('/api/v1/conversations/community-strategy/statements/12/vote', globalThis.location.origin).toString(),
    async ({request}) => {
      const body = await request.json() as {
        choice: 'agree' | 'pass' | 'disagree';
        passReason?: 'unsure' | 'confusing';
      };
      return HttpResponse.json({
        data: {
          statementId: 12,
          choice: body.choice,
          passReason: body.passReason ?? null,
          links: {explore: '/api/v1/conversations/community-strategy/explore'},
        },
      });
    },
  ),
  http.post(
    new URL('/api/v1/conversations/community-strategy/statements', globalThis.location.origin).toString(),
    async ({request}) => {
      const body = await request.json() as {
        text: string;
        derivedFromStatementId?: number;
      };
      return HttpResponse.json({
        data: {
          statementId: 44,
          kind: body.derivedFromStatementId === undefined ? 'new' : 'derivative',
          derivedFromStatementId: body.derivedFromStatementId ?? null,
          newStatementQuotaRemaining: 2,
          links: {explore: '/api/v1/conversations/community-strategy/explore'},
        },
      }, {status: 201});
    },
  ),
  http.get(
    new URL('/api/v1/conversations/community-strategy/arguments', globalThis.location.origin).toString(),
    () => HttpResponse.json({
      data: {
        slug: 'community-strategy',
        title: 'Community strategy',
        pseudonym: 'quiet-otter',
        progress: {completed: 0, total: 1, allDone: false, currentFeaturedStatementId: 8},
        featuredStatements: [{
          id: 8,
          statement: {id: 12, text: 'Our movement should invest more in shared technical infrastructure.'},
          contributionsComplete: false,
          complete: false,
          sides: {
            pro: {
              contribution: {status: 'pending', argumentId: null, capabilities: {submit: true, skip: true}},
              prioritization: {available: false, requiredArgumentCount: 3, argumentCount: 3, selectionBudget: 2, selectedCount: 0, complete: false},
              arguments: [],
            },
            con: {
              contribution: {status: 'skipped', argumentId: null, capabilities: {submit: true, skip: false}},
              prioritization: {available: false, requiredArgumentCount: 3, argumentCount: 2, selectionBudget: 2, selectedCount: 0, complete: true},
              arguments: [],
            },
          },
          capabilities: {flagStatement: true},
        }],
        capabilities: {contribute: true, prioritize: true, flag: true},
        links: {
          self: '/api/v1/conversations/community-strategy/arguments',
          about: '/app/conversations/community-strategy/about',
          conversation: '/c/community-strategy',
          explore: '/app/conversations/community-strategy/explore',
        },
      },
    }),
  ),
  http.post(
    new URL('/api/v1/conversations/community-strategy/featured-statements/8/arguments', globalThis.location.origin).toString(),
    async ({request}) => {
      const body = await request.json() as {side: 'pro' | 'con'; body: string};
      return HttpResponse.json({
        data: {
          featuredStatementId: 8,
          side: body.side,
          status: 'submitted',
          argument: {id: 91, body: body.body, own: true, selected: false, capabilities: {prioritize: false, flag: false}},
          links: {arguments: '/api/v1/conversations/community-strategy/arguments'},
        },
      }, {status: 201});
    },
  ),
  http.put(
    new URL('/api/v1/conversations/community-strategy/featured-statements/8/contributions/:side/skip', globalThis.location.origin).toString(),
    ({params}) => HttpResponse.json({
      data: {
        featuredStatementId: 8,
        side: params.side,
        status: 'skipped',
        links: {arguments: '/api/v1/conversations/community-strategy/arguments'},
      },
    }),
  ),
  http.put(
    new URL('/api/v1/conversations/community-strategy/arguments/:argumentId/priority', globalThis.location.origin).toString(),
    async ({params, request}) => {
      const body = await request.json() as {selected: boolean};
      return HttpResponse.json({
        data: {
          argumentId: Number(params.argumentId), selected: body.selected,
          selectedCount: body.selected ? 2 : 1, selectionBudget: 2,
          links: {arguments: '/api/v1/conversations/community-strategy/arguments'},
        },
      });
    },
  ),
  http.post(
    new URL('/api/v1/conversations/community-strategy/flags', globalThis.location.origin).toString(),
    async ({request}) => {
      const body = await request.json() as {
        contentType: 'statement' | 'argument';
        targetId: number;
        category: 'personal_attack' | 'privacy' | 'off_topic' | 'other';
      };
      return HttpResponse.json({
        data: {
          ...body,
          status: 'open',
          created: true,
          links: {conversation: '/c/community-strategy'},
        },
      }, {status: 201});
    },
  ),
];

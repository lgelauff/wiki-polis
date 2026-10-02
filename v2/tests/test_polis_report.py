"""tools/polis_report: known answers on a tiny synthetic pair of polls, determinism, and no identifiers in the output."""

import csv
import json

from tools.polis_report import polis_report

A_TEXT = {'0': 'S zero', '1': 'S one', '2': 'S two', '3': 'S three', '4': 'I am staff.'}
B_IDS = {'S two': '0', 'S zero': '1', 'S one': '2', 'S three': '3', 'I am staff.': '4'}   # same texts, other ids

# opinion votes per participant on A's statements 0..3, then the role question
A_VOTES = {'1': [1, 1, -1, 1, 1], '2': [1, 1, -1, 0, 1], '3': [1, -1, -1, 1, -1],
           '4': [-1, 1, 1, 1, 1], '5': [1, 1, 0, -1, -1], '6': [1, 1, -1, 1, 1]}
B_VOTES = {'1': [1, 1, -1, 1, 1], '2': [1, 1, -1, 1, 1], '3': [-1, 1, 1, 1, 1],
           '4': [-1, 1, 0, -1, 1], '5': [1, 1, 1, 1, 1]}
A_XID = {'1': 'xid-one', '2': 'xid-two', '3': 'xid-three', '4': 'xid-four', '5': 'xid-five', '6': 'xid-six'}
B_XID = {'1': 'xid-two', '2': 'xid-three', '3': 'xid-four', '4': 'xid-five', '5': 'xid-nine'}
A_GROUP = {'0': '1', '1': '0', '2': '0', '6': '0', '3': '1', '4': '1', '5': '1'}
B_GROUP = {'0': '0', '1': '0', '2': '0', '3': '1', '4': '1', '5': '0'}
SINCE = 1000


def write_poll(d, text_by_id, votes, groups, xids, early=()):
    d.mkdir(parents=True)
    with open(d / 'comments.csv', 'w', newline='') as f:
        w = csv.writer(f); w.writerow(['timestamp', 'datetime', 'comment-id', 'author-id', 'agrees', 'disagrees', 'moderated', 'comment-body'])
        for cid, t in sorted(text_by_id.items()):
            w.writerow([1, '', cid, 0, 0, 0, 1, t])
    rows = []
    for cid in sorted(text_by_id):
        rows.append([500, '', cid, '0', 0])                         # moderator's automatic pass, before the window
    rows += [list(r) for r in early]
    t = 2000
    for p, vs in votes.items():
        for i, v in enumerate(vs):
            t += 1
            rows.append([t, '', str(i), p, v])
    with open(d / 'votes.csv', 'w', newline='') as f:
        w = csv.writer(f); w.writerow(['timestamp', 'datetime', 'comment-id', 'voter-id', 'vote']); w.writerows(rows)
    latest = {}
    for r in rows:
        latest[(r[3], r[2])] = r[4]
    with open(d / 'participant-votes.csv', 'w', newline='') as f:
        w = csv.writer(f); w.writerow(['participant', 'group-id', 'n-comments', 'n-votes', 'n-agree', 'n-disagree'] + sorted(text_by_id))
        for p in sorted({r[3] for r in rows}, key=int):
            w.writerow([p, groups.get(p, ''), 0, 0, 0, 0] + [latest.get((p, c), '') for c in sorted(text_by_id)])
    with open(d / 'xid.csv', 'w', newline='') as f:
        w = csv.writer(f); w.writerow(['participant', 'xid']); w.writerows(sorted(xids.items()))


def build(tmp_path):
    a_votes = dict(A_VOTES)
    write_poll(tmp_path / 'a', A_TEXT, a_votes, A_GROUP, A_XID, early=[(900, '', '0', '7', 1)])   # participant 7 voted only before the window
    # Poll A: participant 2 re-votes on statement 3 (pass, then agree... then pass again: latest is pass)
    with open(tmp_path / 'a' / 'votes.csv', 'a', newline='') as f:
        csv.writer(f).writerows([[3000, '', '3', '2', 1], [3001, '', '3', '2', 0]])
    b_text = {bid: t for t, bid in B_IDS.items()}
    # B votes are given per A statement; write them under B's own ids
    b_votes = {p: [vs[int(next(a for a, t in A_TEXT.items() if t == b_text[str(i)]))] for i in range(5)] for p, vs in B_VOTES.items()}
    write_poll(tmp_path / 'b', b_text, b_votes, B_GROUP, B_XID)
    cfg = {'title': 'Test', 'banner': 'TEST', 'out': 'out', 'since': '1970-01-01T00:16:40Z', 'meta': ['I am staff.'],
           'polls': [{'key': 'a', 'name': 'Poll A', 'dir': 'a', 'report': 'ra', 'url': 'u/a', 'xid': 'a/xid.csv', 'exclude_participants': ['0']},
                     {'key': 'b', 'name': 'Poll B', 'dir': 'b', 'report': 'rb', 'url': 'u/b', 'xid': 'b/xid.csv', 'exclude_participants': ['0']}]}
    (tmp_path / 'config.json').write_text(json.dumps(cfg))
    return polis_report.run(tmp_path / 'config.json', pdf=False)


def rows(path):
    return list(csv.DictReader(open(path, newline='')))


def test_counts_window_exclusion_and_renumbering(tmp_path):
    out = build(tmp_path)
    a = {r['statement']: r for r in rows(out / 'poll-a-statements.csv')}
    # statement 0: agree from 1,2,3,5,6; disagree from 4; not the moderator, not participant 7 (before the window)
    assert (a['0']['All_agree'], a['0']['All_disagree'], a['0']['All_pass']) == ('5', '1', '0')
    # participant 2's latest vote on statement 3 is pass
    assert (a['3']['All_agree'], a['3']['All_disagree'], a['3']['All_pass']) == ('4', '1', '1')
    assert a['4']['label'] == 'role' and a['2']['label'] == '≥70% disagree'
    # Poll B is reported with Poll A's numbers: 'S zero' is B's own id 1 but appears as #0
    b = {r['statement']: r for r in rows(out / 'poll-b-statements.csv')}
    assert b['0']['text'] == 'S zero'
    assert (b['0']['All_agree'], b['0']['All_disagree']) == ('3', '2')


def test_matched_transitions_show_both_directions(tmp_path):
    out = build(tmp_path)
    t = {(r['statement'], r['A_vote'], r['B_vote']): int(r['n']) for r in rows(out / 'transitions_by_statement.csv')}
    assert sum(n for (s, _, _), n in t.items() if s == '0') == 4                 # xid-two..xid-five only
    assert t[('0', 'agree', 'disagree')] == 1 and t[('0', 'agree', 'agree')] == 2 and t[('0', 'disagree', 'disagree')] == 1
    assert t[('1', 'disagree', 'agree')] == 1
    assert t[('3', 'pass', 'agree')] == 1
    pooled = {r['A_vote']: r for r in rows(out / 'transitions_pooled.csv')}
    assert pooled['agree']['B_disagree'] == '1' and pooled['disagree']['B_agree'] == '1'
    m = {r['statement']: r for r in rows(out / 'movers.csv')}
    assert (m['0']['toward_agree'], m['0']['toward_disagree']) == ('0', '1')
    comp = {r['statement']: r for r in rows(out / 'composition.csv')}
    assert (comp['0']['A_only_agree'], comp['0']['A_only_n']) == ('2', '2')      # xid-one and xid-six
    assert (comp['0']['B_only_agree'], comp['0']['B_only_n']) == ('1', '1')      # xid-nine


def test_output_is_deterministic_and_has_no_identifiers(tmp_path):
    out = build(tmp_path)
    first = {p.name: p.read_bytes() for p in sorted(out.iterdir())}
    polis_report.run(tmp_path / 'config.json', pdf=False)
    second = {p.name: p.read_bytes() for p in sorted(out.iterdir())}
    assert first == second
    assert {'poll-a-report.html', 'poll-b-report.html', 'poll-ab-compared.html', 'poll-ab-transitions.html'} <= set(first)
    for name, data in first.items():
        assert b'xid-' not in data, name


def test_comparison_skipped_without_xid_files(tmp_path):
    build(tmp_path)
    cfg = json.loads((tmp_path / 'config.json').read_text())
    for p in cfg['polls']:
        p.pop('xid')
    cfg['out'] = 'out2'
    (tmp_path / 'config.json').write_text(json.dumps(cfg))
    out = polis_report.run(tmp_path / 'config.json', pdf=False)
    assert (out / 'poll-a-report.html').exists() and not (out / 'poll-ab-transitions.html').exists()


def test_small_groups_are_merged_and_never_crossed_with_roles(tmp_path):
    out = build(tmp_path)
    page = (out / 'poll-a-report.html').read_text(encoding='utf-8')
    # both synthetic groups have 3 members: merged into Other, so the group-difference measure is not computed
    assert 'Not computed: fewer than two Polis groups have at least 5 members' in page
    a = {r['statement']: r for r in rows(out / 'poll-a-statements.csv')}
    assert a['4']['Other_agree'] == ''                       # role answers are not shown for Other
    assert a['0']['Other_agree'] == '5'                      # opinion counts of 3+ are shown as they are
    assert a['2']['Other_agree'] == '<3'        # counts of 1-2 are suppressed
    assert 'self-selected' in page.lower()


def test_power_and_baseline_lines(tmp_path):
    out = build(tmp_path)
    page = (out / 'poll-ab-transitions.html').read_text(encoding='utf-8')
    m = {r['statement']: r for r in rows(out / 'movers.csv')}
    assert m['0']['movers'] == '1' and m['0']['smallest_reachable_p'] == '1.0000'
    assert 'could not reach p &lt; 0.05 even without correction' in page
    assert 'answered role question #4 differently' in page

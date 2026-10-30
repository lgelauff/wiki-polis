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
CREATED = 1500   # statements are created inside the window, so only the automatic-vote rule removes the author's passes


def write_poll(d, text_by_id, votes, groups, xids, early=()):
    d.mkdir(parents=True)
    with open(d / 'comments.csv', 'w', newline='') as f:
        w = csv.writer(f); w.writerow(['timestamp', 'datetime', 'comment-id', 'author-id', 'agrees', 'disagrees', 'moderated', 'comment-body'])
        for cid, t in sorted(text_by_id.items()):
            w.writerow([CREATED, '', cid, 0, 0, 0, 1, t])
    rows = []
    for cid in sorted(text_by_id):
        rows.append([CREATED, '', cid, '0', 0])                     # the author's automatic pass, inside the window
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


def build(tmp_path, **settings):
    """Known answers need exact counts, so the small-count rule is off unless a test sets it."""
    a_votes = dict(A_VOTES)
    write_poll(tmp_path / 'a', A_TEXT, a_votes, A_GROUP, A_XID, early=[(900, '', '0', '7', 1)])   # participant 7 voted only before the window
    # Poll A: participant 2 re-votes on statement 3 (pass, then agree... then pass again: latest is pass)
    with open(tmp_path / 'a' / 'votes.csv', 'a', newline='') as f:
        csv.writer(f).writerows([[3000, '', '3', '2', 1], [3001, '', '3', '2', 0],
                                 [3100, '', '1', '0', 1]])   # the author also votes as a participant: this vote counts
    b_text = {bid: t for t, bid in B_IDS.items()}
    # B votes are given per A statement; write them under B's own ids
    b_votes = {p: [vs[int(next(a for a, t in A_TEXT.items() if t == b_text[str(i)]))] for i in range(5)] for p, vs in B_VOTES.items()}
    write_poll(tmp_path / 'b', b_text, b_votes, B_GROUP, B_XID)
    cfg = {'title': 'Test', 'banner': 'TEST', 'out': 'out', 'since': '1970-01-01T00:16:40Z', 'meta': ['I am staff.'],
           'min_participants_for_groups': 3, 'min_cell': 1, 'min_total': 1, **settings,
           'polls': [{'key': 'a', 'name': 'Poll A', 'dir': 'a', 'report': 'ra', 'url': 'u/a', 'xid': 'a/xid.csv'},
                     {'key': 'b', 'name': 'Poll B', 'dir': 'b', 'report': 'rb', 'url': 'u/b', 'xid': 'b/xid.csv'}]}
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
    # automatic votes are not counted, but the author's own later vote is: statement 1 has 5 agrees from 1..6 plus the author's
    assert (a['1']['All_agree'], a['1']['All_disagree'], a['1']['All_pass']) == ('6', '1', '0')
    page = (out / 'poll-a-report.html').read_text(encoding='utf-8')
    assert '5 automatic votes not counted' in page
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


def test_small_counts_are_hidden_and_cannot_be_worked_out_from_the_total():
    cells = polis_report.cells
    assert cells((2, 10, 5), 3)[0] == ['<3', '10', '≥3']     # one hidden: the next-smallest is hidden too
    assert cells((1, 2, 15), 3)[0] == ['<3', '<3', '15']     # two hidden: nothing to add
    assert cells((2, 0, 9), 3)[0] == ['<3', '0', '≥3']
    assert cells((0, 4, 7), 3) == (['0', '4', '7'], [True, True, True])
    assert cells((2, 10, 5), 1)[0] == ['2', '10', '5']       # min_cell 1: the rule is off


def test_default_rule_hides_small_counts_and_small_columns(tmp_path):
    out = build(tmp_path, min_cell=3, min_total=10)
    a = {r['statement']: r for r in rows(out / 'poll-a-statements.csv')}
    # statement 0 is 5 agree, 1 disagree, 0 pass: the 1 is hidden, so the 5 is too
    assert (a['0']['All_agree'], a['0']['All_disagree'], a['0']['All_pass']) == ('≥3', '<3', '0')
    for r in a.values():
        assert not {r['All_agree'], r['All_disagree'], r['All_pass']} & {'1', '2'}
    # both Polis groups have 3 members and "Other" has 6: no column under 10 is shown
    assert 'Other_agree' not in open(out / 'poll-a-statements.csv').readline()
    page = (out / 'poll-a-report.html').read_text(encoding='utf-8')
    row = page[page.index('data-tip="#0:'):]
    row = row[:row.index('class="nums"')]
    assert 'width:0.0%' in row and 'width:16.7%' not in row and 'width:83.3%' not in row   # hidden counts are not drawn
    assert 'Not shown: fewer than 10 people.' in page
    assert 'self-selected' in page.lower()
    # the one-poll-only columns (2 and 1 people) and the matched 4 are under 10
    comp = {r['statement']: r for r in rows(out / 'composition.csv')}
    assert (comp['0']['A_only_agree'], comp['0']['A_only_n'], comp['0']['A_matched_agree']) == ('', '', '')
    compared = (out / 'poll-ab-compared.html').read_text(encoding='utf-8')
    assert 'fewer than 10: most counts are small' in compared
    # per-person transitions and movers stay exact: they are the point of the pair
    t = {(r['statement'], r['A_vote'], r['B_vote']): int(r['n']) for r in rows(out / 'transitions_by_statement.csv')}
    assert t[('0', 'agree', 'disagree')] == 1


def test_power_and_baseline_lines(tmp_path):
    out = build(tmp_path)
    page = (out / 'poll-ab-transitions.html').read_text(encoding='utf-8')
    m = {r['statement']: r for r in rows(out / 'movers.csv')}
    assert m['0']['movers'] == '1' and m['0']['smallest_reachable_p'] == '1.0000'
    assert 'could not reach p &lt; 0.05 even without correction' in page
    assert 'answered role question #4 differently' in page


def test_groups_need_the_minimum_number_of_participants(tmp_path):
    build(tmp_path)
    cfg = json.loads((tmp_path / 'config.json').read_text())
    cfg['min_participants_for_groups'] = 25
    cfg['out'] = 'out3'
    (tmp_path / 'config.json').write_text(json.dumps(cfg))
    out = polis_report.run(tmp_path / 'config.json', pdf=False)
    page = (out / 'poll-a-report.html').read_text(encoding='utf-8')
    assert 'fewer than the 25 needed before opinion groups are shown' in page
    assert 'Other_agree' not in open(out / 'poll-a-statements.csv').readline()


def test_shift_readings_are_rule_based(tmp_path):
    out = build(tmp_path)
    m = {r['statement']: r for r in rows(out / 'movers.csv')}
    assert m['0']['reading'].startswith('Too few people changed their response to tell')
    assert m['2']['reading'] == 'No observed movement.' or m['2']['reading'].startswith('Too few')


def test_comparison_tiles_divide_each_poll_by_its_own_responses(tmp_path):
    """The headline tiles: B's shares are out of B's responses, not A's."""
    build(tmp_path)
    # Matched participant xid-two gives no response to 'S zero' in Poll B (B's own id 1), so
    # among the matched four, A has 16 opinion responses and B has 15.
    votes = tmp_path / 'b' / 'votes.csv'
    kept = [r for r in csv.reader(open(votes, newline='')) if not (r[2] == '1' and r[3] == '1')]
    with open(votes, 'w', newline='') as f:
        csv.writer(f).writerows(kept)
    out = polis_report.run(tmp_path / 'config.json', pdf=False)
    page = (out / 'poll-ab-compared.html').read_text(encoding='utf-8')
    # agree: 9 of 16 in A, 9 of 15 in B; pass: 2 of 16 in A, 1 of 15 in B
    assert '<b>56% → 60%</b><span>of opinion votes agree' in page
    assert '<b>12% → 7%</b><span>of opinion votes pass' in page

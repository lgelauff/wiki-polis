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
           # min_total 1 keeps every label and bar in these small fixtures; a setting passed as None is left out (the default)
           **{k: v for k, v in {'min_participants_for_groups': 3, 'min_total': 1, **settings}.items() if v is not None},
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
    assert '5 responses excluded (5 pass · 0 agree · 0 disagree)' in page   # automatic responses, split by value
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
    out = build(tmp_path, min_total=5)
    page = (out / 'poll-a-report.html').read_text(encoding='utf-8')
    # the synthetic groups have 3 and 4 members: merged into Other, so the group-difference measure is not computed
    assert 'Not computed: fewer than two Polis groups have at least 5 members' in page
    a = {r['statement']: r for r in rows(out / 'poll-a-statements.csv')}
    assert a['4']['Other_agree'] == ''                       # role answers are not shown for Other
    assert a['0']['Other_agree'] == '5'
    assert a['2']['Other_agree'] in {'1', '2'}               # small counts are exact
    assert 'self-selected' in page.lower()


def test_label_sensitivity_counts_the_responses_that_would_change_it():
    t = polis_report.to_change
    assert t((7, 3, 0), 0.7) == '1 response changing from agree to disagree would change this label'      # 70% exactly
    assert t((10, 0, 4), 0.7) == '4 responses changing from agree to disagree would change this label'    # 6 of 10 is below 70%
    assert t((3, 7, 0), 0.7) == '1 response changing from disagree to agree would change this label'
    assert t((6, 4, 0), 0.7) == '1 response changing from disagree to agree would change this label'      # neither: 7 of 10 reaches it
    assert polis_report.label((6, 3, 0), 0.7, 10) == 'few' and polis_report.label((7, 3, 0), 0.7, 10) == 'agree'


def test_default_rule_shows_every_count_and_leaves_out_what_is_too_small_to_carry(tmp_path):
    out = build(tmp_path, min_total=None)   # the default, 10: no statement in these fixtures has 10 responses
    files = [f for f in out.iterdir() if f.suffix in {'.html', '.csv'}]
    assert files and not any('&lt;' + str(n) in f.read_text(encoding='utf-8') or '≥' + str(n) in f.read_text(encoding='utf-8')
                             for f in files for n in (3, 5))      # nothing is masked
    a = {r['statement']: r for r in rows(out / 'poll-a-statements.csv')}
    assert (a['0']['All_agree'], a['0']['All_disagree'], a['0']['All_pass']) == ('5', '1', '0')   # exact
    assert {r['label'] for r in a.values() if r['label'] != 'role'} == {'too few responses for a label'}
    assert all(r['label_sensitivity'] == '' for r in a.values())
    page = (out / 'poll-a-report.html').read_text(encoding='utf-8')
    assert 'Too few responses for a label (fewer than 10 agree + disagree)' in page
    assert 'fewer than 10 responses' in page and 'class="seg agr" style' not in page    # no bars, counts only
    assert 'Other_agree' in open(out / 'poll-a-statements.csv').readline()               # groups of 3 merged into Other, shown
    assert polis_report.share_of(3, 9, 10) == '3 of 9' and polis_report.share_of(3, 10, 10) == '30%'   # a share needs 10 responses
    t = {(r['statement'], r['A_vote'], r['B_vote']): r['n'] for r in rows(out / 'transitions_by_statement.csv')}
    assert '1' in t.values()                                                              # transitions stay exact


def test_observed_values_only_by_default(tmp_path):
    out = build(tmp_path)
    m = {r['statement']: r for r in rows(out / 'movers.csv')}
    assert m['0']['movers'] == '1' and m['0']['test'] == '' and 'sign_test_p' not in m['0']
    for f in out.iterdir():
        if f.suffix in {'.html', '.csv'}:
            text = f.read_text(encoding='utf-8')
            assert not any(w in text for w in ('p = ', 'p &lt;', 'Holm', 'reachable', 'unlikely to be chance')), f.name
    for name in ('poll-a-report.html', 'poll-ab-compared.html', 'poll-ab-transitions.html'):   # every report says so (§2)
        assert 'applies no test' in (out / name).read_text(encoding='utf-8'), name
    page = (out / 'poll-ab-transitions.html').read_text(encoding='utf-8')
    assert 'answered role question' not in page and 'toward the middle' in page   # no role baseline; the middle count stays


def test_a_significance_slot_runs_only_when_switched_on(tmp_path, monkeypatch):
    assert all(v is None for v in polis_report.SLOTS.values())   # every slot ships empty
    stub = lambda family: {c: f'stub on {u}/{d} of {len(family)}' for c, (u, d) in family.items()}   # not a real test
    monkeypatch.setitem(polis_report.SLOTS, 'shift', stub)
    off = build(tmp_path)                                     # a function in the slot, but the setting is off
    assert all(r['test'] == '' for r in rows(off / 'movers.csv'))
    on = build(tmp_path / 'on', significance=True)
    m = {r['statement']: r for r in rows(on / 'movers.csv')}
    assert m['0']['test'].startswith('stub on ') and m['0']['test'].endswith(' of 4')   # the whole family at once
    assert m['0']['reading'].endswith(f"({m['0']['test']})")
    monkeypatch.setitem(polis_report.SLOTS, 'shift', None)    # switched on, but no test in the slot: nothing shown
    empty = build(tmp_path / 'empty', significance=True)
    assert all(r['test'] == '' for r in rows(empty / 'movers.csv'))


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
    assert m['0']['reading'] in {'More moved toward agree (1) than the other way (0).', 'More moved toward disagree (1) than the other way (0).'}
    assert all(r['reading'] == 'No observed movement.' for r in m.values() if r['movers'] == '0')


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


def test_role_answers_split_nothing(tmp_path):
    out = build(tmp_path, min_total=5)
    page = (out / 'poll-a-report.html').read_text(encoding='utf-8')
    assert 'by answer to #4' not in page and 'not used to split other results' in page
    a = {r['statement']: r for r in rows(out / 'poll-a-statements.csv')}
    assert a['4']['All_agree'] != '' and a['4']['Other_agree'] == ''    # a role row has its own count only
    t = {r['statement'] for r in rows(out / 'transitions_by_statement.csv')}
    assert '4' not in t                                                   # role answers are not compared between polls


def test_each_exclusion_has_its_rule_reason_and_count(tmp_path):
    build(tmp_path)
    cfg = json.loads((tmp_path / 'config.json').read_text())
    cfg['since_reason'] = 'test responses before the session opened'
    cfg['polls'][0].update(exclude_participants=['6'], exclude_reason='asked to be left out')
    cfg['out'] = 'out2'
    (tmp_path / 'config.json').write_text(json.dumps(cfg))
    page = (polis_report.run(tmp_path / 'config.json', pdf=False) / 'poll-a-report.html').read_text(encoding='utf-8')
    excluded = page[page.index('<h2>Excluded responses</h2>'):page.index('<h2>Method and caveats</h2>')]
    assert 'reason: test responses before the session opened): 1 response excluded; 1 participant responded only before it' in excluded
    assert 'reason: asked to be left out): 5 responses from 1 participant excluded' in excluded
    assert excluded.count('<li>') == 3

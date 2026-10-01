"""tools/polis_stats: the export reader's cross-checks, the statistics against known answers, and the CLI."""

import csv
import json
import zipfile

import pytest

from tools.polis_stats import synth
from tools.polis_stats.__main__ import main
from tools.polis_stats.export import ExportError, read_export
from tools.polis_stats.stats import Thresholds, compute, wilson


@pytest.fixture
def export_dir(tmp_path):
    data = synth.write(tmp_path / 'export')
    return tmp_path / 'export', data


def test_counts_match_the_known_answers_and_the_latest_vote_wins(export_dir):
    path, data = export_dir
    export = read_export(path)
    report = compute(export)
    for s in report.statements:
        assert (s.agree, s.disagree, s.passes) == tuple(data['truth'][s.id][k] for k in ('agree', 'disagree', 'pass')), s.id
    assert len(export.votes_all) - len(export.votes) == data['revotes']
    assert [i.code for i in export.issues] == ['revotes']          # history is a note, not an error


def test_labels_follow_the_thresholds(export_dir):
    path, data = export_dir
    t = Thresholds(min_votes=10, majority_share=0.7, split_min_share=0.35, max_pass_share=0.5)
    report = compute(read_export(path), t)
    expected = {'agree': [], 'disagree': [], 'split': [], 'pass': [], 'few': []}
    for sid, c in sorted(data['truth'].items()):
        if sid == 4 or sid in synth.META:              # rejected, and meta: counted, never labelled
            continue
        decided, votes = c['agree'] + c['disagree'], c['agree'] + c['disagree'] + c['pass']
        if decided < t.min_votes:
            expected['few'].append(sid)
        elif c['pass'] / votes > t.max_pass_share:
            expected['pass'].append(sid)
        elif c['agree'] / decided >= t.majority_share:
            expected['agree'].append(sid)
        elif c['disagree'] / decided >= t.majority_share:
            expected['disagree'].append(sid)
        elif min(c['agree'], c['disagree']) / decided >= t.split_min_share:
            expected['split'].append(sid)
    assert (report.majority_agree, report.majority_disagree, report.split, report.mostly_pass,
            report.too_few_votes) == (expected['agree'], expected['disagree'], expected['split'],
                                      expected['pass'], expected['few'])
    assert 0 in report.majority_agree and 1 in report.majority_disagree
    assert 2 in report.split and report.too_few_votes == [3]
    assert report.label(4) == ''


def test_a_statement_most_people_passed_on_is_not_a_majority(export_dir):
    path, _ = export_dir
    export = read_export(path)
    for (voter, sid), vote in export.votes.items():
        if sid == 0 and voter % 10 < 6:                # 6 in 10 now pass on "Everyone agrees"
            vote.value = 0
    report = compute(export)
    assert report.label(0) == 'mostly-pass' and 0 not in report.majority_agree


def test_a_raw_sign_export_is_caught_when_read_as_a_polis_export(tmp_path):
    synth.write(tmp_path / 'raw', raw_sign=True)
    codes = {i.code for i in read_export(tmp_path / 'raw').issues}
    assert 'vote-sign-inverted' in codes
    clean = read_export(tmp_path / 'raw', vote_sign='raw')
    assert {i.code for i in clean.issues} == {'revotes'}


def test_a_matrix_cell_that_disagrees_with_votes_csv_is_an_error(export_dir):
    path, _ = export_dir
    rows = list(csv.reader(open(path / 'participants-votes.csv')))
    rows[1][6] = '-1' if rows[1][6] != '-1' else '1'                 # participant 0, statement 0
    with open(path / 'participants-votes.csv', 'w', newline='') as fh:
        csv.writer(fh).writerows(rows)
    assert any(i.code == 'matrix-mismatch' and i.count == 1 for i in read_export(path).issues)


def test_comment_counts_that_do_not_match_the_vote_rows_are_an_error(export_dir):
    path, _ = export_dir
    rows = list(csv.reader(open(path / 'comments.csv')))
    rows[1][3] = str(int(rows[1][3]) + 1)
    with open(path / 'comments.csv', 'w', newline='') as fh:
        csv.writer(fh).writerows(rows)
    assert any(i.code == 'reported-counts-mismatch' for i in read_export(path).issues)


def test_votes_for_unknown_statements_are_counted_not_silently_dropped(export_dir):
    path, _ = export_dir
    with open(path / 'votes.csv', 'a', newline='') as fh:
        csv.writer(fh).writerow([1_799_000_000_000, '', 99, 1, 1])
    issue = next(i for i in read_export(path).issues if i.code == 'vote-for-unknown-statement')
    assert issue.count == 1 and issue.level == 'error'


def test_a_zip_with_a_subfolder_and_prefixed_names_reads_the_same(export_dir, tmp_path):
    path, data = export_dir
    archive = tmp_path / 'export.zip'
    with zipfile.ZipFile(archive, 'w') as z:
        for f in path.iterdir():
            z.write(f, f'2026-polis-abc123/abc123-{f.name}')
    report = compute(read_export(archive))
    assert {s.id: s.agree for s in report.statements} == {k: v['agree'] for k, v in data['truth'].items()}


def test_a_missing_file_or_column_cannot_be_read(export_dir):
    path, _ = export_dir
    rows = [r[:2] for r in csv.reader(open(path / 'votes.csv'))]
    with open(path / 'votes.csv', 'w', newline='') as fh:
        csv.writer(fh).writerows(rows)
    with pytest.raises(ExportError, match='votes.csv lacks column'):
        read_export(path)
    (path / 'votes.csv').unlink()
    with pytest.raises(ExportError, match='lacks votes.csv'):
        read_export(path)


def test_wilson_interval_brackets_the_share():
    low, high = wilson(7, 10)
    assert low < 0.7 < high and 0 <= low and high <= 1
    assert wilson(0, 0) is None


def test_cli_writes_the_report_and_refuses_on_errors(export_dir, tmp_path, capsys):
    path, _ = export_dir
    out = tmp_path / 'out'
    assert main([str(path), '-o', str(out)]) == 0
    for name in ('report.html', 'stats.json', 'statements.csv', 'issues.csv',
                 'charts/statements.svg', 'charts/votes-per-participant.svg', 'charts/votes-per-day.svg'):
        assert (out / name).exists(), name
    stats = json.loads((out / 'stats.json').read_text())
    assert stats['summary']['participants_voting'] == 60 and 0 in stats['labels']['majority_agree']
    assert main([str(path), '-o', str(tmp_path / 'forced'), '--allow-errors']) == 0
    assert (tmp_path / 'forced' / 'stats.json').exists()
    synth.write(tmp_path / 'raw', raw_sign=True)
    assert main([str(tmp_path / 'raw'), '-o', str(tmp_path / 'raw-out')]) == 1
    assert not (tmp_path / 'raw-out' / 'report.html').exists()
    assert main(['/nonexistent/export']) == 2


def test_statements_csv_lists_every_statement_with_its_label(export_dir, tmp_path):
    path, data = export_dir
    out = tmp_path / 'out'
    assert main([str(path), '-o', str(out)]) == 0
    rows = {int(r['statement']): r for r in csv.DictReader(open(out / 'statements.csv'))}
    assert sorted(rows) == sorted(data['truth'])                                  # rejected #4 included
    for sid, c in data['truth'].items():
        assert (int(rows[sid]['agree']), int(rows[sid]['disagree']), int(rows[sid]['pass'])) == \
            (c['agree'], c['disagree'], c['pass'])
    assert rows[3]['label'] == 'too-few-votes' and rows[4]['label'] == ''


def test_malformed_numbers_are_counted_not_a_crash(export_dir):
    path, _ = export_dir
    with open(path / 'votes.csv', 'a', newline='') as fh:
        w = csv.writer(fh)
        w.writerow([1_799_000_000_000, '', 0, 1, '1e400'])
        w.writerow([1_799_000_000_001, '', 0, 1, '0.5'])
        w.writerow(['1e400', '', 0, 2, 1])                                   # absurd time: no crash
    issues = {i.code: i for i in read_export(path).issues}
    assert issues['bad-vote-row'].count == 2


def test_a_very_long_statement_is_read(export_dir):
    path, _ = export_dir
    rows = list(csv.reader(open(path / 'comments.csv')))
    rows[1][-1] = 'x' * 300_000
    with open(path / 'comments.csv', 'w', newline='') as fh:
        csv.writer(fh).writerows(rows)
    assert len(read_export(path).statements[0].text) == 300_000


def test_a_zip_entry_too_large_to_unpack_is_refused(export_dir, tmp_path, monkeypatch):
    from tools.polis_stats import export as export_module
    path, _ = export_dir
    archive = tmp_path / 'big.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
        for f in path.iterdir():
            z.write(f, f.name)
    monkeypatch.setattr(export_module, 'MAX_FILE_BYTES', 100)
    with pytest.raises(ExportError, match='unpacks to more than'):
        read_export(archive)


def test_a_participant_missing_from_the_matrix_is_an_error(export_dir):
    path, _ = export_dir
    rows = [r for r in csv.reader(open(path / 'participants-votes.csv')) if r[0] != '7']
    with open(path / 'participants-votes.csv', 'w', newline='') as fh:
        csv.writer(fh).writerows(rows)
    issue = next(i for i in read_export(path).issues if i.code == 'matrix-missing-participant')
    assert issue.count == 1 and issue.level == 'error'


def test_spreadsheet_formulas_in_statement_text_are_neutralised(export_dir, tmp_path):
    path, _ = export_dir
    rows = list(csv.reader(open(path / 'comments.csv')))
    rows[1][-1] = '=HYPERLINK("http://example.invalid","x")'
    with open(path / 'comments.csv', 'w', newline='') as fh:
        csv.writer(fh).writerows(rows)
    out = tmp_path / 'out'
    assert main([str(path), '-o', str(out)]) == 0
    text = next(r['text'] for r in csv.DictReader(open(out / 'statements.csv')) if r['statement'] == '0')
    assert text.startswith("'=")


def test_meta_statements_get_no_opinion_label(export_dir):
    path, _ = export_dir
    export = read_export(path)
    export.statements[1].is_meta = True
    report = compute(export)
    assert report.label(1) == 'meta' and 1 not in report.majority_disagree
    assert 1 not in [s.id for s in report.opinions()]


def test_the_report_table_lists_every_statement(export_dir, tmp_path):
    path, data = export_dir
    out = tmp_path / 'out'
    assert main([str(path), '-o', str(out)]) == 0
    html = (out / 'report.html').read_text()
    table = html[html.index('<h2>All statements</h2>'):]
    assert all(f'<td class="n">{sid}</td>' in table for sid in data['truth'])     # rejected #4 included
    assert 'too-few-votes' in table and 'consensus' not in table


def test_the_statement_chart_leaves_out_rejected_and_puts_thin_statements_last(export_dir):
    from tools.polis_stats.charts import statement_bars
    path, _ = export_dir
    report = compute(read_export(path))
    svg = statement_bars(report.opinions(), min_votes=report.thresholds.min_votes)
    assert '>#4<' not in svg
    assert svg.index('>#3<') > max(svg.index(f'>#{i}<') for i in (0, 1, 2, 5))
    assert 'few votes' in svg



def test_the_tallest_histogram_bar_is_labelled():
    from tools.polis_stats.charts import votes_per_participant
    svg = votes_per_participant([5] * 40 + [1, 2, 9, 12, 20, 25, 30])      # most participants cast 5 votes
    ticks = [t.split('<')[0] for t in svg.split('text-anchor="middle">')[1:]]
    assert '5' in ticks


def test_groups_come_from_the_participant_matrix(export_dir):
    path, _ = export_dir
    report = compute(read_export(path))
    assert sorted(report.groups) == ['0', '1', '2']
    assert sum(g['members'] for g in report.groups.values()) == 60
    g0, g1 = report.groups['0']['statements'][2], report.groups['1']['statements'][2]
    assert g0['agree'] > g0['disagree'] and g1['disagree'] > g1['agree']


def test_our_projection_separates_the_groups_that_vote_apart(export_dir):
    from tools.polis_stats.groups import project
    path, _ = export_dir
    export = read_export(path)
    points = project(export)
    assert len(points) == 60
    centroid = {}
    for g in (0, 1):
        xs = [points[p] for p in points if export.groups[p] == g]
        centroid[g] = (sum(x for x, _ in xs) / len(xs), sum(y for _, y in xs) / len(xs))
    within = max(abs(points[p][0] - centroid[export.groups[p]][0]) for p in points if export.groups[p] in (0, 1))
    assert abs(centroid[0][0] - centroid[1][0]) > 0.5 * within      # groups 0 and 1 split on statement 2


def test_heatmap_lists_the_most_dividing_statement_first(export_dir):
    from tools.polis_stats.groups import heatmap, spread
    path, _ = export_dir
    report = compute(read_export(path))
    spreads = {s.id: spread(report.groups, s.id, 5) for s in report.opinions()}
    assert max(spreads, key=lambda k: spreads[k] or -1) == 2
    svg = heatmap(report.statements, report.groups)
    assert svg.index('>#2<') < svg.index('>#0<') and '>#4<' not in svg   # rejected statement left out
    assert '>#6<' not in svg                                              # meta statement left out


def test_a_groups_file_replaces_polis_clusters(export_dir, tmp_path):
    path, _ = export_dir
    groups = tmp_path / 'g.csv'
    groups.write_text('participant,group\n' + ''.join(f'{p},{p % 2}\n' for p in range(60)) + '999,1\n')
    out = tmp_path / 'out'
    assert main([str(path), '-o', str(out), '--groups', str(groups)]) == 0
    stats = json.loads((out / 'stats.json').read_text())
    assert stats['summary']['groups'] == 2
    codes = {i['code'] for i in stats['issues']}
    assert {'groups-from-file', 'groups-unknown-participants'} <= codes
    html = (out / 'report.html').read_text()
    assert 'groups from' in html and (out / 'charts' / 'participant-map.svg').exists()


def test_groups_beyond_the_palette_share_the_neutral_style_instead_of_cycling():
    from tools.polis_stats.groups import MAX_GROUPS, _cls
    assert _cls(MAX_GROUPS - 1) != _cls(0)
    assert _cls(MAX_GROUPS) == 'gx' and _cls(MAX_GROUPS + 3) == 'gx'


def test_the_full_table_lists_every_statement_with_its_group_numbers(export_dir, tmp_path):
    path, data = export_dir
    out = tmp_path / 'out'
    assert main([str(path), '-o', str(out)]) == 0
    rows = list(csv.DictReader(open(out / 'statements.csv')))
    assert [int(r['statement']) for r in rows] == sorted(data['truth'])            # rejected #4 included
    assert {'group_0_agree', 'group_2_agree_of_decided', 'group_spread'} <= set(rows[0])
    report = compute(read_export(path))
    for r in rows:
        sid = int(r['statement'])
        for g, d in report.groups.items():
            c = d['statements'].get(sid, {'agree': 0})
            assert int(r[f'group_{g}_agree']) == c['agree']
    html = (out / 'report.html').read_text()
    table = html[html.index('<h2>All statements</h2>'):]
    assert all(f'<td class="n">{sid}</td>' in table for sid in data['truth'])
    assert table.count('<th>Group ') - table.count('<th>Group spread') == 3 and 'Group spread' in table


def test_meta_statements_are_demographics_not_opinions(export_dir):
    path, data = export_dir
    report = compute(read_export(path))
    labelled = report.majority_agree + report.majority_disagree + report.split + report.mostly_pass + report.too_few_votes
    assert 6 not in labelled and 6 not in [s.id for s in report.opinions()]
    opinion = [data['truth'][sid] for sid in data['truth'] if sid not in (4, 6)]
    assert report.summary['agree'] == sum(c['agree'] for c in opinion)
    assert report.summary['statements_meta'] == 1


def test_meta_votes_never_move_the_participant_map(export_dir):
    from tools.polis_stats.groups import project
    path, _ = export_dir
    export = read_export(path)
    before = project(export)
    for (voter, sid), vote in export.votes.items():
        if sid == 6:
            vote.value = -vote.value                                  # flip every meta answer
    assert project(export) == before


def test_meta_crosstab_splits_every_opinion_by_the_meta_answer(export_dir):
    path, _ = export_dir
    export = read_export(path)
    report = compute(export)
    table = report.meta[6]['statements']
    assert 6 not in table and 4 not in table                          # only opinion statements
    for sid, by_answer in table.items():
        both = sum(1 for (voter, s) in export.votes if s == sid and (voter, 6) in export.votes)
        assert sum(sum(c.values()) for c in by_answer.values()) == both


def test_a_missing_meta_column_is_reported(export_dir):
    path, _ = export_dir
    rows = [r[:6] + r[7:] for r in csv.reader(open(path / 'comments.csv'))]     # drop is-meta
    with open(path / 'comments.csv', 'w', newline='') as fh:
        csv.writer(fh).writerows(rows)
    assert any(i.code == 'no-meta-column' for i in read_export(path).issues)


def test_statement_html_is_escaped_in_low_vote_heatmap_cells(export_dir, tmp_path):
    path, _ = export_dir
    rows = list(csv.reader(open(path / 'comments.csv')))
    for r in rows[1:]:
        if r[1] == '3':                                   # statement 3: too few votes, dashed cells
            r[-1] = '<img src=x onerror=alert(1)>'
    with open(path / 'comments.csv', 'w', newline='') as fh:
        csv.writer(fh).writerows(rows)
    out = tmp_path / 'out'
    assert main([str(path), '-o', str(out)]) == 0
    for name in ('report.html', 'charts/groups-heatmap.svg'):
        text = (out / name).read_text()
        assert '<img' not in text and '&lt;img src=x' in text


@pytest.mark.parametrize('body, message', [
    ('participant,group\n1,a\n', 'line 2: participant and group must be whole numbers'),
    ('participant,group\n1,0\n1,1\n', 'line 3: participant 1 appears twice'),
])
def test_a_bad_groups_file_names_the_line(export_dir, tmp_path, capsys, body, message):
    path, _ = export_dir
    groups = tmp_path / 'g.csv'
    groups.write_text(body)
    assert main([str(path), '-o', str(tmp_path / 'out'), '--groups', str(groups)]) == 2
    assert message in capsys.readouterr().err


def test_meta_difference_needs_enough_votes_on_both_sides(export_dir):
    from tools.polis_stats.report import _meta_html
    path, _ = export_dir
    report = compute(read_export(path))
    html = _meta_html(report)
    row3 = html[html.index('<td class="n">3</td>'):]
    row3 = row3[:row3.index('</tr>')]
    assert row3.endswith('<td class="n">—</td>')        # statement 3 has n=1 vs n=3
    assert html.index('<td class="n">3</td>') > html.index('<td class="n">2</td>')   # unrated rows last


def test_the_map_says_how_many_grouped_participants_it_placed(export_dir):
    from tools.polis_stats.groups import map_cutoff, participant_map, project
    path, _ = export_dir
    export = read_export(path)
    report = compute(export)
    svg = participant_map(project(export), export.groups, list(report.groups), export.group_source,
                          cutoff=map_cutoff(export))
    assert f'Placed: {len(project(export))} of 60 participants with a group' in svg

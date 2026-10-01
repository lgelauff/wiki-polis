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


def test_consensus_divisive_and_too_few_follow_the_thresholds(export_dir):
    path, data = export_dir
    t = Thresholds(min_votes=10, consensus_share=0.7, divisive_min_share=0.35)
    report = compute(read_export(path), t)
    expected = {'agree': [], 'disagree': [], 'divisive': [], 'few': []}
    for sid, c in sorted(data['truth'].items()):
        if sid in (4, 6):                              # rejected, and meta: counted, never classified
            continue
        decided = c['agree'] + c['disagree']
        if decided < t.min_votes:
            expected['few'].append(sid)
        elif c['agree'] / decided >= t.consensus_share:
            expected['agree'].append(sid)
        elif c['disagree'] / decided >= t.consensus_share:
            expected['disagree'].append(sid)
        elif min(c['agree'], c['disagree']) / decided >= t.divisive_min_share:
            expected['divisive'].append(sid)
    assert (report.consensus_agree, report.consensus_disagree, report.divisive, report.too_few_votes) == \
        (expected['agree'], expected['disagree'], expected['divisive'], expected['few'])
    # and the designed cases land where they were built to land
    assert 0 in report.consensus_agree and 1 in report.consensus_disagree
    assert 2 in report.divisive and report.too_few_votes == [3]
    assert 4 not in report.consensus_agree + report.consensus_disagree + report.divisive + report.too_few_votes


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
    for name in ('stats.json', 'statements.csv', 'issues.csv'):
        assert (out / name).exists(), name
    stats = json.loads((out / 'stats.json').read_text())
    assert stats['summary']['participants_voting'] == 60 and 0 in stats['consensus_agree']
    synth.write(tmp_path / 'raw', raw_sign=True)
    assert main([str(tmp_path / 'raw'), '-o', str(tmp_path / 'raw-out')]) == 1
    assert not (tmp_path / 'raw-out' / 'stats.json').exists()
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

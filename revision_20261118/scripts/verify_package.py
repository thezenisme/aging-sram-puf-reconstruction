"""Lightweight integrity and manuscript-configuration checks; never run FER sweeps."""
from pathlib import Path
import ast
import csv
import hashlib
import json
import math
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from plot_software_comparison import load_series, crossing


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    checked = 0
    for line in (ROOT / 'SHA256SUMS.txt').read_text().splitlines():
        expected, name = line.split('  ', 1)
        assert digest(ROOT / name) == expected, name
        checked += 1
    manifest = json.loads((ROOT / 'SOURCE_MANIFEST.json').read_text())
    for item in manifest['files']:
        assert digest(ROOT / item['file']) == item['packaged_sha256'], item['file']
        if item['modified_for_packaging'] and item['file'].endswith(('.sv', '.v', '.vhd', '.cpp', '.c', '.h')):
            assert 'path_substitutions' in item, item['file']
            original = (ROOT / item['file']).read_bytes()
            for edit in reversed(item['path_substitutions']):
                original = original.replace(edit['new'].encode(), edit['old'].encode())
            assert hashlib.sha256(original).hexdigest() == item['original_sha256'], item['file']

    paths = [ROOT / 'nr_ldpc_same_channel/results_5g_nr_ldpc_ms_early_stop_10000/fer_summary.csv',
             ROOT / 'polar_same_channel/fixed_scale2_profile768_profile_construct_rate_1_2_1000/fer_summary.csv',
             ROOT / 'turbo_same_channel/results_turbo_lte_qpp_100000_iter10/fer_summary.csv']
    for path, frames in zip(paths, [10000, 1000, 100000]):
        with path.open(encoding='utf-8-sig', newline='') as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 55, path
        for i, row in enumerate(rows):
            assert int(row['frames']) == frames
            assert math.isclose(float(row['scale']), 2.0)
            assert math.isclose(float(row['noise_floor']), (i+1)/1000, abs_tol=1e-9)
            assert math.isclose(int(row['message_failures'])/frames, float(row['message_fer']), abs_tol=1e-9)
        meta = json.loads((path.parent / 'provenance.json').read_text())
        assert meta['frames_per_point'] == frames
        assert meta['seed'] == 20260916
        if frames == 10000:
            assert 'min-sum' in meta['decoder'] and 'scaling_factor=1.0' in meta['decoder']
        elif frames == 1000:
            assert meta['construction_mode'] == 'profile-enrollment'
        else:
            assert meta['iterations'] == 10 and all(float(r['mean_iterations']) == 10 for r in rows)
    profile = (ROOT / 'nr_ldpc_same_channel/puf_profile_long.h').read_text()
    block = re.search(r'REAL_PUF_ERROR_RATES\s*\[4096\]\s*=\s*\{(.*?)\}', profile, re.S)[1]
    values = [float(x.strip()) for x in block.split(',') if x.strip()]
    assert len(values) == 4096 and values.count(.15) == 768 and values.count(.01) == 3328
    assert digest(ROOT / 'nr_ldpc_same_channel/puf_profile_long.h') == digest(
        ROOT / 'turbo_same_channel/results_turbo_lte_qpp_100000_iter10/profile_snapshot.h')

    reports = [
        (ROOT / 'proposed_hw_formal_5bit_message_bram/reference_reports/synthesis/utilization_synth.rpt', (1440,160,3.5,0)),
        (ROOT / 'polar_hw_kestel_512_64/reference_reports/utilization_synth.rpt', (2755,2314,2,0)),
        (ROOT / 'turbo_hw_lte_belov_mosin/reference_reports/turbo_lte_4096_2048_compare_top_utilization_synth.rpt', (6493,5461,21,1)),
    ]
    for path, expected in reports:
        text = path.read_text()
        actual = []
        for label in ['CLB LUTs*', 'CLB Registers', 'Block RAM Tile', 'DSPs']:
            m = re.search(r'^\|\s*' + re.escape(label) + r'\s*\|\s*([0-9.]+)', text, re.M)
            assert m, (path, label)
            actual.append(float(m[1]))
        assert tuple(actual) == expected, (path, actual)

    limits = {k: crossing(points) for k, points in load_series().items()}
    for label, percent in [('NR-LDPC', 8.08), ('Turbo', 8.41), ('Proposed', 9.85)]:
        assert abs(100*limits[label] - percent) < .02, (label, limits[label])
    assert limits['Polar SC'] is None
    for p in ROOT.rglob('*.py'):
        if any(x in p.parts for x in ['vendor', 'build', '__pycache__']):
            continue
        ast.parse(p.read_text(encoding='utf-8-sig'), filename=str(p))
    assert not any('leakage_analysis_revised' in p.name for p in ROOT.rglob('*'))
    print(json.dumps({'passed': True, 'files_hash_checked': checked,
                      'selected_software_results': 3, 'hardware_reports': 3,
                      'linear_interpolation_at_FER_1e_3': limits,
                      'revised_leakage_diagnostic_included': False}, indent=2))


if __name__ == '__main__':
    main()

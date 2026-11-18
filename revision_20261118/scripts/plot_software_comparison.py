"""Regenerate the four-configuration comparison from the selected frozen CSVs."""
from pathlib import Path
import csv
import json

ROOT = Path(__file__).resolve().parents[1]
SOURCES = {
    'Proposed': ROOT.parent / 'results/main_rate12_long.csv',
    'NR-LDPC': ROOT / 'nr_ldpc_same_channel/results_5g_nr_ldpc_ms_early_stop_10000/fer_summary.csv',
    'Polar SC': ROOT / 'polar_same_channel/fixed_scale2_profile768_profile_construct_rate_1_2_1000/fer_summary.csv',
    'Turbo': ROOT / 'turbo_same_channel/results_turbo_lte_qpp_100000_iter10/fer_summary.csv',
}


def load_series():
    result = {}
    for label, path in SOURCES.items():
        with path.open(encoding='utf-8-sig', newline='') as f:
            rows = [{k.strip(): v.strip() for k, v in r.items()} for r in csv.DictReader(f)]
        keys = ('Actual_BER', 'Staircase_FER') if label == 'Proposed' else ('actual_raw_ber', 'message_fer')
        result[label] = [(float(r[keys[0]]), float(r[keys[1]])) for r in rows]
    return result


def crossing(points, target=1e-3):
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if y0 <= target <= y1 and y1 > y0:
            return x0 + (target - y0) * (x1 - x0) / (y1 - y0)
    return None


def main():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    series = load_series()
    output = ROOT / 'build/software_comparison'
    output.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({'font.size': 10, 'pdf.fonttype': 42, 'svg.fonttype': 'none'})
    fig, ax = plt.subplots(figsize=(6.8, 4.6), layout='constrained')
    for label, points in series.items():
        positive = [(x, y) for x, y in points if y > 0]
        ax.semilogy(*zip(*positive), marker='o', markersize=3, linewidth=1, label=label)
    ax.axhline(1e-3, color='0.5', linestyle='--', linewidth=0.8)
    ax.set(xlabel='Raw BER', ylabel='FER', ylim=(1e-5, 1.1))
    ax.legend()
    for ext in ['pdf', 'svg', 'png']:
        fig.savefig(output / f'software_comparison.{ext}', dpi=200)
    estimates = {key: crossing(points) for key, points in series.items()}
    (output / 'breakdown_estimates.json').write_text(json.dumps(estimates, indent=2) + '\n')
    print(json.dumps({'linear_interpolation_at_FER_1e_3': estimates,
                      'zero_failure_points': 'omitted from log plot, not replaced with point estimates',
                      'output': str(output)}, indent=2))


if __name__ == '__main__':
    main()

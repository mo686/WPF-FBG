"""
Plot matching comparison with different bandwidths:
(a) Match with corr_bandwidth=3.0 GHz
(b) Match with corr_bandwidth=1.0 GHz

Shows measured S21 vs best calibration match, with match range shaded.
"""

import os
import sys
import csv
import numpy as np
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'src'))
import plot_style
from plot_style import add_subplot_label
from calibration_pipeline import (
    load_curves_from_directory, build_calibration_table,
    match_curve, extract_peak, S21Curve
)

# ============================================================
# Configuration
# ============================================================
MEAS_FILE_A = r'C:\Users\ezhuzix\OneDrive - Ericsson\Desktop\WPF-FBG\measure\measure_4_18\test_1_1.1_0.0001w_1551.88.csv'
MEAS_FILE_B = r'C:\Users\ezhuzix\OneDrive - Ericsson\Desktop\WPF-FBG\measure\measure_4_18\test_1_1.1_0.0001w_1551.9.csv'
CAL_DIR = r'C:\Users\ezhuzix\OneDrive - Ericsson\Desktop\WPF-FBG\measure\sweep_data_4_18_25'

# Bandwidth settings for each subplot
BW_A = 3.0   # GHz
BW_B = 1.0   # GHz


def load_voltage_scan(filepath):
    """Load multi-voltage S21 scan from CSV."""
    scans = {}
    with open(filepath, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            v = float(row['Voltage'])
            if v not in scans:
                scans[v] = ([], [])
            scans[v][0].append(float(row['Frequency_Hz']))
            scans[v][1].append(float(row['Magnitude_dB']))
    for v in scans:
        scans[v] = (np.array(scans[v][0]), np.array(scans[v][1]))
    return scans


def find_best_match(scans, table, corr_bandwidth):
    """Find the voltage with the best correlation match."""
    best_voltage = None
    best_rho = -1
    best_result = None
    best_meas_curve = None

    for v in sorted(scans.keys()):
        freq_hz, mag_db = scans[v]
        meas_curve = S21Curve(frequency=freq_hz / 1e9, magnitude=mag_db)
        try:
            result = match_curve(meas_curve, table, k_cand=5, smooth_window=5,
                                 corr_bandwidth=corr_bandwidth,
                                 match_mode='correlation')
            if result.rho > best_rho:
                best_rho = result.rho
                best_voltage = v
                best_result = result
                best_meas_curve = meas_curve
        except ValueError:
            continue

    return best_voltage, best_rho, best_result, best_meas_curve


def plot_match_subplot(ax, meas_curve, cal_curve, voltage, rho, delta_lambda, bw, label):
    """Plot a single matching subplot."""
    power = voltage**2 / 100.0  # W, R=100 ohm
    ax.plot(meas_curve.frequency, meas_curve.magnitude,
            color='blue', linewidth=1.5,
            label=f'Measured P={power*1000:.2f} mW')
    ax.plot(cal_curve.frequency, cal_curve.magnitude,
            color='red', linestyle='--', linewidth=1.5,
            label=f'Calibration $\\Delta\\lambda$={delta_lambda:.0f} pm')

    # Shade the match range
    fpeak = extract_peak(meas_curve)
    f_lo = max(fpeak - bw, meas_curve.frequency[0])
    f_hi = min(fpeak + bw, meas_curve.frequency[-1])
    ax.axvspan(f_lo, f_hi, alpha=0.12, color='green',
               label=f'Match range ($\\pm${bw:.1f} GHz)')
    ax.axvline(fpeak, color='green', linestyle=':', linewidth=0.8, alpha=0.6)

    ax.set_title(f'Correlation  $\\rho$={rho:.4f}')
    ax.set_xlabel('Frequency (GHz)')
    ax.set_ylabel('Magnitude (dB)')
    ax.set_xlim(0, 30)
    ax.set_ylim(-85, -30)
    from matplotlib.ticker import MultipleLocator
    ax.yaxis.set_major_locator(MultipleLocator(10))
    ax.legend(loc='upper right')
    add_subplot_label(ax, label)


def main():
    print("Loading calibration table...")
    cal_curves = load_curves_from_directory(CAL_DIR)
    table = build_calibration_table(cal_curves, smooth_window=5)
    print(f"  {len(table)} calibration curves")

    print("Loading measurement scans...")
    scans_a = load_voltage_scan(MEAS_FILE_A)
    scans_b = load_voltage_scan(MEAS_FILE_B)
    print(f"  File A: {len(scans_a)} voltage points")
    print(f"  File B: {len(scans_b)} voltage points")

    # Match with bandwidth A using file A
    print(f"\nMatching file A with BW = {BW_A} GHz...")
    v_a, rho_a, res_a, meas_a = find_best_match(scans_a, table, BW_A)
    cal_a = table.entries[res_a.cal_index].curve
    print(f"  Best: V={v_a:.3f}V, rho={rho_a:.4f}, dl={res_a.delta_lambda:.0f} pm")

    # Match with bandwidth B using file B
    print(f"\nMatching file B with BW = {BW_B} GHz...")
    v_b, rho_b, res_b, meas_b = find_best_match(scans_b, table, BW_B)
    cal_b = table.entries[res_b.cal_index].curve
    print(f"  Best: V={v_b:.3f}V, rho={rho_b:.4f}, dl={res_b.delta_lambda:.0f} pm")

    # ============================================================
    # Plot
    # ============================================================
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.5))

    plot_match_subplot(axes[0], meas_a, cal_a, v_a, rho_a,
                       res_a.delta_lambda, BW_A, '(a)')
    plot_match_subplot(axes[1], meas_b, cal_b, v_b, rho_b,
                       res_b.delta_lambda, BW_B, '(b)')

    plt.tight_layout(pad=1.5)

    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               'matching_comparison.png')
    plt.savefig(output_path, dpi=200, bbox_inches='tight')
    print(f"\nFigure saved: {output_path}")
    plt.show()


if __name__ == '__main__':
    main()

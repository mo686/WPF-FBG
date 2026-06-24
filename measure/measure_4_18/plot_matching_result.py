"""
Plot matching result: (a) FBG spectra comparison, (b) S21 best match with calibration curve.
"""

import os
import sys
import json
import csv
import re
import numpy as np
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'src'))
import plot_style
from plot_style import add_subplot_label
from calibration_pipeline import (
    load_s21_curve, load_curves_from_directory, build_calibration_table,
    match_curve, extract_peak, S21Curve
)

# ============================================================
# Configuration — change paths here
# ============================================================
FBG_FILE_1 = r'C:\Users\ezhuzix\OneDrive - Ericsson\Desktop\WPF-FBG\measure\measure_4_18\FBG_20_4h.json'
FBG_FILE_2 = r'C:\Users\ezhuzix\OneDrive - Ericsson\Desktop\WPF-FBG\measure\measure_4_18\FBG_25_3h.json'
MEAS_FILE = r'C:\Users\ezhuzix\OneDrive - Ericsson\Desktop\WPF-FBG\measure\measure_4_18\test_1_1.15_0.0001w.csv'
CAL_DIR = r'C:\Users\ezhuzix\OneDrive - Ericsson\Desktop\WPF-FBG\measure\sweep_data_4_18_25'


def load_fbg_spectrum(filepath):
    """Load FBG spectrum from JSON file."""
    with open(filepath, 'r') as f:
        data = json.load(f)
    entry = data[0] if isinstance(data, list) else data
    return np.array(entry['rescaled_wavelength']), np.array(entry['rescaled_reference_power'])


def load_voltage_scan(filepath):
    """Load multi-voltage S21 scan from CSV. Returns dict {voltage: (freq_hz, mag_db)}."""
    scans = {}
    with open(filepath, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            v = float(row['Voltage'])
            if v not in scans:
                scans[v] = ([], [])
            scans[v][0].append(float(row['Frequency_Hz']))
            scans[v][1].append(float(row['Magnitude_dB']))
    # Convert to numpy
    for v in scans:
        scans[v] = (np.array(scans[v][0]), np.array(scans[v][1]))
    return scans


def main():
    print("Loading data...")

    # Load FBG spectra
    wl1, pw1 = load_fbg_spectrum(FBG_FILE_1)
    wl2, pw2 = load_fbg_spectrum(FBG_FILE_2)
    label1 = re.search(r'(FBG_\d+)', os.path.basename(FBG_FILE_1)).group(1)
    label2 = re.search(r'(FBG_\d+)', os.path.basename(FBG_FILE_2)).group(1)
    center1 = wl1[np.argmax(pw1)]
    center2 = wl2[np.argmax(pw2)]

    # Load calibration table
    print("Loading calibration table...")
    cal_curves = load_curves_from_directory(CAL_DIR)
    table = build_calibration_table(cal_curves, smooth_window=5)
    print(f"  {len(table)} calibration curves loaded")

    # Load measurement scans and find best match
    print("Loading measurement scans...")
    scans = load_voltage_scan(MEAS_FILE)
    voltages = sorted(scans.keys())
    print(f"  {len(voltages)} voltage points")

    best_voltage = None
    best_rho = -1
    best_result = None
    best_meas_curve = None

    for v in voltages:
        freq_hz, mag_db = scans[v]
        meas_curve = S21Curve(frequency=freq_hz / 1e9, magnitude=mag_db)
        try:
            result = match_curve(meas_curve, table, k_cand=5, smooth_window=5,
                                 match_mode='correlation')
            if result.rho > best_rho:
                best_rho = result.rho
                best_voltage = v
                best_result = result
                best_meas_curve = meas_curve
        except ValueError:
            continue

    best_power = best_voltage**2 / 100.0  # W, R=100 ohm

    print(f"\nBest match: P={best_power*1000:.2f}mW (V={best_voltage:.3f}V), rho={best_rho:.4f}, "
          f"delta_lambda={best_result.delta_lambda:.1f} pm")

    best_cal_curve = table.entries[best_result.cal_index].curve

    # ============================================================
    # Plot
    # ============================================================
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.5))

    # --- (a) FBG spectra comparison ---
    ax1 = axes[0]
    ax1.plot(wl1, pw1, linewidth=1.5, label=label1)
    ax1.plot(wl2, pw2, linewidth=1.5, label=label2)
    ax1.axvline(x=center1, color='C0', linestyle='--', alpha=0.7,
                label=f'{center1:.4f}')
    ax1.axvline(x=center2, color='C1', linestyle='--', alpha=0.7,
                label=f'{center2:.4f}')
    ax1.set_xlabel('Wavelength (nm)')
    ax1.set_ylabel('Transmission (dB)')
    ax1.set_xlim(1551.55, 1552.2)
    ax1.set_ylim(-30, 0)
    ax1.legend(loc='upper right')
    add_subplot_label(ax1, '(a)')

    # --- (b) Best S21 match ---
    ax2 = axes[1]
    ax2.plot(best_meas_curve.frequency, best_meas_curve.magnitude,
             color='blue', linewidth=1.5,
             label=f'Measured P={best_power*1000:.2f} mW')
    ax2.plot(best_cal_curve.frequency, best_cal_curve.magnitude,
             color='red', linestyle='--', linewidth=1.5,
             label=f'Calibration $\\Delta\\lambda$={best_result.delta_lambda:.0f} pm')
    ax2.set_title(f'Correlation  $\\rho$={best_rho:.4f}')
    ax2.set_xlabel('Frequency (GHz)')
    ax2.set_ylabel('RF Gain (dB)')
    ax2.set_xlim(0,30)
    ax2.set_ylim(-85,-30)
    ax2.legend(loc='upper right')
    add_subplot_label(ax2, '(b)')

    plt.tight_layout(pad=1.5)

    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               'matching_result.png')
    plt.savefig(output_path, dpi=200, bbox_inches='tight')
    print(f"\nFigure saved: {output_path}")
    plt.show()


if __name__ == '__main__':
    main()

"""
Calibration Peak Frequency vs Wavelength Shift Analysis
========================================================
Load all calibration S21 curves, extract peak frequency for each,
and plot the relationship between peak frequency (f_peak) and
wavelength shift (delta_lambda).

For Δλ < 0, the MRR resonance is on the short-wavelength side of FBG,
producing a passband at positive frequency; for Δλ > 0, the resonance
is on the long-wavelength side. The signed peak frequency is defined as:
  f_signed = +f_peak  for Δλ > 0
  f_signed = -f_peak  for Δλ < 0
This yields a monotonic linear mapping.
"""

import os
import re
import sys
import csv
import numpy as np
import matplotlib
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
import plot_style

# ============================================================
# Configuration
# ============================================================
CAL_DIR = r'C:\Users\ezhuzix\OneDrive - Ericsson\Desktop\WPF-FBG\measure\sweep_data_4_19_25'
SMOOTH_WINDOW = 5
MAG_THRESHOLD = -40.0   # dB, curves near Δλ=0 with peak weaker than this are "excluded"
FREQ_MIN = 2.0          # GHz, lower bound for peak search
FREQ_MAX = 25.0         # GHz, upper bound for peak search


def extract_peak_frequency(freq_hz, magnitude_db, smooth_window=5):
    """Extract peak frequency from S21 curve (search in FREQ_MIN–FREQ_MAX GHz)."""
    freq_ghz = freq_hz / 1e9
    mag = magnitude_db

    mask = (freq_ghz >= FREQ_MIN) & (freq_ghz <= FREQ_MAX)
    freq_ghz = freq_ghz[mask]
    mag = mag[mask]

    if len(mag) < smooth_window:
        idx = int(np.argmax(mag))
        return freq_ghz[idx], mag[idx]

    kernel = np.ones(smooth_window) / smooth_window
    smoothed = np.convolve(mag, kernel, mode='valid')
    offset = (smooth_window - 1) // 2
    freq_ghz = freq_ghz[offset:offset + len(smoothed)]

    idx = int(np.argmax(smoothed))
    return freq_ghz[idx], smoothed[idx]


def load_csv_fast(filepath):
    """Load CSV with frequency and magnitude columns."""
    freq, mag = [], []
    with open(filepath, 'r') as f:
        reader = csv.reader(f)
        next(reader)
        for row in reader:
            freq.append(float(row[0]))
            mag.append(float(row[1]))
    return np.array(freq), np.array(mag)


def main():
    print("=" * 60)
    print("Calibration f_peak vs Δλ Analysis")
    print("=" * 60)
    print(f"Directory: {CAL_DIR}")

    csv_files = [f for f in os.listdir(CAL_DIR) if f.endswith('.csv')]
    print(f"  Found {len(csv_files)} CSV files")

    # Load ALL data
    all_dl = []
    all_fpeak = []
    all_mag = []

    for i, fname in enumerate(csv_files):
        match = re.search(r'delta_lambda_(-?\d+\.?\d*)', fname)
        if match is None:
            continue
        delta_lambda = float(match.group(1))
        filepath = os.path.join(CAL_DIR, fname)
        try:
            freq_hz, mag_db = load_csv_fast(filepath)
            fpeak, peak_mag = extract_peak_frequency(freq_hz, mag_db, SMOOTH_WINDOW)
            all_dl.append(delta_lambda)
            all_fpeak.append(fpeak)
            all_mag.append(peak_mag)
        except Exception as e:
            print(f"  Warning: {fname}: {e}")

    all_dl = np.array(all_dl)
    all_fpeak = np.array(all_fpeak)
    all_mag = np.array(all_mag)

    # Sort
    sort_idx = np.argsort(all_dl)
    all_dl = all_dl[sort_idx]
    all_fpeak = all_fpeak[sort_idx]
    all_mag = all_mag[sort_idx]

    # Separate valid vs excluded.
    # Only exclude the flat cluster nearest to Δλ=0 (the "middle" flat region).
    # Other flat runs at the edges are NOT excluded.
    signed_all = np.where(all_dl < 0, -all_fpeak, all_fpeak)

    # Detect flat clusters: groups of consecutive points where raw f_peak
    # barely changes between adjacent points
    FPEAK_DIFF_THRESHOLD = 0.05  # GHz
    
    in_flat_run = np.zeros(len(all_fpeak), dtype=bool)
    for i in range(1, len(all_fpeak)):
        if abs(all_fpeak[i] - all_fpeak[i-1]) < FPEAK_DIFF_THRESHOLD:
            in_flat_run[i] = True
            in_flat_run[i-1] = True

    # Find all contiguous flat clusters
    clusters = []
    i = 0
    while i < len(in_flat_run):
        if in_flat_run[i]:
            j = i
            while j < len(in_flat_run) and in_flat_run[j]:
                j += 1
            clusters.append((i, j - 1))  # (start_idx, end_idx)
            i = j
        else:
            i += 1

    # Only exclude the cluster closest to Δλ=0 (the middle one)
    excluded_mask = np.zeros(len(all_dl), dtype=bool)
    if clusters:
        # Find the cluster whose center Δλ is closest to 0
        mid_cluster = min(clusters, key=lambda c: abs(np.mean(all_dl[c[0]:c[1]+1])))
        start, end = mid_cluster
        # Keep first and last of this cluster, exclude the middle
        if end - start >= 2:
            excluded_mask[start+1:end] = True

    valid_mask = ~excluded_mask

    dl_valid = all_dl[valid_mask]
    dl_excluded = all_dl[excluded_mask]
    signed_valid = signed_all[valid_mask]
    signed_excluded = signed_all[excluded_mask]

    print(f"\n  Total: {len(all_dl)} curves")
    print(f"  Valid: {np.sum(valid_mask)}")
    print(f"  Excluded (off-trend): {np.sum(excluded_mask)}")
    print(f"  Δλ range (valid): {dl_valid[0]:.1f} to {dl_valid[-1]:.1f} pm")

    # Signed frequency for valid/excluded
    signed_valid = signed_all[valid_mask]
    signed_excluded = signed_all[excluded_mask]

    # Linear fit on valid signed data
    coeffs = np.polyfit(dl_valid, signed_valid, 1)
    predicted = np.polyval(coeffs, dl_valid)
    ss_res = np.sum((signed_valid - predicted)**2)
    ss_tot = np.sum((signed_valid - np.mean(signed_valid))**2)
    r2 = 1 - ss_res / ss_tot

    print(f"\n  Linear fit (signed): slope = {coeffs[0]*1000:.2f} MHz/pm")
    print(f"  R² = {r2:.6f}")

    # ============================================================
    # Plot
    # ============================================================
    fig, ax = plt.subplots(figsize=(7, 5))

    # Plot excluded points (gray, smaller, labeled)
    if len(dl_excluded) > 0:
        ax.plot(dl_excluded, signed_excluded, 'x', color='gray',
                markersize=4, alpha=0.5, label='Excluded')

    # Plot valid points
    ax.plot(dl_valid, signed_valid, 'o', color='tab:blue',
            markersize=5, alpha=0.8, label='Valid calibration data')

    # Linear fit line
    dl_fit = np.linspace(-165, 165, 300)
    ax.plot(dl_fit, np.polyval(coeffs, dl_fit), '-', color='tab:red',
            linewidth=1.8,
            label=f'Linear fit ({coeffs[0]*1000:.2f} MHz/pm)')

    ax.set_xlabel('$\\Delta\\lambda$ (pm)')
    ax.set_ylabel('Peak Frequency (GHz)')
    ax.legend(loc='upper left')
    ax.text(0.95, 0.08, f'$R^2$ = {r2:.4f}', transform=ax.transAxes,
            ha='right', va='bottom')

    # Show the full ±160 range
    ax.set_xlim(-170, 170)

    # Shade the excluded (middle flat) region
    if len(dl_excluded) > 0:
        exc_dl_min = dl_excluded.min()
        exc_dl_max = dl_excluded.max()
        ax.axvspan(exc_dl_min, exc_dl_max, alpha=0.08, color='orange',
                   label=f'Excluded range ({exc_dl_min:.0f} to {exc_dl_max:.0f} pm)')
        ax.legend(loc='upper left')
    ax.set_xlim(-170, 170)

    plt.tight_layout()

    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               'calibration_fpeak_vs_dlambda.png')
    plt.savefig(output_path, dpi=200, bbox_inches='tight')
    print(f"\nFigure saved: {output_path}")
    plt.show()


if __name__ == '__main__':
    main()

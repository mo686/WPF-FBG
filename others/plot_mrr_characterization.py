"""
MRR Characterization Plot
==========================
(a) MRR drop-port spectrum with FSR, 3dB bandwidth, and Q factor annotated.
(b) Overlay of MRR+FBG spectra at different FBG center wavelengths.
"""

import os
import sys
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
from scipy.signal import find_peaks

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
import plot_style
from plot_style import add_subplot_label

# ============================================================
# Data paths
# ============================================================
DATA_DIR = os.path.dirname(os.path.abspath(__file__))
MRR_DROP_FILE = os.path.join(DATA_DIR, 'MRR_drop.csv')
REF_FILE = os.path.join(DATA_DIR, 'ref.csv')
MRR_FBG_FILES = {
    1546: os.path.join(DATA_DIR, 'MRR_FBG_1546.csv'),
    1548: os.path.join(DATA_DIR, 'MRR_FBG_1548.csv'),
    1550: os.path.join(DATA_DIR, 'MRR_FBG_1550.csv'),
    1552: os.path.join(DATA_DIR, 'MRR_FBG_1552.csv'),
    1554: os.path.join(DATA_DIR, 'MRR_FBG_1554.csv'),
}


def load_santec_csv(filepath):
    """Load Santec IL STS CSV file (skip header, data starts at line 15)."""
    wavelength = []
    power = []
    with open(filepath, 'r') as f:
        lines = f.readlines()
    # Find data start (line after "Wavelength(nm),...")
    data_start = 0
    for i, line in enumerate(lines):
        if line.startswith('Wavelength'):
            data_start = i + 1
            break
    for line in lines[data_start:]:
        parts = line.strip().split(',')
        if len(parts) >= 2 and parts[0] and parts[1]:
            try:
                wavelength.append(float(parts[0]))
                power.append(float(parts[1]))
            except ValueError:
                continue
    return np.array(wavelength), np.array(power)


def find_resonance_peaks(wavelength, power, prominence=3, distance=500):
    """Find resonance peaks (maxima) in the drop-port spectrum."""
    peaks, properties = find_peaks(power, prominence=prominence, distance=distance)
    return peaks, properties


def measure_3db_bandwidth(wavelength, power, peak_idx):
    """Measure 3dB bandwidth around a peak."""
    peak_val = power[peak_idx]
    threshold = peak_val - 3.0

    # Search right
    right_wl = wavelength[peak_idx]
    for j in range(peak_idx + 1, len(power)):
        if power[j] <= threshold:
            # Linear interpolation
            frac = (threshold - power[j-1]) / (power[j] - power[j-1])
            right_wl = wavelength[j-1] + frac * (wavelength[j] - wavelength[j-1])
            break

    # Search left
    left_wl = wavelength[peak_idx]
    for j in range(peak_idx - 1, -1, -1):
        if power[j] <= threshold:
            frac = (threshold - power[j+1]) / (power[j] - power[j+1])
            left_wl = wavelength[j+1] + frac * (wavelength[j] - wavelength[j+1])
            break

    bw = right_wl - left_wl
    return bw, left_wl, right_wl


def main():
    print("=" * 60)
    print("MRR Characterization Plot")
    print("=" * 60)

    # Load MRR drop spectrum
    wl_drop, pw_drop = load_santec_csv(MRR_DROP_FILE)
    print(f"MRR drop: {len(wl_drop)} points, {wl_drop[0]:.3f}-{wl_drop[-1]:.3f} nm")

    # Load reference and subtract
    wl_ref, pw_ref = load_santec_csv(REF_FILE)
    print(f"Reference: {len(wl_ref)} points")
    if len(pw_ref) == len(pw_drop):
        pw_drop = pw_drop - pw_ref
        print("  Reference subtracted from MRR drop")
    else:
        print("  WARNING: ref length mismatch, using raw data")

    # Find resonance peaks
    peaks, props = find_resonance_peaks(wl_drop, pw_drop, prominence=2, distance=2000)
    print(f"Found {len(peaks)} peaks")

    # Calculate FSR (average spacing between adjacent resonance peaks)
    if len(peaks) >= 2:
        peak_wavelengths = wl_drop[peaks]
        peak_wavelengths_sorted = np.sort(peak_wavelengths)
        spacings = np.diff(peak_wavelengths_sorted)
        fsr = np.mean(spacings)
        print(f"FSR = {fsr:.4f} nm (average of {len(spacings)} spacings)")
        print(f"  Individual spacings: {[f'{s:.4f}' for s in spacings]} nm")

        # Use the strongest peak for 3dB BW and Q
        peak_powers = pw_drop[peaks]
        strongest_idx = np.argmax(peak_powers)
        main_peak_idx = peaks[strongest_idx]
    else:
        fsr = 0
        main_peak_idx = peaks[0] if len(peaks) > 0 else np.argmax(pw_drop)

    peak_wl = wl_drop[main_peak_idx]
    bw_3db, left_3db, right_3db = measure_3db_bandwidth(wl_drop, pw_drop, main_peak_idx)
    Q = peak_wl / bw_3db if bw_3db > 0 else 0

    print(f"Main peak: {peak_wl:.4f} nm")
    print(f"3dB bandwidth: {bw_3db*1000:.2f} pm")
    print(f"Q factor: {Q:.0f}")

    # ============================================================
    # Plot: (a) MRR drop full spectrum + FSR
    #        (b) Zoomed single peak for 3dB BW and Q
    #        (c) MRR+FBG overlay
    #        (d) Calibration S21 curve peak with FWHM
    # ============================================================
    fig, axes = plt.subplots(2, 2, figsize=(10, 7.5))

    # --- (a) MRR drop-port full spectrum with FSR annotation ---
    ax1 = axes[0, 0]
    ax1.plot(wl_drop, pw_drop, color='#1f77b4', linewidth=1.5, label='MRR drop')
    ax1.plot(wl_drop[peaks], pw_drop[peaks], 'v', color='#d62728', markersize=8, label='Peaks')

    # FSR arrow between two adjacent peaks near the main peak
    if len(peaks) >= 2:
        peak_wavelengths_sorted = np.sort(wl_drop[peaks])
        main_wl = wl_drop[main_peak_idx]
        main_sorted_idx = np.argmin(np.abs(peak_wavelengths_sorted - main_wl))
        if main_sorted_idx < len(peak_wavelengths_sorted) - 1:
            wl_p1 = peak_wavelengths_sorted[main_sorted_idx]
            wl_p2 = peak_wavelengths_sorted[main_sorted_idx + 1]
        else:
            wl_p1 = peak_wavelengths_sorted[main_sorted_idx - 1]
            wl_p2 = peak_wavelengths_sorted[main_sorted_idx]

        pw_arrow = pw_drop[main_peak_idx]+1.8
        ax1.annotate('', xy=(wl_p1, pw_arrow), xytext=(wl_p2, pw_arrow),
                     arrowprops=dict(arrowstyle='<|-|>', color='black', lw=1.5,
                                     mutation_scale=12))
        ax1.text(wl_p1 - 0.1, pw_arrow,
                 f'FSR = {fsr:.3f} nm', ha='right', va='center',
                 color='black')
        ax1.vlines([wl_p1, wl_p2], [pw_drop[main_peak_idx] + 0.5, pw_drop[main_peak_idx] + 0.5],
                   [pw_arrow, pw_arrow], colors='black', linestyles='--', linewidth=0.8, alpha=0.7)

    ax1.set_xlabel('Wavelength (nm)')
    ax1.set_ylabel('Transmission (dB)')
    ax1.set_ylim(-35, 0)
    ax1.legend(loc='upper right')
    add_subplot_label(ax1, '(a)')

    # --- (b) Zoomed single peak for 3dB BW and Q ---
    ax2 = axes[0, 1]
    zoom_hw = 0.05  # nm half-width
    zoom_mask = (wl_drop >= peak_wl - zoom_hw) & (wl_drop <= peak_wl + zoom_hw)
    ax2.plot(wl_drop[zoom_mask], pw_drop[zoom_mask], color='#1f77b4', linewidth=2.0, label='MRR drop')

    threshold_val = pw_drop[main_peak_idx] - 3.0
    bw_half = (right_3db - left_3db) / 2
    arrow_len = bw_half * 3 
    ax2.annotate('', xy=(left_3db, threshold_val),
                 xytext=(left_3db - arrow_len, threshold_val),
                 arrowprops=dict(arrowstyle='-|>', color='black', lw=1.5, mutation_scale=12))
    ax2.annotate('', xy=(right_3db, threshold_val),
                 xytext=(right_3db + arrow_len, threshold_val),
                 arrowprops=dict(arrowstyle='-|>', color='black', lw=1.5, mutation_scale=12))
    ax2.plot(peak_wl, pw_drop[main_peak_idx], 'v', color='#d62728', markersize=7, label='Peak')
    # Text to the left of left arrow
    ax2.text(left_3db - arrow_len - bw_half * 0.3, threshold_val,
             f'$\\Delta\\lambda_{{3dB}}$ = {bw_3db*1000:.2f} pm\nQ = {Q:,.0f}',
             ha='right', va='center', linespacing=1.8,
             color='black')
    ax2.legend(loc='upper right')

    ax2.set_xlabel('Wavelength (nm)')
    ax2.set_ylabel('Transmission (dB)')
    ax2.set_ylim(-35, -5)
    # Show full wavelength values (no offset notation) with sensible ticks
    ax2.ticklabel_format(axis='x', useOffset=False)
    ax2.xaxis.set_major_locator(plt.MaxNLocator(5))
    add_subplot_label(ax2, '(b)')

    # --- (c) MRR+FBG overlay at different wavelengths ---
    ax3 = axes[1, 0]
    colors_c = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd']
    for i, (wl_center, filepath) in enumerate(sorted(MRR_FBG_FILES.items())):
        if os.path.exists(filepath):
            wl, pw = load_santec_csv(filepath)
            # Compensate source power (+10 dBm → -10 dBm basis), then subtract ref
            pw = pw - 9.9
            if len(pw) == len(pw_ref):
                pw = pw - pw_ref
            ax3.plot(wl, pw, color=colors_c[i % len(colors_c)], linewidth=1.5,
                     label=f'{wl_center} nm')
        else:
            print(f"  Warning: {filepath} not found")

    ax3.set_xlabel('Wavelength (nm)')
    ax3.set_ylabel('Transmission (dB)')
    ax3.set_ylim(-49,-5)
    ax3.legend(loc='upper right')
    add_subplot_label(ax3, '(c)')

    # --- (d) Calibration S21 curve with FWHM annotation ---
    ax4 = axes[1, 1]
    
    CAL_DIR = r'C:\Users\ezhuzix\OneDrive - Ericsson\Desktop\WPF-FBG\measure\sweep_data_4_19_25'
    cal_file = os.path.join(CAL_DIR, 'delta_lambda_50.0.csv')
    if os.path.exists(cal_file):
        import csv as csv_mod
        cal_freq, cal_mag = [], []
        with open(cal_file, 'r') as f:
            reader = csv_mod.reader(f)
            next(reader)
            for row in reader:
                cal_freq.append(float(row[0]))
                cal_mag.append(float(row[1]))
        cal_freq = np.array(cal_freq) / 1e9
        cal_mag = np.array(cal_mag)

        plot_mask = (cal_freq >= 2.5) & (cal_freq <= 10.0)
        ax4.plot(cal_freq[plot_mask], cal_mag[plot_mask], color='#1f77b4', linewidth=1.5, label='$S_{21}$ response')

        freq_search = cal_freq[plot_mask]
        mag_search = cal_mag[plot_mask]
        kernel = np.ones(5) / 5
        smoothed = np.convolve(mag_search, kernel, mode='valid')
        offset = 2
        freq_smooth = freq_search[offset:offset + len(smoothed)]
        
        peak_idx_local = int(np.argmax(smoothed))
        f_peak = freq_smooth[peak_idx_local]
        peak_mag_val = smoothed[peak_idx_local]
        threshold_3db = peak_mag_val - 3.0

        f_right = f_peak
        for j in range(peak_idx_local + 1, len(smoothed)):
            if smoothed[j] <= threshold_3db:
                frac = (threshold_3db - smoothed[j-1]) / (smoothed[j] - smoothed[j-1])
                f_right = freq_smooth[j-1] + frac * (freq_smooth[j] - freq_smooth[j-1])
                break
        f_left = f_peak
        for j in range(peak_idx_local - 1, -1, -1):
            if smoothed[j] <= threshold_3db:
                frac = (threshold_3db - smoothed[j+1]) / (smoothed[j] - smoothed[j+1])
                f_left = freq_smooth[j+1] + frac * (freq_smooth[j] - freq_smooth[j+1])
                break
        fwhm = f_right - f_left

        ax4.plot(f_peak, peak_mag_val, 'v', color='#d62728', markersize=7, label='Peak')
        fwhm_half = fwhm / 2
        arrow_len = fwhm_half * 2
        ax4.annotate('', xy=(f_left, threshold_3db),
                     xytext=(f_left - arrow_len, threshold_3db),
                     arrowprops=dict(arrowstyle='-|>', color='black', lw=1.5, mutation_scale=12))
        ax4.annotate('', xy=(f_right, threshold_3db),
                     xytext=(f_right + arrow_len, threshold_3db),
                     arrowprops=dict(arrowstyle='-|>', color='black', lw=1.5, mutation_scale=12))
        # Text to the left of left arrow
        ax4.text(f_left - arrow_len - fwhm_half * 0.3, threshold_3db,
                 f'FWHM = {fwhm*1000:.0f} MHz\n$\\Delta\\lambda$ = 50 pm',
                 ha='right', va='center', linespacing=1.8,
                 color='black')
        ax4.legend(loc='upper right')
        print(f"Calibration peak (dl=50 pm): f_peak = {f_peak:.3f} GHz, FWHM = {fwhm*1000:.1f} MHz")
    else:
        ax4.text(0.5, 0.5, 'Calibration file not found', transform=ax4.transAxes,
                 ha='center', va='center')

    ax4.set_xlabel('Frequency (GHz)')
    ax4.set_ylabel('RF Gain (dB)')
    ax4.set_xlim(2.3,10.2)
    ax4.set_ylim(-58, -31)
    add_subplot_label(ax4, '(d)')

    plt.tight_layout(pad=1.0, h_pad=1.5, w_pad=1.0)

    # Align y-axis labels across all subplots
    fig.align_ylabels(axes[:, 0])  # left column
    fig.align_ylabels(axes[:, 1])  # right column

    output_path = os.path.join(DATA_DIR, 'MRR_characterization.png')
    plt.savefig(output_path, dpi=200, bbox_inches='tight')
    print(f"\nFigure saved: {output_path}")
    plt.show()


if __name__ == '__main__':
    main()

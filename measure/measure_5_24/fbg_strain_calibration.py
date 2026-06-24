"""
FBG Strain Sensitivity Calibration Script
==========================================
Based on FBG reflection spectra at different strain levels,
extract center wavelength via Gaussian fitting and perform
linear regression to obtain strain sensitivity coefficient.

Measurement conditions:
- Initial fiber length: 120 mm (12 cm)
- Strain ε = ΔL / L
- Wavelength range: 1545–1555 nm
- Resolution: 100001 points (0.1 pm)
"""

import json
import os
import re
import numpy as np
from scipy.optimize import curve_fit
import matplotlib.pyplot as plt

import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'src'))
import plot_style

# ============================================================
# Data path
# ============================================================
DATA_DIR = r'C:\Users\ezhuzix\OneDrive - Ericsson\Desktop\WPF-FBG\measure\measure_5_24'

# Initial length in mm
L0 = 12.0  # 12 

# Initial micrometer reading (no strain, reference position)
INITIAL_READING = 5.225  # cm

# Files grouped by micrometer reading (mm)
# Multiple measurements per position are averaged for better accuracy
STRAIN_FILES = {
    5.230: ['FBG_5.230_1.json'],
    5.231: ['FBG_5.231_2.json'],
    5.232: ['FBG_5.232_2.json'],
    5.233: ['FBG_5.233_2.json'],
    5.234: ['FBG_5.234_2.json'],
    5.235: ['FBG_5.235_2.json'],
    5.236: ['FBG_5.236_2.json'],
    5.237: ['FBG_5.237_1.json'],
}


# ============================================================
# Helper functions
# ============================================================
def load_spectrum(filepath):
    """Load spectrum data from JSON file."""
    with open(filepath, 'r') as f:
        data = json.load(f)
    entry = data[0] if isinstance(data, list) else data
    wavelength = np.array(entry['rescaled_wavelength'])
    power = np.array(entry['rescaled_reference_power'])
    return wavelength, power


def gaussian(x, amp, center, sigma, offset):
    """Gaussian function model."""
    return amp * np.exp(-(x - center)**2 / (2 * sigma**2)) + offset


def find_peak_wavelength_gaussian(wavelength, power, window_pm=500):
    """
    Extract FBG center wavelength using Gaussian fitting.

    Parameters:
        wavelength: wavelength array (nm)
        power: power array (dBm)
        window_pm: fitting window width around peak (pm)

    Returns:
        center_wavelength, center_error, popt
    """
    peak_idx = np.argmax(power)
    peak_wl = wavelength[peak_idx]

    window_nm = window_pm / 1000.0
    mask = (wavelength >= peak_wl - window_nm) & (wavelength <= peak_wl + window_nm)
    wl_fit = wavelength[mask]
    pw_fit = power[mask]

    # Convert to linear scale (dBm -> mW)
    pw_linear = 10**(pw_fit / 10.0)

    amp_init = np.max(pw_linear) - np.min(pw_linear)
    center_init = peak_wl
    sigma_init = 0.1
    offset_init = np.min(pw_linear)

    try:
        popt, pcov = curve_fit(
            gaussian, wl_fit, pw_linear,
            p0=[amp_init, center_init, sigma_init, offset_init],
            maxfev=10000
        )
        center_wavelength = popt[1]
        perr = np.sqrt(np.diag(pcov))
        center_error = perr[1]
    except RuntimeError:
        weights = pw_linear - np.min(pw_linear)
        center_wavelength = np.average(wl_fit, weights=weights)
        center_error = 0.001
        popt = None

    return center_wavelength, center_error, popt


# ============================================================
# Main calibration
# ============================================================
def calibrate():
    """Execute FBG strain sensitivity calibration."""

    print("=" * 60)
    print("FBG Strain Sensitivity Calibration")
    print("=" * 60)
    print(f"Initial length L0 = {L0} cm")
    print(f"Initial reading = {INITIAL_READING} cm")

    readings = []
    delta_L_values = []  # mm
    strain_values = []   # με (microstrain)
    peak_wavelengths = []
    peak_errors = []
    all_spectra = {}

    for reading in sorted(STRAIN_FILES.keys()):
        files = STRAIN_FILES[reading]
        wl_peaks = []

        for fname in files:
            filepath = os.path.join(DATA_DIR, fname)
            if not os.path.exists(filepath):
                print(f"  Warning: file not found: {fname}")
                continue

            wavelength, power = load_spectrum(filepath)
            center, error, _ = find_peak_wavelength_gaussian(wavelength, power)
            wl_peaks.append(center)

        if wl_peaks:
            avg_peak = np.mean(wl_peaks)
            std_peak = np.std(wl_peaks) if len(wl_peaks) > 1 else 0.0001

            delta_L = reading - INITIAL_READING  # cm
            strain = (delta_L / L0) * 1e6  # microstrain (με)

            readings.append(reading)
            delta_L_values.append(delta_L)
            strain_values.append(strain)
            peak_wavelengths.append(avg_peak)
            peak_errors.append(std_peak)

            # Save representative spectrum (last file)
            last_file = files[-1]
            last_path = os.path.join(DATA_DIR, last_file)
            if os.path.exists(last_path):
                wavelength, power = load_spectrum(last_path)
                all_spectra[strain] = (wavelength, power)

            print(f"\n  Reading = {reading:.3f} cm, ΔL = {delta_L*10000:.0f} μm, "
                  f"ε = {strain:.2f} με:")
            print(f"    λ_B = {avg_peak:.6f} ± {std_peak:.6f} nm")
            print(f"    N measurements: {len(wl_peaks)}")

    strain_values = np.array(strain_values)
    peak_wavelengths = np.array(peak_wavelengths)
    peak_errors = np.array(peak_errors)

    # ============================================================
    # Linear regression: λ_B = λ_0 + k_ε * ε
    # ============================================================
    coeffs = np.polyfit(strain_values, peak_wavelengths, 1)
    sensitivity = coeffs[0]  # nm/με
    lambda_0 = coeffs[1]

    predicted = np.polyval(coeffs, strain_values)
    ss_res = np.sum((peak_wavelengths - predicted)**2)
    ss_tot = np.sum((peak_wavelengths - np.mean(peak_wavelengths))**2)
    r_squared = 1 - ss_res / ss_tot

    n = len(strain_values)
    se_slope = np.sqrt(ss_res / (n - 2)) / np.sqrt(np.sum((strain_values - np.mean(strain_values))**2))

    residuals = (peak_wavelengths - predicted) * 1000  # pm

    print("\n" + "=" * 60)
    print("Calibration Results")
    print("=" * 60)
    print(f"  Sensitivity: {sensitivity * 1000:.4f} ± {se_slope * 1000:.4f} pm/με")
    print(f"  Reference wavelength (0 με): {lambda_0:.6f} nm")
    print(f"  R-squared: {r_squared:.8f}")
    print(f"  Max residual: {np.max(np.abs(residuals)):.4f} pm")
    print(f"  RMS residual: {np.sqrt(np.mean(residuals**2)):.4f} pm")

    # ============================================================
    # Plot — Academic paper style
    # ============================================================
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))

    cmap = plt.cm.tab10
    colors = [cmap(i) for i in range(len(all_spectra))]

    # --- (a) FBG reflection spectra at different strains ---
    ax1 = axes[0]
    for i, (strain, (wl, pw)) in enumerate(sorted(all_spectra.items())):
        peak_idx = np.argmax(pw)
        peak_wl = wl[peak_idx]
        mask = (wl >= peak_wl - 0.8) & (wl <= peak_wl + 0.8)
        ax1.plot(wl[mask], pw[mask], color=colors[i], linewidth=1.5,
                 label=f'{strain:.1f} $\\mu\\varepsilon$')

    ax1.set_xlabel('Wavelength (nm)')
    ax1.set_ylabel('Power (dBm)')
    ax1.legend(loc='upper right')
    ax1.xaxis.set_major_locator(plt.MaxNLocator(5))
    plot_style.add_subplot_label(ax1, '(a)')

    # --- (b) Wavelength vs Strain ---
    ax2 = axes[1]
    ax2.plot(strain_values, peak_wavelengths, 'o', color=cmap(3),
             markersize=8, markeredgecolor='black', markeredgewidth=0.8,
             zorder=5, label='Measured data')
    s_fit = np.linspace(strain_values[0] - 5, strain_values[-1] + 5, 100)
    ax2.plot(s_fit, np.polyval(coeffs, s_fit), '-', color=cmap(0),
             linewidth=1.8,
             label=f'Linear fit ($k_\\varepsilon$={sensitivity*1000:.2f} pm/$\\mu\\varepsilon$)')

    ax2.set_xlabel('Strain ($\\mu\\varepsilon$)')
    ax2.set_ylabel('Wavelength (nm)')
    ax2.legend(loc='upper left')
    plot_style.add_subplot_label(ax2, '(b)')
    ax2.text(0.95, 0.08, f'$R^2$ = {r_squared:.6f}', transform=ax2.transAxes,
             ha='right', va='bottom')

    plt.tight_layout(pad=1.5)

    output_path = os.path.join(DATA_DIR, 'FBG_strain_calibration.png')
    plt.savefig(output_path, dpi=200, bbox_inches='tight')
    print(f"\nFigure saved: {output_path}")
    plt.show()

    # ============================================================
    # Save calibration results to JSON
    # ============================================================
    calibration_result = {
        "description": "FBG strain sensitivity calibration",
        "date": "2026-05-24",
        "initial_length_mm": L0,
        "strain_range_microstrain": [float(strain_values[0]), float(strain_values[-1])],
        "method": "Gaussian fit + linear regression",
        "sensitivity_pm_per_microstrain": round(sensitivity * 1000, 4),
        "sensitivity_uncertainty_pm_per_microstrain": round(se_slope * 1000, 4),
        "reference_wavelength_nm": round(float(lambda_0), 6),
        "R_squared": round(r_squared, 8),
        "max_residual_pm": round(float(np.max(np.abs(residuals))), 4),
        "rms_residual_pm": round(float(np.sqrt(np.mean(residuals**2))), 4),
        "calibration_data": [
            {
                "reading_mm": round(float(readings[i]), 3),
                "delta_L_mm": round(float(delta_L_values[i]), 4),
                "strain_microstrain": round(float(strain_values[i]), 2),
                "bragg_wavelength_nm": round(float(peak_wavelengths[i]), 6),
                "wavelength_std_nm": round(float(peak_errors[i]), 6),
                "residual_pm": round(float(residuals[i]), 4)
            }
            for i in range(n)
        ]
    }

    result_path = os.path.join(DATA_DIR, 'FBG_strain_calibration_result.json')
    with open(result_path, 'w', encoding='utf-8') as f:
        json.dump(calibration_result, f, ensure_ascii=False, indent=2)
    print(f"Result saved: {result_path}")

    return calibration_result


if __name__ == '__main__':
    result = calibrate()

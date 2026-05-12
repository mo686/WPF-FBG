"""
FBG温度灵敏度标定脚本
============================
基于不同温度下的FBG反射光谱测量数据，通过高斯拟合提取中心波长，
进行线性回归得到温度灵敏度系数。

测量条件：
- 温度范围：25°C ~ 50°C，步长5°C
- 波长范围：1545 ~ 1555 nm
- 分辨率：100001点（0.1 pm）
"""

import json
import os
import numpy as np
from scipy.optimize import curve_fit
import matplotlib.pyplot as plt

import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'src'))
import plot_style  # 学术论文绘图风格

# ============================================================
# 数据路径
# ============================================================
DATA_DIR = r'C:\Users\ezhuzix\OneDrive - Ericsson\Desktop\WPF-FBG\measure\measure_4_19'

# 温度和对应的数据文件
# 使用初始测量和长时间稳定后的测量取平均，提高精度
TEMP_FILES = {
    20: ['FBG_20_4h.json'],
    25: ['FBG_25.json', 'FBG_25_3h.json'],
    30: ['FBG_30.json', 'FBG_30_3h.json'],
    35: ['FBG_35.json', 'FBG_35_1h.json', 'FBG_35_2h.json'],
    40: ['FBG_40.json', 'FBG_40_1h.json', 'FBG_40_2h.json'],
    45: ['FBG_45.json', 'FBG_45_1h.json'],
    50: ['FBG_50.json', 'FBG_50_1h.json'],
}


# ============================================================
# 辅助函数
# ============================================================
def load_spectrum(filepath):
    """加载光谱数据"""
    with open(filepath, 'r') as f:
        data = json.load(f)
    entry = data[0]
    wavelength = np.array(entry['rescaled_wavelength'])
    power = np.array(entry['rescaled_reference_power'])
    return wavelength, power


def gaussian(x, amp, center, sigma, offset):
    """高斯函数模型"""
    return amp * np.exp(-(x - center)**2 / (2 * sigma**2)) + offset


def find_peak_wavelength_gaussian(wavelength, power, window_pm=500):
    """
    使用高斯拟合提取FBG中心波长

    Parameters:
        wavelength: 波长数组 (nm)
        power: 功率数组 (dBm)
        window_pm: 峰值附近拟合窗口宽度 (pm)

    Returns:
        center_wavelength: 高斯拟合中心波长 (nm)
        center_error: 拟合误差
        popt: 拟合参数
    """
    peak_idx = np.argmax(power)
    peak_wl = wavelength[peak_idx]

    window_nm = window_pm / 1000.0
    mask = (wavelength >= peak_wl - window_nm) & (wavelength <= peak_wl + window_nm)
    wl_fit = wavelength[mask]
    pw_fit = power[mask]

    # 转换为线性尺度 (dBm -> mW)
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


def find_peak_wavelength_centroid(wavelength, power, threshold_db=3):
    """使用质心法提取FBG中心波长"""
    peak_idx = np.argmax(power)
    peak_power = power[peak_idx]

    mask = power >= (peak_power - threshold_db)
    wl_sel = wavelength[mask]
    pw_sel = power[mask]

    pw_linear = 10**(pw_sel / 10.0)
    center_wavelength = np.sum(wl_sel * pw_linear) / np.sum(pw_linear)
    return center_wavelength


# ============================================================
# 主标定流程
# ============================================================
def calibrate():
    """执行FBG温度灵敏度标定"""

    print("=" * 60)
    print("FBG温度灵敏度标定")
    print("=" * 60)

    temperatures = []
    peak_wavelengths_gaussian = []
    peak_wavelengths_centroid = []
    peak_errors = []
    all_spectra = {}

    for temp in sorted(TEMP_FILES.keys()):
        files = TEMP_FILES[temp]
        wl_peaks_g = []
        wl_peaks_c = []

        for fname in files:
            filepath = os.path.join(DATA_DIR, fname)
            if not os.path.exists(filepath):
                continue

            wavelength, power = load_spectrum(filepath)
            center_g, error_g, _ = find_peak_wavelength_gaussian(wavelength, power)
            wl_peaks_g.append(center_g)

            center_c = find_peak_wavelength_centroid(wavelength, power)
            wl_peaks_c.append(center_c)

        if wl_peaks_g:
            avg_peak_g = np.mean(wl_peaks_g)
            std_peak_g = np.std(wl_peaks_g) if len(wl_peaks_g) > 1 else 0.0001
            avg_peak_c = np.mean(wl_peaks_c)

            temperatures.append(temp)
            peak_wavelengths_gaussian.append(avg_peak_g)
            peak_wavelengths_centroid.append(avg_peak_c)
            peak_errors.append(std_peak_g)

            # 保存代表性光谱（使用最后一个稳定测量）
            last_file = files[-1]
            last_path = os.path.join(DATA_DIR, last_file)
            if os.path.exists(last_path):
                wavelength, power = load_spectrum(last_path)
                all_spectra[temp] = (wavelength, power)

            print(f"\n  T = {temp} C:")
            print(f"    Gaussian: lambda_B = {avg_peak_g:.6f} +/- {std_peak_g:.6f} nm")
            print(f"    Centroid: lambda_B = {avg_peak_c:.6f} nm")
            print(f"    N measurements: {len(wl_peaks_g)}")

    temperatures = np.array(temperatures)
    peak_wavelengths_gaussian = np.array(peak_wavelengths_gaussian)
    peak_wavelengths_centroid = np.array(peak_wavelengths_centroid)
    peak_errors = np.array(peak_errors)

    # ============================================================
    # 线性回归: lambda_B = lambda_0 + alpha * T
    # ============================================================
    coeffs_g = np.polyfit(temperatures, peak_wavelengths_gaussian, 1)
    sensitivity_g = coeffs_g[0]  # nm/C
    lambda_0_g = coeffs_g[1]

    predicted_g = np.polyval(coeffs_g, temperatures)
    ss_res_g = np.sum((peak_wavelengths_gaussian - predicted_g)**2)
    ss_tot_g = np.sum((peak_wavelengths_gaussian - np.mean(peak_wavelengths_gaussian))**2)
    r_squared_g = 1 - ss_res_g / ss_tot_g

    coeffs_c = np.polyfit(temperatures, peak_wavelengths_centroid, 1)
    sensitivity_c = coeffs_c[0]
    lambda_0_c = coeffs_c[1]

    predicted_c = np.polyval(coeffs_c, temperatures)
    ss_res_c = np.sum((peak_wavelengths_centroid - predicted_c)**2)
    ss_tot_c = np.sum((peak_wavelengths_centroid - np.mean(peak_wavelengths_centroid))**2)
    r_squared_c = 1 - ss_res_c / ss_tot_c

    n = len(temperatures)
    se_slope_g = np.sqrt(ss_res_g / (n - 2)) / np.sqrt(np.sum((temperatures - np.mean(temperatures))**2))

    residuals_g = (peak_wavelengths_gaussian - predicted_g) * 1000  # pm

    lambda_ref_25 = lambda_0_g + sensitivity_g * 25

    print("\n" + "=" * 60)
    print("Calibration Results")
    print("=" * 60)
    print(f"  Sensitivity: {sensitivity_g * 1000:.4f} +/- {se_slope_g * 1000:.4f} pm/C")
    print(f"  Reference wavelength (25C): {lambda_ref_25:.6f} nm")
    print(f"  R-squared: {r_squared_g:.8f}")
    print(f"  Max residual: {np.max(np.abs(residuals_g)):.4f} pm")
    print(f"  RMS residual: {np.sqrt(np.mean(residuals_g**2)):.4f} pm")
    print(f"  Temperature error: +/-{np.max(np.abs(residuals_g)) / (sensitivity_g * 1000):.4f} C")


    # ============================================================
    # 绘图 — 学术论文风格 (白底、无网格、粗体子图标签)
    # ============================================================
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))

    cmap = plt.cm.tab10
    colors = [cmap(i) for i in range(len(all_spectra))]

    # --- (a) FBG reflection spectra at different temperatures ---
    ax1 = axes[0]
    for i, (temp, (wl, pw)) in enumerate(sorted(all_spectra.items())):
        peak_idx = np.argmax(pw)
        peak_wl = wl[peak_idx]
        mask = (wl >= peak_wl - 0.8) & (wl <= peak_wl + 0.8)
        ax1.plot(wl[mask], pw[mask], color=colors[i], linewidth=1.5,
                 label=f'{temp}$^\\circ$C')

    ax1.set_xlabel('Wavelength (nm)')
    ax1.set_ylabel('Loss (dB)')
    ax1.legend(loc='upper right')
    ax1.xaxis.set_major_locator(plt.MaxNLocator(5))
    plot_style.add_subplot_label(ax1, '(a)')

    # --- (b) Wavelength vs Temperature ---
    ax2 = axes[1]
    ax2.plot(temperatures, peak_wavelengths_gaussian, 'o', color=cmap(3),
             markersize=8, markeredgecolor='black', markeredgewidth=0.8,
             zorder=5, label='Measured data')
    t_fit = np.linspace(temperatures[0] - 3, temperatures[-1] + 3, 100)
    ax2.plot(t_fit, np.polyval(coeffs_g, t_fit), '-', color=cmap(0),
             linewidth=1.8,
             label=f'Linear fit ($\\alpha$={sensitivity_g*1000:.2f} pm/$^\\circ$C)')

    ax2.set_xlabel('Temperature ($^\\circ$C)')
    ax2.set_ylabel('Wavelength (nm)')
    ax2.legend(loc='upper left')
    plot_style.add_subplot_label(ax2, '(b)')
    ax2.text(0.95, 0.08, f'$R^2$ = {r_squared_g:.6f}', transform=ax2.transAxes,
             ha='right', va='bottom')

    plt.tight_layout(pad=1.5)

    output_path = os.path.join(DATA_DIR, 'FBG_temperature_calibration.png')
    plt.savefig(output_path, dpi=200, bbox_inches='tight')
    print(f"\nFigure saved: {output_path}")
    plt.show()


    # ============================================================
    # 保存标定结果到JSON
    # ============================================================
    calibration_result = {
        "description": "FBG temperature sensitivity calibration",
        "date": "2026-04-19",
        "temperature_range_C": [int(temperatures[0]), int(temperatures[-1])],
        "method": "Gaussian fit + linear regression",
        "sensitivity_pm_per_C": round(sensitivity_g * 1000, 4),
        "sensitivity_uncertainty_pm_per_C": round(se_slope_g * 1000, 4),
        "reference_wavelength_nm_at_25C": round(lambda_ref_25, 6),
        "lambda_0_nm": round(lambda_0_g, 6),
        "R_squared": round(r_squared_g, 8),
        "max_residual_pm": round(float(np.max(np.abs(residuals_g))), 4),
        "rms_residual_pm": round(float(np.sqrt(np.mean(residuals_g**2))), 4),
        "temperature_resolution_C": round(float(np.sqrt(np.mean(residuals_g**2))) / (sensitivity_g * 1000), 4),
        "calibration_data": [
            {
                "temperature_C": int(t),
                "bragg_wavelength_nm": round(float(wl), 6),
                "wavelength_std_nm": round(float(err), 6),
                "residual_pm": round(float(res), 4)
            }
            for t, wl, err, res in zip(
                temperatures, peak_wavelengths_gaussian, peak_errors, residuals_g
            )
        ]
    }

    result_path = os.path.join(DATA_DIR, 'FBG_calibration_result.json')
    with open(result_path, 'w', encoding='utf-8') as f:
        json.dump(calibration_result, f, ensure_ascii=False, indent=2)
    print(f"Result saved: {result_path}")

    return calibration_result


if __name__ == '__main__':
    result = calibrate()

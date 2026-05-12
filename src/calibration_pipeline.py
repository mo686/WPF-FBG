"""
光纤传感定标数据处理流水线。

纯数据处理模块，独立于仪器控制层。
接收 CSV 文件作为输入，输出匹配结果和温度计算值。
"""

from __future__ import annotations

import bisect
import os
import re
import warnings
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.interpolate import interp1d


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------

@dataclass
class S21Curve:
    """S21 频率响应曲线"""
    frequency: np.ndarray   # GHz
    magnitude: np.ndarray   # dB


@dataclass
class CalibrationEntry:
    """定标表单条记录"""
    delta_lambda: float     # pm
    fpeak: float            # GHz
    curve: S21Curve


@dataclass
class MatchResult:
    """单条曲线匹配结果"""
    cal_index: int          # 最佳匹配的定标曲线索引
    rho: float              # 归一化互相关系数
    delta_lambda: float     # 对应的波长偏移 (pm)


@dataclass
class PipelineResult:
    """流水线最终输出"""
    best_voltage: float                     # 最佳电压 (V)
    best_cal_index: int                     # 最佳定标曲线索引
    rho_max: float                          # 最大归一化互相关系数
    delta_lambda: float                     # 波长偏移 (pm)
    lambda_fbg: float                       # FBG 中心波长 (nm)
    temperature: float                      # 计算温度 (°C)
    all_match_results: list[MatchResult] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 定标映射表
# ---------------------------------------------------------------------------

class CalibrationTable:
    """
    定标映射表，按 fpeak 升序存储。
    支持通过 fpeak 范围查询候选曲线。
    """

    def __init__(self, entries: list[CalibrationEntry]) -> None:
        self.entries: list[CalibrationEntry] = sorted(
            entries, key=lambda e: e.fpeak
        )
        # 预提取 fpeak 列表，供二分查找使用
        self._fpeaks: list[float] = [e.fpeak for e in self.entries]

    def __len__(self) -> int:
        return len(self.entries)

    def filter_by_sign(self, sign: str) -> "CalibrationTable":
        """返回只包含指定符号 Δλ 的子表。

        Parameters:
            sign: "positive" (Δλ > 0), "negative" (Δλ < 0), "all" (不过滤)
        """
        if sign == "positive":
            filtered = [e for e in self.entries if e.delta_lambda > 0]
        elif sign == "negative":
            filtered = [e for e in self.entries if e.delta_lambda < 0]
        else:
            return self
        if not filtered:
            return self  # 如果过滤后为空，返回原表
        return CalibrationTable(filtered)

    def query_by_fpeak(
        self,
        fpeak: float,
        k: int = 3,
        threshold: float | None = None,
    ) -> list[int]:
        """
        返回与给定 fpeak 最接近的前 k 条记录的索引。
        若指定 threshold，仅返回差值 < threshold 的记录。
        使用 bisect 进行高效查找。
        """
        if not self._fpeaks:
            return []

        pos = bisect.bisect_left(self._fpeaks, fpeak)
        candidates: list[int] = []
        left, right = pos - 1, pos

        while len(candidates) < k and (left >= 0 or right < len(self._fpeaks)):
            ld = abs(self._fpeaks[left] - fpeak) if left >= 0 else float('inf')
            rd = abs(self._fpeaks[right] - fpeak) if right < len(self._fpeaks) else float('inf')

            if ld <= rd:
                if threshold is None or ld < threshold:
                    candidates.append(left)
                left -= 1
            else:
                if threshold is None or rd < threshold:
                    candidates.append(right)
                right += 1

            # 如果两侧都超出 threshold，提前退出
            if threshold is not None and ld >= threshold and rd >= threshold:
                break

        return candidates


# ---------------------------------------------------------------------------
# 数据加载
# ---------------------------------------------------------------------------

# 支持的列名映射：(频率列, 幅度列)
_COLUMN_MAPS: list[tuple[str, str]] = [
    ("Frequency_Hz", "Magnitude_dB"),
    ("frequency", "magnitude_dB"),
]


def load_s21_curve(filepath: str) -> S21Curve:
    """
    从 CSV 文件加载一条 S21 曲线。

    支持列名: Frequency_Hz/Magnitude_dB 或 frequency/magnitude_dB。
    频率自动从 Hz 转换为 GHz。

    Raises:
        FileNotFoundError: 文件不存在
        ValueError: 缺少必需列
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {filepath}")

    df = pd.read_csv(filepath)

    freq_col: str | None = None
    mag_col: str | None = None
    for fc, mc in _COLUMN_MAPS:
        if fc in df.columns and mc in df.columns:
            freq_col, mag_col = fc, mc
            break

    if freq_col is None or mag_col is None:
        raise ValueError(
            f"CSV 缺少必需列。需要 (Frequency_Hz, Magnitude_dB) 或 "
            f"(frequency, magnitude_dB)，实际列: {list(df.columns)}"
        )

    frequency = df[freq_col].to_numpy(dtype=float) / 1e9  # Hz → GHz
    magnitude = df[mag_col].to_numpy(dtype=float)
    return S21Curve(frequency=frequency, magnitude=magnitude)


def load_curves_from_directory(
    directory: str,
    metadata_key: str = "voltage",
) -> list[tuple[float, S21Curve]]:
    """
    批量加载目录下所有 CSV 文件。

    从文件名提取元数据值（电压或波长偏移）。
    文件名中的第一个数值（含可选负号和小数点）被视为元数据值。

    Returns:
        (metadata_value, S21Curve) 列表，按元数据值升序排列。
    """
    dir_path = Path(directory)
    if not dir_path.is_dir():
        raise FileNotFoundError(f"目录不存在: {directory}")

    results: list[tuple[float, S21Curve]] = []
    csv_files = sorted(dir_path.glob("*.csv"))

    for csv_file in csv_files:
        # 从文件名提取数值
        match = re.search(r"(-?\d+\.?\d*)", csv_file.stem)
        if match is None:
            continue  # 跳过无法提取元数据的文件
        metadata_value = float(match.group(1))
        curve = load_s21_curve(str(csv_file))
        results.append((metadata_value, curve))

    results.sort(key=lambda x: x[0])
    return results


# ---------------------------------------------------------------------------
# 频率轴插值对齐
# ---------------------------------------------------------------------------


def interpolate_to_common_grid(
    curve_a: S21Curve,
    curve_b: S21Curve,
    freq_step: float = 0.01,
) -> tuple[S21Curve, S21Curve]:
    """
    将两条曲线插值到公共频率网格。

    频率范围为两条曲线频率轴的交集，步长默认 0.01 GHz。
    使用 scipy.interpolate.interp1d 线性插值。

    Raises:
        ValueError: 频率范围无重叠
    """
    f_min = max(curve_a.frequency[0], curve_b.frequency[0])
    f_max = min(curve_a.frequency[-1], curve_b.frequency[-1])

    if f_min >= f_max:
        raise ValueError(
            f"频率范围无重叠: 曲线A [{curve_a.frequency[0]:.4f}, "
            f"{curve_a.frequency[-1]:.4f}] GHz, "
            f"曲线B [{curve_b.frequency[0]:.4f}, "
            f"{curve_b.frequency[-1]:.4f}] GHz"
        )

    common_freq = np.arange(f_min, f_max, freq_step)
    # 确保至少有一个频率点
    if len(common_freq) == 0:
        common_freq = np.array([f_min])

    interp_a = interp1d(curve_a.frequency, curve_a.magnitude, kind="linear")
    interp_b = interp1d(curve_b.frequency, curve_b.magnitude, kind="linear")

    return (
        S21Curve(frequency=common_freq, magnitude=interp_a(common_freq)),
        S21Curve(frequency=common_freq, magnitude=interp_b(common_freq)),
    )


# ---------------------------------------------------------------------------
# 峰值频率提取
# ---------------------------------------------------------------------------


def extract_peak(curve: S21Curve, smooth_window: int = 5) -> float:
    """
    对 S21 曲线执行移动平均平滑后提取峰值频率。

    使用 numpy.convolve 实现均匀移动平均。
    若数据点数 < smooth_window，跳过平滑。
    多个相同最大值时返回第一个对应频率。

    Returns:
        fpeak (GHz)
    """
    freq = curve.frequency
    mag = curve.magnitude

    if len(mag) >= smooth_window:
        kernel = np.ones(smooth_window) / smooth_window
        smoothed = np.convolve(mag, kernel, mode="valid")
        # mode='valid' 缩短数组，对应调整频率：取中间段
        offset = (smooth_window - 1) // 2
        freq = freq[offset : offset + len(smoothed)]
        mag = smoothed

    peak_idx = int(np.argmax(mag))
    return float(freq[peak_idx])


# ---------------------------------------------------------------------------
# 定标映射表构建
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 曲线匹配
# ---------------------------------------------------------------------------


def normalized_cross_correlation(a: np.ndarray, b: np.ndarray) -> float:
    """
    计算两个等长一维数组的归一化互相关系数。

    ρ = Σ((a-ā)(b-b̄)) / (n·σ_a·σ_b)
    若任一数组标准差为 0，返回 0.0。
    """
    a_centered = a - np.mean(a)
    b_centered = b - np.mean(b)
    numerator = np.sum(a_centered * b_centered)
    denominator = len(a) * np.std(a) * np.std(b)
    if denominator == 0:
        return 0.0
    return float(numerator / denominator)


def _normalize_minmax(arr: np.ndarray) -> np.ndarray:
    """Min-max 归一化到 [0, 1]。若 max==min 返回全零。"""
    mn, mx = np.min(arr), np.max(arr)
    if mx == mn:
        return np.zeros_like(arr)
    return (arr - mn) / (mx - mn)


def match_curve(
    measured: S21Curve,
    table: CalibrationTable,
    k_cand: int = 3,
    freq_threshold: float | None = None,
    freq_step: float = 0.01,
    smooth_window: int = 5,
    corr_bandwidth: float | None = None,
    match_mode: str = "correlation",
) -> MatchResult:
    """
    将一条实测曲线与定标表匹配。

    Parameters:
        match_mode:
            - "correlation": 归一化互相关（原始方式）
            - "fpeak_nearest": 仅用峰值频率最近邻，不看幅度
            - "normalized_shape": 先 min-max 归一化消除幅度差异，再算互相关
            - "fpeak_fit": 对峰值附近做洛伦兹拟合提取精确 f0，
              用拟合 f0 匹配并插值得到 Δλ
        corr_bandwidth: 峰值附近频率半宽 (GHz)，用于 correlation/normalized_shape/fpeak_fit 模式。

    Raises:
        ValueError: 无候选曲线满足条件
    """
    meas_fpeak = extract_peak(measured, smooth_window)
    candidates = table.query_by_fpeak(meas_fpeak, k=k_cand, threshold=freq_threshold)

    if not candidates:
        cal_fpeaks = [e.fpeak for e in table.entries]
        cal_range = f"[{min(cal_fpeaks):.4f}, {max(cal_fpeaks):.4f}]" if cal_fpeaks else "空"
        raise ValueError(
            f"无候选曲线满足条件: 实测 fpeak={meas_fpeak:.4f} GHz, "
            f"定标范围 {cal_range} GHz"
        )

    # fpeak 最近邻模式
    if match_mode == "fpeak_nearest":
        best_idx = candidates[0]
        fpeak_diff = abs(table.entries[best_idx].fpeak - meas_fpeak)
        rho = 1.0 / (1.0 + fpeak_diff)
        return MatchResult(
            cal_index=best_idx,
            rho=rho,
            delta_lambda=table.entries[best_idx].delta_lambda,
        )

    # fpeak 拟合匹配模式：对每条曲线的峰值附近做洛伦兹拟合，
    # 用拟合得到的精确中心频率 f0 进行匹配
    if match_mode == "fpeak_fit":
        from scipy.optimize import curve_fit as _curve_fit

        def _lorentzian(f, f0, gamma, A, offset):
            """对称洛伦兹: A / (1 + ((f-f0)/γ)²) + offset"""
            return A / (1.0 + ((f - f0) / gamma) ** 2) + offset

        def _asym_lorentzian(f, f0, gamma, A, offset, asym):
            """非对称洛伦兹 (Fano): 加线性不对称项"""
            x = (f - f0) / gamma
            return A * (1.0 + asym * x) / (1.0 + x ** 2) + offset

        def _lorentzian_linear(f, f0, gamma, A, offset, slope):
            """洛伦兹 + 线性背景"""
            return A / (1.0 + ((f - f0) / gamma) ** 2) + offset + slope * (f - f0)

        def _gaussian(f, f0, sigma, A, offset):
            """高斯: A * exp(-((f-f0)/σ)²/2) + offset"""
            return A * np.exp(-0.5 * ((f - f0) / sigma) ** 2) + offset

        def _estimate_3db_halfwidth(freq, mag, peak_idx):
            """估算 3dB 半宽。"""
            peak_val = mag[peak_idx]
            threshold = peak_val - 3.0
            right_hw = 0.0
            for j in range(peak_idx + 1, len(mag)):
                if mag[j] <= threshold:
                    right_hw = freq[j] - freq[peak_idx]
                    break
            else:
                right_hw = (freq[-1] - freq[peak_idx]) / 4
            left_hw = 0.0
            for j in range(peak_idx - 1, -1, -1):
                if mag[j] <= threshold:
                    left_hw = freq[peak_idx] - freq[j]
                    break
            else:
                left_hw = (freq[peak_idx] - freq[0]) / 4
            return max((left_hw + right_hw) / 2, 0.001)

        def _fit_f0(curve: S21Curve, bw: float | None) -> float:
            """对峰值附近尝试多种模型拟合，选残差最小的，返回 f0。

            模型优先级：非对称洛伦兹 > 洛伦兹+线性背景 > 对称洛伦兹 > 高斯
            """
            freq = curve.frequency
            mag = curve.magnitude
            rough_peak_idx = int(np.argmax(mag))
            f_peak_rough = freq[rough_peak_idx]

            if bw is not None and bw > 0:
                half_bw = bw
            else:
                hw_3db = _estimate_3db_halfwidth(freq, mag, rough_peak_idx)
                half_bw = hw_3db * 3.0

            mask = (freq >= f_peak_rough - half_bw) & (freq <= f_peak_rough + half_bw)
            f_region = freq[mask]
            m_region = mag[mask]
            if len(f_region) < 5:
                return f_peak_rough

            gamma_init = half_bw / 3.0
            amp = float(np.max(m_region) - np.min(m_region))
            base = float(np.min(m_region))

            # 尝试多种模型，选残差最小的
            best_f0 = f_peak_rough
            best_sse = float("inf")

            models = [
                (_lorentzian, [f_peak_rough, gamma_init, amp, base]),
                (_lorentzian_linear, [f_peak_rough, gamma_init, amp, base, 0.0]),
                (_asym_lorentzian, [f_peak_rough, gamma_init, amp, base, 0.0]),
                (_gaussian, [f_peak_rough, gamma_init, amp, base]),
            ]

            for func, p0 in models:
                try:
                    popt, _ = _curve_fit(
                        func, f_region, m_region, p0=p0,
                        maxfev=10000,
                        bounds=(
                            [f_region[0], 1e-6, -np.inf, -np.inf] + [-np.inf] * (len(p0) - 4),
                            [f_region[-1], half_bw * 2, np.inf, np.inf] + [np.inf] * (len(p0) - 4),
                        ),
                    )
                    fitted = func(f_region, *popt)
                    sse = float(np.sum((m_region - fitted) ** 2))
                    if sse < best_sse:
                        best_sse = sse
                        best_f0 = float(popt[0])
                except Exception:
                    continue

            return best_f0

        # 对实测曲线拟合
        meas_f0 = _fit_f0(measured, corr_bandwidth)

        # 对每条候选定标曲线拟合，找 f0 最接近的
        best_idx = -1
        best_diff = float("inf")
        cal_f0s = {}
        for idx in candidates:
            entry = table.entries[idx]
            cal_f0 = _fit_f0(entry.curve, corr_bandwidth)
            cal_f0s[idx] = cal_f0
            diff = abs(cal_f0 - meas_f0)
            if diff < best_diff:
                best_diff = diff
                best_idx = idx

        if best_idx < 0:
            best_idx = candidates[0]

        # 用 1/(1+diff) 作为匹配质量指标
        rho = 1.0 / (1.0 + best_diff)

        # 如果有足够的定标点，用拟合的 f0-Δλ 关系插值得到更精确的 Δλ
        all_f0s = []
        all_dls = []
        for idx_i, entry in enumerate(table.entries):
            if idx_i in cal_f0s:
                all_f0s.append(cal_f0s[idx_i])
            else:
                all_f0s.append(entry.fpeak)  # 未拟合的用粗略值
            all_dls.append(entry.delta_lambda)
        all_f0s = np.array(all_f0s)
        all_dls = np.array(all_dls)
        # 线性插值 f0 → Δλ
        sort_idx = np.argsort(all_f0s)
        all_f0s_sorted = all_f0s[sort_idx]
        all_dls_sorted = all_dls[sort_idx]
        if len(all_f0s_sorted) >= 2:
            fitted_dl = float(np.interp(meas_f0, all_f0s_sorted, all_dls_sorted))
        else:
            fitted_dl = table.entries[best_idx].delta_lambda

        return MatchResult(
            cal_index=best_idx,
            rho=rho,
            delta_lambda=fitted_dl,
        )

    # correlation / normalized_shape 模式
    best_idx = -1
    best_rho = -float("inf")

    for idx in candidates:
        entry = table.entries[idx]
        try:
            aligned_meas, aligned_cal = interpolate_to_common_grid(
                measured, entry.curve, freq_step
            )
        except ValueError:
            continue

        mag_m = aligned_meas.magnitude
        mag_c = aligned_cal.magnitude

        # 峰值附近频率窗口
        if corr_bandwidth is not None and corr_bandwidth > 0:
            freq = aligned_meas.frequency
            mask = (freq >= meas_fpeak - corr_bandwidth) & (freq <= meas_fpeak + corr_bandwidth)
            if np.sum(mask) >= 2:
                mag_m = mag_m[mask]
                mag_c = mag_c[mask]

        # normalized_shape: 先 min-max 归一化消除幅度差异
        if match_mode == "normalized_shape":
            mag_m = _normalize_minmax(mag_m)
            mag_c = _normalize_minmax(mag_c)

        rho = normalized_cross_correlation(mag_m, mag_c)
        if rho > best_rho:
            best_rho = rho
            best_idx = idx

    if best_idx < 0:
        raise ValueError(
            f"无候选曲线满足条件: 所有候选曲线与实测曲线频率范围无重叠"
        )

    return MatchResult(
        cal_index=best_idx,
        rho=best_rho,
        delta_lambda=table.entries[best_idx].delta_lambda,
    )


# ---------------------------------------------------------------------------
# 定标映射表构建
# ---------------------------------------------------------------------------


def build_calibration_table(
    curves: list[tuple[float, S21Curve]],
    smooth_window: int = 5,
) -> CalibrationTable:
    """
    从 (Δλ, S21Curve) 列表构建定标表。

    对每条曲线提取 fpeak，按 fpeak 升序排列。

    Raises:
        ValueError: 曲线列表为空
    """
    if not curves:
        raise ValueError("需要至少一条定标曲线")

    entries = [
        CalibrationEntry(
            delta_lambda=delta_lambda,
            fpeak=extract_peak(curve, smooth_window),
            curve=curve,
        )
        for delta_lambda, curve in curves
    ]

    return CalibrationTable(entries)


# ---------------------------------------------------------------------------
# 全局最佳选择与温度计算
# ---------------------------------------------------------------------------


def find_best_voltage(
    measured_curves: list[tuple[float, S21Curve]],
    table: CalibrationTable,
    k_cand: int = 3,
    freq_step: float = 0.01,
    smooth_window: int = 5,
    corr_bandwidth: float | None = None,
    match_mode: str = "correlation",
) -> tuple[float, int, float, list[MatchResult]]:
    """
    对所有实测曲线执行匹配，返回最佳电压。

    Parameters:
        match_mode: "correlation" / "fpeak_nearest" / "normalized_shape"
        corr_bandwidth: 峰值附近频率半宽 (GHz)。

    Returns:
        (best_voltage, best_cal_index, best_rho, all_results)
    """
    all_results: list[MatchResult] = []

    for _voltage, curve in measured_curves:
        result = match_curve(
            measured=curve,
            table=table,
            k_cand=k_cand,
            freq_step=freq_step,
            smooth_window=smooth_window,
            corr_bandwidth=corr_bandwidth,
            match_mode=match_mode,
        )
        all_results.append(result)

    best_idx = max(range(len(all_results)), key=lambda i: all_results[i].rho)
    best_result = all_results[best_idx]
    best_voltage = measured_curves[best_idx][0]

    if all(r.rho < 0.5 for r in all_results):
        warnings.warn("匹配质量较低: 所有实测曲线的 ρ_max 均低于 0.5")

    return best_voltage, best_result.cal_index, best_result.rho, all_results


def calculate_temperature(
    delta_lambda: float,
    lambda_ref: float = 1550.0,
    lambda_meas: float | None = None,
    alpha: float = 9.08,
    t0: float = 20.0,
) -> dict:
    """
    根据波长偏移计算温度。

    Δλ* = (λ_meas - λ_ref) * 1000 + Δλ_k   (pm)
    当 λ_meas = λ_ref 时，Δλ* = Δλ_k

    λ_FBG = λ_ref + Δλ*/1000（pm 转 nm）
    ΔT = Δλ* / α
    T = T0 + ΔT

    Parameters:
        delta_lambda: Δλ_k, 匹配到的定标曲线对应的波长偏移 (pm)
        lambda_ref: 定标参考波长 (nm)
        lambda_meas: 测量时激光器实际波长 (nm)，为 None 时视为等于 lambda_ref
        alpha: FBG 温度灵敏度系数 (pm/°C)
        t0: 基准温度 (°C)

    Returns:
        {'lambda_fbg': float, 'delta_lambda': float,
         'delta_t': float, 'temperature': float}
    """
    # Δλ* = (λ_meas - λ_ref) + Δλ_k
    if lambda_meas is None:
        lambda_meas = lambda_ref
    delta_lambda_star = (lambda_meas - lambda_ref) * 1000.0 + delta_lambda

    lambda_fbg = lambda_ref + delta_lambda_star / 1000.0
    delta_t = delta_lambda_star / alpha
    temperature = t0 + delta_t

    return {
        "lambda_fbg": lambda_fbg,
        "delta_lambda": delta_lambda_star,
        "delta_t": delta_t,
        "temperature": temperature,
    }


# ---------------------------------------------------------------------------
# 结果输出与可视化
# ---------------------------------------------------------------------------


def plot_comparison(
    measured: S21Curve,
    calibration: S21Curve,
    voltage: float,
    delta_lambda: float,
    rho: float,
    save_path: str | None = None,
) -> None:
    """
    绘制实测曲线与最佳匹配定标曲线的对比图。

    包含图例标注、轴标签（频率 GHz / 幅度 dB）、不同颜色区分。
    若指定 save_path 则保存图片，否则显示。
    """
    import matplotlib.pyplot as plt
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    import plot_style  # 学术论文绘图风格

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(
        measured.frequency,
        measured.magnitude,
        color="tab:blue",
        label=f"Measured (V={voltage:.2f} V)",
    )
    ax.plot(
        calibration.frequency,
        calibration.magnitude,
        color="tab:red",
        linestyle="--",
        label=f"Calibration ($\\Delta\\lambda$={delta_lambda:.1f} pm)",
    )
    ax.set_xlabel("Frequency (GHz)")
    ax.set_ylabel("Magnitude (dB)")
    ax.set_title(f"Curve Matching  $\\rho$={rho:.4f}")
    ax.legend()
    fig.tight_layout()

    if save_path is not None:
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_path, dpi=150)
    else:
        plt.show()
    plt.close(fig)


def save_results_csv(
    results: list[MatchResult],
    voltages: list[float],
    filepath: str,
) -> None:
    """
    将所有实测曲线的匹配结果保存为 CSV。

    列: voltage, rho_max, delta_lambda, cal_index
    """
    df = pd.DataFrame(
        {
            "voltage": voltages,
            "rho_max": [r.rho for r in results],
            "delta_lambda": [r.delta_lambda for r in results],
            "cal_index": [r.cal_index for r in results],
        }
    )
    Path(filepath).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(filepath, index=False)


# ---------------------------------------------------------------------------
# 端到端流水线入口
# ---------------------------------------------------------------------------


def run_pipeline(
    cal_directory: str,
    meas_directory: str,
    alpha: float = 9.08,
    t0: float = 20.0,
    lambda_ref: float = 1550.0,
    k_cand: int = 3,
    freq_step: float = 0.01,
    smooth_window: int = 5,
    plot: bool = False,
    output_csv: str | None = None,
) -> PipelineResult:
    """
    端到端流水线入口。

    按顺序执行：加载定标数据 → 建立定标表 → 加载测量数据
    → 逐条匹配 → 全局最佳选择 → 温度计算 → 控制台输出。

    可选绘图和 CSV 导出。各阶段异常附带阶段名称前缀。

    Raises:
        各阶段异常附带阶段名称
    """
    # 1. 加载定标数据
    try:
        cal_curves = load_curves_from_directory(cal_directory, metadata_key="delta_lambda")
    except Exception as e:
        raise type(e)(f"[加载定标数据] {e}") from e

    # 2. 建立定标表
    try:
        table = build_calibration_table(cal_curves, smooth_window=smooth_window)
    except Exception as e:
        raise type(e)(f"[建立定标表] {e}") from e

    # 3. 加载测量数据
    try:
        meas_curves = load_curves_from_directory(meas_directory, metadata_key="voltage")
    except Exception as e:
        raise type(e)(f"[加载测量数据] {e}") from e

    # 4. 逐条匹配 → 全局最佳选择
    try:
        best_voltage, best_cal_index, best_rho, all_results = find_best_voltage(
            measured_curves=meas_curves,
            table=table,
            k_cand=k_cand,
            freq_step=freq_step,
            smooth_window=smooth_window,
        )
    except Exception as e:
        raise type(e)(f"[曲线匹配] {e}") from e

    # 5. 温度计算
    try:
        best_delta_lambda = table.entries[best_cal_index].delta_lambda
        temp_result = calculate_temperature(
            delta_lambda=best_delta_lambda,
            lambda_ref=lambda_ref,
            alpha=alpha,
            t0=t0,
        )
    except Exception as e:
        raise type(e)(f"[温度计算] {e}") from e

    # 6. 构建最终结果
    result = PipelineResult(
        best_voltage=best_voltage,
        best_cal_index=best_cal_index,
        rho_max=best_rho,
        delta_lambda=best_delta_lambda,
        lambda_fbg=temp_result["lambda_fbg"],
        temperature=temp_result["temperature"],
        all_match_results=all_results,
    )

    # 7. 控制台输出
    print(f"最佳匹配电压: {result.best_voltage:.2f} V")
    print(f"波长偏移 Δλ: {result.delta_lambda:.2f} pm")
    print(f"计算温度 T: {result.temperature:.2f} °C")
    print(f"匹配相关系数 ρ_max: {result.rho_max:.4f}")

    # 8. 可选绘图
    if plot:
        try:
            best_meas_curve = next(
                curve for v, curve in meas_curves if v == best_voltage
            )
            best_cal_curve = table.entries[best_cal_index].curve
            plot_comparison(
                measured=best_meas_curve,
                calibration=best_cal_curve,
                voltage=best_voltage,
                delta_lambda=best_delta_lambda,
                rho=best_rho,
            )
        except Exception as e:
            raise type(e)(f"[绘图] {e}") from e

    # 9. 可选 CSV 导出
    if output_csv is not None:
        try:
            voltages = [v for v, _ in meas_curves]
            save_results_csv(all_results, voltages, output_csv)
        except Exception as e:
            raise type(e)(f"[CSV 导出] {e}") from e

    return result

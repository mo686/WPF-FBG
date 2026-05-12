"""Spectrum_Panel — 光谱分析面板

提供 CSV 光谱数据加载、功率-波长曲线绘制、
分析参数配置（平滑系数、峰值检测阈值、最小消光比等），
调用 spectrum_analyzer 模块计算 6 项指标并在图表上标注峰值/谷值。
"""

import csv
import logging
from typing import Optional

import numpy as np
from PySide6.QtCore import Slot
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.ui.chart_widget import ChartWidget
from src.ui.log_console import LogConsole
from src import spectrum_analyzer

logger = logging.getLogger(__name__)


class SpectrumPanel(QWidget):
    """光谱分析面板。"""

    def __init__(
        self,
        log_console: LogConsole,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._log = log_console
        self._wavelengths: Optional[np.ndarray] = None
        self._power_data: Optional[np.ndarray] = None
        self._analysis_result: Optional[dict] = None

        self._init_ui()

    # ==================================================================
    # UI 构建
    # ==================================================================

    def _init_ui(self):
        main_layout = QHBoxLayout(self)

        # --- 左侧：文件加载 + 参数 + 按钮 + 结果 ---
        left = QVBoxLayout()

        # 文件加载组
        file_group = QGroupBox("数据文件")
        file_layout = QVBoxLayout()
        self.btn_load = QPushButton("加载 CSV 文件")
        self.file_label = QLabel("未加载文件")
        self.file_label.setWordWrap(True)
        file_layout.addWidget(self.btn_load)
        file_layout.addWidget(self.file_label)
        file_group.setLayout(file_layout)
        left.addWidget(file_group)

        # 分析参数组
        param_group = QGroupBox("分析参数")
        form = QFormLayout()

        self.smooth_sigma = QDoubleSpinBox()
        self.smooth_sigma.setRange(0.0, 50.0)
        self.smooth_sigma.setDecimals(1)
        self.smooth_sigma.setValue(1.0)
        self.smooth_sigma.setSingleStep(0.5)
        form.addRow("平滑系数 (σ):", self.smooth_sigma)

        self.peak_height_pct = QDoubleSpinBox()
        self.peak_height_pct.setRange(0.0, 100.0)
        self.peak_height_pct.setDecimals(0)
        self.peak_height_pct.setValue(70.0)
        self.peak_height_pct.setSingleStep(5.0)
        form.addRow("峰值高度百分位:", self.peak_height_pct)

        self.peak_prominence = QDoubleSpinBox()
        self.peak_prominence.setRange(0.0, 100.0)
        self.peak_prominence.setDecimals(1)
        self.peak_prominence.setValue(1.0)
        self.peak_prominence.setSingleStep(0.5)
        form.addRow("峰值突出度:", self.peak_prominence)

        self.min_er = QDoubleSpinBox()
        self.min_er.setRange(0.0, 50.0)
        self.min_er.setDecimals(1)
        self.min_er.setValue(3.0)
        self.min_er.setSingleStep(0.5)
        self.min_er.setSuffix(" dB")
        form.addRow("最小消光比:", self.min_er)

        param_group.setLayout(form)
        left.addWidget(param_group)

        # 按钮组
        btn_group = QGroupBox("操作")
        btn_layout = QVBoxLayout()
        self.btn_analyze = QPushButton("分析")
        self.btn_analyze.setEnabled(False)
        btn_layout.addWidget(self.btn_analyze)
        btn_group.setLayout(btn_layout)
        left.addWidget(btn_group)

        # 结果显示
        result_group = QGroupBox("分析结果")
        result_layout = QVBoxLayout()
        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setMaximumHeight(200)
        result_layout.addWidget(self.result_text)
        result_group.setLayout(result_layout)
        left.addWidget(result_group)

        left.addStretch()
        main_layout.addLayout(left)

        # --- 右侧：图表 ---
        self.chart = ChartWidget()
        main_layout.addWidget(self.chart, stretch=1)

        # 信号连接
        self.btn_load.clicked.connect(self._on_load_clicked)
        self.btn_analyze.clicked.connect(self._on_analyze_clicked)

    # ==================================================================
    # 按钮槽
    # ==================================================================

    def _on_load_clicked(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, "加载光谱数据", "", "CSV 文件 (*.csv)"
        )
        if not filepath:
            return
        try:
            self._load_csv(filepath)
        except Exception as exc:
            self._on_error(f"加载文件失败: {exc}")

    def _on_analyze_clicked(self):
        if self._wavelengths is None or self._power_data is None:
            QMessageBox.warning(self, "警告", "请先加载光谱数据")
            return
        try:
            self._run_analysis()
        except Exception as exc:
            self._on_error(f"分析失败: {exc}")

    # ==================================================================
    # 数据加载
    # ==================================================================

    def _load_csv(self, filepath: str):
        """加载 CSV 光谱数据文件，要求包含波长和功率列。"""
        wavelengths = []
        power_data = []

        with open(filepath, "r", newline="") as f:
            reader = csv.reader(f)
            header = next(reader, None)

            if header is None:
                raise ValueError("文件为空")

            # 查找波长和功率列（支持多种列名）
            header_lower = [h.strip().lower() for h in header]
            wl_idx = self._find_column(header_lower, ["wavelength", "波长", "wl", "wavelength_nm"])
            pw_idx = self._find_column(header_lower, ["power", "功率", "power_dbm", "intensity"])

            if wl_idx is None or pw_idx is None:
                raise ValueError(
                    "CSV 文件缺少必要列（需要波长和功率列）。"
                    f"找到的列: {header}"
                )

            for row in reader:
                if len(row) <= max(wl_idx, pw_idx):
                    continue
                try:
                    wavelengths.append(float(row[wl_idx]))
                    power_data.append(float(row[pw_idx]))
                except ValueError:
                    continue

        if len(wavelengths) == 0:
            raise ValueError("文件中没有有效的数据行")

        self._wavelengths = np.array(wavelengths)
        self._power_data = np.array(power_data)
        self._analysis_result = None
        self.result_text.clear()

        self.file_label.setText(filepath.split("/")[-1].split("\\")[-1])
        self.btn_analyze.setEnabled(True)
        self._plot_spectrum()
        self._log.append_log(
            f"光谱数据已加载: {len(wavelengths)} 个数据点", "INFO"
        )

    @staticmethod
    def _find_column(header: list, candidates: list) -> Optional[int]:
        """在 header 中查找匹配 candidates 的列索引。"""
        for i, col in enumerate(header):
            if col in candidates:
                return i
        return None

    # ==================================================================
    # 分析
    # ==================================================================

    def _run_analysis(self):
        """调用 spectrum_analyzer 计算 6 项指标并更新图表和结果。"""
        wl = self._wavelengths
        pw = self._power_data

        sigma = self.smooth_sigma.value()
        height_pct = self.peak_height_pct.value()
        prominence = self.peak_prominence.value()
        min_er = self.min_er.value()

        # 平滑
        smoothed = spectrum_analyzer.smooth_spectrum(wl, pw, sigma=sigma)

        # 1. 峰值
        peak_indices, peak_wls, peak_props = spectrum_analyzer.find_peaks(
            wl, smoothed,
            height_percentile=height_pct,
            prominence=prominence,
        )

        # 2. 谷值
        valley_indices, valley_wls = spectrum_analyzer.find_valleys(
            wl, smoothed,
            height_percentile=100 - height_pct,
        )

        # 3. 插损
        il = spectrum_analyzer.insertion_loss(smoothed)

        # 4. 消光比
        er = spectrum_analyzer.extinction_ratio(wl, smoothed)

        # 5. FSR
        fsr = spectrum_analyzer.free_spectral_range(wl, smoothed, return_all=True)

        # 6. FWHM
        fwhm_result = spectrum_analyzer.fwhm(wl, smoothed, min_er=min_er)

        # 保存结果
        self._analysis_result = {
            "peaks": (peak_indices, peak_wls),
            "valleys": (valley_indices, valley_wls),
            "insertion_loss": il,
            "extinction_ratio": er,
            "fsr": fsr,
            "fwhm": fwhm_result,
        }

        # 更新图表（重绘并标注）
        self._plot_spectrum()
        self._annotate_peaks_valleys(peak_indices, peak_wls, valley_indices, valley_wls, smoothed)

        # 更新结果文本
        self._display_results()
        self._log.append_log("光谱分析完成", "INFO")

    # ==================================================================
    # 绘图
    # ==================================================================

    def _plot_spectrum(self):
        """绘制功率随波长变化曲线。"""
        self.chart.clear()
        self.chart.plot(self._wavelengths, self._power_data, color="tab:blue", linewidth=1, label="Raw data")
        self.chart.set_labels(
            xlabel="Wavelength (nm)",
            ylabel="Power (dBm)",
            title="Spectrum Data",
        )
        self.chart.ax.legend(loc="upper right", fontsize=8)
        self.chart.canvas.draw_idle()

    def _annotate_peaks_valleys(
        self,
        peak_indices: np.ndarray,
        peak_wls: np.ndarray,
        valley_indices: np.ndarray,
        valley_wls: np.ndarray,
        smoothed: np.ndarray,
    ):
        """在图表上标注峰值和谷值位置。"""
        ax = self.chart.ax

        # 标注峰值
        if len(peak_indices) > 0:
            ax.plot(
                peak_wls, smoothed[peak_indices],
                "rv", markersize=8, label="Peaks",
            )
            for idx, wl in zip(peak_indices, peak_wls):
                self.chart.add_annotation(
                    wl, smoothed[idx], f"P {wl:.2f}"
                )

        # 标注谷值
        if len(valley_indices) > 0:
            ax.plot(
                valley_wls, smoothed[valley_indices],
                "b^", markersize=8, label="Valleys",
            )
            for idx, wl in zip(valley_indices, valley_wls):
                self.chart.add_annotation(
                    wl, smoothed[idx], f"V {wl:.2f}"
                )

        ax.legend(loc="upper right", fontsize=8)
        self.chart.canvas.draw_idle()

    def _display_results(self):
        """在结果文本框中显示分析结果。"""
        r = self._analysis_result
        if r is None:
            return

        lines = []
        peak_indices, peak_wls = r["peaks"]
        valley_indices, valley_wls = r["valleys"]

        lines.append(f"峰值数量: {len(peak_indices)}")
        if len(peak_wls) > 0:
            lines.append(f"  波长: {', '.join(f'{w:.2f}' for w in peak_wls[:10])}")

        lines.append(f"谷值数量: {len(valley_indices)}")
        if len(valley_wls) > 0:
            lines.append(f"  波长: {', '.join(f'{w:.2f}' for w in valley_wls[:10])}")

        lines.append(f"插损: {r['insertion_loss']:.3f} dB")
        lines.append(f"消光比: {r['extinction_ratio']:.3f} dB")

        fsr = r["fsr"]
        if isinstance(fsr, dict):
            lines.append(f"FSR (均值): {fsr.get('fsr_mean', 0):.4f} nm")
            lines.append(f"FSR (标准差): {fsr.get('fsr_std', 0):.4f} nm")
        else:
            lines.append(f"FSR: {fsr:.4f} nm")

        fwhm_r = r["fwhm"]
        lines.append(f"FWHM: {fwhm_r.get('fwhm', 0):.4f} nm")
        lines.append(f"  中心波长: {fwhm_r.get('center_wavelength', 0):.3f} nm")
        note = fwhm_r.get("note", "")
        if note:
            lines.append(f"  备注: {note}")

        self.result_text.setPlainText("\n".join(lines))

    # ==================================================================
    # 错误处理
    # ==================================================================

    @Slot(str)
    def _on_error(self, msg: str):
        QMessageBox.critical(self, "错误", msg)
        self._log.append_log(msg, "ERROR")
        logger.error(msg)

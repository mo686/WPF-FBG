"""Calibration_Panel — 光纤传感定标流水线面板

提供定标、测量、匹配、求值四步操作流程：
1. 定标：加载定标 CSV 目录，构建定标映射表
2. 测量：加载测量 CSV 文件
3. 匹配：将测量曲线与定标表匹配，找到最佳电压
4. 求值：根据匹配结果计算温度

内含两个子页面：
- 操作页：参数、按钮、结果文本、曲线对比图
- 匹配分析页：四种匹配方式各自的 ρ-电压图 + 汇总图
"""

import json
import logging
import os
from typing import Optional

import numpy as np
from PySide6.QtCore import QThread, Signal, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.ui.chart_widget import ChartWidget
from src.ui.log_console import LogConsole
from src.ui.workers import CalibrationWorker

logger = logging.getLogger(__name__)

_CAL_CONFIG_PATH = os.path.join(
    os.path.dirname(__file__), "..", "config", "last_cal_params.json"
)


class CalibrationPanel(QWidget):
    """光纤传感定标流水线面板。"""

    def __init__(
        self,
        log_console: LogConsole,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._log = log_console
        self._cal_dir: Optional[str] = None
        self._meas_dir: Optional[str] = None
        self._pipeline_result = None

        self._init_ui()
        self._init_worker()
        self._auto_load_last_cal()

    # ==================================================================
    # UI 构建
    # ==================================================================

    def _init_ui(self):
        outer = QVBoxLayout(self)

        # 内部子页签
        self._sub_tabs = QTabWidget()
        outer.addWidget(self._sub_tabs)

        # --- 子页面 1：操作 ---
        op_page = QWidget()
        self._init_operation_page(op_page)
        self._sub_tabs.addTab(op_page, "操作")

        # --- 子页面 2：匹配分析 ---
        analysis_page = QWidget()
        self._init_analysis_page(analysis_page)
        self._sub_tabs.addTab(analysis_page, "匹配分析")

    # ------------------------------------------------------------------

    def _init_operation_page(self, page: QWidget):
        main_layout = QHBoxLayout(page)

        # --- 左侧：参数 + 按钮 + 结果（可滚动）---
        from PySide6.QtWidgets import QScrollArea
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(240)
        scroll.setMaximumWidth(280)

        left_widget = QWidget()
        left = QVBoxLayout(left_widget)

        # 参数组
        param_group = QGroupBox("流水线参数")
        form = QFormLayout()

        self.alpha_input = QDoubleSpinBox()
        self.alpha_input.setRange(0.01, 100.0)
        self.alpha_input.setDecimals(2)
        self.alpha_input.setValue(9.08)
        self.alpha_input.setSuffix(" pm/°C")
        form.addRow("灵敏度系数 α:", self.alpha_input)

        self.t0_input = QDoubleSpinBox()
        self.t0_input.setRange(-273.15, 1000.0)
        self.t0_input.setDecimals(2)
        self.t0_input.setValue(20.0)
        self.t0_input.setSuffix(" °C")
        form.addRow("基准温度 T₀:", self.t0_input)

        self.lambda_ref_input = QDoubleSpinBox()
        self.lambda_ref_input.setRange(1000.0, 2000.0)
        self.lambda_ref_input.setDecimals(3)
        self.lambda_ref_input.setValue(1550.0)
        self.lambda_ref_input.setSuffix(" nm")
        form.addRow("参考波长 λ_ref:", self.lambda_ref_input)

        self.lambda_meas_input = QDoubleSpinBox()
        self.lambda_meas_input.setRange(0.0, 2000.0)
        self.lambda_meas_input.setDecimals(3)
        self.lambda_meas_input.setValue(0.0)
        self.lambda_meas_input.setSuffix(" nm")
        self.lambda_meas_input.setSpecialValueText("同 λ_ref")
        form.addRow("测量波长 λ_meas:", self.lambda_meas_input)

        self.k_cand_input = QSpinBox()
        self.k_cand_input.setRange(1, 20)
        self.k_cand_input.setValue(3)
        form.addRow("候选数 K:", self.k_cand_input)

        self.smooth_input = QSpinBox()
        self.smooth_input.setRange(1, 51)
        self.smooth_input.setValue(5)
        form.addRow("平滑窗口:", self.smooth_input)

        self.corr_bw_input = QDoubleSpinBox()
        self.corr_bw_input.setRange(0.0, 50.0)
        self.corr_bw_input.setDecimals(2)
        self.corr_bw_input.setSuffix(" GHz")
        self.corr_bw_input.setValue(0.0)
        self.corr_bw_input.setToolTip("0 = 自适应；>0 = 峰值 ± 此值范围")
        form.addRow("匹配带宽:", self.corr_bw_input)

        param_group.setLayout(form)
        left.addWidget(param_group)

        # 操作按钮组
        btn_group = QGroupBox("操作流程")
        btn_layout = QVBoxLayout()

        self.btn_load_cal = QPushButton("① 定标 — 加载定标数据")
        self.btn_load_meas = QPushButton("② 测量 — 加载测量数据")
        self.btn_match = QPushButton("③ 匹配（四种方式 × 正/负）")
        self.btn_evaluate = QPushButton("④ 求值 — 计算温度")
        self.btn_optimize = QPushButton("⑤ 参数寻优")
        self.btn_save_result = QPushButton("保存结果 CSV")
        self.btn_save_plot = QPushButton("保存对比图")
        self.btn_close = QPushButton("结束")

        self.btn_load_meas.setEnabled(False)
        self.btn_match.setEnabled(False)
        self.btn_evaluate.setEnabled(False)
        self.btn_optimize.setEnabled(False)
        self.btn_save_result.setEnabled(False)
        self.btn_save_plot.setEnabled(False)

        # 目标 Δλ 输入（用于参数寻优）
        opt_row = QHBoxLayout()
        opt_row.addWidget(QLabel("目标 Δλ:"))
        self.target_dl_input = QDoubleSpinBox()
        self.target_dl_input.setRange(-200.0, 200.0)
        self.target_dl_input.setDecimals(1)
        self.target_dl_input.setValue(38.0)
        self.target_dl_input.setSuffix(" pm")
        opt_row.addWidget(self.target_dl_input)

        for btn in (
            self.btn_load_cal, self.btn_load_meas, self.btn_match,
            self.btn_evaluate,
        ):
            btn_layout.addWidget(btn)
        btn_layout.addLayout(opt_row)
        btn_layout.addWidget(self.btn_optimize)
        for btn in (
            self.btn_save_result, self.btn_save_plot, self.btn_close,
        ):
            btn_layout.addWidget(btn)

        btn_group.setLayout(btn_layout)
        left.addWidget(btn_group)

        # 正/负显示切换
        self.sign_combo = QComboBox()
        self.sign_combo.addItems(["Δλ > 0（升温）", "Δλ < 0（降温）"])
        self.sign_combo.currentIndexChanged.connect(self._on_sign_changed)
        left.addWidget(QLabel("显示组:"))
        left.addWidget(self.sign_combo)

        # 匹配方式显示选择
        from PySide6.QtWidgets import QCheckBox
        mode_group = QGroupBox("显示方式")
        mode_layout = QVBoxLayout()
        self._mode_checks = {}
        for key, label in [
            ("correlation", "归一化互相关"),
            ("fpeak_nearest", "fpeak最近邻"),
            ("normalized_shape", "归一化形状"),
            ("fpeak_fit", "洛伦兹拟合"),
        ]:
            cb = QCheckBox(label)
            cb.setChecked(True)
            cb.stateChanged.connect(self._on_mode_filter_changed)
            mode_layout.addWidget(cb)
            self._mode_checks[key] = cb
        mode_group.setLayout(mode_layout)
        left.addWidget(mode_group)

        # 状态标签
        self.cal_status = QLabel("定标: 未加载")
        self.meas_status = QLabel("测量: 未加载")
        left.addWidget(self.cal_status)
        left.addWidget(self.meas_status)

        # FBG 光谱对比文件路径
        fbg_group = QGroupBox("FBG Spectrum Comparison")
        fbg_layout = QVBoxLayout()
        from PySide6.QtWidgets import QLineEdit
        self.fbg_file1_input = QLineEdit()
        self.fbg_file1_input.setPlaceholderText("FBG file 1 path (.json)")
        self.fbg_file2_input = QLineEdit()
        self.fbg_file2_input.setPlaceholderText("FBG file 2 path (.json)")
        self.btn_browse_fbg1 = QPushButton("Browse...")
        self.btn_browse_fbg2 = QPushButton("Browse...")
        self.btn_browse_fbg1.clicked.connect(self._browse_fbg_file1)
        self.btn_browse_fbg2.clicked.connect(self._browse_fbg_file2)
        row1 = QHBoxLayout()
        row1.addWidget(self.fbg_file1_input, stretch=1)
        row1.addWidget(self.btn_browse_fbg1)
        row2 = QHBoxLayout()
        row2.addWidget(self.fbg_file2_input, stretch=1)
        row2.addWidget(self.btn_browse_fbg2)
        fbg_layout.addLayout(row1)
        fbg_layout.addLayout(row2)
        fbg_group.setLayout(fbg_layout)
        left.addWidget(fbg_group)

        # 结果显示
        result_group = QGroupBox("匹配结果")
        result_layout = QVBoxLayout()
        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setMaximumHeight(200)
        result_layout.addWidget(self.result_text)
        result_group.setLayout(result_layout)
        left.addWidget(result_group)

        left.addStretch()
        scroll.setWidget(left_widget)
        main_layout.addWidget(scroll)

        # --- 右侧：主图表（定标曲线 / 最佳匹配对比）---
        self.chart = ChartWidget()
        main_layout.addWidget(self.chart, stretch=1)

        # 信号连接
        self.btn_load_cal.clicked.connect(self._on_load_cal_clicked)
        self.btn_load_meas.clicked.connect(self._on_load_meas_clicked)
        self.btn_match.clicked.connect(self._on_match_clicked)
        self.btn_evaluate.clicked.connect(self._on_evaluate_clicked)
        self.btn_optimize.clicked.connect(self._on_optimize_clicked)
        self.btn_save_result.clicked.connect(self._on_save_result_clicked)
        self.btn_save_plot.clicked.connect(self._on_save_plot_clicked)
        self.btn_close.clicked.connect(self._on_close_clicked)

    # ------------------------------------------------------------------

    def _init_analysis_page(self, page: QWidget):
        layout = QVBoxLayout(page)

        # 正/负切换（与操作页联动）
        top_bar = QHBoxLayout()
        top_bar.addWidget(QLabel("显示组:"))
        self.analysis_sign_combo = QComboBox()
        self.analysis_sign_combo.addItems(["Δλ > 0（升温）", "Δλ < 0（降温）"])
        self.analysis_sign_combo.currentIndexChanged.connect(
            self._on_analysis_sign_changed
        )
        top_bar.addWidget(self.analysis_sign_combo)
        top_bar.addStretch()
        layout.addLayout(top_bar)

        # 五张图：四种方式各一张 ρ-电压图 + 一张汇总图
        # 用一个 ChartWidget 承载 3×2 子图
        self.analysis_chart = ChartWidget()
        layout.addWidget(self.analysis_chart, stretch=1)

    # ==================================================================
    # Worker / Thread 初始化
    # ==================================================================

    def _init_worker(self):
        self._thread = QThread()
        self._worker = CalibrationWorker()
        self._worker.moveToThread(self._thread)

        self._worker.cal_loaded.connect(self._on_cal_loaded)
        self._worker.meas_loaded.connect(self._on_meas_loaded)
        self._worker.match_done.connect(self._on_match_done)
        self._worker.evaluate_done.connect(self._on_evaluate_done)
        self._worker.optimize_done.connect(self._on_optimize_done)
        self._worker.error_occurred.connect(self._on_error)
        self._worker.operation_finished.connect(self._on_operation_finished)

        self._thread.start()

    # ==================================================================
    # 定标目录持久化
    # ==================================================================

    def _save_last_cal_dir(self, directory: str) -> None:
        try:
            os.makedirs(os.path.dirname(_CAL_CONFIG_PATH), exist_ok=True)
            with open(_CAL_CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump({"last_cal_dir": directory}, f, ensure_ascii=False)
        except Exception as exc:
            logger.debug("保存定标目录配置失败: %s", exc)

    def _load_last_cal_dir(self) -> Optional[str]:
        try:
            with open(_CAL_CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            path = data.get("last_cal_dir")
            if path and os.path.isdir(path):
                return path
        except Exception:
            pass
        return None

    def _auto_load_last_cal(self) -> None:
        last_dir = self._load_last_cal_dir()
        if last_dir:
            self._cal_dir = last_dir
            self._log.append_log(f"自动加载上次定标目录: {last_dir}", "INFO")
            self._set_busy(True)
            self._worker.load_calibration(last_dir, self.smooth_input.value())

    # ==================================================================
    # 按钮槽
    # ==================================================================

    def _browse_fbg_file1(self):
        """Browse for FBG spectrum file 1."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Select FBG File 1", "", "JSON Files (*.json);;All Files (*)"
        )
        if path:
            self.fbg_file1_input.setText(path)

    def _browse_fbg_file2(self):
        """Browse for FBG spectrum file 2."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Select FBG File 2", "", "JSON Files (*.json);;All Files (*)"
        )
        if path:
            self.fbg_file2_input.setText(path)

    def _on_load_cal_clicked(self):
        directory = QFileDialog.getExistingDirectory(
            self, "选择定标数据目录", self._cal_dir or ""
        )
        if not directory:
            return
        self._cal_dir = directory
        self._set_busy(True)
        self._worker.load_calibration(directory, self.smooth_input.value())

    def _on_load_meas_clicked(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, "选择测量 CSV 文件", "", "CSV 文件 (*.csv)"
        )
        if not filepath:
            return
        self._set_busy(True)
        self._worker.load_measurement_file(filepath)

    def _on_match_clicked(self):
        self._set_busy(True)
        corr_bw = self.corr_bw_input.value()
        self._worker.run_match(
            k_cand=self.k_cand_input.value(),
            smooth_window=self.smooth_input.value(),
            corr_bandwidth=corr_bw if corr_bw > 0 else None,
        )

    def _on_optimize_clicked(self):
        self._set_busy(True)
        sign = "positive" if self.sign_combo.currentIndex() == 0 else "negative"
        self._log.append_log(
            f"开始参数寻优，目标 Δλ={self.target_dl_input.value():.1f}pm ...",
            "INFO",
        )
        self._worker.run_optimize(
            target_dl=self.target_dl_input.value(),
            sign=sign,
        )

    def _on_evaluate_clicked(self):
        self._set_busy(True)
        self._worker.run_evaluate(
            alpha=self.alpha_input.value(),
            t0=self.t0_input.value(),
            lambda_ref=self.lambda_ref_input.value(),
            lambda_meas=self.lambda_meas_input.value(),
        )

    def _on_save_result_clicked(self):
        filepath, _ = QFileDialog.getSaveFileName(
            self, "保存结果", "", "CSV 文件 (*.csv)"
        )
        if not filepath:
            return
        try:
            self._worker.save_results(filepath)
            self._log.append_log(f"结果已保存至 {filepath}", "INFO")
        except Exception as exc:
            self._on_error(f"保存结果失败: {exc}")

    def _on_save_plot_clicked(self):
        filepath, _ = QFileDialog.getSaveFileName(
            self, "保存对比图", "", "PNG 图片 (*.png)"
        )
        if not filepath:
            return
        try:
            self.chart.save_figure(filepath)
            self._log.append_log(f"对比图已保存至 {filepath}", "INFO")
        except Exception as exc:
            self._on_error(f"保存图表失败: {exc}")

    # ==================================================================
    # Worker 回调槽
    # ==================================================================

    @Slot(int)
    def _on_cal_loaded(self, count: int):
        self.cal_status.setText(f"定标: 已加载 {count} 条曲线")
        self.btn_load_cal.setEnabled(True)
        self._log.append_log(f"定标数据加载完成，共 {count} 条曲线", "INFO")
        if self._cal_dir:
            self._save_last_cal_dir(self._cal_dir)
        if hasattr(self, '_match_results'):
            self._match_results = {}
        self._pipeline_result = None
        self.result_text.clear()
        self._plot_cal_curves()

    @Slot(int)
    def _on_meas_loaded(self, count: int):
        self.meas_status.setText(f"测量: 已加载 {count} 条曲线")
        self._log.append_log(f"测量数据加载完成，共 {count} 条曲线", "INFO")

    @Slot(object)
    def _on_match_done(self, match_info: dict):
        self._match_results = match_info.get("all_match_results", {})
        self._display_match_results()
        self._log.append_log("匹配完成（四种方式 × 正/负 Δλ）", "INFO")

    @Slot(object)
    def _on_evaluate_done(self, eval_result: dict):
        self._pipeline_result = eval_result
        self.result_text.setPlainText(
            f"求值结果\n"
            f"最佳电压: {eval_result['best_voltage']:.2f} V\n"
            f"波长偏移 Δλ: {eval_result['delta_lambda']:.2f} pm\n"
            f"FBG 波长 λ_FBG: {eval_result['lambda_fbg']:.3f} nm\n"
            f"温度变化 ΔT: {eval_result['delta_t']:.2f} °C\n"
            f"计算温度 T: {eval_result['temperature']:.2f} °C\n"
            f"匹配相关系数 ρ: {eval_result['rho_max']:.4f}"
        )
        self._log.append_log(
            f"求值完成: T={eval_result['temperature']:.2f}°C, "
            f"λ_FBG={eval_result['lambda_fbg']:.3f}nm",
            "INFO",
        )

    @Slot(object)
    def _on_optimize_done(self, result: dict):
        best = result["best"]
        top10 = result["top10"]
        target = result["target_dl"]

        # 将最佳参数自动填入 UI
        self.k_cand_input.setValue(best["k_cand"])
        self.smooth_input.setValue(best["smooth_window"])
        self.corr_bw_input.setValue(best["corr_bandwidth"])

        # 显示结果
        lines = [
            f"=== 参数寻优完成 ===",
            f"目标 Δλ: {target:.1f} pm",
            f"搜索组合: {result['total_tried']}，有效: {result['total_valid']}",
            f"",
            f"最佳参数（已自动填入）:",
            f"  方式: {best['mode_name']}",
            f"  带宽: {best['corr_bandwidth']:.1f} GHz",
            f"  候选数 K: {best['k_cand']}",
            f"  平滑窗口: {best['smooth_window']}",
            f"  → Δλ={best['best_dl']:.2f}pm  "
            f"误差={best['error']:.2f}pm  ρ={best['best_rho']:.4f}",
            f"",
            f"--- Top 10 ---",
        ]
        for i, r in enumerate(top10):
            lines.append(
                f"{i+1}. {r['mode_name']}  "
                f"bw={r['corr_bandwidth']:.1f}  K={r['k_cand']}  "
                f"sw={r['smooth_window']}  "
                f"→ Δλ={r['best_dl']:.1f}pm  "
                f"err={r['error']:.1f}  ρ={r['best_rho']:.4f}"
            )
        self.result_text.setPlainText("\n".join(lines))
        self._log.append_log(
            f"参数寻优完成: 最佳 {best['mode_name']} "
            f"Δλ={best['best_dl']:.1f}pm (误差 {best['error']:.1f}pm)",
            "INFO",
        )

    @Slot(str)
    def _on_error(self, msg: str):
        self._log.append_log(msg, "ERROR")
        logger.error(msg)

    @Slot()
    def _on_operation_finished(self):
        self._set_busy(False)

    # ==================================================================
    # 内部方法
    # ==================================================================

    def _set_busy(self, busy: bool):
        if busy:
            for btn in (
                self.btn_load_cal, self.btn_load_meas,
                self.btn_match, self.btn_evaluate, self.btn_optimize,
            ):
                btn.setEnabled(False)
        else:
            self.btn_load_cal.setEnabled(True)
            has_cal = self._worker._table is not None
            has_meas = bool(self._worker._meas_curves)
            has_match = hasattr(self, '_match_results') and bool(self._match_results)
            self.btn_load_meas.setEnabled(has_cal)
            self.btn_match.setEnabled(has_cal and has_meas)
            self.btn_optimize.setEnabled(has_cal and has_meas)
            self.btn_evaluate.setEnabled(has_match)
            self.btn_save_result.setEnabled(has_match)
            self.btn_save_plot.setEnabled(has_match)

    # ------------------------------------------------------------------
    # 操作页绘图
    # ------------------------------------------------------------------

    def _plot_cal_curves(self):
        """绘制所有定标曲线概览。"""
        cal_curves = self._worker._cal_curves
        if not cal_curves:
            return
        self.chart.figure.clear()
        ax = self.chart.figure.add_subplot(111)
        for dl, curve in cal_curves:
            ax.plot(curve.frequency, curve.magnitude, linewidth=0.8,
                    alpha=0.7)
        ax.set_xlabel("Frequency (GHz)")
        ax.set_ylabel("Magnitude (dB)")
        ax.set_title("Calibration Curves")
        self.chart.ax = ax
        self.chart.figure.tight_layout()
        self.chart.canvas.draw_idle()

    def _plot_best_match(self, sign_data: dict):
        """在操作页绘制最佳匹配曲线对比。

        布局：左侧 subplot (a) 为 FBG 光谱对比，右侧为匹配结果。
        - 1 种方式：右侧单张图 (b)
        - 2-4 种方式：右侧 2×2 子图 (b)(c)(d)(e)
        """
        self.chart.figure.clear()
        modes = list(sign_data.keys())
        n = len(modes)
        if n == 0:
            self.chart.canvas.draw_idle()
            return

        import re as _re

        # Determine layout: left column for FBG spectrum, right for match results
        if n == 1:
            # 1×2 layout: (a) FBG spectrum, (b) match
            ax_fbg = self.chart.figure.add_subplot(1, 2, 1)
            ax_match = self.chart.figure.add_subplot(1, 2, 2)
            match_axes = [ax_match]
        else:
            # Use GridSpec: left half for FBG, right half for 2×2 match subplots
            from matplotlib.gridspec import GridSpec
            gs = GridSpec(2, 4, figure=self.chart.figure)
            ax_fbg = self.chart.figure.add_subplot(gs[:, :2])  # left half
            match_axes = []
            positions = [(0, 2), (0, 3), (1, 2), (1, 3)]
            for i in range(min(n, 4)):
                r, c = positions[i]
                ax = self.chart.figure.add_subplot(gs[r, c])
                match_axes.append(ax)

        # --- Subplot (a): FBG spectrum comparison ---
        fbg_file1 = self.fbg_file1_input.text().strip()
        fbg_file2 = self.fbg_file2_input.text().strip()

        if fbg_file1 and fbg_file2 and os.path.exists(fbg_file1) and os.path.exists(fbg_file2):
            import json as _json
            def _load_fbg(fp):
                with open(fp, 'r', encoding='utf-8') as f:
                    data = _json.load(f)
                entry = data[0] if isinstance(data, list) else data
                return np.array(entry['rescaled_wavelength']), np.array(entry['rescaled_reference_power'])

            wl1, pw1 = _load_fbg(fbg_file1)
            wl2, pw2 = _load_fbg(fbg_file2)

            m1 = _re.search(r'(FBG_\d+)', os.path.basename(fbg_file1))
            m2 = _re.search(r'(FBG_\d+)', os.path.basename(fbg_file2))
            lbl1 = m1.group(1) if m1 else 'Spectrum 1'
            lbl2 = m2.group(1) if m2 else 'Spectrum 2'

            ax_fbg.plot(wl1, pw1, linewidth=1.2, label=lbl1)
            ax_fbg.plot(wl2, pw2, linewidth=1.2, label=lbl2)

            # Mark center wavelengths
            c1 = wl1[np.argmax(pw1)]
            c2 = wl2[np.argmax(pw2)]
            ax_fbg.axvline(x=c1, color='C0', linestyle='--', alpha=0.7,
                           label=f'{c1:.4f}')
            ax_fbg.axvline(x=c2, color='C1', linestyle='--', alpha=0.7,
                           label=f'{c2:.4f}')
        else:
            ax_fbg.text(0.5, 0.5, 'Set FBG file paths\nin left panel',
                        transform=ax_fbg.transAxes, ha='center', va='center',
                        fontsize=9, color='gray')

        ax_fbg.set_xlabel("Wavelength (nm)")
        ax_fbg.set_ylabel("Loss (dBm)")
        ax_fbg.legend(loc='upper right')
        from plot_style import add_subplot_label
        add_subplot_label(ax_fbg, '(a)')

        # --- Match subplots (b), (c), ... ---
        sub_labels = ['(b)', '(c)', '(d)', '(e)']
        corr_bw = self.corr_bw_input.value()  # matching bandwidth from UI

        for i, mode in enumerate(modes[:len(match_axes)]):
            info = sign_data[mode]
            ax = match_axes[i]
            meas = info.get("best_meas_curve")
            cal = info.get("best_cal_curve")
            if meas is not None:
                ax.plot(meas.frequency, meas.magnitude, "b-",
                        label=f"Measured V={info['best_voltage']:.2f}V")
            if cal is not None:
                ax.plot(cal.frequency, cal.magnitude, "r--",
                        label=f"Calibration $\\Delta\\lambda$={info['best_delta_lambda']:.0f}pm")

            # Shade the matching bandwidth range around the peak
            if meas is not None and corr_bw > 0:
                from src.calibration_pipeline import extract_peak
                fpeak = extract_peak(meas)
                f_lo = max(fpeak - corr_bw, meas.frequency[0])
                f_hi = min(fpeak + corr_bw, meas.frequency[-1])
                ax.axvspan(f_lo, f_hi, alpha=0.08, color='green',
                           label=f'Match range (±{corr_bw:.1f} GHz)')
                ax.axvline(fpeak, color='green', linestyle=':', linewidth=0.8, alpha=0.6)

            ax.set_title(
                f"{info['mode_name']}  $\\rho$={info['best_rho']:.4f}"
            )
            ax.set_xlabel("Frequency (GHz)")
            ax.set_ylabel("Magnitude (dB)")
            ax.legend()
            add_subplot_label(ax, sub_labels[i])

        self.chart.ax = (
            self.chart.figure.axes[0] if self.chart.figure.axes else None
        )
        self.chart.figure.tight_layout()
        self.chart.canvas.draw_idle()

    # ------------------------------------------------------------------
    # 匹配分析页绘图
    # ------------------------------------------------------------------

    def _plot_analysis(self, sign_data: dict):
        """在匹配分析页绘制 ρ-电压图。

        - 1 种方式：单张图占满
        - 2-4 种方式：各自独立子图 + 底部汇总图
        """
        fig = self.analysis_chart.figure
        fig.clear()
        modes = list(sign_data.keys())
        n = len(modes)
        if n == 0:
            self.analysis_chart.canvas.draw_idle()
            return

        colors = ["tab:blue", "tab:orange", "tab:green", "tab:red"]
        markers = ["o", "s", "^", "D"]

        if n == 1:
            # 单种方式：一张图占满
            mode = modes[0]
            info = sign_data[mode]
            ax = fig.add_subplot(111)
            voltages = info.get("voltages", [])
            rhos = info.get("per_voltage_rho", [])
            if voltages and rhos:
                ax.plot(voltages, rhos, color=colors[0],
                        marker=markers[0], markersize=5, linewidth=1.2)
                best_v = info["best_voltage"]
                best_rho = info["best_rho"]
                ax.axvline(best_v, color="gray", linestyle=":", linewidth=0.8)
                ax.plot(best_v, best_rho, marker="*", markersize=14,
                        color=colors[0], zorder=5)
                ax.annotate(
                    f"V={best_v:.2f}V\nΔλ={info['best_delta_lambda']:.0f}pm\nρ={best_rho:.4f}",
                    xy=(best_v, best_rho),
                    xytext=(12, -15), textcoords="offset points",
                    fontsize=9, color=colors[0],
                )
            ax.set_xlabel("Voltage (V)")
            ax.set_ylabel("Correlation $\\rho$")
            ax.set_title(f"{info['mode_name']}  $\\rho$ vs Voltage ($\\bigstar$ = best match)")
        else:
            # 多种方式：上方各自子图 + 底部汇总
            rows = 3 if n > 2 else 2
            cols = 2

            for i, mode in enumerate(modes):
                info = sign_data[mode]
                ax = fig.add_subplot(rows, cols, i + 1)
                voltages = info.get("voltages", [])
                rhos = info.get("per_voltage_rho", [])
                if voltages and rhos:
                    ax.plot(voltages, rhos,
                            color=colors[i % len(colors)],
                            marker=markers[i % len(markers)],
                            markersize=4, linewidth=1)
                    best_v = info["best_voltage"]
                    best_rho = info["best_rho"]
                    ax.axvline(best_v, color="gray", linestyle=":", linewidth=0.8)
                    ax.plot(best_v, best_rho, marker="*", markersize=12,
                            color=colors[i % len(colors)], zorder=5)
                    ax.annotate(
                        f"V={best_v:.2f}\n$\\Delta\\lambda$={info['best_delta_lambda']:.0f}pm",
                        xy=(best_v, best_rho),
                        xytext=(8, -10), textcoords="offset points",
                        fontsize=7, color=colors[i % len(colors)],
                    )
                ax.set_title(f"{info['mode_name']}")
                ax.set_xlabel("Voltage (V)")
                ax.set_ylabel("$\\rho$")
                ax.tick_params(labelsize=9)

            # 汇总图
            ax_sum = fig.add_subplot(rows, 1, rows)
            for i, mode in enumerate(modes):
                info = sign_data[mode]
                voltages = info.get("voltages", [])
                rhos = info.get("per_voltage_rho", [])
                if voltages and rhos:
                    ax_sum.plot(voltages, rhos,
                                color=colors[i % len(colors)],
                                marker=markers[i % len(markers)],
                                markersize=4, linewidth=1,
                                label=info["mode_name"])
                    best_v = info["best_voltage"]
                    best_rho = info["best_rho"]
                    ax_sum.plot(best_v, best_rho, marker="*", markersize=10,
                                color=colors[i % len(colors)], zorder=5)
            ax_sum.set_xlabel("Voltage (V)")
            ax_sum.set_ylabel("Correlation $\\rho$")
            ax_sum.set_title("$\\rho$ vs Voltage ($\\bigstar$ = best match)")
            ax_sum.legend(loc="lower right")
            ax_sum.tick_params(labelsize=9)

        self.analysis_chart.ax = fig.axes[0] if fig.axes else None
        fig.tight_layout()
        self.analysis_chart.canvas.draw_idle()

    # ------------------------------------------------------------------
    # 显示 / 切换
    # ------------------------------------------------------------------

    def _get_current_sign_key(self) -> str:
        return "Δλ>0" if self.sign_combo.currentIndex() == 0 else "Δλ<0"

    def _get_visible_modes(self) -> set:
        """返回当前勾选的匹配方式 key 集合。"""
        return {k for k, cb in self._mode_checks.items() if cb.isChecked()}

    def _filter_sign_data(self, sign_data: dict) -> dict:
        """按勾选的方式过滤 sign_data。"""
        visible = self._get_visible_modes()
        return {k: v for k, v in sign_data.items() if k in visible}

    def _on_mode_filter_changed(self, _state: int):
        """勾选变化时刷新图表。"""
        self._display_match_results()

    def _display_match_results(self):
        """显示当前选中正/负组的匹配结果，更新两个页面。"""
        if not hasattr(self, '_match_results') or not self._match_results:
            return
        sign_key = self._get_current_sign_key()
        sign_data = self._match_results.get(sign_key, {})
        if not sign_data:
            self.result_text.setPlainText(f"{sign_key} 组无匹配结果")
            return

        # 按勾选过滤
        filtered = self._filter_sign_data(sign_data)

        # 文本结果（显示所有，不过滤）
        lines = [f"=== {sign_key} 匹配结果 ===\n"]
        for mode, info in sign_data.items():
            lines.append(
                f"{info['mode_name']}:\n"
                f"  V={info['best_voltage']:.2f}V  "
                f"ρ={info['best_rho']:.4f}  "
                f"Δλ={info['best_delta_lambda']:.2f}pm\n"
            )
        self.result_text.setPlainText("".join(lines))

        # 操作页：曲线对比（按勾选过滤）
        self._plot_best_match(filtered)
        # 分析页：ρ vs 电压（按勾选过滤）
        self._plot_analysis(filtered)

    def _on_sign_changed(self, index: int):
        self.analysis_sign_combo.blockSignals(True)
        self.analysis_sign_combo.setCurrentIndex(index)
        self.analysis_sign_combo.blockSignals(False)
        self._display_match_results()

    def _on_analysis_sign_changed(self, index: int):
        self.sign_combo.blockSignals(True)
        self.sign_combo.setCurrentIndex(index)
        self.sign_combo.blockSignals(False)
        self._display_match_results()

    # ------------------------------------------------------------------
    # 重置
    # ------------------------------------------------------------------

    def _on_close_clicked(self):
        """结束操作，重置测量和匹配状态，保留定标数据。"""
        self._log.append_log("定标流水线已重置（定标数据保留）", "INFO")
        self._meas_dir = None
        self._pipeline_result = None
        if hasattr(self, '_match_results'):
            self._match_results = {}
        self._worker._meas_curves = []
        self._worker._match_info = None
        self._worker._all_results = []

        has_cal = self._worker._table is not None
        self.btn_load_cal.setEnabled(True)
        self.btn_load_meas.setEnabled(has_cal)
        self.btn_match.setEnabled(False)
        self.btn_evaluate.setEnabled(False)
        self.btn_save_result.setEnabled(False)
        self.btn_save_plot.setEnabled(False)
        self.meas_status.setText("测量: 未加载")
        if not has_cal:
            self.cal_status.setText("定标: 未加载")
        self.result_text.clear()
        self.chart.clear()
        self.chart.canvas.draw_idle()
        self.analysis_chart.figure.clear()
        self.analysis_chart.canvas.draw_idle()

    # ==================================================================
    # 清理
    # ==================================================================

    def cleanup(self):
        if self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(3000)

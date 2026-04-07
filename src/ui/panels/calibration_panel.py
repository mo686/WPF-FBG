"""Calibration_Panel — 光纤传感定标流水线面板

提供定标、测量、匹配、求值四步操作流程：
1. 定标：加载定标 CSV 目录，构建定标映射表
2. 测量：加载测量 CSV 目录
3. 匹配：将测量曲线与定标表匹配，找到最佳电压
4. 求值：根据匹配结果计算温度

嵌入 ChartWidget 显示匹配对比图和所有曲线。
"""

import logging
from typing import Optional

import numpy as np
from PySide6.QtCore import QThread, Signal, Slot
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.ui.chart_widget import ChartWidget
from src.ui.log_console import LogConsole
from src.ui.workers import CalibrationWorker

logger = logging.getLogger(__name__)


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

    # ==================================================================
    # UI 构建
    # ==================================================================

    def _init_ui(self):
        main_layout = QHBoxLayout(self)

        # --- 左侧：参数 + 按钮 + 结果 ---
        left = QVBoxLayout()

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
        self.btn_save_result = QPushButton("保存结果 CSV")
        self.btn_save_plot = QPushButton("保存对比图")
        self.btn_close = QPushButton("结束")

        self.btn_load_meas.setEnabled(False)
        self.btn_match.setEnabled(False)
        self.btn_evaluate.setEnabled(False)
        self.btn_save_result.setEnabled(False)
        self.btn_save_plot.setEnabled(False)

        for btn in (
            self.btn_load_cal, self.btn_load_meas, self.btn_match,
            self.btn_evaluate, self.btn_save_result, self.btn_save_plot,
            self.btn_close,
        ):
            btn_layout.addWidget(btn)

        btn_group.setLayout(btn_layout)
        left.addWidget(btn_group)

        # 正/负显示切换
        from PySide6.QtWidgets import QComboBox
        self.sign_combo = QComboBox()
        self.sign_combo.addItems(["Δλ > 0（升温）", "Δλ < 0（降温）"])
        self.sign_combo.currentIndexChanged.connect(self._on_sign_changed)
        left.addWidget(QLabel("显示组:"))
        left.addWidget(self.sign_combo)

        # 状态标签
        self.cal_status = QLabel("定标: 未加载")
        self.meas_status = QLabel("测量: 未加载")
        left.addWidget(self.cal_status)
        left.addWidget(self.meas_status)

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
        main_layout.addLayout(left)

        # --- 右侧：图表 ---
        self.chart = ChartWidget()
        main_layout.addWidget(self.chart, stretch=1)

        # 信号连接
        self.btn_load_cal.clicked.connect(self._on_load_cal_clicked)
        self.btn_load_meas.clicked.connect(self._on_load_meas_clicked)
        self.btn_match.clicked.connect(self._on_match_clicked)
        self.btn_evaluate.clicked.connect(self._on_evaluate_clicked)
        self.btn_save_result.clicked.connect(self._on_save_result_clicked)
        self.btn_save_plot.clicked.connect(self._on_save_plot_clicked)
        self.btn_close.clicked.connect(self._on_close_clicked)

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
        self._worker.error_occurred.connect(self._on_error)
        self._worker.operation_finished.connect(self._on_operation_finished)

        self._thread.start()

    # ==================================================================
    # 按钮槽
    # ==================================================================

    def _on_load_cal_clicked(self):
        directory = QFileDialog.getExistingDirectory(self, "选择定标数据目录")
        if not directory:
            return
        self._cal_dir = directory
        self._set_busy(True)
        self._worker.load_calibration(directory, self.smooth_input.value())

    def _on_load_meas_clicked(self):
        """加载测量数据 — 支持目录（多个 CSV）或单个合并 CSV。"""
        from PySide6.QtWidgets import QInputDialog
        choice, ok = QInputDialog.getItem(
            self, "选择加载方式",
            "测量数据来源:",
            ["目录（每个电压一个 CSV）", "单个 CSV 文件（电压扫描导出）"],
            0, False,
        )
        if not ok:
            return
        if "目录" in choice:
            directory = QFileDialog.getExistingDirectory(self, "选择测量数据目录")
            if not directory:
                return
            self._meas_dir = directory
            self._set_busy(True)
            self._worker.load_measurement(directory)
        else:
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

    def _on_evaluate_clicked(self):
        self._set_busy(True)
        self._worker.run_evaluate(
            alpha=self.alpha_input.value(),
            t0=self.t0_input.value(),
            lambda_ref=self.lambda_ref_input.value(),
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
        self.btn_load_meas.setEnabled(True)
        self._log.append_log(f"定标数据加载完成，共 {count} 条曲线", "INFO")
        self._plot_cal_curves()

    @Slot(int)
    def _on_meas_loaded(self, count: int):
        self.meas_status.setText(f"测量: 已加载 {count} 条曲线")
        self.btn_match.setEnabled(True)
        self._log.append_log(f"测量数据加载完成，共 {count} 条曲线", "INFO")

    @Slot(object)
    def _on_match_done(self, match_info: dict):
        self.btn_evaluate.setEnabled(True)
        self.btn_save_result.setEnabled(True)
        self.btn_save_plot.setEnabled(True)
        self._match_results = match_info.get("all_match_results", {})
        self._display_match_results()
        self._log.append_log("匹配完成（四种方式 × 正/负 Δλ）", "INFO")

    @Slot(object)
    def _on_evaluate_done(self, eval_result: dict):
        self.btn_save_plot.setEnabled(True)
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
        for btn in (
            self.btn_load_cal,
            self.btn_load_meas,
            self.btn_match,
            self.btn_evaluate,
        ):
            if busy:
                btn.setEnabled(False)
            # 恢复时由各回调单独控制

    def _plot_cal_curves(self):
        """绘制所有定标曲线概览。"""
        cal_curves = self._worker._cal_curves
        if not cal_curves:
            return
        self.chart.figure.clear()
        ax = self.chart.figure.add_subplot(111)
        for dl, curve in cal_curves:
            ax.plot(curve.frequency, curve.magnitude, linewidth=0.8,
                    alpha=0.7, label=f"Δλ={dl:.0f}pm")
        ax.set_xlabel("频率 (GHz)")
        ax.set_ylabel("幅度 (dB)")
        ax.set_title("定标曲线集")
        if len(cal_curves) <= 10:
            ax.legend(fontsize=7, loc="upper right")
        ax.grid(True, alpha=0.3)
        self.chart.ax = ax
        self.chart.figure.tight_layout()
        self.chart.canvas.draw_idle()

    def _plot_match_comparison(self, match_info: dict):
        """绘制最佳匹配对比图。"""
        meas_curve = match_info.get("best_meas_curve")
        cal_curve = match_info.get("best_cal_curve")
        if meas_curve is None or cal_curve is None:
            return

        self.chart.figure.clear()
        ax = self.chart.figure.add_subplot(111)
        ax.plot(meas_curve.frequency, meas_curve.magnitude,
                color="tab:blue", linewidth=1,
                label=f"实测 (V={match_info['best_voltage']:.2f}V)")
        ax.plot(cal_curve.frequency, cal_curve.magnitude,
                color="tab:red", linestyle="--", linewidth=1,
                label=f"定标 (Δλ={match_info['best_delta_lambda']:.0f}pm)")
        ax.set_xlabel("频率 (GHz)")
        ax.set_ylabel("幅度 (dB)")
        ax.set_title(f"曲线匹配对比  ρ={match_info['best_rho']:.4f}")
        ax.legend()
        ax.grid(True, alpha=0.3)
        self.chart.ax = ax
        self.chart.figure.tight_layout()
        self.chart.canvas.draw_idle()

    # ==================================================================
    # 清理
    # ==================================================================

    def _display_match_results(self):
        """显示当前选中正/负组的四种匹配结果。"""
        if not hasattr(self, '_match_results') or not self._match_results:
            return
        sign_key = "Δλ>0" if self.sign_combo.currentIndex() == 0 else "Δλ<0"
        sign_data = self._match_results.get(sign_key, {})
        if not sign_data:
            self.result_text.setPlainText(f"{sign_key} 组无匹配结果")
            return

        lines = [f"=== {sign_key} 匹配结果 ===\n"]
        for mode, info in sign_data.items():
            lines.append(
                f"{info['mode_name']}:\n"
                f"  V={info['best_voltage']:.2f}V  "
                f"ρ={info['best_rho']:.4f}  "
                f"Δλ={info['best_delta_lambda']:.2f}pm\n"
            )
        self.result_text.setPlainText("".join(lines))

        # 绘制四种方式的对比图
        self._plot_all_modes(sign_data)

    def _on_sign_changed(self, _index: int):
        """切换正/负显示。"""
        self._display_match_results()

    def _on_close_clicked(self):
        """结束操作，重置状态。"""
        self._log.append_log("定标流水线已结束", "INFO")
        self._cal_dir = None
        self._meas_dir = None
        self._pipeline_result = None
        self.btn_load_cal.setEnabled(True)
        self.btn_load_meas.setEnabled(False)
        self.btn_match.setEnabled(False)
        self.btn_evaluate.setEnabled(False)
        self.btn_save_result.setEnabled(False)
        self.btn_save_plot.setEnabled(False)
        self.cal_status.setText("定标: 未加载")
        self.meas_status.setText("测量: 未加载")
        self.result_text.clear()
        self.chart.clear()
        self.chart.canvas.draw_idle()

    def _plot_all_modes(self, sign_data: dict):
        """绘制四种匹配方式的对比图（2×2 子图）。"""
        self.chart.figure.clear()
        modes = list(sign_data.keys())
        n = len(modes)
        if n == 0:
            self.chart.canvas.draw_idle()
            return
        rows = 2 if n > 2 else 1
        cols = 2 if n > 1 else 1

        for i, mode in enumerate(modes):
            info = sign_data[mode]
            ax = self.chart.figure.add_subplot(rows, cols, i + 1)
            meas = info.get("best_meas_curve")
            cal = info.get("best_cal_curve")
            if meas is not None:
                ax.plot(meas.frequency, meas.magnitude, "b-", linewidth=0.8,
                        label=f"实测 V={info['best_voltage']:.2f}V")
            if cal is not None:
                ax.plot(cal.frequency, cal.magnitude, "r--", linewidth=0.8,
                        label=f"定标 Δλ={info['best_delta_lambda']:.0f}pm")
            ax.set_title(f"{info['mode_name']}  ρ={info['best_rho']:.3f}", fontsize=9)
            ax.set_xlabel("频率 (GHz)", fontsize=8)
            ax.set_ylabel("幅度 (dB)", fontsize=8)
            ax.legend(fontsize=6)
            ax.grid(True, alpha=0.3)
            ax.tick_params(labelsize=7)

        self.chart.ax = self.chart.figure.axes[0] if self.chart.figure.axes else None
        self.chart.figure.tight_layout()
        self.chart.canvas.draw_idle()

    def cleanup(self):
        if self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(3000)

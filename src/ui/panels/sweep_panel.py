"""Sweep_Panel — 定标扫描面板

对应 sweep_controller.py 的 SweepController 流程：
1. 配置扫描参数（Vref、波长范围、VNA 参数等）
2. 初始化仪器（Zynq 电压 + VNA）
3. 执行定标扫描（逐点设置波长 → VNA 测量 → 保存 CSV）
4. 支持暂停/恢复/中止
5. 扫描完成后可构建定标表

通过 SweepWorker + QThread 在后台执行仪器操作。
"""

import logging
from typing import Optional

from PySide6.QtCore import QThread, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.ui.chart_widget import ChartWidget
from src.ui.connection_manager import ConnectionManager
from src.ui.log_console import LogConsole
from src.ui.workers import SweepWorker

logger = logging.getLogger(__name__)


class SweepPanel(QWidget):
    """定标扫描面板。"""

    def __init__(
        self,
        connection_manager: ConnectionManager,
        log_console: LogConsole,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._conn_mgr = connection_manager
        self._log = log_console
        self._results = []

        self._init_ui()
        self._init_worker()

    # ==================================================================
    # UI 构建
    # ==================================================================

    def _init_ui(self):
        main_layout = QHBoxLayout(self)

        # --- 左侧：参数 + 按钮（可滚动） ---
        from PySide6.QtWidgets import QScrollArea
        from PySide6.QtCore import Qt

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setMaximumWidth(340)

        left_widget = QWidget()
        left = QVBoxLayout(left_widget)
        left.setContentsMargins(4, 4, 4, 4)
        left.setSpacing(6)

        # 微环 + 波长参数合并为一组
        param_group = QGroupBox("扫描参数")
        param_form = QFormLayout()
        param_form.setSpacing(4)

        self.vref_input = QDoubleSpinBox()
        self.vref_input.setRange(0.0, 10.0)
        self.vref_input.setDecimals(3)
        self.vref_input.setSuffix(" V")
        self.vref_input.setValue(5.0)
        param_form.addRow("Vref:", self.vref_input)

        self.zynq_ch_input = QSpinBox()
        self.zynq_ch_input.setRange(1, 4)
        self.zynq_ch_input.setValue(1)
        param_form.addRow("Zynq 通道:", self.zynq_ch_input)

        self.lambda_ref_input = QDoubleSpinBox()
        self.lambda_ref_input.setRange(1000.0, 1700.0)
        self.lambda_ref_input.setDecimals(3)
        self.lambda_ref_input.setSuffix(" nm")
        self.lambda_ref_input.setValue(1550.0)
        param_form.addRow("λ_ref:", self.lambda_ref_input)

        self.dl_start_input = QDoubleSpinBox()
        self.dl_start_input.setRange(-5000.0, 5000.0)
        self.dl_start_input.setDecimals(1)
        self.dl_start_input.setSuffix(" pm")
        self.dl_start_input.setValue(-500.0)
        param_form.addRow("Δλ 起始:", self.dl_start_input)

        self.dl_stop_input = QDoubleSpinBox()
        self.dl_stop_input.setRange(-5000.0, 5000.0)
        self.dl_stop_input.setDecimals(1)
        self.dl_stop_input.setSuffix(" pm")
        self.dl_stop_input.setValue(500.0)
        param_form.addRow("Δλ 终止:", self.dl_stop_input)

        self.dl_step_input = QDoubleSpinBox()
        self.dl_step_input.setRange(0.1, 1000.0)
        self.dl_step_input.setDecimals(1)
        self.dl_step_input.setSuffix(" pm")
        self.dl_step_input.setValue(50.0)
        param_form.addRow("Δλ 步长:", self.dl_step_input)

        self.vna_start_freq = QDoubleSpinBox()
        self.vna_start_freq.setRange(0, 50)
        self.vna_start_freq.setDecimals(3)
        self.vna_start_freq.setSuffix(" GHz")
        self.vna_start_freq.setValue(0.01)
        param_form.addRow("VNA 起始:", self.vna_start_freq)

        self.vna_stop_freq = QDoubleSpinBox()
        self.vna_stop_freq.setRange(0, 50)
        self.vna_stop_freq.setDecimals(3)
        self.vna_stop_freq.setSuffix(" GHz")
        self.vna_stop_freq.setValue(30.0)
        param_form.addRow("VNA 终止:", self.vna_stop_freq)

        self.vna_points_input = QSpinBox()
        self.vna_points_input.setRange(1, 100001)
        self.vna_points_input.setValue(6001)
        param_form.addRow("VNA 点数:", self.vna_points_input)

        self.output_dir_input = QLineEdit("./sweep_data")
        param_form.addRow("输出目录:", self.output_dir_input)

        param_group.setLayout(param_form)
        left.addWidget(param_group)

        # 操作按钮
        btn_group = QGroupBox("操作")
        btn_layout = QVBoxLayout()
        btn_layout.setSpacing(4)

        self.btn_init = QPushButton("初始化仪器")
        self.btn_start = QPushButton("开始扫描")

        btn_row = QHBoxLayout()
        self.btn_pause = QPushButton("暂停")
        self.btn_resume = QPushButton("恢复")
        self.btn_abort = QPushButton("中止")
        btn_row.addWidget(self.btn_pause)
        btn_row.addWidget(self.btn_resume)
        btn_row.addWidget(self.btn_abort)

        self.btn_build_table = QPushButton("构建定标表")

        self.btn_start.setEnabled(False)
        self.btn_pause.setEnabled(False)
        self.btn_resume.setEnabled(False)
        self.btn_abort.setEnabled(False)
        self.btn_build_table.setEnabled(False)

        btn_layout.addWidget(self.btn_init)
        btn_layout.addWidget(self.btn_start)
        btn_layout.addLayout(btn_row)
        btn_layout.addWidget(self.btn_build_table)

        btn_group.setLayout(btn_layout)
        left.addWidget(btn_group)

        # 进度条 + 状态
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        left.addWidget(self.progress_bar)

        self.status_label = QLabel("状态: 未初始化")
        left.addWidget(self.status_label)

        left.addStretch()
        scroll.setWidget(left_widget)
        main_layout.addWidget(scroll)

        # --- 右侧：图表 + 结果 ---
        right = QVBoxLayout()
        self.chart = ChartWidget()
        right.addWidget(self.chart, stretch=1)

        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setMaximumHeight(120)
        right.addWidget(self.result_text)

        main_layout.addLayout(right, stretch=1)

        # 信号连接
        self.btn_init.clicked.connect(self._on_init_clicked)
        self.btn_start.clicked.connect(self._on_start_clicked)
        self.btn_pause.clicked.connect(self._on_pause_clicked)
        self.btn_resume.clicked.connect(self._on_resume_clicked)
        self.btn_abort.clicked.connect(self._on_abort_clicked)
        self.btn_build_table.clicked.connect(self._on_build_table_clicked)

    # ==================================================================
    # Worker / Thread
    # ==================================================================

    def _init_worker(self):
        self._thread = QThread()
        self._worker = SweepWorker()
        self._worker.moveToThread(self._thread)

        self._worker.initialized.connect(self._on_initialized)
        self._worker.sweep_progress.connect(self._on_sweep_progress)
        self._worker.sweep_finished.connect(self._on_sweep_finished)
        self._worker.table_built.connect(self._on_table_built)
        self._worker.error_occurred.connect(self._on_error)
        self._worker.operation_finished.connect(self._on_operation_finished)

        self._thread.start()

    # ==================================================================
    # 按钮槽
    # ==================================================================

    def _on_init_clicked(self):
        config = self._collect_config()
        self._set_busy(True)
        self._worker.initialize(config)

    def _on_start_clicked(self):
        self._set_busy(True)
        self.btn_pause.setEnabled(True)
        self.btn_abort.setEnabled(True)
        self.btn_start.setEnabled(False)
        self.progress_bar.setValue(0)
        self.status_label.setText("状态: 扫描中...")
        self._worker.run_sweep()

    def _on_pause_clicked(self):
        self._worker.pause()
        self.btn_pause.setEnabled(False)
        self.btn_resume.setEnabled(True)
        self.status_label.setText("状态: 已暂停")

    def _on_resume_clicked(self):
        self._worker.resume()
        self.btn_resume.setEnabled(False)
        self.btn_pause.setEnabled(True)
        self.status_label.setText("状态: 扫描中...")

    def _on_abort_clicked(self):
        self._worker.abort()
        self.btn_pause.setEnabled(False)
        self.btn_resume.setEnabled(False)
        self.btn_abort.setEnabled(False)
        self.status_label.setText("状态: 正在中止...")

    def _on_build_table_clicked(self):
        self._set_busy(True)
        self._worker.build_calibration_table()

    # ==================================================================
    # Worker 回调槽
    # ==================================================================

    @Slot(bool)
    def _on_initialized(self, success: bool):
        if success:
            self.btn_init.setEnabled(False)
            self.btn_start.setEnabled(True)
            self.status_label.setText("状态: 已初始化，可开始扫描")
            self._log.append_log("定标扫描仪器初始化成功", "INFO")
        else:
            self._log.append_log("定标扫描仪器初始化失败", "ERROR")

    @Slot(int, int)
    def _on_sweep_progress(self, current: int, total: int):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        self.status_label.setText(f"状态: 扫描中 {current}/{total}")

    @Slot(object)
    def _on_sweep_finished(self, results: list):
        self._results = results
        self.btn_pause.setEnabled(False)
        self.btn_resume.setEnabled(False)
        self.btn_abort.setEnabled(False)
        self.btn_start.setEnabled(True)
        self.btn_build_table.setEnabled(True)

        success = sum(1 for r in results if r.success)
        skipped = sum(1 for r in results if not r.success)
        self.status_label.setText(f"状态: 扫描完成 (采集 {success}, 跳过 {skipped})")
        self.result_text.setPlainText(
            f"扫描完成\n采集: {success} 条\n跳过: {skipped} 条\n总计: {len(results)} 条"
        )
        self._plot_results(results)
        self._log.append_log(f"定标扫描完成: 采集 {success} 条, 跳过 {skipped} 条", "INFO")

    @Slot(int)
    def _on_table_built(self, count: int):
        self.result_text.append(f"\n定标表已构建，共 {count} 条记录")
        self._log.append_log(f"定标表构建完成，共 {count} 条记录", "INFO")

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

    def _collect_config(self) -> dict:
        return {
            "vref": self.vref_input.value(),
            "zynq_channel": self.zynq_ch_input.value(),
            "lambda_ref": self.lambda_ref_input.value(),
            "delta_lambda_start": self.dl_start_input.value(),
            "delta_lambda_stop": self.dl_stop_input.value(),
            "delta_lambda_step": self.dl_step_input.value(),
            "vna_start_freq": self.vna_start_freq.value() * 1e9,
            "vna_stop_freq": self.vna_stop_freq.value() * 1e9,
            "vna_points": self.vna_points_input.value(),
            "output_dir": self.output_dir_input.text().strip(),
        }

    def _set_busy(self, busy: bool):
        if busy:
            self.btn_init.setEnabled(False)
            self.btn_build_table.setEnabled(False)

    def _plot_results(self, results: list):
        """绘制所有成功采集的 S21 曲线。"""
        self.chart.figure.clear()
        ax = self.chart.figure.add_subplot(111)
        for r in results:
            if r.success and len(r.frequency) > 0:
                freq_ghz = r.frequency / 1e9
                ax.plot(freq_ghz, r.magnitude_dB, linewidth=0.7,
                        alpha=0.7, label=f"Δλ={r.delta_lambda:.0f}pm")
        ax.set_xlabel("频率 (GHz)")
        ax.set_ylabel("幅度 (dB)")
        ax.set_title("定标扫描 S21 曲线集")
        if len([r for r in results if r.success]) <= 15:
            ax.legend(fontsize=6, loc="upper right")
        ax.grid(True, alpha=0.3)
        self.chart.ax = ax
        self.chart.figure.tight_layout()
        self.chart.canvas.draw_idle()

    # ==================================================================
    # 清理
    # ==================================================================

    def cleanup(self):
        if self._thread.isRunning():
            self._worker.abort()
            self._thread.quit()
            self._thread.wait(3000)

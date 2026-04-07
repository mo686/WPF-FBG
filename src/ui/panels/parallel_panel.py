"""Parallel_Panel — 并行控制面板

提供并行控制器配置、初始化、并行测量、电压扫描、紧急停止、结果导出功能。
结果表格显示每个测量点的 session_id、voltages_applied、optical_status、vna_status。
进度条显示扫描进度。通过 ParallelWorker + QThread 在后台执行仪器操作。
"""

import csv
import logging
from typing import List, Optional

from PySide6.QtCore import QThread, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import Qt

from src.ui.connection_manager import ConnectionManager
from src.ui.log_console import LogConsole
from src.ui.workers import ParallelWorker

logger = logging.getLogger(__name__)

# 电压范围常量（与 Zynq 控制器一致）
VOLTAGE_MIN = 0.0
VOLTAGE_MAX = 10.0
DEFAULT_NUM_CHANNELS = 4


class ParallelPanel(QWidget):
    """并行控制面板。"""

    def __init__(
        self,
        connection_manager: ConnectionManager,
        log_console: LogConsole,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._conn_mgr = connection_manager
        self._log = log_console
        self._voltage_inputs: List[QDoubleSpinBox] = []
        self._results: list = []
        self._initialized = False

        self._init_ui()
        self._init_worker()

    # ==================================================================
    # UI 构建
    # ==================================================================

    def _init_ui(self):
        main_layout = QVBoxLayout(self)

        splitter = QSplitter(Qt.Vertical)

        # --- 上半部分：控制区 ---
        top_widget = QWidget()
        top_layout = QHBoxLayout(top_widget)

        # --- 左列：配置 + 操作按钮 ---
        left_col = QVBoxLayout()

        # 配置组
        config_group = QGroupBox("并行控制器配置")
        config_form = QFormLayout()

        self.settle_time_input = QDoubleSpinBox()
        self.settle_time_input.setRange(0.0, 60.0)
        self.settle_time_input.setDecimals(2)
        self.settle_time_input.setValue(0.5)
        self.settle_time_input.setSuffix(" s")
        config_form.addRow("电压稳定等待时间:", self.settle_time_input)

        self.max_workers_input = QSpinBox()
        self.max_workers_input.setRange(1, 16)
        self.max_workers_input.setValue(2)
        config_form.addRow("最大工作线程数:", self.max_workers_input)

        self.output_dir_input = QLineEdit("./parallel_results")
        config_form.addRow("输出目录:", self.output_dir_input)

        config_group.setLayout(config_form)
        left_col.addWidget(config_group)

        # 操作按钮组
        btn_group = QGroupBox("操作")
        btn_layout = QVBoxLayout()

        self.btn_initialize = QPushButton("初始化")
        self.btn_emergency_stop = QPushButton("紧急停止")
        self.btn_emergency_stop.setStyleSheet("background-color: #ff4444; color: white; font-weight: bold;")
        self.btn_export = QPushButton("导出结果")
        self.btn_export.setEnabled(False)

        btn_layout.addWidget(self.btn_initialize)
        btn_layout.addWidget(self.btn_emergency_stop)
        btn_layout.addWidget(self.btn_export)

        btn_group.setLayout(btn_layout)
        left_col.addWidget(btn_group)

        left_col.addStretch()
        top_layout.addLayout(left_col)

        # --- 中列：电压输入 + 并行测量 ---
        mid_col = QVBoxLayout()

        voltage_group = QGroupBox("电压设置 + 并行测量")
        voltage_outer = QVBoxLayout()

        self.include_vna_check = QCheckBox("包含 VNA 测量")
        self.include_vna_check.setChecked(True)
        voltage_outer.addWidget(self.include_vna_check)

        # 可滚动的电压输入区
        self._voltage_container = QWidget()
        self._voltage_layout = QVBoxLayout(self._voltage_container)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._voltage_container)
        voltage_outer.addWidget(scroll, stretch=1)

        self.btn_parallel_measure = QPushButton("并行测量")
        self.btn_parallel_measure.setEnabled(False)
        voltage_outer.addWidget(self.btn_parallel_measure)

        voltage_group.setLayout(voltage_outer)
        mid_col.addWidget(voltage_group)
        top_layout.addLayout(mid_col, stretch=1)

        # --- 右列：电压扫描配置 ---
        right_col = QVBoxLayout()

        sweep_group = QGroupBox("电压扫描")
        sweep_form = QFormLayout()

        self.sweep_channel_input = QSpinBox()
        self.sweep_channel_input.setRange(1, DEFAULT_NUM_CHANNELS)
        self.sweep_channel_input.setValue(1)
        sweep_form.addRow("扫描通道:", self.sweep_channel_input)

        self.sweep_start_input = QDoubleSpinBox()
        self.sweep_start_input.setRange(VOLTAGE_MIN, VOLTAGE_MAX)
        self.sweep_start_input.setDecimals(3)
        self.sweep_start_input.setValue(0.0)
        self.sweep_start_input.setSuffix(" V")
        sweep_form.addRow("起始电压:", self.sweep_start_input)

        self.sweep_end_input = QDoubleSpinBox()
        self.sweep_end_input.setRange(VOLTAGE_MIN, VOLTAGE_MAX)
        self.sweep_end_input.setDecimals(3)
        self.sweep_end_input.setValue(5.0)
        self.sweep_end_input.setSuffix(" V")
        sweep_form.addRow("终止电压:", self.sweep_end_input)

        self.sweep_step_input = QDoubleSpinBox()
        self.sweep_step_input.setRange(0.001, VOLTAGE_MAX)
        self.sweep_step_input.setDecimals(3)
        self.sweep_step_input.setValue(0.5)
        self.sweep_step_input.setSuffix(" V")
        sweep_form.addRow("步进电压:", self.sweep_step_input)

        self.sweep_include_vna_check = QCheckBox("包含 VNA 测量")
        self.sweep_include_vna_check.setChecked(True)
        sweep_form.addRow(self.sweep_include_vna_check)

        sweep_group.setLayout(sweep_form)
        right_col.addWidget(sweep_group)

        self.btn_start_sweep = QPushButton("开始扫描")
        self.btn_start_sweep.setEnabled(False)
        right_col.addWidget(self.btn_start_sweep)

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        right_col.addWidget(self.progress_bar)

        right_col.addStretch()
        top_layout.addLayout(right_col)

        splitter.addWidget(top_widget)

        # --- 下半部分：结果表格 ---
        bottom_widget = QWidget()
        bottom_layout = QVBoxLayout(bottom_widget)

        self.result_table = QTableWidget()
        self.result_table.setColumnCount(4)
        self.result_table.setHorizontalHeaderLabels(
            ["session_id", "voltages_applied", "optical_status", "vna_status"]
        )
        self.result_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.result_table.setEditTriggers(QTableWidget.NoEditTriggers)
        bottom_layout.addWidget(self.result_table)

        splitter.addWidget(bottom_widget)
        main_layout.addWidget(splitter)

        # 生成默认电压输入控件
        self._rebuild_voltage_controls(DEFAULT_NUM_CHANNELS)

        # 信号连接
        self.btn_initialize.clicked.connect(self._on_initialize_clicked)
        self.btn_parallel_measure.clicked.connect(self._on_parallel_measure_clicked)
        self.btn_start_sweep.clicked.connect(self._on_start_sweep_clicked)
        self.btn_emergency_stop.clicked.connect(self._on_emergency_stop_clicked)
        self.btn_export.clicked.connect(self._on_export_clicked)

    def _rebuild_voltage_controls(self, num_channels: int):
        """根据通道数量动态生成电压输入控件。"""
        while self._voltage_layout.count():
            item = self._voltage_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        self._voltage_inputs.clear()

        for i in range(num_channels):
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)

            ch_label = QLabel(f"通道 {i + 1}:")
            ch_label.setFixedWidth(60)

            spin = QDoubleSpinBox()
            spin.setRange(VOLTAGE_MIN, VOLTAGE_MAX)
            spin.setDecimals(3)
            spin.setSuffix(" V")
            spin.setValue(0.0)

            row_layout.addWidget(ch_label)
            row_layout.addWidget(spin, stretch=1)

            self._voltage_layout.addWidget(row_widget)
            self._voltage_inputs.append(spin)

        self._voltage_layout.addStretch()

    # ==================================================================
    # Worker / Thread 初始化
    # ==================================================================

    def _init_worker(self):
        self._thread = QThread()
        self._worker = ParallelWorker()
        self._worker.moveToThread(self._thread)

        # Worker 信号 → UI 槽
        self._worker.initialized.connect(self._on_initialized)
        self._worker.result_ready.connect(self._on_result_ready)
        self._worker.sweep_progress.connect(self._on_sweep_progress)
        self._worker.sweep_finished.connect(self._on_sweep_finished)
        self._worker.error_occurred.connect(self._on_error)
        self._worker.operation_finished.connect(self._on_operation_finished)

        self._thread.start()

    # ==================================================================
    # 按钮槽
    # ==================================================================

    def _on_initialize_clicked(self):
        self._set_busy(True)
        config = {
            "voltage_settle_time": self.settle_time_input.value(),
            "max_workers": self.max_workers_input.value(),
            "output_dir": self.output_dir_input.text().strip(),
        }
        self._worker.initialize(config)

    def _on_parallel_measure_clicked(self):
        voltages = [spin.value() for spin in self._voltage_inputs]
        include_vna = self.include_vna_check.isChecked()
        self._set_busy(True)
        self._worker.run_parallel(voltages, include_vna)

    def _on_start_sweep_clicked(self):
        start_v = self.sweep_start_input.value()
        end_v = self.sweep_end_input.value()
        step_v = self.sweep_step_input.value()

        if step_v <= 0:
            QMessageBox.warning(self, "警告", "步进电压必须大于 0")
            return
        if start_v >= end_v:
            QMessageBox.warning(self, "警告", "起始电压必须小于终止电压")
            return

        num_steps = int(round((end_v - start_v) / step_v)) + 1
        self.progress_bar.setMaximum(num_steps)
        self.progress_bar.setValue(0)

        params = {
            "channel": self.sweep_channel_input.value(),
            "start_voltage": start_v,
            "end_voltage": end_v,
            "step_voltage": step_v,
            "include_vna": self.sweep_include_vna_check.isChecked(),
        }
        self._set_busy(True)
        self._worker.run_sweep(params)

    def _on_emergency_stop_clicked(self):
        self._worker.emergency_stop()
        self._log.append_log("紧急停止已触发", "WARNING")

    def _on_export_clicked(self):
        if not self._results:
            QMessageBox.warning(self, "警告", "没有可导出的结果数据")
            return
        filepath, _ = QFileDialog.getSaveFileName(
            self, "导出结果", "", "CSV 文件 (*.csv)"
        )
        if not filepath:
            return
        try:
            self._export_csv(filepath)
            self._log.append_log(f"结果已导出至 {filepath}", "INFO")
        except Exception as exc:
            self._on_error(f"导出失败: {exc}")

    # ==================================================================
    # Worker 回调槽
    # ==================================================================

    @Slot(bool)
    def _on_initialized(self, success: bool):
        if success:
            self._initialized = True
            self._conn_mgr.register_instrument(
                "Parallel",
                connect_fn=lambda: True,
                disconnect_fn=lambda: True,
            )
            self._conn_mgr.connect_instrument("Parallel")
            self.btn_initialize.setEnabled(False)
            self.btn_parallel_measure.setEnabled(True)
            self.btn_start_sweep.setEnabled(True)
            # 锁定配置
            self.settle_time_input.setEnabled(False)
            self.max_workers_input.setEnabled(False)
            self.output_dir_input.setEnabled(False)
            self._log.append_log("并行控制器初始化成功", "INFO")
        else:
            self._log.append_log("并行控制器初始化失败", "ERROR")

    @Slot(object)
    def _on_result_ready(self, result):
        """单次并行测量结果。"""
        self._results.append(result)
        self._add_result_row(result)
        self.btn_export.setEnabled(True)
        self._log.append_log(f"并行测量完成: {result.session_id}", "INFO")

    @Slot(int, int)
    def _on_sweep_progress(self, current: int, total: int):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)

    @Slot(list)
    def _on_sweep_finished(self, results: list):
        for r in results:
            self._results.append(r)
            self._add_result_row(r)
        self.btn_export.setEnabled(True)
        self._log.append_log(f"电压扫描完成，共 {len(results)} 个测量点", "INFO")

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
        """操作进行中时禁用按钮（紧急停止始终可用）。"""
        self.btn_initialize.setEnabled(not busy and not self._initialized)
        self.btn_parallel_measure.setEnabled(not busy and self._initialized)
        self.btn_start_sweep.setEnabled(not busy and self._initialized)
        # 紧急停止始终可用 — 不在此处禁用

    def _add_result_row(self, result):
        """向结果表格添加一行。"""
        row = self.result_table.rowCount()
        self.result_table.insertRow(row)

        self.result_table.setItem(row, 0, QTableWidgetItem(str(result.session_id)))

        voltages_str = ""
        if result.voltages_applied:
            voltages_str = ", ".join(f"{v:.3f}" for v in result.voltages_applied)
        self.result_table.setItem(row, 1, QTableWidgetItem(voltages_str))

        optical_status = result.optical_status.value if hasattr(result.optical_status, "value") else str(result.optical_status)
        self.result_table.setItem(row, 2, QTableWidgetItem(optical_status))

        vna_status = result.vna_status.value if hasattr(result.vna_status, "value") else str(result.vna_status)
        self.result_table.setItem(row, 3, QTableWidgetItem(vna_status))

    def _export_csv(self, filepath: str):
        """将结果导出为 CSV。"""
        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["session_id", "voltages_applied", "optical_status", "vna_status"])
            for r in self._results:
                voltages_str = ""
                if r.voltages_applied:
                    voltages_str = ", ".join(f"{v:.3f}" for v in r.voltages_applied)
                optical_status = r.optical_status.value if hasattr(r.optical_status, "value") else str(r.optical_status)
                vna_status = r.vna_status.value if hasattr(r.vna_status, "value") else str(r.vna_status)
                writer.writerow([r.session_id, voltages_str, optical_status, vna_status])

    # ==================================================================
    # 清理
    # ==================================================================

    def cleanup(self):
        """安全关闭 Worker 线程。"""
        if self._thread.isRunning():
            self._worker.emergency_stop()
            self._worker.shutdown()
            self._thread.quit()
            self._thread.wait(3000)

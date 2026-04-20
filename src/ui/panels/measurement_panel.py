"""Measurement_Panel — 插损测量面板

对应 measure.py 的 InsertionLossMeasurer 流程：
1. 初始化设备（TSL + MPM + DAQ）
2. 配置扫描参数（波长范围、步长、速度、功率、通道、动态范围）
3. 加载参考数据 或 执行参考测量
4. 执行插损测量（减去参考值）
5. 绘图 / 保存数据 / 保存图表

通过 MeasurementWorker + QThread 在后台执行仪器操作。
"""

import json
import logging
import os
from typing import Optional

from PySide6.QtCore import QThread, Qt, Slot
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
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from src.ui.chart_widget import ChartWidget
from src.ui.connection_manager import ConnectionManager
from src.ui.log_console import LogConsole
from src.ui.workers import MeasurementWorker

logger = logging.getLogger(__name__)

# 动态范围选项（与 reference_panel 一致）
_DYNAMIC_RANGES = {
    1: "-30 ~ +10 dBm",
    2: "-40 ~ 0 dBm",
    3: "-50 ~ -10 dBm",
    4: "-60 ~ -20 dBm",
    5: "-80 ~ -30 dBm",
}

_CHANNEL_OPTIONS = {
    "全部通道": [["0", "1"], ["0", "2"], ["0", "3"], ["0", "4"]],
    "偶数通道": [["0", "2"], ["0", "4"]],
    "奇数通道": [["0", "1"], ["0", "3"]],
    "通道 1": [["0", "1"]],
    "通道 2": [["0", "2"]],
    "通道 3": [["0", "3"]],
    "通道 4": [["0", "4"]],
}


class MeasurementPanel(QWidget):
    """插损测量面板。"""

    def __init__(
        self,
        connection_manager: ConnectionManager,
        log_console: LogConsole,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._conn_mgr = connection_manager
        self._log = log_console
        self._reference_data: Optional[list] = None
        self._measurement_data: Optional[list] = None
        self._params_configured = False

        self._init_ui()
        self._init_worker()
        self._register_instrument()

    # ==================================================================
    # UI 构建
    # ==================================================================

    def _init_ui(self):
        main_layout = QHBoxLayout(self)

        # --- 左侧（可滚动） ---
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setMaximumWidth(320)

        left_widget = QWidget()
        left = QVBoxLayout(left_widget)
        left.setContentsMargins(4, 4, 4, 4)
        left.setSpacing(6)

        # 扫描参数组
        param_group = QGroupBox("扫描参数")
        form = QFormLayout()
        form.setSpacing(4)

        self.start_wl = QDoubleSpinBox()
        self.start_wl.setRange(1000.0, 1700.0)
        self.start_wl.setDecimals(3)
        self.start_wl.setSuffix(" nm")
        self.start_wl.setValue(1545.0)
        form.addRow("起始波长:", self.start_wl)

        self.stop_wl = QDoubleSpinBox()
        self.stop_wl.setRange(1000.0, 1700.0)
        self.stop_wl.setDecimals(3)
        self.stop_wl.setSuffix(" nm")
        self.stop_wl.setValue(1555.0)
        form.addRow("终止波长:", self.stop_wl)

        self.sweep_step = QDoubleSpinBox()
        self.sweep_step.setRange(0.001, 10.0)
        self.sweep_step.setDecimals(3)
        self.sweep_step.setSuffix(" pm")
        self.sweep_step.setValue(0.1)
        form.addRow("扫描步长:", self.sweep_step)

        self.sweep_speed = QDoubleSpinBox()
        self.sweep_speed.setRange(0.1, 200.0)
        self.sweep_speed.setDecimals(1)
        self.sweep_speed.setSuffix(" nm/s")
        self.sweep_speed.setValue(1.0)
        form.addRow("扫描速度:", self.sweep_speed)

        self.power_input = QDoubleSpinBox()
        self.power_input.setRange(-10.0, 10.0)
        self.power_input.setDecimals(1)
        self.power_input.setSuffix(" dBm")
        self.power_input.setValue(10.0)
        form.addRow("输出功率:", self.power_input)

        self.channel_combo = QComboBox()
        self.channel_combo.addItems(list(_CHANNEL_OPTIONS.keys()))
        self.channel_combo.setCurrentText("全部通道")
        form.addRow("测量通道:", self.channel_combo)

        self.range_combo = QComboBox()
        for k, v in _DYNAMIC_RANGES.items():
            self.range_combo.addItem(v, k)
        self.range_combo.setCurrentIndex(0)
        form.addRow("动态范围:", self.range_combo)

        param_group.setLayout(form)
        left.addWidget(param_group)

        # 操作按钮组
        btn_group = QGroupBox("操作")
        btn_layout = QVBoxLayout()
        btn_layout.setSpacing(4)

        self.btn_init = QPushButton("初始化设备")
        self.btn_configure = QPushButton("配置参数")
        self.btn_load_ref = QPushButton("加载参考数据")
        self.btn_reference = QPushButton("参考测量")
        self.btn_measure = QPushButton("插损测量")
        self.btn_save_data = QPushButton("保存数据")
        self.btn_save_plot = QPushButton("保存图表")
        self.btn_shutdown = QPushButton("结束操作")

        self.btn_configure.setEnabled(False)
        self.btn_reference.setEnabled(False)
        self.btn_measure.setEnabled(False)
        self.btn_save_data.setEnabled(False)
        self.btn_save_plot.setEnabled(False)
        self.btn_shutdown.setEnabled(False)

        for btn in (
            self.btn_init, self.btn_configure,
            self.btn_load_ref, self.btn_reference,
            self.btn_measure, self.btn_save_data, self.btn_save_plot,
            self.btn_shutdown,
        ):
            btn_layout.addWidget(btn)

        btn_group.setLayout(btn_layout)
        left.addWidget(btn_group)

        # 状态标签
        self.status_label = QLabel("状态: 未初始化")
        self.ref_label = QLabel("参考: 未加载")
        left.addWidget(self.status_label)
        left.addWidget(self.ref_label)

        left.addStretch()
        scroll.setWidget(left_widget)
        main_layout.addWidget(scroll)

        # --- 右侧：图表 ---
        self.chart = ChartWidget()
        main_layout.addWidget(self.chart, stretch=1)

        # 信号连接
        self.btn_init.clicked.connect(self._on_init_clicked)
        self.btn_configure.clicked.connect(self._on_configure_clicked)
        self.btn_load_ref.clicked.connect(self._on_load_ref_clicked)
        self.btn_reference.clicked.connect(self._on_reference_clicked)
        self.btn_measure.clicked.connect(self._on_measure_clicked)
        self.btn_save_data.clicked.connect(self._on_save_data_clicked)
        self.btn_save_plot.clicked.connect(self._on_save_plot_clicked)
        self.btn_shutdown.clicked.connect(self._on_shutdown_clicked)

    # ==================================================================
    # Worker / Thread
    # ==================================================================

    def _init_worker(self):
        self._thread = QThread()
        self._worker = MeasurementWorker()
        self._worker.moveToThread(self._thread)

        self._worker.initialized.connect(self._on_initialized)
        self._worker.params_configured.connect(self._on_params_configured)
        self._worker.ref_loaded.connect(self._on_ref_loaded)
        self._worker.reference_ready.connect(self._on_reference_ready)
        self._worker.measurement_ready.connect(self._on_measurement_ready)
        self._worker.error_occurred.connect(self._on_error)
        self._worker.operation_finished.connect(self._on_operation_finished)

        self._thread.start()

    def _register_instrument(self):
        self._conn_mgr.register_instrument(
            "Measurement", connect_fn=lambda: True, disconnect_fn=lambda: True,
        )

    # ==================================================================
    # 按钮槽
    # ==================================================================

    def _on_init_clicked(self):
        self._set_busy(True)
        self._worker.initialize_devices()

    def _on_configure_clicked(self):
        params = self._collect_params()
        self._set_busy(True)
        self._worker.configure_parameters(params)

    def _on_load_ref_clicked(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, "加载参考数据", "",
            "参考数据文件 (*.json *.dat);;所有文件 (*)"
        )
        if not filepath:
            return
        self._set_busy(True)
        self._worker.load_reference_data(filepath)

    def _on_reference_clicked(self):
        self._set_busy(True)
        self._worker.run_reference()

    def _on_measure_clicked(self):
        self._set_busy(True)
        self._worker.run_measurement()

    def _on_save_data_clicked(self):
        if self._measurement_data is None:
            QMessageBox.warning(self, "警告", "没有可保存的测量数据")
            return
        filepath, _ = QFileDialog.getSaveFileName(
            self, "保存数据", "", "JSON 文件 (*.json)"
        )
        if not filepath:
            return
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(self._measurement_data, f, ensure_ascii=False, indent=2)
            self._log.append_log(f"数据已保存至 {filepath}", "INFO")
        except Exception as exc:
            self._on_error(f"保存数据失败: {exc}")

    def _on_save_plot_clicked(self):
        filepath, _ = QFileDialog.getSaveFileName(
            self, "保存图表", "", "PNG 图片 (*.png)"
        )
        if not filepath:
            return
        try:
            self.chart.save_figure(filepath)
            self._log.append_log(f"图表已保存至 {filepath}", "INFO")
        except Exception as exc:
            self._on_error(f"保存图表失败: {exc}")

    # ==================================================================
    # Worker 回调槽
    # ==================================================================

    @Slot(bool)
    def _on_initialized(self, success: bool):
        if success:
            self._conn_mgr.connect_instrument("Measurement")
            self.btn_init.setEnabled(False)
            self.btn_configure.setEnabled(True)
            self.btn_shutdown.setEnabled(True)
            self.status_label.setText("状态: 已初始化，请配置参数")
            self._log.append_log("测量设备初始化成功", "INFO")
        else:
            self._log.append_log("测量设备初始化失败", "ERROR")

    @Slot(dict)
    def _on_params_configured(self, params: dict):
        self._params_configured = True
        self.btn_reference.setEnabled(True)
        if self._reference_data is not None:
            self.btn_measure.setEnabled(True)
        self.status_label.setText("状态: 参数已配置")
        self._log.append_log("扫描参数配置完成", "INFO")

    @Slot(list)
    def _on_ref_loaded(self, data: list):
        self._reference_data = data
        count = len(data) if data else 0
        self.ref_label.setText(f"参考: 已加载 ({count} 条)")
        if self._params_configured:
            self.btn_measure.setEnabled(True)
        self._plot_reference()
        self._log.append_log(f"参考数据已加载，共 {count} 条", "INFO")

    @Slot(list)
    def _on_reference_ready(self, data: list):
        self._reference_data = data
        count = len(data) if data else 0
        self.ref_label.setText(f"参考: 已测量 ({count} 条)")
        self.btn_measure.setEnabled(True)
        self._plot_reference()
        self._log.append_log("参考测量完成", "INFO")

    @Slot(list)
    def _on_measurement_ready(self, data: list):
        self._measurement_data = data
        self.btn_save_data.setEnabled(True)
        self.btn_save_plot.setEnabled(True)
        self._plot_measurement()
        self._log.append_log("插损测量完成", "INFO")

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

    def _collect_params(self) -> dict:
        channel_key = self.channel_combo.currentText()
        selected_chans = _CHANNEL_OPTIONS.get(channel_key, [["0", "1"]])
        range_val = self.range_combo.currentData()
        return {
            "start_wavelength": self.start_wl.value(),
            "stop_wavelength": self.stop_wl.value(),
            "sweep_step": self.sweep_step.value() / 1000.0,  # pm → nm
            "sweep_speed": self.sweep_speed.value(),
            "power": self.power_input.value(),
            "selected_chans": selected_chans,
            "selected_ranges": [range_val],
        }

    def _set_busy(self, busy: bool):
        self.btn_init.setEnabled(not busy and self.btn_init.isEnabled())
        self.btn_configure.setEnabled(not busy and self.btn_configure.isEnabled())
        self.btn_reference.setEnabled(not busy and self.btn_reference.isEnabled())
        self.btn_measure.setEnabled(not busy and self.btn_measure.isEnabled())
        self.btn_load_ref.setEnabled(not busy)

    def _plot_reference(self):
        self.chart.clear()
        ax = self.chart.ax
        if self._reference_data and isinstance(self._reference_data, list):
            for item in self._reference_data:
                if isinstance(item, dict):
                    wl = item.get("rescaled_wavelength", [])
                    pw = item.get("log_data",
                                  item.get("rescaled_reference_power", []))
                    if wl and pw:
                        min_len = min(len(wl), len(pw))
                        slot = item.get("SlotNumber", "?")
                        ch = item.get("ChannelNumber", "?")
                        ax.plot(wl[:min_len], pw[:min_len], linewidth=1,
                                label=f"参考 Slot{slot} Ch{ch}")
            ax.set_xlabel("Wavelength (nm)")
            ax.set_ylabel("Power (dBm)")
            ax.set_title("Reference Measurement")
            ax.legend(fontsize=8)
            ax.grid(True, alpha=0.3)
        self.chart.canvas.draw_idle()

    def _plot_measurement(self):
        """只绘制插损测量曲线。"""
        self.chart.clear()
        ax = self.chart.ax
        has_data = False
        if self._measurement_data and isinstance(self._measurement_data, list):
            for item in self._measurement_data:
                if isinstance(item, dict):
                    wl = item.get("rescaled_wavelength", [])
                    pw = item.get("rescaled_reference_power", [])
                    if wl and pw:
                        min_len = min(len(wl), len(pw))
                        slot = item.get("SlotNumber", "?")
                        ch = item.get("ChannelNumber", "?")
                        ax.plot(wl[:min_len], pw[:min_len], linewidth=1.5,
                                label=f"Slot{slot} Ch{ch}")
                        has_data = True
        if has_data:
            ax.set_xlabel("Wavelength (nm)")
            ax.set_ylabel("Insertion Loss (dB)")
            ax.set_title("Insertion Loss Measurement")
            ax.legend(loc="upper right", fontsize=8)
            ax.grid(True, alpha=0.3)
        self.chart.canvas.draw_idle()

    def _on_shutdown_clicked(self):
        """结束操作：断开设备连接。"""
        self._log.append_log("正在结束操作...", "INFO")
        if self._worker and self._worker._measurer and self._worker._measurer.reference_measurement:
            ref_meas = self._worker._measurer.reference_measurement
            try:
                if ref_meas.tsl:
                    ref_meas.tsl.query("*RST")
            except Exception:
                pass
            try:
                if ref_meas.mpm:
                    ref_meas.mpm.cls_status
            except Exception:
                pass
        self._conn_mgr.disconnect_instrument("Measurement")
        self.btn_init.setEnabled(True)
        self.btn_configure.setEnabled(False)
        self.btn_reference.setEnabled(False)
        self.btn_measure.setEnabled(False)
        self.btn_save_data.setEnabled(False)
        self.btn_save_plot.setEnabled(False)
        self.btn_shutdown.setEnabled(False)
        self._params_configured = False
        self.status_label.setText("状态: 未初始化")
        self.ref_label.setText("参考: 未加载")
        self._log.append_log("操作已结束，设备已断开", "INFO")

    def cleanup(self):
        if self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(3000)
"""VNA_Panel — 矢量网络分析仪控制面板

提供 GPIB 地址、频率范围、扫描点数、功率、中频带宽、S 参数类型等参数输入，
连接/断开/测量/保存数据/保存图表按钮，
嵌入 ChartWidget 显示幅度/相位双曲线。
通过 VNAWorker + QThread 在后台执行仪器操作。
"""

import csv
import logging
import os
from typing import Optional

import numpy as np
from PySide6.QtCore import QThread, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QDoubleSpinBox,
    QVBoxLayout,
    QWidget,
)

from src.ui.chart_widget import ChartWidget
from src.ui.connection_manager import ConnectionManager
from src.ui.log_console import LogConsole
from src.ui.workers import VNAWorker

logger = logging.getLogger(__name__)

# S 参数选项
_S_PARAMS = ["S11", "S12", "S21", "S22"]


class VNAPanel(QWidget):
    """VNA 矢量网络分析仪控制面板。"""

    def __init__(
        self,
        connection_manager: ConnectionManager,
        log_console: LogConsole,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._conn_mgr = connection_manager
        self._log = log_console
        self._measurement_data: Optional[dict] = None

        self._init_ui()
        self._init_worker()
        self._register_instrument()

    # ==================================================================
    # UI 构建
    # ==================================================================

    def _init_ui(self):
        main_layout = QHBoxLayout(self)

        # --- 左侧：参数 + 按钮 ---
        left = QVBoxLayout()

        # 参数组
        param_group = QGroupBox("参数设置")
        form = QFormLayout()

        self.gpib_address = QSpinBox()
        self.gpib_address.setRange(0, 30)
        self.gpib_address.setValue(16)
        form.addRow("GPIB 地址:", self.gpib_address)

        # 频率单位选择
        self.freq_unit = QComboBox()
        self.freq_unit.addItems(["Hz", "MHz", "GHz"])
        self.freq_unit.setCurrentText("GHz")
        self.freq_unit.currentTextChanged.connect(self._on_freq_unit_changed)
        form.addRow("频率单位:", self.freq_unit)

        self.start_freq = QDoubleSpinBox()
        self.start_freq.setRange(0, 50e9)
        self.start_freq.setDecimals(3)
        self.start_freq.setSuffix(" GHz")
        self.start_freq.setValue(0.01)  # 10 MHz in GHz
        form.addRow("起始频率:", self.start_freq)

        self.stop_freq = QDoubleSpinBox()
        self.stop_freq.setRange(0, 50e9)
        self.stop_freq.setDecimals(3)
        self.stop_freq.setSuffix(" GHz")
        self.stop_freq.setValue(30.0)  # 30 GHz
        form.addRow("终止频率:", self.stop_freq)

        self.points = QSpinBox()
        self.points.setRange(1, 100001)
        self.points.setValue(6001)
        form.addRow("扫描点数:", self.points)

        self.power = QDoubleSpinBox()
        self.power.setRange(-60, 20)
        self.power.setDecimals(1)
        self.power.setSuffix(" dBm")
        self.power.setValue(-10)
        form.addRow("功率:", self.power)

        self.if_bw = QDoubleSpinBox()
        self.if_bw.setRange(1, 1e6)
        self.if_bw.setDecimals(0)
        self.if_bw.setSuffix(" Hz")
        self.if_bw.setValue(1000)
        form.addRow("中频带宽:", self.if_bw)

        self.s_param = QComboBox()
        self.s_param.addItems(_S_PARAMS)
        self.s_param.setCurrentText("S21")
        form.addRow("S 参数:", self.s_param)

        param_group.setLayout(form)
        left.addWidget(param_group)

        # 按钮组
        btn_group = QGroupBox("操作")
        btn_layout = QVBoxLayout()

        self.btn_connect = QPushButton("连接")
        self.btn_disconnect = QPushButton("断开")
        self.btn_measure = QPushButton("测量")
        self.btn_save_data = QPushButton("保存数据")
        self.btn_save_plot = QPushButton("保存图表")

        self.btn_disconnect.setEnabled(False)
        self.btn_measure.setEnabled(False)
        self.btn_save_data.setEnabled(False)
        self.btn_save_plot.setEnabled(False)

        for btn in (
            self.btn_connect,
            self.btn_disconnect,
            self.btn_measure,
            self.btn_save_data,
            self.btn_save_plot,
        ):
            btn_layout.addWidget(btn)

        btn_group.setLayout(btn_layout)
        left.addWidget(btn_group)
        left.addStretch()

        main_layout.addLayout(left)

        # --- 右侧：图表 ---
        self.chart = ChartWidget()
        main_layout.addWidget(self.chart, stretch=1)

        # 信号连接
        self.btn_connect.clicked.connect(self._on_connect_clicked)
        self.btn_disconnect.clicked.connect(self._on_disconnect_clicked)
        self.btn_measure.clicked.connect(self._on_measure_clicked)
        self.btn_save_data.clicked.connect(self._on_save_data_clicked)
        self.btn_save_plot.clicked.connect(self._on_save_plot_clicked)

    # ==================================================================
    # Worker / Thread 初始化
    # ==================================================================

    def _init_worker(self):
        self._thread = QThread()
        self._worker = VNAWorker()
        self._worker.moveToThread(self._thread)

        # Worker 信号 → UI 槽
        self._worker.connected.connect(self._on_connected)
        self._worker.measurement_ready.connect(self._on_measurement_ready)
        self._worker.error_occurred.connect(self._on_error)
        self._worker.operation_finished.connect(self._on_operation_finished)

        self._thread.start()

    # ==================================================================
    # ConnectionManager 注册
    # ==================================================================

    def _register_instrument(self):
        """向 ConnectionManager 注册 VNA 仪器。

        注意：实际连接/断开由 Worker 在后台线程完成，
        这里注册的回调仅用于 ConnectionManager 状态跟踪。
        """
        self._conn_mgr.register_instrument(
            "VNA",
            connect_fn=lambda: True,
            disconnect_fn=lambda: True,
        )

    # ==================================================================
    # 按钮槽
    # ==================================================================

    def _on_freq_unit_changed(self, unit: str):
        """频率单位切换时更新 SpinBox 后缀和范围。"""
        multiplier_map = {"Hz": 1, "MHz": 1e6, "GHz": 1e9}
        old_suffix = self.start_freq.suffix().strip()
        old_mult = multiplier_map.get(old_suffix, 1)
        new_mult = multiplier_map.get(unit, 1)

        # 转换当前值
        for spin in (self.start_freq, self.stop_freq):
            val_hz = spin.value() * old_mult
            spin.blockSignals(True)
            spin.setSuffix(f" {unit}")
            spin.setRange(0, 50e9 / new_mult)
            spin.setValue(val_hz / new_mult)
            spin.blockSignals(False)

    def _get_freq_hz(self, spin: QDoubleSpinBox) -> float:
        """将 SpinBox 的值转换为 Hz。"""
        unit = self.freq_unit.currentText()
        mult = {"Hz": 1, "MHz": 1e6, "GHz": 1e9}.get(unit, 1)
        return spin.value() * mult

    def _on_connect_clicked(self):
        self._set_busy(True)
        params = {
            "gpib_address": self.gpib_address.value(),
            "start_freq": self._get_freq_hz(self.start_freq),
            "stop_freq": self._get_freq_hz(self.stop_freq),
            "points": self.points.value(),
            "power": self.power.value(),
            "if_bw": self.if_bw.value(),
            "param": self.s_param.currentText(),
        }
        # 使用 QMetaObject.invokeMethod 或直接调用（信号方式）
        self._worker.connect_vna(params)

    def _on_disconnect_clicked(self):
        self._set_busy(True)
        self._worker.disconnect_vna()
        self._conn_mgr.disconnect_instrument("VNA")
        self.btn_connect.setEnabled(True)
        self.btn_disconnect.setEnabled(False)
        self.btn_measure.setEnabled(False)

    def _on_measure_clicked(self):
        self._set_busy(True)
        self._worker.measure()

    def _on_save_data_clicked(self):
        if self._measurement_data is None:
            QMessageBox.warning(self, "警告", "没有可保存的测量数据")
            return
        filepath, _ = QFileDialog.getSaveFileName(
            self, "保存数据", "", "CSV 文件 (*.csv)"
        )
        if not filepath:
            return
        try:
            self._save_csv(filepath)
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
    def _on_connected(self, success: bool):
        if success:
            self._conn_mgr.connect_instrument("VNA")
            self.btn_connect.setEnabled(False)
            self.btn_disconnect.setEnabled(True)
            self.btn_measure.setEnabled(True)
            self._log.append_log("VNA 连接成功", "INFO")
        else:
            self._log.append_log("VNA 连接失败", "ERROR")

    @Slot(dict)
    def _on_measurement_ready(self, data: dict):
        self._measurement_data = data
        self.btn_save_data.setEnabled(True)
        self.btn_save_plot.setEnabled(True)
        self._plot_data(data)
        self._log.append_log("VNA 测量完成", "INFO")

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
        """操作进行中时禁用按钮，防止重复触发。"""
        self.btn_connect.setEnabled(not busy and not self.btn_disconnect.isEnabled())
        self.btn_measure.setEnabled(not busy and self.btn_disconnect.isEnabled())

    def _plot_data(self, data: dict):
        """在 ChartWidget 中绘制幅度和相位分别在两个子图中。"""
        self.chart.figure.clear()

        freq = data["frequency"]
        mag = data["magnitude_dB"]
        phase = data["phase_deg"]

        freq_ghz = np.array(freq) / 1e9
        param_name = self.s_param.currentText()

        # 上方子图：幅度
        ax1 = self.chart.figure.add_subplot(2, 1, 1)
        ax1.plot(freq_ghz, mag, "b-", linewidth=1)
        ax1.set_ylabel("Magnitude (dB)")
        ax1.set_title(f"{param_name} Magnitude")

        # 下方子图：相位
        ax2 = self.chart.figure.add_subplot(2, 1, 2)
        ax2.plot(freq_ghz, phase, "r-", linewidth=1)
        ax2.set_xlabel("Frequency (GHz)")
        ax2.set_ylabel("Phase (deg)")
        ax2.set_title(f"{param_name} Phase")

        # 更新 ax 引用（用于鼠标悬停等）
        self.chart.ax = ax1

        self.chart.figure.tight_layout()
        self.chart.canvas.draw_idle()

    def _save_csv(self, filepath: str):
        """将测量数据导出为 CSV（Frequency_Hz, Magnitude_dB, Phase_deg）。"""
        data = self._measurement_data
        with open(filepath, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Frequency_Hz", "Magnitude_dB", "Phase_deg"])
            for freq, mag, phase in zip(
                data["frequency"], data["magnitude_dB"], data["phase_deg"]
            ):
                writer.writerow([freq, mag, phase])

    # ==================================================================
    # 清理
    # ==================================================================

    def cleanup(self):
        """安全关闭 Worker 线程。"""
        if self._thread.isRunning():
            self._worker.disconnect_vna()
            self._thread.quit()
            self._thread.wait(3000)

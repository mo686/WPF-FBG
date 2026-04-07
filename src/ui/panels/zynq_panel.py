"""Zynq_Panel — Zynq FPGA 电压控制面板

提供串口端口、波特率、通道数量配置控件，
根据通道数量动态生成电压输入控件（范围 0V 至 10V），
按钮：连接、断开、应用电压、全部归零。
显示每个通道当前电压值。
通过 ZynqWorker + QThread 在后台执行仪器操作。
"""

import logging
from typing import List, Optional

from PySide6.QtCore import QThread, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from src.ui.connection_manager import ConnectionManager
from src.ui.log_console import LogConsole
from src.ui.workers import ZynqWorker

logger = logging.getLogger(__name__)

# 电压范围常量
VOLTAGE_MIN = 0.0
VOLTAGE_MAX = 10.0


class ZynqPanel(QWidget):
    """Zynq FPGA 电压控制面板。"""

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
        self._voltage_labels: List[QLabel] = []
        self._connected = False

        self._init_ui()
        self._init_worker()
        self._register_instrument()

    # ==================================================================
    # UI 构建
    # ==================================================================

    def _init_ui(self):
        main_layout = QHBoxLayout(self)

        # --- 左侧：配置 + 按钮 ---
        left = QVBoxLayout()

        # 配置组
        config_group = QGroupBox("串口配置")
        config_form = QFormLayout()

        self.port_input = QLineEdit("COM3")
        config_form.addRow("串口端口:", self.port_input)

        self.baudrate_input = QComboBox()
        self.baudrate_input.addItems(["9600", "19200", "38400", "57600", "115200"])
        self.baudrate_input.setCurrentText("115200")
        config_form.addRow("波特率:", self.baudrate_input)

        self.num_channels_input = QSpinBox()
        self.num_channels_input.setRange(1, 4)
        self.num_channels_input.setValue(4)
        self.num_channels_input.valueChanged.connect(self._rebuild_voltage_controls)
        config_form.addRow("通道数量:", self.num_channels_input)

        config_group.setLayout(config_form)
        left.addWidget(config_group)

        # 按钮组
        btn_group = QGroupBox("操作")
        btn_layout = QVBoxLayout()

        self.btn_connect = QPushButton("连接")
        self.btn_disconnect = QPushButton("断开")
        self.btn_apply = QPushButton("应用电压")
        self.btn_zero_all = QPushButton("全部归零")

        self.btn_disconnect.setEnabled(False)
        self.btn_apply.setEnabled(False)
        self.btn_zero_all.setEnabled(False)

        for btn in (self.btn_connect, self.btn_disconnect, self.btn_apply, self.btn_zero_all):
            btn_layout.addWidget(btn)

        btn_group.setLayout(btn_layout)
        left.addWidget(btn_group)

        left.addStretch()
        main_layout.addLayout(left)

        # --- 右侧：电压通道控件（可滚动） ---
        self.channels_group = QGroupBox("通道电压")
        self.channels_layout = QVBoxLayout()
        self.channels_group.setLayout(self.channels_layout)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.channels_group)
        main_layout.addWidget(scroll, stretch=1)

        # 初始生成电压控件
        self._rebuild_voltage_controls(self.num_channels_input.value())

        # 信号连接
        self.btn_connect.clicked.connect(self._on_connect_clicked)
        self.btn_disconnect.clicked.connect(self._on_disconnect_clicked)
        self.btn_apply.clicked.connect(self._on_apply_clicked)
        self.btn_zero_all.clicked.connect(self._on_zero_all_clicked)

    def _rebuild_voltage_controls(self, num_channels: int):
        """根据通道数量动态生成电压输入控件。"""
        # 清除旧控件
        while self.channels_layout.count():
            item = self.channels_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        self._voltage_inputs.clear()
        self._voltage_labels.clear()

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

            current_label = QLabel("当前: -- V")

            row_layout.addWidget(ch_label)
            row_layout.addWidget(spin, stretch=1)
            row_layout.addWidget(current_label)

            self.channels_layout.addWidget(row_widget)
            self._voltage_inputs.append(spin)
            self._voltage_labels.append(current_label)

        # 底部弹性空间
        self.channels_layout.addStretch()

    # ==================================================================
    # Worker / Thread 初始化
    # ==================================================================

    def _init_worker(self):
        self._thread = QThread()
        self._worker = ZynqWorker()
        self._worker.moveToThread(self._thread)

        # Worker 信号 → UI 槽
        self._worker.connected.connect(self._on_connected)
        self._worker.voltages_updated.connect(self._on_voltages_updated)
        self._worker.error_occurred.connect(self._on_error)
        self._worker.operation_finished.connect(self._on_operation_finished)

        self._thread.start()

    # ==================================================================
    # ConnectionManager 注册
    # ==================================================================

    def _register_instrument(self):
        self._conn_mgr.register_instrument(
            "Zynq",
            connect_fn=lambda: True,
            disconnect_fn=lambda: True,
        )

    # ==================================================================
    # 按钮槽
    # ==================================================================

    def _on_connect_clicked(self):
        self._set_busy(True)
        params = {
            "port": self.port_input.text().strip(),
            "baudrate": int(self.baudrate_input.currentText()),
            "num_channels": self.num_channels_input.value(),
        }
        self._worker.connect_zynq(params)

    def _on_disconnect_clicked(self):
        self._set_busy(True)
        self._worker.disconnect_zynq()
        self._connected = False
        self._conn_mgr.disconnect_instrument("Zynq")
        self.btn_connect.setEnabled(True)
        self.btn_disconnect.setEnabled(False)
        self.btn_apply.setEnabled(False)
        self.btn_zero_all.setEnabled(False)
        # 解锁配置控件
        self.port_input.setEnabled(True)
        self.baudrate_input.setEnabled(True)
        self.num_channels_input.setEnabled(True)

    def _on_apply_clicked(self):
        voltages = [spin.value() for spin in self._voltage_inputs]
        self._set_busy(True)
        self._worker.set_voltages(voltages)

    def _on_zero_all_clicked(self):
        for spin in self._voltage_inputs:
            spin.setValue(0.0)
        voltages = [0.0] * len(self._voltage_inputs)
        self._set_busy(True)
        self._worker.set_voltages(voltages)

    # ==================================================================
    # Worker 回调槽
    # ==================================================================

    @Slot(bool)
    def _on_connected(self, success: bool):
        if success:
            self._connected = True
            self._conn_mgr.connect_instrument("Zynq")
            self.btn_connect.setEnabled(False)
            self.btn_disconnect.setEnabled(True)
            self.btn_apply.setEnabled(True)
            self.btn_zero_all.setEnabled(True)
            # 锁定配置控件
            self.port_input.setEnabled(False)
            self.baudrate_input.setEnabled(False)
            self.num_channels_input.setEnabled(False)
            self._log.append_log("Zynq FPGA 连接成功", "INFO")
        else:
            self._conn_mgr.disconnect_instrument("Zynq")
            self._log.append_log("Zynq FPGA 连接失败", "ERROR")

    @Slot(list)
    def _on_voltages_updated(self, voltages: list):
        for i, v in enumerate(voltages):
            if i < len(self._voltage_labels):
                self._voltage_labels[i].setText(f"当前: {v:.3f} V")

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
        self.btn_connect.setEnabled(not busy and not self._connected)
        self.btn_disconnect.setEnabled(not busy and self._connected)
        self.btn_apply.setEnabled(not busy and self._connected)
        self.btn_zero_all.setEnabled(not busy and self._connected)

    # ==================================================================
    # 清理
    # ==================================================================

    def cleanup(self):
        """安全关闭 Worker 线程，电压置零后断开连接。"""
        if self._thread.isRunning():
            if self._connected:
                self._worker.set_voltages([0.0] * len(self._voltage_inputs))
                self._worker.disconnect_zynq()
            self._thread.quit()
            self._thread.wait(3000)

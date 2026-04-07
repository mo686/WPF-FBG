"""NI_DAQ_Panel — NI-DAQ 电压控制面板

提供设备名称、起始通道、通道数量配置控件，
根据通道数量动态生成电压输入控件（范围 -16V 至 16V），
按钮：初始化、应用电压、全部归零。
显示每个通道当前电压值。
通过 NIDAQWorker + QThread 在后台执行仪器操作。
"""

import logging
from typing import List, Optional

from PySide6.QtCore import QThread, Slot
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QLineEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.ui.connection_manager import ConnectionManager
from src.ui.log_console import LogConsole
from src.ui.workers import NIDAQWorker

logger = logging.getLogger(__name__)

# 电压范围常量
VOLTAGE_MIN = -16.0
VOLTAGE_MAX = 16.0


class NIDAQPanel(QWidget):
    """NI-DAQ 电压控制面板。"""

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
        self._initialized = False

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
        config_group = QGroupBox("设备配置")
        config_form = QFormLayout()

        self.device_name_input = QLineEdit("PXI1Slot3")
        config_form.addRow("设备名称:", self.device_name_input)

        self.start_channel_input = QSpinBox()
        self.start_channel_input.setRange(0, 31)
        self.start_channel_input.setValue(0)
        config_form.addRow("起始通道:", self.start_channel_input)

        self.num_channels_input = QSpinBox()
        self.num_channels_input.setRange(1, 32)
        self.num_channels_input.setValue(4)
        self.num_channels_input.valueChanged.connect(self._rebuild_voltage_controls)
        config_form.addRow("通道数量:", self.num_channels_input)

        config_group.setLayout(config_form)
        left.addWidget(config_group)

        # 按钮组
        btn_group = QGroupBox("操作")
        btn_layout = QVBoxLayout()

        self.btn_initialize = QPushButton("初始化")
        self.btn_apply = QPushButton("应用电压")
        self.btn_zero_all = QPushButton("全部归零")

        self.btn_apply.setEnabled(False)
        self.btn_zero_all.setEnabled(False)

        for btn in (self.btn_initialize, self.btn_apply, self.btn_zero_all):
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
        self.btn_initialize.clicked.connect(self._on_initialize_clicked)
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

        start_ch = self.start_channel_input.value()

        for i in range(num_channels):
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)

            ch_label = QLabel(f"通道 {start_ch + i}:")
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
        self._worker = NIDAQWorker()
        self._worker.moveToThread(self._thread)

        # Worker 信号 → UI 槽
        self._worker.initialized.connect(self._on_initialized)
        self._worker.voltages_updated.connect(self._on_voltages_updated)
        self._worker.error_occurred.connect(self._on_error)
        self._worker.operation_finished.connect(self._on_operation_finished)

        self._thread.start()

    # ==================================================================
    # ConnectionManager 注册
    # ==================================================================

    def _register_instrument(self):
        self._conn_mgr.register_instrument(
            "NI-DAQ",
            connect_fn=lambda: True,
            disconnect_fn=lambda: True,
        )

    # ==================================================================
    # 按钮槽
    # ==================================================================

    def _on_initialize_clicked(self):
        self._set_busy(True)
        params = {
            "device_name": self.device_name_input.text().strip(),
            "start_channel": self.start_channel_input.value(),
            "num_channels": self.num_channels_input.value(),
        }
        self._worker.initialize(params)

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
    def _on_initialized(self, success: bool):
        if success:
            self._initialized = True
            self._conn_mgr.connect_instrument("NI-DAQ")
            self.btn_initialize.setEnabled(False)
            self.btn_apply.setEnabled(True)
            self.btn_zero_all.setEnabled(True)
            # 锁定配置控件
            self.device_name_input.setEnabled(False)
            self.start_channel_input.setEnabled(False)
            self.num_channels_input.setEnabled(False)
            self._log.append_log("NI-DAQ 初始化成功", "INFO")
        else:
            self._log.append_log("NI-DAQ 初始化失败", "ERROR")

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
        self.btn_initialize.setEnabled(not busy and not self._initialized)
        self.btn_apply.setEnabled(not busy and self._initialized)
        self.btn_zero_all.setEnabled(not busy and self._initialized)

    # ==================================================================
    # 清理
    # ==================================================================

    def cleanup(self):
        """安全关闭 Worker 线程，电压置零。"""
        if self._thread.isRunning():
            if self._initialized:
                self._worker.set_voltages([0.0] * len(self._voltage_inputs))
            self._worker.close()
            self._thread.quit()
            self._thread.wait(3000)

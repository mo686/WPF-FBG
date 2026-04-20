"""Laser_Panel — 激光器控制面板

提供波长（1500-1650 nm）和功率（0-10 dBm）输入控件，
连接/断开/应用参数按钮，实时显示当前波长和功率状态。
输入超出范围时阻止提交并显示提示。
通过 LaserWorker + QThread 在后台执行仪器操作。
"""

import logging
from typing import Optional

from PySide6.QtCore import QThread, Slot
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.ui.connection_manager import ConnectionManager
from src.ui.log_console import LogConsole
from src.ui.workers import LaserWorker

logger = logging.getLogger(__name__)

# 参数范围常量
WAVELENGTH_MIN = 1500.0
WAVELENGTH_MAX = 1650.0
POWER_MIN = -10.0
POWER_MAX = 10.0


class LaserPanel(QWidget):
    """激光器控制面板。"""

    def __init__(
        self,
        connection_manager: ConnectionManager,
        log_console: LogConsole,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._conn_mgr = connection_manager
        self._log = log_console

        self._init_ui()
        self._init_worker()
        self._register_instrument()

    # ==================================================================
    # UI 构建
    # ==================================================================

    def _init_ui(self):
        main_layout = QHBoxLayout(self)

        # --- 左侧：参数 + 按钮 + 状态 ---
        left = QVBoxLayout()

        # 参数组
        param_group = QGroupBox("参数设置")
        form = QFormLayout()

        self.wavelength_input = QDoubleSpinBox()
        self.wavelength_input.setRange(WAVELENGTH_MIN, WAVELENGTH_MAX)
        self.wavelength_input.setDecimals(3)
        self.wavelength_input.setSuffix(" nm")
        self.wavelength_input.setValue(1550.0)
        form.addRow("波长:", self.wavelength_input)

        self.power_input = QDoubleSpinBox()
        self.power_input.setRange(POWER_MIN, POWER_MAX)
        self.power_input.setDecimals(2)
        self.power_input.setSuffix(" dBm")
        self.power_input.setValue(5.0)
        form.addRow("功率:", self.power_input)

        param_group.setLayout(form)
        left.addWidget(param_group)

        # 按钮组
        btn_group = QGroupBox("操作")
        btn_layout = QVBoxLayout()

        self.btn_connect = QPushButton("连接")
        self.btn_disconnect = QPushButton("断开")
        self.btn_apply = QPushButton("应用参数")

        self.btn_disconnect.setEnabled(False)
        self.btn_apply.setEnabled(False)

        for btn in (self.btn_connect, self.btn_disconnect, self.btn_apply):
            btn_layout.addWidget(btn)

        btn_group.setLayout(btn_layout)
        left.addWidget(btn_group)

        # 状态显示组
        status_group = QGroupBox("当前状态")
        status_layout = QFormLayout()

        self.lbl_wavelength = QLabel("--")
        self.lbl_power = QLabel("--")
        self.lbl_connected = QLabel("未连接")

        status_layout.addRow("波长:", self.lbl_wavelength)
        status_layout.addRow("功率:", self.lbl_power)
        status_layout.addRow("连接状态:", self.lbl_connected)

        status_group.setLayout(status_layout)
        left.addWidget(status_group)

        left.addStretch()
        main_layout.addLayout(left)

        # 右侧留空（激光器面板无图表需求，但保持布局一致性）
        right_placeholder = QWidget()
        main_layout.addWidget(right_placeholder, stretch=1)

        # 信号连接
        self.btn_connect.clicked.connect(self._on_connect_clicked)
        self.btn_disconnect.clicked.connect(self._on_disconnect_clicked)
        self.btn_apply.clicked.connect(self._on_apply_clicked)

    # ==================================================================
    # Worker / Thread 初始化
    # ==================================================================

    def _init_worker(self):
        self._thread = QThread()
        self._worker = LaserWorker()
        self._worker.moveToThread(self._thread)

        # Worker 信号 → UI 槽
        self._worker.connected.connect(self._on_connected)
        self._worker.status_updated.connect(self._on_status_updated)
        self._worker.error_occurred.connect(self._on_error)
        self._worker.operation_finished.connect(self._on_operation_finished)

        self._thread.start()

    # ==================================================================
    # ConnectionManager 注册
    # ==================================================================

    def _register_instrument(self):
        self._conn_mgr.register_instrument(
            "Laser",
            connect_fn=lambda: True,
            disconnect_fn=lambda: True,
        )

    # ==================================================================
    # 按钮槽
    # ==================================================================

    def _on_connect_clicked(self):
        self._set_busy(True)
        self._worker.connect_laser()

    def _on_disconnect_clicked(self):
        self._set_busy(True)
        self._worker.disconnect_laser()
        self._conn_mgr.disconnect_instrument("Laser")
        self.btn_connect.setEnabled(True)
        self.btn_disconnect.setEnabled(False)
        self.btn_apply.setEnabled(False)
        self.lbl_connected.setText("未连接")
        self.lbl_wavelength.setText("--")
        self.lbl_power.setText("--")

    def _on_apply_clicked(self):
        wavelength = self.wavelength_input.value()
        power = self.power_input.value()

        # 范围验证（QDoubleSpinBox 已限制范围，此处做二次防护）
        if not (WAVELENGTH_MIN <= wavelength <= WAVELENGTH_MAX):
            QMessageBox.warning(
                self,
                "参数超出范围",
                f"波长必须在 {WAVELENGTH_MIN}-{WAVELENGTH_MAX} nm 范围内",
            )
            return
        if not (POWER_MIN <= power <= POWER_MAX):
            QMessageBox.warning(
                self,
                "参数超出范围",
                f"功率必须在 {POWER_MIN}-{POWER_MAX} dBm 范围内",
            )
            return

        self._set_busy(True)
        self._worker.set_wavelength(wavelength)
        self._worker.set_power(power)

    # ==================================================================
    # Worker 回调槽
    # ==================================================================

    @Slot(bool)
    def _on_connected(self, success: bool):
        if success:
            self._conn_mgr.connect_instrument("Laser")
            self.btn_connect.setEnabled(False)
            self.btn_disconnect.setEnabled(True)
            self.btn_apply.setEnabled(True)
            self.lbl_connected.setText("已连接")
            self._log.append_log("激光器连接成功", "INFO")
        else:
            self.lbl_connected.setText("连接失败")
            self._log.append_log("激光器连接失败", "ERROR")

    @Slot(dict)
    def _on_status_updated(self, status: dict):
        wl = status.get("wavelength")
        pw = status.get("power")
        if wl is not None:
            self.lbl_wavelength.setText(f"{wl:.3f} nm")
        if pw is not None:
            self.lbl_power.setText(f"{pw:.2f} dBm")

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
        self.btn_connect.setEnabled(not busy and not self.btn_disconnect.isEnabled())
        self.btn_apply.setEnabled(not busy and self.btn_disconnect.isEnabled())

    # ==================================================================
    # 清理
    # ==================================================================

    def cleanup(self):
        """安全关闭 Worker 线程。"""
        if self._thread.isRunning():
            self._worker.disconnect_laser()
            self._thread.quit()
            self._thread.wait(3000)
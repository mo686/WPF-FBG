"""MainWindow — 仪器控制 GUI 主窗口

创建 QTabWidget 添加 7 个面板选项卡，
StatusBar 显示仪器连接状态指示器，
LogConsole 嵌入底部 QDockWidget，
ConnectionManager 注入各面板。
closeEvent 安全断开所有仪器、电压置零、关闭 QThread。
"""

import logging
from typing import Dict

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QTabWidget,
    QWidget,
)

from src.ui.connection_manager import ConnectionManager, InstrumentStatus
from src.ui.log_console import LogConsole, LogConsoleHandler
from src.ui.panels.vna_panel import VNAPanel
from src.ui.panels.laser_panel import LaserPanel
from src.ui.panels.zynq_panel import ZynqPanel
from src.ui.panels.spectrum_panel import SpectrumPanel
from src.ui.panels.measurement_panel import MeasurementPanel
from src.ui.panels.calibration_panel import CalibrationPanel
from src.ui.panels.reference_panel import ReferencePanel
from src.ui.panels.sweep_panel import SweepPanel
from src.ui.panels.voltage_scan_panel import VoltageScanPanel

logger = logging.getLogger(__name__)

# 仪器名称 → 状态栏显示名
_INSTRUMENT_LABELS = {
    "VNA": "VNA",
    "Laser": "激光器",
    "Zynq": "Zynq",
    "Measurement": "插损测量",
    "Reference": "参考测量",
}

# 状态 → 颜色
_STATUS_COLORS: Dict[str, str] = {
    InstrumentStatus.CONNECTED.value: "#22cc22",      # 绿色
    InstrumentStatus.DISCONNECTED.value: "#aaaaaa",    # 灰色
    InstrumentStatus.ERROR.value: "#ee3333",           # 红色
}


class MainWindow(QMainWindow):
    """仪器控制 GUI 主窗口。"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("光电实验室仪器控制系统")
        self.resize(1280, 800)

        # 共享服务
        self._conn_mgr = ConnectionManager(self)
        self._log_console = LogConsole()

        # 将 Python logging 重定向到 LogConsole
        self._log_handler = LogConsoleHandler(self._log_console)
        self._log_handler.setFormatter(logging.Formatter("%(name)s - %(message)s"))
        logging.getLogger().addHandler(self._log_handler)

        # 状态指示器字典 instrument_name → QLabel
        self._status_indicators: Dict[str, QLabel] = {}

        self._init_panels()
        self._init_status_bar()
        self._init_log_dock()

        # 监听连接状态变化
        self._conn_mgr.status_changed.connect(self._on_status_changed)

    # ==================================================================
    # 初始化
    # ==================================================================

    def _init_panels(self):
        """创建 QTabWidget 并添加 7 个面板选项卡。"""
        self._tabs = QTabWidget()
        self.setCentralWidget(self._tabs)

        self._vna_panel = VNAPanel(self._conn_mgr, self._log_console)
        self._laser_panel = LaserPanel(self._conn_mgr, self._log_console)
        self._zynq_panel = ZynqPanel(self._conn_mgr, self._log_console)
        self._spectrum_panel = SpectrumPanel(self._log_console)
        self._measurement_panel = MeasurementPanel(self._conn_mgr, self._log_console)
        self._calibration_panel = CalibrationPanel(self._log_console)
        self._reference_panel = ReferencePanel(self._conn_mgr, self._log_console)
        self._sweep_panel = SweepPanel(self._conn_mgr, self._log_console)
        self._voltage_scan_panel = VoltageScanPanel(self._conn_mgr, self._log_console)

        self._tabs.addTab(self._vna_panel, "VNA")
        self._tabs.addTab(self._laser_panel, "激光器")
        self._tabs.addTab(self._zynq_panel, "Zynq")
        self._tabs.addTab(self._spectrum_panel, "光谱分析")
        self._tabs.addTab(self._reference_panel, "参考测量")
        self._tabs.addTab(self._measurement_panel, "插损测量")
        self._tabs.addTab(self._voltage_scan_panel, "电压扫描")
        self._tabs.addTab(self._sweep_panel, "定标扫描")
        self._tabs.addTab(self._calibration_panel, "定标流水线")

    def _init_status_bar(self):
        """在 StatusBar 中为每个仪器创建连接状态指示器。"""
        status_bar = self.statusBar()

        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(12)

        for name, display_name in _INSTRUMENT_LABELS.items():
            indicator = QLabel(f"● {display_name}")
            indicator.setStyleSheet(
                f"color: {_STATUS_COLORS[InstrumentStatus.DISCONNECTED.value]}; "
                "font-weight: bold; font-size: 12px;"
            )
            layout.addWidget(indicator)
            self._status_indicators[name] = indicator

        status_bar.addPermanentWidget(container)

    def _init_log_dock(self):
        """将 LogConsole 嵌入底部 QDockWidget。"""
        dock = QDockWidget("日志控制台", self)
        dock.setWidget(self._log_console)
        dock.setAllowedAreas(Qt.BottomDockWidgetArea | Qt.TopDockWidgetArea)
        dock.setFeatures(
            QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable
        )
        self.addDockWidget(Qt.BottomDockWidgetArea, dock)

    # ==================================================================
    # 状态更新
    # ==================================================================

    def _on_status_changed(self, name: str, status: str):
        """ConnectionManager 状态变化时更新 StatusBar 指示器。"""
        indicator = self._status_indicators.get(name)
        if indicator is None:
            return
        color = _STATUS_COLORS.get(status, _STATUS_COLORS[InstrumentStatus.DISCONNECTED.value])
        display_name = _INSTRUMENT_LABELS.get(name, name)
        indicator.setText(f"● {display_name}")
        indicator.setStyleSheet(
            f"color: {color}; font-weight: bold; font-size: 12px;"
        )

    # ==================================================================
    # 关闭事件
    # ==================================================================

    def closeEvent(self, event: QCloseEvent):
        """安全断开所有仪器，电压置零，关闭所有 QThread。"""
        logger.info("正在关闭应用程序，执行安全清理...")

        # 1. 各面板清理（电压置零 + 断开 + 线程关闭）
        panels = [
            self._voltage_scan_panel,
            self._sweep_panel,
            self._zynq_panel,
            self._vna_panel,
            self._laser_panel,
            self._reference_panel,
            self._measurement_panel,
            self._calibration_panel,
        ]
        for panel in panels:
            try:
                panel.cleanup()
            except Exception as exc:
                logger.error("面板清理失败: %s", exc)

        # 2. ConnectionManager 断开所有仪器
        try:
            self._conn_mgr.disconnect_all()
        except Exception as exc:
            logger.error("断开所有仪器失败: %s", exc)

        # 3. 移除 logging handler
        logging.getLogger().removeHandler(self._log_handler)

        logger.info("应用程序已安全关闭")
        event.accept()

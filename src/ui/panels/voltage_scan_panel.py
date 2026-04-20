"""VoltageScan_Panel — 电压扫描测量面板

支持两种测量模式：
- 插损模式：逐点设置电压 → 光学扫描 → 减去参考 → 绘制插损曲线
- VNA S21 模式：逐点设置电压 → VNA 测量 S21 → 绘制幅度曲线

通过 VoltageScanWorker + QThread 在后台执行。
"""

import logging
from typing import Optional

import numpy as np
from PySide6.QtCore import QThread, Qt, Slot
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.ui.chart_widget import ChartWidget
from src.ui.connection_manager import ConnectionManager
from src.ui.log_console import LogConsole
from src.ui.workers import VoltageScanWorker

logger = logging.getLogger(__name__)


class VoltageScanPanel(QWidget):
    """电压扫描测量面板（插损 / VNA S21 双模式）。"""

    def __init__(self, connection_manager, log_console, parent=None):
        super().__init__(parent)
        self._conn_mgr = connection_manager
        self._log = log_console
        self._all_data = []       # 插损模式: [(voltage, mdata)]
        self._all_vna_data = []   # VNA 模式: [(voltage, freq, mag)]

        self._init_ui()
        self._init_worker()

    def _init_ui(self):
        main_layout = QHBoxLayout(self)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setMaximumWidth(340)

        left_widget = QWidget()
        left = QVBoxLayout(left_widget)
        left.setContentsMargins(4, 4, 4, 4)
        left.setSpacing(6)

        # --- 模式选择 ---
        mode_group = QGroupBox("测量模式")
        mode_layout = QVBoxLayout()
        self.radio_loss = QRadioButton("插损测量（光学）")
        self.radio_vna = QRadioButton("VNA S21 测量")
        self.radio_loss.setChecked(True)
        mode_layout.addWidget(self.radio_loss)
        mode_layout.addWidget(self.radio_vna)
        mode_group.setLayout(mode_layout)
        left.addWidget(mode_group)

        self.radio_loss.toggled.connect(self._on_mode_changed)

        # --- 电压扫描参数 ---
        param_group = QGroupBox("电压扫描参数")
        form = QFormLayout()
        form.setSpacing(4)

        self.channel_input = QSpinBox()
        self.channel_input.setRange(1, 4)
        self.channel_input.setValue(1)
        form.addRow("Zynq 通道:", self.channel_input)

        self.start_v = QDoubleSpinBox()
        self.start_v.setRange(0.0, 10.0)
        self.start_v.setDecimals(3)
        self.start_v.setSuffix(" V")
        self.start_v.setValue(0.0)
        form.addRow("起始电压:", self.start_v)

        self.end_v = QDoubleSpinBox()
        self.end_v.setRange(0.0, 10.0)
        self.end_v.setDecimals(3)
        self.end_v.setSuffix(" V")
        self.end_v.setValue(10.0)
        form.addRow("终止电压:", self.end_v)

        self.step_power = QDoubleSpinBox()
        self.step_power.setRange(0.000001, 1.0)
        self.step_power.setDecimals(6)
        self.step_power.setSuffix(" W")
        self.step_power.setValue(0.01)
        form.addRow("步进功耗:", self.step_power)

        self.settle_time = QDoubleSpinBox()
        self.settle_time.setRange(0.0, 30.0)
        self.settle_time.setDecimals(1)
        self.settle_time.setSuffix(" s")
        self.settle_time.setValue(3.0)
        form.addRow("稳定等待:", self.settle_time)

        param_group.setLayout(form)
        left.addWidget(param_group)

        # --- VNA 参数（仅 VNA 模式可见） ---
        self.vna_group = QGroupBox("VNA 参数")
        vna_form = QFormLayout()
        vna_form.setSpacing(4)

        self.vna_gpib = QSpinBox()
        self.vna_gpib.setRange(0, 30)
        self.vna_gpib.setValue(16)
        vna_form.addRow("GPIB 地址:", self.vna_gpib)

        self.vna_start = QDoubleSpinBox()
        self.vna_start.setRange(0, 50)
        self.vna_start.setDecimals(3)
        self.vna_start.setSuffix(" GHz")
        self.vna_start.setValue(0.01)
        vna_form.addRow("起始频率:", self.vna_start)

        self.vna_stop = QDoubleSpinBox()
        self.vna_stop.setRange(0, 50)
        self.vna_stop.setDecimals(3)
        self.vna_stop.setSuffix(" GHz")
        self.vna_stop.setValue(30.0)
        vna_form.addRow("终止频率:", self.vna_stop)

        self.vna_points = QSpinBox()
        self.vna_points.setRange(1, 100001)
        self.vna_points.setValue(6001)
        vna_form.addRow("扫描点数:", self.vna_points)

        self.vna_group.setLayout(vna_form)
        self.vna_group.setVisible(False)
        left.addWidget(self.vna_group)

        # --- 操作按钮 ---
        btn_group = QGroupBox("操作")
        btn_layout = QVBoxLayout()
        btn_layout.setSpacing(4)

        self.btn_init = QPushButton("① 初始化设备")
        self.btn_load_ref = QPushButton("② 加载参考数据")
        self.btn_start = QPushButton("③ 开始扫描")

        btn_row = QHBoxLayout()
        self.btn_abort = QPushButton("中止")
        self.btn_abort.setEnabled(False)
        btn_row.addWidget(self.btn_abort)

        self.btn_save_csv = QPushButton("保存 CSV")
        self.btn_save_plot = QPushButton("保存汇总图")
        self.btn_shutdown = QPushButton("结束操作")
        self.btn_save_csv.setEnabled(False)
        self.btn_save_plot.setEnabled(False)
        self.btn_shutdown.setEnabled(False)
        self.btn_start.setEnabled(False)

        btn_layout.addWidget(self.btn_init)
        btn_layout.addWidget(self.btn_load_ref)
        btn_layout.addWidget(self.btn_start)
        btn_layout.addLayout(btn_row)
        btn_layout.addWidget(self.btn_save_csv)
        btn_layout.addWidget(self.btn_save_plot)
        btn_layout.addWidget(self.btn_shutdown)

        btn_group.setLayout(btn_layout)
        left.addWidget(btn_group)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        left.addWidget(self.progress_bar)

        self.status_label = QLabel("状态: 未初始化")
        left.addWidget(self.status_label)

        left.addStretch()
        scroll.setWidget(left_widget)
        main_layout.addWidget(scroll)

        # --- 右侧 ---
        right = QVBoxLayout()
        self.chart = ChartWidget()
        right.addWidget(self.chart, stretch=1)
        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setMaximumHeight(100)
        right.addWidget(self.result_text)
        main_layout.addLayout(right, stretch=1)

        # 信号
        self.btn_init.clicked.connect(self._on_init_clicked)
        self.btn_load_ref.clicked.connect(self._on_load_ref_clicked)
        self.btn_start.clicked.connect(self._on_start_clicked)
        self.btn_abort.clicked.connect(self._on_abort_clicked)
        self.btn_save_csv.clicked.connect(self._on_save_csv_clicked)
        self.btn_save_plot.clicked.connect(self._on_save_plot_clicked)
        self.btn_shutdown.clicked.connect(self._on_shutdown_clicked)

    def _init_worker(self):
        self._thread = QThread()
        self._worker = VoltageScanWorker()
        self._worker.moveToThread(self._thread)
        self._worker.initialized.connect(self._on_initialized)
        self._worker.ref_loaded.connect(self._on_ref_loaded)
        self._worker.scan_progress.connect(self._on_scan_progress)
        self._worker.point_measured.connect(self._on_point_measured)
        self._worker.vna_point_measured.connect(self._on_vna_point_measured)
        self._worker.scan_finished.connect(self._on_scan_finished)
        self._worker.error_occurred.connect(self._on_error)
        self._worker.operation_finished.connect(self._on_operation_finished)
        self._thread.start()

    # --- 模式切换 ---

    def _on_mode_changed(self, checked: bool):
        is_loss = self.radio_loss.isChecked()
        self.vna_group.setVisible(not is_loss)
        self.btn_load_ref.setVisible(is_loss)

    def _is_vna_mode(self) -> bool:
        return self.radio_vna.isChecked()

    # --- 按钮槽 ---

    def _on_init_clicked(self):
        self._set_busy(True)
        vna_params = None
        if self._is_vna_mode():
            vna_params = {
                "gpib_address": self.vna_gpib.value(),
                "start_freq": self.vna_start.value() * 1e9,
                "stop_freq": self.vna_stop.value() * 1e9,
                "points": self.vna_points.value(),
            }
        self._worker.initialize(vna_params=vna_params)

    def _on_load_ref_clicked(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, "加载参考数据", "",
            "参考数据文件 (*.json *.dat);;所有文件 (*)"
        )
        if not filepath:
            return
        self._set_busy(True)
        self._worker.load_reference(filepath)

    def _on_start_clicked(self):
        # 计算功耗对应的电压范围
        start_power = (self.start_v.value() ** 2) / 100
        end_power = (self.end_v.value() ** 2) / 100
        
        params = {
            "channel": self.channel_input.value(),
            "start_voltage": self.start_v.value(),
            "end_voltage": self.end_v.value(),
            "start_power": start_power,
            "end_power": end_power,
            "step_power": self.step_power.value(),
            "settle_time": self.settle_time.value(),
            "mode": "vna" if self._is_vna_mode() else "loss",
        }
        self._all_data.clear()
        self._all_vna_data.clear()
        self.progress_bar.setValue(0)
        self.btn_start.setEnabled(False)
        self.btn_abort.setEnabled(True)
        self.status_label.setText("状态: 扫描中...")
        self._worker.run_scan(params)

    def _on_abort_clicked(self):
        self._worker.abort()
        self.btn_abort.setEnabled(False)
        self.status_label.setText("状态: 正在中止...")

    def _on_save_csv_clicked(self):
        filepath, _ = QFileDialog.getSaveFileName(self, "保存 CSV", "", "CSV 文件 (*.csv)")
        if not filepath:
            return
        try:
            with open(filepath, "w", newline="", encoding="utf-8") as f:
                if self._all_vna_data:
                    f.write("Voltage,Frequency_Hz,Magnitude_dB\n")
                    for voltage, freq, mag in self._all_vna_data:
                        for fr, m in zip(freq, mag):
                            f.write(f"{voltage:.3f},{fr:.1f},{m:.4f}\n")
                else:
                    f.write("Voltage,Wavelength,InsertionLoss\n")
                    for voltage, mdata in self._all_data:
                        if mdata:
                            item = mdata[-1]
                            for w, p in zip(item.get("rescaled_wavelength", []),
                                            item.get("rescaled_reference_power", [])):
                                f.write(f"{voltage:.3f},{w:.4f},{p:.4f}\n")
            self._log.append_log(f"CSV 已保存至 {filepath}", "INFO")
        except Exception as exc:
            self._on_error(f"保存 CSV 失败: {exc}")

    def _on_save_plot_clicked(self):
        filepath, _ = QFileDialog.getSaveFileName(self, "保存汇总图", "", "PNG 图片 (*.png)")
        if not filepath:
            return
        try:
            self.chart.save_figure(filepath)
            self._log.append_log(f"图表已保存至 {filepath}", "INFO")
        except Exception as exc:
            self._on_error(f"保存图表失败: {exc}")

    # --- Worker 回调 ---

    @Slot(bool)
    def _on_initialized(self, success: bool):
        if success:
            self.btn_init.setEnabled(False)
            if self._is_vna_mode():
                self.btn_start.setEnabled(True)
                self.status_label.setText("状态: 已初始化，可开始 VNA 扫描")
            else:
                self.btn_load_ref.setEnabled(True)
                self.status_label.setText("状态: 已初始化，请加载参考数据")
            self.btn_shutdown.setEnabled(True)
            self._log.append_log("电压扫描设备初始化成功", "INFO")
        else:
            self.btn_init.setEnabled(True)
            self.btn_load_ref.setEnabled(True)
            self._log.append_log("电压扫描设备初始化失败", "ERROR")

    @Slot(bool)
    def _on_ref_loaded(self, success: bool):
        self.btn_load_ref.setEnabled(True)
        if success:
            self.btn_start.setEnabled(True)
            self.status_label.setText("状态: 参考数据已加载，可开始扫描")
            self._log.append_log("参考数据加载成功", "INFO")
        else:
            self._log.append_log("参考数据加载失败", "ERROR")

    @Slot(int, int, float)
    def _on_scan_progress(self, current, total, voltage):
        power = (voltage ** 2) / 100
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        self.status_label.setText(f"状态: 扫描中 {current}/{total} ({voltage:.3f}V, {power:.6f}W)")

    @Slot(float, object)
    def _on_point_measured(self, voltage, mdata):
        self._all_data.append((voltage, mdata))
        self._plot_loss_summary()

    @Slot(float, object, object)
    def _on_vna_point_measured(self, voltage, freq, mag):
        self._all_vna_data.append((voltage, freq, mag))
        self._plot_vna_summary()

    @Slot(int)
    def _on_scan_finished(self, count):
        self.btn_abort.setEnabled(False)
        self.btn_start.setEnabled(True)
        self.btn_save_csv.setEnabled(True)
        self.btn_save_plot.setEnabled(True)
        self.status_label.setText(f"状态: 扫描完成，共 {count} 个点")
        self.result_text.setPlainText(f"扫描完成\n测量点数: {count}")
        self._log.append_log(f"电压扫描完成，共 {count} 个测量点", "INFO")

    @Slot(str)
    def _on_error(self, msg):
        self._log.append_log(msg, "ERROR")
        logger.error(msg)

    @Slot()
    def _on_operation_finished(self):
        self._set_busy(False)

    # --- 内部 ---

    def _set_busy(self, busy):
        if busy:
            self.btn_init.setEnabled(False)
            self.btn_load_ref.setEnabled(False)
            self.btn_start.setEnabled(False)

    def _plot_loss_summary(self):
        self.chart.figure.clear()
        ax = self.chart.figure.add_subplot(111)
        n = len(self._all_data)
        if n == 0:
            self.chart.canvas.draw_idle()
            return
        import matplotlib
        colors = matplotlib.cm.viridis(np.linspace(0, 1, max(n, 1)))
        for i, (voltage, mdata) in enumerate(self._all_data):
            if mdata:
                item = mdata[-1]
                wl = item.get("rescaled_wavelength", [])
                pw = item.get("rescaled_reference_power", [])
                if wl and pw:
                    power = (voltage ** 2) / 100
                    ax.plot(wl, pw, color=colors[i], linewidth=1, label=f"{voltage:.3f}V ({power:.4f}W)")
        ax.set_xlabel("Wavelength (nm)")
        ax.set_ylabel("Insertion Loss (dB)")
        ax.set_title("电压扫描插损汇总")
        if n <= 20:
            ax.legend(fontsize=6, loc="upper right")
        ax.grid(True, alpha=0.3)
        self.chart.ax = ax
        self.chart.figure.tight_layout()
        self.chart.canvas.draw_idle()

    def _plot_vna_summary(self):
        self.chart.figure.clear()
        ax = self.chart.figure.add_subplot(111)
        n = len(self._all_vna_data)
        if n == 0:
            self.chart.canvas.draw_idle()
            return
        import matplotlib
        colors = matplotlib.cm.viridis(np.linspace(0, 1, max(n, 1)))
        for i, (voltage, freq, mag) in enumerate(self._all_vna_data):
            freq_ghz = np.array(freq) / 1e9
            power = (voltage ** 2) / 100
            ax.plot(freq_ghz, mag, color=colors[i], linewidth=0.8, label=f"{voltage:.3f}V ({power:.4f}W)")
        ax.set_xlabel("Frequency (GHz)")
        ax.set_ylabel("Magnitude (dB)")
        ax.set_title("电压扫描 VNA S21 汇总")
        if n <= 20:
            ax.legend(fontsize=6, loc="upper right")
        ax.grid(True, alpha=0.3)
        self.chart.ax = ax
        self.chart.figure.tight_layout()
        self.chart.canvas.draw_idle()

    def _on_shutdown_clicked(self):
        """结束操作：断开设备。"""
        self._log.append_log("正在结束操作...", "INFO")
        self._worker.abort()
        self.btn_init.setEnabled(True)
        self.btn_load_ref.setEnabled(False)
        self.btn_start.setEnabled(False)
        self.btn_abort.setEnabled(False)
        self.btn_shutdown.setEnabled(False)
        self.status_label.setText("状态: 已结束")
        self._log.append_log("操作已结束", "INFO")

    def cleanup(self):
        if self._thread.isRunning():
            self._worker.abort()
            self._thread.quit()
            self._thread.wait(3000)
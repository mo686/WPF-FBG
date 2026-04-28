"""Worker 类 — 所有仪器操作的后台线程 Worker

每个 Worker 继承 BaseWorker(QObject)，通过 moveToThread() 移入 QThread。
Slot 方法使用 try/except 包裹，异常通过 error_occurred 信号传回主线程。
"""

import sys
import os
import logging
from typing import Optional

from PySide6.QtCore import QObject, Signal, Slot

# 确保 src/ 在 sys.path 中，以便导入现有仪器模块
_src_dir = os.path.join(os.path.dirname(__file__), os.pardir)
if _src_dir not in sys.path:
    sys.path.insert(0, os.path.abspath(_src_dir))

logger = logging.getLogger(__name__)


# ======================================================================
# BaseWorker
# ======================================================================

class BaseWorker(QObject):
    """Worker 基类，提供通用信号。"""

    error_occurred = Signal(str)
    operation_finished = Signal()


# ======================================================================
# VNAWorker
# ======================================================================

class VNAWorker(BaseWorker):
    """VNA 矢量网络分析仪 Worker。"""

    measurement_ready = Signal(dict)
    connected = Signal(bool)

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._vna = None

    @Slot(dict)
    def connect_vna(self, params: dict):
        """连接 VNA 并设置参数。"""
        try:
            from vna import VNA

            self._vna = VNA(
                gpib_address=params.get("gpib_address", 16),
                start_freq=params.get("start_freq", 10e6),
                stop_freq=params.get("stop_freq", 30e9),
                points=params.get("points", 6001),
                power=params.get("power", -10),
                if_bw=params.get("if_bw", 1000),
                param=params.get("param", "S21"),
                save_dir=params.get("save_dir", "./vna_data"),
            )
            success = self._vna.connect()
            if success:
                self._vna.setup_parameters()
            self.connected.emit(success)
        except Exception as exc:
            logger.error("VNA 连接失败: %s", exc)
            self.error_occurred.emit(str(exc))
            self.connected.emit(False)
        finally:
            self.operation_finished.emit()

    @Slot()
    def measure(self):
        """执行单次 S 参数测量。"""
        try:
            if self._vna is None:
                self.error_occurred.emit("VNA 未连接")
                return
            data = self._vna.measure()
            if data is None:
                self.error_occurred.emit("VNA 测量返回空数据")
            else:
                self.measurement_ready.emit(data)
        except Exception as exc:
            logger.error("VNA 测量失败: %s", exc)
            self.error_occurred.emit(str(exc))
        finally:
            self.operation_finished.emit()

    @Slot(dict, str)
    def save_data(self, data: dict, filename: str):
        """保存测量数据到 CSV。"""
        try:
            if self._vna is None:
                self.error_occurred.emit("VNA 未连接")
                return
            self._vna.save_data(data, filename)
        except Exception as exc:
            self.error_occurred.emit(str(exc))
        finally:
            self.operation_finished.emit()

    @Slot()
    def disconnect_vna(self):
        """断开 VNA 连接。"""
        try:
            if self._vna:
                self._vna.close()
                self._vna = None
        except Exception as exc:
            logger.error("VNA 断开失败: %s", exc)
            self.error_occurred.emit(str(exc))
        finally:
            self.operation_finished.emit()


# ======================================================================
# LaserWorker
# ======================================================================

class LaserWorker(BaseWorker):
    """激光器控制 Worker。"""

    status_updated = Signal(dict)
    connected = Signal(bool)

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._laser = None

    @Slot()
    def connect_laser(self):
        """连接激光器。"""
        try:
            from laser_controller import LaserController

            self._laser = LaserController()
            success = self._laser.connect()
            self.connected.emit(success)
            if success:
                self.status_updated.emit(self._laser.get_status())
        except Exception as exc:
            logger.error("激光器连接失败: %s", exc)
            self.error_occurred.emit(str(exc))
            self.connected.emit(False)
        finally:
            self.operation_finished.emit()

    @Slot(float)
    def set_wavelength(self, wavelength: float):
        """设置波长。"""
        try:
            if self._laser is None:
                self.error_occurred.emit("激光器未连接")
                return
            success = self._laser.set_wavelength(wavelength)
            if not success:
                self.error_occurred.emit(f"设置波长 {wavelength} nm 失败")
            self.status_updated.emit(self._laser.get_status())
        except Exception as exc:
            self.error_occurred.emit(str(exc))
        finally:
            self.operation_finished.emit()

    @Slot(float)
    def set_power(self, power: float):
        """设置功率。"""
        try:
            if self._laser is None:
                self.error_occurred.emit("激光器未连接")
                return
            success = self._laser.set_power(power)
            if not success:
                self.error_occurred.emit(f"设置功率 {power} dBm 失败")
            self.status_updated.emit(self._laser.get_status())
        except Exception as exc:
            self.error_occurred.emit(str(exc))
        finally:
            self.operation_finished.emit()

    @Slot()
    def disconnect_laser(self):
        """断开激光器连接。"""
        try:
            if self._laser:
                self._laser.disconnect()
                self._laser = None
        except Exception as exc:
            logger.error("激光器断开失败: %s", exc)
            self.error_occurred.emit(str(exc))
        finally:
            self.operation_finished.emit()


# ======================================================================
# NIDAQWorker
# ======================================================================

class NIDAQWorker(BaseWorker):
    """NI-DAQ 电压控制 Worker。"""

    voltages_updated = Signal(list)
    initialized = Signal(bool)

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._controller = None

    @Slot(dict)
    def initialize(self, params: dict):
        """初始化 DAQ 任务。"""
        try:
            from ni_voltage_control import VoltageController

            self._controller = VoltageController(
                device_name=params.get("device_name", "PXI1Slot3"),
                num_channels=params.get("num_channels", 4),
                start_channel=params.get("start_channel", 0),
            )
            success = self._controller.initialize()
            self.initialized.emit(success)
            if success:
                self.voltages_updated.emit(
                    list(self._controller.get_current_voltages())
                )
        except Exception as exc:
            logger.error("NI-DAQ 初始化失败: %s", exc)
            self.error_occurred.emit(str(exc))
            self.initialized.emit(False)
        finally:
            self.operation_finished.emit()

    @Slot(list)
    def set_voltages(self, voltages: list):
        """设置所有通道电压。"""
        try:
            if self._controller is None:
                self.error_occurred.emit("NI-DAQ 未初始化")
                return
            success = self._controller.set_voltages(voltages)
            if not success:
                self.error_occurred.emit("NI-DAQ 设置电压失败")
            self.voltages_updated.emit(
                list(self._controller.get_current_voltages())
            )
        except Exception as exc:
            self.error_occurred.emit(str(exc))
        finally:
            self.operation_finished.emit()

    def close(self):
        """关闭 DAQ 任务。"""
        try:
            if self._controller:
                self._controller.close()
                self._controller = None
        except Exception as exc:
            logger.error("NI-DAQ 关闭失败: %s", exc)


# ======================================================================
# ZynqWorker
# ======================================================================

class ZynqWorker(BaseWorker):
    """Zynq FPGA 电压控制 Worker。"""

    voltages_updated = Signal(list)
    connected = Signal(bool)

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._controller = None

    @Slot(dict)
    def connect_zynq(self, params: dict):
        """连接 Zynq 控制器。"""
        try:
            from zynq_voltage_controller import ZynqVoltageController

            self._controller = ZynqVoltageController(
                port=params.get("port", "/dev/ttyUSB0"),
                baudrate=params.get("baudrate", 115200),
                num_channels=params.get("num_channels", 4),
            )
            success = self._controller.initialize()
            self.connected.emit(success)
            if success:
                self.voltages_updated.emit(
                    list(self._controller.get_current_voltages())
                )
        except Exception as exc:
            logger.error("Zynq 连接失败: %s", exc)
            self.error_occurred.emit(str(exc))
            self.connected.emit(False)
        finally:
            self.operation_finished.emit()

    @Slot(list)
    def set_voltages(self, voltages: list):
        """设置所有通道电压。"""
        try:
            if self._controller is None:
                self.error_occurred.emit("Zynq 未连接")
                return
            success = self._controller.set_voltages(voltages)
            if not success:
                self.error_occurred.emit("Zynq 设置电压失败")
            self.voltages_updated.emit(
                list(self._controller.get_current_voltages())
            )
        except Exception as exc:
            self.error_occurred.emit(str(exc))
        finally:
            self.operation_finished.emit()

    @Slot()
    def disconnect_zynq(self):
        """断开 Zynq 连接。"""
        try:
            if self._controller:
                self._controller.close()
                self._controller = None
        except Exception as exc:
            logger.error("Zynq 断开失败: %s", exc)
            self.error_occurred.emit(str(exc))
        finally:
            self.operation_finished.emit()


# ======================================================================
# MeasurementWorker
# ======================================================================

class MeasurementWorker(BaseWorker):
    """插损测量 Worker — 对应 measure.py 的 InsertionLossMeasurer 流程。

    流程：初始化 → 加载/执行参考测量 → 插损测量（减去参考值）→ 保存
    """

    measurement_ready = Signal(list)    # 插损测量数据（减去参考后）
    reference_ready = Signal(list)      # 参考数据（reference_data_array）
    ref_loaded = Signal(list)           # 从文件加载的参考数据
    params_configured = Signal(dict)    # 参数配置完成
    initialized = Signal(bool)

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._measurer = None           # InsertionLossMeasurer 实例
        self._reference_data = None     # 参考数据（用于减去）

    @Slot()
    def initialize_devices(self):
        """初始化光学测量设备（TSL + MPM + DAQ）。

        使用 ReferenceMeasurement.initialize_optical_devices() 连接设备。
        不自动配置扫描参数 — 用户需要通过 configure_parameters 手动配置。
        """
        try:
            from reference_measurement import ReferenceMeasurement

            ref_meas = ReferenceMeasurement()
            if not ref_meas.initialize_optical_devices():
                self.error_occurred.emit("光学设备初始化失败")
                self.initialized.emit(False)
                return

            from measure import InsertionLossMeasurer
            self._measurer = InsertionLossMeasurer()
            self._measurer.reference_measurement = ref_meas

            self.initialized.emit(True)
        except Exception as exc:
            logger.error("测量设备初始化失败: %s", exc)
            self.error_occurred.emit(f"测量设备初始化失败: {exc}")
            self.initialized.emit(False)
        finally:
            self.operation_finished.emit()

    @Slot(dict)
    def configure_parameters(self, params: dict):
        """配置 TSL 扫描参数（从 GUI 输入）。"""
        try:
            if self._measurer is None or self._measurer.reference_measurement is None:
                self.error_occurred.emit("设备未初始化")
                return
            ref_meas = self._measurer.reference_measurement
            tsl = ref_meas.tsl
            tsl.set_power(params["power"])
            tsl.set_sweep_parameters(
                params["start_wavelength"],
                params["stop_wavelength"],
                params["sweep_step"],
                params["sweep_speed"],
            )
            ref_meas.ilsts.set_selected_channels(params)
            ref_meas.ilsts.set_selected_ranges(params)
            ref_meas.ilsts.set_sts_data_struct()
            ref_meas.ilsts.set_parameters()
            # 保存参数
            from santec import file_saving
            ref_meas.file_manager.save_set_params(
                file_saving.FILE_LAST_REF_PARAMS, tsl, params, ref_meas.ilsts
            )
            self.params_configured.emit(params)
        except Exception as exc:
            self.error_occurred.emit(f"参数配置失败: {exc}")
        finally:
            self.operation_finished.emit()

    @Slot(str)
    def load_reference_data(self, filepath: str):
        """从 JSON/DAT 文件加载参考数据并注入 ILSTS 引擎。

        与 voltage_scan_loss.py 一致：
        1. 读取 JSON → reference_data_array
        2. 调用 sts_reference_from_saved_file() 加载到 ILSTS 引擎
        """
        try:
            import json
            with open(filepath, "r", encoding="utf-8") as f:
                self._reference_data = json.load(f)
            if self._measurer is not None:
                self._measurer.reference_data = self._reference_data
                if (self._measurer.reference_measurement is not None
                        and self._measurer.reference_measurement.ilsts is not None):
                    ilsts = self._measurer.reference_measurement.ilsts
                    ilsts.reference_data_array = self._reference_data
                    # 加载到 ILSTS 引擎
                    if hasattr(ilsts, 'ref_data') and len(ilsts.ref_data) > 0:
                        ilsts.sts_reference_from_saved_file()
                        logger.info("参考数据已加载到 ILSTS 引擎")
            self.ref_loaded.emit(self._reference_data if self._reference_data else [])
        except Exception as exc:
            self.error_occurred.emit(f"加载参考数据失败: {exc}")
        finally:
            self.operation_finished.emit()

    @Slot()
    def run_reference(self):
        """执行参考测量扫描。"""
        try:
            if self._measurer is None or self._measurer.reference_measurement is None:
                self.error_occurred.emit("测量设备未初始化")
                return
            ref_meas = self._measurer.reference_measurement
            ref_meas.ilsts.sts_reference()
            ref_meas.file_manager.save_ref_data(ref_meas.ilsts)
            # 保存参考数据用于后续减法
            from santec import file_saving
            import json, os
            ref_file = file_saving.FILE_LAST_SCAN_REFERENCE_DATA
            if os.path.exists(ref_file):
                with open(ref_file, "r", encoding="utf-8") as f:
                    self._reference_data = json.load(f)
                self._measurer.reference_data = self._reference_data
            ref_data_array = ref_meas.ilsts.reference_data_array
            self.reference_ready.emit(ref_data_array if ref_data_array else [])
        except Exception as exc:
            self.error_occurred.emit(f"参考测量失败: {exc}")
        finally:
            self.operation_finished.emit()

    @Slot()
    def run_measurement(self):
        """执行插损测量（与 voltage_scan_loss.py 一致）。

        流程：
        1. 调用 sts_measurement() 执行 DUT 测量（需要 ILSTS 引擎中已有参考）
        2. 读取 ilsts.il_data_array（插损数据）和 ilsts.wavelength_table
        3. 构建 measurement_data 用于绘图
        """
        try:
            if self._measurer is None or self._measurer.reference_measurement is None:
                self.error_occurred.emit("测量设备未初始化")
                return

            ilsts = self._measurer.reference_measurement.ilsts
            logger.info("测量插损...")

            # 调用 measure_insertion_loss（内部调用 sts_measurement）
            self._measurer.reference_measurement.measure_insertion_loss()

            # 从 ilsts 读取插损数据（与 voltage_scan_loss.py 一致）
            measurement_data = []
            if hasattr(ilsts, 'il_data_array') and ilsts.il_data_array:
                if hasattr(ilsts, 'wavelength_table') and ilsts.wavelength_table:
                    for i, il_data in enumerate(ilsts.il_data_array):
                        measurement_data.append({
                            "MPMNumber": 0,
                            "SlotNumber": 0,
                            "ChannelNumber": i + 1,
                            "rescaled_wavelength": list(ilsts.wavelength_table),
                            "rescaled_reference_power": list(il_data),
                        })

            self.measurement_ready.emit(measurement_data)
        except Exception as exc:
            error_msg = str(exc)
            if "ReferenceNotExist" in error_msg:
                error_msg = (
                    "ILSTS 引擎中没有参考数据。请先执行参考测量或加载参考数据"
                )
            self.error_occurred.emit(f"插损测量失败: {error_msg}")
        finally:
            self.operation_finished.emit()


# ---------------------------------------------------------------------------
# ReferenceMeasurementWorker — 参考插损测量 Worker
# ---------------------------------------------------------------------------


class ReferenceMeasurementWorker(BaseWorker):
    """参考插损测量 Worker — 对应 reference_measurement.py 的 ReferenceMeasurement 流程。

    流程：初始化光设备 → 配置参数 → 执行参考扫描 → 保存参考数据
    """

    initialized = Signal(bool)
    params_configured = Signal(dict)    # 配置完成后的参数
    reference_ready = Signal(list)      # 参考数据 (reference_data_array)

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._ref_meas = None           # ReferenceMeasurement 实例

    @Slot()
    def initialize_devices(self):
        """初始化光设备（TSL + MPM + DAQ）。"""
        try:
            from reference_measurement import ReferenceMeasurement
            self._ref_meas = ReferenceMeasurement()
            success = self._ref_meas.initialize_optical_devices()
            self.initialized.emit(success)
        except Exception as exc:
            logger.error("参考测量设备初始化失败: %s", exc)
            self.error_occurred.emit(f"参考测量设备初始化失败: {exc}")
            self.initialized.emit(False)
        finally:
            self.operation_finished.emit()

    @Slot(dict)
    def configure_parameters(self, params: dict):
        """配置 TSL 扫描参数（从 GUI 输入，不弹 input()）。"""
        try:
            if self._ref_meas is None:
                self.error_occurred.emit("设备未初始化")
                return
            tsl = self._ref_meas.tsl
            # 设置 TSL 参数
            tsl.set_power(params["power"])
            tsl.set_sweep_parameters(
                params["start_wavelength"],
                params["stop_wavelength"],
                params["sweep_step"],
                params["sweep_speed"],
            )
            # 设置通道和动态范围
            self._ref_meas.ilsts.set_selected_channels(params)
            self._ref_meas.ilsts.set_selected_ranges(params)
            self._ref_meas.ilsts.set_sts_data_struct()
            self._ref_meas.ilsts.set_parameters()
            # 保存参数
            from santec import file_saving
            self._ref_meas.file_manager.save_set_params(
                file_saving.FILE_LAST_REF_PARAMS, tsl, params, self._ref_meas.ilsts
            )
            self.params_configured.emit(params)
        except Exception as exc:
            self.error_occurred.emit(f"参数配置失败: {exc}")
        finally:
            self.operation_finished.emit()

    @Slot()
    def run_reference_scan(self):
        """执行参考扫描。"""
        try:
            if self._ref_meas is None:
                self.error_occurred.emit("设备未初始化")
                return
            # 执行扫描（不弹 input）
            self._ref_meas.ilsts.sts_reference()
            # 保存参考数据
            self._ref_meas.file_manager.save_ref_data(self._ref_meas.ilsts)
            # 发射参考数据
            ref_data = self._ref_meas.ilsts.reference_data_array
            self.reference_ready.emit(ref_data if ref_data else [])
        except Exception as exc:
            self.error_occurred.emit(f"参考扫描失败: {exc}")
        finally:
            self.operation_finished.emit()


# ======================================================================
# ParallelWorker
# ======================================================================

class ParallelWorker(BaseWorker):
    """并行控制 Worker。"""

    result_ready = Signal(object)       # ParallelResult
    sweep_progress = Signal(int, int)   # (current_step, total_steps)
    sweep_finished = Signal(list)       # List[ParallelResult]
    initialized = Signal(bool)

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._controller = None

    @Slot(dict)
    def initialize(self, config: dict):
        """初始化并行控制器。"""
        try:
            from parallel_controller import ParallelController

            self._controller = ParallelController(config=config)
            success = self._controller.initialize()
            self.initialized.emit(success)
        except Exception as exc:
            logger.error("并行控制器初始化失败: %s", exc)
            self.error_occurred.emit(str(exc))
            self.initialized.emit(False)
        finally:
            self.operation_finished.emit()

    @Slot(list, bool)
    def run_parallel(self, voltages: list, include_vna: bool):
        """执行一次并行测量。"""
        try:
            if self._controller is None:
                self.error_occurred.emit("并行控制器未初始化")
                return
            result = self._controller.run_parallel_measurement(
                voltages, include_vna=include_vna
            )
            self.result_ready.emit(result)
        except Exception as exc:
            self.error_occurred.emit(str(exc))
        finally:
            self.operation_finished.emit()

    @Slot(dict)
    def run_sweep(self, params: dict):
        """执行电压扫描。"""
        try:
            if self._controller is None:
                self.error_occurred.emit("并行控制器未初始化")
                return

            channel = params["channel"]
            start_v = params["start_voltage"]
            end_v = params["end_voltage"]
            step_v = params["step_voltage"]
            include_vna = params.get("include_vna", True)

            # 计算总步数用于进度报告
            num_steps = int(round((end_v - start_v) / step_v)) + 1

            # 逐步执行以报告进度
            base_voltages = list(self._controller._voltage_controller.current_voltages)
            channel_idx = channel - 1
            results = []

            for i in range(num_steps):
                v = start_v + i * step_v
                voltages = list(base_voltages)
                voltages[channel_idx] = v
                result = self._controller.run_parallel_measurement(
                    voltages, include_vna=include_vna
                )
                results.append(result)
                self.sweep_progress.emit(i + 1, num_steps)

            self.sweep_finished.emit(results)
        except Exception as exc:
            self.error_occurred.emit(str(exc))
        finally:
            self.operation_finished.emit()

    @Slot()
    def emergency_stop(self):
        """紧急停止。"""
        try:
            if self._controller:
                self._controller.emergency_stop()
        except Exception as exc:
            self.error_occurred.emit(str(exc))
        finally:
            self.operation_finished.emit()

    def shutdown(self):
        """关闭并行控制器。"""
        try:
            if self._controller:
                self._controller.shutdown()
                self._controller = None
        except Exception as exc:
            logger.error("并行控制器关闭失败: %s", exc)


# ---------------------------------------------------------------------------
# CalibrationWorker — 定标流水线 Worker
# ---------------------------------------------------------------------------


class CalibrationWorker(BaseWorker):
    """光纤传感定标流水线 Worker。"""

    cal_loaded = Signal(int)        # 定标曲线数量
    meas_loaded = Signal(int)       # 测量曲线数量
    match_done = Signal(object)     # 匹配结果 dict
    evaluate_done = Signal(object)  # 求值结果 dict
    optimize_done = Signal(object)  # 参数优化结果 dict

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._cal_curves = []       # list[(float, S21Curve)]
        self._meas_curves = []      # list[(float, S21Curve)]
        self._table = None          # CalibrationTable
        self._match_info = None     # 匹配结果缓存
        self._all_results = []      # list[MatchResult]

    @Slot(str, int)
    def load_calibration(self, directory: str, smooth_window: int = 5):
        """加载定标数据目录并构建定标表。"""
        try:
            from src.calibration_pipeline import (
                load_curves_from_directory,
                build_calibration_table,
            )
            self._cal_curves = load_curves_from_directory(
                directory, metadata_key="delta_lambda"
            )
            self._table = build_calibration_table(
                self._cal_curves, smooth_window=smooth_window
            )
            self.cal_loaded.emit(len(self._cal_curves))
        except Exception as exc:
            logger.error("加载定标数据失败: %s", exc)
            self.error_occurred.emit(f"加载定标数据失败: {exc}")
        finally:
            self.operation_finished.emit()

    @Slot(str)
    def load_measurement(self, directory: str):
        """加载测量数据目录（每个电压一个 CSV）。"""
        try:
            from src.calibration_pipeline import load_curves_from_directory
            self._meas_curves = load_curves_from_directory(
                directory, metadata_key="voltage"
            )
            self.meas_loaded.emit(len(self._meas_curves))
        except Exception as exc:
            logger.error("加载测量数据失败: %s", exc)
            self.error_occurred.emit(f"加载测量数据失败: {exc}")
        finally:
            self.operation_finished.emit()

    @Slot(str)
    def load_measurement_file(self, filepath: str):
        """从单个合并 CSV 加载测量数据。

        支持电压扫描 VNA 模式导出的格式：
        Voltage,Frequency_Hz,Magnitude_dB
        每个电压值的数据行组成一条 S21 曲线。
        """
        try:
            import pandas as pd
            import numpy as np
            from src.calibration_pipeline import S21Curve

            df = pd.read_csv(filepath)

            # 检测格式
            if "Voltage" in df.columns and "Frequency_Hz" in df.columns and "Magnitude_dB" in df.columns:
                # 电压扫描 VNA 格式：按 Voltage 分组
                self._meas_curves = []
                for voltage, group in df.groupby("Voltage", sort=True):
                    freq = group["Frequency_Hz"].to_numpy(dtype=float) / 1e9  # Hz → GHz
                    mag = group["Magnitude_dB"].to_numpy(dtype=float)
                    self._meas_curves.append((float(voltage), S21Curve(frequency=freq, magnitude=mag)))
            elif "Frequency_Hz" in df.columns and "Magnitude_dB" in df.columns:
                # 单条曲线格式
                freq = df["Frequency_Hz"].to_numpy(dtype=float) / 1e9
                mag = df["Magnitude_dB"].to_numpy(dtype=float)
                self._meas_curves = [(0.0, S21Curve(frequency=freq, magnitude=mag))]
            else:
                self.error_occurred.emit(
                    f"CSV 格式不支持。需要列: Voltage,Frequency_Hz,Magnitude_dB "
                    f"或 Frequency_Hz,Magnitude_dB。实际列: {list(df.columns)}"
                )
                return

            self.meas_loaded.emit(len(self._meas_curves))
        except Exception as exc:
            logger.error("加载测量文件失败: %s", exc)
            self.error_occurred.emit(f"加载测量文件失败: {exc}")
        finally:
            self.operation_finished.emit()

    @Slot(int, int)
    def run_match(self, k_cand: int = 3, smooth_window: int = 5,
                  corr_bandwidth: float = None, match_mode: str = "correlation",
                  split_sign: bool = False):
        """执行曲线匹配 — 四种方式 × 正/负 Δλ。

        始终运行全部四种匹配方式，分正/负两组。
        """
        try:
            from src.calibration_pipeline import find_best_voltage

            if self._table is None:
                self.error_occurred.emit("请先加载定标数据")
                return
            if not self._meas_curves:
                self.error_occurred.emit("请先加载测量数据")
                return

            modes = ["correlation", "fpeak_nearest", "normalized_shape", "fpeak_fit"]
            mode_names = {
                "correlation": "归一化互相关",
                "fpeak_nearest": "fpeak最近邻",
                "normalized_shape": "归一化形状",
                "fpeak_fit": "洛伦兹拟合",
            }
            signs = [("Δλ>0", "positive"), ("Δλ<0", "negative")]

            all_match_results = {}  # {sign_label: {mode: {info}}}
            voltages = [v for v, _ in self._meas_curves]

            for sign_label, sign_key in signs:
                sub_table = self._table.filter_by_sign(sign_key)
                if len(sub_table) == 0:
                    continue
                all_match_results[sign_label] = {}
                for mode in modes:
                    try:
                        bv, bci, brho, ar = find_best_voltage(
                            measured_curves=self._meas_curves,
                            table=sub_table,
                            k_cand=k_cand,
                            smooth_window=smooth_window,
                            corr_bandwidth=corr_bandwidth,
                            match_mode=mode,
                        )
                        best_meas = next((c for v, c in self._meas_curves if v == bv), None)
                        best_cal = sub_table.entries[bci].curve
                        best_dl = sub_table.entries[bci].delta_lambda
                        if mode == "fpeak_fit" and ar:
                            bi = max(range(len(ar)), key=lambda i: ar[i].rho)
                            best_dl = ar[bi].delta_lambda
                        # 每个电压的 ρ 和 Δλ
                        per_voltage_rho = [r.rho for r in ar]
                        per_voltage_dl = [r.delta_lambda for r in ar]
                        all_match_results[sign_label][mode] = {
                            "best_voltage": bv,
                            "best_rho": brho,
                            "best_delta_lambda": best_dl,
                            "best_meas_curve": best_meas,
                            "best_cal_curve": best_cal,
                            "mode_name": mode_names[mode],
                            "voltages": voltages,
                            "per_voltage_rho": per_voltage_rho,
                            "per_voltage_dl": per_voltage_dl,
                        }
                    except Exception as e:
                        logger.warning("匹配失败 %s/%s: %s", sign_label, mode, e)

            self._match_info = {"all_match_results": all_match_results}
            self.match_done.emit(self._match_info)
        except Exception as exc:
            logger.error("曲线匹配失败: %s", exc)
            self.error_occurred.emit(f"曲线匹配失败: {exc}")
        finally:
            self.operation_finished.emit()

    @Slot(float)
    def run_optimize(self, target_dl: float, sign: str = "positive"):
        """网格搜索最佳参数组合，使匹配结果最接近目标 Δλ。

        搜索空间：
        - corr_bandwidth: [0, 0.5, 1.0, 1.5, 2.0, 3.0, 5.0] GHz
        - k_cand: [3, 5, 8, 10, 15]
        - smooth_window: [3, 5, 7, 9, 11]
        - match_mode: 四种方式

        对每组参数运行匹配，记录最佳 Δλ 与目标的误差。
        """
        try:
            from src.calibration_pipeline import find_best_voltage

            if self._table is None:
                self.error_occurred.emit("请先加载定标数据")
                return
            if not self._meas_curves:
                self.error_occurred.emit("请先加载测量数据")
                return

            sub_table = self._table.filter_by_sign(sign)
            if len(sub_table) == 0:
                self.error_occurred.emit(f"定标表中无 {sign} Δλ 数据")
                return

            modes = ["correlation"]
            mode_names = {
                "correlation": "归一化互相关",
            }
            bw_list = [0.0, 0.5, 1.0, 1.5, 2.0, 3.0, 5.0]
            k_list = [3, 5, 8, 10, 15]
            sw_list = [3, 5, 7, 9, 11]

            results = []  # list of dict
            total = len(modes) * len(bw_list) * len(k_list) * len(sw_list)
            count = 0

            for mode in modes:
                for bw in bw_list:
                    for k in k_list:
                        for sw in sw_list:
                            count += 1
                            try:
                                bv, bci, brho, ar = find_best_voltage(
                                    measured_curves=self._meas_curves,
                                    table=sub_table,
                                    k_cand=k,
                                    smooth_window=sw,
                                    corr_bandwidth=bw if bw > 0 else None,
                                    match_mode=mode,
                                )
                                best_dl = sub_table.entries[bci].delta_lambda
                                if mode == "fpeak_fit" and ar:
                                    bi = max(range(len(ar)),
                                             key=lambda i: ar[i].rho)
                                    best_dl = ar[bi].delta_lambda
                                error = abs(best_dl - target_dl)
                                results.append({
                                    "mode": mode,
                                    "mode_name": mode_names[mode],
                                    "corr_bandwidth": bw,
                                    "k_cand": k,
                                    "smooth_window": sw,
                                    "best_voltage": bv,
                                    "best_rho": brho,
                                    "best_dl": best_dl,
                                    "error": error,
                                })
                            except Exception:
                                pass

            if not results:
                self.error_occurred.emit("参数优化失败：所有参数组合均无法完成匹配")
                return

            results.sort(key=lambda r: (r["error"], -r["best_rho"]))

            self.optimize_done.emit({
                "target_dl": target_dl,
                "total_tried": total,
                "total_valid": len(results),
                "best": results[0],
                "top10": results[:10],
            })
        except Exception as exc:
            logger.error("参数优化失败: %s", exc)
            self.error_occurred.emit(f"参数优化失败: {exc}")
        finally:
            self.operation_finished.emit()

    @Slot(float, float, float)
    def run_evaluate(self, alpha: float = 9.08, t0: float = 20.0, lambda_ref: float = 1550.0):
        """根据匹配结果计算温度。"""
        try:
            from src.calibration_pipeline import calculate_temperature

            if self._match_info is None:
                self.error_occurred.emit("请先执行匹配")
                return

            delta_lambda = self._match_info["best_delta_lambda"]
            temp_result = calculate_temperature(
                delta_lambda=delta_lambda,
                lambda_ref=lambda_ref,
                alpha=alpha,
                t0=t0,
            )

            eval_result = {
                "best_voltage": self._match_info["best_voltage"],
                "rho_max": self._match_info["best_rho"],
                "delta_lambda": delta_lambda,
                "lambda_fbg": temp_result["lambda_fbg"],
                "delta_t": temp_result["delta_t"],
                "temperature": temp_result["temperature"],
            }
            self.evaluate_done.emit(eval_result)
        except Exception as exc:
            logger.error("温度计算失败: %s", exc)
            self.error_occurred.emit(f"温度计算失败: {exc}")
        finally:
            self.operation_finished.emit()

    def save_results(self, filepath: str):
        """保存匹配结果到 CSV。"""
        from src.calibration_pipeline import save_results_csv
        voltages = [v for v, _ in self._meas_curves]
        save_results_csv(self._all_results, voltages, filepath)


# ---------------------------------------------------------------------------
# SweepWorker — 定标扫描 Worker
# ---------------------------------------------------------------------------


class SweepWorker(BaseWorker):
    """定标扫描 Worker — 对应 sweep_controller.py 的 SweepController。"""

    initialized = Signal(bool)
    sweep_progress = Signal(int, int)   # (current, total)
    sweep_finished = Signal(object)     # list[SweepResult]
    table_built = Signal(int)           # 定标表条目数

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._controller = None

    @Slot(dict)
    def initialize(self, config: dict):
        """创建 SweepController 并初始化仪器。"""
        try:
            from src.sweep_controller import SweepConfig, SweepController
            from zynq_voltage_controller import ZynqVoltageController
            from vna import VNA
            from laser_controller import LaserController

            sweep_config = SweepConfig(
                vref=config["vref"],
                zynq_channel=config["zynq_channel"],
                lambda_ref=config["lambda_ref"],
                delta_lambda_start=config["delta_lambda_start"],
                delta_lambda_stop=config["delta_lambda_stop"],
                delta_lambda_step=config["delta_lambda_step"],
                vna_start_freq=config["vna_start_freq"],
                vna_stop_freq=config["vna_stop_freq"],
                vna_points=config.get("vna_points", 6001),
                output_dir=config.get("output_dir", "./sweep_data"),
            )

            # 创建仪器实例
            laser = LaserController()
            laser.connect()

            vna = VNA(
                start_freq=sweep_config.vna_start_freq,
                stop_freq=sweep_config.vna_stop_freq,
                points=sweep_config.vna_points,
            )
            vna.connect()
            vna.setup_parameters()

            zynq = ZynqVoltageController(
                port=sweep_config.zynq_port,
                baudrate=sweep_config.zynq_baudrate,
            )
            zynq.initialize()

            self._controller = SweepController(
                config=sweep_config,
                laser=laser,
                vna=vna,
                zynq=zynq,
                on_progress=self._on_progress,
                on_log=self._on_log,
            )

            success = self._controller.initialize()
            self.initialized.emit(success)
        except Exception as exc:
            logger.error("定标扫描初始化失败: %s", exc)
            self.error_occurred.emit(f"定标扫描初始化失败: {exc}")
            self.initialized.emit(False)
        finally:
            self.operation_finished.emit()

    def _on_progress(self, current: int, total: int):
        self.sweep_progress.emit(current, total)

    def _on_log(self, message: str):
        logger.info(message)

    @Slot()
    def run_sweep(self):
        """执行定标扫描。"""
        try:
            if self._controller is None:
                self.error_occurred.emit("请先初始化仪器")
                return
            results = self._controller.run_sweep()
            self.sweep_finished.emit(results)
        except Exception as exc:
            self.error_occurred.emit(f"定标扫描失败: {exc}")
        finally:
            self.operation_finished.emit()

    @Slot()
    def pause(self):
        if self._controller:
            self._controller.pause()

    @Slot()
    def resume(self):
        if self._controller:
            self._controller.resume()

    @Slot()
    def abort(self):
        if self._controller:
            self._controller.abort()

    @Slot()
    def build_calibration_table(self):
        """构建定标映射表。"""
        try:
            if self._controller is None:
                self.error_occurred.emit("请先初始化并完成扫描")
                return
            table = self._controller.build_calibration_table()
            self.table_built.emit(len(table))
        except Exception as exc:
            self.error_occurred.emit(f"构建定标表失败: {exc}")
        finally:
            self.operation_finished.emit()


# ---------------------------------------------------------------------------
# VoltageScanWorker — 电压扫描插损测量 Worker
# ---------------------------------------------------------------------------


class VoltageScanWorker(BaseWorker):
    """电压扫描测量 Worker — 支持插损模式和 VNA S21 模式。"""

    initialized = Signal(bool)
    ref_loaded = Signal(bool)
    scan_progress = Signal(int, int, float)       # (current, total, voltage)
    point_measured = Signal(float, object)         # 插损模式: (voltage, mdata)
    vna_point_measured = Signal(float, object, object)  # VNA 模式: (voltage, freq, mag)
    scan_finished = Signal(int)

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._zynq = None
        self._ref_meas = None
        self._vna = None
        self._reference_data = None
        self._abort_flag = False
        self._original_voltages = None

    @Slot()
    def initialize(self, vna_params=None):
        """初始化 Zynq + 光学设备（插损模式）或 Zynq + VNA（VNA 模式）。"""
        try:
            from zynq_voltage_controller import ZynqVoltageController
            self._zynq = ZynqVoltageController(port='COM3', num_channels=4)
            if not self._zynq.initialize():
                self.error_occurred.emit("Zynq 控制器初始化失败")
                self.initialized.emit(False)
                return

            if vna_params is not None:
                # VNA 模式
                from vna import VNA
                self._vna = VNA(
                    gpib_address=vna_params.get("gpib_address", 16),
                    start_freq=vna_params["start_freq"],
                    stop_freq=vna_params["stop_freq"],
                    points=vna_params.get("points", 6001),
                )
                self._vna.connect()
                self._vna.setup_parameters()
                logger.info("VNA 初始化成功")
            else:
                # 插损模式
                from reference_measurement import ReferenceMeasurement
                self._ref_meas = ReferenceMeasurement()
                if not self._ref_meas.initialize_optical_devices():
                    self.error_occurred.emit("光学测量设备初始化失败")
                    self.initialized.emit(False)
                    return
                # 自动加载上次的扫描参数
                from santec import file_saving
                import json, os
                params_file = file_saving.FILE_LAST_REF_PARAMS
                if os.path.exists(params_file):
                    with open(params_file, "r", encoding="utf-8") as f:
                        prev = json.load(f)
                    self._ref_meas.tsl.set_power(float(prev["power"]))
                    self._ref_meas.tsl.set_sweep_parameters(
                        float(prev["start_wavelength"]),
                        float(prev["stop_wavelength"]),
                        float(prev["sweep_step"]),
                        float(prev["sweep_speed"]),
                    )
                    self._ref_meas.ilsts.set_selected_channels(prev)
                    self._ref_meas.ilsts.set_selected_ranges(prev)
                    self._ref_meas.ilsts.set_sts_data_struct()
                    self._ref_meas.ilsts.set_parameters()

            self.initialized.emit(True)
        except Exception as exc:
            logger.error("电压扫描初始化失败: %s", exc)
            self.error_occurred.emit(f"初始化失败: {exc}")
            self.initialized.emit(False)
        finally:
            self.operation_finished.emit()

    @Slot(str)
    def load_reference(self, filepath: str):
        """加载参考数据并注入 ILSTS 引擎（仅插损模式）。"""
        try:
            import json
            with open(filepath, "r", encoding="utf-8") as f:
                self._reference_data = json.load(f)
            if self._ref_meas and self._ref_meas.ilsts:
                self._ref_meas.ilsts.reference_data_array = self._reference_data
                # 加载到 ILSTS 引擎
                if hasattr(self._ref_meas.ilsts, 'ref_data') and len(self._ref_meas.ilsts.ref_data) > 0:
                    self._ref_meas.ilsts.sts_reference_from_saved_file()
                    logger.info("参考数据已加载到 ILSTS 引擎")
            self.ref_loaded.emit(True)
        except Exception as exc:
            logger.error("加载参考数据失败: %s", exc)
            self.error_occurred.emit(f"加载参考数据失败: {exc}")
            self.ref_loaded.emit(False)
        finally:
            self.operation_finished.emit()

    @Slot(dict)
    def run_scan(self, params: dict):
        """执行电压扫描（根据 mode 选择插损或 VNA）。"""
        mode = params.get("mode", "loss")
        if mode == "vna":
            self._run_vna_scan(params)
        else:
            self._run_loss_scan(params)

    def _run_loss_scan(self, params: dict):
        """插损模式扫描（与 voltage_scan_loss.py 一致）。

        使用 sts_measurement() + il_data_array 获取插损数据。
        """
        try:
            import time
            channel = params["channel"]
            settle = params["settle_time"]
            voltages = self._build_voltage_list(params)
            total = len(voltages)

            self._abort_flag = False
            self._original_voltages = list(self._zynq.current_voltages)
            count = 0

            for i, voltage in enumerate(voltages):
                if self._abort_flag:
                    break
                target = list(self._original_voltages)
                target[channel - 1] = voltage
                if not self._zynq.set_voltages(target):
                    self.scan_progress.emit(i + 1, total, voltage)
                    continue
                time.sleep(settle)

                # DUT 测量（与 voltage_scan_loss.py 一致）
                self._ref_meas.measure_insertion_loss()

                # 从 ilsts 读取插损数据
                ilsts = self._ref_meas.ilsts
                mdata = []
                if hasattr(ilsts, 'il_data_array') and ilsts.il_data_array:
                    if hasattr(ilsts, 'wavelength_table') and ilsts.wavelength_table:
                        for j, il_data in enumerate(ilsts.il_data_array):
                            mdata.append({
                                "MPMNumber": 0,
                                "SlotNumber": 0,
                                "ChannelNumber": j + 1,
                                "rescaled_wavelength": list(ilsts.wavelength_table),
                                "rescaled_reference_power": list(il_data),
                            })

                self.point_measured.emit(voltage, mdata)
                count += 1
                self.scan_progress.emit(i + 1, total, voltage)

            if self._original_voltages:
                self._zynq.set_voltages(self._original_voltages)
            self.scan_finished.emit(count)
        except Exception as exc:
            logger.error("插损扫描失败: %s", exc)
            self.error_occurred.emit(f"插损扫描失败: {exc}")
            self._try_restore_voltages()
        finally:
            self.operation_finished.emit()

    def _run_vna_scan(self, params: dict):
        """VNA S21 模式扫描。"""
        try:
            import time
            channel = params["channel"]
            settle = params["settle_time"]
            voltages = self._build_voltage_list(params)
            total = len(voltages)

            self._abort_flag = False
            self._original_voltages = list(self._zynq.current_voltages)
            count = 0

            for i, voltage in enumerate(voltages):
                if self._abort_flag:
                    break
                target = list(self._original_voltages)
                target[channel - 1] = voltage
                if not self._zynq.set_voltages(target):
                    self.scan_progress.emit(i + 1, total, voltage)
                    continue
                time.sleep(settle)

                # VNA 测量
                data = self._vna.measure()
                freq = data["frequency"]
                mag = data["magnitude_dB"]

                self.vna_point_measured.emit(voltage, list(freq), list(mag))
                count += 1
                self.scan_progress.emit(i + 1, total, voltage)

            if self._original_voltages:
                self._zynq.set_voltages(self._original_voltages)
            self.scan_finished.emit(count)
        except Exception as exc:
            logger.error("VNA 扫描失败: %s", exc)
            self.error_occurred.emit(f"VNA 扫描失败: {exc}")
            self._try_restore_voltages()
        finally:
            self.operation_finished.emit()

    def _build_voltage_list(self, params: dict) -> list:
        # 检查是否使用功耗步进
        if "step_power" in params:
            start_power = params.get("start_power", 0)
            end_power = params.get("end_power", 0)
            step_power = params.get("step_power", 0.01)
            
            # 根据功率计算电压，R=100欧姆
            import math
            voltages = []
            power = start_power
            while power <= end_power + 1e-9:
                # P = U²/R → U = sqrt(P*R)
                voltage = math.sqrt(power * 100)
                voltages.append(round(voltage, 6))
                power += step_power
            return voltages
        else:
            # 保持原有电压步进模式
            start_v = params["start_voltage"]
            end_v = params["end_voltage"]
            step_v = params["step_voltage"]
            voltages = []
            v = start_v
            while v <= end_v + 1e-9:
                voltages.append(round(v, 6))
                v += step_v
            return voltages

    def _try_restore_voltages(self):
        if self._zynq and self._original_voltages:
            try:
                self._zynq.set_voltages(self._original_voltages)
            except Exception:
                pass

    def abort(self):
        self._abort_flag = True
"""
ParallelController - 并行仪器控制器

协调 VNA 矢网仪测量与光学插损测量的并行执行。
直接复用现有类，不修改其内部实现。
"""

import logging
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


class TaskStatus(Enum):
    """测量任务状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ParallelResult:
    """并行测量结果"""
    session_id: str
    optical_data: Optional[Dict[str, Any]]
    vna_data: Optional[Dict[str, Any]]
    voltages_applied: Optional[List[float]]
    optical_status: TaskStatus
    vna_status: TaskStatus
    optical_error: Optional[str] = None
    vna_error: Optional[str] = None
    start_time: float = 0.0
    end_time: float = 0.0


class ParallelController:
    """
    并行仪器控制器 - 协调 VNA 与光学测量的并行执行

    直接复用现有类：
    - ZynqVoltageController 用于电压控制
    - ReferenceMeasurement 用于光学参考测量
    - VNA 用于矢网仪 S 参数测量
    """

    def __init__(self, config: Optional[Dict] = None):
        self._config = config or {}

        # 解析配置，设置默认值
        self._voltage_settle_time: float = self._config.get('voltage_settle_time', 0.5)
        self._max_workers: int = self._config.get('max_workers', 2)
        self._output_dir: str = self._config.get('output_dir', './parallel_results')

        # 仪器实例（延迟初始化）
        self._voltage_controller = None
        self._reference_measurement = None
        self._vna = None

        # 线程池
        self._executor: Optional[ThreadPoolExecutor] = None

        # 线程安全锁
        self._optical_lock = threading.Lock()
        self._vna_lock = threading.Lock()
        self._result_lock = threading.Lock()

        # 状态
        self._initialized: bool = False
        self._results: List[ParallelResult] = []

        # 日志
        self._logger = logging.getLogger(self.__class__.__name__)

    def initialize(self) -> bool:
        """
        初始化所有仪器并创建线程池。

        流程：
        1. 初始化 ZynqVoltageController（COM串口, N通道）
        2. 初始化 ReferenceMeasurement（连接TSL+MPM+DAQ，配置参数）
        3. 初始化 VNA（连接GPIB，设置参数）
        4. 创建 ThreadPoolExecutor

        返回:
            bool: 所有仪器初始化是否成功
        """
        try:
            # 1. 电压控制器
            from zynq_voltage_controller import ZynqVoltageController
            port = self._config.get('voltage_port', 'COM3')
            baudrate = self._config.get('voltage_baudrate', 115200)
            num_channels = self._config.get('voltage_num_channels', 4)
            self._voltage_controller = ZynqVoltageController(
                port=port, baudrate=baudrate, num_channels=num_channels,
            )
            if not self._voltage_controller.initialize():
                self._logger.error("电压控制器初始化失败")
                return False
            self._logger.info("电压控制器初始化成功 (port=%s)", port)
        except Exception as exc:
            self._logger.error("电压控制器初始化异常: %s", exc)
            return False

        try:
            # 2. 光学测量系统
            from reference_measurement import ReferenceMeasurement
            self._reference_measurement = ReferenceMeasurement()
            self._reference_measurement.initialize_optical_devices()
            self._reference_measurement.configure_reference_parameters()
            self._logger.info("光学测量系统初始化成功")
        except Exception as exc:
            self._logger.error("光学测量系统初始化异常: %s", exc)
            return False

        try:
            # 3. VNA
            from vna import VNA
            self._vna = VNA(
                gpib_address=self._config.get('vna_gpib_address', 16),
                start_freq=self._config.get('vna_start_freq', 10e6),
                stop_freq=self._config.get('vna_stop_freq', 30e9),
                points=self._config.get('vna_points', 6001),
                power=self._config.get('vna_power', -10),
                if_bw=self._config.get('vna_if_bw', 1000),
                param=self._config.get('vna_param', 'S21'),
            )
            if not self._vna.connect():
                self._logger.error("VNA 连接失败")
                return False
            if not self._vna.setup_parameters():
                self._logger.error("VNA 参数设置失败")
                return False
            self._logger.info("VNA 初始化成功 (GPIB=%s)", self._vna.gpib_address)
        except Exception as exc:
            self._logger.error("VNA 初始化异常: %s", exc)
            return False

        # 4. 线程池
        self._executor = ThreadPoolExecutor(max_workers=self._max_workers)
        self._initialized = True
        self._logger.info("ParallelController 初始化完成 (workers=%d)", self._max_workers)
        return True

    # ------------------------------------------------------------------
    # 核心并行测量方法
    # ------------------------------------------------------------------

    def _run_optical_measurement(self, voltages: List[float]) -> Dict[str, Any]:
        """
        执行光学测量（在光学线程中运行）。

        流程：
        1. 获取 _optical_lock
        2. 设置电压，失败时抛出 RuntimeError
        3. 等待电压稳定
        4. 执行插损测量
        5. 提取波长和插损数据
        6. 释放 _optical_lock
        """
        with self._optical_lock:
            # 设置电压
            success = self._voltage_controller.set_voltages(voltages)
            if not success:
                raise RuntimeError(
                    f"电压设置失败: voltages={voltages}"
                )

            # 等待电压稳定
            time.sleep(self._voltage_settle_time)

            # 执行光学测量
            self._reference_measurement.measure_insertion_loss()

            # 提取数据
            ilsts = self._reference_measurement.ilsts
            return {
                'wavelengths': list(ilsts.wavelength_table),
                'il_data': [list(ch) for ch in ilsts.il_data_array],
                'reference_data_array': ilsts.reference_data_array,
            }

    def _run_vna_measurement(self) -> Dict[str, Any]:
        """
        执行 VNA 测量（在 VNA 线程中运行）。

        流程：
        1. 获取 _vna_lock
        2. 调用 VNA.measure()
        3. 释放 _vna_lock
        """
        with self._vna_lock:
            result = self._vna.measure()
            return {
                'frequency': result['frequency'],
                's_param': result['s_param'],
                'magnitude_dB': result['magnitude_dB'],
                'phase_deg': result['phase_deg'],
            }

    def run_parallel_measurement(
        self,
        voltages: List[float],
        include_vna: bool = True,
    ) -> ParallelResult:
        """
        执行一次并行测量：设置电压 → 并行执行光学测量和 VNA 测量。

        参数:
            voltages: 电压列表（4通道）
            include_vna: 是否同时执行 VNA 测量

        返回:
            ParallelResult: 合并后的测量结果
        """
        if not self._initialized:
            raise RuntimeError("ParallelController 未初始化，请先调用 initialize()")

        # 生成唯一 session_id: YYYYMMDD_HHMMSS_xxx
        now = datetime.now()
        session_id = now.strftime("%Y%m%d_%H%M%S") + f"_{random.randint(0, 999):03d}"

        start_time = time.time()

        # 初始化结果字段
        optical_data = None
        vna_data = None
        optical_status = TaskStatus.PENDING
        vna_status = TaskStatus.PENDING
        optical_error = None
        vna_error = None

        # 提交光学测量任务
        optical_future = self._executor.submit(self._run_optical_measurement, voltages)

        # 提交 VNA 测量任务（如果需要）
        vna_future = None
        if include_vna:
            vna_future = self._executor.submit(self._run_vna_measurement)

        # 收集光学测量结果
        try:
            optical_data = optical_future.result()
            optical_status = TaskStatus.COMPLETED
        except Exception as exc:
            optical_status = TaskStatus.FAILED
            optical_error = str(exc)
            self._logger.warning("光学测量失败: %s", exc)

        # 收集 VNA 测量结果
        if vna_future is not None:
            try:
                vna_data = vna_future.result()
                vna_status = TaskStatus.COMPLETED
            except Exception as exc:
                vna_status = TaskStatus.FAILED
                vna_error = str(exc)
                self._logger.warning("VNA 测量失败: %s", exc)
        else:
            vna_status = TaskStatus.PENDING

        end_time = time.time()

        result = ParallelResult(
            session_id=session_id,
            optical_data=optical_data,
            vna_data=vna_data,
            voltages_applied=list(voltages),
            optical_status=optical_status,
            vna_status=vna_status,
            optical_error=optical_error,
            vna_error=vna_error,
            start_time=start_time,
            end_time=end_time,
        )

        # 线程安全地追加结果
        with self._result_lock:
            self._results.append(result)

        return result

    # ------------------------------------------------------------------
    # 批量扫描和优化接口
    # ------------------------------------------------------------------

    def run_voltage_sweep_parallel(
        self,
        channel: int,
        start_voltage: float,
        end_voltage: float,
        step_voltage: float,
        include_vna: bool = True,
    ) -> List[ParallelResult]:
        """
        并行电压扫描：对每个电压点，并行执行光学测量和 VNA 测量。

        参数:
            channel: 控制通道（1-4）
            start_voltage: 起始电压
            end_voltage: 终止电压
            step_voltage: 步进电压
            include_vna: 是否同时执行 VNA 测量

        返回:
            List[ParallelResult]: 每个电压点的并行测量结果
        """
        if not self._initialized:
            raise RuntimeError("ParallelController 未初始化，请先调用 initialize()")

        # 计算电压序列
        num_steps = int(round((end_voltage - start_voltage) / step_voltage)) + 1
        voltage_sequence = [
            start_voltage + i * step_voltage for i in range(num_steps)
        ]

        # 获取当前基准电压（4通道）
        base_voltages = list(self._voltage_controller.current_voltages)
        channel_idx = channel - 1  # 转为 0-based 索引

        results: List[ParallelResult] = []
        vna_available = True

        for v in voltage_sequence:
            voltages = list(base_voltages)
            voltages[channel_idx] = v

            # 如果 VNA 在之前的点已不可用，后续点直接标记 VNA 为 FAILED
            use_vna = include_vna and vna_available

            result = self.run_parallel_measurement(voltages, include_vna=use_vna)

            # 检测 VNA 是否在本次测量中变为不可用
            if use_vna and result.vna_status == TaskStatus.FAILED:
                vna_available = False
                self._logger.warning(
                    "VNA 在电压 %.3fV 处变为不可用，后续扫描点将跳过 VNA 测量", v
                )

            # 如果 VNA 不可用且用户原本请求了 VNA，标记状态
            if include_vna and not use_vna:
                result.vna_status = TaskStatus.FAILED
                result.vna_error = result.vna_error or "VNA 在之前的扫描点变为不可用"

            results.append(result)

        return results

    def create_optimization_objective(
        self,
        optical_objective_func: Callable,
        include_vna: bool = False,
    ) -> Callable:
        """
        创建与 OptimizationAdapter 兼容的目标函数。

        参数:
            optical_objective_func: 光学目标函数，接受光学数据字典，返回 FOM 值
            include_vna: 是否在优化过程中同时执行 VNA 测量

        返回:
            Callable: 签名为 (voltages) -> dict 的目标函数
                     返回值包含 'fom', 'voltages' 键
                     如果 include_vna=True，还包含 'vna_data' 键
        """
        error_output = {'voltages': -1, 'fom': 1000.0}

        def objective(voltages) -> Dict[str, Any]:
            try:
                result = self.run_parallel_measurement(
                    list(voltages), include_vna=include_vna,
                )
            except Exception as exc:
                self._logger.warning("并行测量异常: %s", exc)
                return dict(error_output)

            # 光学测量失败 → 返回错误输出
            if result.optical_status != TaskStatus.COMPLETED or result.optical_data is None:
                return dict(error_output)

            # 使用用户提供的目标函数计算 FOM
            try:
                fom = optical_objective_func(result.optical_data)
            except Exception as exc:
                self._logger.warning("目标函数计算异常: %s", exc)
                return dict(error_output)

            output: Dict[str, Any] = {
                'fom': fom,
                'voltages': list(voltages),
            }

            if include_vna and result.vna_data is not None:
                output['vna_data'] = result.vna_data

            return output

        return objective

    # ------------------------------------------------------------------
    # 辅助功能和系统管理
    # ------------------------------------------------------------------

    def emergency_stop(self) -> None:
        """
        紧急停止：停止所有任务，电压置零。

        尽力而为——任何步骤失败都不会阻止后续步骤执行。
        """
        # 1. 停止线程池
        if self._executor:
            try:
                self._executor.shutdown(wait=False, cancel_futures=True)
            except Exception:
                pass

        # 2. 电压置零
        if self._voltage_controller:
            try:
                self._voltage_controller.set_voltages([0.0, 0.0, 0.0, 0.0])
            except Exception:
                pass

        self._logger.warning("紧急停止已执行")

    def get_results(self) -> List[ParallelResult]:
        """获取所有测量结果的副本。"""
        with self._result_lock:
            return list(self._results)

    def get_status(self) -> Dict[str, Any]:
        """
        获取系统状态。

        返回:
            dict: 包含各仪器连接状态、当前电压、测量计数等
        """
        status: Dict[str, Any] = {
            'initialized': self._initialized,
            'measurement_count': len(self._results),
        }

        # 电压控制器状态
        if self._voltage_controller is not None:
            status['voltage_controller'] = {
                'connected': getattr(self._voltage_controller, '_initialized', False),
                'current_voltages': list(
                    getattr(self._voltage_controller, 'current_voltages', [])
                ),
            }
        else:
            status['voltage_controller'] = {'connected': False, 'current_voltages': []}

        # 光学测量系统状态
        status['optical_system'] = {
            'connected': self._reference_measurement is not None,
        }

        # VNA 状态
        if self._vna is not None:
            status['vna'] = {
                'connected': getattr(self._vna, 'connected', False),
            }
        else:
            status['vna'] = {'connected': False}

        return status

    def export_results_csv(self, filepath: str) -> None:
        """
        将所有 ParallelResult 导出为 CSV 格式。

        包含 session_id、voltages_applied、optical_status、vna_status、
        optical_error、vna_error，以及光学/VNA 数据摘要。
        """
        import csv

        with self._result_lock:
            results_copy = list(self._results)

        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                'session_id',
                'voltages_applied',
                'optical_status',
                'vna_status',
                'optical_error',
                'vna_error',
                'optical_wavelength_range',
                'optical_il_channels',
                'vna_freq_range',
                'vna_points',
            ])

            for r in results_copy:
                # 光学数据摘要
                wl_range = ''
                il_channels = ''
                if r.optical_data is not None:
                    wls = r.optical_data.get('wavelengths', [])
                    if wls:
                        wl_range = f"{wls[0]:.2f}-{wls[-1]:.2f}"
                    il_data = r.optical_data.get('il_data', [])
                    il_channels = str(len(il_data))

                # VNA 数据摘要
                freq_range = ''
                vna_pts = ''
                if r.vna_data is not None:
                    freqs = r.vna_data.get('frequency', [])
                    if hasattr(freqs, '__len__') and len(freqs) > 0:
                        freq_range = f"{freqs[0]:.0f}-{freqs[-1]:.0f}"
                        vna_pts = str(len(freqs))

                writer.writerow([
                    r.session_id,
                    str(r.voltages_applied),
                    r.optical_status.value,
                    r.vna_status.value,
                    r.optical_error or '',
                    r.vna_error or '',
                    wl_range,
                    il_channels,
                    freq_range,
                    vna_pts,
                ])

    def shutdown(self) -> None:
        """
        关闭系统：电压置零，关闭所有仪器连接，关闭线程池。
        """
        # 1. 电压置零
        if self._voltage_controller:
            try:
                self._voltage_controller.set_voltages([0.0, 0.0, 0.0, 0.0])
            except Exception as exc:
                self._logger.error("关闭时电压置零失败: %s", exc)

        # 2. 关闭 VNA 连接
        if self._vna:
            try:
                self._vna.close()
            except Exception as exc:
                self._logger.error("关闭 VNA 失败: %s", exc)

        # 3. 关闭电压控制器串口
        if self._voltage_controller:
            try:
                self._voltage_controller.close()
            except Exception as exc:
                self._logger.error("关闭电压控制器失败: %s", exc)

        # 4. 关闭线程池
        if self._executor:
            try:
                self._executor.shutdown(wait=True)
            except Exception as exc:
                self._logger.error("关闭线程池失败: %s", exc)

        # 5. 重置 TSL/MPM
        if self._reference_measurement and hasattr(self._reference_measurement, 'tsl'):
            tsl = self._reference_measurement.tsl
            if tsl is not None:
                try:
                    tsl.query("*RST")
                except Exception as exc:
                    self._logger.error("重置 TSL 失败: %s", exc)

        self._initialized = False
        self._logger.info("ParallelController 已关闭")

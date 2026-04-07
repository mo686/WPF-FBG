"""
定标扫描仪器控制模块。

协调激光器波长扫描与 VNA S21 数据采集的定标流程：
固定微环电压 Vref → 逐步改变激光器波长 → VNA 测量 → 保存 CSV。
"""

from dataclasses import dataclass, field
from typing import Optional, Callable
from pathlib import Path
from datetime import datetime
import threading
import time
import json
import os

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# 数据类
# ---------------------------------------------------------------------------

@dataclass
class SweepConfig:
    """扫描参数配置。"""

    # 微环参考电压
    vref: float                                     # V, 范围 0-10
    zynq_channel: int                               # Zynq 通道编号（从 1 开始）

    # 波长参数
    lambda_ref: float                               # nm, 参考波长
    delta_lambda_start: float                       # pm, 波长偏移起始值
    delta_lambda_stop: float                        # pm, 波长偏移终止值
    delta_lambda_step: float                        # pm, 波长偏移步长

    # VNA 参数
    vna_start_freq: float                           # Hz
    vna_stop_freq: float                            # Hz
    vna_points: int = 6001
    vna_power: float = -10.0                        # dBm
    vna_if_bw: float = 1000.0                       # Hz
    vna_param: str = "S21"

    # Zynq 串口参数
    zynq_port: str = "COM3"
    zynq_baudrate: int = 115200

    # 等待时间
    wavelength_settle_time: float = 1.0             # 秒
    measurement_settle_time: float = 0.5            # 秒

    # 输出目录
    output_dir: str = "./sweep_data"


@dataclass
class SweepResult:
    """单个波长偏移点的采集结果。"""

    delta_lambda: float                             # pm, 当前波长偏移
    wavelength: float                               # nm, 实际设置的波长
    frequency: np.ndarray                           # Hz, 频率数组
    magnitude_dB: np.ndarray                        # dB, 幅度数组
    csv_path: Optional[str] = None                  # 保存的 CSV 路径（失败时为 None）
    success: bool = True                            # 该点是否采集成功
    error: Optional[str] = None                     # 错误信息


@dataclass
class SweepState:
    """扫描运行时状态。"""

    current_index: int = 0                          # 当前步骤索引
    total_steps: int = 0                            # 总步骤数
    current_delta_lambda: float = 0.0               # 当前波长偏移值 (pm)
    collected_count: int = 0                        # 已成功采集的曲线数
    skipped_count: int = 0                          # 已跳过的点数
    is_running: bool = False
    is_paused: bool = False
    start_time: Optional[float] = None
    elapsed_time: float = 0.0


# ---------------------------------------------------------------------------
# 控制器
# ---------------------------------------------------------------------------

class SweepController:
    """协调激光器波长扫描与 VNA S21 数据采集的定标扫描控制器。"""

    def __init__(
        self,
        config: SweepConfig,
        laser,
        vna,
        zynq,
        on_progress: Optional[Callable[[int, int], None]] = None,
        on_log: Optional[Callable[[str], None]] = None,
    ):
        self._config = config
        self._laser = laser
        self._vna = vna
        self._zynq = zynq
        self._on_progress = on_progress
        self._on_log = on_log
        self._state = SweepState()

        # 线程控制标志
        self._pause_event = threading.Event()
        self._pause_event.set()  # 初始为非暂停状态
        self._abort_flag = False
        self._running_lock = threading.Lock()

    # --- 辅助 ---

    def _log(self, message: str) -> None:
        """发送日志消息（如果回调已注册）。"""
        if self._on_log:
            self._on_log(message)

    def get_state(self) -> SweepState:
        """返回当前扫描状态的副本。"""
        return self._state

    # --- 生命周期 ---

    def initialize(self) -> bool:
        """
        初始化仪器：设置 Zynq 电压 → 配置 VNA 参数。

        任一步骤失败返回 False 并断开已连接仪器。
        """
        # 1. 设置 Zynq Vref
        try:
            voltages = [0.0] * self._zynq.num_channels
            voltages[self._config.zynq_channel - 1] = self._config.vref
            ok = self._zynq.set_voltages(voltages)
            if not ok:
                self._log("Zynq 电压设置失败")
                self._safe_disconnect_all()
                return False
            self._log(f"Zynq 通道 {self._config.zynq_channel} 电压已设置为 {self._config.vref} V")
        except Exception as e:
            self._log(f"Zynq 电压设置异常: {e}")
            self._safe_disconnect_all()
            return False

        # 2. 配置 VNA 参数
        try:
            ok = self._vna.setup_parameters()
            if not ok:
                self._log("VNA 参数配置失败")
                self._safe_disconnect_all()
                return False
            self._log("VNA 参数配置完成")
        except Exception as e:
            self._log(f"VNA 参数配置异常: {e}")
            self._safe_disconnect_all()
            return False

        self._log("所有仪器初始化成功")
        return True

    def shutdown(self) -> None:
        """
        安全关闭：恢复激光器波长 → 断开所有仪器。

        每步失败记录日志但继续执行。Zynq 电压保留不变。
        """
        # 1. 恢复激光器波长为 λref
        try:
            self._laser.set_wavelength(self._config.lambda_ref)
            self._log(f"激光器波长已恢复为 {self._config.lambda_ref} nm")
        except Exception as e:
            self._log(f"恢复激光器波长失败: {e}")

        # 2. 断开激光器
        try:
            self._laser.disconnect()
            self._log("激光器已断开")
        except Exception as e:
            self._log(f"断开激光器失败: {e}")

        # 3. 关闭 VNA
        try:
            self._vna.close()
            self._log("VNA 已关闭")
        except Exception as e:
            self._log(f"关闭 VNA 失败: {e}")

        # 4. 关闭 Zynq
        try:
            self._zynq.close()
            self._log("Zynq 已关闭")
        except Exception as e:
            self._log(f"关闭 Zynq 失败: {e}")

    def _safe_disconnect_all(self) -> None:
        """尝试断开所有仪器，忽略异常。"""
        for name, instrument, method in [
            ("激光器", self._laser, "disconnect"),
            ("VNA", self._vna, "close"),
            ("Zynq", self._zynq, "close"),
        ]:
            try:
                getattr(instrument, method)()
            except Exception as e:
                self._log(f"断开 {name} 失败: {e}")

    # --- 扫描控制 ---

    def run_sweep(self) -> list:
        """
        执行定标扫描：逐点设置波长 → 等待 → VNA 测量 → 保存 CSV。

        支持暂停/中止，仪器操作失败时跳过该点。
        使用 _running_lock 防止重复启动。

        Returns:
            list[SweepResult]: 所有波长偏移点的采集结果。
        """
        if not self._running_lock.acquire(blocking=False):
            raise RuntimeError("扫描已在运行中")

        try:
            dl_list = self.delta_lambda_list
            total = len(dl_list)
            results: list = []

            self._abort_flag = False
            self._pause_event.set()
            self._state = SweepState(
                total_steps=total,
                is_running=True,
                start_time=time.time(),
            )
            self._log(f"扫描开始，共 {total} 个波长偏移点")

            for i, dl in enumerate(dl_list):
                # 暂停检查
                self._pause_event.wait()

                # 中止检查
                if self._abort_flag:
                    self._log("扫描已中止")
                    break

                wavelength = self._config.lambda_ref + dl / 1000.0
                self._state.current_index = i
                self._state.current_delta_lambda = dl

                # 1. 设置激光器波长
                try:
                    ok = self._laser.set_wavelength(wavelength)
                    if not ok:
                        raise RuntimeError(f"set_wavelength 返回 False")
                    self._log(f"[{i+1}/{total}] 激光器波长已设置为 {wavelength} nm (Δλ={dl} pm)")
                except Exception as e:
                    self._log(f"[{i+1}/{total}] 激光器波长设置失败 (Δλ={dl} pm): {e}")
                    self._state.skipped_count += 1
                    results.append(SweepResult(
                        delta_lambda=dl, wavelength=wavelength,
                        frequency=np.array([]), magnitude_dB=np.array([]),
                        success=False, error=str(e),
                    ))
                    if self._on_progress:
                        self._on_progress(i + 1, total)
                    continue

                # 2. 等待波长稳定
                time.sleep(self._config.wavelength_settle_time)

                # 3. VNA 测量
                try:
                    data = self._vna.measure()
                    if data is None:
                        raise RuntimeError("VNA measure() 返回 None")
                    freq = data['frequency']
                    mag = data['magnitude_dB']
                    self._log(f"[{i+1}/{total}] VNA 测量完成 (Δλ={dl} pm)")
                except Exception as e:
                    self._log(f"[{i+1}/{total}] VNA 测量失败 (Δλ={dl} pm): {e}")
                    self._state.skipped_count += 1
                    results.append(SweepResult(
                        delta_lambda=dl, wavelength=wavelength,
                        frequency=np.array([]), magnitude_dB=np.array([]),
                        success=False, error=str(e),
                    ))
                    if self._on_progress:
                        self._on_progress(i + 1, total)
                    continue

                # 4. 等待测量稳定
                time.sleep(self._config.measurement_settle_time)

                # 5. 保存 CSV
                csv_path = self.save_curve_csv(dl, freq, mag)

                self._state.collected_count += 1
                results.append(SweepResult(
                    delta_lambda=dl, wavelength=wavelength,
                    frequency=freq, magnitude_dB=mag,
                    csv_path=csv_path, success=True,
                ))

                if self._on_progress:
                    self._on_progress(i + 1, total)

            # 扫描结束，更新状态
            self._state.is_running = False
            self._state.elapsed_time = time.time() - self._state.start_time

            # 保存元数据
            self.save_metadata(results)

            self._log(
                f"扫描完成：采集 {self._state.collected_count} 条，"
                f"跳过 {self._state.skipped_count} 条，"
                f"耗时 {self._state.elapsed_time:.1f} 秒"
            )
            return results
        finally:
            self._state.is_running = False
            self._running_lock.release()

    def pause(self) -> None:
        """暂停扫描（在当前波长点采集完成后生效）。"""
        self._pause_event.clear()
        self._state.is_paused = True
        self._log("扫描已暂停")

    def resume(self) -> None:
        """恢复已暂停的扫描。"""
        self._state.is_paused = False
        self._pause_event.set()
        self._log("扫描已恢复")

    def abort(self) -> None:
        """中止扫描，恢复激光器波长为 λref。"""
        self._abort_flag = True
        # 如果处于暂停状态，需要先恢复以让循环退出
        self._pause_event.set()
        self._state.is_paused = False
        self._log("正在中止扫描...")
        try:
            self._laser.set_wavelength(self._config.lambda_ref)
            self._log(f"激光器波长已恢复为 {self._config.lambda_ref} nm")
        except Exception as e:
            self._log(f"中止时恢复激光器波长失败: {e}")

    # --- 数据保存 ---

    def save_curve_csv(
        self,
        delta_lambda: float,
        frequency: np.ndarray,
        magnitude_dB: np.ndarray,
    ) -> Optional[str]:
        """
        将单条 S21 曲线保存为 CSV 文件。

        列名 ``Frequency_Hz`` 和 ``Magnitude_dB``，与 calibration_pipeline 兼容。
        文件名格式 ``delta_lambda_{value}.csv``。

        Returns:
            保存成功时返回文件路径，失败时返回 None。
        """
        try:
            out_dir = Path(self._config.output_dir)
            out_dir.mkdir(parents=True, exist_ok=True)

            filename = f"delta_lambda_{delta_lambda}.csv"
            filepath = out_dir / filename

            df = pd.DataFrame({
                "Frequency_Hz": frequency,
                "Magnitude_dB": magnitude_dB,
            })
            df.to_csv(filepath, index=False)
            self._log(f"已保存 CSV: {filepath}")
            return str(filepath)
        except Exception as e:
            self._log(f"保存 CSV 失败 (Δλ={delta_lambda} pm): {e}")
            return None

    def save_metadata(self, results: list) -> str:
        """
        生成 metadata.json，记录扫描参数和文件列表。

        Returns:
            metadata.json 的文件路径。
        """
        out_dir = Path(self._config.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        files = []
        for r in results:
            if r.csv_path is not None:
                files.append({
                    "delta_lambda": r.delta_lambda,
                    "path": os.path.basename(r.csv_path),
                })

        metadata = {
            "vref": self._config.vref,
            "lambda_ref": self._config.lambda_ref,
            "zynq_channel": self._config.zynq_channel,
            "delta_lambda_list": self.delta_lambda_list,
            "vna_params": {
                "start_freq": self._config.vna_start_freq,
                "stop_freq": self._config.vna_stop_freq,
                "points": self._config.vna_points,
                "power": self._config.vna_power,
                "if_bw": self._config.vna_if_bw,
                "param": self._config.vna_param,
            },
            "files": files,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "total_collected": self._state.collected_count,
            "total_skipped": self._state.skipped_count,
            "elapsed_seconds": self._state.elapsed_time,
        }

        filepath = out_dir / "metadata.json"
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=4, ensure_ascii=False)
        self._log(f"已保存元数据: {filepath}")
        return str(filepath)

    # --- Pipeline 集成 ---

    def get_output_directory(self) -> str:
        """返回配置的输出目录路径。"""
        return self._config.output_dir

    def build_calibration_table(self, smooth_window: int = 5):
        """
        调用 calibration_pipeline 加载扫描数据并构建定标映射表。

        Returns:
            CalibrationTable 实例。

        Raises:
            calibration_pipeline 处理过程中的异常直接向上传播。
        """
        from src.calibration_pipeline import (
            load_curves_from_directory,
            build_calibration_table as _build_table,
        )

        curves = load_curves_from_directory(self._config.output_dir)
        return _build_table(curves, smooth_window=smooth_window)

    # --- 属性 ---

    @property
    def delta_lambda_list(self) -> list:
        """根据 config 计算波长偏移列表 [Δλ1, Δλ2, …, ΔλM]。"""
        start = self._config.delta_lambda_start
        stop = self._config.delta_lambda_stop
        step = self._config.delta_lambda_step

        if step == 0:
            raise ValueError("Δλ_step 不能为零")

        if start == stop:
            return [start]

        num = int(round((stop - start) / step)) + 1
        return [start + i * step for i in range(num)]

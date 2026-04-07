"""
共享 fixtures 和 Mock 类，用于 ParallelController 测试。

Mock 对象模拟真实仪器接口（ZynqVoltageController、ReferenceMeasurement、VNA），
保持与 src/ 中真实类一致的方法签名和返回类型。
"""

import time
import threading
import numpy as np
import pytest


# ---------------------------------------------------------------------------
# MockZynqVoltageController
# ---------------------------------------------------------------------------

class MockZynqVoltageController:
    """模拟 ZynqVoltageController（src/zynq_voltage_controller.py）"""

    def __init__(self, port='COM3', baudrate=115200, num_channels=4):
        self.port = port
        self.baudrate = baudrate
        self.num_channels = num_channels
        self.current_voltages = [0.0] * num_channels
        self.serial = None

        # 测试辅助：记录调用
        self.call_log = []
        # 控制 set_voltages 是否成功
        self.should_fail = False
        self._initialized = False

    def initialize(self):
        self._initialized = True
        self.call_log.append(('initialize', time.time()))
        return True

    def set_voltages(self, voltages):
        ts = time.time()
        self.call_log.append(('set_voltages', ts, list(voltages)))
        if self.should_fail:
            return False
        if len(voltages) != self.num_channels:
            return False
        self.current_voltages = list(voltages)
        return True

    def close(self):
        self.call_log.append(('close', time.time()))
        self._initialized = False


# ---------------------------------------------------------------------------
# MockILSTS  (模拟 StsProcess.ilsts 暴露的数据结构)
# ---------------------------------------------------------------------------

class MockILSTS:
    """模拟 StsProcess / ILSTS 提供的数据属性"""

    def __init__(self, num_points=100, num_channels=1):
        self.num_points = num_points
        self.num_channels = num_channels
        self._regenerate()

    def _regenerate(self):
        """生成一组随机波长/插损数据"""
        self.wavelength_table = np.linspace(1500.0, 1600.0, self.num_points).tolist()
        self.il_data_array = [
            np.random.uniform(-30.0, 0.0, self.num_points).tolist()
            for _ in range(self.num_channels)
        ]
        self.reference_data_array = [
            {
                'MPMNumber': 0,
                'SlotNumber': 0,
                'ChannelNumber': ch,
                'log_data': np.random.uniform(-40.0, 0.0, self.num_points).tolist(),
            }
            for ch in range(self.num_channels)
        ]


# ---------------------------------------------------------------------------
# MockReferenceMeasurement
# ---------------------------------------------------------------------------

class MockReferenceMeasurement:
    """模拟 ReferenceMeasurement（src/reference_measurement.py）"""

    def __init__(self, num_points=100, num_channels=1):
        self.ilsts = MockILSTS(num_points=num_points, num_channels=num_channels)
        self.tsl = None
        self.mpm = None
        self.daq = None

        # 测试辅助
        self.call_log = []
        self.should_fail = False

    def initialize_optical_devices(self):
        self.call_log.append(('initialize_optical_devices', time.time()))
        return True

    def configure_reference_parameters(self):
        self.call_log.append(('configure_reference_parameters', time.time()))
        return True

    def measure_insertion_loss(self):
        ts = time.time()
        self.call_log.append(('measure_insertion_loss', ts))
        if self.should_fail:
            raise RuntimeError("Mock optical measurement failure")
        # 每次测量重新生成随机数据
        self.ilsts._regenerate()
        return True


# ---------------------------------------------------------------------------
# MockVNA
# ---------------------------------------------------------------------------

class MockVNA:
    """模拟 VNA（src/vna.py）"""

    def __init__(self, gpib_address=16, start_freq=10e6, stop_freq=30e9,
                 points=101, power=-10, if_bw=1000, param='S21',
                 save_dir='./vna_data'):
        self.gpib_address = gpib_address
        self.start_freq = start_freq
        self.stop_freq = stop_freq
        self.points = points
        self.power = power
        self.if_bw = if_bw
        self.param = param
        self.save_dir = save_dir
        self.connected = False

        # 测试辅助
        self.call_log = []
        self.should_fail = False

    def connect(self):
        self.call_log.append(('connect', time.time()))
        self.connected = True
        return True

    def setup_parameters(self):
        self.call_log.append(('setup_parameters', time.time()))
        return True

    def measure(self):
        ts = time.time()
        self.call_log.append(('measure', ts))
        if self.should_fail:
            raise RuntimeError("Mock VNA measurement failure")
        freq = np.linspace(self.start_freq, self.stop_freq, self.points)
        real_part = np.random.uniform(-1, 1, self.points)
        imag_part = np.random.uniform(-1, 1, self.points)
        s_param = real_part + 1j * imag_part
        magnitude_dB = 20 * np.log10(np.abs(s_param))
        phase_deg = np.angle(s_param, deg=True)
        return {
            'frequency': freq,
            's_param': s_param,
            'magnitude_dB': magnitude_dB,
            'phase_deg': phase_deg,
        }

    def close(self):
        self.call_log.append(('close', time.time()))
        self.connected = False


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_voltage_controller():
    return MockZynqVoltageController(port='COM3', num_channels=4)


@pytest.fixture
def mock_reference_measurement():
    return MockReferenceMeasurement(num_points=100, num_channels=1)


@pytest.fixture
def mock_vna():
    return MockVNA(points=101)


@pytest.fixture
def mock_parallel_controller():
    """
    创建一个使用 Mock 仪器的 ParallelController 实例。

    由于 ParallelController 尚未实现（任务 2），此 fixture 采用延迟导入。
    当 ParallelController 可用后，fixture 会跳过真实的 initialize() 流程，
    直接注入 Mock 对象并将控制器标记为已初始化。
    """
    from src.parallel_controller import ParallelController

    config = {
        'voltage_settle_time': 0.0,   # 测试中不需要等待
        'max_workers': 2,
        'output_dir': './test_parallel_results',
        'voltage_port': 'COM3',
        'voltage_num_channels': 4,
        'vna_gpib_address': 16,
        'vna_start_freq': 10e6,
        'vna_stop_freq': 30e9,
        'vna_points': 101,
        'vna_param': 'S21',
    }

    pc = ParallelController(config)

    # 注入 Mock 仪器，跳过真实初始化
    pc._voltage_controller = MockZynqVoltageController(port='COM3', num_channels=4)
    pc._voltage_controller.initialize()
    pc._reference_measurement = MockReferenceMeasurement(num_points=100, num_channels=1)
    pc._vna = MockVNA(points=101)
    pc._vna.connect()
    pc._vna.setup_parameters()

    from concurrent.futures import ThreadPoolExecutor
    pc._executor = ThreadPoolExecutor(max_workers=2)
    pc._initialized = True

    yield pc

    # 清理
    if pc._executor:
        pc._executor.shutdown(wait=True)

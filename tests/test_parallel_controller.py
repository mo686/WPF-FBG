"""
ParallelController 单元测试 + 属性测试

覆盖任务 5 的核心并行测量逻辑：
- _run_optical_measurement
- _run_vna_measurement
- run_parallel_measurement
"""

import threading
import time

import pytest


# =========================================================================
# 5.1 _run_optical_measurement 测试
# =========================================================================

class TestRunOpticalMeasurement:
    """测试 _run_optical_measurement 方法"""

    def test_successful_measurement(self, mock_parallel_controller):
        """正常电压设置 + 光学测量应返回完整数据"""
        pc = mock_parallel_controller
        result = pc._run_optical_measurement([1.0, 2.0, 3.0, 4.0])

        assert 'wavelengths' in result
        assert 'il_data' in result
        assert 'reference_data_array' in result
        assert len(result['wavelengths']) == 100  # MockILSTS num_points
        assert len(result['il_data']) >= 1

    def test_voltage_applied_before_scan(self, mock_parallel_controller):
        """电压设置应在光学扫描之前执行"""
        pc = mock_parallel_controller
        pc._run_optical_measurement([1.0, 2.0, 3.0, 4.0])

        vc_log = pc._voltage_controller.call_log
        rm_log = pc._reference_measurement.call_log

        # 找到 set_voltages 和 measure_insertion_loss 的时间戳
        set_v_ts = [e[1] for e in vc_log if e[0] == 'set_voltages']
        measure_ts = [e[1] for e in rm_log if e[0] == 'measure_insertion_loss']

        assert len(set_v_ts) >= 1
        assert len(measure_ts) >= 1
        assert set_v_ts[-1] <= measure_ts[-1]

    def test_voltage_values_passed_correctly(self, mock_parallel_controller):
        """电压值应正确传递给控制器"""
        pc = mock_parallel_controller
        voltages = [0.5, 1.5, 2.5, 3.5]
        pc._run_optical_measurement(voltages)

        vc_log = pc._voltage_controller.call_log
        set_calls = [e for e in vc_log if e[0] == 'set_voltages']
        assert set_calls[-1][2] == voltages

    def test_voltage_failure_raises_error(self, mock_parallel_controller):
        """电压设置失败时应抛出 RuntimeError"""
        pc = mock_parallel_controller
        pc._voltage_controller.should_fail = True

        with pytest.raises(RuntimeError, match="电压设置失败"):
            pc._run_optical_measurement([1.0, 2.0, 3.0, 4.0])

    def test_voltage_failure_skips_scan(self, mock_parallel_controller):
        """电压设置失败时不应执行光学扫描"""
        pc = mock_parallel_controller
        pc._voltage_controller.should_fail = True

        try:
            pc._run_optical_measurement([1.0, 2.0, 3.0, 4.0])
        except RuntimeError:
            pass

        rm_log = pc._reference_measurement.call_log
        measure_calls = [e for e in rm_log if e[0] == 'measure_insertion_loss']
        assert len(measure_calls) == 0

    def test_optical_lock_is_held(self, mock_parallel_controller):
        """测量期间应持有 _optical_lock"""
        pc = mock_parallel_controller
        lock_held_during = []

        original_measure = pc._reference_measurement.measure_insertion_loss

        def patched_measure():
            lock_held_during.append(pc._optical_lock.locked())
            return original_measure()

        pc._reference_measurement.measure_insertion_loss = patched_measure
        pc._run_optical_measurement([1.0, 2.0, 3.0, 4.0])

        assert lock_held_during[0] is True


# =========================================================================
# 5.2 _run_vna_measurement 测试
# =========================================================================

class TestRunVnaMeasurement:
    """测试 _run_vna_measurement 方法"""

    def test_successful_measurement(self, mock_parallel_controller):
        """正常 VNA 测量应返回完整数据"""
        pc = mock_parallel_controller
        result = pc._run_vna_measurement()

        assert 'frequency' in result
        assert 's_param' in result
        assert 'magnitude_dB' in result
        assert 'phase_deg' in result
        assert len(result['frequency']) == 101  # MockVNA points

    def test_vna_failure_raises(self, mock_parallel_controller):
        """VNA 测量失败时应抛出异常"""
        pc = mock_parallel_controller
        pc._vna.should_fail = True

        with pytest.raises(RuntimeError, match="Mock VNA measurement failure"):
            pc._run_vna_measurement()

    def test_vna_lock_is_held(self, mock_parallel_controller):
        """测量期间应持有 _vna_lock"""
        pc = mock_parallel_controller
        lock_held_during = []

        original_measure = pc._vna.measure

        def patched_measure():
            lock_held_during.append(pc._vna_lock.locked())
            return original_measure()

        pc._vna.measure = patched_measure
        pc._run_vna_measurement()

        assert lock_held_during[0] is True


# =========================================================================
# 5.3 run_parallel_measurement 测试
# =========================================================================

class TestRunParallelMeasurement:
    """测试 run_parallel_measurement 方法"""

    def test_both_succeed(self, mock_parallel_controller):
        """光学和 VNA 均成功时，结果应完整"""
        pc = mock_parallel_controller
        result = pc.run_parallel_measurement([1.0, 2.0, 3.0, 4.0])

        from src.parallel_controller import TaskStatus
        assert result.optical_status == TaskStatus.COMPLETED
        assert result.vna_status == TaskStatus.COMPLETED
        assert result.optical_data is not None
        assert result.vna_data is not None
        assert result.optical_error is None
        assert result.vna_error is None

    def test_session_id_format(self, mock_parallel_controller):
        """session_id 应符合 YYYYMMDD_HHMMSS_xxx 格式"""
        import re
        pc = mock_parallel_controller
        result = pc.run_parallel_measurement([0.0, 0.0, 0.0, 0.0])

        pattern = r'^\d{8}_\d{6}_\d{3}$'
        assert re.match(pattern, result.session_id)

    def test_session_ids_unique(self, mock_parallel_controller):
        """连续两次测量的 session_id 应不同"""
        pc = mock_parallel_controller
        r1 = pc.run_parallel_measurement([0.0, 0.0, 0.0, 0.0])
        r2 = pc.run_parallel_measurement([0.0, 0.0, 0.0, 0.0])
        assert r1.session_id != r2.session_id

    def test_voltages_recorded(self, mock_parallel_controller):
        """voltages_applied 应记录传入的电压"""
        pc = mock_parallel_controller
        voltages = [1.1, 2.2, 3.3, 4.4]
        result = pc.run_parallel_measurement(voltages)
        assert result.voltages_applied == voltages

    def test_without_vna(self, mock_parallel_controller):
        """include_vna=False 时，VNA 状态应为 PENDING"""
        pc = mock_parallel_controller
        result = pc.run_parallel_measurement([1.0, 2.0, 3.0, 4.0], include_vna=False)

        from src.parallel_controller import TaskStatus
        assert result.optical_status == TaskStatus.COMPLETED
        assert result.vna_status == TaskStatus.PENDING
        assert result.vna_data is None

    def test_optical_failure_isolated(self, mock_parallel_controller):
        """光学失败不应影响 VNA 测量"""
        pc = mock_parallel_controller
        pc._reference_measurement.should_fail = True

        result = pc.run_parallel_measurement([1.0, 2.0, 3.0, 4.0])

        from src.parallel_controller import TaskStatus
        assert result.optical_status == TaskStatus.FAILED
        assert result.optical_error is not None
        assert result.vna_status == TaskStatus.COMPLETED
        assert result.vna_data is not None

    def test_vna_failure_isolated(self, mock_parallel_controller):
        """VNA 失败不应影响光学测量"""
        pc = mock_parallel_controller
        pc._vna.should_fail = True

        result = pc.run_parallel_measurement([1.0, 2.0, 3.0, 4.0])

        from src.parallel_controller import TaskStatus
        assert result.vna_status == TaskStatus.FAILED
        assert result.vna_error is not None
        assert result.optical_status == TaskStatus.COMPLETED
        assert result.optical_data is not None

    def test_voltage_failure_optical_fails_vna_ok(self, mock_parallel_controller):
        """电压设置失败时，光学应 FAILED，VNA 应不受影响"""
        pc = mock_parallel_controller
        pc._voltage_controller.should_fail = True

        result = pc.run_parallel_measurement([1.0, 2.0, 3.0, 4.0])

        from src.parallel_controller import TaskStatus
        assert result.optical_status == TaskStatus.FAILED
        assert "电压设置失败" in result.optical_error
        assert result.vna_status == TaskStatus.COMPLETED

    def test_result_appended_to_list(self, mock_parallel_controller):
        """每次测量结果应追加到 _results 列表"""
        pc = mock_parallel_controller
        assert len(pc._results) == 0

        pc.run_parallel_measurement([0.0, 0.0, 0.0, 0.0])
        assert len(pc._results) == 1

        pc.run_parallel_measurement([1.0, 1.0, 1.0, 1.0])
        assert len(pc._results) == 2

    def test_timing_recorded(self, mock_parallel_controller):
        """start_time 和 end_time 应被记录且 end >= start"""
        pc = mock_parallel_controller
        result = pc.run_parallel_measurement([0.0, 0.0, 0.0, 0.0])

        assert result.start_time > 0
        assert result.end_time >= result.start_time

    def test_not_initialized_raises(self):
        """未初始化时调用应抛出 RuntimeError"""
        from src.parallel_controller import ParallelController
        pc = ParallelController()

        with pytest.raises(RuntimeError, match="未初始化"):
            pc.run_parallel_measurement([0.0, 0.0, 0.0, 0.0])


# =========================================================================
# 7.1 run_voltage_sweep_parallel 测试
# =========================================================================

class TestRunVoltageSweepParallel:
    """测试 run_voltage_sweep_parallel 方法"""

    def test_correct_number_of_results(self, mock_parallel_controller):
        """扫描结果数量应等于电压序列长度"""
        pc = mock_parallel_controller
        results = pc.run_voltage_sweep_parallel(
            channel=1, start_voltage=0.0, end_voltage=1.0, step_voltage=0.5,
        )
        # 0.0, 0.5, 1.0 → 3 个点
        assert len(results) == 3

    def test_single_step(self, mock_parallel_controller):
        """start == end 时应返回 1 个结果"""
        pc = mock_parallel_controller
        results = pc.run_voltage_sweep_parallel(
            channel=1, start_voltage=2.0, end_voltage=2.0, step_voltage=0.1,
        )
        assert len(results) == 1

    def test_voltages_applied_correctly(self, mock_parallel_controller):
        """每个结果的 voltages_applied 应在指定通道上反映扫描电压"""
        pc = mock_parallel_controller
        results = pc.run_voltage_sweep_parallel(
            channel=2, start_voltage=0.0, end_voltage=1.0, step_voltage=0.5,
        )
        # channel=2 → index 1
        applied_ch2 = [r.voltages_applied[1] for r in results]
        assert applied_ch2 == pytest.approx([0.0, 0.5, 1.0])

    def test_other_channels_unchanged(self, mock_parallel_controller):
        """非扫描通道的电压应保持不变"""
        pc = mock_parallel_controller
        # 设置基准电压
        pc._voltage_controller.current_voltages = [1.0, 2.0, 3.0, 4.0]
        results = pc.run_voltage_sweep_parallel(
            channel=1, start_voltage=0.0, end_voltage=0.5, step_voltage=0.5,
        )
        for r in results:
            assert r.voltages_applied[1] == 2.0
            assert r.voltages_applied[2] == 3.0
            assert r.voltages_applied[3] == 4.0

    def test_all_succeed_with_vna(self, mock_parallel_controller):
        """所有点均成功时，光学和 VNA 状态均为 COMPLETED"""
        from src.parallel_controller import TaskStatus
        pc = mock_parallel_controller
        results = pc.run_voltage_sweep_parallel(
            channel=1, start_voltage=0.0, end_voltage=0.5, step_voltage=0.5,
        )
        for r in results:
            assert r.optical_status == TaskStatus.COMPLETED
            assert r.vna_status == TaskStatus.COMPLETED

    def test_without_vna(self, mock_parallel_controller):
        """include_vna=False 时，VNA 状态应为 PENDING"""
        from src.parallel_controller import TaskStatus
        pc = mock_parallel_controller
        results = pc.run_voltage_sweep_parallel(
            channel=1, start_voltage=0.0, end_voltage=0.5, step_voltage=0.5,
            include_vna=False,
        )
        for r in results:
            assert r.optical_status == TaskStatus.COMPLETED
            assert r.vna_status == TaskStatus.PENDING

    def test_vna_failure_cascades(self, mock_parallel_controller):
        """VNA 在某个点失败后，后续点的 VNA 应标记为 FAILED"""
        from src.parallel_controller import TaskStatus
        pc = mock_parallel_controller

        call_count = [0]
        original_measure = pc._vna.measure

        def fail_on_second():
            call_count[0] += 1
            if call_count[0] >= 2:
                raise RuntimeError("VNA communication lost")
            return original_measure()

        pc._vna.measure = fail_on_second

        results = pc.run_voltage_sweep_parallel(
            channel=1, start_voltage=0.0, end_voltage=1.0, step_voltage=0.5,
        )
        # 第1个点: VNA 成功
        assert results[0].vna_status == TaskStatus.COMPLETED
        # 第2个点: VNA 失败
        assert results[1].vna_status == TaskStatus.FAILED
        # 第3个点: VNA 应被级联标记为 FAILED（跳过）
        assert results[2].vna_status == TaskStatus.FAILED
        assert results[2].vna_error is not None

    def test_vna_cascade_does_not_affect_optical(self, mock_parallel_controller):
        """VNA 级联失败不应影响光学测量"""
        from src.parallel_controller import TaskStatus
        pc = mock_parallel_controller
        pc._vna.should_fail = True

        results = pc.run_voltage_sweep_parallel(
            channel=1, start_voltage=0.0, end_voltage=0.5, step_voltage=0.5,
        )
        for r in results:
            assert r.optical_status == TaskStatus.COMPLETED

    def test_not_initialized_raises(self):
        """未初始化时调用应抛出 RuntimeError"""
        from src.parallel_controller import ParallelController
        pc = ParallelController()
        with pytest.raises(RuntimeError, match="未初始化"):
            pc.run_voltage_sweep_parallel(
                channel=1, start_voltage=0.0, end_voltage=1.0, step_voltage=0.5,
            )

    def test_results_appended_to_internal_list(self, mock_parallel_controller):
        """扫描结果应追加到 _results 列表"""
        pc = mock_parallel_controller
        initial_count = len(pc._results)
        pc.run_voltage_sweep_parallel(
            channel=1, start_voltage=0.0, end_voltage=1.0, step_voltage=0.5,
        )
        assert len(pc._results) == initial_count + 3


# =========================================================================
# 7.2 create_optimization_objective 测试
# =========================================================================

class TestCreateOptimizationObjective:
    """测试 create_optimization_objective 方法"""

    def test_returns_callable(self, mock_parallel_controller):
        """应返回可调用对象"""
        pc = mock_parallel_controller
        obj = pc.create_optimization_objective(lambda data: 0.5)
        assert callable(obj)

    def test_successful_evaluation(self, mock_parallel_controller):
        """成功测量时应返回包含 fom 和 voltages 的字典"""
        pc = mock_parallel_controller
        obj = pc.create_optimization_objective(lambda data: 42.0)
        result = obj([1.0, 2.0, 3.0, 4.0])

        assert 'fom' in result
        assert 'voltages' in result
        assert result['fom'] == 42.0
        assert result['voltages'] == [1.0, 2.0, 3.0, 4.0]

    def test_optical_failure_returns_error_output(self, mock_parallel_controller):
        """光学测量失败时应返回错误输出"""
        pc = mock_parallel_controller
        pc._voltage_controller.should_fail = True

        obj = pc.create_optimization_objective(lambda data: 0.0)
        result = obj([1.0, 2.0, 3.0, 4.0])

        assert result == {'voltages': -1, 'fom': 1000.0}

    def test_objective_func_exception_returns_error_output(self, mock_parallel_controller):
        """目标函数抛出异常时应返回错误输出"""
        pc = mock_parallel_controller

        def bad_func(data):
            raise ValueError("bad computation")

        obj = pc.create_optimization_objective(bad_func)
        result = obj([1.0, 2.0, 3.0, 4.0])

        assert result == {'voltages': -1, 'fom': 1000.0}

    def test_include_vna_attaches_data(self, mock_parallel_controller):
        """include_vna=True 时，结果应包含 vna_data"""
        pc = mock_parallel_controller
        obj = pc.create_optimization_objective(lambda data: 1.0, include_vna=True)
        result = obj([1.0, 2.0, 3.0, 4.0])

        assert 'vna_data' in result
        assert result['vna_data'] is not None

    def test_no_vna_by_default(self, mock_parallel_controller):
        """默认不包含 vna_data"""
        pc = mock_parallel_controller
        obj = pc.create_optimization_objective(lambda data: 1.0)
        result = obj([1.0, 2.0, 3.0, 4.0])

        assert 'vna_data' not in result

    def test_vna_failure_still_returns_fom(self, mock_parallel_controller):
        """VNA 失败但光学成功时，仍应返回 fom（无 vna_data）"""
        pc = mock_parallel_controller
        pc._vna.should_fail = True

        obj = pc.create_optimization_objective(lambda data: 5.0, include_vna=True)
        result = obj([1.0, 2.0, 3.0, 4.0])

        assert result['fom'] == 5.0
        assert result['voltages'] == [1.0, 2.0, 3.0, 4.0]
        # vna_data should not be present since vna failed (result.vna_data is None)
        assert 'vna_data' not in result

    def test_compatible_with_base_function_manager_format(self, mock_parallel_controller):
        """返回格式应与 BaseFunctionManager._format_result_output() 兼容"""
        pc = mock_parallel_controller
        obj = pc.create_optimization_objective(lambda data: 3.14)
        result = obj([0.0, 0.0, 0.0, 0.0])

        # 必须包含这两个键
        assert 'fom' in result
        assert 'voltages' in result
        # fom 应为数值
        assert isinstance(result['fom'], (int, float))


# =========================================================================
# 9.1 emergency_stop 测试
# =========================================================================

class TestEmergencyStop:
    """测试 emergency_stop 方法"""

    def test_voltages_set_to_zero(self, mock_parallel_controller):
        """紧急停止后电压应置零"""
        pc = mock_parallel_controller
        pc._voltage_controller.set_voltages([5.0, 5.0, 5.0, 5.0])
        pc.emergency_stop()
        assert pc._voltage_controller.current_voltages == [0.0, 0.0, 0.0, 0.0]

    def test_executor_shutdown_called(self, mock_parallel_controller):
        """紧急停止应关闭线程池"""
        pc = mock_parallel_controller
        executor = pc._executor
        pc.emergency_stop()
        assert executor._shutdown

    def test_survives_voltage_controller_exception(self, mock_parallel_controller):
        """电压控制器异常时不应抛出"""
        pc = mock_parallel_controller

        def raise_on_set(v):
            raise RuntimeError("serial port error")

        pc._voltage_controller.set_voltages = raise_on_set
        # 不应抛出异常
        pc.emergency_stop()

    def test_survives_no_executor(self):
        """没有线程池时不应抛出"""
        from src.parallel_controller import ParallelController
        pc = ParallelController()
        pc.emergency_stop()

    def test_survives_no_voltage_controller(self):
        """没有电压控制器时不应抛出"""
        from src.parallel_controller import ParallelController
        pc = ParallelController()
        pc._voltage_controller = None
        pc.emergency_stop()


# =========================================================================
# 9.2 get_results / get_status 测试
# =========================================================================

class TestGetResults:
    """测试 get_results 方法"""

    def test_empty_initially(self, mock_parallel_controller):
        """初始时应返回空列表"""
        pc = mock_parallel_controller
        assert pc.get_results() == []

    def test_returns_copy(self, mock_parallel_controller):
        """应返回副本，修改不影响内部列表"""
        pc = mock_parallel_controller
        pc.run_parallel_measurement([0.0, 0.0, 0.0, 0.0])
        results = pc.get_results()
        results.clear()
        assert len(pc.get_results()) == 1

    def test_contains_all_results(self, mock_parallel_controller):
        """应包含所有已执行的测量结果"""
        pc = mock_parallel_controller
        pc.run_parallel_measurement([1.0, 1.0, 1.0, 1.0])
        pc.run_parallel_measurement([2.0, 2.0, 2.0, 2.0])
        assert len(pc.get_results()) == 2


class TestGetStatus:
    """测试 get_status 方法"""

    def test_initialized_flag(self, mock_parallel_controller):
        """应反映初始化状态"""
        pc = mock_parallel_controller
        status = pc.get_status()
        assert status['initialized'] is True

    def test_not_initialized(self):
        """未初始化时 initialized 应为 False"""
        from src.parallel_controller import ParallelController
        pc = ParallelController()
        status = pc.get_status()
        assert status['initialized'] is False

    def test_measurement_count(self, mock_parallel_controller):
        """measurement_count 应反映已执行的测量次数"""
        pc = mock_parallel_controller
        assert pc.get_status()['measurement_count'] == 0
        pc.run_parallel_measurement([0.0, 0.0, 0.0, 0.0])
        assert pc.get_status()['measurement_count'] == 1

    def test_voltage_controller_status(self, mock_parallel_controller):
        """应包含电压控制器状态"""
        pc = mock_parallel_controller
        status = pc.get_status()
        assert 'voltage_controller' in status
        assert 'connected' in status['voltage_controller']
        assert 'current_voltages' in status['voltage_controller']

    def test_vna_status(self, mock_parallel_controller):
        """应包含 VNA 状态"""
        pc = mock_parallel_controller
        status = pc.get_status()
        assert 'vna' in status
        assert 'connected' in status['vna']

    def test_optical_system_status(self, mock_parallel_controller):
        """应包含光学系统状态"""
        pc = mock_parallel_controller
        status = pc.get_status()
        assert 'optical_system' in status
        assert 'connected' in status['optical_system']

    def test_no_instruments_status(self):
        """无仪器时应返回 disconnected 状态"""
        from src.parallel_controller import ParallelController
        pc = ParallelController()
        status = pc.get_status()
        assert status['voltage_controller']['connected'] is False
        assert status['vna']['connected'] is False
        assert status['optical_system']['connected'] is False


# =========================================================================
# 9.3 export_results_csv 测试
# =========================================================================

class TestExportResultsCsv:
    """测试 export_results_csv 方法"""

    def test_creates_csv_file(self, mock_parallel_controller, tmp_path):
        """应创建 CSV 文件"""
        pc = mock_parallel_controller
        pc.run_parallel_measurement([1.0, 2.0, 3.0, 4.0])
        filepath = str(tmp_path / "results.csv")
        pc.export_results_csv(filepath)

        import os
        assert os.path.exists(filepath)

    def test_csv_header(self, mock_parallel_controller, tmp_path):
        """CSV 应包含正确的表头"""
        pc = mock_parallel_controller
        filepath = str(tmp_path / "results.csv")
        pc.export_results_csv(filepath)

        import csv
        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            header = next(reader)
        assert 'session_id' in header
        assert 'voltages_applied' in header
        assert 'optical_status' in header
        assert 'vna_status' in header

    def test_csv_row_count(self, mock_parallel_controller, tmp_path):
        """CSV 行数应等于测量次数 + 1（表头）"""
        pc = mock_parallel_controller
        pc.run_parallel_measurement([1.0, 1.0, 1.0, 1.0])
        pc.run_parallel_measurement([2.0, 2.0, 2.0, 2.0])
        filepath = str(tmp_path / "results.csv")
        pc.export_results_csv(filepath)

        import csv
        with open(filepath, 'r', encoding='utf-8') as f:
            rows = list(csv.reader(f))
        assert len(rows) == 3  # 1 header + 2 data rows

    def test_session_id_roundtrip(self, mock_parallel_controller, tmp_path):
        """导出后重新读取应能恢复 session_id"""
        pc = mock_parallel_controller
        result = pc.run_parallel_measurement([1.0, 2.0, 3.0, 4.0])
        filepath = str(tmp_path / "results.csv")
        pc.export_results_csv(filepath)

        import csv
        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            row = next(reader)
        assert row['session_id'] == result.session_id

    def test_status_roundtrip(self, mock_parallel_controller, tmp_path):
        """导出后重新读取应能恢复状态值"""
        pc = mock_parallel_controller
        pc.run_parallel_measurement([1.0, 2.0, 3.0, 4.0])
        filepath = str(tmp_path / "results.csv")
        pc.export_results_csv(filepath)

        import csv
        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            row = next(reader)
        assert row['optical_status'] == 'completed'
        assert row['vna_status'] == 'completed'

    def test_optical_data_summary(self, mock_parallel_controller, tmp_path):
        """光学数据摘要应包含波长范围"""
        pc = mock_parallel_controller
        pc.run_parallel_measurement([1.0, 2.0, 3.0, 4.0])
        filepath = str(tmp_path / "results.csv")
        pc.export_results_csv(filepath)

        import csv
        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            row = next(reader)
        assert row['optical_wavelength_range'] != ''
        assert row['optical_il_channels'] != ''

    def test_empty_results(self, mock_parallel_controller, tmp_path):
        """无结果时应只写表头"""
        pc = mock_parallel_controller
        filepath = str(tmp_path / "results.csv")
        pc.export_results_csv(filepath)

        import csv
        with open(filepath, 'r', encoding='utf-8') as f:
            rows = list(csv.reader(f))
        assert len(rows) == 1  # header only


# =========================================================================
# 9.4 shutdown 测试
# =========================================================================

class TestShutdown:
    """测试 shutdown 方法"""

    def test_voltages_zeroed(self, mock_parallel_controller):
        """关闭后电压应置零"""
        pc = mock_parallel_controller
        pc._voltage_controller.set_voltages([5.0, 5.0, 5.0, 5.0])
        pc.shutdown()
        # 检查 set_voltages 最后一次调用是置零
        vc_log = pc._voltage_controller.call_log
        set_calls = [e for e in vc_log if e[0] == 'set_voltages']
        assert set_calls[-1][2] == [0.0, 0.0, 0.0, 0.0]

    def test_vna_closed(self, mock_parallel_controller):
        """关闭后 VNA 应断开连接"""
        pc = mock_parallel_controller
        pc.shutdown()
        close_calls = [e for e in pc._vna.call_log if e[0] == 'close']
        assert len(close_calls) >= 1

    def test_voltage_controller_closed(self, mock_parallel_controller):
        """关闭后电压控制器应关闭"""
        pc = mock_parallel_controller
        pc.shutdown()
        close_calls = [e for e in pc._voltage_controller.call_log if e[0] == 'close']
        assert len(close_calls) >= 1

    def test_initialized_set_to_false(self, mock_parallel_controller):
        """关闭后 _initialized 应为 False"""
        pc = mock_parallel_controller
        assert pc._initialized is True
        pc.shutdown()
        assert pc._initialized is False

    def test_survives_vna_close_exception(self, mock_parallel_controller):
        """VNA 关闭异常时不应抛出"""
        pc = mock_parallel_controller

        def raise_on_close():
            raise RuntimeError("GPIB error")

        pc._vna.close = raise_on_close
        pc.shutdown()  # 不应抛出

    def test_survives_no_instruments(self):
        """无仪器时不应抛出"""
        from src.parallel_controller import ParallelController
        pc = ParallelController()
        pc.shutdown()  # 不应抛出

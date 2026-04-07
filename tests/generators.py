"""
Hypothesis 自定义生成器，用于 ParallelController 属性测试。
"""

from hypothesis import strategies as st


# ---------------------------------------------------------------------------
# 电压列表生成器：4 元素，每个值 0.0 ~ 10.0
# ---------------------------------------------------------------------------

voltage_lists = st.lists(
    st.floats(min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False),
    min_size=4,
    max_size=4,
)


# ---------------------------------------------------------------------------
# 配置字典生成器
# ---------------------------------------------------------------------------

config_dicts = st.fixed_dictionaries({
    'voltage_settle_time': st.floats(min_value=0.0, max_value=2.0,
                                     allow_nan=False, allow_infinity=False),
    'max_workers': st.integers(min_value=1, max_value=4),
    'output_dir': st.just('./test_parallel_results'),
    'vna_gpib_address': st.integers(min_value=1, max_value=30),
    'vna_start_freq': st.floats(min_value=1e6, max_value=1e9,
                                allow_nan=False, allow_infinity=False),
    'vna_stop_freq': st.floats(min_value=1e9, max_value=50e9,
                               allow_nan=False, allow_infinity=False),
    'vna_points': st.integers(min_value=11, max_value=6001),
    'vna_param': st.sampled_from(['S11', 'S21', 'S12', 'S22']),
    'voltage_port': st.just('COM3'),
    'voltage_num_channels': st.just(4),
})


# ---------------------------------------------------------------------------
# ParallelResult 生成器
# ---------------------------------------------------------------------------

def _task_status_strategy():
    """生成 TaskStatus 枚举值（延迟导入，因为 ParallelController 尚未实现）"""
    from src.parallel_controller import TaskStatus
    return st.sampled_from(list(TaskStatus))


def parallel_results():
    """生成包含各种状态组合的 ParallelResult 对象"""
    from src.parallel_controller import ParallelResult, TaskStatus

    return st.builds(
        ParallelResult,
        session_id=st.from_regex(r'[0-9]{8}_[0-9]{6}_[0-9]{3}', fullmatch=True),
        optical_data=st.one_of(st.none(), st.just({
            'wavelengths': [1500.0, 1550.0, 1600.0],
            'il_data': [[-10.0, -12.0, -11.0]],
        })),
        vna_data=st.one_of(st.none(), st.just({
            'frequency': [1e6, 15e9, 30e9],
            's_param': [0.1 + 0.2j, 0.3 + 0.4j, 0.5 + 0.6j],
            'magnitude_dB': [-20.0, -10.0, -6.0],
            'phase_deg': [45.0, 90.0, 135.0],
        })),
        voltages_applied=st.one_of(st.none(), voltage_lists),
        optical_status=_task_status_strategy(),
        vna_status=_task_status_strategy(),
        optical_error=st.one_of(st.none(), st.text(min_size=1, max_size=50)),
        vna_error=st.one_of(st.none(), st.text(min_size=1, max_size=50)),
        start_time=st.floats(min_value=0.0, max_value=1e12,
                             allow_nan=False, allow_infinity=False),
        end_time=st.floats(min_value=0.0, max_value=1e12,
                           allow_nan=False, allow_infinity=False),
    )


# ---------------------------------------------------------------------------
# 故障注入生成器
# ---------------------------------------------------------------------------

FAULT_TARGETS = ('vna', 'optical', 'both', 'none')

fault_injection = st.sampled_from(FAULT_TARGETS)

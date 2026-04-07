# 实施计划：并行仪器控制系统

## 概述

基于设计文档，实现一个轻量级的 `ParallelController` 协调层，使用 `ThreadPoolExecutor` 实现 VNA 矢网仪测量与光学插损测量的并行执行。所有代码集中在 `src/parallel_controller.py`，测试代码在 `tests/` 目录下。

## 任务

- [x] 1. 创建测试基础设施和 Mock 对象
  - [x] 1.1 创建 `tests/conftest.py`，定义共享 fixtures 和 Mock 类
    - 实现 `MockZynqVoltageController`：模拟 `set_voltages()` 返回 True/False，记录调用参数，提供 `current_voltages`、`initialize()`、`close()` 方法
    - 实现 `MockReferenceMeasurement`：模拟 `measure_insertion_loss()` 生成随机波长/插损数据，提供 `ilsts` 属性（含 `wavelength_table`、`il_data_array`、`reference_data_array`）
    - 实现 `MockVNA`：模拟 `connect()`、`setup_parameters()`、`measure()` 生成随机频率/S参数数据、`close()` 方法
    - 提供 `mock_parallel_controller` fixture，使用 Mock 对象创建已初始化的 ParallelController 实例
    - _需求: 1.1, 1.2, 4.1_

  - [x] 1.2 创建 `tests/generators.py`，定义 hypothesis 自定义生成器
    - 实现电压列表生成器：生成4元素列表，每个值在 0.0-10.0 范围内
    - 实现配置字典生成器：生成包含有效参数范围的配置字典
    - 实现 ParallelResult 生成器：生成包含各种状态组合的结果对象
    - 实现故障注入生成器：随机选择 VNA 或光学系统注入异常
    - _需求: 1.1, 8.1_

- [x] 2. 实现数据模型和核心类骨架
  - [x] 2.1 创建 `src/parallel_controller.py`，实现 `TaskStatus` 枚举和 `ParallelResult` 数据类
    - `TaskStatus` 枚举：PENDING、RUNNING、COMPLETED、FAILED
    - `ParallelResult` 数据类：session_id、optical_data、vna_data、voltages_applied、optical_status、vna_status、optical_error、vna_error、start_time、end_time
    - _需求: 2.6, 6.1_

  - [x] 2.2 实现 `ParallelController.__init__(config)` 方法
    - 解析配置字典，设置默认值（voltage_settle_time=0.5, max_workers=2, output_dir='./parallel_results'）
    - 初始化三个 `threading.Lock` 实例：`_optical_lock`、`_vna_lock`、`_result_lock`
    - 初始化仪器引用为 None、`_initialized` 为 False、`_results` 为空列表
    - 配置 `logging.Logger`
    - _需求: 8.1, 8.2, 3.3_

  - [ ]* 2.3 编写属性测试：配置加载正确性（属性 15）
    - **属性 15：配置加载正确性**
    - **验证需求: 8.1, 3.3**

- [x] 3. 实现仪器初始化
  - [x] 3.1 实现 `ParallelController.initialize()` 方法
    - 初始化 `ZynqVoltageController`（使用配置中的 port 和 num_channels）
    - 初始化 `ReferenceMeasurement`（调用 `initialize_optical_devices()` 和 `configure_reference_parameters()`）
    - 初始化 `VNA`（使用配置中的 GPIB 地址、频率范围、扫描点数等参数，调用 `connect()` 和 `setup_parameters()`）
    - 创建 `ThreadPoolExecutor(max_workers=self._max_workers)`
    - 设置 `_initialized = True`
    - 任一仪器初始化失败时记录日志并返回 False
    - _需求: 1.1, 1.5, 8.4_

  - [ ]* 3.2 编写属性测试：仪器初始化完整性（属性 1）
    - **属性 1：仪器初始化完整性**
    - **验证需求: 1.1**

- [x] 4. 检查点 - 确保所有测试通过
  - 确保所有测试通过，如有问题请询问用户。

- [x] 5. 实现核心并行测量逻辑
  - [x] 5.1 实现 `ParallelController._run_optical_measurement(voltages)` 方法
    - 获取 `_optical_lock`
    - 调用 `_voltage_controller.set_voltages(voltages)`，失败时返回错误信息
    - `time.sleep(self._voltage_settle_time)` 等待电压稳定
    - 调用 `_reference_measurement.measure_insertion_loss()`
    - 提取 `wavelength_table` 和 `il_data_array` / `reference_data_array`
    - 释放 `_optical_lock`
    - _需求: 3.2, 3.3, 3.4_

  - [x] 5.2 实现 `ParallelController._run_vna_measurement()` 方法
    - 获取 `_vna_lock`
    - 调用 `_vna.measure()`
    - 返回包含 frequency、s_param、magnitude_dB、phase_deg 的字典
    - 释放 `_vna_lock`
    - _需求: 4.1_

  - [x] 5.3 实现 `ParallelController.run_parallel_measurement(voltages, include_vna)` 方法
    - 生成唯一 session_id（格式 YYYYMMDD_HHMMSS_xxx）
    - 使用 `_executor.submit()` 提交光学测量任务
    - 如果 `include_vna=True`，同时提交 VNA 测量任务
    - 使用 `as_completed()` 或 `future.result()` 收集结果
    - 捕获各任务异常，记录到 ParallelResult 的 error 字段
    - 使用 `_result_lock` 保护结果列表的写入
    - 组装并返回 `ParallelResult`
    - _需求: 2.2, 4.2, 4.4, 7.1_

  - [ ]* 5.4 编写属性测试：电压先于扫描执行（属性 4）
    - **属性 4：电压先于扫描执行**
    - **验证需求: 3.2, 3.3**

  - [ ]* 5.5 编写属性测试：仪器互斥访问（属性 2）
    - **属性 2：仪器互斥访问**
    - **验证需求: 1.2, 1.3, 2.3**

  - [ ]* 5.6 编写属性测试：成功任务的结果完整性（属性 8）
    - **属性 8：成功任务的结果完整性**
    - **验证需求: 2.5, 4.3**

  - [ ]* 5.7 编写属性测试：独立仪器故障隔离（属性 9）
    - **属性 9：独立仪器故障隔离**
    - **验证需求: 4.4, 7.1**

  - [ ]* 5.8 编写属性测试：电压失败级联跳过（属性 5）
    - **属性 5：电压失败级联跳过**
    - **验证需求: 3.4, 1.4**

  - [ ]* 5.9 编写属性测试：会话标识唯一性（属性 12）
    - **属性 12：会话标识唯一性**
    - **验证需求: 6.1, 6.2**

- [x] 6. 检查点 - 确保所有测试通过
  - 确保所有测试通过，如有问题请询问用户。

- [x] 7. 实现批量扫描和优化接口
  - [x] 7.1 实现 `ParallelController.run_voltage_sweep_parallel(channel, start, end, step, include_vna)` 方法
    - 根据 start、end、step 计算电压序列
    - 对每个电压点调用 `run_parallel_measurement()`
    - 收集所有 ParallelResult 到列表
    - 如果 VNA 在某个点变为不可用，后续点标记 VNA 为 FAILED
    - _需求: 3.5, 7.5_

  - [x] 7.2 实现 `ParallelController.create_optimization_objective(optical_func, include_vna)` 方法
    - 返回闭包函数，签名为 `(voltages) -> dict`
    - 闭包内部调用 `run_parallel_measurement()`
    - 使用 `optical_func` 处理光学数据计算 FOM
    - 返回包含 `'fom'` 和 `'voltages'` 键的字典
    - 测量失败时返回 `{'voltages': -1, 'fom': 1000.0}`
    - 如果 `include_vna=True`，额外附加 `'vna_data'` 键
    - _需求: 5.1, 5.2, 5.3, 5.4_

  - [ ]* 7.3 编写属性测试：批量扫描结果数量一致（属性 6）
    - **属性 6：批量扫描结果数量一致**
    - **验证需求: 3.5**

  - [ ]* 7.4 编写属性测试：VNA 与光学测量并行执行（属性 7）
    - **属性 7：VNA 与光学测量并行执行**
    - **验证需求: 4.1**

  - [ ]* 7.5 编写属性测试：优化接口兼容性（属性 10）
    - **属性 10：优化接口兼容性**
    - **验证需求: 5.1**

  - [ ]* 7.6 编写属性测试：错误输出一致性（属性 11）
    - **属性 11：错误输出一致性**
    - **验证需求: 5.4**

  - [ ]* 7.7 编写属性测试：扫描中仪器故障级联（属性 16）
    - **属性 16：扫描中仪器故障级联**
    - **验证需求: 7.5**

- [x] 8. 检查点 - 确保所有测试通过
  - 确保所有测试通过，如有问题请询问用户。

- [x] 9. 实现辅助功能和系统管理
  - [x] 9.1 实现 `ParallelController.emergency_stop()` 方法
    - 调用 `_executor.shutdown(wait=False, cancel_futures=True)` 停止线程池
    - 调用 `_voltage_controller.set_voltages([0.0, 0.0, 0.0, 0.0])` 电压置零
    - 异常时尽力而为（try/except pass）
    - _需求: 7.2, 7.3_

  - [x] 9.2 实现 `ParallelController.get_results()` 和 `ParallelController.get_status()` 方法
    - `get_results()` 返回 `_results` 列表的副本
    - `get_status()` 返回包含各仪器连接状态、当前电压、测量计数的字典
    - _需求: 1.6, 2.6, 6.4_

  - [x] 9.3 实现 `ParallelController.export_results_csv(filepath)` 方法
    - 将所有 ParallelResult 导出为 CSV 格式
    - 包含 session_id、voltages_applied、optical_status、vna_status、optical_error、vna_error
    - 如果有光学数据，包含波长和插损摘要
    - 如果有 VNA 数据，包含频率范围和 S 参数摘要
    - _需求: 6.3_

  - [x] 9.4 实现 `ParallelController.shutdown()` 方法
    - 电压置零
    - 关闭 VNA 连接（`_vna.close()`）
    - 关闭电压控制器串口（`_voltage_controller.close()`）
    - 关闭 ThreadPoolExecutor
    - 重置 TSL/MPM（`_reference_measurement.tsl.query("*RST")`）
    - _需求: 7.2_

  - [ ]* 9.5 编写属性测试：状态查询一致性（属性 3）
    - **属性 3：状态查询一致性**
    - **验证需求: 1.6, 2.6**

  - [ ]* 9.6 编写属性测试：CSV 导出往返一致性（属性 13）
    - **属性 13：CSV 导出往返一致性**
    - **验证需求: 6.3**

  - [ ]* 9.7 编写属性测试：测量数据自动持久化（属性 14）
    - **属性 14：测量数据自动持久化**
    - **验证需求: 5.5, 6.5**

- [x] 10. 最终检查点 - 确保所有测试通过
  - 确保所有测试通过，如有问题请询问用户。

## 备注

- 标记 `*` 的任务为可选任务，可跳过以加速 MVP 开发
- 每个任务引用了具体的需求编号以确保可追溯性
- 检查点确保增量验证
- 属性测试验证设计文档中的16个正确性属性
- 单元测试验证具体场景和边界条件

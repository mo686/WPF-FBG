# 需求文档：并行仪器控制系统

## 简介

本系统将现有的激光器控制（Santec STS）、电压通道控制（NI-DAQmx / Zynq FPGA）、损耗谱绘制、矢量网络分析仪（思仪3671G）控制及S21参数提取功能整合为一个并行控制系统。系统能够同时协调多台仪器的操作，支持并行测量、同步数据采集和协调优化流程，从而提高光子器件表征的效率和自动化程度。

## 术语表

- **Parallel_Controller**: 并行控制系统的核心协调器，负责管理和调度所有仪器的并行操作
- **Task_Scheduler**: 任务调度器，负责将测量任务分配到各仪器并管理执行顺序和依赖关系
- **Instrument_Pool**: 仪器资源池，管理所有已连接仪器的生命周期和访问权限
- **STS_Module**: 激光器扫描测量模块，封装StsProcess、TslInstrument、MpmInstrument和SpuDevice
- **Voltage_Module**: 电压控制模块，封装VoltageController（NI-DAQmx）和ZynqVoltageController（FPGA）
- **VNA_Module**: 矢量网络分析仪模块，封装VNA类的S参数测量功能
- **Spectrum_Module**: 光谱分析模块，封装SpectralFunctions和SpectrumAnalyzer的光谱处理功能
- **Measurement_Task**: 测量任务，描述一次完整的仪器操作（包含仪器类型、参数、依赖关系）
- **Task_Group**: 任务组，一组可并行执行的测量任务集合
- **Execution_Context**: 执行上下文，包含任务执行所需的共享状态和数据
- **Result_Aggregator**: 结果聚合器，收集并合并来自多个并行任务的测量结果
- **Instrument_Lock**: 仪器锁，确保同一物理仪器在同一时刻只被一个任务访问

## 需求

### 需求 1：仪器资源池管理

**用户故事：** 作为实验人员，我希望系统能统一管理所有已连接的仪器资源，以便在并行操作中安全地共享和调度仪器。

#### 验收标准

1. THE Instrument_Pool SHALL 维护所有已注册仪器实例的引用，包括STS_Module、Voltage_Module、VNA_Module和Spectrum_Module
2. WHEN 一个Measurement_Task请求访问某仪器时，THE Instrument_Pool SHALL 通过Instrument_Lock机制确保该仪器在同一时刻仅被一个任务独占访问
3. WHEN 一个仪器被某任务占用且另一任务请求该仪器时，THE Task_Scheduler SHALL 将请求任务置于等待队列，直到仪器释放
4. IF 仪器连接在任务执行过程中断开，THEN THE Instrument_Pool SHALL 将该仪器标记为不可用，并通知所有依赖该仪器的等待任务
5. WHEN 系统启动时，THE Instrument_Pool SHALL 自动检测并注册所有可用的仪器设备
6. THE Instrument_Pool SHALL 提供查询接口，返回每台仪器的当前状态（空闲、占用、不可用）

### 需求 2：并行任务调度

**用户故事：** 作为实验人员，我希望系统能够同时执行多个不冲突的测量任务，以缩短整体实验时间。

#### 验收标准

1. THE Task_Scheduler SHALL 接受一组Measurement_Task，分析任务间的仪器依赖关系，并将无冲突的任务分组为可并行执行的Task_Group
2. WHEN 一个Task_Group中的所有任务使用不同的物理仪器时，THE Parallel_Controller SHALL 同时启动这些任务的执行
3. WHEN 一个Task_Group中存在使用相同仪器的任务时，THE Task_Scheduler SHALL 将这些任务串行排列，同时允许使用不同仪器的任务并行执行
4. THE Task_Scheduler SHALL 支持任务优先级设定，高优先级任务优先获得仪器资源
5. WHEN 所有Task_Group中的任务执行完毕后，THE Result_Aggregator SHALL 收集所有任务的结果并以统一格式返回
6. THE Parallel_Controller SHALL 提供实时的任务执行状态查询接口，返回每个任务的状态（等待、执行中、已完成、失败）

### 需求 3：激光器扫描与电压控制并行协调

**用户故事：** 作为实验人员，我希望在激光器扫描测量的同时能够控制电压通道，以实现电压-光谱联合表征。

#### 验收标准

1. THE Parallel_Controller SHALL 支持在STS_Module执行光谱扫描的同时，通过Voltage_Module设置电压通道输出
2. WHEN 用户提交一个包含电压设置和光谱扫描的联合任务时，THE Task_Scheduler SHALL 先执行电压设置，等待电压稳定后再触发光谱扫描
3. THE Parallel_Controller SHALL 支持配置电压稳定等待时间，默认值为0.5秒
4. WHEN 电压设置失败时，THE Parallel_Controller SHALL 跳过对应的光谱扫描任务，并在结果中记录失败原因
5. THE Parallel_Controller SHALL 支持批量电压-光谱扫描序列，按用户指定的电压列表依次设置电压并执行扫描，每次扫描结果独立存储

### 需求 4：矢网仪与光学测量并行执行

**用户故事：** 作为实验人员，我希望在执行光学插损测量的同时能够进行矢网仪S参数测量，以同步获取光学和射频特性数据。

#### 验收标准

1. THE Parallel_Controller SHALL 支持VNA_Module与STS_Module的完全并行执行，因为两者使用独立的物理仪器
2. WHEN 用户提交同时包含VNA测量和光谱扫描的任务组时，THE Parallel_Controller SHALL 同时启动两项测量
3. WHEN VNA_Module和STS_Module的并行测量均完成后，THE Result_Aggregator SHALL 将两者的结果合并为一个统一的数据结构，包含频率-S参数数据和波长-插损数据
4. IF VNA_Module或STS_Module中任一测量失败，THEN THE Parallel_Controller SHALL 继续执行另一项测量，并在最终结果中标记失败项

### 需求 5：并行优化流程支持

**用户故事：** 作为实验人员，我希望优化算法能够利用并行控制系统加速目标函数评估，以缩短优化收敛时间。

#### 验收标准

1. THE Parallel_Controller SHALL 提供与现有OptimizationAdapter兼容的目标函数接口，使PSO和Bayesian优化器能够透明地使用并行测量能力
2. WHEN 优化器请求评估一组电压参数时，THE Parallel_Controller SHALL 协调Voltage_Module设置电压、STS_Module执行扫描、Spectrum_Module分析光谱的完整流程
3. THE Parallel_Controller SHALL 支持在优化过程中同时执行VNA测量，将S参数数据作为附加优化指标
4. WHEN 优化过程中某次测量失败时，THE Parallel_Controller SHALL 返回预定义的错误输出值（fom=1000.0），与现有BaseFunctionManager的错误处理行为一致
5. THE Parallel_Controller SHALL 记录每次优化评估的完整测量数据（电压、光谱、S参数），供后续分析使用

### 需求 6：测量结果聚合与数据管理

**用户故事：** 作为实验人员，我希望并行测量的所有结果能够被统一收集、关联和存储，以便后续分析和可视化。

#### 验收标准

1. THE Result_Aggregator SHALL 为每次并行测量会话生成唯一的时间戳标识符
2. THE Result_Aggregator SHALL 将来自不同仪器的测量结果按时间戳和任务标识进行关联
3. THE Result_Aggregator SHALL 支持将聚合结果导出为CSV格式，包含所有仪器的测量数据
4. WHEN 并行测量完成后，THE Result_Aggregator SHALL 提供统一的数据访问接口，允许按仪器类型、时间范围或任务标识查询结果
5. THE Result_Aggregator SHALL 在每次测量完成后自动保存原始数据到指定目录，防止数据丢失

### 需求 7：错误处理与系统恢复

**用户故事：** 作为实验人员，我希望系统在并行操作中遇到错误时能够安全地处理异常，保护仪器设备并保留已完成的测量数据。

#### 验收标准

1. IF 任一并行任务抛出异常，THEN THE Parallel_Controller SHALL 捕获该异常，记录错误信息，并继续执行其他不受影响的任务
2. IF 系统检测到严重错误（如仪器通信完全中断），THEN THE Parallel_Controller SHALL 安全地停止所有正在执行的任务，并将所有电压通道置零
3. WHEN 系统执行紧急停止时，THE Voltage_Module SHALL 在500毫秒内将所有电压输出通道设置为0V
4. THE Parallel_Controller SHALL 在每次任务执行前后记录仪器状态日志，包含时间戳、仪器标识和操作结果
5. IF 某仪器在任务执行中变为不可用，THEN THE Parallel_Controller SHALL 将依赖该仪器的后续任务标记为跳过，并在结果中说明原因

### 需求 8：系统配置与初始化

**用户故事：** 作为实验人员，我希望能够通过配置文件或交互界面灵活配置并行控制系统的参数，以适应不同的实验需求。

#### 验收标准

1. THE Parallel_Controller SHALL 支持通过JSON配置文件指定参与并行控制的仪器列表及其连接参数
2. THE Parallel_Controller SHALL 支持配置最大并行任务数，默认值等于已连接的独立仪器数量
3. WHEN 配置文件不存在时，THE Parallel_Controller SHALL 进入交互模式，引导用户逐步配置各仪器参数
4. THE Parallel_Controller SHALL 兼容现有的DeviceManager和ConfigManager配置体系，复用已有的仪器初始化逻辑
5. WHEN 系统初始化完成后，THE Parallel_Controller SHALL 输出所有已连接仪器的状态摘要，包括仪器类型、连接状态和可用通道信息

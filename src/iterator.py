import numpy as np
import matplotlib.pyplot as plt
import time
import csv
import pickle
import os
from datetime import datetime
from scipy import signal

plt.rcParams['font.family'] = ['SimHei']  # 使用黑体
plt.rcParams['axes.unicode_minus'] = False  # 正确显示负号

class Iterator:
    """
    电压扫描器类，用于对多个通道的电压进行遍历扫描，并测量光学性能
    """
    
    def __init__(self, ilsts, voltage_controller, objective_func, bounds, steps_per_dimension, 
                 run_id=1, active_channels=None, total_channels=None):
        """
        初始化电压扫描器
        
        参数:
            ilsts: STS过程对象，用于进行光学测量
            voltage_controller: 电压控制器对象
            objective_func: 目标函数
            bounds: 边界列表，每个元素是一个元组 (min, max)
                    例如: [(0.0, 2.0), (0.0, 3.0)] 表示两个通道的电压范围
            steps_per_dimension: 每个维度的步数列表
                    例如: [5, 10] 表示第一个通道5步，第二个通道10步
            run_id: 运行ID，用于创建结果目录
            active_channels: 实际需要优化的通道索引列表（0-based）
            total_channels: 总通道数
        """
        self.ilsts = ilsts
        self.voltage_controller = voltage_controller
        self.objective_func = objective_func
        self.bounds = bounds
        self.steps_per_dimension = steps_per_dimension
        self.dimensions = len(bounds)
        self.run_id = run_id
        self.active_channels = active_channels or list(range(len(bounds)))
        self.total_channels = total_channels or len(self.active_channels)
        
         # 验证参数
        if len(self.active_channels) != len(bounds):
            raise ValueError("active_channels的长度必须与bounds一致")
        print(f"🎯 初始化遍历扫描器 (运行{run_id})")
        print(f"   激活通道: {[ch+1 for ch in self.active_channels]}")
        print(f"   总通道数: {self.total_channels}")
        self._validate_parameters()
        
        # 初始化结果存储
        self.scan_results = []
        self.best_result = {}
        self.scan_history = []
        
        # 创建结果目录
        self.run_dir = f"./iterator_scan_runs/run_{run_id}"
        os.makedirs(self.run_dir, exist_ok=True)
        
        # 生成通道配置（向后兼容）
        self.channel_configs = []
        for i, (bound, steps) in enumerate(zip(bounds, steps_per_dimension)):
            self.channel_configs.append({
                'channel': i,
                'start': bound[0],
                'stop': bound[1],
                'steps': steps
            })
        
        # 计算总扫描点数
        self.total_points = 1
        for steps in steps_per_dimension:
            self.total_points *= steps
        
        print(f"🎯 初始化遍历扫描器 (运行{run_id})")
        print(f"   通道数量: {self.dimensions}")
        print(f"   总扫描点数: {self.total_points}")
        print(f"   结果目录: {self.run_dir}")
        
        # 显示边界信息
        print("   通道配置详情:")
        for i, (bound, steps) in enumerate(zip(bounds, steps_per_dimension)):
            print(f"     通道 {i}: {bound[0]:.3f}V ~ {bound[1]:.3f}V, {steps}步")
    
    def _validate_parameters(self):
        """验证初始化参数"""
        if len(self.bounds) != len(self.steps_per_dimension):
            raise ValueError("bounds和steps_per_dimension的长度必须一致")
        
        for i, (bound, steps) in enumerate(zip(self.bounds, self.steps_per_dimension)):
            if bound[0] > bound[1]:
                raise ValueError(f"通道 {i} 的边界范围无效: [{bound[0]}, {bound[1]}]")
            if steps < 1:
                raise ValueError(f"通道 {i} 的步数必须大于0: {steps}")
    
    def _map_voltages_to_actual(self, scan_voltages):
        """
        将扫描电压映射到实际的电压向量
        """
        # 创建全零电压向量
        voltages = [0.0] * self.total_channels
        
        # 将扫描电压设置到激活的通道
        for i, channel_index in enumerate(self.active_channels):
            if channel_index < self.total_channels:
                voltages[channel_index] = scan_voltages[i]
        
        return voltages
    
    def configure_scan(self):
        """
        配置电压扫描参数（兼容性方法，参数已在初始化时设置）
        返回:
            bool: 配置成功返回True
        """
        print(f"扫描配置已就绪:")
        print(f"  通道数量: {self.dimensions}")
        print(f"  总扫描点数: {self.total_points}")
        
        for i, (bound, steps) in enumerate(zip(self.bounds, self.steps_per_dimension)):
            print(f"  通道 {i}: {bound[0]:.3f}V ~ {bound[1]:.3f}V, {steps}步")
        
        return True
    
    def configure_scan_legacy(self, channel_configs):
        """
        向后兼容的配置方法（使用原来的通道配置方式）
        注意: 此方法会覆盖初始化时的配置
        
        参数:
            channel_configs: 列表，每个元素是一个字典，包含通道的扫描配置
                             例如: [{'channel': 0, 'start': 0.0, 'stop': 2.0, 'steps': 5}, ...]
        返回:
            bool: 配置成功返回True
        """
        self.channel_configs = channel_configs
        self.dimensions = len(channel_configs)
        
        # 转换为边界格式
        self.bounds = []
        self.steps_per_dimension = []
        for config in channel_configs:
            self.bounds.append((config['start'], config['stop']))
            self.steps_per_dimension.append(config['steps'])
        
        # 重新计算总扫描点数
        self.total_points = 1
        for config in channel_configs:
            self.total_points *= config['steps']
        
        # 重新验证参数
        self._validate_parameters()
        
        print(f"使用传统配置方式，共有{len(channel_configs)}个通道，总计{self.total_points}个测量点")
        return True
    
    def run_scan(self):
        """
        执行电压扫描
        返回:
            dict: 最佳结果
                optimizer_voltages: 扫描器内部的最佳电压组合（只包含激活通道）
                actual_voltages: 实际的最佳电压向量（包含所有通道）
                fom: 最佳目标函数值
                scan_voltages: 向后兼容的别名（同optimizer_voltages）
                voltages: 向后兼容的别名（同actual_voltages）
        """
        # 准备电压值数组
        voltage_ranges = []
        for i, (bound, steps) in enumerate(zip(self.bounds, self.steps_per_dimension)):
            start, stop = bound
            voltage_ranges.append(np.linspace(start, stop, steps))
        
        print(f"\n开始电压扫描，总计{self.total_points}个测量点...")
        start_time = time.time()
        
        # 保存扫描配置
        self._save_scan_config()
            
        # 递归函数，用于生成所有电压组合
        def scan_recursive(channel_idx, current_voltages, scan_idx):
            if channel_idx >= self.dimensions:
                # 将扫描电压映射到实际通道
                actual_voltages = self._map_voltages_to_actual(current_voltages)
                
                print(f"\r扫描点 {scan_idx}/{self.total_points}: 扫描电压={current_voltages}, 实际电压={actual_voltages}", end="")
                
                # 记录扫描开始时间
                scan_start_time = time.time()
                
                # 使用实际电压调用目标函数
                result = self.objective_func(actual_voltages)
                
                # 记录扫描耗时
                scan_time = time.time() - scan_start_time
                
                # 保存结果（包含扫描电压和实际电压）
                result_with_voltages = result.copy()
                result_with_voltages['optimizer_voltages'] = current_voltages.copy()
                result_with_voltages['actual_voltages'] = actual_voltages.copy()
                # 向后兼容
                result_with_voltages['scan_voltages'] = current_voltages.copy()
                result_with_voltages['voltages'] = actual_voltages.copy()
                
                self.scan_results.append(result_with_voltages)
                
                # 记录扫描历史
                self.scan_history.append({
                    'scan_index': scan_idx,
                    'optimizer_voltages': current_voltages.copy(),
                    'actual_voltages': actual_voltages.copy(),
                    'result': result.copy(),
                    'timestamp': time.time(),
                    'scan_time': scan_time
                })
                
                return scan_idx + 1  # 递增扫描点序号
            
            # 当前通道的电压范围
            voltage_range = voltage_ranges[channel_idx]
            
            # 遍历当前通道的所有电压值
            next_scan_idx = scan_idx
            for voltage in voltage_range:
                # 设置当前通道的电压
                new_voltages = current_voltages.copy()
                new_voltages[channel_idx] = voltage
                
                # 递归处理下一个通道
                next_scan_idx = scan_recursive(channel_idx + 1, new_voltages, next_scan_idx)
            
            return next_scan_idx
            
        # 开始递归扫描
        initial_voltages = [0.0] * self.dimensions
        scan_recursive(0, initial_voltages, 1)
        
        total_time = time.time() - start_time
        print(f"\n扫描完成！总耗时: {total_time:.2f}秒")

        # 保存扫描结果
        self.save_results(total_time)
        
        # 分析扫描结果，找出最小值
        self.best_result = self.analyze_results()
        
        # 构建完整的最佳结果
        best_optimizer_voltages = self.best_result.get('optimizer_voltages', [])
        best_actual_voltages = self.best_result.get('actual_voltages', [])
        
        # 如果没有映射的电压，使用向后兼容的方式
        if not best_actual_voltages and 'voltages' in self.best_result:
            best_actual_voltages = self.best_result['voltages']
            best_optimizer_voltages = self.best_result['voltages']  # 假设相同
        
        complete_best_result = {
            'optimizer_voltages': best_optimizer_voltages,
            'actual_voltages': best_actual_voltages,
            'fom': self.best_result['fom'],
            'scan_voltages': best_optimizer_voltages,  # 向后兼容
            'voltages': best_actual_voltages,          # 向后兼容
            'full_result': self.best_result            # 包含所有原始数据
        }
        
        print(f"\n最佳目标函数值: {complete_best_result['fom']:.6f}")
        print(f"扫描器内部电压: {complete_best_result['optimizer_voltages']}")
        print(f"实际通道电压: {complete_best_result['actual_voltages']}")
        
        # 绘制结果
        ifPlot = input(f"\n是否绘制结果图？(y/n, 默认y)：").strip().lower()
        if ifPlot != 'n':
            self.plot_results()
        
        return complete_best_result
    
    def _save_scan_config(self):
        """保存扫描配置"""
        config_file = os.path.join(self.run_dir, 'scan_config.txt')
        
        with open(config_file, 'w', encoding='utf-8') as f:
            f.write("遍历扫描配置详情\n")
            f.write("=" * 50 + "\n\n")
            
            f.write("【扫描参数配置】\n")
            f.write("-" * 30 + "\n")
            f.write(f"运行ID: {self.run_id}\n")
            f.write(f"通道数量: {self.dimensions}\n")
            f.write(f"总扫描点数: {self.total_points}\n")
            f.write(f"配置时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"结果目录: {self.run_dir}\n\n")
            
            f.write("【通道配置详情】\n")
            f.write("-" * 30 + "\n")
            for i, (bound, steps) in enumerate(zip(self.bounds, self.steps_per_dimension)):
                f.write(f"通道 {i}: {bound[0]:.3f}V ~ {bound[1]:.3f}V, {steps}步\n")
        
        print(f"扫描配置已保存: scan_config.txt")
    
    def analyze_results(self):
        """
        分析扫描结果，找出各指标的最小值
        返回: 
            最小值的结果字典（包含电压信息）
        """
        if not self.scan_results:
            print("没有扫描结果可分析")
            return None

        # 自动检测所有可用的指标（排除电压相关字段）
        voltage_fields = ['voltages', 'optimizer_voltages', 'actual_voltages', 'scan_voltages']
        available_metrics = [key for key in self.scan_results[0].keys() 
                            if key not in voltage_fields]
        primary_metric = 'fom'
        
        if primary_metric not in available_metrics:
            print(f"主要指标 '{primary_metric}' 不存在，使用第一个可用指标 '{available_metrics[0]}'")
            primary_metric = available_metrics[0]

        print(f"\n分析结果 - 主要指标: {primary_metric}")
        print("=" * 60)

        # 分析所有指标
        for metric in available_metrics:
            metric_values = [result[metric] for result in self.scan_results]
            
            # 极值分析
            extreMax_indices = signal.argrelextrema(np.array(metric_values), np.greater)[0]
            max_idx = np.argmax(metric_values)
            extreMin_indices = signal.argrelextrema(np.array(metric_values), np.less)[0]
            min_idx = np.argmin(metric_values)

            marker = "★" if metric == primary_metric else " "

            # 输出极值、最值信息
            # for idx in extreMax_indices:
            #     actual_v = self.scan_results[idx].get('actual_voltages', self.scan_results[idx].get('voltages', []))
            #     print(f"{marker} 指标 '{metric}' 的极大值: {metric_values[idx]:.6f}，实际电压: {actual_v}")
            # print(f"{marker} 指标 '{metric}' 的最大值: {metric_values[max_idx]:.6f}，实际电压: {self.scan_results[max_idx].get('actual_voltages', self.scan_results[max_idx].get('voltages', []))}")
            # for idx in extreMin_indices:
            #     actual_v = self.scan_results[idx].get('actual_voltages', self.scan_results[idx].get('voltages', []))
            #     print(f"{marker} 指标 '{metric}' 的极小值: {metric_values[idx]:.6f}，实际电压: {actual_v}")
            # print(f"{marker} 指标 '{metric}' 的最小值: {metric_values[min_idx]:.6f}，实际电压: {self.scan_results[min_idx].get('actual_voltages', self.scan_results[min_idx].get('voltages', []))}")
            # print()

        # 返回主要指标的最小值（包含完整的电压信息）
        min_idx = np.argmin([result[primary_metric] for result in self.scan_results])
        return self.scan_results[min_idx]

    def plot_results(self):
        """
        根据scan_results绘制结果
        边界上下限相同时不纳入作图维度，但在图上标注该固定电压值（0V时不显示）
        """
        if not self.scan_results:
            print("没有扫描结果可绘制")
            return None

        # 获取有效维度（边界上下限不同的维度）和固定维度
        effective_dimensions = []
        fixed_dimensions = []
        effective_voltages = []
        
        for i, bound in enumerate(self.bounds):
            if bound[0] != bound[1]:  # 边界不同，纳入作图维度
                effective_dimensions.append(i)
                effective_voltages.append([r['voltages'][i] for r in self.scan_results])
            else:  # 边界相同，记录固定电压值（0V时不记录）
                fixed_voltage = bound[0]
                if abs(fixed_voltage) > 1e-6:  # 电压不为0时才记录
                    fixed_dimensions.append((i, fixed_voltage))
        
        num_effective_dims = len(effective_dimensions)
        
        if num_effective_dims == 0:
            print("所有通道的边界上下限相同，无法绘制图形")
            return
        
        metrics = [k for k in self.scan_results[0].keys() if k not in ['voltages']]
        
        # 只绘制fom指标
        plot_metrics = ['fom'] if 'fom' in metrics else [metrics[0]]
        print(f"\n将绘制指标: {plot_metrics[0]} (自动选择FOM)")

        ## 单有效维度绘图
        if num_effective_dims == 1:
            v1 = np.array(effective_voltages[0])
            
            for metric in plot_metrics:
                values = [r[metric] for r in self.scan_results]
                
                plt.figure(figsize=(12, 8))
                plt.plot(v1, values, 'bo-', markersize=6, linewidth=2, label=metric)
                
                # 标记最小值点
                min_idx = np.argmin(values)
                plt.plot(v1[min_idx], values[min_idx], 'r*', markersize=15, 
                        label=f'{metric}最小值 ({v1[min_idx]:.3f}V, {values[min_idx]:.6f})')
                
                plt.xlabel(f'Voltage {effective_dimensions[0]+1} (V)')
                plt.ylabel(metric)
                
                # 构建标题，包含固定电压信息（只显示非0固定电压）
                title = f'{metric} vs Voltage {effective_dimensions[0]+1}'
                if fixed_dimensions:
                    fixed_info = " | 固定电压: "
                    fixed_parts = []
                    for dim_idx, fixed_voltage in fixed_dimensions:
                        fixed_parts.append(f'V{dim_idx+1}={fixed_voltage:.3f}V')
                    fixed_info += ", ".join(fixed_parts)
                    title += fixed_info
                plt.title(title)
                
                plt.grid(True, alpha=0.3)
                plt.legend()
                plt.tight_layout()
                
                # 保存图片
                timestamp = time.strftime('%Y%m%d_%H%M%S')
                plot_filename = f"scan_results_1d_{metric}_{timestamp}.png"
                plt.savefig(os.path.join(self.run_dir, plot_filename), dpi=300, bbox_inches='tight')
                plt.show(block=False)

        elif num_effective_dims == 2:
            v1 = np.array(effective_voltages[0])
            v2 = np.array(effective_voltages[1])
            
            from mpl_toolkits.mplot3d import Axes3D
            
            for metric in plot_metrics:
                z = np.array([r[metric] for r in self.scan_results])
                
                fig = plt.figure(figsize=(14, 10))
                ax = fig.add_subplot(111, projection='3d')
                
                # 创建曲面图
                surf = ax.plot_trisurf(v1, v2, z, cmap='viridis', alpha=0.8, edgecolor='gray', linewidth=0.5)
                
                # 标记最小值点
                min_idx = np.argmin(z)
                ax.scatter(v1[min_idx], v2[min_idx], z[min_idx], 
                        color='red', s=100, marker='*', 
                        label=f'最小值: {z[min_idx]:.6f}')
                
                ax.set_xlabel(f'Voltage {effective_dimensions[0]+1} (V)')
                ax.set_ylabel(f'Voltage {effective_dimensions[1]+1} (V)')
                ax.set_zlabel(metric)
                
                # 构建标题，包含固定电压信息（只显示非0固定电压）
                title = f'{metric} vs Voltages (红色星号标记最小值)'
                if fixed_dimensions:
                    fixed_info = "\n固定电压: "
                    fixed_parts = []
                    for dim_idx, fixed_voltage in fixed_dimensions:
                        fixed_parts.append(f'V{dim_idx+1}={fixed_voltage:.3f}V')
                    fixed_info += ", ".join(fixed_parts)
                    title += fixed_info
                ax.set_title(title)
                
                ax.legend()
                fig.colorbar(surf, ax=ax, shrink=0.5, aspect=5)
                plt.tight_layout()
                
                # 保存图片
                timestamp = time.strftime('%Y%m%d_%H%M%S')
                plot_filename = f"scan_results_2d_{metric}_{timestamp}.png"
                plt.savefig(os.path.join(self.run_dir, plot_filename), dpi=300, bbox_inches='tight')
                plt.show(block=False)
        else:
            print(f"有效维度数量 ({num_effective_dims}) 超过2，无法绘制图形")
            print(f"有效维度索引: {effective_dimensions}")
            # 只显示非0的固定电压
            non_zero_fixed = [(dim_idx, voltage) for dim_idx, voltage in fixed_dimensions if abs(voltage) > 1e-6]
            if non_zero_fixed:
                print("固定电压配置:")
                for dim_idx, fixed_voltage in non_zero_fixed:
                    print(f"  通道 {dim_idx+1}: {fixed_voltage:.3f}V")
    
    def save_results(self, total_time=None):
        """
        保存扫描结果到多种格式
        """
        if not self.scan_results:
            print("没有扫描结果可供保存")
            return
        
        # 获取关键词
        keyword = input("请输入保存文件的关键词 (默认为'voltage_scan_results'): ") or "voltage_scan_results"
        timestamp = time.strftime('%Y%m%d_%H%M%S')
        
        # 1. 保存CSV文件
        csv_filename = f"{keyword}_{timestamp}.csv"
        self._save_to_csv(csv_filename)
        
        # 2. 保存Pickle文件
        pkl_filename = f"{keyword}_{timestamp}.pkl"
        self._save_to_pickle(pkl_filename)
        
        # 3. 保存文本摘要
        summary_filename = f"{keyword}_{timestamp}_summary.txt"
        self._save_text_summary(summary_filename, total_time)
        
        print(f"\n结果已保存到目录: {self.run_dir}")
        print(f"  - CSV数据文件: {csv_filename}")
        print(f"  - Pickle完整结果: {pkl_filename}")
        print(f"  - 文本摘要: {summary_filename}")
    
    def _save_to_csv(self, filename):
        """保存结果到CSV文件"""
        try:
            with open(os.path.join(self.run_dir, filename), 'w', newline='', encoding='utf-8') as csvfile:
                # 动态创建CSV表头
                fieldnames = ['scan_index']
                # 获取实际使用的电压通道数
                # 从scan_results中获取实际的电压长度
                if self.scan_results and 'voltages' in self.scan_results[0]:
                    actual_channel_count = len(self.scan_results[0]['voltages'])
                else:
                    actual_channel_count = self.total_channels
                
                # 只添加实际存在的电压列
                for i in range(actual_channel_count):
                    fieldnames.append(f'voltage_{i+1}')
                # 添加其他指标列（排除voltages）
                for key in self.scan_results[0].keys():
                    if key != 'voltages':
                        fieldnames.append(key)
                
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                
                # 写入所有结果
                for scan_idx, result in enumerate(self.scan_results, 1):
                    row = {'scan_index': scan_idx}
                    # 添加电压值
                    for i, v in enumerate(result['voltages']):
                        row[f'voltage_{i+1}'] = v
                    # 动态添加其他指标
                    for key, value in result.items():
                        if key != 'voltages':
                            row[key] = value
                    writer.writerow(row)
        
        except Exception as e:
            print(f"保存CSV文件时出错: {e}")
    
    def _save_to_pickle(self, filename):
        """保存完整结果到Pickle文件"""
        try:
            results_dict = {
                'scan_results': self.scan_results,
                'best_result': self.best_result,
                'bounds': self.bounds,
                'steps_per_dimension': self.steps_per_dimension,
                'dimensions': self.dimensions,
                'run_id': self.run_id,
                'scan_history': self.scan_history,
                'completion_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'total_points': len(self.scan_results)
            }
            
            with open(os.path.join(self.run_dir, filename), 'wb') as f:
                pickle.dump(results_dict, f)
                
        except Exception as e:
            print(f"保存Pickle文件时出错: {e}")
    
    def _save_text_summary(self, filename, total_time=None):
        """保存文本摘要"""
        try:
            with open(os.path.join(self.run_dir, filename), 'w', encoding='utf-8') as f:
                f.write("电压扫描结果摘要\n")
                f.write("=" * 60 + "\n\n")
                
                # 扫描配置信息
                f.write("【扫描配置】\n")
                f.write("-" * 40 + "\n")
                f.write(f"运行ID: {self.run_id}\n")
                f.write(f"通道数量: {self.dimensions}\n")
                f.write(f"总扫描点数: {len(self.scan_results)}\n")
                f.write(f"完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"结果目录: {self.run_dir}\n\n")
                
                # 通道配置详情
                f.write("通道配置详情:\n")
                for i, (bound, steps) in enumerate(zip(self.bounds, self.steps_per_dimension)):
                    f.write(f"  通道 {i}: {bound[0]:.3f}V ~ {bound[1]:.3f}V, {steps}步\n")
                f.write("\n")
                
                # 最佳结果
                if self.best_result:
                    f.write("【最佳结果】\n")
                    f.write("-" * 40 + "\n")
                    f.write(f"最佳FOM值: {self.best_result['fom']:.6f}\n")
                    f.write("最佳电压配置:\n")
                    for i, voltage in enumerate(self.best_result['voltages']):
                        f.write(f"  通道 {i}: {voltage:.3f} V\n")
                    f.write("\n")
                
                # 性能统计
                if self.scan_history:
                    total_scan_time = sum([record['scan_time'] for record in self.scan_history])
                    avg_time = total_scan_time / len(self.scan_history)
                    f.write("【性能统计】\n")
                    f.write("-" * 40 + "\n")
                    if total_time:
                        f.write(f"总运行时间: {total_time:.2f}秒\n")
                    f.write(f"总扫描时间: {total_scan_time:.2f}秒\n")
                    f.write(f"平均每点耗时: {avg_time:.2f}秒\n")
                    f.write(f"扫描速率: {1/avg_time:.2f}点/秒\n")
                
        except Exception as e:
            print(f"保存文本摘要时出错: {e}")
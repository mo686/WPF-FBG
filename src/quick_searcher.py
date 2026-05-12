import numpy as np
import matplotlib.pyplot as plt
import time
import csv
import pickle
import os
from datetime import datetime

import plot_style  # 学术论文绘图风格

class QuickSearcher:
    """
    快速搜索类 - 顺序扫描优化算法
    根据电压通道列表顺序逐个扫描通道电压，找到最小值后固定该通道电压，再扫描下一个通道
    """
    
    def __init__(self, ilsts, voltage_controller, objective_func, bounds, steps_per_dimension, 
                 run_id=1, active_channels=None, total_channels=None):
        """
        初始化快速搜索器
        
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
        
        # 通道映射配置
        self.active_channels = active_channels or list(range(len(bounds)))
        self.total_channels = total_channels or len(self.active_channels)
        
        # 验证参数
        self._validate_parameters()
        
        # 初始化结果存储
        self.scan_results = []
        self.best_result = {}
        self.search_history = []
        self.optimization_path = []  # 记录优化路径
        
        # 创建结果目录
        self.run_dir = f"./quick_search_runs/run_{run_id}"
        os.makedirs(self.run_dir, exist_ok=True)
        
        # 计算总评估点数（比遍历少很多）
        self.total_evaluations = sum(steps_per_dimension)
        
        print(f"🎯 初始化快速搜索器 (运行{run_id})")
        print(f"   激活通道: {[ch+1 for ch in self.active_channels]}")
        print(f"   总通道数: {self.total_channels}")
        print(f"   优化维度: {len(self.active_channels)} -> {self.total_channels}")
        print(f"   预计评估点数: {self.total_evaluations}")
        print(f"   结果目录: {self.run_dir}")
        
        # 显示搜索策略
        print("   搜索策略: 顺序扫描优化")
        for i, (bound, steps) in enumerate(zip(bounds, steps_per_dimension)):
            actual_channel = self.active_channels[i]
            print(f"     通道 {actual_channel+1}: {bound[0]:.3f}V ~ {bound[1]:.3f}V, {steps}步")
    
    def _validate_parameters(self):
        """验证初始化参数"""
        if len(self.bounds) != len(self.steps_per_dimension):
            raise ValueError("bounds和steps_per_dimension的长度必须一致")
        
        if len(self.active_channels) != len(self.bounds):
            raise ValueError("active_channels的长度必须与bounds一致")
        
        for i, (bound, steps) in enumerate(zip(self.bounds, self.steps_per_dimension)):
            if bound[0] > bound[1]:
                raise ValueError(f"通道 {i} 的边界范围无效: [{bound[0]}, {bound[1]}]")
            if steps < 1:
                raise ValueError(f"通道 {i} 的步数必须大于0: {steps}")
    
    def _map_voltages_to_actual(self, scan_voltages):
        """
        将扫描电压映射到实际的电压向量
        
        参数:
        - scan_voltages: 扫描器内部电压向量（只包含激活通道）
        
        返回:
        - 完整的电压向量（包含所有通道，未激活通道设为0）
        """
        # 创建全零电压向量
        voltages = [0.0] * self.total_channels
        
        # 将扫描电压设置到激活的通道
        for i, channel_index in enumerate(self.active_channels):
            if channel_index < self.total_channels:
                voltages[channel_index] = scan_voltages[i]
        
        return voltages
    
    def run_scan(self):
        """
        执行快速顺序搜索
        返回:
            dict: 最佳结果
                optimizer_voltages: 扫描器内部的最佳电压组合（只包含激活通道）
                actual_voltages: 实际的最佳电压向量（包含所有通道）
                fom: 最佳目标函数值
                scan_voltages: 向后兼容的别名（同optimizer_voltages）
                voltages: 向后兼容的别名（同actual_voltages）
        """
        print(f"\n开始快速顺序搜索...")
        print(f"搜索策略: 按通道顺序逐个优化，固定最优值后继续下一通道")
        
        start_time = time.time()
        
        # 保存搜索配置
        self._save_search_config()
        
        # 初始化电压配置（从0开始）- 只包含激活通道
        current_scan_voltages = [0.0] * self.dimensions
        best_scan_voltages = current_scan_voltages.copy()
        
        # 映射到实际电压
        current_actual_voltages = self._map_voltages_to_actual(current_scan_voltages)
        
        # 初始评估
        initial_result = self.objective_func(current_actual_voltages)
        best_fom = initial_result['fom']
        
        self.search_history.append({
            'step': 0,
            'channel': 'initial',
            'scan_voltages': current_scan_voltages.copy(),
            'actual_voltages': current_actual_voltages.copy(),
            'fom': best_fom,
            'timestamp': time.time()
        })
        
        print(f"\n初始状态: 扫描电压={current_scan_voltages}, 实际电压={current_actual_voltages}, FOM={best_fom:.6f}")
        
        # 顺序扫描每个通道
        for channel_idx in range(self.dimensions):
            actual_channel_num = self.active_channels[channel_idx] + 1
            print(f"\n--- 优化通道 {actual_channel_num} (内部索引: {channel_idx}) ---")
            
            # 准备当前通道的电压范围
            start, stop = self.bounds[channel_idx]
            steps = self.steps_per_dimension[channel_idx]
            voltage_range = np.linspace(start, stop, steps)
            
            channel_best_voltage = best_scan_voltages[channel_idx]
            channel_best_fom = best_fom
            
            print(f"扫描范围: {start:.3f}V ~ {stop:.3f}V, {steps}个点")
            
            # 扫描当前通道
            for voltage in voltage_range:
                test_scan_voltages = best_scan_voltages.copy()
                test_scan_voltages[channel_idx] = voltage
                
                # 映射到实际电压
                test_actual_voltages = self._map_voltages_to_actual(test_scan_voltages)
                
                print(f"\n测试电压: 扫描={voltage:.3f}V, 实际通道={actual_channel_num}", end="")
                
                # 评估当前电压配置
                result = self.objective_func(test_actual_voltages)
                current_fom = result['fom']
                
                # 记录搜索历史
                self.search_history.append({
                    'step': len(self.search_history),
                    'channel': channel_idx,
                    'actual_channel': actual_channel_num,
                    'scan_voltages': test_scan_voltages.copy(),
                    'actual_voltages': test_actual_voltages.copy(),
                    'fom': current_fom,
                    'timestamp': time.time()
                })
                
                # 更新最佳值
                if current_fom < channel_best_fom:
                    channel_best_fom = current_fom
                    channel_best_voltage = voltage
                    best_scan_voltages[channel_idx] = voltage
                    
                    print(f" → 新最佳: FOM={current_fom:.6f}")
            
            # 固定当前通道的最佳电压
            best_scan_voltages[channel_idx] = channel_best_voltage
            best_fom = channel_best_fom
            
            # 获取当前完整的实际电压
            current_actual_voltages = self._map_voltages_to_actual(best_scan_voltages)
            
            print(f"\n通道 {actual_channel_num} 优化完成:")
            print(f"  最佳电压: {channel_best_voltage:.3f}V")
            print(f"  最佳FOM: {channel_best_fom:.6f}")
            print(f"  当前扫描配置: {best_scan_voltages}")
            print(f"  当前实际配置: {current_actual_voltages}")
            
            # 记录优化路径
            self.optimization_path.append({
                'channel': channel_idx,
                'actual_channel': actual_channel_num,
                'best_voltage': channel_best_voltage,
                'best_fom': channel_best_fom,
                'scan_voltages': best_scan_voltages.copy(),
                'actual_voltages': current_actual_voltages.copy()
            })
        
        total_time = time.time() - start_time
        
        # 最终评估
        final_actual_voltages = self._map_voltages_to_actual(best_scan_voltages)
        final_result = self.objective_func(final_actual_voltages)
        
        self.best_result = {
            'optimizer_voltages': best_scan_voltages,
            'actual_voltages': final_actual_voltages,
            'fom': final_result['fom'],
            'scan_voltages': best_scan_voltages,  # 向后兼容
            'voltages': final_actual_voltages     # 向后兼容
        }
        
        # 收集所有评估结果用于分析
        self.scan_results = [{
            'scan_voltages': record['scan_voltages'],
            'actual_voltages': record['actual_voltages'],
            'fom': record['fom']
        } for record in self.search_history]
        
        print(f"\n🎉 快速搜索完成!")
        print(f"总耗时: {total_time:.2f}秒")
        print(f"总评估次数: {len(self.search_history)}")
        print(f"最终最佳FOM: {self.best_result['fom']:.6f}")
        print(f"最终扫描配置: {self.best_result['optimizer_voltages']}")
        print(f"最终实际配置: {self.best_result['actual_voltages']}")
        
        # 保存结果
        self.save_results(total_time)
        
        # 绘制结果
        ifPlot = input(f"\n是否绘制结果图？(y/n, 默认y)：").strip().lower()
        if ifPlot != 'n':
            self.plot_results()
        
        return self.best_result
    
    def _save_search_config(self):
        """保存搜索配置"""
        config_file = os.path.join(self.run_dir, 'search_config.txt')
        
        with open(config_file, 'w', encoding='utf-8') as f:
            f.write("快速搜索配置详情\n")
            f.write("=" * 50 + "\n\n")
            
            f.write("【搜索参数配置】\n")
            f.write("-" * 30 + "\n")
            f.write(f"运行ID: {self.run_id}\n")
            f.write(f"激活通道数: {len(self.active_channels)}\n")
            f.write(f"总通道数: {self.total_channels}\n")
            f.write(f"激活通道: {[ch+1 for ch in self.active_channels]}\n")
            f.write(f"预计评估点数: {self.total_evaluations}\n")
            f.write(f"搜索策略: 顺序扫描优化\n")
            f.write(f"配置时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"结果目录: {self.run_dir}\n\n")
            
            f.write("【通道配置详情】\n")
            f.write("-" * 30 + "\n")
            for i, (bound, steps) in enumerate(zip(self.bounds, self.steps_per_dimension)):
                actual_channel = self.active_channels[i]
                f.write(f"通道 {actual_channel+1}: {bound[0]:.3f}V ~ {bound[1]:.3f}V, {steps}步\n")
            
            f.write(f"\n【搜索策略说明】\n")
            f.write("-" * 30 + "\n")
            f.write(f"1. 按通道顺序逐个优化\n")
            f.write(f"2. 对每个通道扫描指定步数的电压值\n")
            f.write(f"3. 找到最佳电压后固定该通道\n")
            f.write(f"4. 继续优化下一个通道\n")
            f.write(f"5. 总评估次数 ≈ 各通道步数之和\n")
            f.write(f"6. 通道映射: {len(self.active_channels)}个激活通道 -> {self.total_channels}个总通道\n")
        
        print(f"搜索配置已保存: search_config.txt")
    
    def plot_results(self):
        """
        绘制快速搜索结果
        """
        if not self.search_history:
            print("没有搜索结果可绘制")
            return
        
        # 绘制优化过程
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        
        # 子图(a): FOM优化过程
        ax1 = axes[0, 0]
        fom_values = [record['fom'] for record in self.search_history]
        steps = list(range(len(fom_values)))
        
        ax1.plot(steps, fom_values, 'bo-', alpha=0.7, linewidth=1, markersize=3)
        ax1.set_xlabel('Evaluation Step')
        ax1.set_ylabel('FOM')
        
        # 标记最佳点
        best_idx = np.argmin(fom_values)
        ax1.plot(best_idx, fom_values[best_idx], 'r*', markersize=10, 
                label=f'Best FOM: {fom_values[best_idx]:.6f}')
        ax1.legend()
        plot_style.add_subplot_label(ax1, '(a)')
        
        # 子图(b): 各通道优化过程
        ax2 = axes[0, 1]
        colors = plt.cm.Set1(np.linspace(0, 1, self.dimensions))
        
        for channel_idx in range(self.dimensions):
            actual_channel_num = self.active_channels[channel_idx] + 1
            channel_steps = []
            channel_foms = []
            
            for i, record in enumerate(self.search_history):
                if record.get('channel') == channel_idx or (i == 0 and record.get('channel') == 'initial'):
                    channel_steps.append(i)
                    channel_foms.append(record['fom'])
            
            if channel_steps:
                ax2.plot(channel_steps, channel_foms, 'o-', color=colors[channel_idx], 
                        label=f'Ch {actual_channel_num}', markersize=4)
        
        ax2.set_xlabel('Evaluation Step')
        ax2.set_ylabel('FOM')
        ax2.legend()
        plot_style.add_subplot_label(ax2, '(b)')
        
        # 子图(c): 实际电压变化过程
        ax3 = axes[1, 0]
        for channel_idx in range(self.total_channels):
            if channel_idx in self.active_channels:
                # 只绘制激活通道的电压变化
                voltages = [record['actual_voltages'][channel_idx] for record in self.search_history]
                ax3.plot(steps, voltages, 'o-', label=f'V{channel_idx+1}', markersize=2, alpha=0.7)
        
        ax3.set_xlabel('Evaluation Step')
        ax3.set_ylabel('Voltage (V)')
        ax3.legend()
        plot_style.add_subplot_label(ax3, '(c)')
        
        # 子图(d): 优化路径总结
        ax4 = axes[1, 1]
        if len(self.optimization_path) >= 2:
            path_foms = [step['best_fom'] for step in self.optimization_path]
            path_channels = [step['actual_channel'] for step in self.optimization_path]
            
            ax4.plot(path_channels, path_foms, 'gs-', linewidth=2, markersize=8, 
                    label='Optimization path')
            ax4.set_xlabel('Channel')
            ax4.set_ylabel('Best FOM')
            ax4.legend()
        plot_style.add_subplot_label(ax4, '(d)')
        
        plt.tight_layout()
        
        # 保存图片
        timestamp = time.strftime('%Y%m%d_%H%M%S')
        plot_filename = f"quick_search_results_{timestamp}.png"
        plt.savefig(os.path.join(self.run_dir, plot_filename), dpi=300, bbox_inches='tight')
        plt.show(block=False)
    
    def save_results(self, total_time=None):
        """
        保存搜索结果到多种格式
        """
        if not self.search_history:
            print("没有搜索结果可供保存")
            return
        
        # 获取关键词
        keyword = input("请输入保存文件的关键词 (默认为'quick_search_results'): ") or "quick_search_results"
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
                fieldnames = ['step', 'internal_channel', 'actual_channel', 'fom']
                # 添加扫描电压列
                for i in range(self.dimensions):
                    fieldnames.append(f'scan_voltage_{i+1}')
                # 添加实际电压列
                for i in range(self.total_channels):
                    fieldnames.append(f'actual_voltage_{i+1}')
                
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                
                for record in self.search_history:
                    row = {
                        'step': record['step'],
                        'internal_channel': record.get('channel', 'initial'),
                        'actual_channel': record.get('actual_channel', 'initial'),
                        'fom': record['fom']
                    }
                    # 添加扫描电压
                    for i, voltage in enumerate(record['scan_voltages']):
                        row[f'scan_voltage_{i+1}'] = voltage
                    # 添加实际电压
                    for i, voltage in enumerate(record['actual_voltages']):
                        row[f'actual_voltage_{i+1}'] = voltage
                    writer.writerow(row)
        
        except Exception as e:
            print(f"保存CSV文件时出错: {e}")
    
    def _save_to_pickle(self, filename):
        """保存完整结果到Pickle文件"""
        try:
            results_dict = {
                'search_history': self.search_history,
                'best_result': self.best_result,
                'optimization_path': self.optimization_path,
                'bounds': self.bounds,
                'steps_per_dimension': self.steps_per_dimension,
                'active_channels': self.active_channels,
                'total_channels': self.total_channels,
                'dimensions': self.dimensions,
                'run_id': self.run_id,
                'completion_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'total_evaluations': len(self.search_history)
            }
            
            with open(os.path.join(self.run_dir, filename), 'wb') as f:
                pickle.dump(results_dict, f)
                
        except Exception as e:
            print(f"保存Pickle文件时出错: {e}")
    
    def _save_text_summary(self, filename, total_time=None):
        """保存文本摘要"""
        try:
            with open(os.path.join(self.run_dir, filename), 'w', encoding='utf-8') as f:
                f.write("快速搜索结果摘要\n")
                f.write("=" * 60 + "\n\n")
                
                # 搜索配置信息
                f.write("【搜索配置】\n")
                f.write("-" * 40 + "\n")
                f.write(f"运行ID: {self.run_id}\n")
                f.write(f"激活通道数: {len(self.active_channels)}\n")
                f.write(f"总通道数: {self.total_channels}\n")
                f.write(f"激活通道: {[ch+1 for ch in self.active_channels]}\n")
                f.write(f"总评估次数: {len(self.search_history)}\n")
                f.write(f"完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"结果目录: {self.run_dir}\n\n")
                
                # 通道配置详情
                f.write("通道配置详情:\n")
                for i, (bound, steps) in enumerate(zip(self.bounds, self.steps_per_dimension)):
                    actual_channel = self.active_channels[i]
                    f.write(f"  通道 {actual_channel+1}: {bound[0]:.3f}V ~ {bound[1]:.3f}V, {steps}步\n")
                f.write("\n")
                
                # 最佳结果
                if self.best_result:
                    f.write("【最佳结果】\n")
                    f.write("-" * 40 + "\n")
                    f.write(f"最佳FOM值: {self.best_result['fom']:.6f}\n")
                    f.write("最佳扫描电压配置:\n")
                    for i, voltage in enumerate(self.best_result['optimizer_voltages']):
                        actual_channel = self.active_channels[i]
                        f.write(f"  通道 {actual_channel+1}: {voltage:.3f} V\n")
                    f.write("最佳实际电压配置:\n")
                    for i, voltage in enumerate(self.best_result['actual_voltages']):
                        if i in self.active_channels or abs(voltage) > 1e-6:
                            f.write(f"  通道 {i+1}: {voltage:.3f} V")
                            if i in self.active_channels:
                                f.write(" *")
                            f.write("\n")
                    f.write("  (* 表示激活的优化通道)\n\n")
                
                # 优化路径
                f.write("【优化路径】\n")
                f.write("-" * 40 + "\n")
                for step in self.optimization_path:
                    f.write(f"  通道 {step['actual_channel']}: 最佳电压={step['best_voltage']:.3f}V, FOM={step['best_fom']:.6f}\n")
                f.write("\n")
                
                # 性能统计
                if self.search_history:
                    f.write("【性能统计】\n")
                    f.write("-" * 40 + "\n")
                    if total_time:
                        f.write(f"总运行时间: {total_time:.2f}秒\n")
                    f.write(f"平均每点耗时: {total_time/len(self.search_history):.2f}秒\n")
                    f.write(f"搜索速率: {len(self.search_history)/total_time:.2f}点/秒\n")
                
        except Exception as e:
            print(f"保存文本摘要时出错: {e}")
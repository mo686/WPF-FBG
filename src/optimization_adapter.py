import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
import pickle
import time
import os
from datetime import datetime

import plot_style  # 学术论文绘图风格

class OptimizationAdapter:
    """
    优化器适配器 - 接收已配置的算法对象和目标函数，提供完整优化流程
    """
    
    def __init__(self, optimizer, objective_func, optimizer_type, run_id=1, 
                 active_channels=None, total_channels=None):
        """
        初始化优化器适配器
        
        参数:
        - optimizer: 已完全配置好的优化算法对象
        - objective_func: 目标函数
        - optimizer_type: 优化器类型 ('PSO' 或 'Bayesian')
        - run_id: 运行ID
        - active_channels: 实际需要优化的通道索引列表（0-based），如 [1, 3] 表示第2和第4个通道
        - total_channels: 总通道数
        - voltage_bounds: 电压边界，用于电压裁剪
        """
        self.optimizer = optimizer
        self.original_objective_func = objective_func
        self.optimizer_type = optimizer_type
        self.run_id = run_id
        
        # 通道映射配置
        self.active_channels = active_channels or list(range(len(optimizer.bounds)))
        self.total_channels = total_channels or len(self.active_channels)
        
        # 创建结果目录
        self.run_dir = f"./{optimizer_type.lower()}_optimization_runs/run_{run_id}"
        os.makedirs(self.run_dir, exist_ok=True)

        # 设置优化器的运行目录
        if hasattr(self.optimizer, 'set_run_directory'):
            self.optimizer.set_run_directory(self.run_dir)
        
        # 优化历史
        self.optimization_history = []
        self.best_parameters = None
        self.best_fom = float('inf')
        
        print(f"🎯 初始化{self.optimizer_type}优化适配器 (运行{run_id})")
        print(f"   激活通道: {[ch+1 for ch in self.active_channels]}")
        print(f"   总通道数: {self.total_channels}")
        print(f"   优化维度: {len(self.active_channels)} -> {self.total_channels}")
    
    def _map_parameters_to_voltages(self, optimizer_parameters):
        """
        将优化器参数映射到实际的电压向量
        
        参数:
        - optimizer_parameters: 优化器产生的参数向量（只包含激活通道）
        
        返回:
        - 完整的电压向量（包含所有通道，未激活通道设为0）
        """
        # 创建全零电压向量
        voltages = [0.0] * self.total_channels
        
        # 将优化器参数设置到激活的通道
        for i, channel_index in enumerate(self.active_channels):
            if channel_index < self.total_channels:
                voltages[channel_index] = optimizer_parameters[i]
        
        return voltages
    
    def _objective_wrapper(self, optimizer_parameters):
        """
        包装目标函数，适配优化器接口
        
        参数:
        - optimizer_parameters: 优化器产生的参数向量（只包含激活通道）
        """
        try:
            # 将优化器参数映射到实际电压通道
            actual_voltages = self._map_parameters_to_voltages(optimizer_parameters)
            
            # 调用原始目标函数 - 传递完整的电压向量
            result = self.original_objective_func(actual_voltages)
            
            # 提取FOM值
            if isinstance(result, dict) and 'fom' in result:
                fom_value = result['fom']
            else:
                fom_value = float(result) if isinstance(result, (int, float)) else float('inf')
            
            # 记录评估历史
            self.optimization_history.append({
                'optimizer_parameters': optimizer_parameters.copy(),
                'actual_voltages': actual_voltages.copy(),
                'fom': fom_value,
                'timestamp': time.time()
            })
            
            # 改进的日志输出
            active_voltages_info = []
            for i, channel_index in enumerate(self.active_channels):
                active_voltages_info.append(f"V{channel_index+1}={actual_voltages[channel_index]:.3f}V")
            
            print(f"🔄 评估: 优化器参数=[{', '.join([f'{p:.3f}' for p in optimizer_parameters])}], "
                  f"实际电压={', '.join(active_voltages_info)}, FOM={fom_value:.6f}")
            
            return fom_value
            
        except Exception as e:
            print(f"❌ 目标函数评估异常: {e}")
            return float('inf')
    
    def _format_parameters(self, parameters):
        """格式化参数显示"""
        parts = []
        for i, name in enumerate(self.optimizer.param_names):
            if name.startswith('V'):
                parts.append(f"{name}={parameters[i]:.3f}V")
            elif name in ['N1', 'N2', 'N3'] or i in getattr(self.optimizer, 'integer_params', []):
                parts.append(f"{name}={int(parameters[i])}")
            else:
                parts.append(f"{name}={parameters[i]:.6f}")
        return ", ".join(parts)
    
    def _format_actual_voltages(self, voltages):
        """格式化实际电压显示"""
        parts = []
        for i, voltage in enumerate(voltages):
            if i in self.active_channels:
                parts.append(f"V{i+1}={voltage:.3f}V*")  # *标记激活通道
            elif voltage != 0:
                parts.append(f"V{i+1}={voltage:.3f}V")
            # 对于未激活且为0的通道，不显示
        return ", ".join(parts) if parts else "全零"
    
    def optimize(self, verbose=True):
        """
        执行优化
        
        参数:
        - verbose: 是否显示详细信息
        
        返回:
        - tuple: (最佳参数, 最佳目标函数值, 优化结果字典)
        """
        print(f"\n🚀 开始{self.optimizer_type}优化...")
        print(f"   通道映射: {len(self.active_channels)}个激活通道 -> {self.total_channels}个总通道")
        
        # 执行优化
        start_time = time.time()
        
        try:
            result = self.optimizer.optimize(
                objective_function=self._objective_wrapper,
                verbose=verbose
            )
            
            # 提取结果
            self.best_parameters = result['best_parameters']
            self.best_fom = result['best_fom']
                
        except Exception as e:
            print(f"❌ 优化过程异常: {e}")
            return None, float('inf'), {}
        
        optimization_time = time.time() - start_time
        
        # 将最佳参数映射回实际电压
        best_actual_voltages = self._map_parameters_to_voltages(self.best_parameters)
        
        print(f"\n✅ {self.optimizer_type}优化完成!")
        print(f"最佳优化器参数: {self._format_parameters(self.best_parameters)}")
        print(f"最佳实际电压: {self._format_actual_voltages(best_actual_voltages)}")
        print(f"最佳目标函数值: {self.best_fom:.6f}")
        print(f"优化耗时: {optimization_time/60:.2f}分钟")
        
        # 保存结果
        self._save_optimization_results(result, optimization_time, best_actual_voltages)
        
        # 可视化优化过程
        self._plot_optimization_process()
        
        return best_actual_voltages, self.best_fom, result
    
    def _plot_optimization_process(self):
        """绘制优化过程"""
        if len(self.optimization_history) < 5:
            print("评估点不足，无法绘制优化过程")
            return
        
        foms = [record['fom'] for record in self.optimization_history]
        best_so_far = [min(foms[:i+1]) for i in range(len(foms))]
        
        fig, axes = plt.subplots(2, 1, figsize=(12, 8))
        
        # 子图(a): 所有评估点
        ax1 = axes[0]
        ax1.plot(range(1, len(foms) + 1), foms, 'bo-', alpha=0.7, linewidth=1, markersize=4, label='All evaluations')
        ax1.axhline(y=self.best_fom, color='r', linestyle='--', linewidth=2, 
                   label=f'Best: {self.best_fom:.6f}')
        ax1.set_xlabel('Evaluation Index')
        ax1.set_ylabel('Objective Function Value')
        ax1.legend()
        plot_style.add_subplot_label(ax1, '(a)')
        
        # 子图(b): 最佳值变化
        ax2 = axes[1]
        ax2.plot(range(1, len(best_so_far) + 1), best_so_far, 'g-o', linewidth=2, markersize=4)
        ax2.set_xlabel('Evaluation Index')
        ax2.set_ylabel('Best Objective Value')
        plot_style.add_subplot_label(ax2, '(b)')
        
        plt.tight_layout()
        
        # 保存图片
        timestamp = time.strftime('%Y%m%d_%H%M%S')
        plot_filename = f"{self.optimizer_type.lower()}_optimization_{timestamp}.png"
        plt.savefig(os.path.join(self.run_dir, plot_filename), dpi=300, bbox_inches='tight')
        print(f"优化过程图片已保存: {plot_filename}")
        
        plt.show(block=False)
    
    def _save_optimization_results(self, result, optimization_time, best_actual_voltages):
        """保存优化结果"""
        # 保存pickle文件
        results_dict = {
            'best_optimizer_parameters': self.best_parameters,
            'best_actual_voltages': best_actual_voltages,
            'best_fitness': self.best_fom,
            'optimization_time': optimization_time,
            'run_id': self.run_id,
            'optimizer_type': self.optimizer_type,
            'param_names': self.optimizer.param_names,
            'active_channels': self.active_channels,
            'total_channels': self.total_channels,
            'bounds': self.optimizer.bounds.tolist() if hasattr(self.optimizer.bounds, 'tolist') else self.optimizer.bounds,
            'evaluation_count': len(self.optimization_history),
            'completion_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'full_result': result,
            'optimization_history': self.optimization_history
        }
        
        with open(os.path.join(self.run_dir, 'final_results.pkl'), 'wb') as f:
            pickle.dump(results_dict, f)
        
        # 保存CSV历史数据
        self._save_optimization_history(best_actual_voltages)
        
        # 保存文本摘要
        self._save_text_summary(results_dict, optimization_time, best_actual_voltages)
    
    def _save_optimization_history(self, best_actual_voltages):
        """保存优化历史数据到CSV"""
        if not self.optimization_history:
            return
        
        df_data = []
        best_so_far = float('inf')
        
        for i, record in enumerate(self.optimization_history):
            optimizer_params = record['optimizer_parameters']
            actual_voltages = record['actual_voltages']
            fom = record['fom']
            
            is_best = fom < best_so_far
            if is_best:
                best_so_far = fom
            
            row = {
                'evaluation_index': i + 1, 
                'fom': fom, 
                'is_best': is_best
            }
            
            # 添加优化器参数值
            for j, name in enumerate(self.optimizer.param_names):
                row[f'optimizer_{name}'] = optimizer_params[j]
            
            # 添加实际电压值
            for ch_idx in range(self.total_channels):
                row[f'actual_V{ch_idx+1}'] = actual_voltages[ch_idx]
                row[f'active_V{ch_idx+1}'] = '是' if ch_idx in self.active_channels else '否'
            
            df_data.append(row)
        
        df = pd.DataFrame(df_data)
        df.to_csv(os.path.join(self.run_dir, 'optimization_history.csv'), index=False)
        print(f"优化历史已保存到: optimization_history.csv")
    
    def _save_text_summary(self, results_dict, optimization_time, best_actual_voltages):
        """保存文本摘要"""
        summary_file = os.path.join(self.run_dir, 'optimization_summary.txt')
        
        with open(summary_file, 'w', encoding='utf-8') as f:
            f.write(f"{self.optimizer_type}优化结果摘要 (运行{self.run_id})\n")
            f.write("=" * 70 + "\n\n")
            
            # 优化器基本信息
            f.write("【优化器基本信息】\n")
            f.write("-" * 40 + "\n")
            f.write(f"优化器类型: {self.optimizer_type}\n")
            f.write(f"运行ID: {self.run_id}\n")
            f.write(f"激活通道数: {len(self.active_channels)}\n")
            f.write(f"总通道数: {self.total_channels}\n")
            f.write(f"激活通道: {[ch+1 for ch in self.active_channels]}\n")
            f.write(f"完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"结果目录: {self.run_dir}\n\n")
            
            # 参数边界信息
            f.write("【优化器参数边界设置】\n")
            f.write("-" * 40 + "\n")
            for i, name in enumerate(self.optimizer.param_names):
                bounds = self.optimizer.bounds[i]
                low, high = bounds[0], bounds[1]
                integer_params = getattr(self.optimizer, 'integer_params', [])
                param_type = "整数" if i in integer_params else "连续"
                f.write(f"  {name}: [{low:.6f}, {high:.6f}] ({param_type})\n")
            f.write("\n")
            
            # 优化结果
            f.write("【优化结果】\n")
            f.write("-" * 40 + "\n")
            f.write(f"最佳目标函数值: {self.best_fom:.6f}\n")
            f.write(f"总评估次数: {len(self.optimization_history)}\n")
            f.write(f"优化耗时: {optimization_time/60:.2f} 分钟\n")
            f.write(f"平均每次评估耗时: {optimization_time/len(self.optimization_history):.2f} 秒\n")
            
            # 收敛信息
            if len(self.optimization_history) > 0:
                initial_fom = self.optimization_history[0]['fom']
                improvement_pct = ((initial_fom - self.best_fom) / initial_fom) * 100
                f.write(f"初始FOM: {initial_fom:.6f}\n")
                f.write(f"改进幅度: {improvement_pct:+.2f}%\n")
            
            f.write("\n")
            
            # 最佳参数配置
            f.write("【最佳优化器参数】\n")
            f.write("-" * 40 + "\n")
            for i, name in enumerate(self.optimizer.param_names):
                if name in ['N1', 'N2', 'N3'] or i in getattr(self.optimizer, 'integer_params', []):
                    f.write(f"  {name}: {int(self.best_parameters[i])}\n")
                elif name.startswith('V'):
                    f.write(f"  {name}: {self.best_parameters[i]:.3f} V\n")
                else:
                    f.write(f"  {name}: {self.best_parameters[i]:.6f}\n")
            
            f.write("\n")
            
            # 最佳实际电压配置
            f.write("【最佳实际电压配置】\n")
            f.write("-" * 40 + "\n")
            for i, voltage in enumerate(best_actual_voltages):
                if i in self.active_channels:
                    f.write(f"  V{i+1}: {voltage:.4f} V *\n")
                elif voltage != 0:
                    f.write(f"  V{i+1}: {voltage:.4f} V\n")
                # 对于未激活且为0的通道，不显示
            f.write("  (* 表示激活的优化通道)\n")
    
        print(f"优化摘要已保存: optimization_summary.txt")
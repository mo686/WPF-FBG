#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
根据CSV文件绘制插损图，并支持查看局部波长范围和局部损耗范围
"""

import csv
import matplotlib.pyplot as plt
import numpy as np
import os

class CSVPlotter:
    """CSV数据绘图类"""
    
    def __init__(self, csv_file_path):
        """初始化CSV绘图器"""
        self.csv_file_path = csv_file_path
        self.data = {}
        self.plot_figures = []
    
    def load_data(self):
        """加载CSV数据"""
        print(f"正在加载数据文件: {self.csv_file_path}")
        
        try:
            with open(self.csv_file_path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                next(reader)  # 跳过表头
                
                for row in reader:
                    if len(row) < 3:
                        continue
                    
                    voltage = float(row[0])
                    wavelength = float(row[1])
                    loss = float(row[2])
                    
                    if voltage not in self.data:
                        self.data[voltage] = {'wavelengths': [], 'losses': []}
                    
                    self.data[voltage]['wavelengths'].append(wavelength)
                    self.data[voltage]['losses'].append(loss)
            
            print(f"成功加载 {len(self.data)} 个电压点的数据")
            return True
        except Exception as e:
            print(f"加载数据失败: {e}")
            return False
    
    def plot_full_range(self):
        """绘制完整范围的插损图"""
        if not self.data:
            print("没有数据可绘制")
            return
        
        try:
            fig = plt.figure(figsize=(12, 8))
            self.plot_figures.append(fig)
            
            # 生成不同的颜色
            voltages = sorted(self.data.keys())
            colors = plt.cm.viridis(np.linspace(0, 1, len(voltages)))
            
            # 收集所有数据点，用于计算范围
            all_wavelengths = []
            all_losses = []
            
            for i, voltage in enumerate(voltages):
                wavelengths = self.data[voltage]['wavelengths']
                losses = self.data[voltage]['losses']
                
                # 收集数据点
                all_wavelengths.extend(wavelengths)
                all_losses.extend(losses)
                
                # 绘制曲线
                plt.plot(wavelengths, losses, 
                        color=colors[i],
                        linewidth=1.5,
                        label=f'{voltage:.3f}V')
                print(f"已添加电压 {voltage:.3f}V 的曲线")
            
            plt.xlabel('Wavelength [nm]')
            plt.ylabel('Insertion Loss [dB]')
            plt.title('Insertion Loss vs Wavelength')
            plt.grid(True, alpha=0.3)
            plt.legend()
            plt.tight_layout()
            plt.show(block=False)
            
            print("完整范围的插损图已绘制完成")
            return all_wavelengths, all_losses
        except Exception as e:
            print(f"绘制完整范围插损图时出错: {e}")
            return [], []
    
    def plot_local_range(self, all_wavelengths, all_losses):
        """绘制局部范围的插损图"""
        if not self.data or not all_wavelengths or not all_losses:
            print("没有数据可绘制")
            return
        
        try:
            # 获取波长范围
            min_wl = min(all_wavelengths)
            max_wl = max(all_wavelengths)
            start_wl = float(input(f"请输入起始波长 (nm) [{min_wl:.2f}-{max_wl:.2f}]: "))
            end_wl = float(input(f"请输入结束波长 (nm) [{min_wl:.2f}-{max_wl:.2f}]: "))
            
            # 获取损耗范围
            min_loss = min(all_losses)
            max_loss = max(all_losses)
            start_loss = float(input(f"请输入起始损耗 (dB) [{min_loss:.2f}-{max_loss:.2f}]: "))
            end_loss = float(input(f"请输入结束损耗 (dB) [{min_loss:.2f}-{max_loss:.2f}]: "))
            
            # 绘制局部范围插损图
            fig = plt.figure(figsize=(12, 8))
            self.plot_figures.append(fig)
            
            # 生成不同的颜色
            voltages = sorted(self.data.keys())
            colors = plt.cm.viridis(np.linspace(0, 1, len(voltages)))
            
            for i, voltage in enumerate(voltages):
                wavelengths = self.data[voltage]['wavelengths']
                losses = self.data[voltage]['losses']
                
                # 筛选波长和损耗范围内的数据
                filtered_wavelengths = []
                filtered_losses = []
                for wl, loss in zip(wavelengths, losses):
                    if start_wl <= wl <= end_wl and start_loss <= loss <= end_loss:
                        filtered_wavelengths.append(wl)
                        filtered_losses.append(loss)
                
                if filtered_wavelengths:
                    plt.plot(filtered_wavelengths, filtered_losses, 
                            color=colors[i],
                            linewidth=1.5,
                            label=f'{voltage:.3f}V')
            
            plt.xlabel('Wavelength [nm]')
            plt.ylabel('Insertion Loss [dB]')
            plt.title(f'Insertion Loss vs Wavelength (Wavelength: {start_wl:.2f}-{end_wl:.2f} nm, Loss: {start_loss:.2f}-{end_loss:.2f} dB)')
            plt.grid(True, alpha=0.3)
            plt.legend()
            plt.tight_layout()
            plt.show(block=False)
            
            print("局部范围的插损图已绘制完成")
        except ValueError:
            print("输入的数值无效")
        except (EOFError, KeyboardInterrupt):
            print("\n用户中断输入")
        except Exception as e:
            print(f"绘制局部范围插损图时出错: {e}")
    
    def run(self):
        """运行绘图流程"""
        # 加载数据
        if not self.load_data():
            return
        
        # 绘制完整范围的插损图
        all_wavelengths, all_losses = self.plot_full_range()
        
        # 询问是否查看局部范围
        try:
            zoom = input("是否需要查看局部波长范围和局部损耗范围的插损图? [y|n]: ").lower() == 'y'
            if zoom:
                self.plot_local_range(all_wavelengths, all_losses)
        except (EOFError, KeyboardInterrupt):
            print("\n用户中断输入")
        
        # 等待用户关闭图像
        try:
            input("按Enter键关闭所有图像...")
        except (EOFError, KeyboardInterrupt):
            pass
        
        # 关闭所有图像
        for fig in self.plot_figures:
            plt.close(fig)
        
        print("绘图完成")

def main():
    """主函数"""
    print("=== CSV数据绘图工具 ===")
    
    # 默认CSV文件路径
    default_csv_path = "c:\\Users\\Photonics\\Desktop\\zzx\\insertion_loss_data\\insertion_loss_20260315_210208.csv"
    
    # 询问用户是否使用默认文件路径
    use_default = input(f"是否使用默认CSV文件路径? [{default_csv_path}] (y/n): ").lower() == 'y'
    
    if use_default:
        csv_file_path = default_csv_path
    else:
        csv_file_path = input("请输入CSV文件路径: ")
    
    # 检查文件是否存在
    if not os.path.exists(csv_file_path):
        print(f"文件不存在: {csv_file_path}")
        return
    
    # 创建CSV绘图器并运行
    plotter = CSVPlotter(csv_file_path)
    plotter.run()

if __name__ == "__main__":
    main()
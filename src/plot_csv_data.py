#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
CSV数据绘制工具 - 读取并绘制CSV文件中的插损数据
"""

import os
import csv
import matplotlib.pyplot as plt
import numpy as np
from tkinter import Tk, filedialog

def plot_csv_data(csv_file):
    """读取CSV文件并绘制数据"""
    print(f"正在读取CSV文件: {csv_file}")
    
    # 读取CSV数据
    data = {}
    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            voltage = float(row['Voltage (V)'])
            wavelength = float(row['Wavelength (nm)'])
            insertion_loss = float(row['Insertion Loss (dB)'])
            
            if voltage not in data:
                data[voltage] = {'wavelengths': [], 'losses': []}
            data[voltage]['wavelengths'].append(wavelength)
            data[voltage]['losses'].append(insertion_loss)
    
    print(f"成功读取 {len(data)} 个电压点的数据")
    
    # 绘制汇总图
    fig = plt.figure(figsize=(12, 8))
    
    # 使用更明显的颜色区分不同电压
    colors = ['blue', 'green', 'red', 'orange', 'purple', 'brown', 'pink', 'gray', 'olive', 'cyan']
    
    # 对电压值进行排序
    sorted_voltages = sorted(data.keys())
    
    for i, voltage in enumerate(sorted_voltages):
        voltage_data = data[voltage]
        wavelengths = voltage_data['wavelengths']
        losses = voltage_data['losses']
        
        # 确保数据按波长排序
        sorted_indices = np.argsort(wavelengths)
        sorted_wavelengths = np.array(wavelengths)[sorted_indices]
        sorted_losses = np.array(losses)[sorted_indices]
        
        # 选择颜色
        color_index = i % len(colors)
        
        # 绘制曲线
        plt.plot(sorted_wavelengths, sorted_losses, 
                 color=colors[color_index],
                 linewidth=1.5,
                 label=f'{voltage:.3f}V')
        print(f"已添加电压 {voltage:.3f}V 的曲线")
    
    # 设置图表属性
    plt.xlabel('Wavelength [nm]')
    plt.ylabel('Insertion Loss [dB]')
    plt.title('Insertion Loss from CSV Data')
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()
    
    # 显示图表
    plt.show()

def select_csv_file():
    """打开文件选择对话框，选择CSV文件"""
    root = Tk()
    root.withdraw()  # 隐藏主窗口
    
    # 打开文件选择对话框
    file_path = filedialog.askopenfilename(
        title="选择CSV文件",
        filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        initialdir="c:\\Users\\Photonics\\Desktop\\zzx\\measurement_data"
    )
    
    return file_path

def main():
    """主函数"""
    print("=== CSV数据绘制工具 ===")
    
    # 选择CSV文件
    csv_file = select_csv_file()
    if not csv_file:
        print("未选择文件，退出程序")
        return
    
    # 绘制数据
    try:
        plot_csv_data(csv_file)
    except Exception as e:
        print(f"绘制数据时出错: {e}")

if __name__ == "__main__":
    main()
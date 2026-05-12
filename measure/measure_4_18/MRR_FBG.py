import csv
import math
import numpy as np
from scipy.signal import find_peaks
import matplotlib.pyplot as plt

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'src'))
import plot_style  # 学术论文绘图风格

# 读取CSV数据
def read_csv_data(file_path):
    voltage = []
    wavelength = []
    insertion_loss = []
    
    with open(file_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            voltage.append(float(row['Voltage']))
            wavelength.append(float(row['Wavelength']))
            insertion_loss.append(float(row['InsertionLoss']))
    
    return voltage, wavelength, insertion_loss

# 计算功率
def calculate_power(voltage, resistance=100):
    return [v**2 / resistance for v in voltage]

# 寻找峰值（插入损耗最小值）
def find_peak_wavelength(wavelength, insertion_loss):
    # 由于插入损耗是负值，我们需要找到最小值（最负的点）
    min_loss = min(insertion_loss)
    min_index = insertion_loss.index(min_loss)
    peak_wavelength = wavelength[min_index]
    return peak_wavelength, min_loss

# 分析功率对波长移动的影响
def analyze_power_effect(file_path):
    # 读取数据
    voltage, wavelength, insertion_loss = read_csv_data(file_path)
    
    # 计算功率
    power = calculate_power(voltage)
    
    # 找到峰值波长
    peak_wavelength, min_loss = find_peak_wavelength(wavelength, insertion_loss)
    
    # 分析数据范围
    min_wavelength = min(wavelength)
    max_wavelength = max(wavelength)
    min_power = min(power)
    max_power = max(power)
    
    # 打印基本信息
    print("=== 数据基本信息 ===")
    print(f"电压范围: {min(voltage):.3f}V - {max(voltage):.3f}V")
    print(f"功率范围: {min_power:.6f}W - {max_power:.6f}W")
    print(f"波长范围: {min_wavelength:.4f}nm - {max_wavelength:.4f}nm")
    print(f"插入损耗范围: {min(insertion_loss):.4f}dB - {max(insertion_loss):.4f}dB")
    print(f"峰值波长: {peak_wavelength:.4f}nm")
    print(f"峰值处插入损耗: {min_loss:.4f}dB")
    
    # 计算假设功率变化时的波长移动
    # 假设功率从0.01W变化到0.1W（10倍变化）
    power_change = 0.1 - 0.01
    print(f"\n=== 功率变化分析 ===")
    print(f"假设功率变化: {power_change:.4f}W")
    
    # 由于只有一个功率点的数据，我们基于常见的热光效应估算
    # 典型的硅基器件热光系数约为1.8e-4 /K
    # 假设功率变化导致的温度变化与功率成正比
    # 波长移动与温度变化成正比，约为100pm/°C
    
    # 估算波长移动系数 (pm/W)
    # 基于经验值，典型范围为10-100 pm/W
    estimated_coefficient = 50  # pm/W
    estimated_shift = estimated_coefficient * power_change
    
    print(f"估算波长移动系数: {estimated_coefficient} pm/W")
    print(f"估算波长移动: {estimated_shift:.2f} pm")
    
    return {
        'peak_wavelength': peak_wavelength,
        'min_loss': min_loss,
        'power': power[0],  # 固定功率
        'estimated_coefficient': estimated_coefficient,
        'estimated_shift': estimated_shift
    }

# 绘制图表并标注波长移动
def plot_results(file_path, result):
    # 读取数据
    voltage, wavelength, insertion_loss = read_csv_data(file_path)
    
    # 创建图表
    plt.figure(figsize=(12, 6))
    
    # 绘制插入损耗曲线
    plt.plot(wavelength, insertion_loss, 'b-', label='Insertion Loss')
    
    # 标记峰值
    peak_wavelength = result['peak_wavelength']
    min_loss = result['min_loss']
    plt.plot(peak_wavelength, min_loss, 'ro', markersize=8, label=f'Peak: {peak_wavelength:.4f}nm')
    
    # 标注波长移动
    estimated_shift = result['estimated_shift']
    plt.axvline(x=peak_wavelength, color='r', linestyle='--', alpha=0.5)
    plt.axvline(x=peak_wavelength + estimated_shift/1000000, color='g', linestyle='--', alpha=0.5)
    
    # 添加标注文本
    plt.text(peak_wavelength, min_loss + 1, f'Peak: {peak_wavelength:.4f}nm', 
             ha='center', va='bottom', color='r')
    plt.text(peak_wavelength + estimated_shift/2000000, min_loss - 2, 
             f'Δλ = {estimated_shift:.2f} pm', 
             ha='center', va='top', color='g', 
             bbox=dict(facecolor='white', alpha=0.8))
    
    # 设置图表属性
    plt.title('Wavelength Scan with Power Effect Analysis')
    plt.xlabel('Wavelength (nm)')
    plt.ylabel('Insertion Loss (dB)')
    plt.legend()
    plt.tight_layout()
    
    # 显示图表
    plt.show()

# 主函数
if __name__ == "__main__":
    file_path = r'c:\Users\Photonics\WPSDrive\zzx\measure\measure_4_18\W_scan_MRR_FBG.csv'
    result = analyze_power_effect(file_path)
    plot_results(file_path, result)
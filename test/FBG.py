import json
import numpy as np
import matplotlib.pyplot as plt

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
import plot_style  # 学术论文绘图风格

def load_spectrum(file_path):
    """加载 JSON 文件，返回波长数组和功率数组"""
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    # 假设 JSON 是列表形式，第一个元素包含数据
    # 根据实际情况调整路径，也可能 data 直接是字典
    if isinstance(data, list):
        record = data[0]
    else:
        record = data
    wavelengths = np.array(record['rescaled_wavelength'])
    powers = np.array(record['rescaled_reference_power'])
    return wavelengths, powers

def find_center_wavelength(wavelengths, powers, method='max'):
    """
    计算 FBG 中心波长。
    method: 'max' 直接取功率最大值对应的波长
            'centroid' 质心法（可选）
    """
    if method == 'max':
        idx = np.argmax(powers)
        center_wl = wavelengths[idx]
    elif method == 'centroid':
        # 质心法，以功率为权重
        center_wl = np.sum(wavelengths * powers) / np.sum(powers)
    else:
        raise ValueError("method must be 'max' or 'centroid'")
    return center_wl

def plot_spectrums(wl1, power1, center1, wl2, power2, center2, label1='FBG_55', label2='FBG_30'):
    """绘制两个FBG的光谱图，标记中心波长"""
    plt.figure(figsize=(12, 6))
    
    # 绘制FBG_55的光谱
    plt.plot(wl1, power1, label=label1, linewidth=1.5)
    # 标记FBG_55的中心波长
    plt.axvline(x=center1, color='blue', linestyle='--', alpha=0.7, label=f'{label1} center: {center1:.5f} nm')
    
    # 绘制FBG_30的光谱
    plt.plot(wl2, power2, label=label2, linewidth=1.5)
    # 标记FBG_30的中心波长
    plt.axvline(x=center2, color='red', linestyle='--', alpha=0.7, label=f'{label2} center: {center2:.5f} nm')
    
    # 设置图表属性
    plt.xlabel('Wavelength (nm)')
    plt.ylabel('Loss (dB)')
    plt.legend()
    plt.tight_layout()
    plt.show()

def main():
    file1 = "measure/measure_4_20/FBG_55_1h.json"
    file2 = "measure/measure_4_20/FBG_30_3h.json"
    
    # 从文件名提取标签
    import re
    label1 = re.search(r'(FBG_\d+)', os.path.basename(file1)).group(1)
    label2 = re.search(r'(FBG_\d+)', os.path.basename(file2)).group(1)
    
    # 加载数据
    wl1, power1 = load_spectrum(file1)
    wl2, power2 = load_spectrum(file2)
    
    # 计算中心波长（使用最大值法，也可改为 centroid）
    center1 = find_center_wavelength(wl1, power1, method='max')
    center2 = find_center_wavelength(wl2, power2, method='max')
    
    # 波长移动 (单位：纳米 → 皮米)
    delta_pm = (center2 - center1) * 1e3
    
    print(f"{label1} 中心波长: {center1:.6f} nm")
    print(f"{label2} 中心波长: {center2:.6f} nm")
    print(f"波长移动 ({label2} - {label1}): {delta_pm:.2f} pm")
    
    # 可选：输出移动方向
    if delta_pm > 0:
        print("波长向长波方向移动（红移）")
    elif delta_pm < 0:
        print("波长向短波方向移动（蓝移）")
    else:
        print("波长未移动")
    
    # 绘制光谱图
    plot_spectrums(wl1, power1, center1, wl2, power2, center2, label1, label2)

if __name__ == "__main__":
    main()
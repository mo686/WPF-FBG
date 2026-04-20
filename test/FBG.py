import json
import numpy as np
import matplotlib.pyplot as plt

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

def plot_spectrums(wl1, power1, center1, wl2, power2, center2):
    """绘制两个FBG的光谱图，标记中心波长"""
    plt.figure(figsize=(12, 6))
    
    # 绘制FBG_20的光谱
    plt.plot(wl1, power1, label='FBG_20', linewidth=1.5)
    # 标记FBG_20的中心波长
    plt.axvline(x=center1, color='blue', linestyle='--', alpha=0.7, label=f'FBG_20中心波长: {center1:.6f} nm')
    
    # 绘制FBG_25的光谱
    plt.plot(wl2, power2, label='FBG_25', linewidth=1.5)
    # 标记FBG_25的中心波长
    plt.axvline(x=center2, color='red', linestyle='--', alpha=0.7, label=f'FBG_25中心波长: {center2:.6f} nm')
    
    # 设置图表属性
    plt.title('FBG光谱对比图')
    plt.xlabel('波长 (nm)')
    plt.ylabel('功率 (dBm)')
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.show()

def main():
    file1 = "measure/measure_4_20/FBG_55_1h.json"
    file2 = "measure/measure_4_20/FBG_30_3h.json"
    
    # 加载数据
    wl1, power1 = load_spectrum(file1)
    wl2, power2 = load_spectrum(file2)
    
    # 计算中心波长（使用最大值法，也可改为 centroid）
    center1 = find_center_wavelength(wl1, power1, method='max')
    center2 = find_center_wavelength(wl2, power2, method='max')
    
    # 波长移动 (单位：米 → 皮米)
    delta_pm = (center2 - center1) * 1e12
    
    print(f"FBG_20 中心波长: {center1:.6f} nm")
    print(f"FBG_25 中心波长: {center2:.6f} nm")
    print(f"波长移动 (25 - 20): {delta_pm:.2f} pm")
    
    # 可选：输出移动方向
    if delta_pm > 0:
        print("波长向长波方向移动（红移）")
    elif delta_pm < 0:
        print("波长向短波方向移动（蓝移）")
    else:
        print("波长未移动")
    
    # 绘制光谱图
    plot_spectrums(wl1, power1, center1, wl2, power2, center2)

if __name__ == "__main__":
    main()
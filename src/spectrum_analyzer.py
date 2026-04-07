import numpy as np
from scipy import signal
from scipy.ndimage import gaussian_filter1d
from typing import Tuple, Dict, List, Optional, Union

def smooth_spectrum(wavelengths: np.ndarray, power_data: np.ndarray, 
                    sigma: float = 1.0) -> np.ndarray:
    """
    高斯平滑光谱数据
    """
    return gaussian_filter1d(power_data, sigma=sigma)

def find_peaks(wavelengths: np.ndarray, power_data: np.ndarray,
               height_percentile: float = 70,
               min_distance_ratio: float = 0.05,
               prominence: float = 1.0) -> Tuple[np.ndarray, np.ndarray, dict]:
    """
    查找光谱峰值
    
    返回:
        peak_indices: 峰值索引
        peak_wavelengths: 峰值波长
        properties: 峰值属性
    """
    # 平滑处理
    smoothed = gaussian_filter1d(power_data, sigma=1.0)
    
    # 设置参数
    height_threshold = np.percentile(smoothed, height_percentile)
    min_distance = max(1, int(len(wavelengths) * min_distance_ratio))
    
    # 找峰
    peaks, properties = signal.find_peaks(
        smoothed,
        height=height_threshold,
        distance=min_distance,
        prominence=prominence,
        width=1
    )
    
    return peaks, wavelengths[peaks], properties

def find_valleys(wavelengths: np.ndarray, power_data: np.ndarray,
                 height_percentile: float = 30,
                 min_distance_ratio: float = 0.05) -> Tuple[np.ndarray, np.ndarray]:
    """
    查找光谱谷值
    """
    smoothed = gaussian_filter1d(power_data, sigma=1.0)
    height_threshold = np.percentile(smoothed, height_percentile)
    min_distance = max(1, int(len(wavelengths) * min_distance_ratio))
    
    valleys, _ = signal.find_peaks(
        -smoothed,
        height=-height_threshold,
        distance=min_distance
    )
    
    return valleys, wavelengths[valleys]

def basic_stats(power_data: np.ndarray) -> Dict[str, float]:
    """
    基本统计指标
    """
    return {
        'min': float(np.min(power_data)),
        'max': float(np.max(power_data)),
        'mean': float(np.mean(power_data)),
        'std': float(np.std(power_data)),
        'peak_to_peak': float(np.max(power_data) - np.min(power_data))
    }

def insertion_loss(power_data: np.ndarray, method: str = 'peak') -> float:
    """
    计算插损
    
    参数:
        power_data: 功率数据 (dB)
        method: 'peak', 'mean', 'min'
    """
    if method == 'peak':
        return float(np.max(power_data))
    elif method == 'mean':
        return float(np.mean(power_data))
    elif method == 'min':
        return float(np.min(power_data))
    else:
        raise ValueError(f"Unknown method: {method}")

def extinction_ratio(wavelengths: np.ndarray, power_data: np.ndarray,
                     method: str = 'peak_to_peak') -> float:
    """
    计算消光比
    
    参数:
        method: 'peak_to_peak' (全局峰峰值)
                'adjacent_peaks' (相邻峰谷值)
                'peak_to_valley' (最高峰到最近谷值)
    """
    if method == 'peak_to_peak':
        return float(np.max(power_data) - np.min(power_data))
    
    elif method == 'adjacent_peaks':
        peaks, peak_wls, _ = find_peaks(wavelengths, power_data)
        if len(peaks) < 2:
            return 0.0
        
        extinctions = []
        for i, peak_idx in enumerate(peaks):
            peak_val = power_data[peak_idx]
            
            # 找左侧谷值
            if i > 0:
                valley_idx = np.argmin(power_data[peaks[i-1]:peak_idx]) + peaks[i-1]
                extinctions.append(peak_val - power_data[valley_idx])
            
            # 找右侧谷值
            if i < len(peaks) - 1:
                valley_idx = np.argmin(power_data[peak_idx:peaks[i+1]]) + peak_idx
                extinctions.append(peak_val - power_data[valley_idx])
        
        return float(np.mean(extinctions)) if extinctions else 0.0
    
    elif method == 'peak_to_valley':
        peaks, _, _ = find_peaks(wavelengths, power_data)
        if len(peaks) == 0:
            return 0.0
        
        # 最高峰
        main_peak = peaks[np.argmax(power_data[peaks])]
        peak_val = power_data[main_peak]
        
        # 找最近的谷值
        valleys, _ = find_valleys(wavelengths, power_data)
        if len(valleys) == 0:
            return peak_val - np.min(power_data)
        
        # 找最近的谷值
        nearest_valley = valleys[np.argmin(np.abs(valleys - main_peak))]
        return float(peak_val - power_data[nearest_valley])
    
    else:
        raise ValueError(f"Unknown method: {method}")

def free_spectral_range(wavelengths: np.ndarray, power_data: np.ndarray,
                        return_all: bool = False,
                        use_peaks: bool = True) -> Union[float, Dict[str, float]]:
    """
    计算自由光谱范围(FSR)
    
    参数:
        wavelengths: 波长数组
        power_data: 功率数据
        return_all: 是否返回所有统计信息
        use_peaks: True使用峰值计算FSR，False使用谷值计算FSR
    """
    if use_peaks:
        # 使用峰值计算FSR
        peak_indices, peak_wls, _ = find_peaks(wavelengths, power_data)
        points = peak_wls
        point_type = 'peak'
    else:
        # 使用谷值计算FSR
        valley_indices, valley_wls = find_valleys(wavelengths, power_data)
        points = valley_wls
        point_type = 'valley'
    
    if len(points) < 2:
        if return_all:
            return {
                'fsr_mean': 0.0,
                'fsr_std': 0.0,
                'fsr_min': 0.0,
                'fsr_max': 0.0,
                'fsr_uniformity': 1.0,
                'n_points': len(points),
                'point_type': point_type
            }
        return 0.0
    
    fsrs = np.diff(points)
    fsr_mean = float(np.mean(fsrs))
    
    if not return_all:
        return fsr_mean
    
    fsr_std = float(np.std(fsrs))
    return {
        'fsr_mean': fsr_mean,
        'fsr_std': fsr_std,
        'fsr_min': float(np.min(fsrs)),
        'fsr_max': float(np.max(fsrs)),
        'fsr_uniformity': float(fsr_std / fsr_mean) if fsr_mean > 0 else 1.0,
        'n_points': len(points),
        'point_type': point_type,
        'wavelengths': points.tolist()
    }

def fwhm(wavelengths: np.ndarray, power_data: np.ndarray,
         peak_idx: Optional[int] = None,
         db_level: float = 3.0,
         min_er: float = 3.0) -> Dict[str, float]:
    """
    计算带宽(FWHM)
    
    参数:
        wavelengths: 波长数组
        power_data: 功率数据 (dB单位)
        peak_idx: 指定峰索引，None则返回第一个满足消光比要求的峰的FWHM
        db_level: 带宽计算的电平值，默认3dB
        min_er: 最小消光比要求，默认3dB
    
    返回:
        dict: 包含以下字段
            - fwhm: 带宽值
            - center_wavelength: 中心波长
            - peak_value: 峰值功率
            - er_satisfied: 是否满足消光比要求
            - note: 备注信息
    """
    # 1. 查找所有峰值和谷值
    peaks, _, _ = find_peaks(wavelengths, power_data)
    valleys, _ = find_valleys(wavelengths, power_data)
    
    if len(peaks) == 0 or len(valleys) < 2:
        return {
            'fwhm': 0.0,
            'center_wavelength': 0.0,
            'peak_value': 0.0,
            'er_satisfied': False,
            'note': 'Insufficient peaks or valleys'
        }
    
    # 2. 计算所有峰谷间的消光比
    peak_valley_pairs = []
    
    for peak in peaks:
        # 找到左侧最近的谷值
        left_valleys = valleys[valleys < peak]
        if len(left_valleys) > 0:
            left_valley = left_valleys[-1]
            left_er = power_data[peak] - power_data[left_valley]
        else:
            continue
        
        # 找到右侧最近的谷值
        right_valleys = valleys[valleys > peak]
        if len(right_valleys) > 0:
            right_valley = right_valleys[0]
            right_er = power_data[peak] - power_data[right_valley]
        else:
            continue
        
        # 检查是否满足消光比要求
        er_satisfied = (left_er >= min_er) and (right_er >= min_er)
        
        peak_valley_pairs.append({
            'peak_idx': peak,
            'peak_wl': wavelengths[peak],
            'peak_value': power_data[peak],
            'left_valley_idx': left_valley,
            'left_valley_wl': wavelengths[left_valley],
            'right_valley_idx': right_valley,
            'right_valley_wl': wavelengths[right_valley],
            'left_er': left_er,
            'right_er': right_er,
            'er_satisfied': er_satisfied
        })
    
    # 3. 计算FSR作为默认值
    fsr_result = free_spectral_range(wavelengths, power_data, return_all=True, use_peaks=True)
    fsr_mean = fsr_result['fsr_mean']
    
    # 4. 根据peak_idx参数选择峰值
    if peak_idx is not None:
        # 返回指定峰的结果
        selected = None
        for pair in peak_valley_pairs:
            if pair['peak_idx'] == peak_idx:
                selected = pair
                break
        
        if selected is None:
            # 没找到指定峰，找最近的
            peak_wls = [p['peak_wl'] for p in peak_valley_pairs]
            nearest_idx = np.argmin(np.abs(peak_wls - wavelengths[peak_idx]))
            selected = peak_valley_pairs[nearest_idx]
    
    elif len(peak_valley_pairs) == 0:
        # 没有满足基本条件的峰谷对
        return {
            'fwhm': float(fsr_mean),
            'center_wavelength': 0.0,
            'peak_value': 0.0,
            'er_satisfied': False,
            'note': f'No valid peak-valley pairs, FWHM set to FSR ({fsr_mean:.3f})'
        }
    
    else:
        # 返回第一个满足消光比要求的峰，如果没有则返回第一个峰
        satisfied_pairs = [p for p in peak_valley_pairs if p['er_satisfied']]
        if satisfied_pairs:
            selected = satisfied_pairs[0]
        else:
            selected = peak_valley_pairs[0]
            return {
                'fwhm': float(fsr_mean),
                'center_wavelength': float(selected['peak_wl']),
                'peak_value': float(selected['peak_value']),
                'er_satisfied': False,
                'note': f'No peak satisfies ER>{min_er}dB, FWHM set to FSR ({fsr_mean:.3f})'
            }
    
    # 5. 如果选择的峰不满足消光比要求，返回FSR
    if not selected['er_satisfied']:
        return {
            'fwhm': float(fsr_mean),
            'center_wavelength': float(selected['peak_wl']),
            'peak_value': float(selected['peak_value']),
            'er_satisfied': False,
            'note': f'ER not satisfied, FWHM set to FSR ({fsr_mean:.3f})'
        }
    
    # 6. 计算-3dB点
    threshold = selected['peak_value'] - db_level
    
    # 左侧找-3dB点：从peak_idx向左搜索，找第一个低于阈值的点
    left_idx = selected['peak_idx']
    while left_idx > selected['left_valley_idx'] and power_data[left_idx] > threshold:
        left_idx -= 1
    
    if left_idx > selected['left_valley_idx'] and left_idx < selected['peak_idx']:
        # 找到交叉点，进行插值
        if left_idx > 0:
            x1, x2 = wavelengths[left_idx], wavelengths[left_idx + 1]
            y1, y2 = power_data[left_idx], power_data[left_idx + 1]
            if y1 <= threshold <= y2:
                left_db = x1 + (threshold - y1) * (x2 - x1) / (y2 - y1)
            else:
                left_db = wavelengths[left_idx]
        else:
            left_db = wavelengths[left_idx]
    else:
        # 没找到，用左侧谷值
        left_db = selected['left_valley_wl']
    
    # 右侧找-3dB点：从peak_idx向右搜索，找第一个低于阈值的点
    right_idx = selected['peak_idx']
    while right_idx < selected['right_valley_idx'] and power_data[right_idx] > threshold:
        right_idx += 1
    
    if right_idx < selected['right_valley_idx'] and right_idx > selected['peak_idx']:
        # 找到交叉点，进行插值
        if right_idx < len(wavelengths) - 1:
            x1, x2 = wavelengths[right_idx - 1], wavelengths[right_idx]
            y1, y2 = power_data[right_idx - 1], power_data[right_idx]
            if y1 >= threshold >= y2:
                right_db = x1 + (threshold - y1) * (x2 - x1) / (y2 - y1)
            else:
                right_db = wavelengths[right_idx]
        else:
            right_db = wavelengths[right_idx]
    else:
        # 没找到，用右侧谷值
        right_db = selected['right_valley_wl']
    
    # 7. 计算FWHM
    if left_db >= right_db:
        fwhm = fsr_mean
        center_wl = selected['peak_wl']
        note = f'Invalid boundaries, FWHM set to FSR ({fsr_mean:.3f})'
    else:
        fwhm = right_db - left_db
        center_wl = (left_db + right_db) / 2
        note = f'Valid FWHM calculated from peak at {selected["peak_wl"]:.3f}nm'
    
    return {
        'fwhm': float(fwhm),
        'center_wavelength': float(center_wl),
        'peak_value': float(selected['peak_value']),
        'er_satisfied': selected['er_satisfied'],
        'note': note
    }

# def finesse(wavelengths: np.ndarray, power_data: np.ndarray) -> float:
#     """
#     计算精细度 (FSR/FWHM)
#     """
#     fsr_val = free_spectral_range(wavelengths, power_data)
#     fwhm_val = fwhm(wavelengths, power_data)['fwhm']
    
#     if fsr_val > 0 and fwhm_val > 0:
#         return float(fsr_val / fwhm_val)
#     return 0.0
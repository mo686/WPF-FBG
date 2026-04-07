#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
目标函数管理器类
提供多种基于光谱的目标函数供用户选择
"""

import numpy as np
from scipy import signal
from scipy.interpolate import interp1d
from base_function_manager import BaseFunctionManager  # 导入基类
import spectrum_analyzer as sa

class SpectralFunctions(BaseFunctionManager):
    """
    基于光谱的目标函数管理器类
    管理需要完整光谱数据的目标函数
    """

    def __init__(self, ilsts, voltage_controller):
        """
        初始化目标函数管理器
        
        参数:
            ilsts: StsProcess实例
            voltage_controller: 电压控制器实例
            auto_update_comprehensive: 是否自动通过静态分析更新元数据
        """
        # 调用父类初始化
        super().__init__(ilsts, voltage_controller)
    
    ### 用于优化的目标函数
    def spectral_smoothness(self, voltages,
                            channels = [1],
                            lambda_range = (1552, 1558),
                            target_IL = -15.0
                            ):
        """
        Spectral Smoothness - 优化平滑光谱的平稳度和目标插损
        参数:
            voltages: 电压数组
            target_loss: 目标插损(dB)
            channels: 目标通道列表
        返回:
            dict: 包含测量结果的字典
        """
        # 设置电压
        if not self._set_voltages_and_wait(voltages):
            print("设置电压失败，返回较大的惩罚值")
            return self.get_error_output()
        
        try:
            # 获取光谱数据（使用基类方法）
            wavelengths, channel_powers = self._get_spectrum_data(channels)
            
            # 计算目标函数
            fom_total = 0.0
            result_details = {}
            
            for ch, power_data in zip(channels, channel_powers):
                # 筛选在lambda_range范围内的数据
                mask = (wavelengths >= lambda_range[0]) & (wavelengths <= lambda_range[1])
                wavelengths_filtered = wavelengths[mask]
                power_data_filtered = power_data[mask]
                
                # 检查是否有有效数据
                if len(power_data_filtered) == 0:
                    print(f"警告: 通道{ch}在波长范围{lambda_range}内没有数据")
                    # 返回较大的惩罚值
                    ch_fom = 1000.0
                    avg_loss = 0.0
                    smoothness = 1000.0
                    loss_error = 1000.0
                else:
                    # 计算平均插损
                    avg_loss = np.mean(power_data_filtered)
                    # 计算光谱平稳度（标准差）
                    smoothness = np.std(power_data_filtered)
                    # 计算与目标插损的差异
                    loss_error = abs(avg_loss - target_IL)
                    # 综合目标函数
                    ch_fom = smoothness
                
                fom_total += ch_fom
                
                # 保存详细结果
                result_details[f'ch{ch}_loss'] = avg_loss
                result_details[f'ch{ch}_smooth'] = smoothness
                result_details[f'ch{ch}_loss_error'] = loss_error
            
            # 创建结果字典
            result = {
                'voltages': voltages.copy(),
                'fom': fom_total
            }
            result.update(result_details)
            
            # 使用基类的格式化输出
            return self._format_result_output(result, "光谱平稳度优化")
            
        except Exception as e:
            print(f"测量过程中出错: {e}")
            import traceback
            traceback.print_exc()
            return self.get_error_output()
        
    def bmzi_search(self, voltages,
                    channels = [1,2],
                    lambda_range = (1630, 1634),
                    target_IL = 6.0,
                    target_CT = 30.0
                    ):
        """
        BMZI Search - 平衡MZI功能重构
        参数:
            voltages: 电压数组
            target_loss: 目标插损(dB)
            channels: 目标通道列表
        返回:
            dict: 包含测量结果的字典
        """
        # 设置电压
        if not self._set_voltages_and_wait(voltages):
            print("设置电压失败，返回较大的惩罚值")
            return self.get_error_output()
        
        try:
            # 获取光谱数据（使用基类方法）
            wavelengths, channel_powers = self._get_spectrum_data(channels)
            
            # 计算目标函数
            fom_total = 0.0
            result_details = {}
            
            for ch, power_data in zip(channels, channel_powers):
                # 筛选在lambda_range范围内的数据
                mask = (wavelengths >= lambda_range[0]) & (wavelengths <= lambda_range[1])
                wavelengths_filtered = wavelengths[mask]
                power_data_filtered = power_data[mask]
                
                # 检查是否有有效数据
                if len(power_data_filtered) == 0:
                    print(f"警告: 通道{ch}在波长范围{lambda_range}内没有数据")
                    # 返回较大的惩罚值
                    avg_loss = -110.0
                    smoothness = 1000.0
                    loss_error = 1000.0
                else:
                    # 计算平均插损
                    avg_loss = np.mean(power_data_filtered)
                    # 计算光谱平稳度（标准差）
                    smoothness = np.std(power_data_filtered)
                
                # 保存详细结果
                result_details[f'ch{ch}_loss'] = avg_loss
                result_details[f'ch{ch}_smooth'] = smoothness
            
            crosstalk = target_CT/abs(result_details['ch1_loss'] - result_details['ch2_loss'])
            insertion_loss = abs(result_details['ch2_loss']/target_IL)
            fom_total = insertion_loss + crosstalk
            # 创建结果字典
            result = {
                'voltages': voltages.copy(),
                'fom': fom_total
            }
            result.update(result_details)
            
            # 使用基类的格式化输出
            return self._format_result_output(result, "BMZI光谱找寻")
            
        except Exception as e:
            print(f"测量过程中出错: {e}")
            import traceback
            traceback.print_exc()
            return self.get_error_output()
        
    def umzi_search(self, voltages,
                    channels = [1,2],
                    lambda_range = (1630, 1634)
                    ):
        """
        UMZI Search - 非平衡MZI功能重构（大消光比、双通道均匀）
        参数:
            voltages: 电压数组
            target_loss: 目标插损(dB)
            channels: 目标通道列表
        返回:
            dict: 包含测量结果的字典
        """
        # 设置电压
        if not self._set_voltages_and_wait(voltages):
            print("设置电压失败，返回较大的惩罚值")
            return self.get_error_output()
        
        try:
            # 获取光谱数据（使用基类方法）
            wavelengths, channel_powers = self._get_spectrum_data(channels)
            
            # 计算目标函数
            fom_total = 0.0
            result_details = {}
            
            mask = (wavelengths >= lambda_range[0]) & (wavelengths <= lambda_range[1])
            wavelengths_filtered = wavelengths[mask]
            power_data_ch1 = channel_powers[0][mask]
            power_data_ch2 = channel_powers[1][mask]

            from scipy.ndimage import gaussian_filter1d

            # ============ 使用find_peaks的光谱分析函数 ============
            def analyze_spectrum_with_peaks(wavelengths, power_data, 
                                            min_peak_height=None, min_distance=None):
                """
                使用find_peaks分析光谱
                返回: (loss, extinction, fsr, fwhm, finesse, n_peaks)
                """
                # 1. 基本统计
                loss = np.mean(power_data)
                extinction = np.max(power_data) - np.min(power_data)
                
                # 2. 平滑光谱以便更好地找峰
                smoothed = gaussian_filter1d(power_data, sigma=1)
                
                # 3. 设置find_peaks参数
                if min_peak_height is None:
                    # 动态阈值：高于平均值的峰
                    min_peak_height = np.percentile(smoothed, 70)
                
                if min_distance is None:
                    # 最小峰间距：总长度的5%
                    min_distance = max(1, len(wavelengths) // 20)
                
                # 4. 使用find_peaks查找峰值
                peaks, properties = signal.find_peaks(
                    smoothed,
                    height = min_peak_height,
                    distance = min_distance,
                    prominence = 1.0,  # 最小 prominence，避免小波动
                    width = 1  # 最小宽度
                )
                
                n_peaks = len(peaks)
                
                # 默认值
                fsr = 0
                fwhm = 0
                finesse = 0
                
                # 5. 如果有足够的峰，计算FSR和FWHM
                if n_peaks >= 2:
                    # 计算FSR（平均峰间距）
                    peak_wavelengths = wavelengths[peaks]
                    fsrs = np.diff(peak_wavelengths)
                    fsr = np.mean(fsrs)
                    fsr_std = np.std(fsrs)
                    fsr_uniformity = fsr_std / fsr if fsr > 0 else 0
                    
                    # 找主峰（最高的峰）计算FWHM
                    main_peak_idx = peaks[np.argmax(power_data[peaks])]
                    main_peak_value = power_data[main_peak_idx]
                    half_max = main_peak_value - 3
                    
                    # 使用find_peaks的width属性也可以计算FWHM
                    # 但为了精确，我们手动计算
                    left_idx = main_peak_idx
                    while left_idx > 0 and power_data[left_idx] > half_max:
                        left_idx -= 1
                    
                    right_idx = main_peak_idx
                    while right_idx < len(power_data)-1 and power_data[right_idx] > half_max:
                        right_idx += 1
                    
                    if left_idx < main_peak_idx and right_idx > main_peak_idx:
                        fwhm = wavelengths[right_idx] - wavelengths[left_idx]
                        if fwhm > 0:
                            finesse = fsr / fwhm
                else:
                    fsr_uniformity = 1.0
                
                # print(f"{channel_name}: 损耗={loss:.2f}dB, 消光比={extinction:.2f}dB, "
                #     f"FSR={fsr:.3f}nm, FWHM={fwhm:.3f}nm, 精细度={finesse:.2f}, 峰数={n_peaks}")
                
                return loss, extinction, fsr, fwhm, finesse

            # 通道1分析
            loss1, ext1, fsr1, fwhm1, fine1 = analyze_spectrum_with_peaks(
                wavelengths_filtered, power_data_ch1
            )
            result_details["ch1_loss"] = loss1
            result_details["ch1_ext"] = ext1
            result_details["ch1_fine"] = fine1

            # 通道2分析
            loss2, ext2, fsr2, fwhm2, fine2 = analyze_spectrum_with_peaks(
                wavelengths_filtered, power_data_ch2
            )
            result_details["ch2_loss"] = loss2
            result_details["ch2_ext"] = ext2
            result_details["ch2_fine"] = fine2

            # 双通道一致性
            loss_diff = abs(loss1 / loss2)
            ext_diff = abs(ext1 / ext2)
            fine_diff = abs(fine1 - fine2)

            # 理想性能指标
            target_loss = 6
            target_er = 20
            target_finesse = 2

            fom_total = fom_total = abs(loss1/target_loss) + abs(target_er/ext1) + abs(target_finesse-fine1) + loss_diff + ext_diff + fine_diff
            # 创建结果字典
            result = {
                'voltages': voltages.copy(),
                'fom': fom_total
            }
            result.update(result_details)
            
            # 使用基类的格式化输出
            return self._format_result_output(result, "UMZI光谱找寻")
            
        except Exception as e:
            print(f"测量过程中出错: {e}")
            import traceback
            traceback.print_exc()
            return self.get_error_output()
        
    def allpass_ring_thru(self, voltages,
                        channels = [1],
                        lambda_range = (1554, 1555)
                        ):
        """
        AllPass Ring Through Port - 全通型微环的直通光谱
        参数:
            voltages: 电压数组
            target_loss: 目标插损(dB)
            channels: 目标通道列表
        返回:
            dict: 包含测量结果的字典
        """
        # 设置电压
        if not self._set_voltages_and_wait(voltages):
            print("设置电压失败，返回较大的惩罚值")
            return self.get_error_output()
        
        try:
            # 获取光谱数据（使用基类方法）
            wavelengths, channel_powers = self._get_spectrum_data(channels)
            
            # 计算目标函数
            fom_total = 0.0
            result_details = {}
            
            mask = (wavelengths >= lambda_range[0]) & (wavelengths <= lambda_range[1])
            wavelengths_filtered = wavelengths[mask]
            power_data_ch1 = channel_powers[0][mask]

            # 1. 插入损耗（背景损耗）
            il = sa.insertion_loss(power_data_ch1, method='peak')
            
            # 2. 消光比（谐振深度）
            ext = sa.extinction_ratio(wavelengths_filtered, power_data_ch1, method='peak_to_peak')
            
            # 3. 峰值精细度 F = FSR/峰值FWHM
            fsr = sa.free_spectral_range(wavelengths_filtered, power_data_ch1, use_peaks=False)
            fwhm = sa.fwhm(wavelengths_filtered, power_data_ch1)['fwhm']
            peak_finesse = fsr / max(fwhm, 1e-5)
            
            # 4. 谷值精细度 = 1/(1 - 1/peak_finesse) = FSR/谷值3dB
            if peak_finesse > 1:
                valley_finesse = 1/(1 - 1/peak_finesse)
            else:
                valley_finesse = 0
                print("警告：峰值精细度异常")
            
            # 保存结果
            result_details = {
                "insertion_loss": float(il),
                "extinction_ratio": float(ext),
                "free_spectral_range": float(fsr),
                "fwhm": float(fsr - fwhm),
                "valley_finesse": float(valley_finesse)
            }

            target_il = -7.0
            target_ext = 20
            target_fine = 5

            fom_total = (target_il-il)**2 + (target_ext-ext)**2
            # 创建结果字典
            result = {
                'voltages': voltages.copy(),
                'fom': fom_total
            }
            result.update(result_details)
            
            # 使用基类的格式化输出
            return self._format_result_output(result, "全通微环光谱搜索")
            
        except Exception as e:
            print(f"测量过程中出错: {e}")
            import traceback
            traceback.print_exc()
            return self.get_error_output()

    def adddrop_ring_drop(self, voltages,
                        channels = [2],
                        lambda_range = (1554, 1555),
                        target_il = -7.5,
                        target_ext = 8
                        ):
        """
        AddDrp Ring Drop Port - 全通型微环的直通光谱
        参数:
            voltages: 电压数组
            target_loss: 目标插损(dB)
            channels: 目标通道列表
        返回:
            dict: 包含测量结果的字典
        """
        # 设置电压
        if not self._set_voltages_and_wait(voltages):
            print("设置电压失败，返回较大的惩罚值")
            return self.get_error_output()
        
        try:
            # 获取光谱数据（使用基类方法）
            wavelengths, channel_powers = self._get_spectrum_data(channels)
            
            # 计算目标函数
            fom_total = 0.0
            result_details = {}
            
            mask = (wavelengths >= lambda_range[0]) & (wavelengths <= lambda_range[1])
            wavelengths_filtered = wavelengths[mask]
            power_data_ch1 = channel_powers[0][mask]

            # 1. 插入损耗（背景损耗）
            il = sa.insertion_loss(power_data_ch1, method='peak')
            
            # 2. 消光比（谐振深度）
            ext = sa.extinction_ratio(wavelengths_filtered, power_data_ch1, method='peak_to_peak')
            
            # 3. 峰值精细度 F = FSR/峰值FWHM
            fsr = sa.free_spectral_range(wavelengths_filtered, power_data_ch1, use_peaks=False)
            fwhm = sa.fwhm(wavelengths_filtered, power_data_ch1)['fwhm']
            
            # 保存结果
            result_details = {
                "insertion_loss": float(il),
                "extinction_ratio": float(ext),
                "free_spectral_range": float(fsr),
                "fwhm": float(fwhm),
            }

            fom_total = (target_il-il)**2 + (target_ext-ext)**2
            # 创建结果字典
            result = {
                'voltages': voltages.copy(),
                'fom': fom_total
            }
            result.update(result_details)
            
            # 使用基类的格式化输出
            return self._format_result_output(result, "上传下载微环光谱搜索")
            
        except Exception as e:
            print(f"测量过程中出错: {e}")
            import traceback
            traceback.print_exc()
            return self.get_error_output()
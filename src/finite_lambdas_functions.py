#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
有限波长数的目标函数管理器
提供多种只使用一个或几个波长处光功率而无需知道完整光谱的目标函数
"""

from base_function_manager import BaseFunctionManager  # 导入基类

class FiniteLambdaFunctions(BaseFunctionManager):
    """
    有限波长数的目标函数管理器类
    管理只使用一个或几个波长处光功率而无需知道完整光谱的目标函数
    """

    def __init__(self, ilsts, voltage_controller):
        """
        初始化目标函数管理器
        
        参数:
            ilsts: StsProcess实例
            voltage_controller: 电压控制器实例
        """
        # 调用父类初始化
        super().__init__(ilsts, voltage_controller)
    
    def _calculate_target_value(self, power, target, target_min=-40):
        """
        功能: 根据目标类型计算数值。注意: PSO为最小值目标优化
        参数:
            power: 测量功率值
            target: 目标类型 ('max', 'min') 或具体目标值(float)
            
        返回:
            float: 计算后的数值
        """
        if target == "max":
            # 最大化：直接返回功率值的相反数（最大化负值相当于最小化原值）
            target_value = 0
        elif target == "min":
            # 最小化：返回原功率值
            target_value = target_min
        elif isinstance(target, (int, float)):
            # 接近设定值：返回与中间值差异的负值
            target_value = target
        else:
            raise ValueError(f"不支持的目标类型: {target}, 仅支持 'max', 'min' 或具体数值")
        return abs(power - target_value)
    
    def _get_target_description(self, target):
        """获取目标的文字描述"""
        if target == "max":
            return "逼近 0 dBm (最大化)"
        elif target == "min":
            return "逼近 -40 dBm (最小化)"
        elif isinstance(target, (int, float)):
            return f"逼近 {target} dBm"
        else:
            return f"未知目标({target})"
    
    ### 用于优化的目标函数
    def single_wavelength_transmittance(self, voltages,
                            channels = [1],
                            wavelength = 1555,
                            target = "max"
                            ):
        """
        Single Wavelegnth Transmittance: 测量电压下的单一波长透过率
        参数:
            voltages: 电压数组
            wavelength: 目标读取的波长
            channels: 目标读取的通道
            
        返回:
            dict: 包含测量结果的字典
                voltages: 输入的电压数组
                fom: 通道1波长透过率
                各个通道的功率信息
        """
        
        # 转换输入波长为单波长（对应目标方向）
        wavelength = wavelength[0] if isinstance(wavelength, list) else wavelength
        target = target[0] if isinstance(target, list) else target

        # 设置电压
        if not self._set_voltages_and_wait(voltages):
            print("设置电压失败，返回较大的惩罚值")
            return self.get_error_output()
        
        # 执行测量
        try:
            powers = self.ilsts.read_wavelength_power(wavelength, channels)
            fom = self._calculate_target_value(powers[0], target)
            result = {
                'voltages': voltages.copy(),
                'fom': fom,
                'wavelength': wavelength,
                'channels': channels,
                'target': target
            }
            # 添加所有通道的功率信息
            for i, ch in enumerate(channels):
                result[f'CH{ch}_power'] = powers[i]
            
            # 使用基类的格式化输出
            return self._format_result_output(result, "单波长优化")
            
        except Exception as e:
            print(f"测量过程中出错: {e}")
            import traceback
            traceback.print_exc()
            return self.get_error_output()
    
    def single_wavelength_transmittance_temp(self, voltages,
                            channels = [1],
                            wavelength = 1633,
                            target = "max"
                            ):
        """
        Single Wavelegnth Transmittance: 测量电压下的单一波长透过率
        参数:
            voltages: 电压数组
            wavelength: 目标读取的波长
            channels: 目标读取的通道
            
        返回:
            dict: 包含测量结果的字典
                voltages: 输入的电压数组
                fom: 通道1波长透过率
                各个通道的功率信息
        """
        
        # 转换输入波长为单波长（对应目标方向）
        wavelength = wavelength[0] if isinstance(wavelength, list) else wavelength
        target = target[0] if isinstance(target, list) else target

        # 设置电压
        if not self._set_voltages_and_wait(voltages):
            print("设置电压失败，返回较大的惩罚值")
            return self.get_error_output()
        
        # 执行测量
        try:
            powers = self.ilsts.read_wavelength_power(wavelength, channels)
            fom = self._calculate_target_value(powers[0], target)
            result = {
                'voltages': voltages.copy(),
                'fom': fom,
                'wavelength': wavelength,
                'channels': channels,
                'target': target
            }
            # 添加所有通道的功率信息
            for i, ch in enumerate(channels):
                result[f'CH{ch}_power'] = powers[i]
            
            # 使用基类的格式化输出
            return self._format_result_output(result, "单波长优化")
            
        except Exception as e:
            print(f"测量过程中出错: {e}")
            import traceback
            traceback.print_exc()
            return self.get_error_output()
    
    def multi_wavelength_optimization(self, voltages, 
                                      channels = [1],
                                    wavelengths = [1555, 1633],
                                    targets = ["max", "max"]
                            ):
        """
        Multiple Wavelegnth Transmittance: 测量电压下的多个波长透过率
        参数:
            voltages: 电压数组
            wavelengths: 目标读取的波长列表
            channels: 目标读取的通道列表
            targets: 优化目标列表，对应每个波长
        返回:
            dict: 包含测量结果的字典
                voltages: 输入的电压数组
                fom: 综合目标函数值
                各个波长和通道的功率信息
        """

        # 验证参数一致性
        if len(wavelengths) != len(targets):
            raise ValueError("波长列表和目标列表长度必须一致")
        
        # 验证目标参数
        for target in targets:
            if target not in ["max", "min"] and not isinstance(target, (int, float)):
                raise ValueError("目标参数必须是 'max', 'min' 或数值")
            
        # 设置电压
        if not self._set_voltages_and_wait(voltages):
            print("设置电压失败，返回较大的惩罚值")
            return self.get_error_output()
        
        # 执行测量
        try:
            fom = 0.0
            measured_powers = []
            individual_errors = []
            all_powers_data = []
            
            for wavelength, target in zip(wavelengths, targets):
                powers = self.ilsts.read_wavelength_power(wavelength, channels)
                measured_power = powers[0]
                measured_powers.append(measured_power)
                all_powers_data.append(powers)
                
                # 计算目标函数
                individual_error = self._calculate_target_value(measured_power, target)
                individual_errors.append(individual_error)
                fom += individual_error
            
            result = {
                'voltages': voltages.copy(),
                'fom': fom,
                'measured_powers': measured_powers,
                'individual_errors': individual_errors,  # 保留用于调试
                'wavelengths': wavelengths,
                'targets': targets,
                'channels': channels,
            }
            
            # 添加所有通道的功率信息
            for i, wavelength in enumerate(wavelengths):
                for channel, power in zip(channels, all_powers_data[i]):
                    result[f'wl_{wavelength}nm_ch{channel}_power'] = power
            
            # 使用基类的格式化输出
            return self._format_result_output(result, "多波长优化")
            
        except Exception as e:
            print(f"测量过程中出错: {e}")
            import traceback
            traceback.print_exc()
            return self.get_error_output()
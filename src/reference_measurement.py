#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
参考测量模块 - 实现光设备的参考插损测量功能
"""

import os
import json
import time
import matplotlib.pyplot as plt

import plot_style  # 学术论文绘图风格

# Importing modules from the santec directory
from santec import (TslInstrument, MpmInstrument, SpuDevice,
                    GetAddress, file_saving, StsProcess, log_to_screen)

class InputValidator:
    """输入验证器类"""
    @staticmethod
    def get_valid_input(prompt, field_name, expected_type='str', 
                       value_range=None, min_count=None, max_count=None, 
                       default=None):
        """通用输入验证方法"""
        while True:
            user_input = input(prompt).strip()
            
            if not user_input and default is not None:
                print(f"✓ {field_name}使用默认值: {default}")
                return default
            
            is_valid, result, error_msg = InputValidator._validate_input(
                user_input, expected_type, value_range, 
                min_count, max_count, field_name
            )
            
            if is_valid:
                print(f"✓ {field_name}设置成功: {result}")
                return result
            else:
                print(f"✗ 输入错误: {error_msg}")

    @staticmethod
    def _validate_input(input_str, expected_type, value_range=None, min_count=None, max_count=None, field_name="输入"):
        """输入验证核心逻辑"""
        if not input_str.strip():
            return False, None, f"{field_name}不能为空"
        
        try:
            if expected_type == 'int':
                converted_value = int(input_str)
            elif expected_type == 'float':
                converted_value = float(input_str)
            elif expected_type == 'str':
                converted_value = input_str.strip()
            elif expected_type == 'int_list':
                converted_value = [int(item.strip()) for item in input_str.split() if item.strip()]
            elif expected_type == 'float_list':
                converted_value = [float(item.strip()) for item in input_str.split() if item.strip()]
            else:
                converted_value = expected_type(input_str)
            
            # 列表数量检查
            if expected_type in ['int_list', 'float_list']:
                if min_count is not None and len(converted_value) < min_count:
                    return False, None, f"{field_name}至少需要 {min_count} 个元素"
                if max_count is not None and len(converted_value) > max_count:
                    return False, None, f"{field_name}最多允许 {max_count} 个元素"
            
            # 范围检查
            if value_range is not None:
                if isinstance(value_range, (tuple, list)) and len(value_range) == 2:
                    min_val, max_val = value_range
                    if expected_type in ['int_list', 'float_list']:
                        out_of_range_items = []
                        for item in converted_value:
                            if item < min_val or item > max_val:
                                out_of_range_items.append(str(item))
                        if out_of_range_items:
                            return False, None, f"{field_name}以下值超出范围 {min_val}-{max_val}: {', '.join(out_of_range_items)}"
                    else:
                        if converted_value < min_val or converted_value > max_val:
                            return False, None, f"{field_name}必须在 {min_val} 到 {max_val} 之间"
                elif isinstance(value_range, (list, set)):
                    if expected_type in ['int_list', 'float_list']:
                        invalid_items = []
                        for item in converted_value:
                            if item not in value_range:
                                invalid_items.append(str(item))
                        if invalid_items:
                            return False, None, f"{field_name}以下值不在允许范围内 {list(value_range)}: {', '.join(invalid_items)}"
                    else:
                        if converted_value not in value_range:
                            return False, None, f"{field_name}必须是 {list(value_range)} 中的一个"
            
            return True, converted_value, ""
            
        except ValueError:
            type_names = {
                'int': "整数", 'float': "数字", 'str': "字符串",
                'int_list': "整数列表", 'float_list': "数字列表"
            }
            type_name = type_names.get(expected_type, "指定类型")
            return False, None, f"{field_name}必须是有效的{type_name}"
        except Exception as e:
            return False, None, f"{field_name}处理出错: {str(e)}"

class DeviceConnector:
    """设备连接器类"""
    @staticmethod
    def connect_optical_devices(auto_select = True):
        """连接光设备"""
        device_address = GetAddress()
        device_address.initialize_instrument_addresses(auto_select=auto_select)
        tsl_instrument = device_address.get_tsl_address()
        mpm_instrument = device_address.get_mpm_address()
        dev_address = device_address.get_dev_address()

        tsl = TslInstrument(instrument=tsl_instrument)
        tsl.connect()

        mpm = MpmInstrument(instrument=mpm_instrument)
        mpm.connect()

        daq = SpuDevice(device_name=dev_address)
        daq.connect()

        return tsl, mpm, daq

class ParameterManager:
    """参数管理器类"""
    @staticmethod
    def setting_tsl_sweep_params(connected_tsl: TslInstrument, 
                                 previous_param_data: dict, 
                                 validator: InputValidator) -> dict:
        """为 TSL 仪器设置扫描参数"""
        if previous_param_data is not None:
            # 显示历史参数
            print("Start Wavelength (nm): " + str(previous_param_data["start_wavelength"]))
            print("Stop Wavelength (nm): " + str(previous_param_data["stop_wavelength"]))
            print("Sweep Step (nm): " + str(previous_param_data["sweep_step"]))
            print("Sweep Speed (nm): " + str(previous_param_data["sweep_speed"]))
            print("Output Power (dBm): " + str(previous_param_data["power"]))
            print("Selected Channels: " + str(previous_param_data["selected_chans"]))
            print("Dynamic Ranges: " + str(previous_param_data["selected_ranges"]))
            
            ans = input(f"\n是否加载最近的参数设置 {file_saving.FILE_LAST_REF_PARAMS}? [y|n]: ")
            if ans in "Yy":
                # 使用历史参数
                start_wavelength = float(previous_param_data["start_wavelength"])
                stop_wavelength = float(previous_param_data["stop_wavelength"])
                sweep_step = float(previous_param_data["sweep_step"])
                sweep_speed = float(previous_param_data["sweep_speed"])
                power = float(previous_param_data["power"])
                selected_chans = previous_param_data["selected_chans"]
                selected_ranges = previous_param_data["selected_ranges"]
            else:
                # 重新输入参数
                start_wavelength = validator.get_valid_input(
                    "\nInput Start Wavelength (nm): ",
                    "起始波长",
                    expected_type='float',
                    default=previous_param_data["start_wavelength"]
                )
                stop_wavelength = validator.get_valid_input(
                    "Input Stop Wavelength (nm): ",
                    "结束波长",
                    expected_type='float',
                    default=previous_param_data["stop_wavelength"]
                )
                sweep_step = validator.get_valid_input(
                    "Input Sweep Step (pm): ",
                    "扫描步长",
                    expected_type='float',
                    default=previous_param_data["sweep_step"] * 1000
                ) / 1000

                if connected_tsl.get_tsl_type_flag() is True:
                    sweep_speed = validator.get_valid_input(
                        "Input Sweep Speed (nm/sec): ",
                        "扫描速度",
                        expected_type='float',
                        default=previous_param_data["sweep_speed"]
                    )
                else:
                    num = 1
                    print('\nSpeed table:')
                    for i in connected_tsl.get_sweep_speed_table():
                        print(str(num) + "- " + str(i))
                        num += 1
                    speed = validator.get_valid_input(
                        "Select a sweep speed (nm/sec): ",
                        "扫描速度",
                        expected_type='int',
                        value_range=(1, len(connected_tsl.get_sweep_speed_table()))
                    )
                    sweep_speed = connected_tsl.get_sweep_speed_table()[speed - 1]

                power = validator.get_valid_input(
                    "Input Output Power (dBm): ",
                    "输出功率",
                    expected_type='float',
                    value_range=(0, 10),
                    default=previous_param_data["power"]
                )
                while power > 10:
                    print("Invalid value of Output Power ( <=10 dBm )")
                    power = float(input("Input Output Power (dBm): "))
                
                # 选择通道
                print("\nAvailable modules/channels:")
                print("Module 0: Channels [1, 2, 3, 4]")
                print("\nChannels measurement options:")
                print("  1. All channels")
                print("  2. Even channels")
                print("  3. Odd channels")
                print("  4. Specific channels")
                
                channel_option = validator.get_valid_input(
                    "Select channels to be measured: ",
                    "通道测量选项",
                    expected_type='int',
                    value_range=(1, 4)
                )
                
                if channel_option == 1:
                    selected_chans = [["0", "1"], ["0", "2"], ["0", "3"], ["0", "4"]]
                elif channel_option == 2:
                    selected_chans = [["0", "2"], ["0", "4"]]
                elif channel_option == 3:
                    selected_chans = [["0", "1"], ["0", "3"]]
                else:  # Specific channels
                    selected_chans = []
                    while True:
                        channel_input = input("Input (module,channel) to be tested [ex: (0,1); (1,1)]  ")
                        try:
                            # 解析输入格式
                            if channel_input.strip():
                                # 移除括号并分割
                                parts = channel_input.strip('()').split(',')
                                if len(parts) == 2:
                                    module, channel = parts[0].strip(), parts[1].strip()
                                    selected_chans.append([module, channel])
                                    break
                                else:
                                    print("输入格式错误，请重新输入")
                            else:
                                # 默认值
                                selected_chans = [["0", "1"]]
                                break
                        except Exception as e:
                            print(f"输入错误: {e}")
                
                # 选择动态范围
                print("\nAvailable dynamic ranges:")
                print("1. -30 ~ +10dBm")
                print("2. -40 ~ 0dBm")
                print("3. -50 ~ -10dBm")
                print("4. -60 ~ -20dBm")
                print("5. -80 ~ -30dBm")
                
                range_input = validator.get_valid_input(
                    "Select a dynamic range (Ex: 1,2,3): ",
                    "动态范围",
                    expected_type='int',
                    value_range=(1, 5)
                )
                selected_ranges = [range_input]
        else:
            # 首次输入参数
            start_wavelength = validator.get_valid_input(
                "\nInput Start Wavelength (nm): ",
                "起始波长",
                expected_type='float',
                default=1545.0
            )
            stop_wavelength = validator.get_valid_input(
                "Input Stop Wavelength (nm): ",
                "结束波长",
                expected_type='float',
                default=1555.0
            )
            sweep_step = validator.get_valid_input(
                "Input Sweep Step (pm): ",
                "扫描步长",
                expected_type='float',
                default=0.1
            ) / 1000

            if connected_tsl.get_tsl_type_flag() is True:
                sweep_speed = validator.get_valid_input(
                    "Input Sweep Speed (nm/sec): ",
                    "扫描速度",
                    expected_type='float',
                    default=1
                )
            else:
                num = 1
                print('\nSpeed table:')
                for i in connected_tsl.get_sweep_speed_table():
                    print(str(num) + "- " + str(i))
                    num += 1
                speed = validator.get_valid_input(
                    "Select a sweep speed (nm/sec): ",
                    "扫描速度",
                    expected_type='int',
                    value_range=(1, len(connected_tsl.get_sweep_speed_table()))
                )
                sweep_speed = connected_tsl.get_sweep_speed_table()[speed - 1]

            power = validator.get_valid_input(
                "Input Output Power (dBm): ",
                "输出功率",
                expected_type='float',
                value_range=(0, 10),
                default=10
            )
            while power > 10:
                print("Invalid value of Output Power ( <=10 dBm )")
                power = float(input("Input Output Power (dBm): "))
            
            # 选择通道
            print("\nAvailable modules/channels:")
            print("Module 0: Channels [1, 2, 3, 4]")
            print("\nChannels measurement options:")
            print("  1. All channels")
            print("  2. Even channels")
            print("  3. Odd channels")
            print("  4. Specific channels")
            
            channel_option = validator.get_valid_input(
                "Select channels to be measured: ",
                "通道测量选项",
                expected_type='int',
                value_range=(1, 4)
            )
            
            if channel_option == 1:
                selected_chans = [["0", "1"], ["0", "2"], ["0", "3"], ["0", "4"]]
            elif channel_option == 2:
                selected_chans = [["0", "2"], ["0", "4"]]
            elif channel_option == 3:
                selected_chans = [["0", "1"], ["0", "3"]]
            else:  # Specific channels
                selected_chans = []
                while True:
                    channel_input = input("Input (module,channel) to be tested [ex: (0,1); (1,1)]  ")
                    try:
                        # 解析输入格式
                        if channel_input.strip():
                            # 移除括号并分割
                            parts = channel_input.strip('()').split(',')
                            if len(parts) == 2:
                                module, channel = parts[0].strip(), parts[1].strip()
                                selected_chans.append([module, channel])
                                break
                            else:
                                print("输入格式错误，请重新输入")
                        else:
                            # 默认值
                            selected_chans = [["0", "1"]]
                            break
                    except Exception as e:
                        print(f"输入错误: {e}")
            
            # 选择动态范围
            print("\nAvailable dynamic ranges:")
            print("1. -30 ~ +10dBm")
            print("2. -40 ~ 0dBm")
            print("3. -50 ~ -10dBm")
            print("4. -60 ~ -20dBm")
            print("5. -80 ~ -30dBm")
            
            range_input = validator.get_valid_input(
                "Select a dynamic range (Ex: 1,2,3): ",
                "动态范围",
                expected_type='int',
                value_range=(1, 5)
            )
            selected_ranges = [range_input]

        # 设置TSL参数
        connected_tsl.set_power(power)
        connected_tsl.set_sweep_parameters(start_wavelength, stop_wavelength, sweep_step, sweep_speed)
        
        # 返回参数
        return {
            "start_wavelength": start_wavelength,
            "stop_wavelength": stop_wavelength,
            "sweep_step": sweep_step,
            "sweep_speed": sweep_speed,
            "power": power,
            "selected_chans": selected_chans,
            "selected_ranges": selected_ranges
        }

    @staticmethod
    def prompt_and_get_previous_param_data(file_last_scan_params: str) -> dict | None:
        """如果可用，提示用户加载之前的参数设置"""
        if not os.path.exists(file_last_scan_params):
            return None
        
        with open(file_last_scan_params, encoding='utf-8') as json_file:
            previous_settings = json.load(json_file)

        return previous_settings

class FileManager:
    """文件管理器类"""
    @staticmethod
    def save_set_params(file_last_scan_params: str, tsl: TslInstrument, params: dict, ilsts: StsProcess) -> None:
        """将测量设置保存至文件中"""
        print(f"保存参数到文件 {file_last_scan_params}...")
        file_saving.save_sts_parameter_data(tsl, ilsts, file_last_scan_params)

    @staticmethod
    def save_ref_data(ilsts: StsProcess) -> None:
        """将参考数据保存至文件中"""
        print(f"保存参考数据到文件 {file_saving.FILE_LAST_SCAN_REFERENCE_DATA}...")
        file_saving.save_reference_data(ilsts, file_saving.FILE_LAST_SCAN_REFERENCE_DATA)

class Visualizer:
    """可视化器类"""
    @staticmethod
    def plot_reference_data(ilsts: StsProcess):
        """绘制参考插损数据图像"""
        try:
            if not hasattr(ilsts, 'reference_data_array') or not ilsts.reference_data_array:
                print("没有可用的参考插损数据")
                return
            
            plt.figure(figsize=(10, 6))
            
            for ref_item in ilsts.reference_data_array:
                slot_num = ref_item["SlotNumber"]
                channel_num = ref_item["ChannelNumber"]
                wavelengths = ref_item["rescaled_wavelength"]
                reference_power = ref_item["rescaled_reference_power"]
                
                plt.plot(wavelengths, reference_power, 
                        label=f'Slot{slot_num} Ch{channel_num}')
            
            plt.xlabel('Wavelength (nm)')
            plt.ylabel('Reference Power (dBm)')
            plt.title('Reference Insertion Loss Measurement')
            plt.legend()
            plt.tight_layout()
            plt.show(block=False)
            
        except Exception as e:
            print(f"绘制参考插损图像时出错: {e}")

class ReferenceMeasurement:
    """参考测量类"""
    def __init__(self):
        self.validator = InputValidator()
        self.device_connector = DeviceConnector()
        self.param_manager = ParameterManager()
        self.file_manager = FileManager()
        self.visualizer = Visualizer()
        self.tsl = None
        self.mpm = None
        self.daq = None
        self.ilsts = None

    def initialize_optical_devices(self):
        """初始化光设备"""
        print("步骤 1: 初始化光设备...")
        self.tsl, self.mpm, self.daq = self.device_connector.connect_optical_devices()
        self.tsl.write("*CLS")
        self.tsl.write("*RST")
        time.sleep(1)
        self.mpm.cls_status
        time.sleep(1)
        
        while self.mpm is None:
            print("未检测到MPM设备, 请检查连接后重试。")
            input("按ENTER重试...")
            self.tsl, self.mpm, self.daq = self.device_connector.connect_optical_devices()
            
        self.ilsts = StsProcess(self.tsl, self.mpm, self.daq)
        return True

    def configure_reference_parameters(self):
        """配置参考测量参数"""
        print("\n步骤 2: 配置参考测量参数...")
        previous_params = self.param_manager.prompt_and_get_previous_param_data(file_saving.FILE_LAST_REF_PARAMS)
        
        # 设置TSL扫描参数
        params = self.param_manager.setting_tsl_sweep_params(self.tsl, previous_params, self.validator)
        
        # 设置选中的通道
        self.ilsts.set_selected_channels(params)
        
        # 设置选中的动态范围
        self.ilsts.set_selected_ranges(params)
        
        # 设置数据结构和参数
        self.ilsts.set_sts_data_struct()  # 测量数据保存空间创建
        self.ilsts.set_parameters()  # 扫描波长相关参数设置执行
        
        # 保存参数
        self.file_manager.save_set_params(file_saving.FILE_LAST_REF_PARAMS, self.tsl, params, self.ilsts)
        
        return params

    def perform_reference_measurement(self, prompt_user=True):
        """执行参考测量"""
        # 提示用户连接测试通道
        if prompt_user:
            input("\nConnect Slot0 Ch1, then press ENTER")
        
        # 执行扫描
        print("\nScanning...")
        self.ilsts.sts_reference()
        
        # 询问是否显示参考插损图像
        if prompt_user:
            show_ref_plot = input("\n是否显示参考插损图像? [y|n] (默认y): ") in "Yy"
            if show_ref_plot:
                print("正在绘制参考插损图像...")
                self.visualizer.plot_reference_data(self.ilsts)
            
            # 询问是否保存参考数据
            save_ref = input("\n是否保存参考数据? [y|n] (默认y): ") in "Yy"
            if save_ref:
                self.file_manager.save_ref_data(self.ilsts)

    def measure_insertion_loss(self):
        """测量插损"""
        try:
            # 执行扫描
            print("\n测量插损...")
            self.ilsts.sts_measurement()
            return True
        except Exception as e:
            print(f"测量插损过程中出错: {e}")
            return False

    def run(self):
        """运行参考测量流程"""
        try:
            # 初始化光设备
            if not self.initialize_optical_devices():
                return False
            
            # 配置参考测量参数
            self.configure_reference_parameters()
            
            # 执行参考测量
            self.perform_reference_measurement()
            
            print("\n参考测量完成！")
            return True
        except Exception as e:
            print(f"参考测量过程中出错: {e}")
            return False
        finally:
            # 关闭设备
            if self.tsl:
                self.tsl.query("*RST")
            if self.mpm:
                self.mpm.cls_status

if __name__ == "__main__":
    print("=== 参考测量模块 ===")
    measurement = ReferenceMeasurement()
    measurement.run()
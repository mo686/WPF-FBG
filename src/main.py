#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Santec IL STS - 完整重构版本
"""

import os
import json
import time
import matplotlib.pyplot as plt
import nidaqmx.system
import msvcrt
import datetime
import serial.tools.list_ports

import plot_style  # 学术论文绘图风格

# Importing modules from the santec directory
from santec import (TslInstrument, MpmInstrument, SpuDevice,
                    GetAddress, file_saving, StsProcess, log_to_screen)
# 电压源控制
from ni_voltage_control import VoltageController
from zynq_voltage_controller import ZynqVoltageController
# 目标函数
from finite_lambdas_functions import FiniteLambdaFunctions
from spectral_functions import SpectralFunctions
# 优化方法
from iterator import Iterator
from quick_searcher import QuickSearcher
from optimization_adapter import OptimizationAdapter
from pso import PSO
from bayesian import Bayesian

# ========== 输入验证器类 ==========
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

# ========== 设备连接器类 ==========
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

    @staticmethod
    def list_available_devices():
        """列出所有可用的NI-DAQmx设备"""
        system = nidaqmx.system.System.local()
        devices = []
        print("可用设备列表: ")
        for i, device in enumerate(system.devices):
            print(f"{i+1}. {device.name} ({device.product_type})")
            devices.append(device.name)
        return devices

    @staticmethod
    def list_serial_ports():
        """列出所有可用的串口设备"""
        ports = list(serial.tools.list_ports.comports())
        print("可用串口: ")
        for i, port in enumerate(ports):
            print(f"{i+1}. {port.device} - {port.description}")
        return [port.device for port in ports]

# ========== 参数管理器类 ==========
class ParameterManager:
    """参数管理器类"""
    @staticmethod
    def setting_tsl_sweep_params(connected_tsl: TslInstrument, 
                                 previous_param_data: dict,
                                 auto_mode: bool = False) -> None:
        """为 TSL 仪器设置扫描参数"""
        if previous_param_data is not None:
            # 自动模式：直接使用历史参数，不询问
            start_wavelength = float(previous_param_data["start_wavelength"])
            stop_wavelength = float(previous_param_data["stop_wavelength"])
            sweep_step = float(previous_param_data["sweep_step"])
            sweep_speed = float(previous_param_data["sweep_speed"])
            power = float(previous_param_data["power"])
            if auto_mode:
                print("✅ 自动使用历史扫描参数")
        else:
            start_wavelength = float(input("\nInput Start Wavelength (nm): "))
            stop_wavelength = float(input("Input Stop Wavelength (nm): "))
            sweep_step = float(input("Input Sweep Step (pm): ")) / 1000

            if connected_tsl.get_tsl_type_flag() is True:
                sweep_speed = float(input("Input Sweep Speed (nm/sec): "))
            else:
                num = 1
                print('\nSpeed table:')
                for i in connected_tsl.get_sweep_speed_table():
                    print(str(num) + "- " + str(i))
                    num += 1
                speed = input("Select a sweep speed (nm/sec): ")
                sweep_speed = connected_tsl.get_sweep_speed_table()[int(speed) - 1]

            power = float(input("Input Output Power (dBm): "))
            while power > 10:
                print("Invalid value of Output Power ( <=10 dBm )")
                power = float(input("Input Output Power (dBm): "))

        connected_tsl.set_power(power)
        connected_tsl.set_sweep_parameters(start_wavelength, stop_wavelength, sweep_step, sweep_speed)

    @staticmethod
    def prompt_and_get_previous_param_data(file_last_scan_params: str, 
                                           auto_mode: bool = False) -> dict | None:
        """如果可用，提示用户加载之前的参数设置"""
        if not os.path.exists(file_last_scan_params):
            return None
        
        with open(file_last_scan_params, encoding='utf-8') as json_file:
            previous_settings = json.load(json_file)

        if auto_mode:
            print("✅ 自动加载历史参数")
            return previous_settings
        else: 
            print("Start Wavelength (nm): " + str(previous_settings["start_wavelength"]))
            print("Stop Wavelength (nm): " + str(previous_settings["stop_wavelength"]))
            print("Sweep Step (nm): " + str(previous_settings["sweep_step"]))
            print("Sweep Speed (nm): " + str(previous_settings["sweep_speed"]))
            print("Output Power (dBm): " + str(previous_settings["power"]))
            print("Selected Channels: " + str(previous_settings["selected_chans"]))
            print("Dynamic Ranges: " + str(previous_settings["selected_ranges"]))
            ans = input(f"\n是否加载最近的参数设置 {file_last_scan_params}? [y|n]: ")
            return previous_settings if ans in "Yy" else None

    @staticmethod
    def prompt_and_get_previous_reference_data(auto_mode: bool = False) -> dict | None:
        """询问用户是否使用之前存在的参考数据"""
        if not os.path.exists(file_saving.FILE_LAST_SCAN_REFERENCE_DATA):
            return None

        if auto_mode:
            print("✅ 自动加载参考数据")
            with open(file_saving.FILE_LAST_SCAN_REFERENCE_DATA, 'r', encoding='utf-8') as file:
                data = file.read()
                previous_reference = json.loads(data)
            return previous_reference
        else: 
            ans = input(f"\n是否使用最近的参考数据文件 '{file_saving.FILE_LAST_SCAN_REFERENCE_DATA}'? [y|n] (默认y): ")
            if ans not in "Yy":
                return None

        int_file_size = int(os.path.getsize(file_saving.FILE_LAST_SCAN_REFERENCE_DATA))
        str_file_size = f"{int_file_size / 1000000:.2f} MB" if int_file_size > 1000000 else f"{int_file_size / 1000:.2f} KB"

        print(f"打开 {str_file_size} 文件 '{file_saving.FILE_LAST_SCAN_REFERENCE_DATA}'...")
        with open(file_saving.FILE_LAST_SCAN_REFERENCE_DATA, 'r', encoding='utf-8') as file:
            data = file.read()
            previous_reference = json.loads(data)
        return previous_reference

# ========== 文件管理器类 ==========
class FileManager:
    """文件管理器类"""
    @staticmethod
    def save_set_params(file_last_scan_params: str, tsl: TslInstrument, previous_param_data: dict, ilsts: StsProcess) -> None:
        """将测量设置保存至文件中"""
        if previous_param_data is None:
            print(f"保存参数到文件 {file_last_scan_params}...")
            file_saving.save_sts_parameter_data(tsl, ilsts, file_last_scan_params)

    @staticmethod
    def save_ref_data(ilsts: StsProcess) -> None:
        """将参考数据保存至文件中"""
        print(f"保存参考数据到文件 {file_saving.FILE_LAST_SCAN_REFERENCE_DATA}...")
        file_saving.save_reference_data(ilsts, file_saving.FILE_LAST_SCAN_REFERENCE_DATA)

    @staticmethod
    def save_measure_data(ilsts: StsProcess) -> None:
        """将测量数据保存至文件中"""
        print(f"\n保存测量数据到文件 {file_saving.FILE_MEASUREMENT_DATA_RESULTS}...")
        file_saving.save_measurement_data(ilsts, file_saving.FILE_MEASUREMENT_DATA_RESULTS)

        print(f"保存DUT数据到文件 {file_saving.FILE_DUT_DATA_RESULTS}...")
        file_saving.save_dut_result_data(ilsts, file_saving.FILE_DUT_DATA_RESULTS)

# ========== 可视化器类 ==========
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

    @staticmethod
    def plot_scan_data(ilsts: StsProcess):
        """绘制扫描数据"""
        try:
            if not hasattr(ilsts, 'il_data_array') or not ilsts.il_data_array:
                print("没有可用的扫描数据")
                return
            
            if hasattr(ilsts, 'wavelength_table'):
                wavelengths = ilsts.wavelength_table
            else:
                print("无法获取波长数据")
                return
            
            num_channels = len(ilsts.il_data_array)
            plt.figure(figsize=(12, 8))
            
            for i in range(num_channels):
                channel_data = ilsts.il_data_array[i]
                plt.plot(wavelengths, channel_data, label=f'CH{i+1}', linewidth=2)
            
            plt.xlabel('Wavelength (nm)', fontsize=12)
            plt.ylabel('Transmission (dBm)', fontsize=12)
            plt.title('Scan Data - All Selected Channels', fontsize=14)
            plt.legend()
            plt.tight_layout()
            plt.show(block=False)
                    
        except Exception as e:
            print(f"绘制扫描数据时出错: {e}")

# ========== 工具函数类 ==========
class UtilityFunctions:
    """工具函数类"""
    @staticmethod
    def zero_all_ports(controller, num_ch):
        """将所有电压端口置零"""
        try:
            zeros = [0.0] * int(num_ch)
            if hasattr(controller, 'set_voltages'):
                controller.set_voltages(zeros)
            elif hasattr(controller, 'set_voltage'):
                for ch in range(int(num_ch)):
                    controller.set_voltage(ch, 0.0)
            elif hasattr(controller, 'set'):
                controller.set(zeros)
            else:
                print("警告：控制器未实现已知的设置接口，无法自动置零")
                return False
            time.sleep(0.05)
            print(f"已将所有 {num_ch} 个电压通道置零")
            return True
        except Exception as e:
            print(f"置零失败: {e}")
            return False

    @staticmethod
    def monitor_power_loop(ilsts, wavelength: float, channel_numbers: list | None = None, refresh_interval: float = 0.1):
        """在指定波长下循环刷新并输出所有通道的光功率"""
        if channel_numbers is None:
            try:
                if hasattr(ilsts, 'selected_chans') and ilsts.selected_chans:
                    channel_numbers = [int(ch[1]) for ch in ilsts.selected_chans]
                else:
                    channel_numbers = [1, 2, 3, 4]
            except Exception:
                channel_numbers = [1, 2, 3, 4]

        print(f"开始在 {wavelength} nm 下循环读取通道功率，监测通道: {channel_numbers}。按 Enter 结束。")
        try:
            while True:
                powers = ilsts.read_wavelength_power(wavelength, channel_numbers)
                ts = datetime.datetime.now().strftime("%H:%M:%S")
                line = " | ".join([f"CH{ch}: {p:.3f} dBm" for ch, p in zip(channel_numbers, powers)])
                print(f"\r[{ts}] {line}", end='', flush=True)

                if msvcrt.kbhit():
                    key = msvcrt.getch()
                    if key in (b'\r', b'\n'):
                        print("\n检测到回车键，退出监测。")
                        break
                time.sleep(refresh_interval)
        except KeyboardInterrupt:
            print("检测到中断，退出监测。")
        except Exception as e:
            print(f"监测过程中发生异常: {e}")

# ========== 配置管理器类 ==========
class ConfigManager:
    """配置管理器类 - 负责读取和管理外部配置"""
    def __init__(self, config_dir=r"src\config"):
        self.config_dir = config_dir
        self.config_file = os.path.join(self.config_dir, "voltage_controller_config.json")
    
    def config_exists(self):
        """检查配置文件是否存在"""
        return os.path.exists(self.config_file)
    
    def get_voltage_controller_config(self):
        """获取电压控制器配置"""
        if not self.config_exists():
            return None
        
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            if "voltage_controller" in config:
                voltage_config = config["voltage_controller"]
                self._validate_config(voltage_config)
                print(f"✅ 已加载电压控制器配置: {voltage_config}")
                return voltage_config
            else:
                return None
                
        except Exception as e:
            print(f"❌ 读取配置文件失败: {e}")
            return None
    
    def save_voltage_controller_config(self, config_data):
        """保存电压控制器配置到文件"""
        try:
            # 准备完整的配置结构
            full_config = {
                "voltage_controller": config_data,
                "description": "电压控制器配置 - 自动保存的用户选择",
                "last_updated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
            # 确保配置目录存在
            os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
            
            # 保存到文件
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(full_config, f, indent=4, ensure_ascii=False)
            
            print(f"✅ 电压控制器配置已保存到: {self.config_file}")
            print(f"   配置内容: {config_data}")
            return True
            
        except Exception as e:
            print(f"❌ 保存配置文件失败: {e}")
            return False
    
    def _validate_config(self, config):
        """验证配置有效性"""
        validations = {
            "voltage_source": (1, 3),
            "num_channels": (1, 16),
            "device_index": (0, 15),
            "start_channel": (0, 15),
            "port_index": (0, 10),
            "baudrate_index": (0, 7)
        }
        
        for key, (min_val, max_val) in validations.items():
            if key in config:
                value = config[key]
                if not (min_val <= value <= max_val):
                    print(f"⚠️ 配置项 {key} 的值 {value} 超出合理范围 [{min_val}, {max_val}]")

# ========== 设备管理器类 ==========
class DeviceManager:
    """设备管理器类"""
    def __init__(self, config_manager=None):
        self.tsl = None
        self.mpm = None
        self.daq = None
        self.voltage_controller = None
        self.num_channels = 0
        self.connector = DeviceConnector()
        self.utility = UtilityFunctions()
        self.config_manager = config_manager or ConfigManager()
        self.current_config = {}  # 保存当前使用的配置
        
    def initialize_optical_devices(self):
        """初始化光设备"""
        self.tsl, self.mpm, self.daq = self.connector.connect_optical_devices()
        self.tsl.write("*CLS")
        self.tsl.write("*RST")
        time.sleep(1)
        self.mpm.cls_status
        time.sleep(1)
        
        while self.mpm is None:
            print("未检测到MPM设备, 请检查连接后重试。")
            input("按ENTER重试...")
            self.tsl, self.mpm, self.daq = self.connector.connect_optical_devices()
            
        return StsProcess(self.tsl, self.mpm, self.daq)
    
    def initialize_voltage_controller(self, validator, auto_mode=False):
        """初始化电压控制器
        Args:
            validator: 输入验证器
            auto_mode: 是否自动模式
        Returns:
            tuple: (success, config_type)
                success: 初始化是否成功
                config_type: 配置类型，可选值:
                    - "auto_config": 使用自动配置成功
                    - "auto_fallback": 自动配置失败后使用交互配置  
                    - "interactive": 直接使用交互配置
                    - "none": 无电压控制
        """
        CONFIG_TYPES = {
            "auto_config": "自动配置",
            "auto_fallback": "自动回退配置", 
            "interactive": "交互配置",
            "none": "无配置"
        }
        
        config_type = "interactive"  # 默认配置类型
        
        # 1. 尝试自动配置（仅在自动模式且配置文件存在时）
        if auto_mode and self.config_manager.config_exists():
            config = self.config_manager.get_voltage_controller_config()
            if config:
                print("🔄 尝试自动配置电压控制器...")
                success = self._initialize_with_config(validator, config)
                if success:
                    print("✅ 电压控制器自动配置成功")
                    return True, "auto_config"
                else:
                    print("⚠️ 自动配置失败，切换到交互配置")
                    config_type = "auto_fallback"
        
        # 2. 交互配置模式
        print("🔧 进入电压控制器交互配置模式")
        success = self._initialize_interactive(validator)
        
        if not success:
            print("❌ 电压控制器配置失败")
            return False, config_type
        
        # 3. 简化保存逻辑：只在明确需要时保存
        should_save = self._should_save_config(auto_mode, config_type)
        if should_save:
            self._save_current_config()
        
        print(f"✅ 电压控制器初始化完成")
        return True, config_type
    
    def _initialize_with_config(self, validator, config):
        """使用配置初始化电压控制器"""
        voltage_source = config.get('voltage_source', 2)
        
        if voltage_source == 1:
            return self._initialize_ni_daq_with_config(config)
        elif voltage_source == 2:
            return self._initialize_fpga_with_config(config)
        else:
            print("配置中设置为无电压控制")
            return False
    
    def _initialize_ni_daq_with_config(self, config):
        """使用配置初始化NI-DAQ电压控制器"""
        print("\n正在初始化NI-DAQ电压控制器...")
        available_devices = self.connector.list_available_devices()
        if not available_devices:
            print("未找到可用的NI-DAQ设备")
            return False
        
        device_index = config.get('device_index', 0)
        if device_index >= len(available_devices):
            print(f"⚠️ 配置中的设备索引 {device_index} 无效，使用第一个设备")
            device_index = 0
        
        self.num_channels = config.get('num_channels', 4)
        start_channel = config.get('start_channel', 0)
        
        print(f"✅ 使用配置: 设备索引={device_index}, 通道数={self.num_channels}, 起始通道={start_channel}")
        
        voltage_device = available_devices[device_index]
        self.voltage_controller = VoltageController(
            voltage_device, 
            num_channels=self.num_channels, 
            start_channel=start_channel
        )
        
        # 保存当前配置
        self.current_config = config.copy()
        
        # 自动置零
        zero_success = self.utility.zero_all_ports(self.voltage_controller, self.num_channels)
        if zero_success:
            print("✅ NI-DAQ电压控制器初始化成功")
            return True
        else:
            print("❌ NI-DAQ电压控制器初始化失败")
            return False
    
    def _initialize_fpga_with_config(self, config):
        """使用配置初始化FPGA电压控制器"""
        print("\n正在初始化FPGA电压源控件...")
        available_serial = self.connector.list_serial_ports()
        if not available_serial:
            print("未找到可用串口设备")
            return False
        
        port_index = config.get('port_index', 0)
        if port_index >= len(available_serial):
            print(f"⚠️ 配置中的串口索引 {port_index} 无效，使用第一个串口")
            port_index = 0
        
        selected_port = available_serial[port_index]
        
        # 波特率配置
        baudrate_options = [9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600]
        baudrate_index = config.get('baudrate_index', 4)
        if baudrate_index >= len(baudrate_options):
            baudrate_index = 4
        
        selected_baudrate = baudrate_options[baudrate_index]
        self.num_channels = config.get('num_channels', 4)
        
        print(f"✅ 使用配置: 串口={selected_port}, 波特率={selected_baudrate}, 通道数={self.num_channels}")
        
        # 初始化控制器
        self.voltage_controller = ZynqVoltageController(
            port=selected_port,
            baudrate=selected_baudrate,
            num_channels=self.num_channels
        )
        
        # 保存当前配置
        self.current_config = config.copy()
        
        if self.voltage_controller and self.voltage_controller.initialize():
            # 自动置零
            zero_success = self.utility.zero_all_ports(self.voltage_controller, self.num_channels)
            if zero_success:
                print("✅ FPGA电压控制器初始化成功")
                return True
            else:
                print("⚠️ 电压控制器初始化成功但置零失败")
                return True
        else:
            print("❌ FPGA电压控制器初始化失败")
            self.voltage_controller = None
            return False
    
    def _initialize_interactive(self, validator):
        """交互式初始化电压控制器"""
        print("\n请选择电压源: ")
        print("1. NI-DAQ电压控制")
        print("2. FPGA-Zynq电压控制")
        print("3. 无电压控制")
        
        voltage_source = validator.get_valid_input(
            "\n请输入选项 (1/2/3, 默认为2): ",
            "电压源",
            expected_type='int',
            value_range=(1, 3),
            default=2
        )
        
        # 保存用户选择的配置
        self.current_config['voltage_source'] = voltage_source
        
        if voltage_source == 1:
            return self._initialize_ni_daq_interactive(validator)
        elif voltage_source == 2:
            return self._initialize_fpga_interactive(validator)
        else:
            print("跳过电压控制初始化")
            return False
    
    def _initialize_ni_daq_interactive(self, validator):
        """交互式初始化NI-DAQ电压控制器"""
        print("\n正在初始化NI-DAQ电压控制器...")
        available_devices = self.connector.list_available_devices()
        if not available_devices:
            print("未找到可用的NI-DAQ设备")
            return False
        
        # 用户选择设备
        device_index = validator.get_valid_input(
            "请选择PXIe-4322设备编号: ",
            "PXIe-4322设备",
            expected_type='int',
            value_range=(1, len(available_devices))
        ) - 1
        
        # 用户配置通道
        self.num_channels = validator.get_valid_input(
            "请输入要使用的通道数量(默认为4): ",
            "通道数量",
            expected_type='int',
            value_range=(1, 16),
            default=4
        )
        
        start_channel = validator.get_valid_input(
            "请输入起始通道编号(默认为0): ",
            "起始通道",
            expected_type='int',
            value_range=(0, 15),
            default=0
        )
        
        # 保存用户选择的配置
        self.current_config['device_index'] = device_index
        self.current_config['num_channels'] = self.num_channels
        self.current_config['start_channel'] = start_channel
        
        voltage_device = available_devices[device_index]
        self.voltage_controller = VoltageController(
            voltage_device, 
            num_channels=self.num_channels, 
            start_channel=start_channel
        )
        
        # 自动置零
        zero_success = self.utility.zero_all_ports(self.voltage_controller, self.num_channels)
        if zero_success:
            print("✅ NI-DAQ电压控制器初始化成功")
            return True
        else:
            print("❌ NI-DAQ电压控制器初始化失败")
            return False
    
    def _initialize_fpga_interactive(self, validator):
        """交互式初始化FPGA电压控制器"""
        print("\n正在初始化FPGA电压源控件...")
        available_serial = self.connector.list_serial_ports()
        if not available_serial:
            print("未找到可用串口设备")
            return False
        
        # 用户选择串口
        port_num = len(available_serial)
        if port_num > 1:
            port_index = validator.get_valid_input(
                f"请选择要使用的串口设备编号 (1-{port_num}): ",
                "串口设备",
                expected_type='int',
                value_range=(1, port_num)
            ) - 1
        else:
            port_index = 0
        
        selected_port = available_serial[port_index]
        
        # 波特率配置
        baudrate_options = [9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600]
        print("\n可选波特率:")
        for i, rate in enumerate(baudrate_options):
            print(f"{i+1}. {rate}")

        baudrate_index = validator.get_valid_input(
            "请选择波特率编号 (默认115200): ",
            "波特率",
            expected_type='int',
            value_range=(1, len(baudrate_options)),
            default=5
        ) - 1
        
        selected_baudrate = baudrate_options[baudrate_index]
        
        # 通道数量配置
        self.num_channels = validator.get_valid_input(
            "请输入要使用的DAC通道数量 (默认为4): ",
            "DAC通道数量",
            expected_type='int',
            value_range=(1, 16),
            default=4
        )
        
        # 保存用户选择的配置
        self.current_config['port_index'] = port_index
        self.current_config['baudrate_index'] = baudrate_index
        self.current_config['num_channels'] = self.num_channels
        
        # 初始化控制器
        self.voltage_controller = ZynqVoltageController(
            port=selected_port,
            baudrate=selected_baudrate,
            num_channels=self.num_channels
        )
        
        if self.voltage_controller and self.voltage_controller.initialize():
            # 自动置零
            zero_success = self.utility.zero_all_ports(self.voltage_controller, self.num_channels)
            if zero_success:
                print("✅ FPGA电压控制器初始化成功")
                return True
            else:
                print("⚠️ 电压控制器初始化成功但置零失败")
                return True
        else:
            print("❌ FPGA电压控制器初始化失败")
            self.voltage_controller = None
            return False
    
    def _should_save_config(self, auto_mode, config_type):
        """判断是否需要保存配置 - 简化逻辑"""
        if auto_mode:
            # 自动模式下：只有自动回退情况才保存（即配置文件存在但初始化失败）
            if config_type == "auto_fallback":
                print("💾 自动保存新的电压控制器配置")
                return True
            return False
        else:
            # 手动模式下询问用户
            save_choice = input("\n是否保存此电压控制器配置? [y|n] (默认n): ").strip()
            return save_choice in "Yy"  # 默认不保存

    def _save_current_config(self):
        """保存当前配置"""
        if self.current_config:
            success = self.config_manager.save_voltage_controller_config(self.current_config)
            if success:
                print("✅ 电压控制器配置已保存")
            else:
                print("❌ 配置保存失败")
        else:
            print("⚠️ 无当前配置可保存")
    
    def rst_optical(self):
        if self.tsl:
            self.tsl.query("*RST")
            time.sleep(1)
            print("✅ 激光器缓存已通过复位清空")
        
        if self.mpm:
            self.mpm.cls_status
            time.sleep(1)
            print("✅ 探测器缓存已通过复位清空")

    def shutdown(self):
        """关闭所有设备"""
        if self.voltage_controller:
            self.utility.zero_all_ports(self.voltage_controller, self.num_channels)
            self.voltage_controller.close()
        
        self.rst_optical()

# ========== 参数配置器类 ==========
class ParameterConfigurator:
    """参数配置器类"""
    def __init__(self, validator):
        self.validator = validator
        self.param_manager = ParameterManager()
        self.file_manager = FileManager()
        
    def configure_sweep_parameters(self, tsl, ilsts, param_type, auto_mode=False):
        """配置扫描参数"""
        path_params = self._get_param_path(param_type)
        previous_params = self.param_manager.prompt_and_get_previous_param_data(
            path_params, auto_mode=auto_mode
        )
        
        self.param_manager.setting_tsl_sweep_params(tsl, previous_params)
        ilsts.set_selected_channels(previous_params)
        
        if param_type in ['opt', 'scan']:
            ilsts.set_selected_ranges(previous_params, if_update_range=1)
            ilsts.resample_reference_data()
            ilsts.set_parameters(if_rst_ref=0)
            ilsts.sts_reference_from_resampled_data()
        if param_type == 'ref':
            ilsts.set_selected_ranges(previous_params)
            ilsts.set_sts_data_struct()                         #测量数据保存空间创建
            ilsts.set_parameters()                              #扫描波长相关参数设置执行
        
        self.file_manager.save_set_params(path_params, tsl, previous_params, ilsts)
        return previous_params
    
    def _get_param_path(self, param_type):
        """获取参数文件路径"""
        paths = {
            'ref': file_saving.FILE_LAST_REF_PARAMS,
            'opt': file_saving.FILE_LAST_OPT_PARAMS,
            'scan': file_saving.FILE_LAST_SCAN_PARAMS
        }
        return paths.get(param_type, file_saving.FILE_LAST_REF_PARAMS)

# ========== 工作流管理器类 ==========
class WorkflowManager:
    """工作流管理器类 - 合并自动模式功能"""
    def __init__(self, validator, param_config, device_manager, auto_mode=False):
        self.validator = validator
        self.param_config = param_config
        self.device_manager = device_manager
        self.param_manager = ParameterManager()
        self.file_manager = FileManager()
        self.visualizer = Visualizer()
        self.utility = UtilityFunctions()
        self.auto_mode = auto_mode
        self.default_config = {
            'auto_load_reference': True, 
            'skip_polarization': True
        }
    
    def perform_reference_measurement(self, ilsts, previous_params=None):
        """执行参考测量"""
        if self.auto_mode and self.default_config['auto_load_reference']:
            # 自动模式：直接加载参考数据
            previous_ref_data = self.param_manager.prompt_and_get_previous_reference_data(auto_mode=True)
            if previous_ref_data is not None:
                ilsts.reference_data_array = previous_ref_data
                print("✅ 自动加载参考数据")
                return
        
        if previous_params is None:
            print("\n⚠️ 未加载参考参数配置，强制进行新的参考测量")
            previous_ref_data = None
        else:
            previous_ref_data = self.param_manager.prompt_and_get_previous_reference_data()
        
        if previous_ref_data is not None:
            ilsts.reference_data_array = previous_ref_data
        
        if len(ilsts.reference_data_array) == 0:
            ilsts.sts_reference()
        else:
            print("加载参考插损中...")
            ilsts.sts_reference_from_saved_file()
        
        show_ref_plot = input("\n是否显示参考插损图像? [y|n] (默认n): ") in "Yy"
        if show_ref_plot:
            print("正在绘制参考插损图像...")
            self.visualizer.plot_reference_data(ilsts)
        
        save_ref = input("\n是否保存参考数据? [y|n] (默认n): ") in "Yy"
        if save_ref:
            self.file_manager.save_ref_data(ilsts)
    
    def perform_polarization_adjustment(self, ilsts):
        """执行偏振调节"""
        if self.auto_mode and self.default_config['skip_polarization']:
            print("ℹ️  自动跳过偏振调节")
            return
        
        if_polar = input("\n是否需要调节偏振? [y|n] (默认n): ")
        if if_polar in "Yy":
            print("\n请连接DUT, 即将开始调节偏振。")
            polar_wl = self.validator.get_valid_input(
                "请输入监测波长 [nm]: ",
                "监测波长",
                expected_type='float',
                value_range=(1480, 1640)
            )
            print("正在读取光功率...按ENTER键退出监测...")
            self.utility.monitor_power_loop(ilsts, polar_wl)
        else:
            print("跳过偏振调节步骤。")
    
    def perform_quick_initialization(self, ilsts):
        """快速初始化 - 自动模式专用"""
        if not self.auto_mode:
            return False      
        print("🚀 快速初始化中...")
        
        try:
            # 自动配置参考测量参数
            tsl = self.device_manager.tsl
            previous_params = self.param_config.configure_sweep_parameters(
                tsl, ilsts, 'ref', auto_mode=True
            )
            
            # 自动加载参考测量
            self.perform_reference_measurement(ilsts)
            
            # 自动跳过偏振调节
            self.perform_polarization_adjustment(ilsts)

            # 电压控制器初始化 - 简化处理
            voltage_success, config_type = self.device_manager.initialize_voltage_controller(
                self.validator, 
                auto_mode=True
            )
            
            if voltage_success:
                config_status = {
                    "auto_config": "✅ 电压控制器自动配置成功",
                    "auto_fallback": "🔄 电压控制器配置成功（使用新配置）", 
                    "interactive": "🔧 电压控制器配置成功"
                }
                print(config_status.get(config_type, "✅ 电压控制器配置成功"))
            else:
                print("⚠️ 电压控制器初始化失败，将进行无电压控制的操作")
            
            print("✅ 快速初始化完成")
            return True
            
        except Exception as e:
            print(f"❌ 快速初始化失败: {e}")
            return False

    def select_objective_function(self, ilsts, voltage_controller):
        """选择目标函数"""
        print("\n请选择目标函数构建方式: ")
        print("1. 基于光谱构建目标函数")
        print("2. 基于有限波长构建目标函数")
        
        object_type = self.validator.get_valid_input(
            "\n请输入选项 (1/2, 默认为1): ",
            "目标函数构建方式",
            expected_type='int',
            value_range=(1, 2),
            default=1
        )
        
        if object_type == 1:
            return self._select_spectral_function(ilsts, voltage_controller)
        else:
            return self._select_finite_lambda_function(ilsts, voltage_controller)
    
    def _select_spectral_function(self, ilsts, voltage_controller):
        """选择光谱目标函数"""
        # 修复：传递正确的参数
        tsl = self.device_manager.tsl
        self.param_config.configure_sweep_parameters(tsl, ilsts, 'opt')
        spectral_funcs = SpectralFunctions(ilsts, voltage_controller)
        num_funcs = spectral_funcs.display_function_info()
        
        func_choice = self.validator.get_valid_input(
            f"请选择目标函数编号 (1-{num_funcs}): ",
            "目标函数",
            expected_type='int',
            value_range=(1, num_funcs)
        )
        
        return spectral_funcs.get_function_by_index(func_choice)
    
    def _select_finite_lambda_function(self, ilsts, voltage_controller):
        """选择有限波长目标函数"""
        finite_lambda_funcs = FiniteLambdaFunctions(ilsts, voltage_controller)
        num_funcs = finite_lambda_funcs.display_function_info()
        
        func_choice = self.validator.get_valid_input(
            f"请选择目标函数编号 (1-{num_funcs}): ",
            "目标函数",
            expected_type='int',
            value_range=(1, num_funcs)
        )
        
        return finite_lambda_funcs.get_function_by_index(func_choice)
    
    def configure_voltage_parameters(self, num_channels):
        """配置电压参数"""
        print(f"\n系统检测到 {num_channels} 个可用电压端口")
        
        # 选择通道
        selected_channels = self.validator.get_valid_input(
            f"请输入要使用的电压通道编号 [1-{num_channels}] (空格分隔，默认全部): ",
            "电压通道",
            expected_type='int_list',
            value_range=(1, num_channels),
            min_count=1,
            max_count=num_channels,
            default=list(range(1, num_channels + 1))
        )
        selected_channels = [ch - 1 for ch in selected_channels]
        
        # 配置电压范围
        print(f"\n正在配置选中的 {len(selected_channels)} 个电压通道的范围:")
        active_bounds = []
        for channel_index in selected_channels:
            print(f"\n正在配置端口 {channel_index + 1} 的电压范围:")
            
            start_voltage = self.validator.get_valid_input(
                "起始电压 (≥0.0V, 默认0.0V): ",
                "起始电压",
                expected_type='float',
                value_range=(0, 10),
                default=0.0
            )
            
            stop_voltage = self.validator.get_valid_input(
                "结束电压 (≥起始电压, 默认5.0V): ",
                "结束电压",
                expected_type='float',
                value_range=(start_voltage, 10),
                default=5.0
            )
            
            active_bounds.append((start_voltage, stop_voltage))
        
        return {
            'selected_channels': selected_channels,
            'active_bounds': active_bounds,
            'num_channels': num_channels
        }
    
    def select_work_mode(self):
        """选择工作模式"""
        print("\n请选择电压控制模式:")
        print("1. 粒子群优化 - 使用粒子群算法自动寻找最佳电压")
        print("2. 贝叶斯优化 - 使用高斯过程回归进行全局优化")
        print("3. 电压遍历 - 指定范围内的所有电压组合进行遍历")
        print("4. 快速扫描 - 逐个扫描指定通道电压")
        print("5. 直接赋值 - 输入固定电压")
        
        work_mode = self.validator.get_valid_input(
            "\n请输入选项 (1-5, 默认为1): ",
            "电压控制模式",
            expected_type='int',
            value_range=(1, 5),
            default=1
        )
        return str(work_mode)  # 转换为字符串以保持兼容性
    
    def execute_direct_voltage_assignment(self, num_channels):
        """执行直接电压赋值"""
        print("\n=== 配置固定电压参数 ===")
        # 询问run_id
        run_id = self.validator.get_valid_input(
            "请输入电压赋值运行ID (默认为1): ",
            "运行ID",
            expected_type='int',
            value_range=(1, 100),
            default=1
        )

        best_voltage = [0.0] * num_channels
        
        selected_channels = self.validator.get_valid_input(
            f"请输入要配置的端口 [1-{num_channels}]: ",
            "电压端口",
            expected_type='int_list',
            value_range=(1, num_channels),
            min_count=1,
            max_count=num_channels
        )
        selected_channels = [ch - 1 for ch in selected_channels]
        
        for channel_index in selected_channels:
            voltage = self.validator.get_valid_input(
                f"请输入端口 {channel_index + 1} 的电压值 (默认0.0V): ",
                "电压值",
                expected_type='float',
                value_range=(0, 10),
                default=0.0
            )
            best_voltage[channel_index] = voltage
        
        voltage_dir = self.save_voltage_assignment_config(best_voltage, run_id)
        
        return {'voltages': best_voltage, 
                'run_dir': voltage_dir}
    
    def save_voltage_assignment_config(self, voltage_values, run_id=1):
        """保存直接电压赋值配置到TXT文件
        
        Args:
            voltage_values: 电压值列表
            run_id: 运行ID
            
        Returns:
            str: 创建的目录路径
        """
        import os
        import datetime
        
        # 创建目录
        voltage_dir = f"./voltage_assignment_runs/run_{run_id}"
        if not os.path.exists(voltage_dir):
            os.makedirs(voltage_dir, exist_ok=True)
            print(f"📁 创建电压赋值目录: {voltage_dir}")
        
        # 保存TXT文件
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        txt_file = os.path.join(voltage_dir, f"voltage_config_run{run_id}_{timestamp}.txt")
        
        with open(txt_file, 'w', encoding='utf-8') as f:
            f.write(f"电压赋值配置 - 运行{run_id}\n")
            f.write("=" * 50 + "\n")
            f.write(f"创建时间: {timestamp}\n")
            f.write(f"运行ID: {run_id}\n\n")
            
            f.write("电压配置:\n")
            f.write("-" * 30 + "\n")
            for i, voltage in enumerate(voltage_values):
                f.write(f"通道 {i+1}: {voltage:.3f} V\n")
            
            f.write("\n备注:\n")
            f.write("-" * 30 + "\n")
            f.write("直接电压赋值模式\n")
            f.write(f"总通道数: {len(voltage_values)}\n")
        
        print(f"✅ 电压配置已保存到: {txt_file}")
        return voltage_dir
    
    def should_perform_spectrum_sweep(self):
        """询问是否进行光谱扫描"""
        response = input("\n是否继续进行光谱扫描? [y|n] (默认为n): ")
        return response in "Yy"
    
    def perform_spectrum_sweep(self, ilsts):
        """执行光谱扫描"""
        print("\n正在进行DUT光谱测量")
        tsl = self.device_manager.tsl
        self.param_config.configure_sweep_parameters(tsl, ilsts, 'scan')
        ilsts.sts_measurement()
        self.visualizer.plot_scan_data(ilsts)
        ilsts.get_dut_data()
        self.file_manager.save_measure_data(ilsts)

# ========== 优化器工厂类 ==========
class OptimizerFactory:
    """优化器工厂类"""
    def __init__(self, validator):
        self.validator = validator
    
    def create_optimizer(self, work_mode, active_bounds, selected_channels, num_channels, 
                        ilsts, voltage_controller, objective_func):
        """创建优化器"""
        run_id = self._get_run_id()
        
        if work_mode == "1":  # PSO
            optimizer = self._create_pso(active_bounds, selected_channels, num_channels, run_id)
            optimizer_type = 'PSO'
            adapter = OptimizationAdapter(
                optimizer=optimizer,
                objective_func=objective_func,
                optimizer_type=optimizer_type,
                run_id=run_id,
                active_channels=selected_channels,
                total_channels=num_channels
            )
            return adapter, optimizer_type
            
        elif work_mode == "2":  # Bayesian
            optimizer = self._create_bayesian(active_bounds, selected_channels, num_channels, run_id)
            optimizer_type = 'Bayesian'
            adapter = OptimizationAdapter(
                optimizer=optimizer,
                objective_func=objective_func,
                optimizer_type=optimizer_type,
                run_id=run_id,
                active_channels=selected_channels,
                total_channels=num_channels
            )
            return adapter, optimizer_type
            
        elif work_mode == "3":  # Iterator
            return self._create_iterator(active_bounds, selected_channels, num_channels, 
                                       run_id, ilsts, voltage_controller, objective_func), 'Iterator'
        elif work_mode == "4":  # QuickSearcher
            return self._create_quick_searcher(active_bounds, selected_channels, num_channels, 
                                             run_id, ilsts, voltage_controller, objective_func), 'QuickSearcher'
        else:
            raise ValueError(f"不支持的优化模式: {work_mode}")
    
    def _get_run_id(self):
        """获取通用参数"""
        run_id = self.validator.get_valid_input(
            "\n输入运行ID (默认为1): ", 
            "运行ID",
            expected_type='int', 
            value_range=(1, 100), 
            default=1
        )
        return run_id
    
    def _create_pso(self, active_bounds, selected_channels, num_channels, run_id):
        """创建PSO优化器"""
        print("\n=== 配置粒子群优化参数 ===")
        
        particle_num = self.validator.get_valid_input(
            "输入每代粒子个数 (≥5, 默认为15): ",
            "粒子个数",
            expected_type='int',
            value_range=(5, 100),
            default=15
        )
        
        max_iter = self.validator.get_valid_input(
            "输入最大迭代次数 (≥5, 默认为30): ",
            "最大迭代次数", 
            expected_type='int',
            value_range=(5, 200),
            default=30
        )
        
        print("\n按ENTER键开始PSO优化")
        input()
        
        return PSO(
            bounds=active_bounds,
            param_names=[f'V{i+1}' for i in selected_channels],
            integer_params=[],
            run_id=run_id,
            num_particles=particle_num,
            max_iter=max_iter
        )
    
    def _create_bayesian(self, active_bounds, selected_channels, num_channels, run_id):
        """创建贝叶斯优化器"""
        print("\n=== 配置贝叶斯优化参数 ===")
        
        n_init = self.validator.get_valid_input(
            "输入初始采样点数量 (≥10, 默认为15): ",
            "初始采样点数量",
            expected_type='int',
            value_range=(10, 50),
            default=15
        )
        
        max_iter = self.validator.get_valid_input(
            "输入最大迭代次数 (≥5, 默认为50): ",
            "最大迭代次数",
            expected_type='int', 
            value_range=(5, 500),
            default=50
        )

        early_stop = self.validator.get_valid_input(
            "输入早停忍耐次数 (≥10, 默认为20): ",
            "早停忍耐次数",
            expected_type='int', 
            value_range=(10, 50),
            default=20
        )

        exploration_factor = self.validator.get_valid_input(
            "输入探索因子 (0~1, 越大越倾向探索, 默认0.6): ",
            "探索因子",
            expected_type='float', 
            value_range=(0, 1),
            default=0.6
        )

        local_ratio = self.validator.get_valid_input(
            "输入局部因子 (0~1, 越大越倾向局部, 默认0.4): ",
            "局部因子",
            expected_type='float', 
            value_range=(0, 1),
            default=0.4
        )
        
        print("\n按ENTER键开始贝叶斯优化")
        input()
        
        return Bayesian(
            bounds=active_bounds,
            param_names=[f'V{i+1}' for i in selected_channels],
            integer_params=[],
            run_id=run_id,
            n_init=n_init,
            n_iter=max_iter,
            early_stopping_patience=early_stop,
            exploration_factor=exploration_factor,
            local_ratio=local_ratio
        )
    
    def _create_iterator(self, active_bounds, selected_channels, num_channels, run_id, 
                        ilsts, voltage_controller, objective_func):
        """创建遍历扫描器"""
        print("\n=== 配置遍历扫描参数 ===")
        active_steps = self._get_voltage_steps(selected_channels)
        
        return Iterator(
            ilsts,
            voltage_controller,
            objective_func,
            bounds=active_bounds,
            steps_per_dimension=active_steps,
            run_id=run_id,
            active_channels=selected_channels,
            total_channels=num_channels
        )
    
    def _create_quick_searcher(self, active_bounds, selected_channels, num_channels, run_id, 
                              ilsts, voltage_controller, objective_func):
        """创建快速扫描器"""
        print("\n=== 配置快速扫描参数 ===")
        active_steps = self._get_voltage_steps(selected_channels)

        return QuickSearcher(
            ilsts,
            voltage_controller,
            objective_func,
            bounds=active_bounds,
            steps_per_dimension=active_steps,
            run_id=run_id,
            active_channels=selected_channels,
            total_channels=num_channels
        )
    
    def _get_voltage_steps(self, selected_channels):
        """获取电压步数配置"""
        active_steps = []
        for channel_index in selected_channels:
            steps = self.validator.get_valid_input(
                f"请输入端口 {channel_index + 1} 的扫描步数 (默认11): ",
                "扫描步数",
                expected_type='int',
                value_range=(1, 1000),
                default=11
            )
            active_steps.append(steps)
        return active_steps
    
# ========== 主函数 ==========
def MAIN() -> None:
    """ 主函数 - 流程化运行和回溯 """
    # 初始化管理器
    validator = InputValidator()
    device_manager = DeviceManager()
    param_config = ParameterConfigurator(validator)

    # 快速配置选项
    print("=== 可编程光子智能测试系统 ===")
    print("1. 快速模式 (使用历史配置，推荐后续使用)")
    print("2. 完整模式 (完整交互，推荐首次使用)")
    auto_mode_choice = validator.get_valid_input("\n请输入选项 (1-2): ",
                                            "快速启动",
                                            expected_type='int',
                                            value_range=(1, 2)
                                        )
    auto_mode = (auto_mode_choice == 1)
    if auto_mode:
        print("🚀 快速模式 - 使用历史配置")
        # 检查历史配置是否存在
        if not os.path.exists(file_saving.FILE_LAST_REF_PARAMS):
            print("⚠️ 未找到历史配置，自动切换到完整模式")
            auto_mode = False
    else:
        print("🔧 完整模式 - 完整交互流程")    
    
    workflow_manager = WorkflowManager(validator, 
                                       param_config, 
                                       device_manager, 
                                       auto_mode = auto_mode)
    
    # 状态变量
    current_work_mode = None
    current_voltage_params = None
    current_objective_function = None
    current_best_voltage = None
    current_run_dir = None
    ilsts = None
    voltage_initialized = False
    
    def initialize_system():
        """初始化系统"""
        nonlocal ilsts, voltage_initialized
        print("步骤 1: 初始化光设备...")
        ilsts = device_manager.initialize_optical_devices()

        # 使用快速初始化（如果启用自动模式）
        if auto_mode:
            print("🚀 执行快速初始化...")
            success = workflow_manager.perform_quick_initialization(ilsts)
            if success:
                print("✅ 快速初始化完成")
                voltage_initialized = (device_manager.voltage_controller is not None)
                return True
            else: 
                print("⚠️ 快速初始化失败，使用完整流程")
        
        print("\n步骤 2: 配置参考测量参数...")
        previous_params = param_config.configure_sweep_parameters(device_manager.tsl, ilsts, 'ref')
        workflow_manager.perform_reference_measurement(ilsts, previous_params)
        workflow_manager.perform_polarization_adjustment(ilsts)
        
        print("\n步骤 3: 初始化电压控制器...")
        voltage_initialized, _ = device_manager.initialize_voltage_controller(validator, auto_mode=False)
        return True
    
    def select_objective_function():
        """选择目标函数"""
        nonlocal current_objective_function
        print("\n步骤 4: 选择目标函数...")
        selected_function, function_info = workflow_manager.select_objective_function(
            ilsts, device_manager.voltage_controller
        )
        current_objective_function = selected_function
        # print(f"✅ 目标函数选择完成: {function_info}")
        return True
    
    def select_algorithm():
        """选择优化算法"""
        nonlocal current_work_mode
        print("\n步骤 5: 选择工作模式...")
        current_work_mode = workflow_manager.select_work_mode()
        print(f"✅ 算法选择完成: {get_algorithm_name(current_work_mode)}")
        return True
    
    def run_optimization(optimizer, work_mode):
        """运行优化器"""
        nonlocal current_best_voltage
        
        print("\n按ENTER键开始优化...")
        input()
        
        if work_mode in ["1", "2"]:  # PSO 或 Bayesian
            best_voltage, best_fitness, result = optimizer.optimize()
            current_best_voltage = best_voltage
            return best_voltage is not None
            
        elif work_mode in ["3", "4"]:  # Iterator 或 QuickSearcher
            best_result = optimizer.run_scan()
            current_best_voltage = best_result['actual_voltages'] if best_result else None
            return current_best_voltage is not None
            
        return False
    
    def configure_voltage_parameters():
        """配置电压参数"""
        nonlocal current_voltage_params
        print("\n步骤 6: 配置电压参数...")
        current_voltage_params = workflow_manager.configure_voltage_parameters(
            device_manager.num_channels
        )
        return True
    
    def perform_spectral_sweep():
        """执行光谱扫描"""
        if workflow_manager.should_perform_spectrum_sweep():
            print("\n执行光谱扫描...")
            workflow_manager.perform_spectrum_sweep(ilsts)
            return True
        return False
    
    def set_optimal_voltage():
        """设置最佳电压"""
        if current_best_voltage:
            success = device_manager.voltage_controller.set_voltages(current_best_voltage)
            if success:
                print("✅ 最佳电压设置成功")
                return True
            else:
                print("❌ 电压设置失败")
        return False
    
    def show_menu():
        """显示菜单"""
        print("\n" + "="*50)
        print("🎉 当前流程运行完成！")
        print("="*50)
        print("请选择下一步操作：")
        print("1. 重新配置优化器参数并重新运行")
        print("2. 更换优化算法")
        print("3. 重新选择目标函数") 
        print("4. 退出程序")
        print("="*50)
        
        choice = validator.get_valid_input("\n请输入选项 (1-4): ",
                                            "菜单选项",
                                            expected_type='int',
                                            value_range=(1, 4)
                                        )
        return str(choice)
    
    def get_algorithm_name(work_mode):
        """获取算法名称"""
        algorithm_names = {
            "1": "粒子群优化",
            "2": "贝叶斯优化", 
            "3": "电压遍历",
            "4": "快速扫描",
            "5": "直接电压赋值"
        }
        return algorithm_names.get(work_mode, "未知算法")
    
    # 主程序循环
    program_state = "INIT"  # INIT, OBJECTIVE_SELECTED, ALGORITHM_SELECTED, VOLTAGE_CONFIGURED, OPTIMIZATION_DONE
    
    try:
        while True:
            if program_state == "INIT":
                # 初始状态：运行完整的光系统初始化
                if not initialize_system():
                    print("❌ 光系统初始化失败，程序退出")
                    break
                if not voltage_initialized:
                    # 无电压控制，直接进行光谱扫描
                    print("⚠️  未初始化电压控制，直接进行光谱扫描")
                    program_state = "OPTIMIZATION_DONE"
                else:
                    program_state = "INITIALIZED"
                continue
            
            elif program_state == "INITIALIZED":
                # 光系统已初始化：正在选择目标函数
                if select_objective_function():
                    program_state = "OBJECTIVE_SELECTED"
                continue
            
            elif program_state == "OBJECTIVE_SELECTED":
                # 目标函数已选择：正在选择算法
                if select_algorithm():
                    program_state = "ALGORITHM_SELECTED"
                continue
            
            elif program_state == "ALGORITHM_SELECTED":
                # 算法已选择：正在配置电压参数
                if current_work_mode == "5":
                    # 直接电压赋值
                    voltage_result = workflow_manager.execute_direct_voltage_assignment(
                        device_manager.num_channels
                    )
                    current_best_voltage = voltage_result['voltages']
                    current_run_dir = voltage_result['run_dir']
                    program_state = "OPTIMIZATION_DONE"
                else:
                    if configure_voltage_parameters():
                        program_state = "VOLTAGE_CONFIGURED"
                continue
            
            elif program_state == "VOLTAGE_CONFIGURED":
                # 电压参数已配置：正在配置优化器参数并运行
                optimizer_factory = OptimizerFactory(validator)
                optimizer, optimizer_type = optimizer_factory.create_optimizer(
                    work_mode = current_work_mode,
                    active_bounds = current_voltage_params['active_bounds'],
                    selected_channels = current_voltage_params['selected_channels'],
                    num_channels = current_voltage_params['num_channels'],
                    ilsts = ilsts,
                    voltage_controller = device_manager.voltage_controller,
                    objective_func = current_objective_function
                )

                if optimizer and hasattr(optimizer, 'run_dir'):
                    current_run_dir = optimizer.run_dir
                    print(f"📁 优化器目录已记录: {current_run_dir}")
                if optimizer and run_optimization(optimizer, current_work_mode):
                    print("✅ 优化完成")
                    program_state = "OPTIMIZATION_DONE"
                else:
                    print("❌ 优化失败，请重新选择算法")
                    program_state = "ALGORITHM_SELECTED"
                continue
            
            elif program_state == "OPTIMIZATION_DONE":
                # 优化已完成：展示光谱结果，显示菜单选择下一步
                if voltage_initialized: 
                    set_optimal_voltage()
                perform_spectral_sweep()

                if current_run_dir:
                    success = file_saving.move_spectrum_files_to_directory(
                                            target_dir = current_run_dir,
                                            measurement_file = file_saving.FILE_MEASUREMENT_DATA_RESULTS,
                                            dut_file = file_saving.FILE_DUT_DATA_RESULTS
                                            )
                    if success:
                        print("✅ 光谱文件已成功移动到优化器目录")
                
                device_manager.rst_optical()
                input("\n输入ENTER退出本轮优化")

                # 电压清零
                device_manager.utility.zero_all_ports(
                        device_manager.voltage_controller, 
                        device_manager.num_channels)
                # 还原到优化所用参数
                param_config.configure_sweep_parameters(
                        device_manager.tsl, 
                        ilsts, 
                        'opt',
                        auto_mode = True)
                
                choice = show_menu()
                if choice == '1':
                    # 重新配置优化器参数并重新运行
                    print("\n=== 重新配置优化器参数 ===")
                    program_state = "ALGORITHM_SELECTED"
                elif choice == '2':
                    # 更换算法：回到算法选择状态
                    print("\n=== 更换算法 ===")
                    program_state = "OBJECTIVE_SELECTED"
                elif choice == '3':
                    # 重新选择目标函数：回到目标函数选择状态
                    print("\n=== 重新选择目标函数 ===")
                    program_state = "INITIALIZED"
                elif choice == '4':
                    # 退出程序
                    print("👋 感谢使用，程序退出！")
                    break
            else:
                print("❌ 未知的程序状态，程序退出")
                break
                
    except KeyboardInterrupt:
        print("\n\n⚠️ 检测到用户中断，程序退出")
    except Exception as e:
        print(f"\n\n❌ 程序出现未预期异常: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # 系统关闭
        print("\n正在关闭系统...")
        device_manager.shutdown()
        print("程序已安全退出\n")

if __name__ == "__main__":
    MAIN()
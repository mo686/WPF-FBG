"""激光器控制器模块

本模块提供了控制激光器波长和输出功率的功能，基于 Santec TSL 仪器。
"""

import logging
from typing import Optional, Dict, Any, List
import time

# 配置日志（减少日志输出）
logging.basicConfig(level=logging.WARNING, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 导入 TSL 相关模块
try:
    from santec.tsl_instrument_class import TslInstrument, InstrumentError
    from santec.get_address import GetAddress, Instrument
    from zynq_voltage_controller import ZynqVoltageController
except ImportError as e:
    logger.error(f"无法导入相关模块: {e}")
    raise

class LaserController:
    """激光器控制器类
    
    提供控制激光器波长和输出功率的功能，以及电压扫描和评价
    """
    
    def __init__(self):
        """初始化激光器控制器"""
        self.tsl = None
        self.connected = False
        self.wavelength_range = (1500, 1650)  # 波长范围 (nm)
        self.power_range = (-10, 10)  # 功率范围 (dBm)
        self.current_wavelength = None  # 存储当前波长
        self.current_power = None  # 存储当前功率
        self.voltage_controller = None  # 电压控制器
        self.voltage_connected = False  # 电压控制器连接状态
    
    def connect(self) -> bool:
        """连接到激光器
        
        返回:
            bool: 连接是否成功
        """
        try:
            print("正在连接到激光器...")
            
            # 检测可用的仪器
            get_address = GetAddress()
            
            # 初始化仪器地址，自动选择模式
            get_address.initialize_instrument_addresses(connection_configuration="GPIB", auto_select=True)
            
            # 获取 TSL 仪器地址
            tsl_instrument = get_address.get_tsl_address()
            
            print(f"找到 TSL 仪器: {tsl_instrument.ProductName}, 资源: {tsl_instrument.ResourceValue}")
            
            # 根据接口类型创建 TSL 仪器实例
            interface = tsl_instrument.Interface.upper()
            if interface == "GPIB":
                self.tsl = TslInstrument(
                    interface="GPIB",
                    instrument=tsl_instrument
                )
            elif interface == "USB":
                self.tsl = TslInstrument(
                    interface="USB",
                    instrument=tsl_instrument
                )
            else:
                print(f"不支持的接口类型: {interface}")
                return False
            
            # 连接到设备
            self.tsl.connect()
            
            # 连接成功
            self.connected = True
            print(f"激光器连接成功 ({interface})")
            
            return True
        except Exception as e:
            print(f"连接激光器失败: {e}")
            self.connected = False
            return False
    
    def initialize_voltage_controller(self) -> bool:
        """初始化电压控制器
        
        返回:
            bool: 初始化是否成功
        """
        try:
            print("初始化电压控制器...")
            # 创建控制器实例
            self.voltage_controller = ZynqVoltageController(port='COM3', num_channels=4)  # Windows系统通常使用COM端口
            
            # 初始化连接
            if not self.voltage_controller.initialize():
                print("控制器初始化失败")
                return False
            
            self.voltage_connected = True
            print("电压控制器初始化成功")
            return True
        except Exception as e:
            print(f"初始化电压控制器失败: {e}")
            self.voltage_connected = False
            return False
    
    def set_power(self, power: float) -> bool:
        """设置激光器输出功率
        
        参数:
            power: 输出功率，单位 dBm
            
        返回:
            bool: 设置是否成功
        """
        if not self.connected:
            print("激光器未连接")
            return False
        
        try:
            # 验证功率范围
            if not (self.power_range[0] <= power <= self.power_range[1]):
                print(f"功率超出范围 {self.power_range[0]}-{self.power_range[1]} dBm: {power} dBm")
                return False
            
            print(f"设置激光器功率: {power} dBm")
            self.tsl.set_power(power)
            self.current_power = power  # 更新当前功率
            print("功率设置成功")
            return True
        except Exception as e:
            print(f"设置功率失败: {e}")
            return False
    
    def set_wavelength(self, wavelength: float) -> bool:
        """设置激光器波长
        
        参数:
            wavelength: 波长，单位 nm
            
        返回:
            bool: 设置是否成功
        """
        if not self.connected:
            print("激光器未连接")
            return False
        
        try:
            # 验证波长范围
            if not (self.wavelength_range[0] <= wavelength <= self.wavelength_range[1]):
                print(f"波长超出范围 {self.wavelength_range[0]}-{self.wavelength_range[1]} nm: {wavelength} nm")
                return False
            
            print(f"设置激光器波长: {wavelength} nm")
            self.tsl.set_wavelength(wavelength)
            self.current_wavelength = wavelength  # 更新当前波长
            print("波长设置成功")
            return True
        except Exception as e:
            print(f"设置波长失败: {e}")
            return False
    
    def get_power(self) -> Optional[float]:
        """获取当前激光器功率
        
        返回:
            float: 当前功率值，单位 dBm；如果未连接返回 None
        """
        if not self.connected:
            print("激光器未连接")
            return None
        
        try:
            # 获取功率值
            power = self.tsl.power
            self.current_power = power  # 更新当前功率
            print(f"当前功率: {power} dBm")
            return power
        except Exception as e:
            # 如果直接获取失败，返回缓存的功率值
            if self.current_power is not None:
                print(f"当前功率: {self.current_power} dBm")
                return self.current_power
            print(f"获取功率失败: {e}")
            return None
    
    def get_wavelength(self) -> Optional[float]:
        """获取当前激光器波长
        
        返回:
            float: 当前波长值，单位 nm；如果未连接返回 None
        """
        if not self.connected:
            print("激光器未连接")
            return None
        
        try:
            # 尝试直接获取波长值
            # 注意：TSL 类可能没有 wavelength 属性，需要使用其他方法
            # 这里使用缓存的波长值
            if self.current_wavelength is not None:
                print(f"当前波长: {self.current_wavelength} nm")
                return self.current_wavelength
            else:
                print("未设置波长")
                return None
        except Exception as e:
            # 如果获取失败，返回缓存的波长值
            if self.current_wavelength is not None:
                print(f"当前波长: {self.current_wavelength} nm")
                return self.current_wavelength
            print(f"获取波长失败: {e}")
            return None
    
    def get_scan_parameters(self):
        """获取电压扫描参数"""
        while True:
            try:
                start_voltage = float(input("请输入起始电压 (V) [0-10]: "))
                if 0 <= start_voltage <= 10:
                    break
                else:
                    print("电压值必须在 0V 到 10V 之间")
            except ValueError:
                print("请输入有效的数字")
        
        while True:
            try:
                end_voltage = float(input("请输入结束电压 (V) [0-10]: "))
                if 0 <= end_voltage <= 10:
                    break
                else:
                    print("电压值必须在 0V 到 10V 之间")
            except ValueError:
                print("请输入有效的数字")
        
        while True:
            try:
                step_voltage = float(input("请输入步进电压 (V) [0.01-1]: "))
                if 0.01 <= step_voltage <= 1:
                    break
                else:
                    print("步进电压必须在 0.01V 到 1V 之间")
            except ValueError:
                print("请输入有效的数字")
        
        while True:
            try:
                channel = int(input("请输入控制通道 (1-4): "))
                if 1 <= channel <= 4:
                    break
                else:
                    print("通道号必须在 1 到 4 之间")
            except ValueError:
                print("请输入有效的数字")
        
        return start_voltage, end_voltage, step_voltage, channel
    
    def get_user_evaluation(self, voltage):
        """获取用户评价
        
        参数:
            voltage: 当前电压值
            
        返回:
            float: 用户评价值
        """
        while True:
            try:
                score = float(input(f"请为电压 {voltage:.3f}V 给出评价值 (0-10): "))
                if 0 <= score <= 10:
                    return score
                else:
                    print("评价值必须在 0 到 10 之间")
            except ValueError:
                print("请输入有效的数字")
    
    def set_voltage(self, channel: int, voltage: float) -> bool:
        """设置单个通道的电压
        
        参数:
            channel: 通道号 (1-4)
            voltage: 电压值 (0-10 V)
            
        返回:
            bool: 设置是否成功
        """
        if not self.voltage_connected:
            if not self.initialize_voltage_controller():
                return False
        
        try:
            # 验证通道范围
            if not (1 <= channel <= 4):
                print(f"通道号必须在 1-4 之间: {channel}")
                return False
            
            # 验证电压范围
            if not (0 <= voltage <= 10):
                print(f"电压值必须在 0-10 V 之间: {voltage} V")
                return False
            
            # 获取当前电压状态
            current_voltages = self.voltage_controller.current_voltages.copy()
            
            # 设置目标电压
            target_voltages = current_voltages.copy()
            target_voltages[channel-1] = voltage  # 通道索引从0开始
            
            print(f"设置通道 {channel} 电压: {voltage:.3f}V")
            success = self.voltage_controller.set_voltages(target_voltages)
            
            if success:
                print("电压设置成功")
                return True
            else:
                print("电压设置失败")
                return False
        except Exception as e:
            print(f"设置电压失败: {e}")
            return False
    
    def run_voltage_scan(self):
        """运行电压扫描与评价"""
        if not self.connected:
            print("激光器未连接，无法运行电压扫描")
            return
        
        if not self.voltage_connected:
            if not self.initialize_voltage_controller():
                return
        
        # 获取扫描参数
        start_voltage, end_voltage, step_voltage, channel = self.get_scan_parameters()
        
        # 计算电压步进点
        if start_voltage <= end_voltage:
            voltage_range = range(int(start_voltage / step_voltage), int(end_voltage / step_voltage) + 1)
            voltages = [i * step_voltage for i in voltage_range]
            # 确保包含终止电压
            if voltages[-1] < end_voltage:
                voltages.append(end_voltage)
        else:
            voltage_range = range(int(start_voltage / step_voltage), int(end_voltage / step_voltage) - 1, -1)
            voltages = [i * step_voltage for i in voltage_range]
            # 确保包含终止电压
            if voltages[-1] > end_voltage:
                voltages.append(end_voltage)
        
        print(f"\n开始对通道 {channel} 进行电压扫描")
        print(f"电压范围: {start_voltage}V 到 {end_voltage}V, 步进: {step_voltage}V")
        print(f"总共需要测试 {len(voltages)} 个电压点\n")
        
        # 初始化最佳电压和评分
        best_voltage = start_voltage
        best_score = float('-inf')
        score_history = []
        
        # 获取当前的电压状态以便恢复
        original_voltages = self.voltage_controller.current_voltages.copy()
        
        # 执行扫描
        for i, voltage in enumerate(voltages):
            print(f"[{i+1}/{len(voltages)}] 设置电压: {voltage:.3f}V")
            
            # 设置当前电压
            target_voltages = original_voltages.copy()
            target_voltages[channel-1] = voltage  # 通道索引从0开始
            
            if not self.voltage_controller.set_voltages(target_voltages):
                print(f"  设置电压 {voltage}V 失败，跳过此点")
                continue
            
            # 等待电压稳定
            time.sleep(0.5)
            
            # 获取用户评价
            user_score = self.get_user_evaluation(voltage)
            
            # 记录评分
            score_history.append((voltage, user_score))
            
            # 更新最佳电压和评分
            if user_score > best_score:
                best_score = user_score
                best_voltage = voltage
                print(f"  -> 新的最佳评分! 电压: {best_voltage:.3f}V, 评分: {best_score}")
            else:
                print(f"  当前最佳: {best_voltage:.3f}V (评分: {best_score})")
            
            print()  # 空行分隔
        
        # 扫描完成
        print("="*50)
        print(f"电压扫描完成!")
        print(f"最佳电压: {best_voltage:.3f}V")
        print(f"对应评分: {best_score}")
        print("="*50)
        
        # 显示评分历史
        show_history = input("是否显示完整的评分历史? (y/n): ").lower() == 'y'
        if show_history:
            print("\n评分历史:")
            print("电压(V)\t\t评分")
            print("-"*20)
            for voltage, score in score_history:
                marker = " <- 最佳" if voltage == best_voltage else ""
                print(f"{voltage:.3f}\t\t{score}{marker}")
        
        # 恢复原始电压
        print("\n恢复原始电压...")
        if not self.voltage_controller.set_voltages(original_voltages):
            print("恢复原始电压失败")
        else:
            print("原始电压恢复成功")
    
    def disconnect(self) -> bool:
        """断开激光器连接
        
        返回:
            bool: 断开是否成功
        """
        if not self.connected:
            print("激光器未连接")
            return True
        
        try:
            print("正在断开激光器连接...")
            self.tsl.disconnect()
            self.connected = False
            print("激光器连接已断开")
            
            # 断开电压控制器
            if self.voltage_connected:
                print("断开电压控制器连接...")
                # 这里可以添加断开电压控制器的代码
                self.voltage_connected = False
                print("电压控制器连接已断开")
            
            return True
        except Exception as e:
            print(f"断开连接失败: {e}")
            return False
    
    def get_status(self) -> Dict[str, Any]:
        """获取激光器状态
        
        返回:
            Dict: 包含激光器状态的字典
        """
        status = {
            'connected': self.connected,
            'wavelength': self.get_wavelength(),
            'power': self.get_power(),
            'wavelength_range': self.wavelength_range,
            'power_range': self.power_range,
            'voltage_connected': self.voltage_connected
        }
        return status

def get_user_input():
    """获取用户输入的波长和功率"""
    print("=== 激光器参数设置 ===")
    
    # 获取波长输入
    while True:
        try:
            wavelength = float(input("请输入激光器波长 (nm) [1500-1650]: "))
            if 1500 <= wavelength <= 1650:
                break
            else:
                print("波长必须在 1500-1650 nm 范围内")
        except ValueError:
            print("请输入有效的数字")
    
    # 获取功率输入
    while True:
        try:
            power = float(input("请输入输出光功率 (dBm) [-10-10]: "))
            if -10 <= power <= 10:
                break
            else:
                print("功率必须在 -10-10 dBm 范围内")
        except ValueError:
            print("请输入有效的数字")
    
    return wavelength, power

def get_user_choice():
    """获取用户选择的操作"""
    print("\n=== 操作菜单 ===")
    print("1. 调整波长")
    print("2. 调整功率")
    print("3. 查看当前状态")
    print("4. 运行电压扫描")
    print("5. 设置单个通道电压")
    print("6. 退出")
    
    while True:
        try:
            choice = int(input("请选择操作 (1-6): "))
            if 1 <= choice <= 6:
                return choice
            else:
                print("请输入 1-6 之间的数字")
        except ValueError:
            print("请输入有效的数字")

def get_wavelength_input():
    """获取用户输入的波长"""
    while True:
        try:
            wavelength = float(input("请输入激光器波长 (nm) [1500-1650]: "))
            if 1500 <= wavelength <= 1650:
                return wavelength
            else:
                print("波长必须在 1500-1650 nm 范围内")
        except ValueError:
            print("请输入有效的数字")

def get_power_input():
    """获取用户输入的功率"""
    while True:
        try:
            power = float(input("请输入输出光功率 (dBm) [-10-10]: "))
            if -10 <= power <= 10:
                return power
            else:
                print("功率必须在 -10-10 dBm 范围内")
        except ValueError:
            print("请输入有效的数字")

def get_voltage_input():
    """获取用户输入的电压"""
    while True:
        try:
            voltage = float(input("请输入电压值 (V) [0-10]: "))
            if 0 <= voltage <= 10:
                return voltage
            else:
                print("电压必须在 0-10 V 范围内")
        except ValueError:
            print("请输入有效的数字")

def get_channel_input():
    """获取用户输入的通道"""
    while True:
        try:
            channel = int(input("请输入控制通道 (1-4): "))
            if 1 <= channel <= 4:
                return channel
            else:
                print("通道号必须在 1 到 4 之间")
        except ValueError:
            print("请输入有效的数字")

def main():
    """示例代码"""
    print("=== 激光器控制器 ===")
    
    # 创建激光器控制器实例
    laser = LaserController()
    
    # 连接激光器
    if laser.connect():
        print("✅ 激光器连接成功")
        
        # 初始化设置
        wavelength, power = get_user_input()
        
        # 设置初始波长
        if laser.set_wavelength(wavelength):
            print(f"✅ 波长设置成功: {wavelength} nm")
        else:
            print(f"❌ 波长设置失败: {wavelength} nm")
        
        # 设置初始功率
        if laser.set_power(power):
            print(f"✅ 功率设置成功: {power} dBm")
        else:
            print(f"❌ 功率设置失败: {power} dBm")
        
        # 主循环
        while True:
            # 获取用户选择
            choice = get_user_choice()
            
            if choice == 1:
                # 调整波长
                new_wavelength = get_wavelength_input()
                if laser.set_wavelength(new_wavelength):
                    print(f"✅ 波长设置成功: {new_wavelength} nm")
                else:
                    print(f"❌ 波长设置失败: {new_wavelength} nm")
            
            elif choice == 2:
                # 调整功率
                new_power = get_power_input()
                if laser.set_power(new_power):
                    print(f"✅ 功率设置成功: {new_power} dBm")
                else:
                    print(f"❌ 功率设置失败: {new_power} dBm")
            
            elif choice == 3:
                # 查看当前状态
                status = laser.get_status()
                print("\n=== 当前状态 ===")
                print(f"连接状态: {'已连接' if status['connected'] else '未连接'}")
                print(f"当前波长: {status['wavelength']} nm")
                print(f"当前功率: {status['power']} dBm")
                print(f"电压控制器状态: {'已连接' if status['voltage_connected'] else '未连接'}")
            
            elif choice == 4:
                # 运行电压扫描
                laser.run_voltage_scan()
            
            elif choice == 5:
                # 设置单个通道电压
                channel = get_channel_input()
                voltage = get_voltage_input()
                if laser.set_voltage(channel, voltage):
                    print(f"✅ 通道 {channel} 电压设置成功: {voltage:.3f}V")
                else:
                    print(f"❌ 通道 {channel} 电压设置失败: {voltage:.3f}V")
            
            elif choice == 6:
                # 退出
                break
        
        # 断开连接
        if laser.disconnect():
            print("\n✅ 激光器连接已断开")
        else:
            print("\n❌ 断开连接失败")
    else:
        print("❌ 激光器连接失败")
    
    print("\n=== 操作完成 ===")
    input("按 Enter 键退出...")

if __name__ == "__main__":
    main()
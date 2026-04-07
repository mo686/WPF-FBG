import numpy as np
import nidaqmx
from nidaqmx.constants import TerminalConfiguration
import nidaqmx.system

class VoltageController:
    """
    用于控制DAQ设备输出电压的类。
    
    属性:
        device_name (str): DAQ设备名称
        channels (list): 要使用的模拟输出通道列表
    """
    
    def __init__(self, device_name, num_channels=4, start_channel=0):
        """
        初始化电压控制器
        
        参数:
            device_name (str): PXI设备名称，例如"PXI1Slot3"
            num_channels (int): 要使用的通道数量，默认为4
            start_channel (int): 起始通道编号，默认为0
        """
        self.device_name = device_name
        # 根据起始通道和通道数自动生成通道列表
        self.channels = [f"ao{i}" for i in range(start_channel, start_channel + num_channels)]
        self.current_voltages = np.zeros(len(self.channels))
        self.task = None
        
    def initialize(self):
        """初始化DAQ任务"""
        try:
            self.task = nidaqmx.Task()
            # 添加所有通道 - 修改电压范围为0V到10V
            for channel in self.channels:
                self.task.ao_channels.add_ao_voltage_chan(
                    f"{self.device_name}/{channel}",
                    min_val=-16.0,  # PXIe-4322支持±16V
                    max_val=16.0
                )
            return True
        except Exception as e:
            print(f"初始化电压控制器时发生错误: {e}")
            if self.task:
                self.task.close()
                self.task = None
            return False
    
    def set_voltages(self, voltages):
        """
        同时设置多个通道的电压
        
        参数:
            voltages (list): 电压值列表，必须与通道数量一致
        
        返回:
            bool: 设置成功返回True，否则返回False
        """
        if len(voltages) != len(self.channels):
            print(f"错误: 电压值数量({len(voltages)})与通道数量({len(self.channels)})不匹配")
            return False
            
        try:
            if not self.task:
                if not self.initialize():
                    return False
                    
            # 将电压值限制在-16V到16V范围内
            clipped_voltages = np.clip(voltages, -16.0, 16.0)
            self.task.write(clipped_voltages, auto_start=True)
            self.current_voltages = clipped_voltages
            return True
        except Exception as e:
            print(f"设置电压时发生错误: {e}")
            return False
    
    def get_current_voltages(self):
        """获取当前设置的电压值"""
        return self.current_voltages
    
    def close(self):
        """关闭DAQ任务"""
        if self.task:
            self.task.stop()
            self.task.close()
            self.task = None
    
    def __del__(self):
        """在对象被删除时确保关闭任务"""
        self.close()


def test_voltage_controller(device_name):
    """
    测试电压控制器的功能
    
    参数:
        device_name (str): DAQ设备名称
    """
    print("测试电压控制器...")
    controller = VoltageController(device_name)
    
    if controller.initialize():
        print("成功初始化电压控制器")
        
        # 测试设置电压为[1.0, 2.0, 3.0, 4.0]
        test_voltages = [1.0, 2.0, 3.0, 4.0]
        if controller.set_voltages(test_voltages):
            print(f"成功设置电压: {controller.get_current_voltages()}")
        else:
            print("设置电压失败")
        
        # 关闭控制器
        controller.close()
    else:
        print("初始化电压控制器失败")


if __name__ == "__main__":
    # 获取本地系统
    system = nidaqmx.system.System.local()
    devices = list(system.devices)

    if not devices:
        print("未找到DAQ设备")
        exit()

    # 列出所有设备供选择
    print("\n系统中的所有NI-DAQmx设备：")
    for i, device in enumerate(devices):
        print(f"\n设备 {i+1}:")
        print(f"  名称: {device.name}")
        print(f"  产品类型: {device.product_type}")
        
        # 只显示模拟输出通道
        ao_channels = list(device.ao_physical_chans)
        if ao_channels:
            print("  可用的模拟输出通道:")
            for channel in ao_channels:
                print(f"    - {channel.name}")
        else:
            print("  该设备没有模拟输出通道")
        
        print("---------------------")

    # 让用户选择设备
    while True:
        try:
            device_index = int(input("\n请选择要使用的设备编号 (1-{}): ".format(len(devices)))) - 1
            if 0 <= device_index < len(devices):
                selected_device = devices[device_index]
                # 检查所选设备是否有模拟输出通道
                if list(selected_device.ao_physical_chans):
                    break
                else:
                    print("所选设备没有模拟输出通道，请选择其他设备")
            else:
                print(f"请输入1到{len(devices)}之间的数字")
        except ValueError:
            print("请输入有效的数字")

    # 配置通道参数
    try:
        num_channels = int(input("\n请输入要使用的模拟输出通道数量 (默认为4): ") or "4")
        start_channel = int(input("请输入起始通道编号 (默认为0): ") or "0")
        
        # 验证通道配置是否有效
        available_channels = len(list(selected_device.ao_physical_chans))
        if start_channel + num_channels > available_channels:
            raise ValueError(f"通道配置无效：设备只有{available_channels}个模拟输出通道")
        
        # 创建并测试电压控制器
        print(f"\n使用设备 {selected_device.name} 进行电压控制...")
        controller = VoltageController(selected_device.name, 
                                     num_channels=num_channels,
                                     start_channel=start_channel)
        
        if controller.initialize():
            print("成功初始化电压控制器")
            
            # 让用户输入电压值
            voltages = []
            print("\n请为每个通道输入电压值 (-16V 到 16V):")
            for i in range(num_channels):
                while True:
                    try:
                        voltage = float(input(f"通道 ao{start_channel + i} 的电压值: "))
                        if -16 <= voltage <= 16:
                            voltages.append(voltage)
                            break
                        else:
                            print("电压值必须在 -16V 到 16V 之间")
                    except ValueError:
                        print("请输入有效的数字")
            
            # 设置电压并显示结果
            if controller.set_voltages(voltages):
                print(f"\n成功设置电压: {controller.get_current_voltages()}")
            else:
                print("设置电压失败")
            
            # 关闭控制器
            controller.close()
        else:
            print("初始化电压控制器失败")
            
    except ValueError as e:
        print(f"输入错误: {e}")
    except Exception as e:
        print(f"操作过程中发生错误: {e}")
    finally:
        print("\n电压控制操作结束") 
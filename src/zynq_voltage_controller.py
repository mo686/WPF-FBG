import serial
import time
import struct

class ZynqVoltageController:
    """
    通过串口与Zynq 7020 FPGA通信控制DAC输出电压
    """
    
    def __init__(self, port='/dev/ttyUSB0', baudrate=115200, num_channels=4):
        """
        初始化Zynq FPGA电压控制器
        
        参数:
            port (str): 串口端口名称
            baudrate (int): 波特率
            num_channels (int): 电压通道数
        """
        self.port = port
        self.baudrate = baudrate
        self.num_channels = num_channels
        self.current_voltages = [0.0] * num_channels
        self.serial = None
        
    def initialize(self):
        """初始化串口连接"""
        try:
            self.serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=1
            )
            
            if self.serial.is_open:
                print(f"串口 {self.port} 已成功打开")
                # 不需要特殊的初始化命令
                return True
            else:
                print(f"无法打开串口 {self.port}")
                return False
        except Exception as e:
            print(f"初始化FPGA控制器时出错: {e}")
            return False
    
    def set_voltages(self, voltages):
        """
        设置多个通道的电压
        
        参数:
            voltages (list): 电压值列表
        
        返回:
            bool: 成功返回True
        """
        if len(voltages) != self.num_channels:
            print(f"错误: 电压值数量({len(voltages)})与通道数量({self.num_channels})不匹配")
            return False
        
        try:
            if not self.serial or not self.serial.is_open:
                if not self.initialize():
                    return False
            
            # 发送设置电压的命令，注意通道从1开始
            for i, voltage in enumerate(voltages):
                # 限制电压范围
                clipped_voltage = max(0.0, min(10.0, voltage))
                # 直接发送通道号(从1开始)和电压值
                channel_number = i + 1  # 通道编号从1开始
                self._send_command(channel_number, clipped_voltage)
                time.sleep(0.1)  # 小延迟确保命令被处理
            
            self.current_voltages = voltages
            return True
        except Exception as e:
            print(f"设置电压时出错: {e}")
            return False
    
    def _send_command(self, channel, voltage):
        """
        向FPGA发送电压设置命令（不等待回复）- 用于优化过程
        
        参数:
            channel (int): 通道序号(从1开始)
            voltage (float): 电压值
        """
        # 构建简单的命令字符串: "<通道序号> <电压值>"
        command = f"{channel} {voltage}\n"
        
        # 只发送数据，不等待回复
        self.serial.write(command.encode('utf-8'))
        
        # 清除接收缓冲区中累积的回复，避免下次读取时混淆
        time.sleep(0.1)  # 短暂等待回复到达
        if self.serial.in_waiting:
            self.serial.reset_input_buffer()
    
    def _send_command_with_response(self, channel, voltage):
        """
        向FPGA发送电压设置命令并读取完整回复
        
        参数:
            channel (int): 通道序号(从1开始)
            voltage (float): 电压值
        
        返回:
            str: FPGA的完整回复消息
        """
        # 构建简单的命令字符串: "<通道序号> <电压值>"
        command = f"{channel} {voltage}\n"
        
        # 清空接收缓冲区
        self.serial.reset_input_buffer()
        
        # 发送数据
        self.serial.write(command.encode('utf-8'))
        
        # 等待一段时间让FPGA处理并回复
        time.sleep(0.1)
        
        # 读取所有可用的回复行
        responses = []
        timeout_start = time.time()
        timeout_limit = 2.0  # 2秒超时时间
        
        while True:
            # 检查是否有数据可读
            if self.serial.in_waiting:
                line = self.serial.readline().decode('utf-8', errors='ignore').strip()
                if line:  # 忽略空行
                    responses.append(line)
                timeout_start = time.time()  # 收到数据后重置超时计时
            else:
                # 如果一段时间没有新数据，认为传输结束
                if time.time() - timeout_start > 0.5:  # 0.5秒无数据视为结束
                    break
                
            # 总体超时保护
            if time.time() - timeout_start > timeout_limit:
                responses.append("ERROR: 读取回复超时")
                break
        
        # 返回所有回复行，用换行符连接
        if responses:
            return "\n".join(responses)
        else:
            return "无回复"
    
    def get_current_voltages(self):
        """获取当前所有通道的电压值"""
        return self.current_voltages
    
    def close(self):
        """关闭串口连接"""
        if self.serial and self.serial.is_open:
            self.serial.close()
            print(f"串口 {self.port} 已关闭")
    
    def __del__(self):
        """析构函数确保关闭串口"""
        self.close()

def list_serial_ports():
    """列出所有可用的串口设备"""
    import serial.tools.list_ports
    ports = list(serial.tools.list_ports.comports())
    print("可用串口:")
    for i, port in enumerate(ports):
        print(f"{i+1}. {port.device} - {port.description}")
    return [port.device for port in ports]

# 检测电压是否正确输出的函数
def verify_voltage_output(controller, channel, expected_voltage):
    """
    验证指定通道的电压输出是否正确
    
    参数:
        controller: FPGA控制器实例
        channel: 要验证的通道(从1开始)
        expected_voltage: 期望的电压值
    
    返回:
        bool: 验证成功返回True
    """
    # 在实际应用中，这里应该有读取实际输出电压的代码
    # 例如，通过FPGA的ADC反馈或外部万用表读取
    
    # 这里仅模拟验证过程
    print(f"验证通道{channel}电压输出: 期望值为{expected_voltage}V")
    
    # 添加手动确认步骤
    confirm = input("电压输出是否符合预期? (y/n): ")
    return confirm.lower() == 'y'

if __name__ == "__main__":
    print("\n=== Xilinx Zynq 7020 FPGA 电压控制器测试程序 ===\n")
    
    # 列出可用串口设备
    available_ports = list_serial_ports()
    
    if not available_ports:
        print("未找到可用串口设备，请检查连接")
        exit()
    
    # 选择串口设备
    port_index = 0
    if len(available_ports) > 1:
        while True:
            try:
                port_index = int(input("\n请选择要使用的串口设备编号 (1-{}): ".format(len(available_ports)))) - 1
                if 0 <= port_index < len(available_ports):
                    break
                else:
                    print(f"请输入1到{len(available_ports)}之间的数字")
            except ValueError:
                print("请输入有效的数字")
    
    selected_port = available_ports[port_index]
    
    # 选择波特率
    baudrate_options = [9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600]
    print("\n可选波特率:")
    for i, rate in enumerate(baudrate_options):
        print(f"{i+1}. {rate}")
    
    baudrate_index = 4  # 默认选择115200
    try:
        baudrate_choice = input("\n请选择波特率编号 (默认5-115200): ")
        if baudrate_choice.strip():
            baudrate_index = int(baudrate_choice) - 1
            if not (0 <= baudrate_index < len(baudrate_options)):
                print(f"无效选择，使用默认波特率115200")
                baudrate_index = 4
    except ValueError:
        print("无效输入，使用默认波特率115200")
    
    selected_baudrate = baudrate_options[baudrate_index]
    
    # 配置通道参数
    try:
        num_channels = int(input("\n请输入要使用的DAC通道数量 (默认为4): ") or "4")
        
        # 创建并测试FPGA控制器
        print(f"\n使用串口 {selected_port} (波特率: {selected_baudrate}) 连接FPGA...")
        controller = ZynqVoltageController(
            port=selected_port,
            baudrate=selected_baudrate,
            num_channels=num_channels
        )
        
        if controller.initialize():
            print("成功初始化FPGA控制器")
            
            # 测试选项菜单
            while True:
                print("\n=== FPGA控制器测试菜单 ===")
                print("1. 设置单个通道电压")
                print("2. 设置所有通道电压")
                print("3. 设置所有通道为0V")
                print("4. 测试电压扫描")
                print("5. 增强版FPGA回复测试")
                print("6. 退出测试程序")
                
                choice = input("\n请选择操作: ")
                
                if choice == "1":
                    # 设置单个通道电压
                    try:
                        # 这里通道选择从1开始
                        channel = int(input(f"请选择通道 (1-{num_channels}): "))
                        if not (1 <= channel <= num_channels):
                            print(f"无效通道，请选择1到{num_channels}之间的值")
                            continue
                        
                        voltage = float(input("请输入电压值 (0V 到 10V): "))
                        if not (0 <= voltage <= 10):
                            print("电压值必须在 0V 到 10V 之间")
                            continue
                        
                        # 生成电压列表，只更新选定通道
                        voltages = controller.current_voltages.copy()
                        # 注意：内部通道索引从0开始，外部显示从1开始
                        voltages[channel-1] = voltage
                        
                        if controller.set_voltages(voltages):
                            print(f"已设置通道{channel}电压为{voltage}V")
                            time.sleep(0.1)
                            # 验证输出
                            verify_voltage_output(controller, channel, voltage)
                        else:
                            print("设置电压失败")
                    except ValueError:
                        print("请输入有效的数字")
                
                elif choice == "2":
                    # 设置所有通道电压
                    try:
                        voltages = []
                        print(f"\n请为每个通道输入电压值 (0V 到 10V):")
                        for i in range(num_channels):
                            while True:
                                try:
                                    # 显示从1开始的通道号
                                    voltage = float(input(f"通道 {i+1} 的电压值: "))
                                    if 0 <= voltage <= 10:
                                        voltages.append(voltage)
                                        break
                                    else:
                                        print("电压值必须在 0V 到 10V 之间")
                                except ValueError:
                                    print("请输入有效的数字")
                        
                        if controller.set_voltages(voltages):
                            print(f"\n成功设置所有通道电压: {controller.get_current_voltages()}")
                            
                            # 询问是否验证每个通道
                            verify_all = input("是否验证所有通道电压输出? (y/n): ")
                            if verify_all.lower() == 'y':
                                for i, voltage in enumerate(voltages):
                                    # 验证时显示从1开始的通道号
                                    verify_voltage_output(controller, i+1, voltage)
                        else:
                            print("设置电压失败")
                    except Exception as e:
                        print(f"设置电压时出错: {e}")
                
                elif choice == "3":
                    # 设置所有通道为0V
                    zero_voltages = [0.0] * num_channels
                    if controller.set_voltages(zero_voltages):
                        print("已将所有通道电压设置为0V")
                    else:
                        print("设置电压失败")
                
                elif choice == "4":
                    # 测试电压扫描
                    try:
                        # 通道选择从1开始
                        channel = int(input(f"请选择要扫描的通道 (1-{num_channels}): "))
                        if not (1 <= channel <= num_channels):
                            print(f"无效通道，请选择1到{num_channels}之间的值")
                            continue
                        
                        start_voltage = float(input("请输入起始电压 (0V 到 10V): "))
                        end_voltage = float(input("请输入结束电压 (0V 到 10V): "))
                        steps = int(input("请输入扫描步数: "))
                        delay = float(input("请输入每步延时(秒): "))
                        
                        if not (0 <= start_voltage <= 10 and 0 <= end_voltage <= 10):
                            print("电压值必须在 0V 到 10V 之间")
                            continue
                        
                        print(f"\n开始扫描通道{channel}电压从{start_voltage}V到{end_voltage}V，共{steps}步...")
                        
                        # 计算电压步长
                        voltage_step = (end_voltage - start_voltage) / (steps - 1) if steps > 1 else 0
                        
                        # 执行扫描
                        scan_voltages = controller.current_voltages.copy()
                        for i in range(steps):
                            current_voltage = start_voltage + i * voltage_step
                            # 内部通道索引从0开始
                            scan_voltages[channel-1] = current_voltage
                            
                            if controller.set_voltages(scan_voltages):
                                print(f"步骤 {i+1}/{steps}: 通道{channel}电压 = {current_voltage:.3f}V")
                                time.sleep(delay)
                            else:
                                print(f"步骤 {i+1}/{steps}: 设置电压失败")
                                break
                        
                        print("电压扫描完成")
                        
                        # 询问是否将电压恢复为0V
                        reset = input("是否将此通道电压恢复为0V? (y/n): ")
                        if reset.lower() == 'y':
                            scan_voltages[channel-1] = 0.0
                            controller.set_voltages(scan_voltages)
                            print(f"已将通道{channel}电压重置为0V")
                            
                    except ValueError:
                        print("请输入有效的数字")
                
                elif choice == "5":
                    # 增强版FPGA回复测试
                    try:
                        print("\n=== 增强版FPGA回复测试模式 ===")
                        print("在此模式下，您可以发送命令并查看FPGA的完整回复")
                        
                        while True:
                            print("\n选项:")
                            print("1. 发送标准电压命令")
                            print("2. 发送自定义命令")
                            print("3. 监听模式")
                            print("4. 返回主菜单")
                            
                            test_option = input("\n请选择测试方式: ")
                            
                            if test_option == "1":
                                # 标准电压命令
                                # 通道选择从1开始
                                channel = int(input(f"请选择通道 (1-{num_channels}): "))
                                if not (1 <= channel <= num_channels):
                                    print(f"无效通道，请选择1到{num_channels}之间的值")
                                    continue
                                
                                voltage = float(input("请输入电压值 (0V 到 10V): "))
                                if not (0 <= voltage <= 10):    
                                    print("电压值必须在 0V 到 10V 之间")
                                    continue
                                
                                print(f"\n发送命令: '{channel} {voltage}'")
                                
                                # 使用增强版的响应读取
                                response = controller._send_command_with_response(channel, voltage)
                                print(f"\nFPGA完整回复:\n{response}")
                                
                                # 更新当前电压记录
                                voltages = controller.current_voltages.copy()
                                voltages[channel-1] = voltage
                                controller.current_voltages = voltages
                                
                            elif test_option == "2":
                                # 自定义命令
                                custom_cmd = input("请输入自定义命令: ")
                                
                                # 清空接收缓冲区
                                controller.serial.reset_input_buffer()
                                
                                # 确保命令以换行符结束
                                if not custom_cmd.endswith('\n'):
                                    custom_cmd += '\n'
                                
                                print(f"发送命令: '{custom_cmd.strip()}'")
                                controller.serial.write(custom_cmd.encode('utf-8'))
                                
                                # 读取回复
                                time.sleep(0.1)
                                responses = []
                                timeout_start = time.time()
                                
                                while True:
                                    if controller.serial.in_waiting:
                                        line = controller.serial.readline().decode('utf-8', errors='ignore').strip()
                                        if line:
                                            responses.append(line)
                                        timeout_start = time.time()
                                    elif time.time() - timeout_start > 0.5:
                                        break
                                    if time.time() - timeout_start > 2.0:
                                        responses.append("ERROR: 读取回复超时")
                                        break
                                
                                print("\nFPGA完整回复:")
                                if responses:
                                    for i, resp in enumerate(responses):
                                        print(f"{i+1}. '{resp}'")
                                else:
                                    print("无回复")
                                    
                            elif test_option == "3":
                                # 监听模式
                                print("\n=== 监听模式 ===")
                                print("将持续监听并显示从FPGA收到的所有数据")
                                print("按Enter键停止监听")
                                
                                # 清空缓冲区
                                controller.serial.reset_input_buffer()
                                
                                # 设置非阻塞模式
                                import msvcrt
                                
                                print("开始监听...\n")
                                start_time = time.time()
                                while True:
                                    # 检查用户是否按下Enter键
                                    if msvcrt.kbhit() and msvcrt.getch() == b'\r':
                                        print("\n停止监听")
                                        break
                                    
                                    # 读取并显示数据
                                    if controller.serial.in_waiting:
                                        data = controller.serial.readline().decode('utf-8', errors='ignore').strip()
                                        if data:
                                            elapsed = time.time() - start_time
                                            print(f"[{elapsed:.2f}s] 收到: '{data}'")
                                    
                                    # 短暂休眠避免CPU占用过高
                                    time.sleep(0.01)
                                
                            elif test_option == "4":
                                # 返回主菜单
                                break
                                
                            else:
                                print("无效选项，请重试")
                                
                    except ValueError:
                        print("请输入有效的数字")
                    except Exception as e:
                        print(f"测试过程中出错: {e}")
                        import traceback
                        traceback.print_exc()
                
                elif choice == "6":
                    # 退出程序
                    break
                
                else:
                    print("无效选择，请重试")
            
            # 关闭控制器前询问是否将所有电压归零
            zero_before_exit = input("\n是否在退出前将所有通道电压设置为0V? (y/n): ")
            if zero_before_exit.lower() == 'y':
                zero_voltages = [0.0] * num_channels
                controller.set_voltages(zero_voltages)
                print("已将所有通道电压设置为0V")
            
            # 关闭控制器
            controller.close()
        else:
            print("初始化FPGA控制器失败")
            
    except ValueError as e:
        print(f"输入错误: {e}")
    except Exception as e:
        print(f"操作过程中发生错误: {e}")
    finally:
        print("\nFPGA电压控制测试程序已结束")
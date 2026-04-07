#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
单通道电压控制模块 - 实现单通道电压扫描和评价功能
"""

import time

class OneChannelVoltageController:
    """单通道电压控制器类"""
    
    def __init__(self, controller, channel=1):
        """初始化单通道电压控制器
        
        参数:
            controller: ZynqVoltageController实例
            channel: 要控制的通道号(从1开始)
        """
        self.controller = controller
        self.channel = channel
    
    def voltage_scan_with_evaluation(self, start_voltage=0.0, end_voltage=10.0, step_voltage=0.1):
        """
        对指定通道进行电压扫描，并在每个电压点收集用户的评价，返回评价值最高的电压值
        
        参数:
            start_voltage: 起始电压值
            end_voltage: 终止电压值
            step_voltage: 步进电压值
        
        返回:
            tuple: (最高评价值对应的电压, 最高评分值)
        """
        # 验证输入参数
        if not (0.0 <= start_voltage <= 10.0 and 0.0 <= end_voltage <= 10.0):
            raise ValueError("电压值必须在 0V 到 10V 之间")
        
        if step_voltage <= 0:
            raise ValueError("步进电压必须大于0")
        
        if self.channel < 1 or self.channel > self.controller.num_channels:
            raise ValueError(f"通道号必须在 1 到 {self.controller.num_channels} 之间")
        
        # 确定扫描方向
        if start_voltage <= end_voltage:
            voltage_range = lambda: range(int(start_voltage / step_voltage), int(end_voltage / step_voltage) + 1)
            voltages = [i * step_voltage for i in voltage_range()]
            # 确保包含终止电压
            if voltages[-1] < end_voltage:
                voltages.append(end_voltage)
        else:
            voltage_range = lambda: range(int(start_voltage / step_voltage), int(end_voltage / step_voltage) - 1, -1)
            voltages = [i * step_voltage for i in voltage_range()]
            # 确保包含终止电压
            if voltages[-1] > end_voltage:
                voltages.append(end_voltage)
        
        print(f"开始对通道 {self.channel} 进行电压扫描")
        print(f"电压范围: {start_voltage}V 到 {end_voltage}V, 步进: {step_voltage}V")
        print(f"总共需要测试 {len(voltages)} 个电压点\n")
        
        best_voltage = start_voltage
        best_score = float('-inf')
        score_history = []  # 存储所有电压点的评分历史
        
        # 获取当前的电压状态以便恢复
        original_voltages = self.controller.current_voltages.copy()
        
        try:
            for i, voltage in enumerate(voltages):
                print(f"[{i+1}/{len(voltages)}] 设置电压: {voltage:.3f}V")
                
                # 设置当前电压
                target_voltages = original_voltages.copy()
                target_voltages[self.channel-1] = voltage  # 通道索引从0开始
                
                if not self.controller.set_voltages(target_voltages):
                    print(f"  设置电压 {voltage}V 失败，跳过此点")
                    continue
                
                # 等待用户输入评价值
                while True:
                    try:
                        user_score = float(input(f"  请输入在 {voltage:.3f}V 时的评价值: "))
                        break
                    except ValueError:
                        print("  请输入有效的数值")
                
                score_history.append((voltage, user_score))
                
                # 更新最佳电压和评分
                if user_score > best_score:
                    best_score = user_score
                    best_voltage = voltage
                    print(f"  -> 新的最佳评分! 电压: {best_voltage:.3f}V, 评分: {best_score}")
                else:
                    print(f"  当前最佳: {best_voltage:.3f}V (评分: {best_score})")
                
                print()  # 空行分隔
            
            print("="*50)
            print(f"电压扫描完成!")
            print(f"最佳电压: {best_voltage:.3f}V")
            print(f"对应评分: {best_score}")
            print("="*50)
            
            # 可选：显示评分历史
            show_history = input("是否显示完整的评分历史? (y/n): ").lower() == 'y'
            if show_history:
                print("\n评分历史:")
                print("电压(V)\t\t评分")
                print("-"*20)
                for voltage, score in score_history:
                    marker = " <- 最佳" if voltage == best_voltage else ""
                    print(f"{voltage:.3f}\t\t{score}{marker}")
            
            return best_voltage, best_score
            
        except KeyboardInterrupt:
            print("\n\n扫描被用户中断")
            # 在中断时返回当前最佳结果
            print(f"当前最佳电压: {best_voltage:.3f}V (评分: {best_score})")
            return best_voltage, best_score
        finally:
            # 扫描结束后将电压恢复到原始状态
            print(f"\n正在将通道 {self.channel} 电压恢复到原始状态...")
            self.controller.set_voltages(original_voltages)
            print("电压已恢复")

# 示例使用方法
def example_usage():
    """
    使用示例
    """
    from zynq_voltage_controller import ZynqVoltageController
    
    # 创建控制器实例
    controller = ZynqVoltageController(port='COM3', num_channels=4)  # Windows系统通常使用COM端口
    
    # 初始化连接
    if controller.initialize():
        print("控制器初始化成功")
        
        # 创建单通道控制器实例
        one_channel_controller = OneChannelVoltageController(controller, channel=1)
        
        # 获取用户输入的扫描参数
        while True:
            try:
                start_voltage = float(input("请输入起始电压 (0-10V): "))
                if not (0.0 <= start_voltage <= 10.0):
                    print("电压值必须在 0V 到 10V 之间")
                    continue
                
                end_voltage = float(input("请输入终止电压 (0-10V): "))
                if not (0.0 <= end_voltage <= 10.0):
                    print("电压值必须在 0V 到 10V 之间")
                    continue
                
                step_voltage = float(input("请输入步进电压: "))
                if step_voltage <= 0:
                    print("步进电压必须大于0")
                    continue
                break
            except ValueError:
                print("请输入有效的数值")
        
        # 执行电压扫描
        best_voltage, best_score = one_channel_controller.voltage_scan_with_evaluation(
            start_voltage=start_voltage,   # 起始电压
            end_voltage=end_voltage,     # 终止电压
            step_voltage=step_voltage     # 步进电压
        )
        
        print(f"最终结果 - 最佳电压: {best_voltage}V, 评分: {best_score}")
        
        # 关闭连接
        controller.close()
    else:
        print("控制器初始化失败")

if __name__ == "__main__":
    example_usage()
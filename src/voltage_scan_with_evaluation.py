#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
电压扫描与评价模块 - 实现电压扫描、插损测量和用户评价功能
"""

import time
import matplotlib.pyplot as plt
from zynq_voltage_controller import ZynqVoltageController
from reference_measurement import ReferenceMeasurement

import plot_style  # 学术论文绘图风格

class VoltageScanEvaluator:
    """电压扫描与评价类"""
    
    def __init__(self):
        """初始化电压扫描与评价器"""
        self.controller = None
        self.reference_measurement = None
        self.channel = 1  # 默认控制通道1
        self.start_voltage = 0.0
        self.end_voltage = 10.0
        self.step_voltage = 0.1
        self.best_voltage = None
        self.best_score = float('-inf')
        self.score_history = []
        self.original_voltages = None
        self.plot_figures = []  # 存储所有绘制的图像
        self.plot_counter = 0  # 绘制次数计数器
        self.reference_data = None  # 存储参考测量数据
        self.all_measurement_data = []  # 存储所有测量数据，用于最后汇总
        self.save_to_csv = False  # 是否保存数据到csv文件
        self.csv_file_path = None  # csv文件路径
    
    def initialize_voltage_controller(self):
        """初始化电压控制器"""
        print("初始化电压控制器...")
        # 创建控制器实例
        self.controller = ZynqVoltageController(port='COM3', num_channels=4)  # Windows系统通常使用COM端口
        
        # 初始化连接
        if not self.controller.initialize():
            print("控制器初始化失败")
            return False
        
        print("控制器初始化成功")
        return True
    
    def initialize_reference_measurement(self):
        """初始化参考测量"""
        print("初始化参考测量设备...")
        self.reference_measurement = ReferenceMeasurement()
        if not self.reference_measurement.initialize_optical_devices():
            print("参考测量设备初始化失败")
            return False
        
        # 配置参考测量参数
        self.reference_measurement.configure_reference_parameters()
        
        # 询问是否使用之前的参考数据
        import os
        from santec import file_saving
        
        reference_file = file_saving.FILE_LAST_SCAN_REFERENCE_DATA
        if os.path.exists(reference_file):
            use_previous = input("\n是否使用之前的参考损耗数据? [y|n] (默认y): ") in "Yy"
            if use_previous:
                # 直接加载之前的参考数据
                import json
                with open(reference_file, 'r', encoding='utf-8') as f:
                    self.reference_data = json.load(f)
                print(f"参考测量数据已从文件 {reference_file} 加载")
                print(f"参考数据长度: {len(self.reference_data)}")
                if self.reference_data:
                    print(f"第一个参考数据项包含的字段: {list(self.reference_data[0].keys())}")
                    # 同时设置reference_data_array，确保后续测量能够使用
                    if not hasattr(self.reference_measurement.ilsts, 'reference_data_array'):
                        self.reference_measurement.ilsts.reference_data_array = []
                    self.reference_measurement.ilsts.reference_data_array = self.reference_data
                    print("参考数据已设置到reference_data_array")
                print("参考测量设备初始化成功")
                return True
        
        # 执行初始参考测量
        print("执行初始参考测量...")
        # 这里我们执行参考测量，让用户连接激光器和光功率计
        
        # 先执行扫描获取数据
        input("\nConnect Slot0 Ch1, then press ENTER")
        
        print("\nScanning...")
        self.reference_measurement.ilsts.sts_reference()
        
        # 然后询问用户是否显示图像和保存数据到文件
        show_ref_plot = input("\n是否显示参考插损图像? [y|n] (默认y): ") in "Yy"
        if show_ref_plot:
            print("正在绘制参考插损图像...")
            self.reference_measurement.visualizer.plot_reference_data(self.reference_measurement.ilsts)
        
        # 询问是否保存参考数据到文件
        save_ref = input("\n是否保存参考数据? [y|n] (默认y): ") in "Yy"
        if save_ref:
            self.reference_measurement.file_manager.save_ref_data(self.reference_measurement.ilsts)
        
        # 从文件中读取参考数据
        import json
        
        if os.path.exists(reference_file):
            with open(reference_file, 'r', encoding='utf-8') as f:
                self.reference_data = json.load(f)
            print(f"参考测量数据已从文件 {reference_file} 加载")
            print(f"参考数据长度: {len(self.reference_data)}")
            if self.reference_data:
                print(f"第一个参考数据项包含的字段: {list(self.reference_data[0].keys())}")
        else:
            # 如果文件不存在，使用内存中的数据
            import copy
            self.reference_data = copy.deepcopy(self.reference_measurement.ilsts.reference_data_array)
            print("参考测量数据已保存到内存")
            print(f"内存中参考数据长度: {len(self.reference_data)}")
        
        print("参考测量设备初始化成功")
        return True
    
    def get_scan_parameters(self):
        """获取扫描参数"""
        print("\n请输入扫描参数:")
        
        # 再次配置参考测量参数
        # self.reference_measurement.configure_reference_parameters()

        # 询问是否保存数据到csv文件
        try:
            save_csv = input("是否保存每次测量数据到CSV文件? (y/n): ").lower() == 'y'
            self.save_to_csv = save_csv
            if save_csv:
                import os
                import datetime
                # 创建保存目录
                save_dir = f"./measurement_data/{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
                os.makedirs(save_dir, exist_ok=True)
                self.csv_file_path = os.path.join(save_dir, "insertion_loss_data.csv")
                print(f"数据将保存到: {self.csv_file_path}")
                # 写入CSV文件头
                with open(self.csv_file_path, 'w', newline='', encoding='utf-8') as f:
                    f.write("Voltage (V),Wavelength (nm),Insertion Loss (dB)\n")
        except (EOFError, KeyboardInterrupt):
            print("\n用户中断输入")
            return False
        
        while True:
            try:
                self.start_voltage = float(input("请输入起始电压 (0-10V): "))
                if not (0.0 <= self.start_voltage <= 10.0):
                    print("电压值必须在 0V 到 10V 之间")
                    continue
                
                self.end_voltage = float(input("请输入终止电压 (0-10V): "))
                if not (0.0 <= self.end_voltage <= 10.0):
                    print("电压值必须在 0V 到 10V 之间")
                    continue
                
                self.step_voltage = float(input("请输入步进电压: "))
                if self.step_voltage <= 0:
                    print("步进电压必须大于0")
                    continue
                break
            except ValueError:
                print("请输入有效的数值")
            except (EOFError, KeyboardInterrupt):
                print("\n用户中断输入")
                return False
        return True

    def plot_insertion_loss(self, voltage):
        """绘制插损图"""
        print(f"\n正在测量 {voltage:.3f}V 下的插损...")
        
        # 执行参考测量
        self.reference_measurement.measure_insertion_loss()
        
        # 增加绘制计数器
        self.plot_counter += 1
        
        # 绘制插损图
        try:
            if not hasattr(self.reference_measurement.ilsts, 'reference_data_array') or not self.reference_measurement.ilsts.reference_data_array:
                print("没有可用的参考插损数据")
                return
            
            # 确保使用last_scan_reference_data.dat中的数据
            import json
            import os
            from santec import file_saving
            
            reference_file = file_saving.FILE_LAST_SCAN_REFERENCE_DATA
            if os.path.exists(reference_file):
                with open(reference_file, 'r', encoding='utf-8') as f:
                    self.reference_data = json.load(f)
                print(f"参考测量数据已从文件 {reference_file} 加载")
                print(f"参考数据长度: {len(self.reference_data)}")
                if self.reference_data:
                    print(f"第一个参考数据项包含的字段: {list(self.reference_data[0].keys())}")
            
            # 减去参考值
            measurement_data = []
            if self.reference_data:
                print(f"使用参考数据减去损耗，参考数据长度: {len(self.reference_data)}")
                print(f"当前测量数据长度: {len(self.reference_measurement.ilsts.reference_data_array)}")
                
                # 遍历每个测量通道
                for i, ref_item in enumerate(self.reference_measurement.ilsts.reference_data_array):
                    # 创建一个新的字典，复制原始数据
                    new_item = ref_item.copy()
                    
                    # 检查参考数据是否足够
                    if i < len(self.reference_data) and "log_data" in self.reference_data[i]:
                        ref_values = self.reference_data[i]["log_data"]
                        print(f"使用log_data字段减去参考损耗，通道 {ref_item['SlotNumber']}-{ref_item['ChannelNumber']}，长度: {len(ref_values)}")
                    elif self.reference_data and "log_data" in self.reference_data[0]:
                        # 参考数据通道不足，使用第一个参考数据
                        ref_values = self.reference_data[0]["log_data"]
                        print(f"参考数据通道不足，使用第一个参考数据减去损耗，通道 {ref_item['SlotNumber']}-{ref_item['ChannelNumber']}，长度: {len(ref_values)}")
                    else:
                        print(f"警告: 参考数据不足，无法减去参考损耗，通道 {ref_item['SlotNumber']}-{ref_item['ChannelNumber']}")
                        measurement_data.append(new_item)
                        continue
                    
                    # 确保数据长度匹配
                    if len(ref_item["rescaled_reference_power"]) != len(ref_values):
                        print(f"警告: 数据长度不匹配，测量数据: {len(ref_item['rescaled_reference_power'])}, 参考数据: {len(ref_values)}")
                        # 取较短的长度
                        min_len = min(len(ref_item["rescaled_reference_power"]), len(ref_values))
                        new_item["rescaled_reference_power"] = [
                            p - ref_p for p, ref_p in zip(
                                ref_item["rescaled_reference_power"][:min_len],
                                ref_values[:min_len]
                            )
                        ]
                    else:
                        new_item["rescaled_reference_power"] = [
                            p - ref_p for p, ref_p in zip(
                                ref_item["rescaled_reference_power"],
                                ref_values
                            )
                        ]
                    measurement_data.append(new_item)
                    print(f"已减去参考损耗，通道 {ref_item['SlotNumber']}-{ref_item['ChannelNumber']}")
            else:
                print("警告: 没有参考数据，无法减去参考损耗")
                measurement_data = self.reference_measurement.ilsts.reference_data_array
            
            # 保存测量数据，用于最后汇总
            self.all_measurement_data.append((voltage, measurement_data))
            
            # 如果用户选择保存数据到csv文件
            if self.save_to_csv and self.csv_file_path and measurement_data:
                ref_item = measurement_data[-1]  # 只取一个曲线
                wavelengths = ref_item["rescaled_wavelength"]
                reference_power = ref_item["rescaled_reference_power"]
                
                # 写入CSV文件
                with open(self.csv_file_path, 'a', newline='', encoding='utf-8') as f:
                    for wl, il in zip(wavelengths, reference_power):
                        f.write(f"{voltage:.3f},{wl:.2f},{il:.4f}\n")
                print(f"数据已保存到: {self.csv_file_path}")
            
            # 只显示一个曲线
            if measurement_data:
                ref_item = measurement_data[-1]  # 只取一个曲线
                slot_num = ref_item["SlotNumber"]
                channel_num = ref_item["ChannelNumber"]
                wavelengths = ref_item["rescaled_wavelength"]
                reference_power = ref_item["rescaled_reference_power"]
                
                fig = plt.figure(figsize=(10, 6))
                self.plot_figures.append(fig)  # 存储图像
                
                plt.plot(wavelengths, reference_power, 
                        label=f'Slot{slot_num} Ch{channel_num}')
                
                plt.xlabel('Wavelength (nm)')
                plt.ylabel('Insertion Loss (dB)')
                plt.title(f'Insertion Loss at {voltage:.3f}V')
                plt.legend()
                plt.tight_layout()
                plt.show(block=False)
        except Exception as e:
            print(f"绘制参考插损图像时出错: {e}")
        
        # 询问是否放大查看某个波长范围
        try:
            zoom = input("是否需要放大查看某个波长范围? [y|n]: ").lower() == 'y'
            if zoom:
                try:
                    start_wl = float(input("请输入起始波长 (nm): "))
                    end_wl = float(input("请输入结束波长 (nm): "))
                    
                    # 减去参考值
                    measurement_data = []
                    if self.reference_data:
                        for i, ref_item in enumerate(self.reference_measurement.ilsts.reference_data_array):
                            # 创建一个新的字典，复制原始数据
                            new_item = ref_item.copy()
                            
                            # 检查参考数据是否足够
                            if i < len(self.reference_data) and "log_data" in self.reference_data[i]:
                                ref_values = self.reference_data[i]["log_data"]
                            elif self.reference_data and "log_data" in self.reference_data[0]:
                                # 参考数据通道不足，使用第一个参考数据
                                ref_values = self.reference_data[0]["log_data"]
                            else:
                                measurement_data.append(new_item)
                                continue
                            
                            # 确保数据长度匹配
                            if len(ref_item["rescaled_reference_power"]) != len(ref_values):
                                # 取较短的长度
                                min_len = min(len(ref_item["rescaled_reference_power"]), len(ref_values))
                                new_item["rescaled_reference_power"] = [
                                    p - ref_p for p, ref_p in zip(
                                        ref_item["rescaled_reference_power"][:min_len],
                                        ref_values[:min_len]
                                    )
                                ]
                            else:
                                new_item["rescaled_reference_power"] = [
                                    p - ref_p for p, ref_p in zip(
                                        ref_item["rescaled_reference_power"],
                                        ref_values
                                    )
                                ]
                            measurement_data.append(new_item)
                    else:
                        measurement_data = self.reference_measurement.ilsts.reference_data_array
                    
                    # 绘制放大后的插损图
                    if measurement_data:
                        ref_item = measurement_data[-1]  # 只取一个曲线
                        slot_num = ref_item["SlotNumber"]
                        channel_num = ref_item["ChannelNumber"]
                        wavelengths = ref_item["rescaled_wavelength"]
                        reference_power = ref_item["rescaled_reference_power"]
                        
                        # 筛选波长范围内的数据
                        filtered_wavelengths = []
                        filtered_power = []
                        for wl, p in zip(wavelengths, reference_power):
                            if start_wl <= wl <= end_wl:
                                filtered_wavelengths.append(wl)
                                filtered_power.append(p)
                        
                        fig = plt.figure(figsize=(10, 6))
                        self.plot_figures.append(fig)  # 存储图像
                        
                        plt.plot(filtered_wavelengths, filtered_power, 
                                label=f'Slot{slot_num} Ch{channel_num}')
                        
                        plt.xlabel('Wavelength (nm)')
                        plt.ylabel('Insertion Loss (dB)')
                        plt.title(f'Insertion Loss at {voltage:.3f}V (Zoomed)')
                        plt.legend()
                        plt.tight_layout()
                        plt.show(block=False)
                except ValueError:
                    print("输入的波长值无效")
                except (EOFError, KeyboardInterrupt):
                    print("\n用户中断输入")
        except (EOFError, KeyboardInterrupt):
            print("\n用户中断输入")
    
    def get_user_evaluation(self, voltage):
        """获取用户评价"""
        while True:
            try:
                user_score = float(input(f"  请输入在 {voltage:.3f}V 时的评价值: "))
                return user_score
            except ValueError:
                print("  请输入有效的数值")
            except (EOFError, KeyboardInterrupt):
                print("\n用户中断输入，安全退出")
                raise
    
    def save_all_figures(self):
        """保存所有绘制的图像"""
        if not self.plot_figures:
            print("没有可保存的图像")
            return
        
        import os
        import datetime
        
        # 创建保存目录
        save_dir = f"./insertion_loss_plots/{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
        os.makedirs(save_dir, exist_ok=True)
        
        # 保存所有图像
        for i, fig in enumerate(self.plot_figures):
            file_path = os.path.join(save_dir, f"insertion_loss_{i+1}.png")
            fig.savefig(file_path)
            print(f"图像已保存到: {file_path}")
        
        print(f"所有图像已保存到目录: {save_dir}")
    
    def plot_summary(self):
        """绘制所有曲线的汇总图"""
        if not self.all_measurement_data:
            print("没有可汇总的测量数据")
            return
        
        try:
            fig = plt.figure(figsize=(12, 8))
            self.plot_figures.append(fig)  # 存储图像
            
            # 使用更明显的颜色区分不同电压
            colors = ['blue', 'green', 'red', 'orange', 'purple', 'brown', 'pink', 'gray', 'olive', 'cyan']
            
            print(f"汇总图将显示 {len(self.all_measurement_data)} 条曲线")
            
            for i, (voltage, measurement_data) in enumerate(self.all_measurement_data):
                if measurement_data:
                    # 确保使用不同的颜色，即使电压数量超过颜色列表长度
                    color_index = i % len(colors)
                    
                    # 只取最后一个曲线
                    if len(measurement_data) > 0:
                        ref_item = measurement_data[-1]
                        wavelengths = ref_item["rescaled_wavelength"]
                        reference_power = ref_item["rescaled_reference_power"]
                        
                        plt.plot(wavelengths, reference_power, 
                                color=colors[color_index],
                                linewidth=1.5,
                                label=f'{voltage:.3f}V')
                        print(f"已添加电压 {voltage:.3f}V 的曲线")
            
            plt.xlabel('Wavelength (nm)')
            plt.ylabel('Insertion Loss (dB)')
            plt.title('Insertion Loss Summary')
            plt.legend()
            plt.tight_layout()
            plt.show(block=False)
            
            print("汇总图已绘制完成")
        except Exception as e:
            print(f"绘制汇总图时出错: {e}")
            import traceback
            traceback.print_exc()
    
    def run_scan(self):
        """运行电压扫描与评价"""
        try:
            # 初始化设备
            if not self.initialize_voltage_controller():
                return False
            
            if not self.initialize_reference_measurement():
                return False
            
            # 获取扫描参数
            if not self.get_scan_parameters():
                return False
            
            # 计算电压步进点
            if self.start_voltage <= self.end_voltage:
                voltage_range = lambda: range(int(self.start_voltage / self.step_voltage), int(self.end_voltage / self.step_voltage) + 1)
                voltages = [i * self.step_voltage for i in voltage_range()]
                # 确保包含终止电压
                if voltages[-1] < self.end_voltage:
                    voltages.append(self.end_voltage)
            else:
                voltage_range = lambda: range(int(self.start_voltage / self.step_voltage), int(self.end_voltage / self.step_voltage) - 1, -1)
                voltages = [i * self.step_voltage for i in voltage_range()]
                # 确保包含终止电压
                if voltages[-1] > self.end_voltage:
                    voltages.append(self.end_voltage)
            
            print(f"\n开始对通道 {self.channel} 进行电压扫描")
            print(f"电压范围: {self.start_voltage}V 到 {self.end_voltage}V, 步进: {self.step_voltage}V")
            print(f"总共需要测试 {len(voltages)} 个电压点\n")
            
            # 初始化最佳电压和评分
            self.best_voltage = self.start_voltage
            self.best_score = float('-inf')
            self.score_history = []
            
            # 获取当前的电压状态以便恢复
            self.original_voltages = self.controller.current_voltages.copy()
            
            # 执行扫描
            for i, voltage in enumerate(voltages):
                print(f"[{i+1}/{len(voltages)}] 设置电压: {voltage:.3f}V")
                
                # 设置当前电压
                target_voltages = self.original_voltages.copy()
                target_voltages[self.channel-1] = voltage  # 通道索引从0开始
                
                if not self.controller.set_voltages(target_voltages):
                    print(f"  设置电压 {voltage}V 失败，跳过此点")
                    continue
                
                # 等待电压稳定
                time.sleep(0.5)
                
                # 询问用户选择
                while True:
                    try:
                        choice = input("  请选择操作: [1]查看插损图 [2]给出评价值: ").strip()
                        if choice == '1':
                            # 查看插损图
                            # 直接调用plot_insertion_loss，内部会增加plot_counter
                            self.plot_insertion_loss(voltage)
                            # 等待用户关闭图像
                            input("  按Enter键继续...")
                        elif choice == '2':
                            # 给出评价值
                            user_score = self.get_user_evaluation(voltage)
                            break
                        else:
                            print("  请输入有效的选项")
                    except (EOFError, KeyboardInterrupt):
                        print("\n用户中断输入，安全退出")
                        raise
                
                # 记录评分
                self.score_history.append((voltage, user_score))
                
                # 更新最佳电压和评分
                if user_score > self.best_score:
                    self.best_score = user_score
                    self.best_voltage = voltage
                    print(f"  -> 新的最佳评分! 电压: {self.best_voltage:.3f}V, 评分: {self.best_score}")
                else:
                    print(f"  当前最佳: {self.best_voltage:.3f}V (评分: {self.best_score})")
                
                print()  # 空行分隔
            
            # 扫描完成
            print("="*50)
            print(f"电压扫描完成!")
            print(f"最佳电压: {self.best_voltage:.3f}V")
            print(f"对应评分: {self.best_score}")
            print("="*50)
            
            # 可选：显示评分历史
            try:
                show_history = input("是否显示完整的评分历史? (y/n): ").lower() == 'y'
                if show_history:
                    print("\n评分历史:")
                    print("电压(V)\t\t评分")
                    print("-"*20)
                    for voltage, score in self.score_history:
                        marker = " <- 最佳" if voltage == self.best_voltage else ""
                        print(f"{voltage:.3f}\t\t{score}{marker}")
            except (EOFError, KeyboardInterrupt):
                print("\n用户中断输入")
            
            # 绘制汇总图
            self.plot_summary()
            
            
            # 询问是否保存图像
            try:
                if self.plot_figures:
                    save_figures = input("是否保存所有插损图像? (y/n): ").lower() == 'y'
                    if save_figures:
                        self.save_all_figures()
            except (EOFError, KeyboardInterrupt):
                print("\n用户中断输入")
            
            return True
            
        except KeyboardInterrupt:
            print("\n\n扫描被用户中断")
            # 在中断时返回当前最佳结果
            print(f"当前最佳电压: {self.best_voltage:.3f}V (评分: {self.best_score})")
            # 询问是否保存图像
            try:
                if self.plot_figures:
                    save_figures = input("是否保存所有插损图像? (y/n): ").lower() == 'y'
                    if save_figures:
                        self.save_all_figures()
            except (EOFError, KeyboardInterrupt):
                print("\n用户中断输入")
            return False
        except EOFError:
            print("\n用户中断输入，安全退出")
            # 询问是否保存图像
            try:
                if self.plot_figures:
                    save_figures = input("是否保存所有插损图像? (y/n): ").lower() == 'y'
                    if save_figures:
                        self.save_all_figures()
            except (EOFError, KeyboardInterrupt):
                print("\n用户中断输入")
            return False
        except Exception as e:
            print(f"扫描过程中出错: {e}")
            return False
        finally:
            # 扫描结束后将电压恢复到原始状态
            if self.controller and self.original_voltages:
                print(f"\n正在将通道 {self.channel} 电压恢复到原始状态...")
                self.controller.set_voltages(self.original_voltages)
                print("电压已恢复")
            
            # 关闭设备
            if self.controller:
                self.controller.close()
            
            if self.reference_measurement:
                if self.reference_measurement.tsl:
                    self.reference_measurement.tsl.query("*RST")
                if self.reference_measurement.mpm:
                    self.reference_measurement.mpm.cls_status
            
            # 关闭所有图像
            for fig in self.plot_figures:
                plt.close(fig)

def main():
    """主函数"""
    print("=== 电压扫描与评价系统 ===")
    evaluator = VoltageScanEvaluator()
    evaluator.run_scan()

if __name__ == "__main__":
    main()
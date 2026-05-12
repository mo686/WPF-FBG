#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
插损测量脚本 - 简单测量和绘制插损图
"""

import os
import json
import time
import matplotlib.pyplot as plt
from reference_measurement import ReferenceMeasurement

import plot_style  # 学术论文绘图风格

class InsertionLossMeasurer:
    """插损测量类"""
    
    def __init__(self):
        """初始化插损测量器"""
        self.reference_measurement = None
        self.reference_data = None  # 存储参考测量数据
        self.plot_figures = []  # 存储绘制的图像
    
    def initialize(self):
        """初始化设备和参考测量"""
        print("初始化插损测量系统...")
        
        # 初始化参考测量
        self.reference_measurement = ReferenceMeasurement()
        if not self.reference_measurement.initialize_optical_devices():
            print("参考测量设备初始化失败")
            return False
        
        # 配置参考测量参数
        self.reference_measurement.configure_reference_parameters()
        
        # 检查是否有上次的参考数据
        from santec import file_saving
        reference_file = file_saving.FILE_LAST_SCAN_REFERENCE_DATA
        use_last_reference = False
        
        if os.path.exists(reference_file):
            # 询问用户是否使用上次的参考数据
            choice = input("是否使用上次的参考数据? [y/n]: ").lower()
            use_last_reference = choice == 'y'
        
        if use_last_reference:
            # 使用上次的参考数据
            with open(reference_file, 'r', encoding='utf-8') as f:
                self.reference_data = json.load(f)
            print(f"已使用上次的参考数据: {reference_file}")
            # 将参考数据加载到 C++ 中
            self.reference_measurement.ilsts.reference_data_array = self.reference_data
            self.reference_measurement.ilsts.sts_reference_from_saved_file()
        else:
            # 执行新的参考测量
            print("执行参考测量...")
            input("\nConnect Slot0 Ch1, then press ENTER")
            print("\nScanning...")
            self.reference_measurement.ilsts.sts_reference()
            
            # 绘制参考插损图像
            print("绘制参考插损图像...")
            self.reference_measurement.visualizer.plot_reference_data(self.reference_measurement.ilsts)
            
            # 保存参考数据到文件
            print("保存参考数据...")
            self.reference_measurement.file_manager.save_ref_data(self.reference_measurement.ilsts)
            
            # 从文件中读取参考数据
            if os.path.exists(reference_file):
                with open(reference_file, 'r', encoding='utf-8') as f:
                    self.reference_data = json.load(f)
                print(f"参考测量数据已保存并加载: {reference_file}")
            else:
                print("参考数据文件不存在")
                return False
        
        print("初始化完成")
        return True
    
    def measure_insertion_loss(self):
        """测量插损"""
        print("\n测量插损...")
        
        # 执行插损测量
        success = self.reference_measurement.measure_insertion_loss()
        
        # 构建测量数据
        measurement_data = []
        
        if success:
            # 从 StsProcess 获取插损数据
            ilsts = self.reference_measurement.ilsts
            
            # 检查是否有插损数据
            if hasattr(ilsts, 'il_data_array') and ilsts.il_data_array:
                # 检查是否有波长数据
                if hasattr(ilsts, 'wavelength_table') and ilsts.wavelength_table:
                    # 为每个通道创建测量数据
                    for i, il_data in enumerate(ilsts.il_data_array):
                        # 创建一个新的字典来存储测量数据
                        measurement_item = {
                            "MPMNumber": 0,
                            "SlotNumber": 0,  # 假设使用 Slot 0
                            "ChannelNumber": i + 1,  # 通道号从 1 开始
                            "rescaled_wavelength": ilsts.wavelength_table,
                            "rescaled_reference_power": list(il_data)  # 插损数据
                        }
                        measurement_data.append(measurement_item)
                else:
                    print("警告: 没有波长数据")
            else:
                print("警告: 没有插损数据")
        else:
            print("警告: 插损测量失败")
        
        return measurement_data
    
    def plot_insertion_loss(self, measurement_data):
        """绘制插损图"""
        try:
            if not measurement_data:
                print("没有可用的插损数据")
                return
            
            fig = plt.figure(figsize=(10, 6))
            self.plot_figures.append(fig)  # 存储图像
            
            # 只显示第一个曲线
            ref_item = measurement_data[-1]  # 只取最后一个曲线
            slot_num = ref_item["SlotNumber"]
            channel_num = ref_item["ChannelNumber"]
            wavelengths = ref_item["rescaled_wavelength"]
            reference_power = ref_item["rescaled_reference_power"]
            
            plt.plot(wavelengths, reference_power, 
                    label=f'Slot{slot_num} Ch{channel_num}')
            
            plt.xlabel('Wavelength (nm)')
            plt.ylabel('Insertion Loss (dB)')
            plt.title('Insertion Loss Measurement')
            plt.legend()
            plt.tight_layout()
            plt.show(block=False)
        except Exception as e:
            print(f"绘制插损图像时出错: {e}")
    
    def plot_zoomed_insertion_loss(self, measurement_data):
        """绘制放大的插损图"""
        try:
            if not measurement_data:
                print("没有可用的插损数据")
                return
            
            # 获取波长范围
            ref_item = measurement_data[-1]
            wavelengths = ref_item["rescaled_wavelength"]
            min_wl = min(wavelengths)
            max_wl = max(wavelengths)
            
            print(f"\n当前波长范围: {min_wl:.2f} - {max_wl:.2f} nm")
            start_wl = float(input("输入起始波长 (nm): "))
            end_wl = float(input("输入结束波长 (nm): "))
            
            if start_wl >= end_wl:
                print("起始波长必须小于结束波长")
                return
            
            fig = plt.figure(figsize=(10, 6))
            self.plot_figures.append(fig)  # 存储图像
            
            # 只显示第一个曲线
            ref_item = measurement_data[-1]  # 只取最后一个曲线
            slot_num = ref_item["SlotNumber"]
            channel_num = ref_item["ChannelNumber"]
            wavelengths = ref_item["rescaled_wavelength"]
            reference_power = ref_item["rescaled_reference_power"]
            
            filtered_wavelengths = []
            filtered_power = []
            for wl, p in zip(wavelengths, reference_power):
                if start_wl <= wl <= end_wl:
                    filtered_wavelengths.append(wl)
                    filtered_power.append(p)
            
            plt.plot(filtered_wavelengths, filtered_power, 
                    label=f'Slot{slot_num} Ch{channel_num}')
            
            plt.xlabel('Wavelength (nm)')
            plt.ylabel('Insertion Loss (dB)')
            plt.title(f'Insertion Loss ({start_wl}-{end_wl} nm)')
            plt.legend()
            plt.tight_layout()
            plt.show(block=False)
        except ValueError:
            print("输入的波长值无效")
        except Exception as e:
            print(f"绘制放大插损图像时出错: {e}")
    
    def save_loss_data(self, measurement_data, filename):
        """保存损耗数据到文件"""
        try:
            import json
            import os
            
            # 处理文件名，确保目录存在
            dir_path = os.path.dirname(filename)
            if dir_path:
                os.makedirs(dir_path, exist_ok=True)
            
            # 保存数据
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(measurement_data, f, ensure_ascii=False, indent=2)
            
            print(f"✅ 损耗数据已保存到: {os.path.abspath(filename)}")
            return True
        except Exception as e:
            print(f"❌ 保存损耗数据失败: {e}")
            return False
    
    def save_loss_plot(self, filename):
        """保存损耗图到文件"""
        try:
            import os
            
            # 处理文件名，确保目录存在
            dir_path = os.path.dirname(filename)
            if dir_path:
                os.makedirs(dir_path, exist_ok=True)
            
            # 保存最后绘制的图像
            if self.plot_figures:
                fig = self.plot_figures[-1]
                fig.savefig(filename, dpi=300, bbox_inches='tight')
                print(f"✅ 损耗图已保存到: {os.path.abspath(filename)}")
                return True
            else:
                print("❌ 没有可保存的图像")
                return False
        except Exception as e:
            print(f"❌ 保存损耗图失败: {e}")
            return False
    
    def run(self):
        """运行插损测量流程"""
        try:
            # 初始化
            if not self.initialize():
                return False
            
            # 测量插损
            measurement_data = self.measure_insertion_loss()
            
            # 绘制插损图
            self.plot_insertion_loss(measurement_data)
            
            # 询问是否放大查看
            zoom = input("\n是否需要放大查看某个波长范围? [y|n]: ").lower() == 'y'
            if zoom:
                self.plot_zoomed_insertion_loss(measurement_data)
            
            # 询问是否保存损耗数据
            save_data = input("\n是否保存损耗数据? [y|n]: ").lower() == 'y'
            if save_data:
                default_filename = f"./measure/loss_data/{time.strftime('%Y%m%d_%H%M%S')}.json"
                filename = input(f"请输入保存文件名 (默认: {default_filename}): ") or default_filename
                if not filename.endswith('.json'):
                    filename += '.json'
                self.save_loss_data(measurement_data, filename)
            
            # 询问是否保存损耗图
            save_plot = input("\n是否保存损耗图? [y|n]: ").lower() == 'y'
            if save_plot:
                default_filename = f"./measure/loss_plot/{time.strftime('%Y%m%d_%H%M%S')}.png"
                filename = input(f"请输入保存文件名 (默认: {default_filename}): ") or default_filename
                if not (filename.endswith('.png') or filename.endswith('.jpg') or filename.endswith('.jpeg')):
                    filename += '.png'
                self.save_loss_plot(filename)
            
            # 等待用户关闭图像
            input("\n按Enter键退出...")
            
            return True
        except KeyboardInterrupt:
            print("\n用户中断操作")
            return False
        except Exception as e:
            print(f"运行过程中出错: {e}")
            return False
        finally:
            # 关闭设备
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
    print("=== 插损测量系统 ===")
    measurer = InsertionLossMeasurer()
    measurer.run()

if __name__ == "__main__":
    main()
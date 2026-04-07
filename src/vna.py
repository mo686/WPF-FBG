import pyvisa
import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
import time
import os

class VNA:
    """
    思仪3671G 矢量网络分析仪控制类
    用于执行 S 参数测量并保存数据
    """
    
    def __init__(self, gpib_address=16, start_freq=10e6, stop_freq=30e9, 
                 points=6001, power=-10, if_bw=1000, param='S21', 
                 save_dir='./vna_data'):
        """
        初始化 VNA 类
        
        参数:
            gpib_address: GPIB 地址
            start_freq: 起始频率 (Hz)
            stop_freq: 终止频率 (Hz)
            points: 扫描点数
            power: 输出功率 (dBm)
            if_bw: 中频带宽 (Hz)
            param: 待测参数（如 'S21'）
            save_dir: 数据保存目录
        """
        self.gpib_address = gpib_address
        self.resource_name = f'GPIB1::{gpib_address}::INSTR'
        self.start_freq = start_freq
        self.stop_freq = stop_freq
        self.points = points
        self.power = power
        self.if_bw = if_bw
        self.param = param
        self.save_dir = save_dir
        
        self.rm = None
        self.vna = None
        self.connected = False
        
        # 创建保存目录
        if not os.path.exists(self.save_dir):
            os.makedirs(self.save_dir)
            print(f"创建目录: {self.save_dir}")
    
    def connect(self):
        """
        连接到 VNA 仪器
        """
        try:
            self.rm = pyvisa.ResourceManager()
            self.vna = self.rm.open_resource(self.resource_name)
            self.vna.timeout = 60000  # 超时时间 (ms)
            self.vna.write_termination = '\n'  # 写入终止符
            self.vna.read_termination = '\n'   # 读取终止符
            self.connected = True
            print("连接成功")
            return True
        except Exception as e:
            print("连接失败:", e)
            return False
    
    def setup_parameters(self):
        """
        设置测量参数
        """
        if not self.connected:
            print("错误：未连接到仪器")
            return False
        
        try:
            print("设置仪器参数...")
            self.vna.write("*RST")                     # 复位仪器
            self.vna.write(f":SENS:FREQ:STAR {self.start_freq}")
            self.vna.write(f":SENS:FREQ:STOP {self.stop_freq}")
            self.vna.write(f":SENS:SWE:POIN {self.points}")
            self.vna.write(f":SOUR:POW {self.power}")
            self.vna.write(f":SENS:BAND {self.if_bw}")      # 设置中频带宽

            # 创建并选择测量参数
            meas_name = "MEAS1"
            self.vna.write(f':CALC:PAR:DEF:EXT "{meas_name}", "{self.param}"')
            self.vna.write(f':CALC:PAR:SEL "{meas_name}"')

            # 关闭连续扫描
            self.vna.write(":INIT:CONT OFF")
            print("参数设置完成")
            return True
        except Exception as e:
            print("参数设置失败:", e)
            return False
    
    def measure(self):
        """
        执行单次测量
        
        返回:
            dict: 包含测量数据的字典，包括频率、S参数、幅度和相位
        """
        if not self.connected:
            print("错误：未连接到仪器")
            return None
        
        try:
            start_time = time.time()
            
            print("开始扫描...")
            self.vna.write(":INIT:IMM")                # 启动单次扫描
            self.vna.query("*OPC?")                    # 等待扫描完成（返回 "1"）

            print("扫描完成，读取数据...")

            # 读取频率数据
            freq_str = self.vna.query(":SENS1:X?")
            freq = np.array(freq_str.strip().split(','), dtype=float)

            # 读取复数数据（修正后原始数据）
            data_str = self.vna.query(":CALC1:DATA? SDATA")
            data_vals = np.array(data_str.strip().split(','), dtype=float)

            # 解析为复数数组
            if len(data_vals) % 2 != 0:
                print("警告：读取的数据长度不是偶数，可能数据不完整")
                return None
            s_param = data_vals[0::2] + 1j * data_vals[1::2]

            # 检查数据长度是否匹配
            if len(freq) != len(s_param):
                print(f"错误：频率数据长度 ({len(freq)}) 与 S 参数数据长度 ({len(s_param)}) 不匹配")
                return None

            elapsed = time.time() - start_time
            print(f"数据读取完成，耗时 {elapsed:.2f} 秒")

            # 计算幅度 (dB) 和相位 (度)
            magnitude_dB = 20 * np.log10(np.abs(s_param))
            phase_deg = np.angle(s_param, deg=True)

            return {
                'frequency': freq,
                's_param': s_param,
                'magnitude_dB': magnitude_dB,
                'phase_deg': phase_deg
            }
        except Exception as e:
            print("测量失败:", e)
            return None
    
    def save_data(self, data, filename=None):
        """
        保存测量数据到 CSV 文件
        
        参数:
            data: 测量数据字典
            filename: 文件名（可选）
            
        返回:
            str: 保存的文件路径
        """
        if data is None:
            print("错误：无数据可保存")
            return None
        
        try:
            if filename is None:
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                filename = f'vna_{self.param.lower()}_measurement_{timestamp}.csv'
            
            csv_path = os.path.join(self.save_dir, filename)
            
            df = pd.DataFrame({
                'Frequency_Hz': data['frequency'],
                'Real': np.real(data['s_param']),
                'Imaginary': np.imag(data['s_param']),
                'Magnitude_dB': data['magnitude_dB'],
                'Phase_deg': data['phase_deg']
            })
            df.to_csv(csv_path, index=False)
            print(f"数据已保存至 {csv_path}")
            return csv_path
        except Exception as e:
            print("保存数据失败:", e)
            return None
    
    def plot(self, data, filename=None, show=True):
        """
        绘制测量数据图表
        
        参数:
            data: 测量数据字典
            filename: 文件名（可选）
            show: 是否显示图表
            
        返回:
            str: 保存的图片路径
        """
        if data is None:
            print("错误：无数据可绘制")
            return None
        
        try:
            freq_ghz = data['frequency'] / 1e9
            
            plt.figure(figsize=(10, 6))

            plt.subplot(2, 1, 1)
            plt.plot(freq_ghz, data['magnitude_dB'], 'b-', linewidth=1)
            plt.grid(True)
            plt.ylabel('Magnitude (dB)')
            plt.title(f'{self.param} Magnitude Response')

            plt.subplot(2, 1, 2)
            plt.plot(freq_ghz, data['phase_deg'], 'r-', linewidth=1)
            plt.grid(True)
            plt.xlabel('Frequency (GHz)')
            plt.ylabel('Phase (deg)')
            plt.title(f'{self.param} Phase Response')

            plt.tight_layout()
            
            if filename is None:
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                filename = f'vna_{self.param.lower()}_plot_{timestamp}.png'
            
            plot_path = os.path.join(self.save_dir, filename)
            plt.savefig(plot_path, dpi=300)
            
            if show:
                plt.show()
            else:
                plt.close()
            
            print(f"图表已保存至 {plot_path}")
            return plot_path
        except Exception as e:
            print("绘制图表失败:", e)
            return None
    
    def run_measurements(self, measurement_times=1, save=True, plot=True):
        """
        执行多次测量
        
        参数:
            measurement_times: 测量次数
            save: 是否保存数据
            plot: 是否绘制图表
            
        返回:
            list: 保存的文件路径列表
        """
        if not self.connected:
            print("错误：未连接到仪器")
            return []
        
        saved_files = []
        
        for i in range(measurement_times):
            print("\n" + "="*50)
            print(f"测量 #{i + 1}/{measurement_times}")
            print("="*50)
            
            # 执行测量
            data = self.measure()
            if data is None:
                continue
            
            # 保存数据
            if save:
                csv_path = self.save_data(data)
                if csv_path:
                    saved_files.append(csv_path)
            
            # 绘制图表
            if plot:
                self.plot(data)
        
        return saved_files
    
    def close(self):
        """
        关闭连接
        """
        if self.vna:
            try:
                self.vna.close()
            except:
                pass
        if self.rm:
            try:
                self.rm.close()
            except:
                pass
        self.connected = False
        print("连接已关闭")
    
    def __enter__(self):
        """
        上下文管理器入口
        """
        self.connect()
        self.setup_parameters()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        上下文管理器出口
        """
        self.close()


def main():
    """
    主函数，演示 VNA 类的使用
    """
    # 打印设置信息
    print("=== 思仪3671G S21 参数提取（Python版）===")
    
    # 使用上下文管理器创建 VNA 实例
    with VNA(gpib_address=16, 
             start_freq=10e6, 
             stop_freq=30e9, 
             points=6001, 
             power=-10, 
             if_bw=1000, 
             param='S21') as vna:
        
        # 执行3次测量
        vna.run_measurements(measurement_times=1, save=True, plot=True)

    print("\n程序结束。")

if __name__ == "__main__":
    main()
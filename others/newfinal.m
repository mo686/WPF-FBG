% function simple_vna_data_acquisition()
% 思仪3671G简化数据采集程序
% 直接读取指定参数的测量数据

clear; close all; clc;

%% 仪器连接参数
gpib_address = 16;  % GPIB地址

%% 测量参数设置（直接修改这里的值）
start_freq = 10e6;    % 起始频率(Hz)
stop_freq = 30e9;     % 终止频率(Hz)
points = 6001;        % 扫描点数
power_level = -10;   % 输出功率(dBm)
if_bandwidth = 1000; % 中频带宽(Hz)
param = 'S11'; % 测试参数(S11/S21/S12/S22)

fprintf('=== 思仪3671G简化数据采集 ===\n');
fprintf('参数设置:\n');
fprintf('  频率范围: %.1f MHz - %.1f MHz\n', start_freq/1e6, stop_freq/1e6);
fprintf('  扫描点数: %d\n', points);
fprintf('  输出功率: %.1f dBm\n', power_level);
fprintf('  中频带宽: %.0f Hz\n', if_bandwidth);
fprintf('  测试参数: %s\n\n', param);

tic % 开始计时

%% 1. 建立GPIB连接
fprintf('连接仪器...');
instrreset;
vna = gpib('ni', 0, gpib_address);
vna.InputBufferSize = 1000000;
vna.Timeout = 60;
fopen(vna);
fprintf('成功\n');

%% 2. 发送简单设置命令
fprintf('设置仪器参数...');

% 复位仪器
fprintf(vna,"*RST\n");

fprintf(vna, sprintf(':SENS:FREQ:STAR %g', start_freq));
fprintf(vna, sprintf(':SENS:FREQ:STOP %g', stop_freq));
fprintf(vna, sprintf(':SENS:SWE:POIN %d', points));
fprintf(vna, sprintf(':SOUR:POW %g', power_level));

% 3. 配置测量
measName = 'MEAS1';
fprintf(vna, sprintf(':CALC:PAR:DEF:EXT "%s", "%s"', measName, param));
fprintf(vna, sprintf(':CALC:PAR:SEL "%s"', measName));

% 4. 执行单次扫描
fprintf(vna, ':INIT:CONT OFF');
fprintf(vna, ':INIT:IMM');

% 5. 等待扫描完成
fprintf(vna, '*OPC?');
fprintf('完成\n');

%     % 6. 读取数据
fprintf(vna, ':SENS1:X?');
freq_data = str2num(fscanf(vna)); %#ok<ST2NM>

% 读取测量数据（实部+虚部）
fprintf(vna, ':CALC1:DATA? SDATA');
% pause(1);
rawData = str2num(fscanf(vna)); %#ok<ST2NM>
% 在此处编写你的代码
toc % 结束计时并输出所用时间


%     rawData = fprintf(vna);

% 7. 解析数据
for n = 1:length(rawData)/2
    data(n) = rawData(2*n-1) + 1i*rawData(2*n);
end

%     % 8. 生成频率数组
%      freq = linspace(startFreq, stopFreq, points)';
% 9. 关闭连接
clear vna;
s21 =data;
% 计算幅度和相位
magnitude = 20*log10(abs(s21));
phase = angle(s21) * 180/pi;

% 绘制结果
figure;
subplot(2,1,1);
plot(freq_data/1e9, magnitude);
xlabel('Frequency (GHz)');
ylabel('Magnitude (dB)');
title(sprintf('%s Magnitude Response', param));
grid on;

subplot(2,1,2);
plot(freq_data/1e9, phase);
xlabel('Frequency (GHz)');
ylabel('Phase (deg)');
title(sprintf('%s Phase Response', param));
grid on;

% 保存数据
dataTable = table(freq, real(s21), imag(s21), magnitude, phase, ...
    'VariableNames', {'Frequency_Hz', 'Real', 'Imaginary', 'Magnitude_dB', 'Phase_deg'});
writetable(dataTable, 'vna_measurement.csv');

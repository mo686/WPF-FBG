#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
目标函数管理器基类
提供所有目标函数管理器共有的方法
"""

import time
import numpy as np
import ast
from santec import StsProcess

class BaseFunctionManager:
    """
    目标函数管理器的基类
    提供所有管理器共有的方法和接口
    """
    
    def __init__(self, ilsts: StsProcess, voltage_controller, auto_scan_methods=True):
        """
        初始化基类
        
        参数:
            ilsts: StsProcess实例
            voltage_controller: 电压控制器实例
        """
        self.ilsts = ilsts
        self.voltage_controller = voltage_controller
        self.wait_time = 0.5
        self.error_output = {'voltages': -1, 'fom': 1000.0}
        self.available_functions = {}  # 子类需要重写这个

        # 自动扫描类中的方法
        if auto_scan_methods:
            self._scan_and_register_methods()
    
    def _scan_and_register_methods(self):
        """
        自动扫描类中的方法并注册到available_functions
        """
        print(f"正在扫描 {self.__class__.__name__} 中的目标函数...")
        
        # 定义要排除的方法（基类方法和特殊方法）
        exclude_methods = {
            '__init__', '__class__', '__del__', '__str__', '__repr__',
            '_scan_and_register_methods', 'get_error_output', 'set_wait_time',
            'update_function_parameters', 'get_function_metadata', 
            '_format_result_output', '_print_formatted_result',
            '_validate_measurement_data', '_set_voltages_and_wait',
            '_get_spectrum_data', 'list_available_functions',
            'display_function_info', 'get_function_by_index', 'get_configuration',
            'check_instrument_connection', 'is_ready_for_measurement',
            'extract_function_metadata_static', '_extract_ast_value',
            '_extract_function_description', '_extract_function_parameters',
            '_extract_set_params_dict', 'update_all_functions_comprehensive'
        }
        
        registered_count = 0
        
        # 扫描所有方法
        for method_name in dir(self):
            # 排除私有方法和特殊方法
            if method_name.startswith('_') and not method_name.startswith('__'):
                continue
                
            # 排除基类方法和特殊方法
            if method_name in exclude_methods:
                continue
                
            method = getattr(self, method_name)
            
            # 检查是否是可调用方法且不是属性
            if callable(method) and not isinstance(method, type):
                # 检查方法是否有合适的签名（至少接受voltages参数）
                try:
                    import inspect
                    sig = inspect.signature(method)
                    params = list(sig.parameters.keys())
                    
                    # 目标函数应该至少接受voltages参数
                    if len(params) >= 1 and ('voltages' in params):
                        # 注册方法
                        self.available_functions[method_name] = {
                            "function": method,
                            "description": "",  # 初始为空，后续通过静态分析填充
                            "parameters": {}    # 初始为空，后续通过静态分析填充
                        }
                        print(f"✓ 注册目标函数: {method_name}")
                        registered_count += 1
                        
                except (ValueError, TypeError):
                    continue
        
        print(f"扫描完成，共注册 {registered_count} 个目标函数")
        
        # 自动通过静态分析更新元数据
        self.update_all_functions_comprehensive()
    
    def get_error_output(self):
        """
        获取标准错误输出
        
        返回:
            dict: 标准错误输出字典
        """
        return self.error_output.copy()
    
    def _format_result_output(self, result, function_name=""):
        """
        统一格式化输出结果
        
        参数:
            result: 原始结果字典
            function_name: 函数名称
            
        返回:
            dict: 格式化后的结果
        """
        # 确保结果包含必要字段
        formatted_result = result.copy()
        
        # 添加格式化字段
        if 'voltages' in formatted_result and formatted_result['voltages'] is not None:
            if isinstance(formatted_result['voltages'], (list, np.ndarray)):
                formatted_result['voltages_formatted'] = [f"{v:.2f}V" for v in formatted_result['voltages']]
            else:
                formatted_result['voltages_formatted'] = f"{formatted_result['voltages']:.2f}V"
        
        # 格式化FOM值
        if 'fom' in formatted_result and formatted_result['fom'] is not None:
            formatted_result['fom'] = round(formatted_result['fom'], 6)
        
        # 打印格式化结果
        self._print_formatted_result(formatted_result, function_name)
        
        return formatted_result
    
    def _print_formatted_result(self, result, function_name):
        """
        统一打印格式化结果
        
        参数:
            result: 格式化后的结果字典
            function_name: 函数名称
        """
        print(f"\n{'='*60}")
        if function_name:
            print(f"📊 {function_name} 优化结果")
        else:
            print(f"📊 优化结果")
        print(f"{'='*60}")
        
        # 显示FOM值
        fom_value = result.get('fom', 'N/A')
        print(f"🎯 目标函数值 (FOM): {fom_value}")
        
        # 显示电压信息
        voltages_fmt = result.get('voltages_formatted', 'N/A')
        print(f"⚡ 施加电压: {voltages_fmt}")
        
        # 显示其他详细信息（排除系统字段）
        system_fields = ['voltages', 'fom', 'voltages_formatted', 'description', 'parameters']
        for key, value in result.items():
            if key not in system_fields:
                if isinstance(value, float):
                    print(f"   {key}: {value:.3f}")
                elif isinstance(value, (list, np.ndarray)) and len(value) > 0 and isinstance(value[0], float):
                    print(f"   {key}: {[f'{v:.3f}' for v in value]}")
                else:
                    print(f"   {key}: {value}")
        
        # 显示描述信息
        if 'description' in result:
            print(f"📝 {result['description']}")
        
        print(f"{'='*60}")
    
    def _set_voltages_and_wait(self, voltages, wait_time=None):
        """
        设置电压并等待稳定的通用方法
        
        参数:
            voltages: 电压数组
            wait_time: 等待时间(秒)，如果为None则使用self.wait_time
            
        返回:
            bool: 是否成功设置电压
        """
        if wait_time is None:
            wait_time = self.wait_time
            
        success = self.voltage_controller.set_voltages(voltages)
        if success:
            time.sleep(wait_time)
        return success
    
    def _get_spectrum_data(self, channels):
        """
        功能：获取指定通道的光谱数据
        参数:
            channels: 通道列表
        返回:
            tuple: (波长数组, 各通道功率数组)
        """
        try:
            # 执行测量
            self.ilsts.sts_measurement()
            
            # 获取波长数据
            if hasattr(self.ilsts, 'wavelength_table'):
                wavelengths = np.array(self.ilsts.wavelength_table)
            else:
                raise ValueError("无法获取波长数据")
            
            # 获取各通道功率数据
            channel_powers = []
            for ch_idx in channels:
                if hasattr(self.ilsts, 'il_data_array') and len(self.ilsts.il_data_array) >= ch_idx:
                    channel_powers.append(np.array(self.ilsts.il_data_array[ch_idx-1]))
                else:
                    raise ValueError(f"无法获取通道{ch_idx}的数据")
            
            return wavelengths, channel_powers
            
        except Exception as e:
            print(f"获取光谱数据时出错: {e}")
            raise
    
    def list_available_functions(self):
        """
        功能：列出所有可用的目标函数
        返回:
            dict: 可用函数字典
        """
        return self.available_functions.copy()
    
    def display_function_info(self):
        """
        功能：显示所有可用目标函数的信息
        返回:
            int: 可用函数数量
        """
        print(f"\n{'='*50}")
        print(f"📋 可用目标函数列表 ({self.__class__.__name__})")
        print(f"{'='*50}")
        
        for i, (name, info) in enumerate(self.available_functions.items(), 1):
            print(f"{i}. {name}")
            print(f"📝 描述: {info['description']}")
            # if info.get('parameters'):
            #     print(f"   参数: {info['parameters']}")
            print()
        
        total_functions = len(self.available_functions)
        print(f"总计: {total_functions} 个函数")
        return total_functions
    
    def get_function_by_index(self, index: int):
        """
        功能：通过索引获取目标函数
        
        参数:
            index: 函数索引(从1开始)
            
        返回:
            function: 目标函数
            dict: 函数信息
        """
        function_names = list(self.available_functions.keys())
        if 1 <= index <= len(function_names):
            function_name = function_names[index - 1]
            function_info = self.available_functions[function_name]
            
            # 显示选中函数的详细信息，包括参数值
            print(f"\n{'='*60}")
            print(f"📋 已选择目标函数: {function_name}")
            print(f"{'='*60}")
            
            if function_info.get('parameters'):
                print(f"🔧 参数配置:")
                for param_name, param_value in function_info['parameters'].items():
                    print(f"    {param_name}: {param_value}")
            else:
                print("🔧 参数: 无")
            
            return function_info['function'], function_info
        else:
            raise ValueError(f"无效的函数索引: {index}，可用索引范围: 1-{len(function_names)}")
    
    def extract_function_metadata_static(self, func):
        """
        功能：通过静态分析函数源代码来提取完整的函数元数据
        参数:
            func: 目标函数           
        返回:
            dict: 包含描述和参数名和默认值的字典
        """
        import inspect
        import ast
        
        try:
            # 获取函数的源代码
            func_source = inspect.getsource(func)
            
            # 修复缩进问题
            lines = func_source.split('\n')
            first_non_empty_line = None
            for line in lines:
                if line.strip():
                    first_non_empty_line = line
                    break
            
            if first_non_empty_line:
                indent_level = len(first_non_empty_line) - len(first_non_empty_line.lstrip())
                fixed_lines = []
                for line in lines:
                    if line.strip():
                        if line.startswith(' ' * indent_level):
                            fixed_lines.append(line[indent_level:])
                        else:
                            fixed_lines.append(line)
                    else:
                        fixed_lines.append(line)
                
                func_source = '\n'.join(fixed_lines)
            
            # 解析源代码为AST
            tree = ast.parse(func_source)
            
            # 提取函数文档字符串（描述）
            description = self._extract_function_description(tree)
            
            # 提取参数信息（从函数签名）
            parameters = self._extract_function_parameters(tree)
            
            # 提取set_params字典中的默认参数
            set_params = self._extract_set_params_dict(tree)
            
            # 合并参数信息：优先级 params > set_params > 函数参数
            final_parameters = {}
            
            # 首先添加函数参数
            for key, value in parameters.items():
                final_parameters[key] = value
            
            # 然后添加set_params（覆盖同名参数）
            for key, value in set_params.items():
                final_parameters[key] = value

            return {
                'description': description,
                'parameters': final_parameters
            }
            
        except Exception as e:
            print(f"提取函数 {func.__name__} 的元数据时出错: {e}")
            return None
    
    def _extract_ast_value(self, node):
        """
        从AST节点提取值 - 兼容各种Python版本
        """
        try:
            # 尝试用常量类型提取（Python 3.8+）
            if hasattr(ast, 'Constant') and isinstance(node, ast.Constant):
                return node.value
            
            # 尝试用数字类型提取（Python 3.7-）
            if isinstance(node, ast.Num):
                return node.n
            
            # 尝试用字符串类型提取（Python 3.7-）
            if isinstance(node, ast.Str):
                return node.s
            
            # 处理负数（如 -6.0）
            if isinstance(node, ast.UnaryOp):
                if isinstance(node.op, ast.USub):
                    operand = node.operand
                    operand_value = self._extract_ast_value(operand)
                    if operand_value is not None:
                        return -operand_value
            
            # 处理列表
            if isinstance(node, ast.List):
                return [self._extract_ast_value(elt) for elt in node.elts]
            
            # 处理元组
            if isinstance(node, ast.Tuple):
                return tuple([self._extract_ast_value(elt) for elt in node.elts])
            
            # 处理表达式（如 -6.0 可能被解析为表达式）
            if isinstance(node, ast.Expr):
                return self._extract_ast_value(node.value)
            
        except Exception as e:
            print(f"提取AST值时出错: {e}")
        
        return None
    
    def _extract_function_description(self, tree):
        """
        从AST树中提取函数文档字符串
        参数:
            tree: AST树
        返回:
            str: 函数描述
        """
        description = ""
        
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                # 获取函数的文档字符串
                docstring = ast.get_docstring(node)
                if docstring:
                    # 提取第一行或前几行作为描述
                    lines = docstring.strip().split('\n')
                    if lines:
                        # 取第一行，去除多余的空格
                        description = lines[0].strip()
                        # 如果第一行太短，考虑取更多内容
                        if len(description) < 10 and len(lines) > 1:
                            description = ' '.join([line.strip() for line in lines[:2]])
                break
        
        return description
    
    def _extract_function_parameters(self, tree):
        """
        从AST树中提取函数参数信息
        
        参数:
            tree: AST树
            
        返回:
            dict: 参数信息字典
        """
        parameters = {}
        
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                # 分析函数参数
                for arg in node.args.args:
                    if arg.arg not in ['self', 'voltages']:  # 排除self和voltages参数
                        parameters[arg.arg] = None  # 参数名，没有默认值
                
                # 如果有默认值参数
                if node.args.defaults:
                    # 计算有默认值的参数数量
                    num_defaults = len(node.args.defaults)
                    # 有默认值的参数从参数列表的末尾开始
                    args_with_defaults = node.args.args[-num_defaults:]
                    
                    for arg, default in zip(args_with_defaults, node.args.defaults):
                        if arg.arg not in ['self', 'voltages']:
                            default_value = self._extract_ast_value(default)
                            if default_value is not None:
                                parameters[arg.arg] = default_value
                break
        
        return parameters

    def _extract_set_params_dict(self, tree):
        """
        从AST树中提取params字典
        参数:
            tree: AST树
            
        返回:
            dict: params字典内容
        """
        set_params_dict = {}
        
        for node in ast.walk(tree):
            # 查找赋值语句，目标为params
            if (isinstance(node, ast.Assign) and 
                len(node.targets) == 1 and 
                isinstance(node.targets[0], ast.Name) and 
                node.targets[0].id == 'params'):
                
                # 检查赋值值是否为字典
                if isinstance(node.value, ast.Dict):
                    keys = node.value.keys
                    values = node.value.values
                    
                    # 提取字典的键值对
                    for key_node, value_node in zip(keys, values):
                        if isinstance(key_node, ast.Constant):  # 字符串键
                            key = key_node.value
                            value = self._extract_ast_value(value_node)
                            if value is not None:
                                set_params_dict[key] = value
                break
        
        return set_params_dict

    def update_all_functions_comprehensive(self):
        """
        通过静态分析全面更新所有目标函数的元数据
        """
        print("正在通过静态分析全面更新目标函数元数据...")
        
        updated_count = 0
        for func_name, func_info in self.available_functions.items():
            func = func_info['function']
            
            # 提取完整的函数元数据
            metadata = self.extract_function_metadata_static(func)
            
            if metadata:
                # 更新描述（如果提取到了新的描述）
                if metadata['description'] and metadata['description'] != func_info.get('description', ''):
                    func_info['description'] = metadata['description']
                    print(f"✓ 已更新函数 '{func_name}' 的描述: {metadata['description']}")
                
                # 更新参数
                if metadata['parameters']:
                    func_info['parameters'] = metadata['parameters']
                    print(f"✓ 已更新函数 '{func_name}' 的参数: {metadata['parameters']}")
                
                updated_count += 1
            else:
                print(f"⚠ 无法从函数 '{func_name}' 中提取元数据")
        
        print(f"全面静态分析完成，成功更新了 {updated_count}/{len(self.available_functions)} 个函数的元数据")
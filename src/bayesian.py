import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
import pickle
import time
import os
from datetime import datetime
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import RBF, WhiteKernel, ConstantKernel
from sklearn.preprocessing import StandardScaler

class Bayesian:
    """基础贝叶斯优化器类"""
    
    def __init__(self, bounds, integer_params, param_names, 
                run_id = 1,
                n_init = 15,
                n_iter = 105,
                early_stopping_patience = 20,
                early_stopping_threshold = 1e-3,  # 早停阈值
                exploration_factor = 0.6,
                local_ratio = 0.4,
                use_knowledge_guide = False,
                knowledge_file = None,
                sampling_strategy = 'mixed',
                lhs_ratio = 0.9,
                boundary_ratio = 0.1,
                min_distance = 0.0001,
                candidate_count = 1000,
                sobol_scramble = True,
                halton_scramble = True
                ):
        """
        初始化基础贝叶斯优化器
        """
        self.bounds = np.array(bounds)
        self.integer_params = integer_params
        self.param_names = param_names
        self.n_init = n_init
        self.n_iter = n_iter
        self.total_evaluations = n_init + n_iter
        self.run_id = run_id
        self.use_knowledge_guide = use_knowledge_guide
        self.knowledge_file = knowledge_file
        self.exploration_factor = exploration_factor
        self.local_ratio = local_ratio
        self.early_stopping_patience = early_stopping_patience
        self.early_stopping_threshold = early_stopping_threshold

        # 新增采样策略参数
        self.sampling_strategy = sampling_strategy
        self.lhs_ratio = lhs_ratio
        self.boundary_ratio = boundary_ratio
        self.min_distance = min_distance
        self.candidate_count = candidate_count
        self.sobol_scramble = sobol_scramble
        self.halton_scramble = halton_scramble
        
        # 不再创建目录，由适配器设置
        self.run_dir = None
        
        # 保存算法配置
        self.algorithm_config = {
            'n_init': n_init,
            'n_iter': n_iter,
            'total_evaluations': n_init + n_iter,
            'early_stopping_patience': early_stopping_patience,
            'early_stopping_threshold': early_stopping_threshold,
            'exploration_factor': exploration_factor,
            'local_ratio': local_ratio,
            'use_knowledge_guide': use_knowledge_guide,
            'knowledge_file': knowledge_file,
            'sampling_strategy': sampling_strategy,
            'lhs_ratio': lhs_ratio,
            'boundary_ratio': boundary_ratio,
            'min_distance': min_distance,
            'candidate_count': candidate_count,
            'sobol_scramble': sobol_scramble,
            'halton_scramble': halton_scramble,
            'initial_gamma': 0.3,
            'final_gamma': 0.1
        }
        
        # 数据标准化器
        self.continuous_indices = [i for i in range(len(param_names)) if i not in integer_params]
        self.X_scaler = StandardScaler()
        self.y_scaler = StandardScaler()

        # 基于 min_distance 设置电压精度
        self.voltage_precision = min_distance
        self.voltage_decimals = max(0, -int(np.log10(self.voltage_precision)) + 1)
        
        # 高斯过程配置 - 使用标准化空间中的合理边界
        n_dims = len(self.continuous_indices)
        self.kernel = ConstantKernel(1.0) * RBF(
            length_scale=[1.0] * n_dims,
            length_scale_bounds=[(1e-3, 1e3)] * n_dims
        ) + WhiteKernel(
            noise_level=0.01,
            noise_level_bounds=(1e-6, 1.0)
        )

        self.gp = GaussianProcessRegressor(
            kernel=self.kernel,
            n_restarts_optimizer=5,
            normalize_y=False,  # 手动标准化
            random_state=self.run_id,
            alpha=1e-6
        )
        
        # 优化历史
        self.X_history = np.empty((0, len(self.param_names)))
        self.y_history = []
        self.best_x = None
        self.best_y = float('inf')
        self.iteration_data = []
        
        # 动态LCB参数
        self.initial_gamma = 0.3
        self.final_gamma = 0.1
        self.gamma = self.initial_gamma
        
        # 知识引导相关
        self.prior_knowledge = None
        self.optimal_regions = None
        if use_knowledge_guide and knowledge_file:
            self._load_and_analyze_knowledge(knowledge_file)
        
        # 早停相关变量
        self.no_improvement_count = 0
        self.best_y_so_far = float('inf')
        
        print(f"🎯 初始化贝叶斯优化器 (运行{run_id})")
        print(f"   参数数量: {len(param_names)} (其中{len(integer_params)}个整数参数)")
        print(f"   优化策略: {n_init}初始点 + {n_iter}次贝叶斯迭代")
        print(f"   早停机制: 耐心值={early_stopping_patience}, 阈值={early_stopping_threshold}")
        print(f"   知识引导: {'启用' if use_knowledge_guide else '禁用'}")
        print(f"   采样策略: {sampling_strategy}")

    def set_run_directory(self, run_dir):
        """由适配器设置运行目录"""
        self.run_dir = run_dir

    def save_algorithm_config(self):
        """保存贝叶斯算法配置到文件"""
        if not self.run_dir:
            print("⚠️ 运行目录未设置，跳过保存算法配置")
            return
            
        config_file = os.path.join(self.run_dir, 'bayesian_algorithm_config.txt')
        
        with open(config_file, 'w', encoding='utf-8') as f:
            f.write("贝叶斯优化算法配置详情\n")
            f.write("=" * 50 + "\n\n")
            
            f.write("【基本参数配置】\n")
            f.write("-" * 30 + "\n")
            f.write(f"初始采样点数量: {self.algorithm_config['n_init']}\n")
            f.write(f"迭代次数: {self.algorithm_config['n_iter']}\n")
            f.write(f"总评估次数: {self.algorithm_config['total_evaluations']}\n")
            f.write(f"早停耐心值: {self.algorithm_config['early_stopping_patience']}\n")
            f.write(f"早停阈值: {self.algorithm_config['early_stopping_threshold']}\n")
            f.write(f"探索因子: {self.algorithm_config['exploration_factor']}\n")
            f.write(f"局部候选点比例: {self.algorithm_config['local_ratio']}\n")
            
            f.write(f"\n【早停机制说明】\n")
            f.write("-" * 40 + "\n")
            f.write(f"触发条件: 连续无显著改进次数 ≥ {self.algorithm_config['early_stopping_patience']}\n")
            f.write(f"显著改进: FOM改进 > {self.algorithm_config['early_stopping_threshold']}\n")
            f.write(f"注: 改进小于阈值时计入'无改进'次数\n")

            f.write(f"\n【采样策略配置】\n")
            f.write("-" * 30 + "\n")
            f.write(f"采样策略: {self.algorithm_config['sampling_strategy']}\n")
            if self.algorithm_config['sampling_strategy'] == 'mixed':
                f.write(f"LHS采样比例: {self.algorithm_config['lhs_ratio']}\n")
                f.write(f"边界采样比例: {self.algorithm_config['boundary_ratio']}\n")
            f.write(f"候选点数量: {self.algorithm_config['candidate_count']}\n")
            f.write(f"最小点间距: {self.algorithm_config['min_distance']}\n")
            f.write(f"Sobol序列加扰: {'是' if self.algorithm_config['sobol_scramble'] else '否'}\n")
            f.write(f"Halton序列加扰: {'是' if self.algorithm_config['halton_scramble'] else '否'}\n")
            
            f.write(f"\n【知识引导配置】\n")
            f.write("-" * 30 + "\n")
            f.write(f"知识引导: {'启用' if self.algorithm_config['use_knowledge_guide'] else '禁用'}\n")
            if self.algorithm_config['use_knowledge_guide']:
                f.write(f"知识文件: {self.algorithm_config['knowledge_file']}\n")
                f.write("优质区域采样: 70%在优质区域，30%在全局范围\n")
            
            f.write(f"\n【候选点生成策略】\n")
            f.write("-" * 30 + "\n")
            f.write(f"全局候选点比例: {1 - self.algorithm_config['local_ratio']:.1%}\n")
            f.write(f"局部候选点比例: {self.algorithm_config['local_ratio']:.1%}\n")
            f.write("局部扰动: 基于最佳点进行小范围随机扰动\n")
            f.write("整数参数: 在最佳点基础上加减1-3的整数扰动\n")
            f.write("连续参数: 基于参数范围的比例扰动\n")
            
            f.write(f"\n【配置时间】\n")
            f.write("-" * 30 + "\n")
            f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        
        print(f"贝叶斯算法配置已保存: bayesian_algorithm_config.txt")
    
    def _load_and_analyze_knowledge(self, knowledge_file):
        """加载并分析先验知识"""
        try:
            with open(knowledge_file, 'rb') as f:
                self.prior_knowledge = pickle.load(f)
            
            print(f"💡 已加载先验知识: {knowledge_file}")
            
            if 'all_evaluations' not in self.prior_knowledge:
                print("⚠️ 先验知识中没有评估数据")
                return
            
            evaluations = self.prior_knowledge['all_evaluations']
            if len(evaluations) < 5:
                print("⚠️ 先验数据点太少")
                return
            
            # 按FOM排序，选择前50%的优质点
            sorted_evals = sorted(evaluations, key=lambda x: x[1])
            n_top = max(5, int(len(evaluations) * 0.5))
            top_evals = sorted_evals[:n_top]
            top_points = np.array([point for point, fom in top_evals])
            
            print(f"📊 分析前50%优质区域 ({n_top}个点)")
            print(f"   FOM范围: {top_evals[0][1]:.6f} - {top_evals[-1][1]:.6f}")
            
            # 分析优质区域的参数范围
            self.optimal_regions = {}
            param_names = self.prior_knowledge.get('param_names', self.param_names)
            
            for i, param_name in enumerate(param_names):
                if i >= top_points.shape[1]:
                    continue
                    
                param_values = top_points[:, i]
                
                if param_name in ['N1', 'N2', 'N3']:
                    min_val = int(np.min(param_values))
                    max_val = int(np.max(param_values))
                    unique_vals = np.unique(param_values)
                    
                    self.optimal_regions[param_name] = {
                        'type': 'integer',
                        'min': min_val,
                        'max': max_val,
                        'common_values': unique_vals.tolist()
                    }
                else:
                    min_val = float(np.min(param_values))
                    max_val = float(np.max(param_values))
                    mean_val = float(np.mean(param_values))
                    std_val = float(np.std(param_values))
                    
                    self.optimal_regions[param_name] = {
                        'type': 'continuous',
                        'min': min_val,
                        'max': max_val,
                        'mean': mean_val,
                        'std': std_val
                    }
            
            print(f"✅ 已分析出 {len(self.optimal_regions)} 个参数的优化区域")
            
        except Exception as e:
            print(f"❌ 加载分析先验知识失败: {e}")
    
    def generate_initial_points(self):
        """生成初始点 - 根据采样策略"""
        print(f"🎯 生成 {self.n_init} 个初始点 (策略: {self.sampling_strategy})")
        
        if self.use_knowledge_guide and self.optimal_regions:
            # 知识引导：在优质区域和非优质区域混合采样
            n_optimal = max(1, int(self.n_init * 0.7))
            n_non_optimal = self.n_init - n_optimal
            
            optimal_points = self._generate_optimal_region_points(n_optimal)
            non_optimal_points = self._generate_points_by_strategy(n_non_optimal)
            points = np.vstack([optimal_points, non_optimal_points])
        else:
            # 根据采样策略生成点
            points = self._generate_points_by_strategy(self.n_init)
        
        # 打乱点顺序，增加随机性
        np.random.shuffle(points)
        
        # 显示生成的初始点信息
        for i, point in enumerate(points[:3]):
            print(f"   初始点{i+1}: {self._format_parameters(point)}")
        if len(points) > 3:
            print(f"   ... 共{len(points)}个点")
        
        return points
    
    def _generate_points_by_strategy(self, n_points):
        """根据采样策略生成点"""
        if self.sampling_strategy == 'mixed':
            return self._generate_mixed_points(n_points)
        elif self.sampling_strategy == 'lhs':
            return self._generate_global_lhs_points(n_points)
        elif self.sampling_strategy == 'random':
            return self._generate_enhanced_random_points(n_points)
        elif self.sampling_strategy == 'sobol':
            return self._generate_sobol_points(n_points)
        elif self.sampling_strategy == 'halton':
            return self._generate_halton_points(n_points)
        else:
            print(f"⚠️ 未知采样策略: {self.sampling_strategy}，使用混合采样")
            return self._generate_mixed_points(n_points)
    
    def _generate_mixed_points(self, n_points):
        """混合采样策略：LHS + 随机采样"""
        n_lhs = max(1, int(n_points * self.lhs_ratio))
        n_random = n_points - n_lhs
        
        lhs_points = self._generate_global_lhs_points(n_lhs)
        random_points = self._generate_enhanced_random_points(n_random)
        points = np.vstack([lhs_points, random_points])
        
        return points
    
    def _generate_sobol_points(self, n_points):
        """生成Sobol序列点"""
        try:
            from scipy.stats import qmc
            
            # 生成Sobol序列
            sobol = qmc.Sobol(d=len(self.param_names), scramble=self.sobol_scramble)
            samples = sobol.random(n_points)
            
            points = np.zeros((n_points, len(self.param_names)))
            for i in range(n_points):
                for j in range(len(self.param_names)):
                    points[i, j] = self._map_sample_to_range(samples[i, j], j)
            
            print(f"   Sobol序列采样: {n_points}个点")
            return points
            
        except ImportError:
            print("⚠️ 无法导入scipy.stats.qmc，使用LHS采样")
            return self._generate_global_lhs_points(n_points)
        except Exception as e:
            print(f"⚠️ Sobol采样异常: {e}，使用LHS采样")
            return self._generate_global_lhs_points(n_points)
    
    def _generate_halton_points(self, n_points):
        """生成Halton序列点"""
        try:
            from scipy.stats import qmc
            
            # 生成Halton序列
            halton = qmc.Halton(d=len(self.param_names), scramble=self.halton_scramble)
            samples = halton.random(n_points)
            
            points = np.zeros((n_points, len(self.param_names)))
            for i in range(n_points):
                for j in range(len(self.param_names)):
                    points[i, j] = self._map_sample_to_range(samples[i, j], j)
            
            print(f"   Halton序列采样: {n_points}个点")
            return points
            
        except ImportError:
            print("⚠️ 无法导入scipy.stats.qmc，使用LHS采样")
            return self._generate_global_lhs_points(n_points)
        except Exception as e:
            print(f"⚠️ Halton采样异常: {e}，使用LHS采样")
            return self._generate_global_lhs_points(n_points)
    
    def _generate_optimal_region_points(self, n_points):
        """在优质区域生成采样点"""
        if self.sampling_strategy == 'lhs':
            return self._generate_optimal_region_lhs_points(n_points)
        else:
            return self._generate_optimal_region_random_points(n_points)
    
    def _generate_optimal_region_random_points(self, n_points):
        """在优质区域生成随机点"""
        points = np.zeros((n_points, len(self.param_names)))
        
        for i in range(n_points):
            for j, param_name in enumerate(self.param_names):
                if param_name in self.optimal_regions:
                    region = self.optimal_regions[param_name]
                    if region['type'] == 'integer':
                        low, high = region['min'], region['max']
                        if low == high:
                            points[i, j] = low
                        else:
                            points[i, j] = np.random.randint(low, high + 1)
                    else:
                        low, high = region['min'], region['max']
                        if low == high:
                            points[i, j] = low
                        else:
                            points[i, j] = np.random.uniform(low, high)
                else:
                    low, high = self.bounds[j]
                    if j in self.integer_params:
                        points[i, j] = np.random.randint(low, high + 1)
                    else:
                        points[i, j] = np.random.uniform(low, high)
        
        return points
    
    def _generate_enhanced_random_points(self, n_points):
        """生成增强的随机点"""
        points = np.zeros((n_points, len(self.param_names)))
        
        # 采样策略分布
        n_boundary = max(1, int(n_points * self.boundary_ratio))
        n_interior = n_points - n_boundary
        
        for i in range(n_points):
            for j in range(len(self.param_names)):
                low, high = self.bounds[j]
                
                if i < n_boundary:
                    # 边界采样策略
                    if np.random.random() < 0.5:
                        value = low + np.random.random() * 0.2 * (high - low)
                    else:
                        value = high - np.random.random() * 0.2 * (high - low)
                else:
                    # 内部采样策略
                    value = np.random.uniform(low, high)
                
                points[i, j] = self._process_single_parameter(value, j)
        
        return points
    
    def _generate_optimal_region_lhs_points(self, n_points):
        """在优质区域生成LHS采样点"""
        points = np.zeros((n_points, len(self.param_names)))
        
        lhs_samples = self._generate_lhs_samples_with_bounds(n_points, len(self.param_names))
        for i in range(n_points):
            for j, param_name in enumerate(self.param_names):
                if param_name in self.optimal_regions:
                    region = self.optimal_regions[param_name]
                    if region['type'] == 'integer':
                        low, high = region['min'], region['max']
                        if low == high:
                            points[i, j] = low
                        else:
                            value = low + lhs_samples[i, j] * (high - low)
                            points[i, j] = int(round(value))
                    else:
                        low, high = region['min'], region['max']
                        if low == high:
                            points[i, j] = low
                        else:
                            points[i, j] = low + lhs_samples[i, j] * (high - low)
                else:
                    points[i, j] = self._map_sample_to_range(lhs_samples[i, j], j)
        
        return points
    
    def _generate_global_lhs_points(self, n_points):
        """在全局范围内生成LHS采样点"""
        try:
            if n_points <= 0:
                return np.empty((0, len(self.param_names)))
                
            points = np.zeros((n_points, len(self.param_names)))
            lhs_samples = self._generate_lhs_samples_with_bounds(n_points, len(self.param_names))
            
            for i in range(n_points):
                for j in range(len(self.param_names)):
                    points[i, j] = self._map_sample_to_range(lhs_samples[i, j], j)
            
            return points
            
        except Exception as e:
            print(f"⚠️ 全局LHS采样异常: {e}")
            return self._generate_random_points(n_points)
    
    def _generate_random_points(self, n_points):
        """生成随机点作为备用"""
        points = np.zeros((n_points, len(self.param_names)))
        for i in range(n_points):
            for j in range(len(self.param_names)):
                low, high = self.bounds[j]
                if j in self.integer_params:
                    points[i, j] = np.random.randint(low, high + 1)
                else:
                    points[i, j] = np.random.uniform(low, high)
        return points
    
    def _generate_lhs_samples_with_bounds(self, n_points, n_dims):
        """生成包含边界的LHS样本矩阵"""
        samples = np.zeros((n_points, n_dims))
        
        for j in range(n_dims):
            intervals = np.linspace(0, 1, n_points + 1)
            
            # 增加随机扰动
            perturbation = np.random.uniform(-0.1, 0.1, n_points)
            perturbation = np.clip(perturbation, -intervals[1]/2, intervals[1]/2)
            
            dim_samples = np.random.uniform(intervals[:-1], intervals[1:], n_points)
            dim_samples = np.clip(dim_samples + perturbation, 0, 1)
            
            np.random.shuffle(dim_samples)
            samples[:, j] = dim_samples
            
            # 确保包含边界点
            if np.random.random() < 0.8:
                samples[0, j] = 0.0
                samples[-1, j] = 1.0
        
        return samples
    
    def _map_sample_to_range(self, sample_value, param_index):
        """将样本值映射到参数范围"""
        low, high = self.bounds[param_index, 0], self.bounds[param_index, 1]    
        if param_index in self.integer_params:
            value = low + sample_value * (high - low)
            return int(round(value))
        else:
            value = low + sample_value * (high - low)
            if self.param_names[param_index].startswith('V'):
                return round(value / self.voltage_precision) * self.voltage_precision
            else:
                return value
    
    def _process_single_parameter(self, value, param_index):
        """处理单个参数值"""
        if param_index in self.integer_params:
            return int(round(value))
        else:
            if self.param_names[param_index].startswith('V'):
                return round(value / self.voltage_precision) * self.voltage_precision
            else:
                return value
    
    def _process_parameters(self, x):
        """处理参数"""
        processed = np.copy(x)
        for i in range(len(self.param_names)):
            processed[i] = self._process_single_parameter(x[i], i)
        return processed
    
    def _format_parameters(self, x):
        """格式化参数显示"""
        parts = []
        for i, name in enumerate(self.param_names):
            if name in ['N1', 'N2', 'N3']:
                parts.append(f"{name}={int(x[i])}")
            elif name.startswith('V'):
                # 使用计算得到的小数位数显示
                parts.append(f"{name}={x[i]:.{self.voltage_decimals}f}V")
            else:
                value_um = x[i] * 1e6
                parts.append(f"{name}={value_um:.3f}μm")
        return ", ".join(parts)
    
    def evaluate_point(self, x, objective_function):
        """评估点"""
        x_processed = self._process_parameters(x)
        
        try:
            param_str = self._format_parameters(x_processed)
            print(f"🔄 评估点: {param_str}")
            
            start_time = time.time()
            fom_value = objective_function(x_processed)
            eval_time = time.time() - start_time
            
            print(f"✅ FOM={fom_value:.6f}, 耗时: {eval_time:.1f}秒")
            return fom_value
            
        except Exception as e:
            print(f"❌ 评估异常: {e}")
            return float('inf')
    
    def get_next_point(self, n_candidates=None):
        """获取下一个评估点"""
        if n_candidates is None:
            n_candidates = self.candidate_count
            
        candidates = np.array([])
        try:
            n_local = int(n_candidates * self.local_ratio)
            n_global = n_candidates - n_local
            
            # 生成候选点
            global_candidates = self._generate_points_by_strategy(n_global) if n_global > 0 else []
            local_candidates = []
            if n_local > 0:
                for _ in range(n_local):
                    candidate = self._generate_local_candidate()
                    local_candidates.append(candidate)
                local_candidates = np.array(local_candidates)
            
            # 合并候选点
            if len(global_candidates) > 0 and len(local_candidates) > 0:
                candidates = np.vstack([global_candidates, local_candidates])
            elif len(global_candidates) > 0:
                candidates = global_candidates
            elif len(local_candidates) > 0:
                candidates = local_candidates
            
            # 处理参数精度
            for i in range(len(candidates)):
                candidates[i] = self._process_parameters(candidates[i])
            
            # 去重
            candidates = self._improved_deduplication(candidates)
            
            # 确保最小距离
            candidates = self._ensure_minimum_distance(candidates, self.min_distance)
            
            print(f"📋 生成候选点: 全局{n_global}个, 局部{n_local}个, 去重后{len(candidates)}个")
            
        except Exception as e:
            print(f"⚠️ 候选点生成异常: {e}")
            candidates = self._generate_points_by_strategy(n_candidates)
        
        # 确保candidates不为空
        if len(candidates) == 0:
            print("⚠️ 候选点为空，使用随机点")
            candidates = self._generate_points_by_strategy(10)
        
        # 选择下一个点
        if len(self.X_history) >= 3:
            try:
                acquisition_values = self._calculate_acquisition(candidates)
                best_idx = np.argmax(acquisition_values)
                best_candidate = candidates[best_idx]
                
                best_acq = acquisition_values[best_idx]
                print(f"  采集函数最佳值: {best_acq:.4f}")
                
            except Exception as e:
                print(f"⚠️ 采集函数选择异常: {e}")
                best_candidate = candidates[np.random.randint(0, len(candidates))]
        else:
            best_candidate = candidates[np.random.randint(0, len(candidates))]
            print("🔄 使用随机选择（样本不足）")
        
        best_candidate = self._process_parameters(best_candidate)
        print(f"🎯 选择点: {self._format_parameters(best_candidate)}")
        return best_candidate

    def _improved_deduplication(self, candidates):
        """改进的去重策略"""
        if len(candidates) <= 1:
            return candidates
        
        unique_candidates = []
        tolerance = 1e-4
        
        for candidate in candidates:
            is_duplicate = False
            for existing in unique_candidates:
                if np.allclose(candidate, existing, atol=tolerance):
                    is_duplicate = True
                    break
            if not is_duplicate:
                unique_candidates.append(candidate)
        
        return np.array(unique_candidates)

    def _generate_local_candidate(self):
        """生成局部候选点"""
        try:
            if self.best_x is None:
                return self._generate_points_by_strategy(1)[0]
            
            candidate = np.copy(self.best_x)
            
            for i in range(len(self.param_names)):
                if i in self.integer_params:
                    perturbation = np.random.choice([-3, -2, -1, 1, 2, 3])
                    new_value = candidate[i] + perturbation
                    candidate[i] = np.clip(new_value, int(self.bounds[i, 0]), int(self.bounds[i, 1]))
                else:
                    range_width = self.bounds[i, 1] - self.bounds[i, 0]
                    progress = min(1.0, len(self.X_history) / self.total_evaluations)
                    base_scale = 0.2
                    perturbation_scale = base_scale - (base_scale - 0.05) * progress
                    
                    perturbation = np.random.uniform(-range_width * perturbation_scale, 
                                                    range_width * perturbation_scale)
                    new_value = candidate[i] + perturbation
                    
                    candidate[i] = self._process_single_parameter(new_value, i)
                    candidate[i] = np.clip(candidate[i], self.bounds[i, 0], self.bounds[i, 1])
            
            return candidate
            
        except Exception as e:
            print(f"⚠️ 局部候选点生成异常: {e}")
            return self._generate_points_by_strategy(1)[0]

    def _ensure_minimum_distance(self, candidates, min_distance):
        """确保候选点之间的最小距离"""
        if len(candidates) <= 1:
            return candidates 
        
        filtered_candidates = [candidates[0]]
        
        for i in range(1, len(candidates)):
            candidate = candidates[i]
            too_close = False
            
            for existing in filtered_candidates:
                distance = np.linalg.norm(candidate - existing)
                if distance < min_distance:
                    too_close = True
                    break
            
            if not too_close:
                filtered_candidates.append(candidate)
        
        return np.array(filtered_candidates)
    
    def _calculate_acquisition(self, candidates):
        """计算动态LCB采集函数值"""
        if len(candidates) == 0:
            return np.array([])
        
        if len(self.X_history) < 3:
            return np.random.random(len(candidates))
        
        try:
            # 动态调整gamma值
            progress = min(1.0, len(self.X_history) / self.total_evaluations)
            self.gamma = self.initial_gamma - (self.initial_gamma - self.final_gamma) * progress
            
            # 提取候选点的连续维度
            candidates_continuous = candidates[:, self.continuous_indices]
            
            # 使用当前的标准化器进行转换
            candidates_scaled = self.X_scaler.transform(candidates_continuous)
            
            # 预测
            mu_scaled, sigma = self.gp.predict(candidates_scaled, return_std=True)
            
            # 确保sigma为正
            sigma = np.maximum(sigma, 1e-4)
            
            # LCB采集函数（在标准化空间计算）
            acquisition = -mu_scaled + self.gamma * sigma
            
            if len(self.X_history) % 10 == 0:
                print(f"    动态γ: {self.gamma:.3f}")
                print(f"    采集值范围: [{acquisition.min():.3f}, {acquisition.max():.3f}]")
            
            return acquisition
            
        except Exception as e:
            print(f"  ⚠️ 采集函数计算异常: {e}")
            return np.random.random(len(candidates))
    
    def fit_gp_model(self):
        """拟合高斯过程模型 - 每次都基于当前所有数据重新标准化"""
        if len(self.X_history) < 3:
            print("  GP模型: 样本不足 (<3)，跳过拟合")
            return False
        
        try:
            # 获取当前所有历史数据
            X_all = self.X_history
            y_all = np.array(self.y_history).reshape(-1, 1)
            
            # 提取连续参数维度
            X_continuous = X_all[:, self.continuous_indices]
            
            # 重新拟合标准化器（基于当前所有数据）
            X_scaled = self.X_scaler.fit_transform(X_continuous)
            y_scaled = self.y_scaler.fit_transform(y_all).ravel()
            
            # 拟合GP模型
            self.gp.fit(X_scaled, y_scaled)
            
            # 获取并显示优化后的核参数
            kernel_params = self.gp.kernel_.get_params()
            noise = kernel_params.get('k2__noise_level', 'N/A')
            length = kernel_params.get('k1__k2__length_scale', 'N/A')
            
            # 计算统计数据
            fom_min, fom_max = y_all.min(), y_all.max()
            fom_range = fom_max - fom_min
            
            print(f"  ✅ GP模型拟合成功")
            print(f"    样本数: {len(self.X_history)}")
            print(f"    FOM范围: [{fom_min:.6f}, {fom_max:.6f}], 跨度={fom_range:.6f}")
            print(f"    噪声水平: {noise:.6f} (标准化空间)")
            print(f"    长度尺度: {length}")
            
            return True
        
        except Exception as e:
            print(f"  ❌ GP拟合异常: {e}")
            return False

    def _fallback_gp_fit(self, X_continuous):
        """备用GP拟合方法"""
        try:
            fallback_kernel = RBF(length_scale=1.0) + WhiteKernel(noise_level=1e-3)
            fallback_gp = GaussianProcessRegressor(
                kernel=fallback_kernel,
                n_restarts_optimizer=5,
                normalize_y=True,
                random_state=42,
                alpha=1e-5
            )
            fallback_gp.fit(X_continuous, self.y_history)
            self.gp = fallback_gp
            print("🔄 使用备用GP模型")
        except Exception as e:
            print(f"❌ 备用GP也失败: {e}")
    
    def update_history(self, x, y, iteration, point_type):
        """更新历史记录"""
        self.X_history = np.vstack([self.X_history, x]) if len(self.X_history) > 0 else x.reshape(1, -1)
        self.y_history.append(y)
        
        improvement = False
        if y < self.best_y:
            self.best_y = y
            self.best_x = x.copy()
            improvement = True
        
        record = {
            'iteration': iteration,
            'FOM': y,
            'best_FOM': self.best_y,
            'type': point_type,
            'improvement': improvement,
            'run_id': self.run_id,
            'gamma': self.gamma
        }
        
        for i, name in enumerate(self.param_names):
            record[name] = x[i]
        
        self.iteration_data.append(record)
        return improvement
    
    def optimize(self, objective_function, callback=None, verbose=True):
        """
        执行贝叶斯优化
        """
        print(f"\n🚀 开始贝叶斯优化 (运行{self.run_id})")
        print(f"早停机制: 连续{self.early_stopping_patience}次无改进则停止, 阈值={self.early_stopping_threshold}")
        
        # 保存算法配置（如果目录已设置）
        if self.run_dir:
            self.save_algorithm_config()
        
        total_start_time = time.time()
        
        # 阶段1: 初始探索
        print(f"\n🔍 阶段1: 初始探索 ({self.n_init}个点)")
        initial_points = self.generate_initial_points()
        
        initial_foms = []
        for i, point in enumerate(initial_points):
            y = self.evaluate_point(point, objective_function)
            initial_foms.append(y)
            improvement = self.update_history(point, y, i+1, 'initial')
            status = " 🎯新最佳!" if improvement else ""
            
            if callback:
                callback(point, y, i+1)
                
            print(f"  初始点{i+1}: FOM={y:.6f}, 最佳={self.best_y:.6f}{status}")
        
        # 分析初始点质量
        initial_best = min(initial_foms)
        initial_avg = np.mean(initial_foms)
        print(f"📊 初始点质量: 最佳={initial_best:.6f}, 平均={initial_avg:.6f}")
        
        if len(self.X_history) >= 2:
            X_continuous = self.X_history[:, self.continuous_indices]
            self.X_scaler.fit(X_continuous)
            self.y_scaler.fit(np.array(self.y_history).reshape(-1, 1))
            print("✅ 数据标准化已完成")
        
        # 阶段2: 贝叶斯优化
        print(f"\n🔍 阶段2: 贝叶斯优化 ({self.n_iter}次迭代)")
        optimization_start_time = time.time()
        
        # 重置早停计数器
        self.no_improvement_count = 0
        self.best_y_so_far = self.best_y
        
        for i in range(self.n_iter):
            iter_num = i + 1 + self.n_init
            
            print(f"\n--- 第 {iter_num} 次迭代 (贝叶斯{i+1}/{self.n_iter}) ---")
            print(f"   当前最佳: FOM={self.best_y:.6f}")
            print(f"   连续无改进次数: {self.no_improvement_count}/{self.early_stopping_patience}")
            
            # 检查早停条件
            if self.no_improvement_count >= self.early_stopping_patience:
                print(f"⏹️  连续{self.early_stopping_patience}次无改进，提前停止优化")
                break
            
            self.fit_gp_model()
            x_next = self.get_next_point()
            y_next = self.evaluate_point(x_next, objective_function)
            improvement = self.update_history(x_next, y_next, iter_num, 'bayesian')
            
            # 更新早停计数器
            improvement_value = self.best_y_so_far - self.best_y #阈值判断

            if improvement and improvement_value > self.early_stopping_threshold:
                self.no_improvement_count = 0
                self.best_y_so_far = self.best_y
            else:
                self.no_improvement_count += 1
            
            if callback:
                callback(x_next, y_next, iter_num)
                
            status = " 🎯新最佳!" if improvement else ""
            print(f"迭代{iter_num:3d}: FOM={y_next:.6f}, 最佳={self.best_y:.6f}{status}")
        
        optimization_time = time.time() - optimization_start_time
        total_time = time.time() - total_start_time
        
        # 显示优化总结
        actual_iterations = len(self.iteration_data) - self.n_init
        print(f"\n✅ 贝叶斯优化完成!")
        print(f"📊 总迭代: {len(self.iteration_data)} 次 (初始{self.n_init} + 贝叶斯{actual_iterations})")
        print(f"⏱️  总时间: {total_time/60:.1f}分钟")
        
        improvement_pct = ((initial_best - self.best_y) / initial_best) * 100
        print(f"📈 优化效果: {initial_best:.6f} → {self.best_y:.6f} (改进: {improvement_pct:+.1f}%)")
        
        if self.no_improvement_count >= self.early_stopping_patience:
            print(f"🛑 优化因连续{self.early_stopping_patience}次无改进而提前停止")
        else:
            print(f"🏁 优化完成所有预定迭代")
        
        return {
            'best_parameters': self.best_x,
            'best_fom': self.best_y,
            'initial_best_fom': initial_best,
            'initial_avg_fom': initial_avg,
            'convergence_history': self.iteration_data.copy(),
            'total_time': total_time,
            'early_stopped': self.no_improvement_count >= self.early_stopping_patience,
            'no_improvement_count': self.no_improvement_count
        }
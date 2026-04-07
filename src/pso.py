import numpy as np
import time
import os
from datetime import datetime

class Particle:
    def __init__(self, bounds, dimensions, integer_params=None, param_names=None, initial_position=None):
        self.dimensions = dimensions
        self.integer_params = integer_params or []
        self.param_names = param_names or [f"param_{i}" for i in range(dimensions)]
        self.bounds = bounds
        
        # 初始化粒子位置
        if initial_position is not None:
            self.position = np.array(initial_position, dtype=float)
            self.position = self._clip_to_bounds(self.position)
        else:
            self.position = self._generate_random_position()
        
        # 处理整数参数
        self.position = self._process_parameters(self.position)
        
        # 初始化粒子速度
        self.velocity = self._generate_initial_velocity()
        
        # 当前粒子的最佳位置
        self.best_position = np.copy(self.position)
        # 当前粒子的最佳适应度值
        self.best_fom = float('inf')
        # 停滞计数器
        self.stagnation_count = 0
    
    def _generate_random_position(self):
        """生成随机位置"""
        position = np.zeros(self.dimensions)
        for i in range(self.dimensions):
            low, high = self.bounds[i]
            position[i] = np.random.uniform(low, high)
        return position
    
    def _generate_initial_velocity(self):
        """生成初始速度"""
        velocity = np.zeros(self.dimensions)
        for i in range(self.dimensions):
            low, high = self.bounds[i]
            velocity_range = 0.2 * abs(high - low)
            velocity[i] = np.random.uniform(-velocity_range, velocity_range)
        return velocity
    
    def _clip_to_bounds(self, position):
        """将位置裁剪到边界内"""
        clipped = np.copy(position)
        for i in range(self.dimensions):
            low, high = self.bounds[i]
            clipped[i] = np.clip(position[i], low, high)
        return clipped
    
    def _process_parameters(self, x):
        """处理参数 - 整数参数四舍五入"""
        processed = np.copy(x)
        for i in self.integer_params:
            processed[i] = int(round(x[i]))
        return processed
    
    def _format_parameters(self, x):
        """格式化参数显示"""
        parts = []
        for i, name in enumerate(self.param_names):
            if i in self.integer_params:
                parts.append(f"{name}={int(x[i])}")
            else:
                parts.append(f"{name}={x[i]:.6f}")
        return ", ".join(parts)
    
    def update_velocity(self, global_best_position, w=0.7, c1=1.5, c2=1.5, iteration=0, max_iter=100):
        """更新粒子速度"""
        # 动态惯性权重
        w = w * (0.9 - 0.5) * (max_iter - iteration) / max_iter + 0.5
        
        # 动态学习因子
        c1_dynamic = c1 * (1.0 - 0.5 * iteration / max_iter)
        c2_dynamic = c2 * (1.0 + iteration / max_iter)
        
        # 随机系数
        r1 = np.random.random(len(self.position))
        r2 = np.random.random(len(self.position))
        
        # 更新速度公式
        cognitive_component = c1_dynamic * r1 * (self.best_position - self.position)
        social_component = c2_dynamic * r2 * (global_best_position - self.position)
        
        # 基础速度更新
        self.velocity = w * self.velocity + cognitive_component + social_component
        
        # 添加速度限制
        avg_range = np.mean([abs(high - low) for low, high in self.bounds])
        max_velocity = avg_range * (1.5 - (1.5 - 0.7) * (iteration / max_iter))
        velocity_magnitude = np.linalg.norm(self.velocity)
        if velocity_magnitude > max_velocity:
            self.velocity = self.velocity * (max_velocity / velocity_magnitude)
        
        # 如果粒子停滞，增加随机扰动
        if self.stagnation_count > 3:
            perturbation = np.random.normal(0, 0.1 * avg_range, len(self.position))
            self.velocity += perturbation
            self.stagnation_count = 0
    
    def update_position(self):
        """更新粒子位置"""
        old_position = np.copy(self.position)
        self.position = self.position + self.velocity
        
        # 边界处理
        self.position = self._clip_to_bounds(self.position)
        
        # 处理整数参数
        self.position = self._process_parameters(self.position)
        
        # 检查位置是否改变
        if np.allclose(old_position, self.position, rtol=1e-5, atol=1e-5):
            self.stagnation_count += 1
        else:
            self.stagnation_count = 0

class PSO:
    def __init__(self, bounds, param_names=None,
                 integer_params=None, 
                 run_id = 1,
                 num_particles = 30, 
                 max_iter = 100, 
                 w = 0.7, 
                 c1 = 1.5, 
                 c2 = 1.5, 
                 stagnation_threshold = 20,
                 early_stop_patience = 20,  # 新增：早停耐心值
                 early_stop_threshold = 1e-5,  # 新增：早停阈值
                 initial_positions = None
                 ):
        """
        初始化PSO算法（新增早停机制）
        """
        self.bounds = np.array(bounds)
        self.dimensions = len(bounds)        
        self.integer_params = integer_params or []
        self.param_names = param_names or [f"param_{i}" for i in range(self.dimensions)]
        self.run_id = run_id
        self.num_particles = num_particles
        self.max_iter = max_iter
        self.w = w
        self.c1 = c1
        self.c2 = c2
        self.stagnation_threshold = stagnation_threshold
        self.early_stop_patience = early_stop_patience  # 新增
        self.early_stop_threshold = early_stop_threshold  # 新增
        
        # 创建运行目录
        self.run_dir = None
        
        # 初始化粒子群
        self.particles = []
        if initial_positions is not None:
            num_initial = min(len(initial_positions), num_particles)
            for i in range(num_initial):
                particle = Particle(bounds, self.dimensions, integer_params, param_names, initial_positions[i])
                self.particles.append(particle)
            
            for _ in range(num_particles - num_initial):
                particle = Particle(bounds, self.dimensions, integer_params, param_names, None)
                self.particles.append(particle)
        else:
            self.particles = [Particle(self.bounds, self.dimensions, self.integer_params, self.param_names) 
                            for _ in range(self.num_particles)]
        
        # 全局最佳位置和适应度
        self.global_best_position = None
        self.global_best_fom = float('inf')
        
        # 存储优化历史
        self.fom_history = []
        self.iteration_data = []
        
        # 停滞检测参数
        self.stagnation_counter = 0
        self.fom_threshold = 1e-6
        
        # 新增：早停相关参数
        self.no_improvement_count = 0  # 连续无改进次数
        self.best_fom_so_far = float('inf')  # 迄今最佳FOM
        
        # 真正的全局最优解
        self.true_global_best_position = None
        self.true_global_best_fom = float('inf')
        
        print(f"🎯 初始化PSO优化器 (运行{self.run_id})")
        print(f"   参数数量: {self.dimensions} (其中{len(integer_params)}个整数参数)")
        print(f"   粒子数量: {num_particles}")
        print(f"   最大迭代次数: {max_iter}")
        print(f"   重启机制: 连续{stagnation_threshold}次无改进则重启")
        print(f"   早停机制: 连续{early_stop_patience}次无改进则停止")  # 新增
        
        # 显示边界信息
        print(f"   参数边界:")
        for i, name in enumerate(self.param_names):
            low, high = self.bounds[i]
            param_type = "整数" if i in self.integer_params else "连续"
            print(f"     {name}: [{low:.6f}, {high:.6f}] ({param_type})")

        # 保存配置信息用于后续输出
        self.algorithm_config = {
            'num_particles': num_particles,
            'max_iter': max_iter,
            'w': w,
            'c1': c1,
            'c2': c2,
            'stagnation_threshold': stagnation_threshold,
            'early_stop_patience': early_stop_patience,  # 新增
            'early_stop_threshold': early_stop_threshold,  # 新增
            'global_initial_temp': 0.06,
            'local_initial_temp': 0.025,
            'fom_threshold': 1e-6
        }

    def _process_parameters(self, x):
        """处理参数 - 整数参数四舍五入"""
        processed = np.copy(x)
        for i in self.integer_params:
            processed[i] = int(round(x[i]))
        return processed
    
    def _format_parameters(self, x):
        """格式化参数显示"""
        parts = []
        for i, name in enumerate(self.param_names):
            if i in self.integer_params:
                parts.append(f"{name}={int(x[i])}")
            else:
                parts.append(f"{name}={x[i]:.6f}")
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

    def set_initial_positions(self, initial_positions):
        """设置粒子的初始位置"""
        num_initial = min(len(initial_positions), self.num_particles)
        for i in range(num_initial):
            self.particles[i].position = np.array(initial_positions[i], dtype=float)
            self.particles[i].position = self.particles[i]._clip_to_bounds(self.particles[i].position)
            self.particles[i].position = self._process_parameters(self.particles[i].position)
            self.particles[i].best_position = np.copy(self.particles[i].position)
            self.particles[i].best_fom = float('inf')

    def calculate_diversity(self):
        """计算种群多样性"""
        positions = np.array([p.position for p in self.particles])
        return np.mean(np.std(positions, axis=0))
        
    def initialize_particles(self):
        """初始化或重新初始化粒子群"""
        self.particles = [Particle(self.bounds, self.dimensions, self.integer_params, self.param_names) 
                         for _ in range(self.num_particles)]
    
    def update_history(self, iteration, best_fom, improvement, diversity, early_stop_status=False):
        """更新历史记录（新增早停状态）"""
        record = {
            'iteration': iteration,
            'best_fom': best_fom,
            'true_best_fom': self.true_global_best_fom,
            'improvement': improvement,
            'diversity': diversity,
            'stagnation_count': self.stagnation_counter,
            'no_improvement_count': self.no_improvement_count,  # 新增
            'early_stop_triggered': early_stop_status,  # 新增
            'run_id': self.run_id
        }
        
        self.iteration_data.append(record)
        return improvement

    def optimize(self, objective_function, callback=None, verbose=True):
        """
        执行PSO优化（集成早停机制）
        
        返回:
        - 优化结果字典
        """
        print(f"\n🚀 开始PSO优化 (运行{self.run_id})")
        print(f"参数数量: {self.dimensions}个")
        print(f"优化策略: {self.num_particles}个粒子, {self.max_iter}次迭代")
        print(f"重启机制: 连续{self.stagnation_threshold}次无改进则重启")
        print(f"早停机制: 连续{self.early_stop_patience}次无改进则停止")  # 新增

        # 保存算法配置（如果目录已设置）
        if self.run_dir:
            self.save_algorithm_config()
        
        total_start_time = time.time()
        
        # 初始化温度参数
        global_initial_temp = 0.06
        local_initial_temp = 0.025
        
        # 初始化全局最佳位置
        initial_foms = []
        for particle in self.particles:
            fom = self.evaluate_point(particle.position, objective_function)
            initial_foms.append(fom)
            
            # 更新粒子的个体最佳
            particle.best_fom = fom
            particle.best_position = np.copy(particle.position)
            
            # 更新全局最佳
            if fom < self.global_best_fom:
                self.global_best_fom = fom
                self.global_best_position = np.copy(particle.position)
        
        # 初始化真正的全局最优解
        self.true_global_best_position = np.copy(self.global_best_position)
        self.true_global_best_fom = self.global_best_fom
        
        # 初始化早停相关变量
        self.best_fom_so_far = self.true_global_best_fom
        self.no_improvement_count = 0
        
        initial_best = min(initial_foms)
        initial_avg = np.mean(initial_foms)
        
        print(f"📊 初始FOM: 最佳={initial_best:.6f}, 平均={initial_avg:.6f}")
        print(f"📊 早停基准FOM: {self.best_fom_so_far:.6f}")
        
        prev_best_fom = self.global_best_fom
        
        # 记录初始状态
        diversity = self.calculate_diversity()
        self.update_history(0, self.global_best_fom, True, diversity)
        
        # 迭代优化
        optimization_start_time = time.time()
        early_stop_triggered = False  # 早停标志
        actual_iterations = 0  # 实际执行迭代次数
        
        for i in range(self.max_iter):
            iter_num = i + 1
            actual_iterations = iter_num
            
            print(f"\n--- 第 {iter_num} 次迭代 (PSO {iter_num}/{self.max_iter}) ---")
            print(f"   当前最佳: FOM={self.global_best_fom:.6f}")
            print(f"   真正最佳: FOM={self.true_global_best_fom:.6f}")
            print(f"   连续无改进次数(重启): {self.stagnation_counter}/{self.stagnation_threshold}")
            print(f"   连续无改进次数(早停): {self.no_improvement_count}/{self.early_stop_patience}")  # 新增
            
            # 计算当前温度
            global_temp = global_initial_temp * (1 - i / self.max_iter)
            local_temp = local_initial_temp * (1 - i / self.max_iter)
            
            # 计算当前种群多样性
            diversity = self.calculate_diversity()
            
            # 如果多样性太低，对部分粒子进行重新初始化
            if diversity < 0.08 and i < self.max_iter * 0.8:
                print(f"🔄 迭代 {iter_num}: 种群多样性过低 ({diversity:.6f})，重新初始化部分粒子")
                num_reinit = self.num_particles // 4
                for j in range(num_reinit):
                    self.particles[j] = Particle(self.bounds, self.dimensions, self.integer_params, self.param_names)
            
            improvement = False
            for particle in self.particles:
                # 更新粒子速度和位置
                particle.update_velocity(self.global_best_position, self.w, self.c1, self.c2, i, self.max_iter)
                particle.update_position()
                
                # 计算新位置的FOM
                fom = self.evaluate_point(particle.position, objective_function)
                
                # 更新粒子的个体最佳
                if fom < particle.best_fom:
                    particle.best_fom = fom
                    particle.best_position = np.copy(particle.position)
                else:
                    delta = fom - particle.best_fom
                    acceptance_probability = np.exp(-delta / local_temp)
                    
                    if np.random.random() < acceptance_probability:
                        particle.best_fom = fom
                        particle.best_position = np.copy(particle.position)
                
                # 更新全局最佳
                if fom < self.global_best_fom:
                    self.global_best_fom = fom
                    self.global_best_position = np.copy(particle.position)
                    self.stagnation_counter = 0
                    improvement = True
                else:
                    delta = fom - self.global_best_fom
                    acceptance_probability = np.exp(-delta / global_temp)
                    
                    if np.random.random() < acceptance_probability:
                        print(f"🔄 迭代 {iter_num}: 接受全局次优解，FOM: {fom:.6f}，接受概率: {acceptance_probability:.4f}")
                        self.global_best_fom = fom
                        self.global_best_position = np.copy(particle.position)
                        self.stagnation_counter = 0
                        improvement = True
                
                # 更新真正的全局最优解
                if fom < self.true_global_best_fom:
                    self.true_global_best_fom = fom
                    self.true_global_best_position = np.copy(particle.position)
                    print(f"🎯 迭代 {iter_num}: 发现新的全局最优解，FOM: {fom:.6f}")
                    improvement = True
            
            # 早停机制检查（参考pso_improved.py的改进）
            current_improvement = self.best_fom_so_far - self.true_global_best_fom
            
            if current_improvement > self.early_stop_threshold:
                # 有显著改善
                self.no_improvement_count = 0
                self.best_fom_so_far = self.true_global_best_fom
                print(f"✅ 早停检测: 本次迭代改善 {current_improvement:.6f}，重置早停计数器")
            else:
                # 无显著改善
                self.no_improvement_count += 1
                print(f"⚠️  早停检测: 无显著改善 (连续 {self.no_improvement_count} 次)")
            
            # 检查是否达到早停条件
            if self.no_improvement_count >= self.early_stop_patience:
                print(f"🛑 迭代 {iter_num}: 触发早停机制，连续 {self.no_improvement_count} 次迭代无改善")
                early_stop_triggered = True
                break
            
            # 记录当前迭代
            self.update_history(iter_num, self.global_best_fom, improvement, diversity)
            
            # 检查是否停滞（重启机制）
            if abs(self.global_best_fom - prev_best_fom) < self.fom_threshold:
                self.stagnation_counter += 1
            else:
                self.stagnation_counter = 0
            
            # 如果停滞太久，进行重启（但仅在未触发早停时）
            if self.stagnation_counter >= self.stagnation_threshold and not early_stop_triggered:
                print(f"🔄 迭代 {iter_num}: 优化停滞 ({self.stagnation_counter} 次)，尝试重启")
                # 保存当前最佳结果
                best_position = np.copy(self.global_best_position)
                best_fom = self.global_best_fom
                
                # 重新初始化部分粒子
                self.initialize_particles()
                
                # 保留一个粒子在最佳位置附近
                self.particles[0].position = best_position + np.random.normal(0, 0.1, self.dimensions)
                self.particles[0].position = self.particles[0]._clip_to_bounds(self.particles[0].position)
                self.particles[0].best_position = np.copy(best_position)
                self.particles[0].best_fom = best_fom
                
                self.stagnation_counter = 0
            
            prev_best_fom = self.global_best_fom
            
            # 调用回调函数
            if callback:
                callback(self.global_best_position, self.global_best_fom, iter_num)
            
            status = " 🎯新最佳!" if improvement else ""
            print(f"迭代{iter_num:3d}: FOM={self.global_best_fom:.6f}, 真正最佳={self.true_global_best_fom:.6f}{status}")
        
        # 如果触发了早停，记录最后一次迭代
        if early_stop_triggered:
            self.update_history(actual_iterations, self.global_best_fom, False, diversity, early_stop_status=True)
        
        optimization_time = time.time() - optimization_start_time
        total_time = time.time() - total_start_time
        
        # 显示优化总结
        print(f"\n{'='*60}")
        print(f"✅ PSO优化完成!")
        print(f"{'='*60}")
        print(f"📊 总迭代: {actual_iterations} 次 (最大设定: {self.max_iter})")
        print(f"⏱️  优化时间: {optimization_time/60:.1f}分钟")
        print(f"⏱️  总时间: {total_time/60:.1f}分钟")
        
        improvement_pct = ((initial_best - self.true_global_best_fom) / initial_best) * 100
        print(f"📈 优化效果: {initial_best:.6f} → {self.true_global_best_fom:.6f} (改进: {improvement_pct:+.1f}%)")
        
        # 显示终止原因
        if early_stop_triggered:
            print(f"🛑 终止原因: 早停机制触发 (连续 {self.no_improvement_count} 次无改进)")
            print(f"💡 节省迭代: {self.max_iter - actual_iterations} 次")
        elif self.stagnation_counter >= self.stagnation_threshold:
            print(f"🛑 终止原因: 重启机制触发 (连续 {self.stagnation_counter} 次停滞)")
        else:
            print(f"🏁 终止原因: 完成所有预定迭代")
        
        print(f"{'='*60}")
        
        return {
            'best_parameters': self.true_global_best_position,
            'best_fom': self.true_global_best_fom,
            'final_fom': self.global_best_fom,
            'initial_best_fom': initial_best,
            'convergence_history': self.iteration_data.copy(),
            'total_time': total_time,
            'optimization_time': optimization_time,
            'actual_iterations': actual_iterations,  # 新增
            'early_stop_triggered': early_stop_triggered,  # 新增
            'restart_triggered': self.stagnation_counter >= self.stagnation_threshold,
            'stagnation_count': self.stagnation_counter,
            'no_improvement_count': self.no_improvement_count  # 新增
        }
    
    def save_algorithm_config(self):
        """保存PSO算法配置到文件（更新为包含早停机制）"""
        config_file = os.path.join(self.run_dir, 'pso_algorithm_config.txt')
        
        with open(config_file, 'w', encoding='utf-8') as f:
            f.write("PSO算法配置详情 (含早停机制)\n")
            f.write("=" * 60 + "\n\n")
            
            f.write("【核心算法参数配置】\n")
            f.write("-" * 40 + "\n")
            f.write(f"粒子数量: {self.algorithm_config['num_particles']}\n")
            f.write(f"最大迭代次数: {self.algorithm_config['max_iter']}\n")
            f.write(f"惯性权重 (w): {self.algorithm_config['w']}\n")
            f.write(f"认知参数 (c1): {self.algorithm_config['c1']}\n")
            f.write(f"社会参数 (c2): {self.algorithm_config['c2']}\n")
            
            f.write(f"\n【重启机制配置】\n")
            f.write("-" * 40 + "\n")
            f.write(f"停滞阈值: {self.algorithm_config['stagnation_threshold']}\n")
            f.write(f"FOM改进阈值: {self.algorithm_config['fom_threshold']}\n")
            
            f.write(f"\n【早停机制配置】\n")
            f.write("-" * 40 + "\n")
            f.write(f"早停耐心值: {self.algorithm_config['early_stop_patience']}\n")
            f.write(f"早停阈值: {self.algorithm_config['early_stop_threshold']}\n")
            f.write(f"注: 连续无改进次数 ≥ 早停耐心值 时触发早停\n")
            
            f.write(f"\n【模拟退火参数】\n")
            f.write("-" * 40 + "\n")
            f.write(f"全局初始温度: {self.algorithm_config['global_initial_temp']}\n")
            f.write(f"局部初始温度: {self.algorithm_config['local_initial_temp']}\n")
            
            f.write(f"\n【问题配置】\n")
            f.write("-" * 40 + "\n")
            f.write(f"参数维度: {self.dimensions}\n")
            f.write(f"整数参数个数: {len(self.integer_params)}\n")
            if len(self.integer_params) > 0:
                f.write(f"整数参数索引: {self.integer_params}\n")
            
            f.write(f"\n【参数边界】\n")
            f.write("-" * 40 + "\n")
            for i, name in enumerate(self.param_names):
                low, high = self.bounds[i]
                param_type = "整数" if i in self.integer_params else "连续"
                f.write(f"{name:15s}: [{low:.6f}, {high:.6f}] ({param_type})\n")
            
            f.write(f"\n【配置信息】\n")
            f.write("-" * 40 + "\n")
            f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"运行ID: {self.run_id}\n")
            f.write(f"运行目录: {self.run_dir}\n")
            
            f.write(f"\n【算法特点】\n")
            f.write("-" * 40 + "\n")
            f.write("1. 标准PSO + 模拟退火接受次优解\n")
            f.write("2. 动态惯性权重和认知/社会参数\n")
            f.write("3. 种群多样性监测与部分重启\n")
            f.write("4. 双重终止机制: 重启 + 早停\n")
            f.write("5. 电压组优化友好（支持整数/连续混合参数）\n")
        
        print(f"✅ PSO算法配置已保存: {config_file}")
        print(f"   包含早停机制配置: patience={self.early_stop_patience}, threshold={self.early_stop_threshold}")

    def set_run_directory(self, run_dir):
        """由适配器设置运行目录"""
        self.run_dir = run_dir
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pulp
import itertools
import random
import time
import warnings
warnings.filterwarnings('ignore')

# ================== 0. 全局设置 ===================
plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False

# ================== 1. 数据加载 ===================
try:
    df = pd.read_excel('附件1.xlsx', sheet_name=0, header=None)
    print("成功读取附件1.xlsx")
    # 假设格式：第一行为标题，从第二行开始是小时需求
    # 简单处理：读取后转为数组
    # 这里需要根据附件具体格式解析，现假定表格结构：
    # 列0: 时段标签，列1-100: 第1天组1, 第1天组2,...,第10天组10
    # 读取数值，忽略第一列
    data = df.iloc[1:, 1:].values.astype(int)  # 11行 × 100列
    demand_3d = np.zeros((10, 10, 11), dtype=int)
    for col in range(100):
        day = col // 10
        grp = col % 10
        demand_3d[day, grp, :] = data[:, col]
    print("数据加载并整理为 (天, 小组, 小时) 三维数组。")
except Exception as e:
    print(f"未能读取附件1.xlsx ({e})，使用模拟需求数据（正态分布取整，峰值适当调整）。")
    np.random.seed(42)
    # 生成合理需求：基础需求5~15，高峰时段提升
    base = np.random.poisson(lam=8, size=(10, 10, 11))
    # 给某些天/组/小时增加高峰
    for d in range(10):
        for g in range(10):
            for h in range(11):
                if 9 <= h <= 11 or 14 <= h <= 16:  # 模拟高峰
                    base[d,g,h] += np.random.poisson(lam=5)
    demand_3d = base

# 全局需求形状
T_days = 10
G_groups = 10
H_hours = 11

# 时段索引对应的实际时间
hour_labels = [f'{8+i}:00-{9+i}:00' for i in range(11)]

# ================== 2. 列生成器 ==================
def generate_shift_8h():
    """生成一个8小时连续班次的开始小时索引列表 (0~3)"""
    return list(range(4))

def generate_single_day_schedule_q1(group, shift_start):
    """问题1的单日安排：固定小组，给定8小时班开始时间，返回(day, group, hour)工作矩阵 (11,)"""
    work = np.zeros(H_hours, dtype=int)
    start = shift_start
    for h in range(start, start+8):
        work[h] = 1
    return work

def generate_single_day_schedule_q2(group, shift_start):
    """问题2的单日安排：同q1"""
    return generate_single_day_schedule_q1(group, shift_start)

def generate_single_day_schedule_q3(mode, g1, t1, g2=None, t2=None):
    """
    问题3单日安排：
    mode='A': 单组8小时连续，参数g1,t1
    mode='B': 双组各4小时，参数g1,t1,g2,t2
    返回: (group, hour) 工作矩阵 (10,11)
    """
    work = np.zeros((G_groups, H_hours), dtype=int)
    if mode == 'A':
        for h in range(t1, t1+8):
            work[g1, h] = 1
    else:  # mode B
        for h in range(t1, t1+4):
            work[g1, h] = 1
        for h in range(t2, t2+4):
            work[g2, h] = 1
    return work

def get_valid_combinations_q3():
    """返回问题3模式B的所有可行(g1,t1,g2,t2)组合列表，t1,t2满足间隔≥2h且不超出19点"""
    combos = []
    for g1 in range(G_groups):
        for t1 in range(0, 8):  # 4小时段开始时间0~7
            if t1+4 > 11: continue
            for g2 in range(G_groups):
                if g2 == g1: continue
                for t2 in range(t1+6, 11):  # 至少间隔2h: t2 - (t1+4) >=2 -> t2 >= t1+6
                    if t2+4 <= 11:
                        combos.append((g1, t1, g2, t2))
    return combos

valid_q3_combos = get_valid_combinations_q3()  # 约数千种，供随机选择

def generate_columns_for_problem(problem_id, num_columns=2000):
    """
    根据问题编号生成指定数量的排班列。
    每列格式: [
        (休息日列表, 
         [对于每一天的排班信息：q1/q2: (组, 开始时间) 或 q3: ('A', g1, t1) / ('B', g1, t1, g2, t2))
        ]
    ]
    实际返回覆盖矩阵 columns_coverage: list of np.array (10,10,11)
    """
    columns = []
    rest_combinations = list(itertools.combinations(range(T_days), 2))  # 45种
    for i in range(num_columns):
        rest = random.choice(rest_combinations)
        day_info = []
        for d in range(T_days):
            if d in rest:
                day_info.append(None)  # 休息
                continue
            if problem_id == 1:
                # 固定小组，随机选一个组，然后选一个8小时班
                grp = random.randint(0, G_groups-1)
                shift = random.choice(generate_shift_8h())
                day_info.append(('Q1', grp, shift))
            elif problem_id == 2:
                # 每天可以选不同组
                grp = random.randint(0, G_groups-1)
                shift = random.choice(generate_shift_8h())
                day_info.append(('Q2', grp, shift))
            elif problem_id == 3:
                if random.random() < 0.5:  # 模式A
                    grp = random.randint(0, G_groups-1)
                    shift = random.choice(generate_shift_8h())
                    day_info.append(('Q3A', grp, shift))
                else:  # 模式B
                    combo = random.choice(valid_q3_combos)
                    g1, t1, g2, t2 = combo
                    day_info.append(('Q3B', g1, t1, g2, t2))
        # 构建覆盖矩阵
        cover = np.zeros((T_days, G_groups, H_hours), dtype=int)
        for d in range(T_days):
            if day_info[d] is None:
                continue
            info = day_info[d]
            if info[0] in ('Q1', 'Q2', 'Q3A'):
                _, grp, shift = info
                for h in range(shift, shift+8):
                    cover[d, grp, h] = 1
            else:  # Q3B
                _, g1, t1, g2, t2 = info
                for h in range(t1, t1+4):
                    cover[d, g1, h] = 1
                for h in range(t2, t2+4):
                    cover[d, g2, h] = 1
        columns.append(cover)
    return columns

# ================== 3. ILP求解 ==================
def solve_set_covering(columns, demand, time_limit=20):
    """
    求解集合覆盖ILP，返回 (选中的列索引列表, 最小人数, 求解状态)
    """
    n = len(columns)
    prob = pulp.LpProblem("SetCover", pulp.LpMinimize)
    x = [pulp.LpVariable(f"x_{i}", cat='Binary') for i in range(n)]
    # 目标
    prob += pulp.lpSum(x)
    # 约束
    for d in range(T_days):
        for g in range(G_groups):
            for h in range(H_hours):
                # 系数向量
                coeffs = [columns[i][d,g,h] for i in range(n)]
                if max(coeffs) == 0:
                    # 如果没有列能覆盖这个需求点且需求>0，则无解，返回None
                    if demand[d,g,h] > 0:
                        return None, None, "无可行列覆盖某些需求点"
                    else:
                        continue
                prob += pulp.lpSum([coeffs[i] * x[i] for i in range(n)]) >= demand[d,g,h]
    # 求解
    solver = pulp.PULP_CBC_CMD(msg=False, timeLimit=time_limit)
    prob.solve(solver)
    status = pulp.LpStatus[prob.status]
    if status not in ('Optimal', 'Feasible', 'Not Solved'):
        return None, None, status
    selected = [i for i in range(n) if pulp.value(x[i]) > 0.5]
    obj = int(pulp.value(prob.objective))
    return selected, obj, status

# ================== 4. 验证函数 ==================
def verify_solution(columns_selected, selected_indices, demand):
    """验证覆盖情况并返回最大缺口和溢出的统计"""
    total_cover = np.zeros_like(demand)
    for idx in selected_indices:
        total_cover += columns_selected[idx]
    gap = demand - total_cover
    max_shortfall = np.max(gap)
    total_overflow = np.sum(np.maximum(total_cover - demand, 0))
    return max_shortfall, total_overflow, total_cover

# ================== 5. 主流程 ==================
def run_problem(prob_id, prob_name, num_base_columns=2000, num_extra_steps=2, extra_cols=500, time_limit=20):
    """
    逐步增加列并求解，记录目标值变化用于收敛图。
    返回 (final_selected, final_obj, history_list_of_tuple(num_cols, obj))
    """
    history = []
    columns_current = []
    for step in range(num_extra_steps+1):
        new_cols = generate_columns_for_problem(prob_id, num_columns=num_base_columns if step==0 else extra_cols)
        columns_current.extend(new_cols)
        selected, obj, status = solve_set_covering(columns_current, demand_3d, time_limit=time_limit)
        if selected is None:
            print(f"  [{prob_name}] 第{step+1}次求解({len(columns_current)}列): 无可行解，继续增加列...")
            history.append((len(columns_current), None))
        else:
            print(f"  [{prob_name}] 第{step+1}次求解({len(columns_current)}列): 最少人数={obj}, 状态={status}")
            history.append((len(columns_current), obj))
            if status == 'Optimal' or (step == num_extra_steps):
                # 最后一次或者最优则终止
                final_selected = selected
                final_obj = obj
                final_columns = columns_current
                break
    else:
        # 最后一次
        selected, obj, status = solve_set_covering(columns_current, demand_3d, time_limit=time_limit)
        if selected is None:
            raise RuntimeError(f"{prob_name} 无法找到可行解")
        final_selected = selected
        final_obj = obj
        final_columns = columns_current
        history.append((len(columns_current), obj))
    return final_columns, final_selected, final_obj, history

print("开始求解问题1...")
t0 = time.time()
cols1, sel1, obj1, hist1 = run_problem(1, "问题1", num_base_columns=1500, num_extra_steps=2, extra_cols=500, time_limit=20)
print(f"问题1求解完成，最少人数: {obj1}, 耗时: {time.time()-t0:.1f}s")

print("开始求解问题2...")
t0 = time.time()
cols2, sel2, obj2, hist2 = run_problem(2, "问题2", num_base_columns=1500, num_extra_steps=2, extra_cols=500, time_limit=20)
print(f"问题2求解完成，最少人数: {obj2}, 耗时: {time.time()-t0:.1f}s")

print("开始求解问题3...")
t0 = time.time()
cols3, sel3, obj3, hist3 = run_problem(3, "问题3", num_base_columns=1500, num_extra_steps=2, extra_cols=500, time_limit=30)
print(f"问题3求解完成，最少人数: {obj3}, 耗时: {time.time()-t0:.1f}s")

# ================== 6. 结果验证 ==================
short1, over1, cover1 = verify_solution(cols1, sel1, demand_3d)
short2, over2, cover2 = verify_solution(cols2, sel2, demand_3d)
short3, over3, cover3 = verify_solution(cols3, sel3, demand_3d)
print(f"问题1验证 - 最大缺口: {short1}, 总溢出: {over1}")
print(f"问题2验证 - 最大缺口: {short2}, 总溢出: {over2}")
print(f"问题3验证 - 最大缺口: {short3}, 总溢出: {over3}")

# ================== 7. 可视化 ==================
# 图1：需求热力图（以第0天为例）
plt.figure(figsize=(10,6))
sns_heat = demand_3d[0].T  # (小时×小组)
plt.imshow(sns_heat, aspect='auto', cmap='YlOrRd', origin='lower')
plt.colorbar(label='需求人数')
plt.xticks(ticks=np.arange(G_groups), labels=[f'小组{i+1}' for i in range(G_groups)])
plt.yticks(ticks=np.arange(H_hours), labels=hour_labels)
plt.xlabel('小组')
plt.ylabel('时段')
plt.title('第1天各小组每小时需求热力图')
plt.tight_layout()
plt.savefig('图1_需求热力图.png')
plt.close()

# 图2：各小组10天平均需求相关性热力图
avg_demand_g = np.mean(demand_3d, axis=(0,2))  # (10,10) 天×组，计算组间相关性
corr_g = np.corrcoef(demand_3d.reshape(-1, G_groups).T)
plt.figure(figsize=(9,8))
plt.imshow(corr_g, cmap='coolwarm', vmin=-1, vmax=1)
plt.colorbar()
plt.xticks(ticks=np.arange(G_groups), labels=[f'G{i+1}' for i in range(G_groups)], rotation=45)
plt.yticks(ticks=np.arange(G_groups), labels=[f'G{i+1}' for i in range(G_groups)])
plt.title('各小组需求相关性热力图')
plt.tight_layout()
plt.savefig('图2_需求相关性热力图.png')
plt.close()

# 图3：收敛曲线（问题1历史）
plt.figure(figsize=(8,5))
cols_history = [h[0] for h in hist1]
objs_history = [h[1] if h[1] is not None else np.nan for h in hist1]
plt.plot(cols_history, objs_history, 'bo-', linewidth=2)
plt.xlabel('列池大小')
plt.ylabel('最少临时工人数')
plt.title('问题1：列池规模与求解人数收敛图')
plt.grid(True)
plt.tight_layout()
plt.savefig('图3_收敛曲线.png')
plt.close()

# 图4：三个问题最少人数对比
fig, ax = plt.subplots()
names = ['问题1\n固定小组', '问题2\n日变动组', '问题3\n跨组+休息']
values = [obj1, obj2, obj3]
ax.bar(names, values, color=['#1f77b4', '#ff7f0e', '#2ca02c'])
ax.set_ylabel('最少临时工人数')
ax.set_title('三种工作模式所需最少人数对比')
for i, v in enumerate(values):
    ax.text(i, v+0.5, str(v), ha='center', fontweight='bold')
plt.tight_layout()
plt.savefig('图4_问题人数对比图.png')
plt.close()

# 图5：灵敏度分析（问题1，需求倍数变化）
multipliers = [0.8, 0.9, 1.0, 1.1, 1.2]
sens_result = []
for mult in multipliers:
    demand_scaled = (demand_3d * mult).astype(int)
    # 生成固定列池求解（为节省时间，只用2000列，time limit 15s）
    cols_temp = generate_columns_for_problem(1, num_columns=2000)
    sel_temp, obj_temp, _ = solve_set_covering(cols_temp, demand_scaled, time_limit=15)
    if sel_temp is not None:
        sens_result.append((mult, obj_temp))
    else:
        sens_result.append((mult, None))
plt.figure(figsize=(6,5))
mults = [s[0] for s in sens_result]
objs = [s[1] if s[1] is not None else np.nan for s in sens_result]
plt.plot(mults, objs, 's-', linewidth=2)
plt.xlabel('需求倍数')
plt.ylabel('最少临时工人数')
plt.title('问题1需求灵敏度分析')
plt.grid(True)
plt.tight_layout()
plt.savefig('图5_灵敏度分析图.png')
plt.close()

print("所有图表已保存。")
print("问题1最少人数:", obj1)
print("问题2最少人数:", obj2)
print("问题3最少人数:", obj3)
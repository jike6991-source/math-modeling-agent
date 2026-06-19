import pandas as pd
import numpy as np
import pickle
import traceback
import time
import pulp
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# 全局中文字体设置
plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False

# ---------- 1. 数据加载与预处理 ----------
file_path = r'D:\桌面\math-modeling-agent\projects\2026-06-19_184948\data\附件1.xls'
df = pd.read_excel(file_path, header=None)
# 前两行为标题，数据从第2行开始
data_rows = df.iloc[2:112, :]  # 第2行到第111行（共110行）
# 列：0-天, 1-小时(文本), 2-11 为小组1~10
days = data_rows.iloc[:, 0].astype(int).values - 1  # 转为0~9
hours_str = data_rows.iloc[:, 1].values  # 如 '8:00-9:00'
group_data = data_rows.iloc[:, 2:12].astype(int).values  # 形状 (110, 10)

# 转换小时索引：8:00-9:00 -> 0, ..., 18:00-19:00 -> 10
hour_mapping = {}
for idx, hstr in enumerate(hours_str):
    start = int(hstr.split(':')[0])
    hour_idx = start - 8
    hour_mapping[idx] = hour_idx
hour_idx_arr = np.array([hour_mapping[i] for i in range(len(hours_str))])

# 构建需求三维数组 demand[d][h][g]
demand = np.zeros((10, 11, 10), dtype=int)
for row in range(110):
    d = days[row]
    h = hour_idx_arr[row]
    demand[d, h, :] = group_data[row, :]

print("数据加载完成，需求矩阵形状:", demand.shape)

# ---------- 2. 模式生成函数 ----------
def generate_modes(problem_type):
    """
    problem_type: 1,2,3
    返回模式列表 modes, 每个模式为 dict:
      'a': 三维数组 (11,10) 0/1, 表示该模式每天对 (小时,小组) 的覆盖情况
      'desc': 描述字符串
    索引0固定为休息模式 (全0数组)
    """
    modes = []
    # 休息模式
    zero = np.zeros((11, 10), dtype=int)
    modes.append({'a': zero, 'desc': 'rest'})
    if problem_type in (1, 2):
        # 连续8小时模式
        for s in range(0, 4):  # 开始时段 0,1,2,3
            for g in range(10):
                cover = np.zeros((11, 10), dtype=int)
                for h in range(s, s+8):
                    cover[h, g] = 1  # 注意 h 在0~10内
                modes.append({'a': cover, 'desc': f'cont8_s{s}_g{g+1}'})
    elif problem_type == 3:
        # 连续8小时模式 (同问题1,2)
        for s in range(0, 4):
            for g in range(10):
                cover = np.zeros((11, 10), dtype=int)
                for h in range(s, s+8):
                    cover[h, g] = 1
                modes.append({'a': cover, 'desc': f'cont8_s{s}_g{g+1}'})
        # 拆分模式：第一段 (s1) 连续4h, 第二段 (s2) 连续4h, 间隔>=2h
        # s1 合法: 0,1; s2 合法: 满足 s2 >= s1+4+2 = s1+6, 且 s2+3 <=10 => s2<=7
        for s1 in [0, 1]:
            for s2 in range(s1+6, 8):  # s2 = s1+6, s1+7
                if s2 > 7:
                    continue
                for g1 in range(10):
                    for g2 in range(10):
                        cover = np.zeros((11, 10), dtype=int)
                        for h in range(s1, s1+4):
                            cover[h, g1] = 1
                        for h in range(s2, s2+4):
                            cover[h, g2] = 1
                        modes.append({'a': cover, 'desc': f'split_s1{s1}_s2{s2}_g1{g1+1}_g2{g2+1}'})
    return modes

# ---------- 3. 构建并求解单个问题的函数 ----------
def solve_problem(problem_id, K_upper, time_limit=60):
    """
    problem_id: 1,2,3
    K_upper: 工人数量上界
    返回 (status, obj_value, solution_vars, run_time)
      solution_vars: 若成功，字典 {i: {d: mode_idx}} 等
    """
    modes = generate_modes(problem_id)
    M = len(modes)  # 包含休息模式0
    print(f"问题{problem_id}: 模式数={M-1}（不含休息）")

    # 建立模型
    prob = pulp.LpProblem(f"Problem{problem_id}", pulp.LpMinimize)
    
    # 决策变量
    z = [pulp.LpVariable(f"z_{i}", cat='Binary') for i in range(K_upper)]
    x = {}
    for i in range(K_upper):
        for d in range(10):
            for m in range(M):
                x[(i, d, m)] = pulp.LpVariable(f"x_{i}_{d}_{m}", cat='Binary')
    
    # 目标函数
    prob += pulp.lpSum(z[i] for i in range(K_upper))
    
    # 约束1: 每天每工人选一个模式
    for i in range(K_upper):
        for d in range(10):
            prob += pulp.lpSum(x[(i, d, m)] for m in range(M)) == 1
    
    # 约束2: 工作天数 = 8*z_i (若z=1)
    for i in range(K_upper):
        # 非休息模式 m>0
        prob += pulp.lpSum(x[(i, d, m)] for d in range(10) for m in range(1, M)) == 8 * z[i]
    
    # 约束3: 需求覆盖
    for d in range(10):
        for h in range(11):
            for g in range(10):
                prob += pulp.lpSum(
                    x[(i, d, m)] * modes[m]['a'][h, g]
                    for i in range(K_upper)
                    for m in range(M)
                ) >= demand[d, h, g]
    
    # 问题1额外约束：固定小组
    if problem_id == 1:
        y = {}
        for i in range(K_upper):
            for g in range(10):
                y[(i, g)] = pulp.LpVariable(f"y_{i}_{g}", cat='Binary')
        for i in range(K_upper):
            prob += pulp.lpSum(y[(i, g)] for g in range(10)) == z[i]
        # 连接 x 和 y：如果某模式涉及小组 g，则 x 必须受 y[i,g] 约束
        # 模式 m (m>0) 有对应小组（我们从desc解析或通过a矩阵判断）
        # 简便方式：对每个模式m>0，提取其覆盖的小组（a矩阵中任意小时有1的小组）
        for i in range(K_upper):
            for d in range(10):
                for m in range(1, M):
                    # 找出模式m覆盖的唯一小组 (对于问题1, 所有连续模式只有一个组)
                    g_set = np.where(modes[m]['a'].sum(axis=0) > 0)[0]
                    if len(g_set) == 0:
                        continue  # 休息模式不存在 m=0已在前面
                    # 问题1只允许连续8h模式，所以g_set只有一个元素
                    g_mode = g_set[0]
                    prob += x[(i, d, m)] <= y[(i, g_mode)]
    
    # 求解
    start_time = time.time()
    solver = pulp.PULP_CBC_CMD(msg=False, timeLimit=time_limit)
    prob.solve(solver)
    elapsed = time.time() - start_time
    status = pulp.LpStatus[prob.status]
    print(f"问题{problem_id} 状态: {status}, 用时: {elapsed:.2f}s")
    
    obj = None
    sol = None
    if prob.status in (pulp.LpStatusOptimal, pulp.LpStatusNotSolved, pulp.LpStatusFeasible):
        try:
            obj = pulp.value(prob.objective)
        except:
            obj = None
        # 提取非零变量，只记录使用的工人
        used_workers = []
        for i in range(K_upper):
            if pulp.value(z[i]) > 0.5:
                schedule = {}
                for d in range(10):
                    for m in range(M):
                        if pulp.value(x[(i, d, m)]) > 0.5:
                            schedule[d] = m
                            break
                used_workers.append(schedule)
        sol = {'num_used': len(used_workers), 'schedules': used_workers}
        print(f"问题{problem_id} 最优人数估计: {sol['num_used']}")
    else:
        print(f"问题{problem_id} 未找到可行解")
    
    return status, obj, sol, elapsed

# ---------- 4. 估计工人数上界并求解三个问题 ----------
max_demand_per_hour = demand.max()  # 单小时单小组最大需求
total_demand_max = demand.sum(axis=(1,2)).max()  # 每天总需求最大
K_est = max(30, total_demand_max // 8 + 10)  # 粗略估计每人工作8h，覆盖所有需求小时数
print(f"估计工人数上界 K = {K_est}")

results = {}
time_limits = [60, 60, 60]  # 每个问题时间上限
for pid in [1, 2, 3]:
    status, obj, sol, elapsed = solve_problem(pid, K_est, time_limit=time_limits[pid-1])
    results[f'problem{pid}'] = {
        'status': status,
        'objective': obj,
        'solution': sol,
        'time': elapsed
    }

# ---------- 5. 结果验证 ----------
def verify_solution(problem_id, sol_dict, demand):
    if sol_dict is None or sol_dict['num_used'] == 0:
        print(f"问题{problem_id} 无可行解，跳过验证")
        return
    modes = generate_modes(problem_id)
    schedules = sol_dict['schedules']
    coverage = np.zeros_like(demand, dtype=int)
    for worker_sched in schedules:
        for d in range(10):
            m = worker_sched[d]
            coverage[d] += modes[m]['a']
    # 检查是否满足需求
    shortfall = (demand > coverage).sum()
    if shortfall == 0:
        print(f"问题{problem_id} 需求覆盖验证通过，所有时段均满足")
    else:
        print(f"问题{problem_id} 需求覆盖存在 {shortfall} 个不足时段")
    # 检查每个工人工作天数
    wrong_days = 0
    for worker_sched in schedules:
        days_worked = sum(1 for d in range(10) if worker_sched[d] != 0)
        if days_worked != 8:
            wrong_days += 1
    if wrong_days == 0:
        print(f"问题{problem_id} 工作天数验证通过，所有工人工作8天")
    else:
        print(f"问题{problem_id} 有 {wrong_days} 个工人工作天数不是8")

for pid in [1,2,3]:
    verify_solution(pid, results[f'problem{pid}']['solution'], demand)

# 序列化结果
_results = {
    'demand': demand,
    'results': results
}
with open('_results.pkl', 'wb') as f:
    pickle.dump(_results, f)

# ---------- 6. 可视化（5张图，独立try-except） ----------
import traceback

# 图1：某小组10天需求热力图（以小组1为例）
try:
    plt.figure(figsize=(10, 6))
    g = 0
    demand_g = demand[:, :, g].T  # (小时, 天)
    plt.imshow(demand_g, cmap='YlOrRd', aspect='auto', origin='lower')
    plt.colorbar(label='需求人数')
    plt.xlabel('天')
    plt.ylabel('小时 (8:00-19:00)')
    plt.title(f'小组1 需求热力图')
    plt.xticks(range(10), [f'Day{d+1}' for d in range(10)])
    plt.yticks(range(11), [f'{8+h}:00' for h in range(11)])
    plt.savefig('图1_需求热力图.png', dpi=150, bbox_inches='tight')
    plt.close()
    print('[CHART_OK:图1_需求热力图.png]')
except Exception as e:
    plt.close('all')
    print('[CHART_FAIL:图1_需求热力图.png]')
    print(traceback.format_exc())

# 图2：所有小组总需求时间分布（按天总需求）
try:
    plt.figure(figsize=(10, 5))
    daily_total = demand.sum(axis=(1,2))  # 每天总需求人时
    plt.bar(range(1, 11), daily_total, color='skyblue', edgecolor='black')
    plt.xlabel('天')
    plt.ylabel('总需求人时')
    plt.title('每天所有小组总需求人时')
    plt.xticks(range(1, 11))
    plt.grid(axis='y', linestyle='--', alpha=0.7)
    plt.savefig('图2_总需求分布.png', dpi=150, bbox_inches='tight')
    plt.close()
    print('[CHART_OK:图2_总需求分布.png]')
except Exception as e:
    plt.close('all')
    print('[CHART_FAIL:图2_总需求分布.png]')
    print(traceback.format_exc())

# 图3：三个问题最少人数对比柱状图
try:
    plt.figure(figsize=(8, 5))
    labels = ['问题1', '问题2', '问题3']
    values = []
    for pid,lab in zip([1,2,3], labels):
        sol = results[f'problem{pid}']['solution']
        if sol is not None:
            values.append(sol['num_used'])
        else:
            values.append(0)
    plt.bar(labels, values, color=['#FF9999', '#66B2FF', '#99FF99'])
    plt.xlabel('问题')
    plt.ylabel('最少临时工人数')
    plt.title('三个问题最优人数对比')
    for i, v in enumerate(values):
        plt.text(i, v+0.5, str(v), ha='center')
    plt.savefig('图3_最优人数对比.png', dpi=150, bbox_inches='tight')
    plt.close()
    print('[CHART_OK:图3_最优人数对比.png]')
except Exception as e:
    plt.close('all')
    print('[CHART_FAIL:图3_最优人数对比.png]')
    print(traceback.format_exc())

# 图4：问题1排班示例甘特图（前5名工人）
try:
    pid = 1
    sol = results['problem1']['solution']
    if sol is not None and sol['num_used'] > 0:
        modes = generate_modes(pid)
        schedules = sol['schedules'][:5]
        fig, ax = plt.subplots(figsize=(12, 5))
        colors = plt.cm.tab20.colors
        worker_idx = 0
        for sched in schedules:
            for d in range(10):
                m = sched[d]
                if m == 0:
                    continue
                # 得到工作时段和小组
                # 从模式描述获取
                desc = modes[m]['desc']
                # 简单处理：若为cont8模式, 提取开始时段和小组
                if desc.startswith('cont8'):
                    parts = desc.split('_s')
                    start = int(parts[1].split('_')[0])
                    g = int(parts[1].split('g')[1]) - 1
                    ax.broken_barh([(d*11 + start, 8)], (worker_idx*10, 8), facecolors=colors[g % len(colors)])
            worker_idx += 1
        ax.set_xlabel('天-小时索引')
        ax.set_ylabel('工人')
        ax.set_title('问题1：部分工人排班甘特图（前5人）')
        ax.set_yticks([i*10+4 for i in range(5)])
        ax.set_yticklabels([f'工人{i+1}' for i in range(5)])
        ax.set_xlim(0, 110)
        # 标注小组颜色图例略
        plt.savefig('图4_排班甘特图.png', dpi=150, bbox_inches='tight')
        plt.close()
        print('[CHART_OK:图4_排班甘特图.png]')
    else:
        print('[CHART_FAIL:图4_排班甘特图.png] (无数据)')
except Exception as e:
    plt.close('all')
    print('[CHART_FAIL:图4_排班甘特图.png]')
    print(traceback.format_exc())

# 图5：问题1每日各小组需求覆盖对比示例（Day1检查）
try:
    pid = 1
    sol = results['problem1']['solution']
    if sol is not None and sol['num_used'] > 0:
        d = 0
        modes = generate_modes(pid)
        # 计算覆盖矩阵
        coverage = np.zeros((11, 10), dtype=int)
        for sched in sol['schedules']:
            m = sched[d]
            coverage += modes[m]['a']
        # 绘制某小组（如小组1）的需求与覆盖对比
        g = 0
        plt.figure(figsize=(10, 4))
        hours = np.arange(11)
        plt.plot(hours, demand[d, :, g], 'o-', label='需求')
        plt.plot(hours, coverage[:, g], 's-', label='覆盖')
        plt.xlabel('小时')
        plt.ylabel('人数')
        plt.title(f'问题1 Day1 小组1 需求与覆盖对比')
        plt.legend()
        plt.grid(True)
        plt.savefig('图5_覆盖验证.png', dpi=150, bbox_inches='tight')
        plt.close()
        print('[CHART_OK:图5_覆盖验证.png]')
    else:
        print('[CHART_FAIL:图5_覆盖验证.png] (无数据)')
except Exception as e:
    plt.close('all')
    print('[CHART_FAIL:图5_覆盖验证.png]')
    print(traceback.format_exc())

print('所有图表生成完毕。')
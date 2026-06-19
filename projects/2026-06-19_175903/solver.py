import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from collections import defaultdict
import time
import sys
import warnings
warnings.filterwarnings('ignore')

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False

# ===================== 数据加载与预处理 =====================
data_path = r'D:\桌面\math-modeling-agent\projects\2026-06-19_175903\data\附件1.xls'
try:
    df_raw = pd.read_excel(data_path, header=None)
except Exception as e:
    print(f"读取数据失败: {e}")
    sys.exit(1)

# 根据预览，跳过前两行（标题和表头），提取需求数据
# 数据行从索引2开始
data_lines = df_raw.iloc[2:, :].reset_index(drop=True)
# 列: 0-天, 1-小时, 2..11-小组1..10
days = data_lines.iloc[:, 0].astype(int)
hours = data_lines.iloc[:, 1]  # 字符串
demand_raw = data_lines.iloc[:, 2:12].astype(int).values  # shape (n,10)

# 重塑为 (10天, 11小时, 10小组)
# 转换小时为索引0-10，对应8:00-19:00
# 根据数据，每天有11行，共110行
n_days = 10
n_hours = 11
n_groups = 10
assert demand_raw.shape[0] == n_days * n_hours, "数据行数不符合10天*11小时"

demand = np.zeros((n_days, n_hours, n_groups), dtype=int)
for idx in range(len(demand_raw)):
    d = days[idx] - 1  # 0-based
    # 小时字符串解析，按顺序对应8:00-9:00 .. 18:00-19:00
    h = idx % n_hours
    demand[d, h, :] = demand_raw[idx, :]

print("需求数据加载完成，形状:", demand.shape)

# ===================== 生成合法工作日班次模式 =====================
# 小时索引0..10，每个模式由两个不重叠的连续4小时段组成，外加一个休息模式(全0)
patterns = []  # 每个元素是一个长度为11的0/1列表，patterns[0]是休息
patterns.append([0]*n_hours)  # 休息
work_patterns = []  # 非休息模式索引

# 枚举段1起始s1 (0..7)，段2起始s2 (s1+4..7)
for s1 in range(0, 8):
    for s2 in range(s1+4, 8):  # 保证不重叠
        vec = [0]*n_hours
        for i in range(s1, s1+4):
            vec[i] = 1
        for i in range(s2, s2+4):
            vec[i] = 1
        patterns.append(vec)
        work_patterns.append(len(patterns)-1)

num_patterns = len(patterns)
print(f"模式总数: {num_patterns}, 工作模式: {len(work_patterns)}")

# ===================== 问题一：MILP 小组独立 =====================
def solve_problem1_group(g_index, time_limit=30):
    """
    对指定小组使用MILP求解最小工人数
    """
    from pulp import LpProblem, LpMinimize, LpVariable, lpSum, LpStatus, value, PULP_CBC_CMD

    dem_g = demand[:, :, g_index]  # (10,11)
    max_dem = dem_g.max()
    # 保守上界
    K_up = max(30, int(max_dem * 3))
    # 模式索引
    M_rest = 0  # 休息模式
    M_work = work_patterns

    prob = LpProblem(f"P1_Group{g_index+1}", LpMinimize)

    # 变量
    u = [LpVariable(f"u_{i}", cat='Binary') for i in range(K_up)]
    # x[i][t][m] 只有 u[i]==1 时可能为1
    x = [[[LpVariable(f"x_{i}_{t}_{m}", cat='Binary') 
           for m in range(num_patterns)] for t in range(n_days)] for i in range(K_up)]

    # 目标
    prob += lpSum(u)

    # 约束
    for i in range(K_up):
        for t in range(n_days):
            # 每天必须选一个模式（若u_i=0则全0）
            prob += lpSum(x[i][t][m] for m in range(num_patterns)) == u[i]
        # 总工作天数=8
        prob += lpSum(x[i][t][m] for t in range(n_days) for m in M_work) == 8 * u[i]
        # 对称破缺
        if i < K_up-1:
            prob += u[i] >= u[i+1]

    # 需求覆盖
    for t in range(n_days):
        for h in range(n_hours):
            prob += lpSum(x[i][t][m] * patterns[m][h] 
                         for i in range(K_up) for m in range(num_patterns)) >= int(dem_g[t, h])

    # 求解
    prob.solve(PULP_CBC_CMD(msg=False, timeLimit=time_limit))
    status = LpStatus[prob.status]
    if status in ['Optimal', 'Feasible']:
        used = int(value(lpSum(u)))
        # 提取排班
        schedule = [[[] for _ in range(n_days)] for _ in range(used)]
        idx = 0
        for i in range(K_up):
            if value(u[i]) and value(u[i]) > 0.5:
                for t in range(n_days):
                    for m in range(num_patterns):
                        if value(x[i][t][m]) > 0.5:
                            schedule[idx][t] = patterns[m]
                idx += 1
        return used, schedule, status
    else:
        return None, None, status


print("\n开始求解问题1...")
p1_workers_per_group = []
p1_schedules = []
start_time = time.time()
for g in range(n_groups):
    print(f"  小组 {g+1}...")
    num, sched, st = solve_problem1_group(g, time_limit=30)
    if num is not None:
        p1_workers_per_group.append(num)
        p1_schedules.append(sched)
        print(f"    小组 {g+1}: 最少工人数 = {num}, 状态={st}")
    else:
        # 如果失败，保守估计一个值（不会用于后续绘图分析）
        p1_workers_per_group.append(0)
        p1_schedules.append([])
        print(f"    小组 {g+1}: 求解失败, 状态={st}")
p1_total = sum(p1_workers_per_group)
print(f"问题1总工人数: {p1_total}, 耗时: {time.time()-start_time:.1f}s")

# ===================== 问题二：CP-SAT 全局建模 =====================
from ortools.sat.python import cp_model

def solve_problem2_cp(time_limit=30):
    """
    使用CP-SAT求解问题2，最小化工日数
    采用逐步增加工人数的策略
    """
    # 确定下界：单个小时最大需求
    lb = int(np.max(demand))  # 至少需要这些工人
    # 遍历K从lb到某个上界
    max_K = 200
    for K in range(lb, max_K+1):
        model = cp_model.CpModel()
        # 变量: mode[i,t] 取值范围 0..num_patterns-1, 0=休息
        mode = {}
        for i in range(K):
            for t in range(n_days):
                mode[i,t] = model.NewIntVar(0, num_patterns-1, f'mode_{i}_{t}')
        
        # 辅助: work[i,t] 是否工作 (mode != 0)
        work = {}
        for i in range(K):
            for t in range(n_days):
                w = model.NewBoolVar(f'work_{i}_{t}')
                model.Add(mode[i,t] == 0).OnlyEnforceIf(w.Not())
                model.Add(mode[i,t] != 0).OnlyEnforceIf(w)
                work[i,t] = w
        
        # 每天选择小组: group[i,t] 0..10, 0表示休息
        group = {}
        for i in range(K):
            for t in range(n_days):
                group[i,t] = model.NewIntVar(0, n_groups, f'group_{i}_{t}')
                # 休息时小组必须为0
                model.Add(group[i,t] == 0).OnlyEnforceIf(work[i,t].Not())
                # 工作时小组必须 >=1
                model.Add(group[i,t] >= 1).OnlyEnforceIf(work[i,t])
        
        # 每个工人工作总天数=8
        for i in range(K):
            model.Add(sum(work[i,t] for t in range(n_days)) == 8)
        
        # 需求覆盖: 对于每个t,h,g，累计模式中覆盖小时的工人
        # 创建辅助变量 cover_hour[i,t,h] 布尔，表示是否在第h小时工作（根据模式）
        cover_hour = {}
        for i in range(K):
            for t in range(n_days):
                for h in range(n_hours):
                    cov = model.NewBoolVar(f'cov_{i}_{t}_{h}')
                    # 约束: cov == 1 当且仅当 mode对应的模式p[h]==1
                    # 通过AllowedAssignments约束
                    allowed = []
                    for m_idx in range(num_patterns):
                        if patterns[m_idx][h] == 1:
                            # 允许 (mode=m_idx, cov=True)
                            allowed.append([m_idx, 1])
                        else:
                            # (mode=m_idx, cov=False)
                            allowed.append([m_idx, 0])
                    model.AddAllowedAssignments([mode[i,t], cov], allowed)
                    cover_hour[i,t,h] = cov
        
        # 小组覆盖累计
        for t in range(n_days):
            for h in range(n_hours):
                for g in range(1, n_groups+1):  # g=1..10
                    # sum over i of (group[i,t]==g and cover_hour[i,t,h]) >= demand[t,h,g-1]
                    works_in_group = []
                    for i in range(K):
                        is_g = model.NewBoolVar(f'isgroup_{i}_{t}_{g}')
                        model.Add(group[i,t] == g).OnlyEnforceIf(is_g)
                        model.Add(group[i,t] != g).OnlyEnforceIf(is_g.Not())
                        b = model.NewBoolVar(f'contributes_{i}_{t}_{h}_{g}')
                        model.AddBoolAnd([is_g, cover_hour[i,t,h]]).OnlyEnforceIf(b)
                        model.AddBoolOr([is_g.Not(), cover_hour[i,t,h].Not()]).OnlyEnforceIf(b.Not())
                        works_in_group.append(b)
                    model.Add(sum(works_in_group) >= int(demand[t,h,g-1]))
        
        # 目标：最小化工日数？这里K固定，我们只要找可行解，所以没有目标。
        # 设置求解器找第一个可行解
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = time_limit
        solver.parameters.num_search_workers = 8
        status = solver.Solve(model)
        if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
            print(f"    问题2: K={K} 找到可行解, 状态={solver.StatusName(status)}")
            # 提取排班
            schedule = [{'groups':[], 'modes':[]} for _ in range(K)]
            actual_used = 0
            for i in range(K):
                any_work = False
                for t in range(n_days):
                    g_val = solver.Value(group[i,t])
                    m_val = solver.Value(mode[i,t])
                    schedule[i]['groups'].append(g_val)
                    schedule[i]['modes'].append(m_val)
                    if g_val != 0:
                        any_work = True
                if any_work:
                    actual_used += 1
            return actual_used, schedule, status
        else:
            # print(f"    问题2: K={K} 不可行或超时")
            pass
    return None, None, cp_model.UNKNOWN

print("\n开始求解问题2 (CP-SAT)...")
start_time = time.time()
p2_workers, p2_schedule, p2_status = solve_problem2_cp(time_limit=30)
print(f"问题2总工人数: {p2_workers}, 耗时: {time.time()-start_time:.1f}s")

# ===================== 问题三：CP-SAT 双段跨组 =====================
def solve_problem3_cp(time_limit=30):
    """
    使用CP-SAT求解问题3，每个工人每天两个4小时段，可分配不同小组，间隔≥2h
    """
    lb = int(np.max(demand))
    max_K = 200
    for K in range(lb, max_K+1):
        model = cp_model.CpModel()
        # 对于每个工人每天，创建两个段的起始和小组
        # 段变量: start[i,t,k] 0..7, 长度固定4; group_seg[i,t,k] 1..10 (如果使用)
        seg_start = {}
        seg_group = {}
        seg_present = {}  # 该段是否使用
        work_day = {}
        for i in range(K):
            for t in range(n_days):
                # 每天两个段
                seg_start[i,t,0] = model.NewIntVar(0, 7, f'start_{i}_{t}_0')
                seg_start[i,t,1] = model.NewIntVar(0, 7, f'start_{i}_{t}_1')
                seg_group[i,t,0] = model.NewIntVar(1, n_groups, f'seg_group_{i}_{t}_0')
                seg_group[i,t,1] = model.NewIntVar(1, n_groups, f'seg_group_{i}_{t}_1')
                # 布尔指示该天是否工作 (两个段都使用)
                w = model.NewBoolVar(f'work_{i}_{t}')
                # 如果工作，强制两段均启用；如果休息，不启用段（通过约束覆盖）
                work_day[i,t] = w
                # 约束：两个段不重叠且间隔≥2小时，即 |start0 - start1| >= 6
                # 采用差值绝对值
                diff = model.NewIntVar(-7, 7, f'diff_{i}_{t}')
                model.Add(diff == seg_start[i,t,0] - seg_start[i,t,1])
                abs_diff = model.NewIntVar(0, 7, f'absdiff_{i}_{t}')
                # abs 建模
                model.AddAbsEquality(abs_diff, diff)
                model.Add(abs_diff >= 6).OnlyEnforceIf(w)
                # 休息日：两者起始设为0，但不强制group，通过需求覆盖自然不需要
        
        # 工作总天数=8
        for i in range(K):
            model.Add(sum(work_day[i,t] for t in range(n_days)) == 8)
        
        # 需求覆盖：对于每个t,h,g，累计覆盖该小时且工作在组g的段
        for t in range(n_days):
            for h in range(n_hours):
                for g in range(1, n_groups+1):
                    cnt = []
                    for i in range(K):
                        for k in range(2):
                            # 段k覆盖小时h 条件: work_day[i,t] and seg_group[i,t,k]==g and seg_start <= h < seg_start+4
                            covers = model.NewBoolVar(f'cov_{i}_{t}_{h}_{g}_{k}')
                            # 分段条件
                            is_group = model.NewBoolVar(f'isg_{i}_{t}_{k}_{g}')
                            model.Add(seg_group[i,t,k] == g).OnlyEnforceIf(is_group)
                            model.Add(seg_group[i,t,k] != g).OnlyEnforceIf(is_group.Not())
                            # 覆盖小时：start <= h and start+4 > h 即 start <= h and start >= h-3 (等价)
                            # 用两个布尔指示
                            lo = model.NewBoolVar(f'lo_{i}_{t}_{h}_{k}')
                            hi = model.NewBoolVar(f'hi_{i}_{t}_{h}_{k}')
                            model.Add(seg_start[i,t,k] <= h).OnlyEnforceIf(lo)
                            model.Add(seg_start[i,t,k] > h).OnlyEnforceIf(lo.Not())
                            model.Add(seg_start[i,t,k] + 4 > h).OnlyEnforceIf(hi)
                            model.Add(seg_start[i,t,k] + 4 <= h).OnlyEnforceIf(hi.Not())
                            # 综合：covers = work_day[t] && is_group && lo && hi
                            model.AddBoolAnd([work_day[i,t], is_group, lo, hi]).OnlyEnforceIf(covers)
                            model.AddBoolOr([work_day[i,t].Not(), is_group.Not(), lo.Not(), hi.Not()]).OnlyEnforceIf(covers.Not())
                            cnt.append(covers)
                    model.Add(sum(cnt) >= int(demand[t,h,g-1]))
        
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = time_limit
        solver.parameters.num_search_workers = 8
        status = solver.Solve(model)
        if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
            print(f"    问题3: K={K} 找到可行解, 状态={solver.StatusName(status)}")
            # 提取排班
            schedule = []
            actual_used = 0
            for i in range(K):
                day_info = []
                used = False
                for t in range(n_days):
                    if solver.Value(work_day[i,t]):
                        used = True
                        segs = []
                        for k in range(2):
                            s = solver.Value(seg_start[i,t,k])
                            g = solver.Value(seg_group[i,t,k])
                            segs.append((s,g))
                        day_info.append(segs)
                    else:
                        day_info.append([])
                schedule.append(day_info)
                if used:
                    actual_used += 1
            return actual_used, schedule, status
        # else: continue
    return None, None, cp_model.UNKNOWN

print("\n开始求解问题3 (CP-SAT)...")
start_time = time.time()
p3_workers, p3_schedule, p3_status = solve_problem3_cp(time_limit=30)
print(f"问题3总工人数: {p3_workers}, 耗时: {time.time()-start_time:.1f}s")

# ===================== 结果验证与图表生成 =====================
def verify_demand(schedule, demand, problem=1):
    """简单验证需求满足情况，返回最大缺口"""
    cover = np.zeros_like(demand, dtype=int)
    if problem == 1:
        # schedule: list of per group schedules
        for g in range(n_groups):
            sched_g = schedule[g]
            for worker in sched_g:
                for t in range(n_days):
                    if worker[t]:
                        pat = np.array(worker[t])
                        cover[t, :, g] += pat
    elif problem == 2:
        # schedule: list of workers, each with groups and modes lists
        for worker in schedule:
            for t in range(n_days):
                g = worker['groups'][t]
                if g != 0:
                    m = worker['modes'][t]
                    cover[t, :, g-1] += np.array(patterns[m])
    elif problem == 3:
        # schedule: list of workers, each a list of days with list of (start, group) pairs
        for worker in schedule:
            for t in range(n_days):
                for seg in worker[t]:
                    if seg:
                        s, g = seg
                        for h in range(s, s+4):
                            if 0 <= h < n_hours:
                                cover[t, h, g-1] += 1
    shortage = demand - cover
    max_short = shortage.max()
    return max_short

# 验证
if p1_schedules:
    p1_short = verify_demand(p1_schedules, demand, problem=1)
    print(f"问题1需求验证最大缺口: {p1_short}")
if p2_schedule:
    p2_short = verify_demand(p2_schedule, demand, problem=2)
    print(f"问题2需求验证最大缺口: {p2_short}")
if p3_schedule:
    p3_short = verify_demand(p3_schedule, demand, problem=3)
    print(f"问题3需求验证最大缺口: {p3_short}")

# ---------- 图1: 需求热力图（所有小组每天总需求） ----------
daily_total_demand = demand.sum(axis=2)  # (10,11)
plt.figure(figsize=(12,6))
plt.imshow(daily_total_demand.T, aspect='auto', cmap='YlOrRd', origin='lower')
plt.colorbar(label='总需求人数')
plt.xlabel('天')
plt.ylabel('小时')
plt.title('图1：各天各小时总需求热力图')
plt.xticks(np.arange(n_days), [f'Day {i+1}' for i in range(n_days)])
plt.yticks(np.arange(n_hours), [f'{8+h}:00' for h in range(n_hours)])
plt.tight_layout()
plt.savefig('图1_需求热力图.png')
plt.close()

# ---------- 图2: 问题1各小组最小工人数柱状图 ----------
if p1_workers_per_group:
    groups = [f'小组{i+1}' for i in range(n_groups)]
    plt.figure(figsize=(10,5))
    plt.bar(groups, p1_workers_per_group, color='skyblue')
    plt.title('图2：问题1各小组所需最少临时工数')
    plt.xlabel('小组')
    plt.ylabel('工人数')
    for i, v in enumerate(p1_workers_per_group):
        plt.text(i, v+0.5, str(v), ha='center')
    plt.tight_layout()
    plt.savefig('图2_问题1小组工人数.png')
    plt.close()

# ---------- 图3: 问题2某天甘特图（第5天为例） ----------
if p2_schedule:
    day_idx = 4  # 第5天
    # 随机取前30个工人绘制
    workers_to_plot = min(30, p2_workers)
    fig, ax = plt.subplots(figsize=(14, 8))
    y_labels = []
    for i in range(workers_to_plot):
        g = p2_schedule[i]['groups'][day_idx]
        m = p2_schedule[i]['modes'][day_idx]
        if g != 0:
            pat = np.array(patterns[m])
            # 找出工作小时段并画矩形
            in_work = np.where(pat == 1)[0]
            if len(in_work) > 0:
                start_h = in_work[0]
                end_h = in_work[-1] + 1
                ax.barh(i, end_h-start_h, left=start_h, color=f'C{g-1}', alpha=0.8)
        y_labels.append(f'工{i+1}')
    ax.set_yticks(range(workers_to_plot))
    ax.set_yticklabels(y_labels, fontsize=6)
    ax.set_xlim(0, 11)
    ax.set_xticks(range(0,12))
    ax.set_xticklabels([f'{8+h}:00' for h in range(12)])
    ax.set_xlabel('小时')
    ax.set_ylabel('工人')
    ax.set_title(f'图3：问题2第{day_idx+1}天工人排班甘特图（显示前{workers_to_plot}人）')
    ax.grid(axis='x', linestyle='--', alpha=0.5)
    plt.tight_layout()
    plt.savefig('图3_问题2甘特图.png')
    plt.close()

# ---------- 图4: 问题3工人休息日分布饼图 ----------
if p3_schedule:
    rest_days_count = []
    for i in range(p3_workers):
        rest_days = sum(1 for t in range(n_days) if not p3_schedule[i][t])
        rest_days_count.append(rest_days)
    # 理论上都是2，检查一下
    unique, counts = np.unique(rest_days_count, return_counts=True)
    plt.figure(figsize=(6,6))
    plt.pie(counts, labels=[f'{u}天休息 ({c})' for u,c in zip(unique, counts)], autopct='%1.1f%%', startangle=90)
    plt.title('图4：问题3工人休息天数分布')
    plt.tight_layout()
    plt.savefig('图4_问题3休息分布.png')
    plt.close()

# ---------- 图5: 三种模式总工人数对比 ----------
total_workers = []
labels = ['问题1', '问题2', '问题3']
if p1_workers_per_group:
    total_workers.append(p1_total)
else:
    total_workers.append(0)
if p2_workers:
    total_workers.append(p2_workers)
else:
    total_workers.append(0)
if p3_workers:
    total_workers.append(p3_workers)
else:
    total_workers.append(0)

plt.figure(figsize=(8,5))
bars = plt.bar(labels, total_workers, color=['#1f77b4', '#ff7f0e', '#2ca02c'])
plt.title('图5：三种工作模式所需最少临时工数对比')
plt.ylabel('临时工数')
for bar, val in zip(bars, total_workers):
    plt.text(bar.get_x()+bar.get_width()/2, bar.get_height()+0.5, str(val), ha='center')
plt.tight_layout()
plt.savefig('图5_三种模式对比.png')
plt.close()

print("\n所有图表已生成。")
print(f"最终结果: 问题1={p1_total}, 问题2={p2_workers}, 问题3={p3_workers}")
import pandas as pd
import numpy as np
import pulp
import matplotlib.pyplot as plt
import warnings
warnings.filterwarnings('ignore')

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False

# ==================== 1. 数据加载与预处理 ====================
file_path = r'D:\桌面\math-modeling-agent\projects\2026-06-17_232229\data\附件1.xls'
df = pd.read_excel(file_path, header=1)  # 第0行是标题，第1行是列名
df = df.dropna(how='all')               # 删除可能的空行
# 列名：天、小时、小组1...小组10
# 构建需求矩阵 D[g][d][h] (g:0-9, d:0-9, h:0-10)
days = sorted(df['天'].unique())
hours_str = df['小时'].unique()
# 将小时字符串映射为小时索引1-11
hour_map = {}
for i, h in enumerate(hours_str):
    hour_map[h] = i+1  # 1-based
# 初始化需求数组
num_groups = 10
num_days = 10
num_hours = 11
D = np.zeros((num_groups, num_days, num_hours), dtype=int)
for _, row in df.iterrows():
    d = int(row['天']) - 1  # 0-based
    h_str = row['小时']
    h = hour_map[h_str] - 1  # 0-based
    for g in range(num_groups):
        D[g, d, h] = int(row[f'小组{g+1}'])
print("数据加载完成，需求矩阵形状:", D.shape)

# ==================== 2. 工作模式生成 ====================
# 小时索引1-11，连续4小时段起点1..8（1:8:00-9:00, ..., 8:15:00-16:00? 实际8+3=11，即18:00-19:00? 需要验证：起点8对应15:00-16:00? 不对，8:00开始为1，所以起点8对应15:00-16:00，然后+3到18:00-19:00? 小时8-11对应15:00-19:00，但11小时中最后一个是18:00-19:00，所以起点8+3=11正确。所以起点索引1到8。
def generate_daily_patterns():
    """生成10种不重叠的每日工作模式，返回模式列表，每个模式为小时索引集合（0-10）"""
    patterns = []
    for i in range(1, 9):  # 起点1..8
        for j in range(i+4, 9):  # 起点j ≥ i+4 确保不重叠
            hours = set(range(i-1, i+3)) | set(range(j-1, j+3))  # 转换为0-based小时索引
            patterns.append(hours)
    return patterns

patterns = generate_daily_patterns()  # 10种模式
num_patterns = len(patterns)
print(f"每日工作模式数: {num_patterns}")

# 模式覆盖矩阵 a[p,h] (0-based)
a = np.zeros((num_patterns, num_hours), dtype=int)
for p, hours_set in enumerate(patterns):
    for h in hours_set:
        a[p, h] = 1

# ==================== 3. 问题1求解（各小组独立） ====================
print("\n======= 问题1求解 =======")
N1 = np.zeros(num_groups, dtype=int)
z1 = np.zeros((num_groups, num_patterns, num_days), dtype=int)

for g in range(num_groups):
    print(f"求解小组 {g+1}...")
    prob = pulp.LpProblem(f"Problem1_Group{g+1}", pulp.LpMinimize)
    # 变量
    N = pulp.LpVariable(f"N_{g}", lowBound=0, cat='Integer')
    z = pulp.LpVariable.dicts(f"z_{g}", ((p,d) for p in range(num_patterns) for d in range(num_days)),
                              lowBound=0, cat='Integer')
    # 目标
    prob += N
    # 约束
    for d in range(num_days):
        for h in range(num_hours):
            prob += pulp.lpSum([a[p,h] * z[p,d] for p in range(num_patterns)]) >= D[g,d,h]
    for d in range(num_days):
        prob += pulp.lpSum([z[p,d] for p in range(num_patterns)]) <= N
    # 总人天
    prob += pulp.lpSum([z[p,d] for p in range(num_patterns) for d in range(num_days)]) == 8 * N
    # 求解
    solver = pulp.PULP_CBC_CMD(msg=False, timeLimit=15)
    prob.solve(solver)
    if pulp.LpStatus[prob.status] in ['Optimal', 'Feasible']:
        N1[g] = int(pulp.value(N))
        for p in range(num_patterns):
            for d in range(num_days):
                z1[g,p,d] = int(pulp.value(z[p,d]) or 0)
        print(f"  小组{g+1} 最优工人数: {N1[g]}")
    else:
        print(f"  小组{g+1} 求解失败，使用下界估计")
        # 简单下界：总人时/64
        total_work = D[g,:,:].sum()
        N1[g] = int(np.ceil(total_work / 64))
        # 设置z为0（不精确）
        z1[g,:,:] = 0

total_N1 = N1.sum()
print(f"问题1总临时工数: {total_N1}")

# ==================== 4. 问题2求解（全局模型） ====================
print("\n======= 问题2求解 =======")
prob2 = pulp.LpProblem("Problem2", pulp.LpMinimize)
N2 = pulp.LpVariable("N", lowBound=0, cat='Integer')
z2 = pulp.LpVariable.dicts("z2", ((g,p,d) for g in range(num_groups) for p in range(num_patterns) for d in range(num_days)),
                           lowBound=0, cat='Integer')
# 目标
prob2 += N2
# 需求约束
for g in range(num_groups):
    for d in range(num_days):
        for h in range(num_hours):
            prob2 += pulp.lpSum([a[p,h] * z2[g,p,d] for p in range(num_patterns)]) >= D[g,d,h]
# 每天总人数约束
for d in range(num_days):
    prob2 += pulp.lpSum([z2[g,p,d] for g in range(num_groups) for p in range(num_patterns)]) <= N2
# 总人天约束
prob2 += pulp.lpSum([z2[g,p,d] for g in range(num_groups) for p in range(num_patterns) for d in range(num_days)]) == 8 * N2

solver2 = pulp.PULP_CBC_CMD(msg=False, timeLimit=30)
prob2.solve(solver2)
if pulp.LpStatus[prob2.status] in ['Optimal', 'Feasible']:
    N2_val = int(pulp.value(N2))
    z2_arr = np.zeros((num_groups, num_patterns, num_days), dtype=int)
    for g in range(num_groups):
        for p in range(num_patterns):
            for d in range(num_days):
                z2_arr[g,p,d] = int(pulp.value(z2[g,p,d]) or 0)
    print(f"问题2最小临时工数: {N2_val}")
else:
    print("问题2求解失败，使用估计值")
    total_work = D.sum()
    N2_val = int(np.ceil(total_work / 64))
    z2_arr = np.zeros((num_groups, num_patterns, num_days), dtype=int)

# ==================== 5. 问题3求解（全局模型） ====================
print("\n======= 问题3求解 =======")
# 构建双组模式列表
def generate_double_group_patterns():
    """返回双组模式列表，每个模式表示为 (g1, p1, g2, p2)，并计算覆盖矩阵 c[g,h]"""
    double_patterns = []
    for g1 in range(num_groups):
        for g2 in range(num_groups):
            if g1 == g2:
                continue
            for p1 in range(num_patterns):
                # 时段p1的起始小时索引 (0-based)
                # pattern由两个不重叠时段组成，取其第一个时段的起点（最小的小时索引）
                # 计算p1覆盖的小时最小值，用作起始
                h_set1 = patterns[p1]
                start1 = min(h_set1)  # 0-based
                end1 = max(h_set1)    # 0-based
                # 要求第二时段始于第一时段结束+2小时，即 start2 >= end1 + 3 (因为end1是最后小时，结束时间=end1+1? 注意小时索引：如果end1=3（11:00-12:00），则结束时间为12:00，休息2小时后14:00，即小时索引5（13:00-14:00? 不对，需要统一）
                # 更精确：每个时段覆盖小时{ start, start+1, start+2, start+3 }，结束时间为start+4小时（如8:00-12:00，结束12:00）。所以休息2小时要求下一时段开始时间≥12:00+2=14:00，即下一时段起始小时索引≥6（14:00对应小时7? 我们小时索引0:8:00, 1:9:00, ..., 10:18:00-19:00。所以若第一时段结束于小时索引s+3，则结束时间对应索引s+4? 实际上是小时[s, s+3]，结束时刻为(s+4):00。所以休息2小时后至少(s+6):00开始，即下一时段起始小时索引至少为s+5（因为s+6对应小时索引s+6?）。简化：我们直接用小时索引范围：第一时段覆盖s..s+3，结束时对应小时索引s+3+1? 不好。我们用整数小时段表示：小时段h对应从h:00到h+1:00，其中h=8,9,...,18。我们用小时索引1-11对应8:00-9:00,...,18:00-19:00。那么第一时段从起始小时索引i到i+3，结束于(i+4):00。休息2小时后最早开始于(i+6):00，即起始小时索引i+5（因为 (i+6):00对应小时索引i+5+1? 混乱）。我们采取更直接的方法：枚举所有可能的两个4小时时段，检查其是否满足间隔≥2小时。用整数小时表示（8-18），两个时段分别从a1,a2开始（a1,a2∈{8,9,10,11,12,13,14,15}），各覆盖[a1, a1+3]和[a2, a2+3]。时间限制：a1+3+2 ≤ a2，即a2 ≥ a1+5。所以枚举a1和a2。我们生成的patterns是基于小时索引0-based（0对应8:00），所以起始索引x (0-7)。条件：x1+3+2 ≤ x2 => x2 ≥ x1+5。因此x1最大为2（因为x1=2时x2≥7，x2最大7）。所以枚举x1=0,1,2；x2从x1+5到7。按小时索引0-7对应原小时8-15。这样生成的双组模式覆盖小时集合：第一个小组的小时集{x1..x1+3}，第二个小组的小时集{x2..x2+3}。
    min_start = 0
    max_start = 7
    double_patterns = []
    for g1 in range(num_groups):
        for g2 in range(num_groups):
            if g1 == g2:
                continue
            for x1 in range(0, 3):  # x1=0,1,2
                for x2 in range(x1+5, max_start+1):
                    # 构建覆盖向量
                    cover = [ (g1, list(range(x1, x1+4))), (g2, list(range(x2, x2+4))) ]
                    double_patterns.append(cover)
    return double_patterns

double_patterns = generate_double_group_patterns()
num_double = len(double_patterns)
print(f"双组模式数: {num_double}")

# 合并单组和双组模式：总模式数
# 单组模式：每个模式对应 (g, p) 及覆盖小时（直接使用patterns）
single_patterns = []
for g in range(num_groups):
    for p in range(num_patterns):
        cover = [ (g, list(patterns[p])) ]
        single_patterns.append(cover)
all_patterns = single_patterns + double_patterns
M = len(all_patterns)
print(f"总模式数: {M}")

# 构建覆盖矩阵 c[m][g][h] (0-based)
c = np.zeros((M, num_groups, num_hours), dtype=int)
for m, cover_list in enumerate(all_patterns):
    for g, hours_list in cover_list:
        for h in hours_list:
            c[m, g, h] = 1

# 建立问题3的ILP
prob3 = pulp.LpProblem("Problem3", pulp.LpMinimize)
N3 = pulp.LpVariable("N3", lowBound=0, cat='Integer')
z3 = pulp.LpVariable.dicts("z3", ((m, d) for m in range(M) for d in range(num_days)),
                           lowBound=0, cat='Integer')
prob3 += N3
# 需求约束
for g in range(num_groups):
    for d in range(num_days):
        for h in range(num_hours):
            prob3 += pulp.lpSum([c[m,g,h] * z3[m,d] for m in range(M)]) >= D[g,d,h]
# 每天总人数约束
for d in range(num_days):
    prob3 += pulp.lpSum([z3[m,d] for m in range(M)]) <= N3
# 总人天约束
prob3 += pulp.lpSum([z3[m,d] for m in range(M) for d in range(num_days)]) == 8 * N3

solver3 = pulp.PULP_CBC_CMD(msg=False, timeLimit=40)
prob3.solve(solver3)
if pulp.LpStatus[prob3.status] in ['Optimal', 'Feasible']:
    N3_val = int(pulp.value(N3))
    z3_arr = np.zeros((M, num_days), dtype=int)
    for m in range(M):
        for d in range(num_days):
            z3_arr[m,d] = int(pulp.value(z3[m,d]) or 0)
    print(f"问题3最小临时工数: {N3_val}")
else:
    print("问题3求解失败，使用估计值")
    total_work = D.sum()
    N3_val = int(np.ceil(total_work / 64))
    z3_arr = np.zeros((M, num_days), dtype=int)

# ==================== 6. 结果验证 ====================
print("\n======= 结果验证 =======")
# 验证问题1每个小组需求是否满足（使用求解得到的z1）
print("问题1约束满足检查:")
for g in range(num_groups):
    max_vio = 0
    for d in range(num_days):
        for h in range(num_hours):
            cover = sum(z1[g,p,d] * a[p,h] for p in range(num_patterns))
            if cover < D[g,d,h]:
                max_vio = max(max_vio, D[g,d,h] - cover)
    if max_vio == 0:
        print(f"  小组{g+1}: 所有需求满足")
    else:
        print(f"  小组{g+1}: 最大违反 {max_vio}（可能由于求解超时）")

# 验证问题2
print("\n问题2约束满足检查:")
max_vio2 = 0
for g in range(num_groups):
    for d in range(num_days):
        for h in range(num_hours):
            cover = sum(z2_arr[g,p,d] * a[p,h] for p in range(num_patterns))
            if cover < D[g,d,h]:
                max_vio2 = max(max_vio2, D[g,d,h] - cover)
if max_vio2 == 0:
    print("  所有需求满足")
else:
    print(f"  最大违反 {max_vio2}")

# 验证问题3
print("\n问题3约束满足检查:")
max_vio3 = 0
for g in range(num_groups):
    for d in range(num_days):
        for h in range(num_hours):
            cover = sum(z3_arr[m,d] * c[m,g,h] for m in range(M))
            if cover < D[g,d,h]:
                max_vio3 = max(max_vio3, D[g,d,h] - cover)
if max_vio3 == 0:
    print("  所有需求满足")
else:
    print(f"  最大违反 {max_vio3}")

# 输出总人数
print(f"\n问题1总人数: {total_N1}")
print(f"问题2总人数: {N2_val}")
print(f"问题3总人数: {N3_val}")

# ==================== 7. 可视化（5张图） ====================
print("\n======= 生成图表 =======")

# 图1: 各小组需求热力图（10天×11小时）
fig, axes = plt.subplots(2, 5, figsize=(20, 8))
for g in range(num_groups):
    ax = axes[g//5, g%5]
    data = D[g,:,:]  # 10x11
    im = ax.imshow(data, aspect='auto', cmap='YlOrRd')
    ax.set_title(f'小组{g+1}')
    ax.set_xlabel('小时')
    ax.set_ylabel('天')
    plt.colorbar(im, ax=ax)
plt.tight_layout()
plt.savefig('图1_需求热力图.png')
plt.close()

# 图2: 各小组总需求条形图
total_demand = D.sum(axis=(1,2))  # sum over days and hours
groups = [f'小组{i+1}' for i in range(num_groups)]
plt.figure(figsize=(10,5))
plt.bar(groups, total_demand, color='steelblue')
plt.title('各小组总需求（人时）')
plt.ylabel('总人时需求')
plt.xticks(rotation=45)
plt.tight_layout()
plt.savefig('图2_各小组总需求.png')
plt.close()

# 图3: 问题1各小组最优工人数条形图
plt.figure(figsize=(10,5))
plt.bar(groups, N1, color='coral')
plt.title('问题1各小组所需最少临时工人数')
plt.ylabel('工人数')
plt.xticks(rotation=45)
plt.tight_layout()
plt.savefig('图3_问题1工人数.png')
plt.close()

# 图4: 问题2第1天各小组各模式工人数堆叠条形图（展示一天）
d0 = 0  # 第1天
fig, ax = plt.subplots(figsize=(12,6))
# 计算每个模式（小组+模式）第1天的工人数
modes_day0 = []
groups_day0 = []
for g in range(num_groups):
    for p in range(num_patterns):
        val = z2_arr[g,p,d0]
        if val > 0:
            modes_day0.append(val)
            groups_day0.append(f'G{g+1}P{p}')
bars = ax.bar(range(len(modes_day0)), modes_day0, color='green', alpha=0.7)
ax.set_xticks(range(len(modes_day0)))
ax.set_xticklabels(groups_day0, rotation=90, fontsize=8)
ax.set_title(f'问题2第1天各模式工人数分布')
ax.set_ylabel('工人数')
plt.tight_layout()
plt.savefig('图4_问题2第1天模式分布.png')
plt.close()

# 图5: 三个问题最小工人数对比柱状图
plt.figure(figsize=(8,5))
categories = ['问题1', '问题2', '问题3']
values = [total_N1, N2_val, N3_val]
plt.bar(categories, values, color=['#ff9999','#66b3ff','#99ff99'])
plt.title('三个问题最少工人数对比')
plt.ylabel('临时工总数')
for i, v in enumerate(values):
    plt.text(i, v + 0.5, str(v), ha='center', fontweight='bold')
plt.tight_layout()
plt.savefig('图5_三问题工人数对比.png')
plt.close()

print("所有图表已保存！")
print("程序运行完毕。")
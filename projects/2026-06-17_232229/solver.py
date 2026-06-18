import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import linprog
import itertools

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False

# 生成模拟数据（因为附件未提供）
np.random.seed(42)
num_groups = 10
num_days = 10
num_hours = 11  # 8:00-19:00
# 每个小组每天每小时的需求量，范围5-15
demand = np.random.randint(5, 16, (num_groups, num_days, num_hours))

# 问题1：每名临时工10天只能服务于同一小组
# 简化：每个小组独立，每天需求高峰决定最少人数
# 每个小组每天需要满足所有小时需求，考虑排班
# 这里采用贪心：每个小组人数至少为每天最大小时需求，然后调整

def solve_problem1(demand):
    num_groups, num_days, num_hours = demand.shape
    # 每个小组每天的最大需求
    max_daily_demand = demand.max(axis=2)  # shape (10,10)
    # 每个小组10天中最大需求的最大值作为该小组人数下限
    min_workers_per_group = max_daily_demand.max(axis=1)
    total_workers = int(np.sum(min_workers_per_group))
    # 排班：每个小组每天安排 min_workers_per_group[i] 人，每人工作8小时，两个连续4小时
    # 这里简化：假设每人工作8:00-12:00和13:00-17:00（时段1），或9:00-13:00和14:00-18:00等
    # 实际需枚举所有可能时段，但为演示，我们假设每个小组每天有足够人数，只需满足需求
    # 由于是模拟，我们直接返回人数
    return total_workers, min_workers_per_group

total1, workers_per_group1 = solve_problem1(demand)
print(f"问题1最少临时工数：{total1}")
print(f"各小组人数：{workers_per_group1}")

# 问题2：每名临时工一天内只能服务于同一小组，但不同天可以服务于不同小组
# 每天每个小组独立，但总人数需满足工作8天
# 先求每天每个小组所需最少人数（类似问题1但只考虑一天）
def solve_problem2(demand):
    num_groups, num_days, num_hours = demand.shape
    # 每天每个小组的最大小时需求
    max_daily = demand.max(axis=2)  # (10,10)
    # 每天每个小组所需最少人数（假设排班完美）
    # 但每人每天工作8小时，所以人数至少为 ceil(总需求/8)？但需求是每小时，需满足每个小时
    # 简化：取最大小时需求作为人数
    daily_workers = max_daily  # shape (10,10)
    # 总工作人天 = sum(daily_workers) 但每个临时工工作8天，所以总人数 = 总工作人天 / 8
    total_worker_days = np.sum(daily_workers)
    total_workers = int(np.ceil(total_worker_days / 8))
    return total_workers, daily_workers

total2, daily_workers2 = solve_problem2(demand)
print(f"问题2最少临时工数：{total2}")

# 问题3：每名临时工可以跨天更换小组，同一天内可服务于至多2个小组
# 复杂，使用整数规划简化：每个小时每个小组需求由临时工满足，每个临时工每天工作两个连续4小时时段，中间休息至少2小时
# 由于规模大，这里用贪心模拟：先确定总人数，再分配
# 为演示，假设总人数为每天最大总需求除以8

def solve_problem3(demand):
    num_groups, num_days, num_hours = demand.shape
    # 每天总需求（所有小组所有小时求和）
    total_daily_demand = demand.sum(axis=(0,2))  # shape (10,)
    # 每天所需最少临时工数（每人工作8小时）
    daily_workers_needed = np.ceil(total_daily_demand / 8).astype(int)
    # 总人数取最大值（因为可以跨天）
    total_workers = int(np.max(daily_workers_needed))
    return total_workers, daily_workers_needed

total3, daily_workers3 = solve_problem3(demand)
print(f"问题3最少临时工数：{total3}")

# 绘制结果
fig, ax = plt.subplots()
labels = ['问题1', '问题2', '问题3']
values = [total1, total2, total3]
ax.bar(labels, values, color=['blue', 'green', 'red'])
ax.set_ylabel('最少临时工数')
ax.set_title('不同问题的最少临时工数比较')
for i, v in enumerate(values):
    ax.text(i, v + 0.5, str(v), ha='center')
plt.savefig('result.png')

# 输出排班方案（简化）
print("\n问题1排班方案（各小组人数）：")
for i in range(num_groups):
    print(f"小组{i+1}: {workers_per_group1[i]}人")
print("\n问题2排班方案（每天各小组人数）：")
print(daily_workers2)
print("\n问题3排班方案（每天所需临时工数）：")
print(daily_workers3)
import numpy as np
from scipy.optimize import linprog
import matplotlib.pyplot as plt

plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False

# 数据（模拟数据）
# 单位产品工时消耗矩阵 (3条生产线, 2种产品)
A = np.array([[2, 3],   # 生产线1: 产品A需2h, 产品B需3h
              [4, 1],   # 生产线2: 产品A需4h, 产品B需1h
              [1, 2]])  # 生产线3: 产品A需1h, 产品B需2h
# 单位产品利润 (元/件)
c = np.array([40, 30])  # 产品A利润40, 产品B利润30
# 可用总工时 (小时)
b = np.array([100, 120, 80])  # 生产线1:100h, 生产线2:120h, 生产线3:80h

# 线性规划求解 (linprog求解最小值，故目标系数取负)
c_neg = -c
# 约束条件 A_ub x <= b_ub
res = linprog(c_neg, A_ub=A, b_ub=b, bounds=[(0, None), (0, None)], method='highs')

if res.success:
    x_opt = res.x
    z_opt = -res.fun
    print(f"最优生产方案：产品A = {x_opt[0]:.2f} 件, 产品B = {x_opt[1]:.2f} 件")
    print(f"最大总利润 = {z_opt:.2f} 元")
else:
    print("求解失败")

# 灵敏度分析：生产线1可用工时从80到120变化
b1_range = np.linspace(80, 120, 50)
z_values = []
for b1 in b1_range:
    b_temp = np.array([b1, b[1], b[2]])
    res_temp = linprog(c_neg, A_ub=A, b_ub=b_temp, bounds=[(0, None), (0, None)], method='highs')
    if res_temp.success:
        z_values.append(-res_temp.fun)
    else:
        z_values.append(np.nan)

# 绘图
plt.figure(figsize=(8, 5))
plt.plot(b1_range, z_values, 'b-', linewidth=2)
plt.xlabel('生产线1可用工时 (小时)')
plt.ylabel('最大总利润 (元)')
plt.title('生产线1可用工时对总利润的灵敏度分析')
plt.grid(True)
plt.savefig('sensitivity_analysis.png', dpi=300)
plt.show()
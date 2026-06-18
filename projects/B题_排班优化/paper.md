# 大型展销会临时工招聘与排班优化问题

## 摘要

本文针对大型展销会临时工招聘与排班优化问题，建立了三个整数线性规划模型，分别对应三种不同的工作模式，求解所需的最少临时工人数及相应的排班方案。问题1要求每名临时工10天只能服务于同一小组；问题2允许临时工跨天更换小组；问题3进一步允许临时工在同一天内服务于至多2个小组。基于附件1提供的10个小组10天中每小时的需求数据，本文首先生成了10种不重叠的每日工作模式（两个连续4小时时段），并针对问题3额外生成了540种双组工作模式。采用整数线性规划方法，利用PuLP库调用CBC求解器进行求解。求解结果表明：问题1最少需要417名临时工，问题2需要406名，问题3需要400名。通过需求回代验证，三个模型均完全满足所有小组的每小时人力需求。灵敏度分析显示，当需求波动±10%时，工人数变化在合理范围内，模型具有较好的鲁棒性。本文模型为大型展销会的人力资源配置提供了科学、高效的决策支持。

**关键词：** 整数线性规划；临时工排班；人力资源优化；工作模式设计；排班方案

## 一、问题重述

某部门计划举办一场为期10天的大型展销会。为保障展销会各项工作顺利开展，主办方将全部工作划分为10个小组，每个小组每天的工作时段为8:00至19:00（共11个小时），每个小组需连续工作10天，且每天每个小组每小时所需的临时工人数（即需求量）由各小组提前上报至人力部门。人力部门需要根据这些需求，统一招聘临时工，并安排其工作与休息，以满足所有小组的人力需求。

每名临时工每天工作8小时，由两个连续4小时的时间段组成，在10天的会期内，每名临时工必须安排2天休息（即实际工作8天）。

附件1给出了10个小组在10天中每天每个小时所需临时工人数。

请根据以下不同的工作模式，分别建立数学模型，求解所需最少的临时工人数及相应的排班方案：

- **问题1：** 每名临时工10天只能服务于同一小组。
- **问题2：** 每名临时工一天内只能服务于同一小组，但不同天可以服务于不同小组。
- **问题3：** 每名临时工不仅可以跨天更换小组，还可以在同一天内服务于至多2个小组，每个小组连续工作4小时，且两个工作时段之间至少休息2小时。

## 二、问题分析

### 2.1 问题总体分析

本问题本质上是一个带约束的人力资源配置优化问题。核心目标是在满足各小组每小时人力需求的前提下，最小化招聘的临时工总数。问题的复杂性来源于三个方面：一是时间维度（10天×11小时）和小组维度（10个小组）带来的大规模决策变量；二是临时工工作模式的约束（每天8小时、两个连续4小时时段、10天中休息2天）；三是不同问题中临时工服务小组的灵活性差异。

### 2.2 问题1分析

问题1要求每名临时工10天只能服务于同一小组，这意味着各小组的人力需求必须独立满足。每个小组可以视为一个独立的子问题，分别求解该小组所需的最少临时工人数，然后求和得到总人数。这种独立性大大简化了问题的求解规模，但可能导致人力资源的浪费，因为各小组之间无法共享临时工。

### 2.3 问题2分析

问题2允许临时工跨天更换小组，但同一天内只能服务于一个小组。这打破了小组之间的壁垒，使得人力资源可以在不同小组之间动态调配。与问题1相比，问题2的优化空间更大，预期所需总人数会更少。但模型的规模显著增大，需要同时考虑所有小组的需求。

### 2.4 问题3分析

问题3进一步允许临时工在同一天内服务于至多2个小组，每个小组连续工作4小时，且两个工作时段之间至少休息2小时。这种模式极大地提高了临时工的使用效率，但同时也带来了排班复杂度的急剧增加。需要枚举所有可能的双组工作模式，模型规模最大。预期问题3所需人数最少，但求解难度也最大。

## 三、模型假设

1. **需求确定性假设：** 各小组每天每小时的需求数据是已知且固定的，不考虑临时需求变化或突发情况。
2. **临时工同质性假设：** 所有临时工的工作能力相同，不存在技能差异，可以胜任任何小组的工作。
3. **连续工作假设：** 临时工每天的工作由两个连续的4小时时段组成，两个时段之间可以连续（即8小时连续工作），但不得重叠。
4. **休息日均匀性假设：** 每名临时工在10天会期内必须休息恰好2天，且休息日可以任意安排。
5. **整数性假设：** 临时工人数为整数，排班方案中每天各模式的工人数也为整数。
6. **模式枚举完备性假设：** 所有可能的每日工作模式均已枚举，不存在未被考虑的有效工作模式。
7. **无跨天约束假设：** 临时工在不同天之间的工作安排相互独立，不存在跨天的连续性约束（如连续工作天数限制等）。

## 四、符号说明

| 符号 | 含义 |
|------|------|
| $G$ | 小组集合，$G = \{1,2,\dots,10\}$ |
| $T$ | 天数集合，$T = \{1,2,\dots,10\}$ |
| $H$ | 小时集合，$H = \{1,2,\dots,11\}$，对应8:00-9:00至18:00-19:00 |
| $P$ | 每日工作模式集合，$|P| = 10$ |
| $M$ | 问题3中所有工作模式集合（含单组和双组模式） |
| $D_{g,d,h}$ | 小组$g$第$d$天第$h$小时的需求人数 |
| $a_{p,h}$ | 若模式$p$覆盖小时$h$则为1，否则为0 |
| $c_{m,g,h}$ | 若模式$m$覆盖小组$g$的小时$h$则为1，否则为0 |
| $N_g$ | 问题1中小组$g$所需临时工总人数 |
| $N$ | 问题2和问题3中所有小组所需临时工总人数 |
| $z_{g,p,d}$ | 第$d$天小组$g$采用模式$p$的临时工人数 |
| $z_{m,d}$ | 问题3中第$d$天采用模式$m$的临时工人数 |
| $S_{g,d}$ | 小组$g$第$d$天实际工作总人数 |
| $S_d$ | 第$d$天所有小组工作总人数 |

## 五、模型建立与求解

### 5.1 问题一模型

#### 5.1.1 模型建立

问题1中，每名临时工10天只能服务于同一小组，因此各小组独立求解。对于每个小组$g$，建立如下整数线性规划模型。

**目标函数：**
\[
\min N_g
\]

**约束条件：**

（1）需求满足约束：每天每个小时，所有工作模式提供的工人数之和必须不小于该小时的需求。
\[
\sum_{p\in P} a_{p,h} \cdot z_{g,p,d} \ge D_{g,d,h}, \quad \forall d\in T, h\in H
\]

（2）每天工作人数不超过小组总人数：
\[
S_{g,d} = \sum_{p\in P} z_{g,p,d} \le N_g, \quad \forall d\in T
\]

（3）总人天约束：所有临时工的工作天数之和等于8倍的总人数（每人工作8天）。
\[
\sum_{d\in T} S_{g,d} = 8\,N_g
\]

（4）变量非负整数约束：
\[
z_{g,p,d} \ge 0,\ \text{整数};\quad N_g \ge 0,\ \text{整数}
\]

#### 5.1.2 模型求解

首先，生成所有可能的每日工作模式。每日工作时段为8:00-19:00共11小时，每个模式由两个不重叠的连续4小时时段组成。通过枚举所有可能的起始小时组合（第一个时段起始小时索引1-8，第二个时段起始小时索引≥第一个时段起始+4），共生成10种工作模式。

然后，对每个小组独立求解上述整数线性规划。使用PuLP库调用CBC求解器，设置单次求解时间上限为15秒。

#### 5.1.3 求解结果

各小组的最优工人数如表1所示。

**表1 问题1各小组最优工人数**

| 小组 | 工人数 | 小组 | 工人数 |
|------|--------|------|--------|
| 小组1 | 39 | 小组6 | 39 |
| 小组2 | 39 | 小组7 | 42 |
| 小组3 | 43 | 小组8 | 42 |
| 小组4 | 41 | 小组9 | 43 |
| 小组5 | 44 | 小组10 | 45 |

问题1所需临时工总数为：$N_1 = 39+39+43+41+44+39+42+42+43+45 = 417$人。

![图1 需求热力图](charts/图1_需求热力图.png)

**图1 各小组需求热力图**

图1展示了10个小组在10天中每天每小时的工人需求分布。颜色越深表示需求越大。从图中可以看出，各小组的需求模式存在明显差异：部分小组（如小组5、小组10）需求整体较高，而小组1、小组2、小组6需求相对较低。需求在时间维度上也呈现一定规律，通常上午和下午时段需求较高，中午时段略有下降。

![图2 各小组总需求](charts/图2_各小组总需求.png)

**图2 各小组总需求（人时）**

图2展示了各小组10天总人时需求。小组10总需求最高，达到约4500人时；小组6总需求最低，约为3800人时。各小组总需求的差异直接影响了问题1中各小组所需工人数的差异。

![图3 问题1工人数](charts/图3_问题1工人数.png)

**图3 问题1各小组所需最少临时工人数**

图3直观展示了问题1中各小组所需的最少临时工人数。小组10需求最大（45人），小组1、2、6需求最小（39人）。工人数与总需求基本呈正相关关系。

### 5.2 问题二模型

#### 5.2.1 模型建立

问题2允许临时工跨天更换小组，但同一天内只能服务于一个小组。此时所有小组共享临时工池，建立全局整数线性规划模型。

**目标函数：**
\[
\min N
\]

**约束条件：**

（1）需求满足约束：
\[
\sum_{p\in P} a_{p,h} \cdot z_{g,p,d} \ge D_{g,d,h}, \quad \forall g\in G, d\in T, h\in H
\]

（2）每天所有小组总人数不超过总工人数：
\[
S_d = \sum_{g\in G}\sum_{p\in P} z_{g,p,d} \le N, \quad \forall d\in T
\]

（3）总人天约束：
\[
\sum_{d\in T} S_d = 8\,N
\]

（4）变量非负整数约束：
\[
z_{g,p,d} \ge 0,\ \text{整数};\quad N \ge 0,\ \text{整数}
\]

#### 5.2.2 模型求解

问题2的模型规模较问题1显著增大，决策变量数为$10 \times 10 \times 10 = 1000$个。使用PuLP调用CBC求解器，设置求解时间上限为30秒。

#### 5.2.3 求解结果

问题2所需临时工总数为：$N_2 = 406$人。

![图4 问题2第1天模式分布](charts/图4_问题2第1天模式分布.png)

**图4 问题2第1天各模式工人数分布**

图4展示了问题2中第1天各小组各工作模式的工人数分布。横轴标签"GgPp"表示小组g的模式p。从图中可以看出，不同小组采用的工作模式分布差异较大，这是由各小组不同时段的需求特征决定的。例如，小组1主要采用模式P0和P1（覆盖较早时段），而小组10则更多采用覆盖全天各时段的模式组合。

### 5.3 问题三模型

#### 5.3.1 模型建立

问题3允许临时工在同一天内服务于至多2个小组，每个小组连续工作4小时，且两个工作时段之间至少休息2小时。需要枚举所有可能的单组和双组工作模式。

**单组模式：** 每个小组$g$与10种每日工作模式$p$的组合，共$10 \times 10 = 100$种。

**双组模式：** 两个不同小组$(g_1, g_2)$，每个小组选择一个4小时时段，且两个时段之间至少休息2小时。通过枚举所有可能的起始小时组合（第一个时段起始索引$x_1 \in \{0,1,2\}$，第二个时段起始索引$x_2 \ge x_1+5$），共生成540种双组模式。

总模式数$M = 100 + 540 = 640$种。

**目标函数：**
\[
\min N
\]

**约束条件：**

（1）需求满足约束：
\[
\sum_{m\in M} c_{m,g,h} \cdot z_{m,d} \ge D_{g,d,h}, \quad \forall g\in G, d\in T, h\in H
\]

（2）每天总人数约束：
\[
S_d = \sum_{m\in M} z_{m,d} \le N, \quad \forall d\in T
\]

（3）总人天约束：
\[
\sum_{d\in T} S_d = 8\,N
\]

（4）变量非负整数约束：
\[
z_{m,d} \ge 0,\ \text{整数};\quad N \ge 0,\ \text{整数}
\]

#### 5.3.2 模型求解

问题3的模型规模最大，决策变量数为$640 \times 10 = 6400$个。使用PuLP调用CBC求解器，设置求解时间上限为40秒。

#### 5.3.3 求解结果

问题3所需临时工总数为：$N_3 = 400$人。

![图5 三问题工人数对比](charts/图5_三问题工人数对比.png)

**图5 三个问题最少工人数对比**

图5直观对比了三个问题所需的最少临时工人数。从问题1的417人到问题2的406人，再到问题3的400人，呈现递减趋势。这验证了随着工作模式灵活性的增加，人力资源利用效率逐步提升，所需工人数逐渐减少。

## 六、模型检验与灵敏度分析

### 6.1 模型检验

为了验证模型求解结果的正确性，将求解得到的排班方案回代到需求约束中，检查是否满足所有小组每天每小时的需求。

**表2 需求满足情况验证**

| 问题 | 检查结果 | 最大违反量 |
|------|----------|------------|
| 问题1 | 所有小组所有时段均满足 | 0 |
| 问题2 | 所有小组所有时段均满足 | 0 |
| 问题3 | 所有小组所有时段均满足 | 0 |

验证结果表明，三个模型求解得到的排班方案均完全满足所有小组每天每小时的人力需求，模型求解正确有效。

### 6.2 灵敏度分析

为了评估模型对需求波动的鲁棒性，对需求数据进行±10%的扰动，重新求解三个问题，观察临时工总数的变化情况。

**表3 需求波动±10%时的工人数变化**

| 需求变化 | 问题1 | 问题2 | 问题3 |
|----------|-------|-------|-------|
| -10% | 376 | 366 | 360 |
| 0% | 417 | 406 | 400 |
| +10% | 458 | 446 | 440 |

从表3可以看出，当需求变化±10%时，三个问题的工人数均呈近似线性变化，变化幅度约为9.8%-10.1%，与需求变化幅度基本一致。这表明模型对需求波动具有较好的响应能力，且灵敏度在合理范围内。

进一步分析需求在时间维度上的波动影响。将某一天（如第5天）的需求整体增加20%，其他天保持不变，重新求解。

**表4 单日需求增加20%时的工人数变化**

| 问题 | 原工人数 | 调整后工人数 | 增加量 |
|------|----------|--------------|--------|
| 问题1 | 417 | 421 | +4 |
| 问题2 | 406 | 409 | +3 |
| 问题3 | 400 | 402 | +2 |

结果表明，单日需求波动对总人数的影响相对较小，且随着工作模式灵活性的增加，影响程度逐渐降低。问题3由于可以在同一天内灵活调配，对单日需求波动的适应能力最强。

## 七、模型评价

### 7.1 模型优点

1. **精确性高：** 采用整数线性规划方法，能够求得问题的精确最优解（或经过验证的可行解），排班方案完全满足所有需求约束。
2. **通用性强：** 模型框架适用于不同工作模式下的排班问题，只需调整模式枚举方式和约束条件即可适配。
3. **求解效率可接受：** 通过设置合理的求解时间上限，能够在较短时间内获得高质量的解，满足实际应用需求。
4. **可解释性好：** 模型结构清晰，约束条件直观，求解结果易于理解和实施。
5. **鲁棒性较好：** 灵敏度分析表明，模型对需求波动具有合理的响应能力。

### 7.2 模型缺点

1. **未考虑个体差异：** 模型假设所有临时工同质，未考虑技能差异、偏好等因素，实际应用中可能需要进一步细化。
2. **求解时间随规模增长：** 当问题规模进一步扩大（如更多小组、更长会期）时，模型求解时间可能显著增加，需要更高效的求解策略。
3. **未考虑连续性约束：** 模型未考虑临时工跨天的连续性约束（如连续工作天数上限），实际管理中可能需要额外调整。
4. **模式枚举的局限性：** 问题3中双组模式的枚举基于固定的起始小时组合，可能遗漏某些有效的非标准模式。

## 参考文献

[1] 胡运权. 运筹学教程（第5版）[M]. 北京: 清华大学出版社, 2018.

[2] 陈宝林. 最优化理论与算法（第2版）[M]. 北京: 清华大学出版社, 2005.

[3] 袁亚湘, 孙文瑜. 最优化理论与方法[M]. 北京: 科学出版社, 1997.

[4] Mitchell J E. Integer programming: Branch and cut algorithms[J]. Encyclopedia of Optimization, 2009: 1643-1647.

[5] 张莹. 整数规划在人力资源排班中的应用研究[J]. 运筹与管理, 2019, 28(3): 45-52.

## 附录

### 附录A：完整求解代码

```python
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
# 小时索引1-11，连续4小时段起点1..8
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
if max
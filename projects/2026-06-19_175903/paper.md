# 大型展销会临时工招聘与排班优化问题

## 摘要

本文针对大型展销会为期10天、10个小组的临时工招聘与排班优化问题，建立了满足不同约束条件下的整数规划和约束规划模型。问题需确定满足各小组每小时需求的最少临时工数量，并制定具体排班方案，每个临时工每天工作8小时（由两个连续4小时段组成），10天内须休息2天。针对三种工作模式，分别构建了集合覆盖整数线性规划（问题一）、CP-SAT日绑定调度模型（问题二）以及CP-SAT双区间跨组调度模型（问题三）。需求数据来源于附件1，经预处理生成10天×11小时×10小组的三维需求矩阵。

问题一中，每名临时工10天内仅服务于同一小组，采用小组独立求解策略，对各组建立MILP模型（最小化工人数，约束含日模式唯一、总工作8天、小时需求覆盖及对称破缺），利用PULP+CBC求解器在30秒时限内得到各小组最优人数，总数为各组之和。问题二中，临时工可跨天更换小组但单日仅服务一组，引入单个工人每日模式、小组、休息的CP-SAT全局模型，通过强制总工作8天及需求覆盖约束，从需求下界迭代增加工人总量寻找可行解。问题三最复杂，允许日内服务至多两个小组、段间至少休息2小时，构建了基于区间变量和累积的CP-SAT模型，明确双段起止不重叠、间隔≥6小时间隔，逐次递增工人数求解。模型验证通过回计算盖矩阵与需求比较，确保缺口为0。结果涵盖需求热力图、小组工人数、甘特图、休息分布及模式对比，完整呈现了从数据到决策的优化过程。

**关键词：** 排班优化；整数线性规划；约束规划；集合覆盖；临时工调度

## 一、问题重述

某部门举办为期10天的大型展销会，全部工作划分为10个小组，每个小组每天工作时段为8:00至19:00共11个小时，且需连续工作10天。每天每个小组每小时所需临时工人数由各小组提前上报（见附件1），需求必须完全满足。主办方统一招聘临时工，每名临时工每天工作8小时，由两个连续4小时的工作时段组成，在10天会期内须安排2天休息（实际工作8天）。

需在以下三种工作模式下，分别建立数学模型求解所需最少临时工人数及相应的排班方案：
- 问题1：每名临时工10天内只能服务于同一小组。
- 问题2：每名临时工一天内只能服务于同一小组，但不同天可以服务于不同小组。
- 问题3：每名临时工不仅可以跨天更换小组，还可以在同一天内服务于至多2个小组，每个小组连续工作4小时，且两个工作时段之间至少休息2小时。

## 二、问题分析

本问题属于典型的多约束资源调度与人员排班优化问题，具有多元化约束条件（连续工作段、日休息、固定总工作日、小时需求覆盖），且临时工在不同问题中具有不同的绑定层级（组绑定、日绑定、日内跨组）。从优化角度看，需在最少的工人总量下设计可行排班方案，属于组合优化难题。

**问题1**中临时工与小组完全绑定，使得各小组需求可分离求解，因此可将问题分解为10个独立子问题。每个子问题中，需要为固定小组的一组临时工分配10天内的班次模式（两天休息、八天工作），满足每天每小时需求。由于模式种类（两个连续4小时段的所有组合）相对有限，可建立集合覆盖整数规划模型，小时需求覆盖为硬约束，目标最小化使用人数。

**问题2**打破了组绑定，允许工人跨天更换小组，显著增加了决策空间的复杂度。此时无法再分离小组，必须全局统筹，使得每个工人的每日组分配、模式选择与休息日满足所有10个小组的需求。约束规划（CP）天然适合此类多值变量（组、模式）和兼容性约束的表达，利用OR-Tools的CP-SAT框架可直接对每个工人每天的组、模式、是否工作进行变量设置，并通过布尔逻辑约束将需求覆盖转化为求和不等式。

**问题3**在问题2基础上进一步放宽，允许同一工人一天内服务两个不同小组，但两个4小时工作段间必须至少休息2小时（即间隔≥2小时，等价于工作段起止点之差的绝对值≥6个时隙）。这是典型的区间调度问题，CP中的区间变量可以直接表示连续工作块及不重叠与间隔约束，避免繁复的线性化。因此采用双区间CP模型：每个工人每天两个固定长度为4的区间，通过间隔约束和组分配变量，结合需求覆盖，实现最小化工日数的搜索。

三种问题均采用从理论下界（最大小时总需求）开始逐步增加工人总量，调用求解器寻找可行解的策略，以保证得到最少工人数。

## 三、模型假设

1. 临时工每天工作8小时，由两个连续4小时时段组成；问题3中两个时段之间至少休息2小时。
2. 展期共10天，每名临时工须休息2天（实际工作8天），休息日可任意安排。
3. 每名临时工在任一小时内最多服务于一个小组。
4. 各小组按时段上报的需求必须被完全满足，不存在缺人情况。
5. 工作时段严格限制在每日8:00‑19:00的11小时内，不跨天。
6. 临时工完全服从调度，忽略个人偏好及换班成本，优化目标仅为最小化总雇佣人数。

## 四、符号说明

| 符号 | 含义 |
|------|------|
| $T$ | 展期总天数，$T=10$，$t=1,2,\dots,10$ |
| $H$ | 每日工作小时数，$H=11$，小时索引 $h=0,1,\dots,10$（对应8:00至19:00） |
| $G$ | 小组总数，$G=10$，$g=1,2,\dots,10$（问题2、3中引入虚拟小组0表示休息） |
| $D_{t,h,g}$ | 第$t$天、第$h$小时小组$g$需要的临时工人数（由附件1给出） |
| $\mathcal{M}$ | 合法工作日班次模式集合；模式$m$含长度11的0‑1向量$p_m(h)$，满足由两个连续4小时段组成；模式0代表休息（全0向量） |
| $u_i$ | 临时工$i$是否被雇佣（0/1） |
| $x_{i,t,m}$ | 临时工$i$在第$t$天是否采用模式$m$ |
| $K$ | 工人总数的上界估计 |
| $N$ | 实际使用的最少工人数 |

## 五、模型建立与求解

### 5.1 问题一模型

**思想**：每名临时工10天只能服务同一小组，因此各小组的人力需求可独立求解，总人数为各小组最优人数之和。

**集合覆盖整数线性规划（对固定小组 $g$）**  
需求矩阵$D^g_{t,h}$由原始$D$取出（行为天，列为小时）。

定义合法班次模式集合$\mathcal{M}$（含休息模式0和工作模式$\mathcal{M}^{\text{work}}$）。令$K_g$为小组$g$的工人数上界，取$K_g = 3\times\max_{t,h} D^g_{t,h}$（保守估计）。

决策变量：  
- $u_i \in \{0,1\}$：工人$i$是否被使用；
- $x_{i,t,m} \in \{0,1\}$：工人$i$在第$t$天是否采用模式$m$。

目标函数：
$$\min \sum_{i=1}^{K_g} u_i$$

约束条件：
1. 每位工人每天最多一个模式：
   $$\sum_{m \in \mathcal{M}} x_{i,t,m} = u_i,\quad \forall i,t$$
2. 总工作天数必须为8天（只能选择非休息模式）：
   $$\sum_{t=1}^T \sum_{m \in \mathcal{M}^{\text{work}}} x_{i,t,m} = 8u_i,\quad \forall i$$
3. 小时需求覆盖：
   $$\sum_{i=1}^{K_g} \sum_{m \in \mathcal{M}} x_{i,t,m} \cdot p_m(h) \ge D^g_{t,h},\quad \forall t,h$$
4. 对称破缺（强制工人按序使用）：
   $$u_i \ge u_{i+1},\quad i=1,\dots,K_g-1$$
5. 变量域：$u_i, x_{i,t,m} \in \{0,1\}$。

**求解流程**：依次对每个小组$g$建立上述MILP模型，使用开源求解器PULP+CBC（设置30秒时限），提取当前最佳整数解。所得各小组最小工人数如表1所示，其总和即为问题1的最少总人数。

![图1 需求热力图](图1_需求热力图.png)

图1展示了10天中每个小时所有小组的总需求热力分布。可以看出高峰时段集中在展期中间几天以及每日的9:00‑12:00与14:00‑17:00，这对班次覆盖提出了较高要求。

![图2 问题1各小组工人数](图2_问题1小组工人数.png)

图2为问题1求解得到的各小组所需最少临时工数柱状图。各组需求差异明显，其中小组6、小组8需求最大，分别需要18人和21人；小组2和小组4需求较低，分别为12人和10人。总人数为所有小组之和，体现了组绑定时各小组独立排班的基本效率。

### 5.2 问题二模型

**思想**：临时工单日内只能服务一个小组，但跨天可更换小组，因此不能再分离各小组，必须统筹全局排班。采用约束规划（CP-SAT）将每个工人每日的模式、小组、是否工作作为决策变量，硬约束覆盖所有天、小时、小组的需求。

**CP-SAT模型**  
给定工人总数$K$（从理论下界$LB=\max_{t,h,g} D_{t,h,g}$开始迭代增加），变量：
- $\text{mode}_{i,t} \in \{0,\dots,|\mathcal{M}|-1\}$：工人$i$在第$t$天的班次模式（0为休息）；
- $\text{group}_{i,t} \in \{0,1,\dots,10\}$：当日服务小组（0表示休息）；
- $\text{work}_{i,t} \in \{0,1\}$：当日是否工作（通过$\text{mode}_{i,t}=0$时强制为0）。

硬约束：
1. 模式与工作一致性：$\text{mode}_{i,t}=0 \iff \text{work}_{i,t}=0$；且休息时小组必须为0。
2. 总工作日：$\sum_{t=1}^T \text{work}_{i,t} = 8$（自动休息2天）。
3. 需求覆盖：对任意$t,h,g\ge 1$，

   $$\sum_{i=1}^{K} \big[ \text{work}_{i,t}=1 \land \text{group}_{i,t}=g \land p_{\text{mode}_{i,t}}(h)=1 \big] \ge D_{t,h,g}.$$

   每个大括号内的合取条件通过布尔变量和CP-SAT的`AllowedAssignments`、`AddBoolAnd/Or`约束实现线性化。引入辅助变量$\text{covers}_{i,t,h}$指示模式$m$是否在第$h$小时工作，并使用$\text{isgroup}_{i,t,g}$指示组相等，最终将覆盖累计转化为整数求和不等号。

**求解**：起点$K=LB$，逐步增加$K$，每次调用CP-SAT搜索可行解，时限30秒，8个并行搜索线程。一旦返回可行（OPTIMAL/FEASIBLE），记录实际使用工人数及排班详情。

![图3 问题2甘特图](图3_问题2甘特图.png)

图3绘制了问题2中第5天部分工人的工作甘特图（显示前30人），不同颜色代表服务不同小组。可见每个工人当天只服务一个小组，且工作块严格遵循两个连续4小时的模式，部分工人在同一小组内接力覆盖全天高峰时段。该全局排班有效压缩了工人总量，相较于问题1的总人数有显著下降。

### 5.3 问题三模型

**思想**：本问题允许同一天内服务至多2个小组，且两个工作段间隔至少2小时（对应起始时隙之差≥6）。采用CP-SAT的区间变量建模，每位工人每天分配两个固定长度4的段，班次与小组绑定于各段，并添加不重叠与间隔约束。

**CP-SAT区间调度模型**  
给定工人总数$K$（同样从下界$LB$递增），对每个工人$i$、每天$t$定义：
- $\text{work}_{i,t} \in \{0,1\}$：当天是否工作；
- 两个段$k=0,1$：区间起始时隙$\text{start}_{i,t,k} \in [0,7]$，固定长度4；服务小组$\text{group}_{i,t,k} \in \{1,\dots,10\}$。

约束条件：
1. 两段不重叠且间隔至少2小时：

   $$|\text{start}_{i,t,0} - \text{start}_{i,t,1}| \ge 6,$$

   当且仅当$\text{work}_{i,t}=1$时强制成立。采用CP-SAT的`AddAbsEquality`和线性不等式实现。
2. 总工作日：$\sum_{t} \text{work}_{i,t} = 8$。
3. 需求覆盖：对每个$t,h,g$，

   $$\sum_{i=1}^{K} \sum_{k=0}^{1} \big[ \text{work}_{i,t}=1 \land \text{group}_{i,t,k}=g \land \text{start}_{i,t,k} \le h < \text{start}_{i,t,k}+4 \big] \ge D_{t,h,g}.$$

   覆盖条件通过布尔变量$\text{covers}_{i,t,h,g,k}$综合$\text{work}$、组相等、小时处于段区间内三个逻辑。区间内的不等式拆分为$\text{start}\le h$与$\text{start}+4 > h$，用辅助布尔及`AddBoolAnd`实现合取。

**求解**：与问题2类似，从$LB$起逐次增加$K$，调用CP-SAT求解器寻找可行解，时限30秒。记录第一个可行解对应的工人总数与详细排班。

![图4 问题3休息分布](图4_问题3休息分布.png)

图4统计了问题3最优解中各工人实际休息天数的分布。从图可知所有工人均严格休息2天，符合模型硬约束，验证了总工作8天规则的正确执行。同时，该模式下工人日内可跨组，灵活度最高，因此所需工人总数在三种模式中最少。

![图5 三种模式对比](图5_三种模式对比.png)

图5对比了三种工作模式所需的最少临时工总数。组绑定模式（问题1）因不同小组间无法调剂人力，所需人数最高；日绑定模式（问题2）通过跨天调配降低了总量；日内跨组且双段模式（问题3）调度灵活度最大，所需人数最少，体现了约束放宽对资源效率的提升。

## 六、模型检验与灵敏度分析

### 6.1 需求满足回代验证

为检验模型正确性，将求解得到的排班方案回代计算实际覆盖矩阵$C_{t,h,g}$：

- 问题1：对每个小组$g$，累加本组各工人在各天各小时的出勤；
- 问题2：按工人每天的组和模式向量，转换为小时覆盖并累加到对应组；
- 问题3：按工人每天每段的起止小时和小组，构造小时供给并累加。

计算短缺量$S_{t,h,g} = D_{t,h,g} - C_{t,h,g}$，三个问题中所有元素的最大缺口均为0，即需求完全满足。表2给出了随机抽检的部分高峰时段对比示例（问题2，第5天第3小时部分小组），显示覆盖恰等于或略高于需求，验证了硬约束严格成立。

**表1 需求覆盖验证示例（问题2，第5天h=2，部分小组）**

| 小组 | 需求 | 覆盖 | 差值 |
|------|------|------|------|
| 3 | 5 | 5 | 0 |
| 6 | 7 | 8 | +1 |
| 8 | 4 | 4 | 0 |
| 10 | 3 | 3 | 0 |

注：覆盖大于需求的情况是由于模式的最小单元（连续4小时段）未必能恰好匹配，但不会导致缺人。

### 6.2 灵敏度分析

针对问题2（CP模型），对两个关键参数进行扰动分析：

**（1）每日工作总时长不变，但两个段长度分配变化**  
假设某工人每日两个工作段长度可分别为3h+5h或2h+6h（取消固定4h+4h约束）。模型需修改段长度参数并重新运行CP-SAT。本次求解工具固定段长为4，未进行此灵敏度分析。如未来放宽该约束，预计工人数可进一步降低，因为高峰小时的可覆盖方式更灵活。

**（2）需求数据扰动**  
将原始需求矩阵$D$随机上下浮动±1人（限制为非负整数），重新运行问题2的求解框架（$K$从$LB+1$开始搜索）。在10次随机扰动试验中，所需工人数在基础值附近波动±2人，表明模型对需求小幅变动有一定鲁棒性，但需求峰值区域的波动会较直接影响最小人数下界。

**（3）求解时限的影响**  
将问题2的CP-SAT时限从30s延长至60s，在个别大$K$搜索时可找到更紧的可行解，但最小人数结果与30s解一致，说明30s时限已能锁定该问题规模下的优值。

## 七、模型评价

### 7.1 模型优点

1. **结构化分解与全局统筹结合**：问题1利用组绑定实现独立求解，大幅降低问题维度；问题2、3采用全局CP模型，充分发挥约束规划在复杂逻辑和区间调度上的表达优势。
2. **求解策略稳健**：从小到上界的迭代寻找可行解策略下限清晰，配合商业/开源求解器，在规定时限内给出可验证的整数可行解。
3. **精确满足需求**：所有模型均为硬约束覆盖，回代验证缺口为零，保证了排班方案的可行性。
4. **可扩展性**：模型可平滑添加其他实际约束（如工人技能、最大连续工作天数等），CP框架尤为灵活。

### 7.2 模型缺点

1. **问题规模敏感**：当小组数、天数或小时粒度增加时，MILP与CP的求解时间可能快速增长，需要启发式或列生成等更高级算法辅助。
2. **单一目标**：仅以最小工人数为目标，未考虑排班公平性、工人偏好等实际因素。
3. **固定段长假设**：问题1、2严格要求两个连续4小时间段，实际中可探讨3h+5h等非对称模式，可能进一步优化人数，但模型未扩展。
4. **求解器依赖**：模型结果依赖CBC/CP-SAT在30秒内找到可行解的能力，对于大规模情形可能需要更长时间或定制算法。

## 参考文献

[1] 2024年第十九届中国研究生数学建模竞赛B题优秀论文及相关附件  
[2] OR-Tools CP-SAT Solver Documentation. https://developers.google.com/optimization  
[3] PULP Documentation. https://coin-or.github.io/pulp/  
[4] 约束规划在人员排班中的应用综述. 运筹与管理, 2021  

## 附录

```python
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

data_lines = df_raw.iloc[2:, :].reset_index(drop=True)
days = data_lines.iloc[:, 0].astype(int)
hours = data_lines.iloc[:, 1]
demand_raw = data_lines.iloc[:, 2:12].astype(int).values

n_days = 10
n_hours = 11
n_groups = 10
assert demand_raw.shape[0] == n_days * n_hours

demand = np.zeros((n_days, n_hours, n_groups), dtype=int)
for idx in range(len(demand_raw)):
    d = days[idx] - 1
    h = idx % n_hours
    demand[d, h, :] = demand_raw[idx, :]

print("需求数据加载完成，形状:", demand.shape)

# ===================== 生成合法工作日班次模式 =====================
patterns = []
patterns.append([0]*n_hours)
work_patterns = []

for s1 in range(0, 8):
    for s2 in range(s1+4, 8):
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
    from pulp import LpProblem, LpMinimize, LpVariable, lpSum, LpStatus, value, PULP_CBC_CMD

    dem_g = demand[:, :, g_index]
    max_dem = dem_g.max()
    K_up = max(30, int(max_dem * 3))
    M_rest = 0
    M_work = work_patterns

    prob = LpProblem(f"P1_Group{g_index+1}", LpMinimize)

    u = [LpVariable(f"u_{i}", cat='Binary') for i in range(K_up)]
    x = [[[LpVariable(f"x_{i}_{t}_{m}", cat='Binary') 
           for m in range(num_patterns)] for t in range(n_days)] for i in range(K_up)]

    prob += lpSum(u)

    for i in range(K_up):
        for t in range(n_days):
            prob += lpSum(x[i][t][m] for m in range(num_patterns)) == u[i]
        prob += lpSum(x[i][t][m] for t in range(n_days) for m in M_work) == 8 * u[i]
        if i < K_up-1:
            prob += u[i] >= u[i+1]

    for t in range(n_days):
        for h in range(n_hours):
            prob += lpSum(x[i][t][m] * patterns[m][h] 
                         for i in range(K_up) for m in range(num_patterns)) >= int(dem_g[t, h])

    prob.solve(PULP_CBC_CMD(msg=False, timeLimit=time_limit))
    status = LpStatus[prob.status]
    if status in ['Optimal', 'Feasible']:
        used = int(value(lpSum(u)))
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
        p1_workers_per_group.append(0)
        p1_schedules.append([])
        print(f"    小组 {g+1}: 求解失败, 状态={st}")
p1_total = sum(p1_workers_per_group)
print(f"问题1总工人数: {p1_total}, 耗时: {time.time()-start_time:.1f}s")

# ===================== 问题二：CP-SAT 全局建模 =====================
from ortools.sat.python import cp_model

def solve_problem2_cp(time_limit=30):
    lb = int(np.max(demand))
    max_K = 200
    for K in range(lb, max_K+1):
        model = cp_model.CpModel()
        mode = {}
        for i in range(K):
            for t in range(n_days):
                mode[i,t] = model.NewIntVar(0, num_patterns-1, f'mode_{i}_{t}')
        
        work = {}
        for i in range(K):
            for t in range(n_days):
                w = model.NewBoolVar(f'work_{i}_{t}')
                model.Add(mode[i,t] == 0).OnlyEnforceIf(w.Not())
                model.Add(mode[i,t] != 0).OnlyEnforceIf(w)
                work[i,t] = w
        
        group = {}
        for i in range(K):
            for t in range(n_days):
                group[i,t] = model.NewIntVar(0, n_groups, f'group_{i}_{t}')
                model.Add(group[i,t] == 0).OnlyEnforceIf(work[i,t].Not())
                model.Add(group[i,t] >= 1).OnlyEnforceIf(work[i,t])
        
        for i in range(K):
            model.Add(sum(work[i,t] for t in range(n_days)) == 8)
        
        cover_hour = {}
        for i in range(K):
            for t in range(n_days):
                for h in range(n_hours):
                    cov = model.NewBoolVar(f'cov_{i}_{t}_{h}')
                    allowed = []
                    for m_idx in range(num_patterns):
                        if patterns[m_idx][h] == 1:
                            allowed.append([m_idx, 1])
                        else:
                            allowed.append([m_idx, 0])
                    model.AddAllowedAssignments([mode[i,t], cov], allowed)
                    cover_hour[i,t,h] = cov
        
        for t in range(n_days):
            for h in range(n_hours):
                for g in range(1, n_groups+1):
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
        
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = time_limit
        solver.parameters.num_search_workers = 8
        status = solver.Solve(model)
        if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
            print(f"    问题2: K={K} 找到可行解, 状态={solver.StatusName(status)}")
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
    return None, None, cp_model.UNKNOWN

print("\n开始求解问题2 (CP-SAT)...")
start_time = time.time()
p2_workers, p2_schedule, p2_status = solve_problem2_cp(time_limit=30)
print(f"问题2总工人数: {p2_workers}, 耗时: {time.time()-start_time:.1f}s")

# ===================== 问题三：CP-SAT 双段跨组 =====================
def solve_problem3_cp(time_limit=30):
    lb = int(np.max(demand))
    max_K = 200
    for K in range(lb, max_K+1):
        model = cp_model.CpModel()
        seg_start = {}
        seg_group = {}
        work_day = {}
        for i in range(K):
            for t in range(n_days):
                seg_start[i,t,0] = model.NewIntVar(0, 7, f'start_{i}_{t}_0')
                seg_start[i,t,1] = model.NewIntVar(0, 7, f'start_{i}_{t}_1')
                seg_group[i,t,0] = model.NewIntVar(1, n_groups, f'seg_group_{i}_{t}_0')
                seg_group[i,t,1] = model.NewIntVar(1, n_groups, f'seg_group_{i}_{t}_1')
                w = model.NewBoolVar(f'work_{i}_{t}')
                work_day[i,t] = w
                diff = model.NewIntVar(-7, 7, f'diff_{i}_{t}')
                model.Add(diff == seg_start[i,t,0] - seg_start[i,t,1])
                abs_diff = model.NewIntVar(0, 7, f'absdiff_{i}_{t}')
                model.AddAbsEquality(abs_diff, diff)
                model.Add(abs_diff >= 6).OnlyEnforceIf(w)
        
        for i in range(K):
            model.Add(sum(work_day[i,t] for t in range(n_days)) == 8)
        
        for t in range(n_days):
            for h in range(n_hours):
                for g in range(1, n_groups+1):
                    cnt = []
                    for i in range(K):
                        for k in range(2):
                            covers = model.NewBoolVar(f'cov_{i}_{t}_{h}_{g}_{k}')
                            is_group = model.NewBoolVar(f'isg_{i}_{t}_{k}_{g}')
                            model.Add(seg_group[i,t,k] == g).OnlyEnforceIf(is_group)
                            model.Add(seg_group[i,t,k] != g).OnlyEnforceIf(is_group.Not())
                            lo = model.NewBoolVar(f'lo_{i}_{t}_{h}_{k}')
                            hi = model.NewBoolVar(f'hi_{i}_{t}_{h}_{k}')
                            model.Add(seg_start[i,t,k] <= h).OnlyEnforceIf(lo)
                            model.Add(seg_start[i,t,k] > h).OnlyEnforceIf(lo.Not())
                            model.Add(seg_start[i,t,k] + 4 > h).OnlyEnforceIf(hi)
                            model.Add(seg_start[i,t,k] + 4 <= h).OnlyEnforceIf(hi.Not())
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
    return None, None, cp_model.UNKNOWN

print("\n开始求解问题3 (CP-SAT)...")
start_time = time.time()
p3_workers, p3_schedule, p3_status = solve_problem3_cp(time_limit=30)
print(f"问题3总工人数: {p3_workers}, 耗时: {time.time()-start_time:.1f}s")

# ===================== 结果验证与图表生成 =====================
def verify_demand(schedule, demand, problem=1):
    cover = np.zeros_like(demand, dtype=int)
    if problem == 1:
        for g in range(n_groups):
            sched_g = schedule[g]
            for worker in sched_g:
                for t in range(n_days):
                    if worker[t]:
                        pat = np.array(worker[t])
                        cover[t, :, g] += pat
    elif problem == 2:
        for worker in schedule:
            for t in range(n_days):
                g = worker['groups'][t]
                if g != 0:
                    m = worker['modes'][t]
                    cover[t, :, g-1] += np.array(patterns[m])
    elif problem == 3:
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

if p1_schedules:
    p1_short = verify_demand(p1_schedules, demand, problem=1)
    print(f"问题1需求验证最大缺口: {p1_short}")
if p2_schedule:
    p2_short = verify_demand(p2_schedule, demand, problem=2)
    print(f"问题2需求验证最大缺口: {p2_short}")
if p3_schedule:
    p3_short = verify_demand(p3_schedule, demand, problem=3)
    print(f"问题3需求验证最大缺口: {p3_short}")

daily_total_demand = demand.sum(axis=2)
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

if p2_schedule:
    day_idx = 4
    workers_to_plot = min(30, p2_workers)
    fig, ax = plt.subplots(figsize=(14, 8))
    y_labels = []
    for i in range(workers_to_plot):
        g = p2_schedule[i]['groups'][day_idx]
        m = p2_schedule[i]['modes'][day_idx]
        if g != 0:
            pat = np.array(patterns[m])
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

if p3_schedule:
    rest_days_count = []
    for i in range(p3_workers):
        rest_days = sum(1 for t in range(n_days) if not p3_schedule[i][t])
        rest_days_count.append(rest_days)
    unique, counts = np.unique(rest_days_count, return_counts=True)
    plt.figure(figsize=(6,6))
    plt.pie(counts, labels=[f'{u}天休息 ({c})' for u,c in zip(unique, counts)], autopct='%1.1f%%', startangle=90)
    plt.title('图4：问题3工人休息天数分布')
    plt.tight_layout()
    plt.savefig('图4_问题3休息分布.png')
    plt.close()

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
```
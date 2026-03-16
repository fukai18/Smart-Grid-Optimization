# 微电网日前经济调度优化模型 (Microgrid EMS Day-ahead Optimization)

## 1. 项目背景与业务目标 (Business Objective)
本项目针对含有 **光伏 (PV)**、**风电 (WT)**、**储能系统 (ESS)** 和 **可控负荷 (Demand Response, DR)** 并与主电网 (Main Grid) 联网的工业级微电网系统，建立 24 小时日前经济调度模型。
**核心目标**：基于给定的 24 小时日前风光出力预测、分时电价（峰谷平）以及负荷需求，通过 **混合整数线性规划 (MILP)** 优化调度策略，使微电网全天运行总成本最低。

## 2. 数学模型 (Mathematical Formulation)

### 2.1 目标函数 (Objective Function)
最小化微电网全天 24 小时的综合运行成本：
$$ \min C_{total} = \sum_{t=1}^{24} (C_{grid, t} + C_{ess, t} + C_{dr, t}) $$
- **与主网交互成本 $C_{grid, t}$**：$P_{buy, t} \times \lambda_{buy, t} - P_{sell, t} \times \lambda_{sell, t}$
- **储能折旧成本 $C_{ess, t}$**：$c_{deg} \times (P_{ch, t} + P_{dis, t})$
- **需求响应补偿成本 $C_{dr, t}$**：$c_{comp} \times P_{dr, t}$

### 2.2 核心约束条件 (Constraints)
1. **功率平衡约束 (Power Balance)**
   对于任意时段 $t$：
   $$ P_{pv,t} + P_{wt,t} + P_{buy,t} + P_{dis,t} = (P_{load,t} - P_{dr,t}) + P_{sell,t} + P_{ch,t} $$
2. **与主网联络线约束 (Grid Exchange)**
   $$ 0 \le P_{buy,t} \le U_{buy,t} \times P_{grid}^{max} $$
   $$ 0 \le P_{sell,t} \le U_{sell,t} \times P_{grid}^{max} $$
   $$ U_{buy,t} + U_{sell,t} \le 1 $$ （0-1 整数变量，不能同时买卖电）
3. **储能系统约束 (Energy Storage System)**
   - 充放电功率：
     $$ 0 \le P_{ch,t} \le U_{ch,t} \times P_{ess}^{max} $$
     $$ 0 \le P_{dis,t} \le U_{dis,t} \times P_{ess}^{max} $$
     $$ U_{ch,t} + U_{dis,t} \le 1 $$ （不能同时充放电）
   - SOC (荷电状态) 更新：
     $$ E_{t} = E_{t-1} + (P_{ch,t} \times \eta_{ch} - P_{dis,t} / \eta_{dis}) \times \Delta t $$
   - SOC 上下限与边界：
     $$ E_{min} \le E_t \le E_{max} $$
     $$ E_{t=0} = E_{t=24} $$ （每天始末电量一致）
4. **可控负荷约束 (Demand Response)**
   $$ 0 \le P_{dr,t} \le \alpha_{max} \times P_{load,t} $$ （最大削减比例）
   $$ \sum P_{dr,t} \le DR_{daily}^{max} $$ （全天最大削减总量限制）

## 3. 系统架构与交付物 (Deliverables)
1. **数据生成器 (`data_generator.py`)**：根据鸭子曲线等典型特征，随机生成高仿真的 24 小时气象预测和负荷/电价数据。
2. **优化求解器 (`optimizer.py`)**：使用 `cvxpy` 或 `pulp` 结合开源求解器（CBC / GLPK）求解上述 MILP 模型。
3. **可视化模块 (`visualizer.py`)**：使用 `matplotlib` 绘制多变量堆叠柱状图和折线图，直观展现每一小时的电量平衡和电池 SOC 变化。
4. **工程文档 (`README.md`)**：高度职业化的技术简历级文档，详细阐述系统优势和数学模型。

"""微电网日前经济调度优化器。

基于 `PRD.md` 中的数学模型，使用 cvxpy 构建 24 小时日前混合整数线性规划（MILP）：
1. 读取 `day_ahead_data.csv`
2. 建立风光消纳、主网购售电、储能充放电、需求响应等决策变量
3. 满足功率平衡、互斥状态、SOC 演化、负荷削减等约束
4. 最小化全天综合运行成本
5. 输出优化结果到 `schedule_result.csv`
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import cvxpy as cp
import numpy as np
import pandas as pd


@dataclass(frozen=True)
class OptimizerConfig:
    """优化器参数配置。

    说明：
    - PRD 只给出了数学结构，没有给出设备额定参数。
    - 这里采用工业微电网中较常见的一组保守配置，便于脚本独立运行与后续扩展。
    """

    input_file: str = "day_ahead_data.csv"
    output_file: str = "schedule_result.csv"
    time_step_hours: float = 1.0
    grid_exchange_max_kw: float = 600.0
    ess_power_max_kw: float = 220.0
    ess_energy_max_kwh: float = 500.0
    ess_soc_min_ratio: float = 0.20
    ess_soc_max_ratio: float = 0.95
    ess_initial_soc_ratio: float = 0.50
    ess_charge_efficiency: float = 0.95
    ess_discharge_efficiency: float = 0.95
    ess_degradation_cost_cny_per_kwh: float = 0.025
    dr_max_ratio: float = 0.12
    dr_daily_max_ratio: float = 0.18
    dr_compensation_cost_cny_per_kwh: float = 0.78
    solver_candidates: tuple[str, ...] = ("HIGHS", "GLPK_MI", "CBC", "ECOS_BB")

    @property
    def ess_energy_min_kwh(self) -> float:
        return self.ess_energy_max_kwh * self.ess_soc_min_ratio

    @property
    def ess_energy_max_limit_kwh(self) -> float:
        return self.ess_energy_max_kwh * self.ess_soc_max_ratio

    @property
    def ess_initial_energy_kwh(self) -> float:
        return self.ess_energy_max_kwh * self.ess_initial_soc_ratio


def load_day_ahead_data(file_path: str) -> pd.DataFrame:
    """加载并校验日前输入数据。"""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"未找到日前数据文件：{path.resolve()}")

    df = pd.read_csv(path)
    required_columns = {
        "hour",
        "pv_power_kw",
        "wt_power_kw",
        "base_load_kw",
        "buy_price_cny_per_kwh",
        "sell_price_cny_per_kwh",
    }
    missing_columns = required_columns.difference(df.columns)
    if missing_columns:
        raise ValueError(f"输入数据缺少必要字段：{sorted(missing_columns)}")

    if len(df) != 24:
        raise ValueError("优化器要求输入数据严格为 24 小时。")

    if not np.array_equal(df["hour"].to_numpy(), np.arange(24)):
        raise ValueError("hour 列必须为 0 到 23 的连续整数。")

    if (df["sell_price_cny_per_kwh"] >= df["buy_price_cny_per_kwh"]).any():
        raise ValueError("售电价必须严格低于购电价，否则会引入套利漏洞。")

    return df


def build_optimization_problem(
    data: pd.DataFrame, config: OptimizerConfig
) -> tuple[cp.Problem, dict[str, cp.Variable]]:
    """构建 MILP 优化问题。"""
    horizon = len(data)
    delta_t = config.time_step_hours

    pv_forecast = data["pv_power_kw"].to_numpy(dtype=float)
    wt_forecast = data["wt_power_kw"].to_numpy(dtype=float)
    load_forecast = data["base_load_kw"].to_numpy(dtype=float)
    buy_price = data["buy_price_cny_per_kwh"].to_numpy(dtype=float)
    sell_price = data["sell_price_cny_per_kwh"].to_numpy(dtype=float)

    # 连续决策变量。
    pv_used = cp.Variable(horizon, nonneg=True, name="pv_used")
    wt_used = cp.Variable(horizon, nonneg=True, name="wt_used")
    grid_buy = cp.Variable(horizon, nonneg=True, name="grid_buy")
    grid_sell = cp.Variable(horizon, nonneg=True, name="grid_sell")
    ess_charge = cp.Variable(horizon, nonneg=True, name="ess_charge")
    ess_discharge = cp.Variable(horizon, nonneg=True, name="ess_discharge")
    ess_soc = cp.Variable(horizon, name="ess_soc")
    load_curtailed = cp.Variable(horizon, nonneg=True, name="load_curtailed")

    # 0-1 互斥状态变量。
    is_buying = cp.Variable(horizon, boolean=True, name="is_buying")
    is_selling = cp.Variable(horizon, boolean=True, name="is_selling")
    is_charging = cp.Variable(horizon, boolean=True, name="is_charging")
    is_discharging = cp.Variable(horizon, boolean=True, name="is_discharging")

    constraints = []

    # 风光利用不能超过预测值。
    constraints.extend(
        [
            pv_used <= pv_forecast,
            wt_used <= wt_forecast,
        ]
    )

    # 主网购售电互斥约束。
    constraints.extend(
        [
            grid_buy <= is_buying * config.grid_exchange_max_kw,
            grid_sell <= is_selling * config.grid_exchange_max_kw,
            is_buying + is_selling <= 1,
        ]
    )

    # 储能充放电互斥约束。
    constraints.extend(
        [
            ess_charge <= is_charging * config.ess_power_max_kw,
            ess_discharge <= is_discharging * config.ess_power_max_kw,
            is_charging + is_discharging <= 1,
        ]
    )

    # 需求响应约束。
    constraints.extend(
        [
            load_curtailed <= config.dr_max_ratio * load_forecast,
            cp.sum(load_curtailed) <= config.dr_daily_max_ratio * np.sum(load_forecast),
        ]
    )

    # 功率平衡约束。
    constraints.append(
        pv_used + wt_used + grid_buy + ess_discharge
        == (load_forecast - load_curtailed) + grid_sell + ess_charge
    )

    # SOC 边界约束。
    constraints.extend(
        [
            ess_soc >= config.ess_energy_min_kwh,
            ess_soc <= config.ess_energy_max_limit_kwh,
        ]
    )

    # SOC 动态方程。
    for t in range(horizon):
        previous_soc = config.ess_initial_energy_kwh if t == 0 else ess_soc[t - 1]
        constraints.append(
            ess_soc[t]
            == previous_soc
            + (
                ess_charge[t] * config.ess_charge_efficiency
                - ess_discharge[t] / config.ess_discharge_efficiency
            )
            * delta_t
        )

    # 首末电量一致，满足日前滚动调度边界条件。
    constraints.append(ess_soc[horizon - 1] == config.ess_initial_energy_kwh)

    # 综合运行成本。
    grid_cost = cp.sum(cp.multiply(grid_buy, buy_price) - cp.multiply(grid_sell, sell_price))
    ess_cost = config.ess_degradation_cost_cny_per_kwh * cp.sum(ess_charge + ess_discharge)
    dr_cost = config.dr_compensation_cost_cny_per_kwh * cp.sum(load_curtailed)
    objective = cp.Minimize(grid_cost + ess_cost + dr_cost)

    problem = cp.Problem(objective, constraints)
    variables = {
        "pv_used": pv_used,
        "wt_used": wt_used,
        "grid_buy": grid_buy,
        "grid_sell": grid_sell,
        "ess_charge": ess_charge,
        "ess_discharge": ess_discharge,
        "ess_soc": ess_soc,
        "load_curtailed": load_curtailed,
        "is_buying": is_buying,
        "is_selling": is_selling,
        "is_charging": is_charging,
        "is_discharging": is_discharging,
    }
    return problem, variables


def solve_problem(problem: cp.Problem, solver_candidates: Iterable[str]) -> str:
    """按优先级尝试可用求解器。"""
    installed = set(cp.installed_solvers())
    last_error: Exception | None = None

    for solver_name in solver_candidates:
        if solver_name not in installed:
            continue

        try:
            problem.solve(solver=solver_name, verbose=False)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            continue

        if problem.status in {cp.OPTIMAL, cp.OPTIMAL_INACCURATE}:
            return solver_name

    if last_error is not None:
        raise RuntimeError(f"求解器执行失败，最后一次错误为：{last_error}") from last_error

    raise RuntimeError(
        f"当前环境未找到可用的 MILP 求解器。已安装求解器：{sorted(installed)}；"
        f"期望候选：{list(solver_candidates)}"
    )


def build_result_dataframe(
    data: pd.DataFrame,
    variables: dict[str, cp.Variable],
    total_cost: float,
    config: OptimizerConfig,
) -> pd.DataFrame:
    """将优化结果整理为结构化输出表。"""
    result = data.copy()

    for column_name, variable in variables.items():
        result[column_name] = np.round(np.asarray(variable.value, dtype=float), 4)

    result["pv_curtailed_kw"] = np.round(result["pv_power_kw"] - result["pv_used"], 4)
    result["wt_curtailed_kw"] = np.round(result["wt_power_kw"] - result["wt_used"], 4)
    result["served_load_kw"] = np.round(result["base_load_kw"] - result["load_curtailed"], 4)
    result["grid_cost_cny"] = np.round(
        result["grid_buy"] * result["buy_price_cny_per_kwh"]
        - result["grid_sell"] * result["sell_price_cny_per_kwh"],
        4,
    )
    result["ess_cost_cny"] = np.round(
        config.ess_degradation_cost_cny_per_kwh * (result["ess_charge"] + result["ess_discharge"]),
        4,
    )
    result["dr_cost_cny"] = np.round(result["load_curtailed"] * config.dr_compensation_cost_cny_per_kwh, 4)
    result["total_cost_cny_daily"] = round(total_cost, 4)
    return result


def validate_solution(result: pd.DataFrame, config: OptimizerConfig) -> None:
    """对优化解进行数值校验，防止静默错误。"""
    tolerance = 1e-4

    balance_lhs = result["pv_used"] + result["wt_used"] + result["grid_buy"] + result["ess_discharge"]
    balance_rhs = result["served_load_kw"] + result["grid_sell"] + result["ess_charge"]
    max_balance_error = np.max(np.abs(balance_lhs - balance_rhs))
    if max_balance_error > tolerance:
        raise ValueError(f"功率平衡校验失败，最大误差为 {max_balance_error:.6f}。")

    if (result["grid_buy"] > tolerance).astype(int).add((result["grid_sell"] > tolerance).astype(int)).max() > 1:
        raise ValueError("存在同时购电和售电的时段，违反互斥约束。")

    if (result["ess_charge"] > tolerance).astype(int).add((result["ess_discharge"] > tolerance).astype(int)).max() > 1:
        raise ValueError("存在同时充电和放电的时段，违反互斥约束。")

    if not np.isclose(result["ess_soc"].iloc[-1], config.ess_initial_energy_kwh, atol=tolerance):
        raise ValueError("储能末时刻 SOC 未回到初始值。")


def save_result(df: pd.DataFrame, output_file: str) -> Path:
    """保存调度结果。"""
    output_path = Path(output_file).resolve()
    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    return output_path


def main() -> None:
    """脚本入口。"""
    config = OptimizerConfig()
    data = load_day_ahead_data(config.input_file)
    problem, variables = build_optimization_problem(data, config)
    solver_name = solve_problem(problem, config.solver_candidates)

    if problem.value is None:
        raise RuntimeError(f"优化结束但未返回目标值，求解状态：{problem.status}")

    total_cost = float(problem.value)
    result = build_result_dataframe(data, variables, total_cost, config)
    validate_solution(result, config)
    output_path = save_result(result, config.output_file)

    print(f"优化求解完成，状态：{problem.status}")
    print(f"使用求解器：{solver_name}")
    print(f"最优总成本：{total_cost:.4f} CNY")
    print(f"调度结果已保存：{output_path}")


if __name__ == "__main__":
    main()

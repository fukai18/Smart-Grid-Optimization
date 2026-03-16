"""微电网日前数据生成器。

根据 PRD 要求生成 24 小时日前预测数据，包括：
1. 光伏出力（鸭子曲线风格，中午高峰，夜间为 0）
2. 风机出力（随机但平滑）
3. 基础负荷（早晚双峰）
4. 分时电价（峰谷平，且售电价低于购电价）
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class GeneratorConfig:
    """数据生成器参数配置。"""

    hours: int = 24
    random_seed: int = 42
    output_file: str = "day_ahead_data.csv"
    pv_capacity_kw: float = 520.0
    wt_capacity_kw: float = 360.0
    load_base_kw: float = 430.0


def generate_pv_profile(hours: np.ndarray, rng: np.random.Generator, capacity_kw: float) -> np.ndarray:
    """生成具有鸭子曲线特征的光伏出力。"""
    sunrise = 6.0
    sunset = 18.0
    daylight = np.clip((hours - sunrise) / (sunset - sunrise), 0.0, 1.0)

    # 使用正弦包络模拟太阳辐照度，并叠加轻微云层扰动。
    solar_envelope = np.sin(np.pi * daylight)
    cloud_effect = 1.0 - 0.08 * np.cos((hours - 12.0) / 2.0) + rng.normal(0.0, 0.015, size=hours.size)
    pv_profile = capacity_kw * np.clip(solar_envelope * cloud_effect, 0.0, 1.0)

    # 夜间光伏必须为 0。
    pv_profile[(hours < sunrise) | (hours >= sunset)] = 0.0
    return np.round(pv_profile, 2)


def generate_wt_profile(hours: np.ndarray, rng: np.random.Generator, capacity_kw: float) -> np.ndarray:
    """生成随机但平滑的风机出力曲线。"""
    base = 0.50 + 0.12 * np.sin(2.0 * np.pi * (hours + 3.0) / 24.0)
    harmonic = 0.08 * np.sin(4.0 * np.pi * (hours + 1.0) / 24.0)
    noise = rng.normal(0.0, 0.06, size=hours.size)
    raw_profile = np.clip(base + harmonic + noise, 0.12, 0.92)

    # 简单平滑处理，避免小时级跳变过大。
    kernel = np.array([0.2, 0.6, 0.2])
    smoothed = np.convolve(np.pad(raw_profile, (1, 1), mode="edge"), kernel, mode="valid")
    wt_profile = capacity_kw * np.clip(smoothed, 0.10, 0.95)
    return np.round(wt_profile, 2)


def generate_load_profile(hours: np.ndarray, rng: np.random.Generator, base_load_kw: float) -> np.ndarray:
    """生成早晚双峰的基础负荷曲线。"""
    morning_peak = 140.0 * np.exp(-0.5 * ((hours - 8.0) / 2.0) ** 2)
    evening_peak = 180.0 * np.exp(-0.5 * ((hours - 19.0) / 2.5) ** 2)
    midday_dip = 45.0 * np.exp(-0.5 * ((hours - 13.0) / 3.0) ** 2)
    nighttime_recovery = 35.0 * np.exp(-0.5 * ((hours - 23.0) / 2.8) ** 2)
    noise = rng.normal(0.0, 8.0, size=hours.size)

    load_profile = base_load_kw + morning_peak + evening_peak - midday_dip + nighttime_recovery + noise
    load_profile = np.clip(load_profile, 300.0, None)
    return np.round(load_profile, 2)


def classify_tou_period(hour: int) -> str:
    """根据小时划分峰谷平时段。"""
    if 0 <= hour < 8:
        return "Valley"
    if 10 <= hour < 14 or 18 <= hour < 22:
        return "Peak"
    return "Flat"


def generate_tou_prices(hours: np.ndarray, rng: np.random.Generator) -> pd.DataFrame:
    """生成分时购售电价，保证售电价始终低于购电价。"""
    buy_price_map = {
        "Valley": 0.38,
        "Flat": 0.67,
        "Peak": 0.98,
    }
    sell_discount_map = {
        "Valley": 0.16,
        "Flat": 0.18,
        "Peak": 0.22,
    }

    periods = [classify_tou_period(int(hour)) for hour in hours]
    buy_prices = []
    sell_prices = []

    for period in periods:
        buy_base = buy_price_map[period]
        discount = sell_discount_map[period]

        # 添加轻微随机扰动，使价格更贴近真实交易场景。
        buy_price = max(buy_base + rng.normal(0.0, 0.01), 0.01)
        sell_price = max(buy_price - discount + rng.normal(0.0, 0.005), 0.01)

        # 严格确保售电价低于购电价。
        if sell_price >= buy_price:
            sell_price = max(buy_price - max(discount, 0.05), 0.01)

        buy_prices.append(round(buy_price, 4))
        sell_prices.append(round(sell_price, 4))

    return pd.DataFrame(
        {
            "tou_period": periods,
            "buy_price_cny_per_kwh": buy_prices,
            "sell_price_cny_per_kwh": sell_prices,
        }
    )


def build_day_ahead_dataframe(config: GeneratorConfig) -> pd.DataFrame:
    """构建完整的日前 24 小时数据表。"""
    rng = np.random.default_rng(config.random_seed)
    hours = np.arange(config.hours)

    df = pd.DataFrame({"hour": hours})
    df["pv_power_kw"] = generate_pv_profile(hours, rng, config.pv_capacity_kw)
    df["wt_power_kw"] = generate_wt_profile(hours, rng, config.wt_capacity_kw)
    df["base_load_kw"] = generate_load_profile(hours, rng, config.load_base_kw)

    price_df = generate_tou_prices(hours, rng)
    df = pd.concat([df, price_df], axis=1)

    validate_day_ahead_data(df)
    return df


def validate_day_ahead_data(df: pd.DataFrame) -> None:
    """对生成结果做基础校验，确保可直接用于后续优化模块。"""
    if len(df) != 24:
        raise ValueError("日前数据必须严格包含 24 条小时记录。")

    if not df["hour"].equals(pd.Series(np.arange(24), name="hour")):
        raise ValueError("hour 列必须为 0 到 23 的连续整数。")

    if (df["pv_power_kw"] < 0).any() or (df["wt_power_kw"] < 0).any() or (df["base_load_kw"] <= 0).any():
        raise ValueError("出力与负荷数据必须满足非负或正值约束。")

    night_hours = df["hour"].isin([0, 1, 2, 3, 4, 5, 18, 19, 20, 21, 22, 23])
    if not (df.loc[night_hours, "pv_power_kw"] == 0).all():
        raise ValueError("夜间时段的光伏出力必须为 0。")

    if not (df["sell_price_cny_per_kwh"] < df["buy_price_cny_per_kwh"]).all():
        raise ValueError("售电价必须严格低于购电价。")


def save_to_csv(df: pd.DataFrame, output_file: str) -> Path:
    """保存结果到 CSV 文件。"""
    output_path = Path(output_file).resolve()
    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    return output_path


def main() -> None:
    """程序入口。"""
    config = GeneratorConfig()
    day_ahead_df = build_day_ahead_dataframe(config)
    output_path = save_to_csv(day_ahead_df, config.output_file)
    print(f"日前数据已生成：{output_path}")


if __name__ == "__main__":
    main()

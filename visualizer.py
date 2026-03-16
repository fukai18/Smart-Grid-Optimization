import pandas as pd
import matplotlib.pyplot as plt

# 读取数据
data = pd.read_csv('day_ahead_data.csv')
schedule = pd.read_csv('schedule_result.csv')

# 合并数据 (使用 inner 连接)
df = pd.merge(data, schedule, on='hour', suffixes=('', '_sch'))

# 绘图设置
fig, ax = plt.subplots(3, 1, figsize=(10, 15))

# 1. 功率曲线
ax[0].plot(df['hour'], df['pv_power_kw'], label='PV Power', color='orange')
ax[0].plot(df['hour'], df['wt_power_kw'], label='WT Power', color='green')
ax[0].plot(df['hour'], df['base_load_kw'], label='Load', color='red', linestyle='--')
ax[0].set_title('Power Schedule')
ax[0].legend()

# 2. SOC 曲线 (直接读取 schedule，因为 data 里没有 ess_soc)
ax[1].plot(df['hour'], df['ess_soc'], label='ESS SOC', color='blue')
ax[1].set_title('ESS SOC Evolution')
ax[1].legend()

# 3. 电价响应
ax[2].plot(df['hour'], df['buy_price_cny_per_kwh'], label='Buy Price', color='purple')
ax[2].plot(df['hour'], df['sell_price_cny_per_kwh'], label='Sell Price', color='brown')
ax[2].set_title('TOU Electricity Price')
ax[2].legend()

plt.tight_layout()
plt.savefig('schedule_visualization.png')
print("Visualization saved to schedule_visualization.png")

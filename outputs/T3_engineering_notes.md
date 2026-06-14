# T3 工程细节说明

这份文件记录项目运行、数据文件、依赖包和可替换数据接口；上交版学术报告见 `outputs/T3_report.md`。

## 运行环境

- 操作系统/终端：Windows PowerShell。
- Python：当前运行环境为 Python 3.13.5。
- 已使用包：`pandas`、`numpy`、`scipy`、`statsmodels`、`matplotlib`。
- 未强制使用包：`yfinance`、`ruptures`、`arch`、R `strucchange`。因此 Yahoo 期货和正式 Bai-Perron 多断点包不是当前主流程依赖。

## 运行命令

```powershell
python src\t3_oil_event_study.py
```

脚本会重新生成 CSV、图表和两份 Markdown 文件：`T3_report.md` 与 `T3_engineering_notes.md`。

## 数据集与联网情况

- 官方 FRED CSV 直连在本机运行时出现过连接超时，因此当前工作区保存了同 FRED 口径的本地 CSV：`DCOILWTICO.csv` 与 `DCOILBRENTEU.csv`。
- `DCOILWTICO.csv` 字段为 `date,wti_price_usd`；`DCOILBRENTEU.csv` 字段为 `date,brent_price_usd`。
- ACLED 需要账号/API key，当前没有账号导出文件，因此主流程使用 `data/manual_events.csv` 的人工核验事件清单。
- 已检测到 ACLED 汇总 Excel：`data\Middle-East_aggregated_data_up_to_week_of-2026-05-30.xlsx`。
- 原文件是中东地区按周聚合数据；当前脚本筛选 2025-01-01 至 2026-06-01，目标国家为 Iran, Israel, Lebanon, Syria, Iraq, Yemen。
- 使用字段：`WEEK`、`COUNTRY`、`ADMIN1`、`EVENT_TYPE`、`SUB_EVENT_TYPE`、`EVENTS`、`FATALITIES`、`POPULATION_EXPOSURE`。
- 它不是逐事件数据，因此没有完整的 `actor1/actor2/notes` 级别信息；当前用于背景统计和事件周强度映射。
- GDELT 当前未并入真实逐日导出；`manual_events.csv` 中的 `gdelt_goldstein` 与 `mentions` 是占位/演示字段。
- 若之后取得真实数据，把 ACLED 导出放入 `data/acled_events.csv`，GDELT 导出放入 `data/gdelt_events.csv`，脚本会按 `event_date` 自动聚合并覆盖人工占位字段。

## 输入与输出文件

| file                                 | exists   |   size_bytes |
|:-------------------------------------|:---------|-------------:|
| DCOILWTICO.csv                       | True     |       172415 |
| DCOILBRENTEU.csv                     | True     |       168099 |
| data\manual_events.csv               | True     |         1538 |
| outputs\oil_daily.csv                | True     |        22967 |
| outputs\events_candidate.csv         | True     |         1838 |
| outputs\event_results.csv            | True     |         8031 |
| outputs\its_results.csv              | True     |         2486 |
| outputs\multi_event_its_results.csv  | True     |         1137 |
| outputs\break_results.csv            | True     |         1659 |
| outputs\acled_weekly_summary.csv     | True     |         1515 |
| outputs\acled_country_summary.csv    | True     |          132 |
| outputs\acled_event_type_summary.csv | True     |         1272 |
| outputs\acled_event_week_mapping.csv | True     |          317 |
| figures\oil_prices_events.png        | True     |       148871 |
| figures\oil_returns_events.png       | True     |       214969 |
| figures\acled_weekly_events.png      | True     |       147874 |
| figures\acled_country_summary.png    | True     |        40998 |

## 数据维度

| dataset                  |   rows |   columns |
|:-------------------------|-------:|----------:|
| oil_daily                |    487 |         5 |
| events_candidate         |      5 |        14 |
| event_results            |     30 |        17 |
| its_results              |     10 |        14 |
| multi_event_its_results  |     10 |         7 |
| break_results            |     20 |         8 |
| acled_raw_filtered       |  18062 |        13 |
| acled_weekly_summary     |     74 |         3 |
| acled_country_summary    |      6 |         3 |
| acled_event_type_summary |     25 |         4 |
| acled_event_week_mapping |      5 |         7 |

## 脚本结构

- `load_oil_data()`：读取 WTI/Brent CSV，合并共同交易日，计算对数收益率。
- `load_events()`：读取人工事件清单，并在存在 ACLED/GDELT 导出时自动合并事件强度字段。
- `event_study()`：估计市场模型，计算三个事件窗口的 AR/CAR、t 值、p 值和显著性排序。
- `its_for_event()`：对每个事件和油价基准估计局部 ITS，并输出 DW、BP 与 Newey-West 修正结果。
- `multi_event_its()`：在同一回归中纳入多个事件的 post 项，辅助分离密集事件影响。
- `break_results()`：用分段线性 RSS/BIC 网格搜索近似结构断点检验。
- `write_report()`：生成更偏论文风格的上交报告。
- `write_engineering_notes()`：生成本文档，集中说明工程细节。

## 当前实现边界

- 报告中的事件标题仍应在最终提交前逐条替换为完整、可引用的新闻链接或 ACLED/GDELT 记录。
- 结构断点部分是 Bai-Perron 思想的近似实现，不等价于正式多断点 Bai-Perron 检验。
- 当前市场模型使用 WTI 与 Brent 互为市场因子，适合低依赖复现；若加入美元指数、商品指数或能源 ETF，可增强正常收益模型。

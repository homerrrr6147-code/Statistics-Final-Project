from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.stats.multitest import multipletests


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
TABLES = Path(__file__).resolve().parent / "tables"
TABLES.mkdir(exist_ok=True)


def esc(value) -> str:
    text = str(value)
    for old, new in [
        ("\\", r"\textbackslash{}"),
        ("&", r"\&"),
        ("%", r"\%"),
        ("_", r"\_"),
        ("#", r"\#"),
    ]:
        text = text.replace(old, new)
    return text


def write_table(filename: str, columns: list[str], rows: list[list], align: str | None = None) -> None:
    if align is None:
        align = "l" + "r" * (len(columns) - 1)
    lines = [
        r"\begin{tabular}{" + align + "}",
        r"\toprule",
        " & ".join(columns) + r" \\",
        r"\midrule",
    ]
    lines.extend(" & ".join(esc(x) for x in row) + r" \\" for row in rows)
    lines.extend([r"\bottomrule", r"\end{tabular}", ""])
    (TABLES / filename).write_text("\n".join(lines), encoding="utf-8")


oil = pd.read_csv(OUT / "oil_daily.csv")
events = pd.read_csv(OUT / "events_candidate.csv").sort_values("event_date")
car = pd.read_csv(OUT / "event_results.csv")
its = pd.read_csv(OUT / "its_results.csv")
breaks = pd.read_csv(OUT / "break_results.csv")
acled_country = pd.read_csv(OUT / "acled_country_summary.csv")
event_week = pd.read_csv(OUT / "acled_event_week_mapping.csv")

desc_rows = []
for col, name in [("r_wti", "WTI"), ("r_brent", "Brent")]:
    x = oil[col].dropna() * 100
    desc_rows.append(
        [
            name,
            len(x),
            f"{x.mean():.3f}",
            f"{x.std():.3f}",
            f"{x.min():.3f}",
            f"{x.median():.3f}",
            f"{x.max():.3f}",
            f"{stats.skew(x):.3f}",
            f"{stats.kurtosis(x, fisher=False):.3f}",
        ]
    )
write_table(
    "descriptive.tex",
    ["变量", "$N$", "均值", "标准差", "最小值", "中位数", "最大值", "偏度", "峰度"],
    desc_rows,
    "lrrrrrrrr",
)

event_labels = {
    "E1": "以色列打击伊朗核设施和军事目标",
    "E2": "伊以导弹与空袭交锋持续",
    "E3": "美以对伊朗发动联合打击",
    "E4": "哈尔克岛及石油出口设施风险",
    "E5": "海上封锁与霍尔木兹海峡风险",
}
source_labels = {
    "E1": "CSIS/公开新闻",
    "E2": "CSIS/ACLED周度",
    "E3": "The Guardian",
    "E4": "Washington Post",
    "E5": "Washington Post",
}
event_rows = []
for _, r in events.iterrows():
    event_rows.append(
        [r.event_id, r.event_date, r.trading_date, event_labels.get(r.event_id, r.title), source_labels.get(r.event_id, r.source)]
    )
write_table("events.tex", ["编号", "事件日期", "交易日", "事件说明", "核验来源"], event_rows, "lllll")

car_rows = []
for _, r in car.sort_values(["window", "asset", "event_id"]).iterrows():
    window = "$" + str(r.window).replace("[", "[").replace("]", "]") + "$"
    car_rows.append([window, r.asset, r.event_id, f"{r.CAR_pct:.3f}", f"{r.t_stat:.3f}", f"{r.p_value:.4f}", r.sig_level])
write_table("car_all_windows.tex", ["窗口", "基准", "事件", r"CAR(\%)", "$t$", "$p$", "显著性"], car_rows, "lllrrrr")

main = car[car.window == "[0,+3]"].copy()
main["p_bonf"] = multipletests(main.p_value, method="bonferroni")[1]
main["p_fdr"] = multipletests(main.p_value, method="fdr_bh")[1]
multi_rows = []
for _, r in main.sort_values(["asset", "event_id"]).iterrows():
    multi_rows.append([r.asset, r.event_id, f"{r.CAR_pct:.3f}", f"{r.p_value:.4f}", f"{r.p_bonf:.4f}", f"{r.p_fdr:.4f}"])
write_table("multiple_testing.tex", ["基准", "事件", r"CAR(\%)", "原始$p$", "Bonferroni", "BH--FDR"], multi_rows, "llrrrr")

its_rows = []
for _, r in its.sort_values(["asset", "event_id"]).iterrows():
    its_rows.append(
        [r.asset, r.event_id, f"{r.level_shift_pct:.3f}", f"{r.trend_shift_pct:.4f}", f"{r.NW_p_level:.4f}", f"{r.DW:.3f}", f"{r.BP_p:.4f}"]
    )
write_table("its.tex", ["基准", "事件", r"水平变化(\%)", "趋势变化", "NW $p$", "DW", "BP $p$"], its_rows, "llrrrrr")

break_rows = []
for _, r in breaks.groupby("asset", as_index=False).head(5).iterrows():
    break_rows.append([r.asset, int(r.break_rank), r.break_date, r.nearest_event_date, int(r.days_to_nearest_event), "是" if r.break_support else "否"])
write_table("breaks.tex", ["基准", "排序", "断点日期", "最近事件", "相差天数", "支持"], break_rows, "lrllrl")

country_rows = [[r.COUNTRY, int(r.EVENTS), int(r.FATALITIES)] for _, r in acled_country.iterrows()]
write_table("acled_country.tex", ["国家", "事件数", "死亡人数"], country_rows, "lrr")

week_rows = []
for _, r in event_week.sort_values("event_date").iterrows():
    week_rows.append([r.event_id, r.event_date, r.acled_week, int(r.week_events), int(r.week_fatalities), r.top_country_in_week])
write_table("event_week.tex", ["事件", "事件日期", "ACLED周", "周事件数", "周死亡数", "事件最多国家"], week_rows, "lllrrl")

ordered = events.sort_values("event_date").copy()
ordered["days_since_previous"] = pd.to_datetime(ordered.event_date).diff().dt.days
overlap_rows = []
for _, r in ordered.iterrows():
    gap = "--" if pd.isna(r.days_since_previous) else int(r.days_since_previous)
    overlap = "--" if pd.isna(r.days_since_previous) else ("是" if r.days_since_previous <= 5 else "否")
    overlap_rows.append([r.event_id, r.event_date, gap, overlap])
write_table("event_overlap.tex", ["事件", "日期", "距上一事件/天", "五日窗口可能重叠"], overlap_rows, "llrl")

corr = oil[["r_wti", "r_brent"]].corr().iloc[0, 1]
(TABLES / "summary_macros.tex").write_text(
    "\n".join(
        [
            rf"\newcommand{{\OilSampleN}}{{{len(oil)}}}",
            rf"\newcommand{{\ReturnCorrelation}}{{{corr:.3f}}}",
            rf"\newcommand{{\EventCount}}{{{len(events)}}}",
        ]
    )
    + "\n",
    encoding="utf-8",
)

print(f"Generated LaTeX tables in {TABLES}")

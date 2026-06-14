from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats
from statsmodels.stats.diagnostic import het_breuschpagan
from statsmodels.stats.stattools import durbin_watson


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
OUT_DIR = ROOT / "outputs"
FIG_DIR = ROOT / "figures"

ANALYSIS_START = "2024-06-01"
EVENT_SAMPLE_START = "2025-01-01"
EVENT_SAMPLE_END = "2026-06-01"
TARGET_COUNTRIES = ["Iran", "Israel", "Lebanon", "Syria", "Iraq", "Yemen"]
ESTIMATION_DAYS = 120
ESTIMATION_GAP = 21
MIN_ESTIMATION_DAYS = 60
EVENT_WINDOWS = {
    "[-1,+1]": (-1, 1),
    "[0,+3]": (0, 3),
    "[0,+5]": (0, 5),
}


@dataclass
class MarketModel:
    alpha: float
    beta: float
    sigma: float
    nobs: int


def ensure_dirs() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    FIG_DIR.mkdir(exist_ok=True)


def read_price_csv(path: Path, value_name: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    date_col = next((c for c in df.columns if c.lower() in {"date", "observation_date"}), df.columns[0])
    value_cols = [c for c in df.columns if c != date_col]
    if not value_cols:
        raise ValueError(f"No value column found in {path}")
    out = df[[date_col, value_cols[0]]].rename(columns={date_col: "date", value_cols[0]: value_name})
    out["date"] = pd.to_datetime(out["date"])
    out[value_name] = pd.to_numeric(out[value_name], errors="coerce")
    return out.dropna()


def load_oil_data() -> pd.DataFrame:
    wti = read_price_csv(ROOT / "DCOILWTICO.csv", "wti")
    brent = read_price_csv(ROOT / "DCOILBRENTEU.csv", "brent")
    oil = pd.merge(wti, brent, on="date", how="inner").sort_values("date")
    oil = oil[(oil["date"] >= ANALYSIS_START) & (oil["date"] <= EVENT_SAMPLE_END)].copy()
    oil["r_wti"] = np.log(oil["wti"]).diff()
    oil["r_brent"] = np.log(oil["brent"]).diff()
    oil = oil.dropna().reset_index(drop=True)
    return oil


def load_events(oil: pd.DataFrame) -> pd.DataFrame:
    events = pd.read_csv(DATA_DIR / "manual_events.csv")
    events["event_date"] = pd.to_datetime(events["event_date"])
    events = merge_optional_event_exports(events)
    events = events[(events["event_date"] >= EVENT_SAMPLE_START) & (events["event_date"] <= EVENT_SAMPLE_END)].copy()
    trading_dates = oil["date"].to_numpy()
    mapped_dates = []
    for dt in events["event_date"]:
        idx = np.searchsorted(trading_dates, np.datetime64(dt), side="left")
        if idx >= len(trading_dates):
            mapped_dates.append(pd.NaT)
        else:
            mapped_dates.append(pd.Timestamp(trading_dates[idx]))
    events["trading_date"] = mapped_dates
    events = events.dropna(subset=["trading_date"]).copy()

    abs_ret = oil.set_index("date")[["r_wti", "r_brent"]].abs()
    market_component = []
    for dt in events["trading_date"]:
        local = abs_ret.loc[:dt].tail(20)
        market_component.append(float(local[["r_wti", "r_brent"]].mean(axis=1).max() * 1000))
    events["oil_vol_component"] = market_component
    events["event_score"] = (
        events["acled_count"].fillna(0) * 2
        + events["fatalities"].fillna(0) * 0.05
        + events["gdelt_goldstein"].abs().fillna(0) * 3
        + np.log1p(events["mentions"].fillna(0)) * 5
    )
    events = events.sort_values("event_score", ascending=False).reset_index(drop=True)
    events["rank"] = np.arange(1, len(events) + 1)
    return events


def load_acled_aggregates(events: pd.DataFrame) -> dict[str, pd.DataFrame]:
    matches = sorted(DATA_DIR.glob("Middle-East_aggregated_data*.xlsx"))
    if not matches:
        empty = pd.DataFrame()
        return {
            "raw": empty,
            "weekly": empty,
            "country": empty,
            "event_type": empty,
            "event_week": empty,
            "source_file": pd.DataFrame([{"source_file": ""}]),
        }

    path = matches[-1]
    raw = pd.read_excel(path)
    raw["WEEK"] = pd.to_datetime(raw["WEEK"], errors="coerce")
    raw = raw[
        (raw["WEEK"] >= EVENT_SAMPLE_START)
        & (raw["WEEK"] <= EVENT_SAMPLE_END)
        & (raw["COUNTRY"].isin(TARGET_COUNTRIES))
    ].copy()
    raw["EVENTS"] = pd.to_numeric(raw["EVENTS"], errors="coerce").fillna(0)
    raw["FATALITIES"] = pd.to_numeric(raw["FATALITIES"], errors="coerce").fillna(0)

    weekly = (
        raw.groupby("WEEK", as_index=False)[["EVENTS", "FATALITIES"]]
        .sum()
        .sort_values("WEEK")
    )
    country = (
        raw.groupby("COUNTRY", as_index=False)[["EVENTS", "FATALITIES"]]
        .sum()
        .sort_values("EVENTS", ascending=False)
    )
    event_type = (
        raw.groupby(["EVENT_TYPE", "SUB_EVENT_TYPE"], as_index=False)[["EVENTS", "FATALITIES"]]
        .sum()
        .sort_values("EVENTS", ascending=False)
    )

    country_week = raw.groupby(["WEEK", "COUNTRY"], as_index=False)[["EVENTS", "FATALITIES"]].sum()
    rows = []
    for _, event in events.iterrows():
        event_date = pd.Timestamp(event["event_date"])
        days_to_saturday = (5 - event_date.weekday()) % 7
        event_week = event_date + pd.to_timedelta(days_to_saturday, unit="D")
        week_total = weekly[weekly["WEEK"] == event_week]
        country_breakdown = country_week[country_week["WEEK"] == event_week].sort_values("EVENTS", ascending=False)
        top_country = country_breakdown.iloc[0]["COUNTRY"] if not country_breakdown.empty else ""
        top_country_events = int(country_breakdown.iloc[0]["EVENTS"]) if not country_breakdown.empty else 0
        rows.append(
            {
                "event_id": event["event_id"],
                "event_date": event_date.date().isoformat(),
                "acled_week": event_week.date().isoformat(),
                "week_events": int(week_total["EVENTS"].iloc[0]) if not week_total.empty else 0,
                "week_fatalities": int(week_total["FATALITIES"].iloc[0]) if not week_total.empty else 0,
                "top_country_in_week": top_country,
                "top_country_events": top_country_events,
            }
        )
    event_week = pd.DataFrame(rows)

    return {
        "raw": raw,
        "weekly": weekly,
        "country": country,
        "event_type": event_type,
        "event_week": event_week,
        "source_file": pd.DataFrame([{"source_file": str(path.relative_to(ROOT))}]),
    }


def merge_optional_event_exports(events: pd.DataFrame) -> pd.DataFrame:
    """Merge account-backed ACLED/GDELT exports when the user provides them."""
    out = events.copy()
    acled_path = DATA_DIR / "acled_events.csv"
    if acled_path.exists():
        acled = pd.read_csv(acled_path)
        date_col = next((c for c in acled.columns if c.lower() in {"event_date", "date"}), None)
        if date_col:
            acled["event_date"] = pd.to_datetime(acled[date_col], errors="coerce")
            fatal_col = next((c for c in acled.columns if c.lower() == "fatalities"), None)
            agg_map = {"event_id": "count"}
            if fatal_col:
                agg_map[fatal_col] = "sum"
            grouped = acled.groupby("event_date").agg(agg_map).rename(columns={"event_id": "acled_count"})
            if fatal_col:
                grouped = grouped.rename(columns={fatal_col: "fatalities"})
            out = out.drop(columns=[c for c in ["acled_count", "fatalities"] if c in out.columns]).merge(
                grouped.reset_index(), on="event_date", how="left"
            )

    gdelt_path = DATA_DIR / "gdelt_events.csv"
    if gdelt_path.exists():
        gdelt = pd.read_csv(gdelt_path, low_memory=False)
        if "SQLDATE" in gdelt.columns:
            gdelt["event_date"] = pd.to_datetime(gdelt["SQLDATE"].astype(str), format="%Y%m%d", errors="coerce")
        else:
            date_col = next((c for c in gdelt.columns if c.lower() in {"event_date", "date"}), None)
            if date_col:
                gdelt["event_date"] = pd.to_datetime(gdelt[date_col], errors="coerce")
        if "event_date" in gdelt.columns:
            gold_col = next((c for c in gdelt.columns if c.lower() == "goldsteinscale"), None)
            agg = pd.DataFrame({"event_date": sorted(gdelt["event_date"].dropna().unique())})
            mentions = gdelt.groupby("event_date").size().rename("mentions").reset_index()
            agg = agg.merge(mentions, on="event_date", how="left")
            if gold_col:
                gold = gdelt.groupby("event_date")[gold_col].mean().rename("gdelt_goldstein").reset_index()
                agg = agg.merge(gold, on="event_date", how="left")
            out = out.drop(columns=[c for c in ["gdelt_goldstein", "mentions"] if c in out.columns]).merge(
                agg, on="event_date", how="left"
            )

    for col in ["acled_count", "fatalities", "gdelt_goldstein", "mentions"]:
        if col not in out.columns:
            out[col] = 0
        out[col] = out[col].fillna(0)
    return out


def positional_index(oil: pd.DataFrame, dt: pd.Timestamp) -> int:
    matches = oil.index[oil["date"] == dt]
    if len(matches) == 0:
        raise ValueError(f"Trading date {dt} not found in oil data")
    return int(matches[0])


def fit_market_model(oil: pd.DataFrame, event_idx: int, target: str, market: str) -> MarketModel | None:
    est_end = event_idx - ESTIMATION_GAP
    est_start = est_end - ESTIMATION_DAYS
    est_start = max(est_start, 0)
    if est_end <= est_start:
        return None
    est = oil.iloc[est_start:est_end].dropna(subset=[target, market])
    if len(est) < MIN_ESTIMATION_DAYS:
        return None
    x = sm.add_constant(est[market])
    fit = sm.OLS(est[target], x).fit()
    sigma = math.sqrt(float(np.sum(fit.resid**2) / max(fit.df_resid, 1)))
    return MarketModel(float(fit.params["const"]), float(fit.params[market]), sigma, int(fit.nobs))


def event_study(oil: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    rows = []
    configs = {
        "WTI": ("r_wti", "r_brent"),
        "Brent": ("r_brent", "r_wti"),
    }
    for _, event in events.iterrows():
        event_idx = positional_index(oil, event["trading_date"])
        for asset, (target, market) in configs.items():
            model = fit_market_model(oil, event_idx, target, market)
            if model is None:
                continue
            for label, (lo, hi) in EVENT_WINDOWS.items():
                start = max(event_idx + lo, 0)
                end = min(event_idx + hi, len(oil) - 1)
                win = oil.iloc[start : end + 1].copy()
                expected = model.alpha + model.beta * win[market]
                ar = win[target] - expected
                car = float(ar.sum())
                n = len(ar)
                t_stat = car / (model.sigma * math.sqrt(n)) if model.sigma > 0 and n else np.nan
                p_value = float(2 * (1 - stats.t.cdf(abs(t_stat), df=max(model.nobs - 2, 1)))) if np.isfinite(t_stat) else np.nan
                rows.append(
                    {
                        "event_id": event["event_id"],
                        "event_date": event["event_date"].date().isoformat(),
                        "trading_date": event["trading_date"].date().isoformat(),
                        "title": event["title"],
                        "asset": asset,
                        "window": label,
                        "CAR": car,
                        "CAR_pct": car * 100,
                        "t_stat": t_stat,
                        "p_value": p_value,
                        "sig_level": sig_level(p_value),
                        "n_window": n,
                        "n_estimation": model.nobs,
                        "alpha": model.alpha,
                        "beta": model.beta,
                        "sigma": model.sigma,
                    }
                )
    results = pd.DataFrame(rows)
    if not results.empty:
        results["abs_t"] = results["t_stat"].abs()
        results["rank"] = results.groupby(["asset", "window"])["abs_t"].rank(ascending=False, method="dense").astype(int)
        results = results.drop(columns=["abs_t"])
    return results


def sig_level(p: float) -> str:
    if not np.isfinite(p):
        return ""
    if p < 0.01:
        return "***"
    if p < 0.05:
        return "**"
    if p < 0.10:
        return "*"
    return "n.s."


def its_for_event(oil: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, event in events.iterrows():
        event_idx = positional_index(oil, event["trading_date"])
        for asset, target in {"WTI": "r_wti", "Brent": "r_brent"}.items():
            start = max(event_idx - 40, 0)
            end = min(event_idx + 40, len(oil) - 1)
            local = oil.iloc[start : end + 1].copy().reset_index(drop=True)
            local["time"] = np.arange(len(local))
            e_local = event_idx - start
            local["post"] = (local["time"] >= e_local).astype(int)
            local["time_after"] = np.where(local["time"] >= e_local, local["time"] - e_local, 0)
            x = sm.add_constant(local[["time", "post", "time_after"]])
            y = local[target]
            fit = sm.OLS(y, x).fit()
            nw = fit.get_robustcov_results(cov_type="HAC", maxlags=5)
            bp_stat, bp_p, _, _ = het_breuschpagan(fit.resid, x)
            dw = durbin_watson(fit.resid)
            rows.append(
                {
                    "event_id": event["event_id"],
                    "asset": asset,
                    "event_date": event["event_date"].date().isoformat(),
                    "trading_date": event["trading_date"].date().isoformat(),
                    "level_shift": float(fit.params["post"]),
                    "level_shift_pct": float(fit.params["post"] * 100),
                    "trend_shift": float(fit.params["time_after"]),
                    "trend_shift_pct": float(fit.params["time_after"] * 100),
                    "OLS_se_level": float(fit.bse["post"]),
                    "NW_se_level": float(nw.bse[list(x.columns).index("post")]),
                    "NW_p_level": float(nw.pvalues[list(x.columns).index("post")]),
                    "DW": float(dw),
                    "BP_stat": float(bp_stat),
                    "BP_p": float(bp_p),
                }
            )
    return pd.DataFrame(rows)


def multi_event_its(oil: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    rows = []
    sample = oil[(oil["date"] >= EVENT_SAMPLE_START) & (oil["date"] <= EVENT_SAMPLE_END)].copy().reset_index(drop=True)
    sample["time"] = np.arange(len(sample))
    for asset, target in {"WTI": "r_wti", "Brent": "r_brent"}.items():
        design = sample[["time"]].copy()
        for _, event in events.iterrows():
            idx = np.searchsorted(sample["date"].to_numpy(), np.datetime64(event["trading_date"]), side="left")
            design[f"{event['event_id']}_post"] = (sample["time"] >= idx).astype(int)
            design[f"{event['event_id']}_trend"] = np.where(sample["time"] >= idx, sample["time"] - idx, 0)
        x = sm.add_constant(design)
        fit = sm.OLS(sample[target], x).fit()
        nw = fit.get_robustcov_results(cov_type="HAC", maxlags=5)
        for _, event in events.iterrows():
            col = f"{event['event_id']}_post"
            pos = list(x.columns).index(col)
            rows.append(
                {
                    "model": "multi_event_ITS",
                    "asset": asset,
                    "event_id": event["event_id"],
                    "level_shift": float(fit.params[col]),
                    "level_shift_pct": float(fit.params[col] * 100),
                    "NW_se_level": float(nw.bse[pos]),
                    "NW_p_level": float(nw.pvalues[pos]),
                }
            )
    return pd.DataFrame(rows)


def segmented_rss(y: np.ndarray, min_size: int = 25) -> pd.DataFrame:
    n = len(y)
    rows = []
    x_full = np.arange(n)
    full_x = sm.add_constant(x_full)
    full_fit = sm.OLS(y, full_x).fit()
    full_rss = float(np.sum(full_fit.resid**2))
    for bp in range(min_size, n - min_size):
        x1 = sm.add_constant(np.arange(bp))
        x2 = sm.add_constant(np.arange(n - bp))
        fit1 = sm.OLS(y[:bp], x1).fit()
        fit2 = sm.OLS(y[bp:], x2).fit()
        rss = float(np.sum(fit1.resid**2) + np.sum(fit2.resid**2))
        bic = n * math.log(rss / n) + 4 * math.log(n)
        rows.append({"break_idx": bp, "rss": rss, "rss_gain": full_rss - rss, "bic": bic})
    return pd.DataFrame(rows).sort_values("bic")


def break_results(oil: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    sample = oil[(oil["date"] >= EVENT_SAMPLE_START) & (oil["date"] <= EVENT_SAMPLE_END)].copy().reset_index(drop=True)
    rows = []
    event_dates = pd.to_datetime(events["trading_date"]).tolist()
    for asset, target in {"WTI": "r_wti", "Brent": "r_brent"}.items():
        candidates = segmented_rss(sample[target].to_numpy()).head(10)
        for rank, row in enumerate(candidates.itertuples(index=False), start=1):
            dt = sample.loc[int(row.break_idx), "date"]
            nearest = min(event_dates, key=lambda e: abs((e - dt).days))
            rows.append(
                {
                    "asset": asset,
                    "break_rank": rank,
                    "break_date": dt.date().isoformat(),
                    "bic": float(row.bic),
                    "rss_gain": float(row.rss_gain),
                    "nearest_event_date": nearest.date().isoformat(),
                    "days_to_nearest_event": abs((nearest - dt).days),
                    "break_support": abs((nearest - dt).days) <= 5,
                }
            )
    return pd.DataFrame(rows)


def make_figures(oil: pd.DataFrame, events: pd.DataFrame, acled: dict[str, pd.DataFrame] | None = None) -> None:
    sample = oil[(oil["date"] >= EVENT_SAMPLE_START) & (oil["date"] <= EVENT_SAMPLE_END)].copy()
    fig, ax = plt.subplots(figsize=(11, 5))
    ax.plot(sample["date"], sample["wti"], label="WTI")
    ax.plot(sample["date"], sample["brent"], label="Brent")
    for _, event in events.iterrows():
        ax.axvline(event["trading_date"], color="tab:red", alpha=0.25, linewidth=1)
    ax.set_title("WTI and Brent crude prices with selected conflict events")
    ax.set_ylabel("USD / barrel")
    ax.legend()
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(FIG_DIR / "oil_prices_events.png", dpi=180)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(11, 5))
    ax.plot(sample["date"], sample["r_wti"] * 100, label="WTI return")
    ax.plot(sample["date"], sample["r_brent"] * 100, label="Brent return")
    for _, event in events.iterrows():
        ax.axvline(event["trading_date"], color="tab:red", alpha=0.25, linewidth=1)
    ax.set_title("Daily log returns with selected conflict events")
    ax.set_ylabel("Daily log return (%)")
    ax.legend()
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(FIG_DIR / "oil_returns_events.png", dpi=180)
    plt.close(fig)

    if not acled or acled["weekly"].empty or acled["country"].empty:
        return

    weekly = acled["weekly"].copy()
    fig, ax1 = plt.subplots(figsize=(11, 5))
    ax1.plot(weekly["WEEK"], weekly["EVENTS"], color="tab:blue", label="Events")
    ax1.set_ylabel("Weekly events", color="tab:blue")
    ax1.tick_params(axis="y", labelcolor="tab:blue")
    ax2 = ax1.twinx()
    ax2.plot(weekly["WEEK"], weekly["FATALITIES"], color="tab:red", alpha=0.75, label="Fatalities")
    ax2.set_ylabel("Weekly fatalities", color="tab:red")
    ax2.tick_params(axis="y", labelcolor="tab:red")
    ax1.set_title("ACLED weekly conflict intensity in target Middle East countries")
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(FIG_DIR / "acled_weekly_events.png", dpi=180)
    plt.close(fig)

    country = acled["country"].copy().sort_values("EVENTS", ascending=True)
    fig, ax = plt.subplots(figsize=(9, 5))
    y = np.arange(len(country))
    ax.barh(y - 0.18, country["EVENTS"], height=0.36, label="Events")
    ax.barh(y + 0.18, country["FATALITIES"], height=0.36, label="Fatalities")
    ax.set_yticks(y)
    ax.set_yticklabels(country["COUNTRY"])
    ax.set_xlabel("Count")
    ax.set_title("ACLED events and fatalities by target country")
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIG_DIR / "acled_country_summary.png", dpi=180)
    plt.close(fig)


def write_report(
    oil: pd.DataFrame,
    events: pd.DataFrame,
    event_results: pd.DataFrame,
    its_results: pd.DataFrame,
    multi_its: pd.DataFrame,
    breaks: pd.DataFrame,
    acled: dict[str, pd.DataFrame] | None = None,
) -> None:
    primary = event_results[event_results["window"] == "[0,+3]"].copy()
    primary = primary.sort_values(["asset", "rank"])
    sig = primary[primary["sig_level"].isin(["*", "**", "***"])]

    def fmt_pct(value: float) -> str:
        return f"{value:.2f}%"

    def fmt_p(value: float) -> str:
        return "<0.0001" if value < 0.0001 else f"{value:.4f}"

    def top_car_sentence(asset: str) -> str:
        part = primary[primary["asset"] == asset].copy()
        if part.empty:
            return f"- {asset}：无可用 CAR 结果。"
        top_abs = part.iloc[part["CAR_pct"].abs().argmax()]
        top_sig = part.sort_values("p_value").iloc[0]
        return (
            f"- {asset}：主窗口 `[0,+3]` 下绝对冲击最大的事件是 {top_abs['event_id']}，"
            f"CAR={fmt_pct(top_abs['CAR_pct'])}，t={top_abs['t_stat']:.2f}，p={fmt_p(top_abs['p_value'])}；"
            f"统计显著性最强的事件是 {top_sig['event_id']}，"
            f"p={fmt_p(top_sig['p_value'])}，显著性标记为 `{top_sig['sig_level']}`。"
        )

    def top_its_sentence(asset: str) -> str:
        part = its_results[its_results["asset"] == asset].copy()
        if part.empty:
            return f"- {asset}：无可用 ITS 结果。"
        top_level = part.iloc[part["level_shift_pct"].abs().argmax()]
        top_nw = part.sort_values("NW_p_level").iloc[0]
        return (
            f"- {asset}：局部 ITS 中即时水平变化幅度最大的是 {top_level['event_id']}，"
            f"level shift={fmt_pct(top_level['level_shift_pct'])}；"
            f"Newey-West 修正后最显著的是 {top_nw['event_id']}，"
            f"p={fmt_p(top_nw['NW_p_level'])}。"
        )

    bp_issue_count = int((its_results["BP_p"] < 0.05).sum())
    dw_mean = float(its_results["DW"].mean())
    break_support_count = int(breaks["break_support"].sum())
    break_total = int(len(breaks))
    sample_oil = oil[(oil["date"] >= EVENT_SAMPLE_START) & (oil["date"] <= EVENT_SAMPLE_END)]
    wti_range = (float(sample_oil["wti"].min()), float(sample_oil["wti"].max()))
    brent_range = (float(sample_oil["brent"].min()), float(sample_oil["brent"].max()))
    event_table = events[["event_id", "event_date", "trading_date", "title", "event_score", "rank"]].copy()
    event_table["event_date"] = pd.to_datetime(event_table["event_date"]).dt.date
    event_table["trading_date"] = pd.to_datetime(event_table["trading_date"]).dt.date
    acled_available = bool(acled and not acled["weekly"].empty)
    if acled_available:
        acled_country = acled["country"].copy()
        acled_event_week = acled["event_week"].copy()
        acled_total_events = int(acled_country["EVENTS"].sum())
        acled_total_fatalities = int(acled_country["FATALITIES"].sum())
        top_acled_country = acled_country.sort_values("EVENTS", ascending=False).iloc[0]
        top_acled_week = acled["weekly"].sort_values("EVENTS", ascending=False).iloc[0]
        acled_background = (
            f"ACLED 中东汇总数据进一步显示，在 {EVENT_SAMPLE_START} 至 {EVENT_SAMPLE_END} 期间，"
            f"目标国家合计记录 {acled_total_events:,} 起事件和 {acled_total_fatalities:,} 人死亡。"
            f"按事件数看，最高的国家是 {top_acled_country['COUNTRY']}，共 {int(top_acled_country['EVENTS']):,} 起；"
            f"周度事件峰值出现在 {pd.Timestamp(top_acled_week['WEEK']).date()} 所在周，"
            f"该周目标国家合计 {int(top_acled_week['EVENTS']):,} 起事件。"
        )
        acled_data_note = (
            "ACLED 汇总数据来自中东地区周度聚合表，粒度为“周-国家-一级行政区-事件类型/子类型”。"
            "它可以衡量事件发生周的区域冲突强度，但不包含逐条事件的参与方和文字叙述，"
            "因此本报告将其作为背景验证数据，而不直接替代人工核验事件清单。"
        )
    else:
        acled_event_week = pd.DataFrame()
        acled_background = "当前未检测到 ACLED 中东汇总数据，因此报告只使用人工核验事件清单。"
        acled_data_note = "当前未检测到 ACLED 中东汇总数据。"

    lines = [
        "# T3 中东冲突对国际油价冲击：事件研究法与回归分析",
        "",
        "## 摘要",
        "",
        (
            "本文围绕“中东冲突升级是否会对国际油价造成统计显著冲击”这一问题，"
            "以 2025-2026 年伊以冲突及其外溢事件为研究对象，使用 WTI 与 Brent 日度油价构造对数收益率，"
            "并选取 7 个关键事件进行事件研究和中断时间序列分析。研究的核心不是简单描述油价涨跌，"
            "而是把每个事件前后的价格变化拆分为正常波动与异常冲击，进一步检验哪些事件的影响具有统计显著性。"
        ),
        "",
        (
            f"实证样本覆盖 {oil['date'].min().date()} 至 {oil['date'].max().date()}，"
            f"主事件窗口采用 `[0,+3]`。在 {len(primary)} 个资产-事件组合中，"
            f"有 {len(sig)} 个组合达到 10% 或更高显著性。"
            "报告同时给出 Durbin-Watson、Breusch-Pagan、Newey-West 修正和结构断点近似结果，"
            "以检查回归结论是否受到残差自相关、异方差或结构变化的影响。"
        ),
        "",
        "## 研究背景与问题提出",
        "",
        (
            "原油价格对地缘政治风险高度敏感。中东地区既是全球重要产油区，也是关键航运通道所在地，"
            "一旦军事冲突影响石油设施、出口预期或霍尔木兹海峡等运输瓶颈，市场往往会迅速把风险溢价计入期货和现货价格。"
            "但是，油价本身也会受到库存、美元、OPEC 预期、宏观需求和金融市场风险偏好的影响，"
            "因此“冲突发生后油价上涨或下跌”并不等同于“冲突造成了统计显著冲击”。"
        ),
        "",
        acled_background,
        "",
        (
            "本作业采用事件研究法和回归分析来回答三个问题：第一，每次重大事件后 WTI 与 Brent 的异常收益有多大；"
            "第二，哪些事件的累计异常收益 CAR 在统计意义上显著；第三，当多个事件密集发生时，"
            "能否通过中断时间序列模型分离单次冲击的即时水平变化和后续趋势变化。"
        ),
        "",
        "## 数据来源与变量解释",
        "",
        "### 数据来源与处理过程",
        "",
        f"- 油价样本：用于建模的价格数据从 {oil['date'].min().date()} 开始，以保证早期事件也有足够的估计窗口；主报告关注 {EVENT_SAMPLE_START} 至 {EVENT_SAMPLE_END} 的事件样本。",
        "- WTI 与 Brent 日度价格采用 FRED 口径的日度原油价格数据，并统一到共同交易日。",
        "- 事件样本由人工核验的中东冲突升级事件构成，并预留 ACLED 与 GDELT 指标作为事件强度补充。",
        f"- {acled_data_note}",
        "- 对油价先按日期合并，再剔除缺失值，并计算日对数收益率。对数收益率比简单涨跌幅更适合时间序列建模，因为连续多期收益可以近似相加。",
        "",
        "### 单项数据解释",
        "",
        f"- `wti`：West Texas Intermediate，美国轻质低硫原油价格，报告样本内价格区间为 {wti_range[0]:.2f} 至 {wti_range[1]:.2f} 美元/桶。WTI 对北美供需、库存和金融交易预期较敏感。",
        f"- `brent`：Brent 原油价格，报告样本内价格区间为 {brent_range[0]:.2f} 至 {brent_range[1]:.2f} 美元/桶。Brent 更常被视为国际海运原油基准，对中东供应风险的反应通常更直接。",
        "- `r_wti`、`r_brent`：WTI 与 Brent 的日对数收益率，计算公式为 `r_t = ln(P_t) - ln(P_{t-1})`。本报告把收益率作为被解释变量，而不是直接回归价格水平，以降低趋势和量纲问题。",
        "- `event_date`：事件实际发生日期。若事件发生在周末或非交易日，油价无法在当天交易，因此不能直接用于收益率窗口。",
        "- `trading_date`：事件映射到的第一个可交易日，是事件研究和 ITS 的实际冲击日期。",
        "- `acled_count`：同日 ACLED 冲突事件数量，反映事件密度。当前为可插拔字段，取得 ACLED 导出后可自动替换。",
        "- `fatalities`：ACLED 记录的死亡人数，用来近似事件严重程度。该变量可能存在低报或统计口径差异，因此只作为辅助权重。",
        "- `gdelt_goldstein`：GDELT 的事件方向和强度分数，负值通常代表冲突、威胁或对抗性事件，绝对值越大表示事件强度越高。",
        "- `mentions`：GDELT 或新闻数据中同日相关报道数量，用来刻画市场可观察的信息强度。",
        "- `event_score`：事件筛选得分，由事件密度、死亡数、GoldsteinScale 绝对值、新闻提及量和局部油价波动共同构成，用于对候选事件排序。",
        "- `ACLED EVENTS/FATALITIES`：ACLED 汇总表中的周度事件数与死亡人数。本报告用它说明候选事件发生周的地区冲突强度，而不把它当作逐事件记录。",
        "",
        "## 事件选择与样本构造",
        "",
        (
            "事件研究法要求事件日期尽可能清晰，并且事件窗口之间不能过度重叠。"
            "本报告先保留 2025-2026 年与伊朗、以色列及周边航运风险相关的候选事件，"
            "再根据事件得分和交易日映射结果选择 7 个事件。"
            "对于相距较近的事件，后续多事件 ITS 会共同纳入多个 post 项，以减少单事件窗口互相污染。"
        ),
        "",
        event_table.round({"event_score": 3}).to_markdown(index=False),
        "",
        "下表把 7 个油价事件映射到 ACLED 汇总数据中的对应周，用于判断事件发生时区域冲突强度是否同步升高：",
        "",
        (
            acled_event_week.to_markdown(index=False)
            if acled_available
            else "未检测到 ACLED 汇总数据，暂不生成事件周强度表。"
        ),
        "",
        "## 统计方法链",
        "",
        "### 1. 事件窗口与 CAR 计算",
        "",
        (
            "事件研究法的出发点是比较“事件发生后的实际收益”与“如果事件没有发生，本应出现的正常收益”。"
            "设资产 `i` 在日期 `t` 的收益率为 `R_{i,t}`，正常收益为 `E(R_{i,t})`，则异常收益为："
        ),
        "",
        "`AR_{i,t} = R_{i,t} - E(R_{i,t})`",
        "",
        "在事件窗口 `[τ_1, τ_2]` 内，累计异常收益为：",
        "",
        "`CAR_i(τ_1, τ_2) = Σ_{t=τ_1}^{τ_2} AR_{i,t}`",
        "",
        "本报告使用 `[-1,+1]`、`[0,+3]` 和 `[0,+5]` 三个窗口。`[-1,+1]` 用于捕捉提前交易或时区差异，`[0,+3]` 作为主窗口，`[0,+5]` 用于观察冲击是否延续。",
        "",
        "### 2. 正常收益模型：市场模型",
        "",
        (
            "为了估计正常收益，本报告采用市场模型。由于当前不强制引入额外商品指数，"
            "WTI 与 Brent 互为市场参照：估计 WTI 时用 Brent 收益作为市场因子，估计 Brent 时用 WTI 收益作为市场因子。"
            "模型为："
        ),
        "",
        "`R_{i,t} = α_i + β_i R_{m,t} + ε_{i,t}`",
        "",
        f"其中估计窗口为事件日前 {ESTIMATION_DAYS} 个交易日，并跳过事件日前 {ESTIMATION_GAP} 个交易日，避免事件预期污染正常收益估计。若早期事件样本不足，则至少保留 {MIN_ESTIMATION_DAYS} 个交易日。",
        "",
        "### 3. CAR 显著性 t 检验",
        "",
        "CAR 的显著性检验考察累计异常收益是否显著偏离 0。若事件窗口长度为 `L`，估计窗口残差标准差为 `σ̂_AR`，检验统计量写作：",
        "",
        "`t = CAR / (σ̂_AR √L)`",
        "",
        "原假设为 `H_0: CAR = 0`，即事件没有造成异常收益；备择假设为 `H_1: CAR ≠ 0`。报告中 `* / ** / ***` 分别代表 10%、5% 和 1% 显著性。",
        "",
        "### 4. 中断时间序列 ITS",
        "",
        "事件研究关注窗口内的累计冲击，ITS 则进一步区分事件后的即时水平变化和趋势变化。局部 ITS 模型为：",
        "",
        "`r_t = β_0 + β_1 time_t + β_2 post_t + β_3 time_after_t + ε_t`",
        "",
        "`β_2` 表示事件发生后收益率水平的即时跳变，`β_3` 表示事件后趋势斜率的变化。多事件 ITS 在同一模型中放入多个事件的 `post` 与 `time_after` 变量，用来在事件密集时期分离不同事件的影响。",
        "",
        "### 5. 残差诊断：DW 与 BP",
        "",
        "Durbin-Watson 统计量用于检查残差一阶自相关，数值接近 2 通常表示自相关不明显；明显小于 2 往往提示正自相关。Breusch-Pagan 检验用于检查异方差，若 p 值较小，则说明残差方差可能随解释变量变化，常规 OLS 标准误可能不稳健。",
        "",
        "### 6. Newey-West 修正",
        "",
        "油价收益率可能存在短期自相关和条件异方差。Newey-West 标准误在估计系数不变的前提下修正协方差矩阵，使回归推断对异方差和自相关更稳健。本报告对 ITS 的水平冲击项报告 Newey-West 修正后的标准误和 p 值。",
        "",
        "### 7. Bai-Perron 结构断点思想",
        "",
        (
            "Bai-Perron 方法的目标是在未知断点位置下寻找时间序列结构发生变化的日期。"
            "当前实现不强制安装专用包，因此采用单断点分段线性 RSS/BIC 网格搜索作为近似："
            "对每个候选断点分别拟合断点前后两段线性趋势，选择 BIC 最优的日期。"
            "若最优断点距离候选冲突事件不超过 5 天，则记为 `break_support=True`，作为事件冲击改变油价结构的辅助证据。"
        ),
        "",
        "## 实证结果与解释",
        "",
        "主表使用 `[0,+3]` 事件窗口；`* / ** / ***` 分别表示 10% / 5% / 1% 显著。",
        "",
        primary[["asset", "event_id", "event_date", "CAR_pct", "t_stat", "p_value", "sig_level", "rank"]]
        .round({"CAR_pct": 3, "t_stat": 3, "p_value": 4})
        .to_markdown(index=False),
        "",
        f"主窗口下显著事件数量为 {len(sig)} / {len(primary)}（按资产-事件组合计）。从资产维度看：",
        "",
        top_car_sentence("WTI"),
        top_car_sentence("Brent"),
        "",
        (
            "CAR 的符号反映异常收益方向：正值表示事件窗口内油价相对正常收益模型上行，"
            "负值表示相对正常收益模型下行。需要注意，负向 CAR 并不一定说明冲突降低油价，"
            "它可能意味着市场此前已经提前计价，或事件后出现了停火、增产、需求转弱等相反信息。"
        ),
        "",
        "## 稳健性与残差诊断",
        "",
        "### 局部 ITS 结果",
        "",
        (
            "下表报告每个事件前后约 40 个交易日内的 ITS 回归。`level_shift_pct` 是事件后的即时水平变化，"
            "`trend_shift_pct` 是事件后的趋势变化；`NW_p_level` 是对水平变化项进行 Newey-West 修正后的 p 值。"
        ),
        "",
        its_results[["asset", "event_id", "level_shift_pct", "trend_shift_pct", "NW_se_level", "NW_p_level", "DW", "BP_p"]]
        .round({"level_shift_pct": 3, "trend_shift_pct": 4, "NW_se_level": 4, "NW_p_level": 4, "DW": 3, "BP_p": 4})
        .to_markdown(index=False),
        "",
        top_its_sentence("WTI"),
        top_its_sentence("Brent"),
        "",
        (
            f"诊断结果显示，DW 统计量均值约为 {dw_mean:.2f}，整体接近 2，说明一阶自相关不是最突出的风险；"
            f"BP 检验在 {bp_issue_count} 个局部回归中达到 5% 显著，提示部分模型存在异方差，"
            "因此报告 Newey-West 修正结果是必要的。"
        ),
        "",
        "### 多事件 ITS 结果",
        "",
        "多事件 ITS 用多个 `post` 与 `post-trend` 项共同分离冲击，适合处理事件密集发生、单一事件窗口可能重叠的情况：",
        "",
        multi_its[["asset", "event_id", "level_shift_pct", "NW_se_level", "NW_p_level"]]
        .round({"level_shift_pct": 3, "NW_se_level": 4, "NW_p_level": 4})
        .to_markdown(index=False),
        "",
        "多事件模型的系数不应简单等同于因果效应，因为同一时期可能还存在库存、宏观需求和政策预期变化；但它提供了一个更严格的分离框架，避免把相邻事件的影响全部归于某一个事件。",
        "",
        "## 结构断点分析",
        "",
        "当前环境未强制安装 Bai-Perron 专用包，因此用单断点分段线性 RSS/BIC 网格搜索作近似筛查；`break_support=True` 表示断点距候选事件不超过 5 天。",
        "",
        breaks[["asset", "break_rank", "break_date", "nearest_event_date", "days_to_nearest_event", "break_support"]]
        .head(12)
        .to_markdown(index=False),
        "",
        (
            f"在前 {break_total} 个断点候选中，有 {break_support_count} 个与候选事件相距不超过 5 天。"
            "这种接近并不能单独证明因果关系，但它说明油价收益序列的结构变化日期与冲突事件日期存在一定重合，"
            "可作为事件研究和 ITS 之外的辅助证据。"
        ),
        "",
        "## 结论、局限与后续改进",
        "",
        (
            "本文完成了作业要求中的统计方法链：事件窗口 CAR 计算、正常收益市场模型、CAR 显著性 t 检验、"
            "中断时间序列 ITS、DW/BP 残差诊断、Newey-West 修正和结构断点近似。"
            "从结果看，不同事件对 WTI 和 Brent 的影响方向与显著性并不完全一致，"
            "说明中东冲突对油价的影响并非单一的“冲突升级则油价必然上涨”，而是取决于市场是否提前计价、事件是否触及供应链、以及后续政策和外交信息。"
        ),
        "",
        (
            "本研究的主要局限有三点。第一，事件强度指标仍有进一步精确化空间，最终研究可使用 ACLED 与 GDELT 的逐日事件数据进行严格校准。"
            "第二，WTI 与 Brent 互为市场因子的设定能够刻画两类油价基准之间的共同波动，但更理想的市场模型还可加入美元指数、能源板块指数或广义商品指数。"
            "第三，当前结构断点检验采用单断点近似，后续可扩展为多断点 Bai-Perron 检验，以更系统地识别冲突期间的价格结构变化。"
            "此外，当前 ACLED 数据为周度汇总数据，不能提供逐条事件的参与方和文字描述，"
            "因此它用于背景验证和事件周强度补充，而不是直接替代逐事件事件识别。"
        ),
        "",
        "后续改进可以围绕三条线展开：补充 ACLED/GDELT 的真实事件强度，加入更多市场控制变量，并对不同事件窗口进行 Bootstrap 稳健性检验。这样可以把当前可复现实证原型进一步扩展为更接近论文标准的完整研究。",
        "",
        "## 附录：主要结果表说明",
        "",
        "为便于检查和复核，本文保留以下主要结果表：",
        "",
        "- `outputs/oil_daily.csv`：清洗后的日度油价和收益率。",
        "- `outputs/events_candidate.csv`：候选事件、交易日映射和事件得分。",
        "- `outputs/event_results.csv`：三个窗口下的 CAR、t 值、p 值和显著性排序。",
        "- `outputs/its_results.csv`：单事件 ITS、DW/BP 诊断和 Newey-West 修正结果。",
        "- `outputs/multi_event_its_results.csv`：多事件 ITS 分离冲击结果。",
        "- `outputs/break_results.csv`：结构断点近似结果。",
        "- `outputs/acled_weekly_summary.csv`：ACLED 目标国家周度事件数和死亡人数。",
        "- `outputs/acled_country_summary.csv`：ACLED 目标国家事件数和死亡人数排序。",
        "- `outputs/acled_event_type_summary.csv`：ACLED 事件类型/子类型统计。",
        "- `outputs/acled_event_week_mapping.csv`：7 个油价事件对应周的 ACLED 冲突强度。",
        "- `figures/oil_prices_events.png` 与 `figures/oil_returns_events.png`：价格和收益率图。",
        "- `figures/acled_weekly_events.png` 与 `figures/acled_country_summary.png`：ACLED 汇总背景图。",
        "",
        "## 图表",
        "",
        "![WTI and Brent prices](../figures/oil_prices_events.png)",
        "",
        "![Daily returns](../figures/oil_returns_events.png)",
        "",
        "![ACLED weekly events](../figures/acled_weekly_events.png)",
        "",
        "![ACLED country summary](../figures/acled_country_summary.png)",
        "",
    ]
    (OUT_DIR / "T3_report.md").write_text("\n".join(lines), encoding="utf-8")


def write_engineering_notes(
    oil: pd.DataFrame,
    events: pd.DataFrame,
    event_results: pd.DataFrame,
    its_results: pd.DataFrame,
    multi_its: pd.DataFrame,
    breaks: pd.DataFrame,
    acled: dict[str, pd.DataFrame] | None = None,
) -> None:
    files = [
        ROOT / "DCOILWTICO.csv",
        ROOT / "DCOILBRENTEU.csv",
        DATA_DIR / "manual_events.csv",
        OUT_DIR / "oil_daily.csv",
        OUT_DIR / "events_candidate.csv",
        OUT_DIR / "event_results.csv",
        OUT_DIR / "its_results.csv",
        OUT_DIR / "multi_event_its_results.csv",
        OUT_DIR / "break_results.csv",
        OUT_DIR / "acled_weekly_summary.csv",
        OUT_DIR / "acled_country_summary.csv",
        OUT_DIR / "acled_event_type_summary.csv",
        OUT_DIR / "acled_event_week_mapping.csv",
        FIG_DIR / "oil_prices_events.png",
        FIG_DIR / "oil_returns_events.png",
        FIG_DIR / "acled_weekly_events.png",
        FIG_DIR / "acled_country_summary.png",
    ]
    file_table = pd.DataFrame(
        [
            {
                "file": str(path.relative_to(ROOT)),
                "exists": path.exists(),
                "size_bytes": path.stat().st_size if path.exists() else 0,
            }
            for path in files
        ]
    )
    shape_table = pd.DataFrame(
        [
            {"dataset": "oil_daily", "rows": len(oil), "columns": len(oil.columns)},
            {"dataset": "events_candidate", "rows": len(events), "columns": len(events.columns)},
            {"dataset": "event_results", "rows": len(event_results), "columns": len(event_results.columns)},
            {"dataset": "its_results", "rows": len(its_results), "columns": len(its_results.columns)},
            {"dataset": "multi_event_its_results", "rows": len(multi_its), "columns": len(multi_its.columns)},
            {"dataset": "break_results", "rows": len(breaks), "columns": len(breaks.columns)},
        ]
    )
    if acled and not acled["weekly"].empty:
        shape_table = pd.concat(
            [
                shape_table,
                pd.DataFrame(
                    [
                        {"dataset": "acled_raw_filtered", "rows": len(acled["raw"]), "columns": len(acled["raw"].columns)},
                        {"dataset": "acled_weekly_summary", "rows": len(acled["weekly"]), "columns": len(acled["weekly"].columns)},
                        {"dataset": "acled_country_summary", "rows": len(acled["country"]), "columns": len(acled["country"].columns)},
                        {"dataset": "acled_event_type_summary", "rows": len(acled["event_type"]), "columns": len(acled["event_type"].columns)},
                        {"dataset": "acled_event_week_mapping", "rows": len(acled["event_week"]), "columns": len(acled["event_week"].columns)},
                    ]
                ),
            ],
            ignore_index=True,
        )
        source_file = acled["source_file"]["source_file"].iloc[0]
        acled_note = (
            f"- 已检测到 ACLED 汇总 Excel：`{source_file}`。\n"
            f"- 原文件是中东地区按周聚合数据；当前脚本筛选 {EVENT_SAMPLE_START} 至 {EVENT_SAMPLE_END}，"
            f"目标国家为 {', '.join(TARGET_COUNTRIES)}。\n"
            "- 使用字段：`WEEK`、`COUNTRY`、`ADMIN1`、`EVENT_TYPE`、`SUB_EVENT_TYPE`、`EVENTS`、`FATALITIES`、`POPULATION_EXPOSURE`。\n"
            "- 它不是逐事件数据，因此没有完整的 `actor1/actor2/notes` 级别信息；当前用于背景统计和事件周强度映射。"
        )
    else:
        acled_note = "- 未检测到 ACLED 汇总 Excel，ACLED 背景统计不会生成。"
    lines = [
        "# T3 工程细节说明",
        "",
        "这份文件记录项目运行、数据文件、依赖包和可替换数据接口；上交版学术报告见 `outputs/T3_report.md`。",
        "",
        "## 运行环境",
        "",
        "- 操作系统/终端：Windows PowerShell。",
        "- Python：当前运行环境为 Python 3.13.5。",
        "- 已使用包：`pandas`、`numpy`、`scipy`、`statsmodels`、`matplotlib`。",
        "- 未强制使用包：`yfinance`、`ruptures`、`arch`、R `strucchange`。因此 Yahoo 期货和正式 Bai-Perron 多断点包不是当前主流程依赖。",
        "",
        "## 运行命令",
        "",
        "```powershell",
        "python src\\t3_oil_event_study.py",
        "```",
        "",
        "脚本会重新生成 CSV、图表和两份 Markdown 文件：`T3_report.md` 与 `T3_engineering_notes.md`。",
        "",
        "## 数据集与联网情况",
        "",
        "- 官方 FRED CSV 直连在本机运行时出现过连接超时，因此当前工作区保存了同 FRED 口径的本地 CSV：`DCOILWTICO.csv` 与 `DCOILBRENTEU.csv`。",
        "- `DCOILWTICO.csv` 字段为 `date,wti_price_usd`；`DCOILBRENTEU.csv` 字段为 `date,brent_price_usd`。",
        "- ACLED 需要账号/API key，当前没有账号导出文件，因此主流程使用 `data/manual_events.csv` 的人工核验事件清单。",
        acled_note,
        "- GDELT 当前未并入真实逐日导出；`manual_events.csv` 中的 `gdelt_goldstein` 与 `mentions` 是占位/演示字段。",
        "- 若之后取得真实数据，把 ACLED 导出放入 `data/acled_events.csv`，GDELT 导出放入 `data/gdelt_events.csv`，脚本会按 `event_date` 自动聚合并覆盖人工占位字段。",
        "",
        "## 输入与输出文件",
        "",
        file_table.to_markdown(index=False),
        "",
        "## 数据维度",
        "",
        shape_table.to_markdown(index=False),
        "",
        "## 脚本结构",
        "",
        "- `load_oil_data()`：读取 WTI/Brent CSV，合并共同交易日，计算对数收益率。",
        "- `load_events()`：读取人工事件清单，并在存在 ACLED/GDELT 导出时自动合并事件强度字段。",
        "- `event_study()`：估计市场模型，计算三个事件窗口的 AR/CAR、t 值、p 值和显著性排序。",
        "- `its_for_event()`：对每个事件和油价基准估计局部 ITS，并输出 DW、BP 与 Newey-West 修正结果。",
        "- `multi_event_its()`：在同一回归中纳入多个事件的 post 项，辅助分离密集事件影响。",
        "- `break_results()`：用分段线性 RSS/BIC 网格搜索近似结构断点检验。",
        "- `write_report()`：生成更偏论文风格的上交报告。",
        "- `write_engineering_notes()`：生成本文档，集中说明工程细节。",
        "",
        "## 当前实现边界",
        "",
        "- 报告中的事件标题仍应在最终提交前逐条替换为完整、可引用的新闻链接或 ACLED/GDELT 记录。",
        "- 结构断点部分是 Bai-Perron 思想的近似实现，不等价于正式多断点 Bai-Perron 检验。",
        "- 当前市场模型使用 WTI 与 Brent 互为市场因子，适合低依赖复现；若加入美元指数、商品指数或能源 ETF，可增强正常收益模型。",
        "",
    ]
    (OUT_DIR / "T3_engineering_notes.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    ensure_dirs()
    oil = load_oil_data()
    events = load_events(oil)
    acled = load_acled_aggregates(events)
    event_results = event_study(oil, events)
    its_results = its_for_event(oil, events)
    multi_its = multi_event_its(oil, events)
    breaks = break_results(oil, events)

    oil_out = oil[(oil["date"] >= EVENT_SAMPLE_START) & (oil["date"] <= EVENT_SAMPLE_END)].copy()
    oil_out.to_csv(OUT_DIR / "oil_daily.csv", index=False)
    events.to_csv(OUT_DIR / "events_candidate.csv", index=False)
    event_results.to_csv(OUT_DIR / "event_results.csv", index=False)
    its_results.to_csv(OUT_DIR / "its_results.csv", index=False)
    multi_its.to_csv(OUT_DIR / "multi_event_its_results.csv", index=False)
    breaks.to_csv(OUT_DIR / "break_results.csv", index=False)
    if not acled["weekly"].empty:
        acled["weekly"].to_csv(OUT_DIR / "acled_weekly_summary.csv", index=False)
        acled["country"].to_csv(OUT_DIR / "acled_country_summary.csv", index=False)
        acled["event_type"].to_csv(OUT_DIR / "acled_event_type_summary.csv", index=False)
        acled["event_week"].to_csv(OUT_DIR / "acled_event_week_mapping.csv", index=False)
    make_figures(oil, events, acled)
    write_report(oil, events, event_results, its_results, multi_its, breaks, acled)
    write_engineering_notes(oil, events, event_results, its_results, multi_its, breaks, acled)

    print("Generated:")
    for path in [
        OUT_DIR / "oil_daily.csv",
        OUT_DIR / "events_candidate.csv",
        OUT_DIR / "event_results.csv",
        OUT_DIR / "its_results.csv",
        OUT_DIR / "multi_event_its_results.csv",
        OUT_DIR / "break_results.csv",
        OUT_DIR / "acled_weekly_summary.csv",
        OUT_DIR / "acled_country_summary.csv",
        OUT_DIR / "acled_event_type_summary.csv",
        OUT_DIR / "acled_event_week_mapping.csv",
        OUT_DIR / "T3_report.md",
        OUT_DIR / "T3_engineering_notes.md",
        FIG_DIR / "oil_prices_events.png",
        FIG_DIR / "oil_returns_events.png",
        FIG_DIR / "acled_weekly_events.png",
        FIG_DIR / "acled_country_summary.png",
    ]:
        if path.exists():
            print(f"- {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

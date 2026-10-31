import pandas as pd


def latest_at_cutoff(fc: pd.DataFrame, cutoff_hhmm: str = "09:00") -> pd.DataFrame:
    """For each target half-hour, keep the newest forecast published at or before
    the day-ahead decision cutoff (D-1 at cutoff_hhmm, UTC == UK time in January).
    Forecasts published later are ignored, which avoids look-ahead leakage."""
    if fc.empty or "startTime" not in fc or "publishTime" not in fc:
        return pd.DataFrame(columns=["startTime", "publishTime", "forecast"])
    h, m = map(int, cutoff_hhmm.split(":"))
    fc = fc.copy()
    fc["cutoff"] = (fc["startTime"].dt.normalize() - pd.Timedelta(days=1)
                    + pd.Timedelta(hours=h, minutes=m))
    ok = fc[fc["publishTime"] <= fc["cutoff"]]
    if ok.empty:
        return pd.DataFrame(columns=["startTime", "publishTime", "forecast"])
    return (ok.sort_values(["startTime", "publishTime"])
              .drop_duplicates("startTime", keep="last")
              .sort_values("startTime")[["startTime", "publishTime", "generation"]]
              .rename(columns={"generation": "forecast"}))


def join(sel: pd.DataFrame, actual: pd.DataFrame) -> pd.DataFrame:
    if actual.empty or "startTime" not in actual:
        a = pd.DataFrame(columns=["startTime", "actual"])
    else:
        col = "actual" if "actual" in actual.columns else "generation"
        a = actual.rename(columns={col: "actual"}).drop_duplicates("startTime")[["startTime", "actual"]]
    if sel.empty or "startTime" not in sel:
        s = pd.DataFrame(columns=["startTime", "publishTime", "forecast"])
    else:
        s = sel
    return s.merge(a, on="startTime", how="outer").sort_values("startTime")


def summarize(df: pd.DataFrame) -> dict:
    if df.empty or "forecast" not in df or "actual" not in df:
        return {"n": 0}
    d = df.dropna(subset=["forecast", "actual"])
    if d.empty:
        return {"n": 0}
    e = d["forecast"] - d["actual"]
    ae = e.abs()
    actual_sum = d["actual"].sum()
    wape = round(ae.sum() / actual_sum * 100, 1) if actual_sum > 0 else 0.0
    if "publishTime" in d and d["publishTime"].notna().any():
        hrs = (d["startTime"] - d["publishTime"]).dt.total_seconds() / 3600
        med_hrs = round(hrs.dropna().median(), 1) if not hrs.dropna().empty else None
    else:
        med_hrs = None
    return {
        "n": int(len(d)),
        "mae": round(ae.mean(), 1),
        "rmse": round((e ** 2).mean() ** 0.5, 1),
        "bias": round(e.mean(), 1),
        "p95_abs_err": round(ae.quantile(0.95), 1),
        "wape_pct": wape,
        "median_horizon_h": med_hrs,
        "by_hour": {int(h): round(v, 1)
                    for h, v in ae.groupby(d["startTime"].dt.hour).mean().items()},
    }


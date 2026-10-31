import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import pandas as pd
import pytest
from logic import join, latest_at_cutoff, summarize

T = lambda s: pd.Timestamp(s, tz="UTC")


def test_picks_latest_forecast_before_cutoff_and_ignores_later_ones():
    fc = pd.DataFrame({
        "startTime": [T("2026-01-11 12:00")] * 4,
        "publishTime": [T("2026-01-09 20:00"), T("2026-01-10 08:00"),
                        T("2026-01-10 10:00"), T("2026-01-11 06:00")],
        "generation": [50, 100, 200, 300]})
    out = latest_at_cutoff(fc, "09:00")
    assert out.forecast.tolist() == [100]


def test_no_forecast_before_cutoff_gives_no_row():
    fc = pd.DataFrame({"startTime": [T("2026-01-11 12:00")],
                       "publishTime": [T("2026-01-10 09:30")], "generation": [1]})
    assert latest_at_cutoff(fc, "09:00").empty


def test_summary_metrics_baseline():
    sel = pd.DataFrame({"startTime": [T("2026-01-11 00:00"), T("2026-01-11 00:30")],
                        "publishTime": [T("2026-01-10 08:00")] * 2, "forecast": [110, 90]})
    act = pd.DataFrame({"startTime": sel.startTime, "generation": [100, 100]})
    s = summarize(join(sel, act))
    assert s["mae"] == 10 and s["bias"] == 0 and s["rmse"] == 10 and s["n"] == 2


def test_no_data_leakage_synthetic_multi_day():
    """Verify across multiple target days and publishing horizons that NO forecast
    published after D-1 09:00 UTC cutoff is ever selected."""
    rows = []
    base_delivery = T("2026-01-05 14:00")
    for offset in range(5):
        target_delivery = base_delivery + pd.Timedelta(days=offset)
        cutoff = target_delivery.normalize() - pd.Timedelta(days=1) + pd.Timedelta(hours=9)
        
        # 1. Very early forecast (D-2)
        rows.append({"startTime": target_delivery, "publishTime": cutoff - pd.Timedelta(days=1), "generation": 10})
        # 2. Morning before cutoff (D-1 08:30)
        rows.append({"startTime": target_delivery, "publishTime": cutoff - pd.Timedelta(minutes=30), "generation": 20})
        # 3. Exact cutoff boundary (D-1 09:00) -> Should be chosen as latest valid
        rows.append({"startTime": target_delivery, "publishTime": cutoff, "generation": 30})
        # 4. Leakage candidate 1: 1 second after cutoff (D-1 09:00:01) -> MUST NOT LEAK
        rows.append({"startTime": target_delivery, "publishTime": cutoff + pd.Timedelta(seconds=1), "generation": 999})
        # 5. Leakage candidate 2: afternoon of D-1 (D-1 15:00) -> MUST NOT LEAK
        rows.append({"startTime": target_delivery, "publishTime": cutoff + pd.Timedelta(hours=6), "generation": 888})
        # 6. Leakage candidate 3: delivery day morning (D 06:00) -> MUST NOT LEAK
        rows.append({"startTime": target_delivery, "publishTime": target_delivery - pd.Timedelta(hours=8), "generation": 777})

    fc = pd.DataFrame(rows)
    selected = latest_at_cutoff(fc, "09:00")
    
    # Exactly one row per target day
    assert len(selected) == 5
    # Every selected row must have generation == 30 (the one published exactly at 09:00)
    assert (selected["forecast"] == 30).all()
    # Confirm every publishTime is <= cutoff
    for _, r in selected.iterrows():
        expected_cutoff = r["startTime"].normalize() - pd.Timedelta(days=1) + pd.Timedelta(hours=9)
        assert r["publishTime"] <= expected_cutoff


def test_hand_verified_metrics_tiny_example():
    """Verify MAE, RMSE, Bias, p95, and WAPE against exact manual calculations:
    Points:
      1: Forecast 110, Actual 100 -> error +10, abs error 10
      2: Forecast  80, Actual 100 -> error -20, abs error 20
      3: Forecast 100, Actual 100 -> error   0, abs error  0
    Hand calculations:
      n = 3
      MAE = (10 + 20 + 0) / 3 = 10.0 MW
      RMSE = sqrt((100 + 400 + 0) / 3) = sqrt(166.6667) = 12.9 MW
      Bias = (+10 - 20 + 0) / 3 = -3.3 MW (forecast lower than actual wind, over-bought)
      p95_abs_err = 19.0 MW (quantile 0.95 on [0, 10, 20])
      wape_pct = (30 / 300) * 100 = 10.0%
      median_horizon_h = 24.0 h (horizon 24, 25, 26 -> median 25)
    """
    sel = pd.DataFrame({
        "startTime": [T("2026-01-15 00:00"), T("2026-01-15 01:00"), T("2026-01-15 02:00")],
        "publishTime": [T("2026-01-14 00:00"), T("2026-01-14 00:00"), T("2026-01-14 00:00")],
        "forecast": [110.0, 80.0, 100.0]
    })
    act = pd.DataFrame({
        "startTime": sel["startTime"],
        "generation": [100.0, 100.0, 100.0]
    })
    j = join(sel, act)
    res = summarize(j)
    
    assert res["n"] == 3
    assert res["mae"] == 10.0
    assert res["rmse"] == 12.9
    assert res["bias"] == -3.3
    assert res["p95_abs_err"] == 19.0
    assert res["wape_pct"] == 10.0


def test_edge_cases_empty_inputs():
    """Verify empty DataFrames do not raise exceptions."""
    empty_fc = pd.DataFrame(columns=["startTime", "publishTime", "generation"])
    empty_act = pd.DataFrame(columns=["startTime", "generation"])
    
    out_fc = latest_at_cutoff(empty_fc, "09:00")
    assert out_fc.empty
    assert list(out_fc.columns) == ["startTime", "publishTime", "forecast"]
    
    j = join(out_fc, empty_act)
    assert j.empty
    
    s = summarize(j)
    assert s == {"n": 0}


def test_edge_cases_zero_actuals_division():
    """Verify zero actuals do not raise ZeroDivisionError."""
    sel = pd.DataFrame({
        "startTime": [T("2026-01-15 00:00")],
        "publishTime": [T("2026-01-14 08:00")],
        "forecast": [50.0]
    })
    act = pd.DataFrame({
        "startTime": [T("2026-01-15 00:00")],
        "generation": [0.0]
    })
    j = join(sel, act)
    s = summarize(j)
    assert s["n"] == 1
    assert s["wape_pct"] == 0.0


def test_edge_cases_duplicate_rows():
    """Verify duplicate actuals or forecasts are deduplicated and do not multiply rows."""
    sel = pd.DataFrame({
        "startTime": [T("2026-01-15 12:00"), T("2026-01-15 12:00")],
        "publishTime": [T("2026-01-14 08:00"), T("2026-01-14 08:00")],
        "generation": [100.0, 100.0]
    })
    act = pd.DataFrame({
        "startTime": [T("2026-01-15 12:00"), T("2026-01-15 12:00")],
        "generation": [95.0, 95.0]
    })
    filtered_sel = latest_at_cutoff(sel, "09:00")
    assert len(filtered_sel) == 1
    j = join(filtered_sel, act)
    assert len(j) == 1


def test_edge_cases_missing_half_hours():
    """Verify hourly forecasts correctly align with half-hourly actuals (outer join)."""
    sel = pd.DataFrame({
        "startTime": [T("2026-01-15 00:00"), T("2026-01-15 01:00")],
        "publishTime": [T("2026-01-14 08:00"), T("2026-01-14 08:00")],
        "generation": [200.0, 250.0]
    })
    act = pd.DataFrame({
        "startTime": [T("2026-01-15 00:00"), T("2026-01-15 00:30"),
                      T("2026-01-15 01:00"), T("2026-01-15 01:30")],
        "generation": [190.0, 195.0, 240.0, 245.0]
    })
    filtered_sel = latest_at_cutoff(sel, "09:00")
    j = join(filtered_sel, act)
    assert len(j) == 4
    # Points with missing forecasts are dropped in summarize
    s = summarize(j)
    assert s["n"] == 2


def test_edge_cases_actuals_not_yet_available():
    """Verify future delivery day with forecasts but no actuals records properly."""
    sel = pd.DataFrame({
        "startTime": [T("2026-01-15 00:00")],
        "publishTime": [T("2026-01-14 08:00")],
        "generation": [200.0]
    })
    act = pd.DataFrame(columns=["startTime", "generation"])
    filtered_sel = latest_at_cutoff(sel, "09:00")
    j = join(filtered_sel, act)
    assert len(j) == 1
    assert pd.isna(j.iloc[0]["actual"])
    s = summarize(j)
    assert s == {"n": 0}


def test_custom_cutoff_configuration():
    """Verify cutoff logic with custom cutoff times (e.g. 12:00, 17:00)."""
    fc = pd.DataFrame({
        "startTime": [T("2026-01-15 14:00")] * 3,
        "publishTime": [T("2026-01-14 09:30"), T("2026-01-14 11:45"), T("2026-01-14 13:00")],
        "generation": [100, 200, 300]
    })
    # With 09:00 cutoff: all are after 09:00, empty result
    assert latest_at_cutoff(fc, "09:00").empty
    # With 12:00 cutoff: 11:45 is latest valid
    assert latest_at_cutoff(fc, "12:00")["forecast"].tolist() == [200]
    # With 17:00 cutoff: 13:00 is latest valid
    assert latest_at_cutoff(fc, "17:00")["forecast"].tolist() == [300]

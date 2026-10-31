import datetime as dt
import json
import os
from pathlib import Path

import httpx
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

try:
    from logic import join, latest_at_cutoff, summarize
except ImportError:
    from backend.logic import join, latest_at_cutoff, summarize


BASE = "https://data.elexon.co.uk/bmrs/api/v1/datasets"
CUTOFF = os.getenv("DECISION_CUTOFF_UTC", "09:00")  # configurable gate-closure proxy
from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(app: FastAPI):
    if CACHE_FILE.exists():
        try:
            _data()
        except Exception:
            pass
    yield


app = FastAPI(title="Wind forecast portal", lifespan=lifespan)
_cache: dict = {}



CACHE_FILE = Path(__file__).resolve().parent / ".cache_data.pkl"


def _stream(name: str, params: dict) -> list:
    last_err = None
    for attempt in range(3):
        try:
            r = httpx.get(f"{BASE}/{name}/stream", params=params, timeout=60)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last_err = e
            import time
            time.sleep(1)
    raise last_err


def _frame(rows: list) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    for c in ("startTime", "publishTime"):
        if c in df:
            df[c] = pd.to_datetime(df[c], utc=True)
    return df


def _fetch_all():
    act, fc = [], []
    # FUELHH actuals for all of January 2026
    a = dt.date(2026, 1, 1)
    end_a = dt.date(2026, 2, 1)
    while a < end_a:
        b = min(a + dt.timedelta(days=6), dt.date(2026, 1, 31))
        act += _stream("FUELHH", {"settlementDateFrom": a.isoformat(),
                                  "settlementDateTo": b.isoformat(),
                                  "fuelType": "WIND"})
        a = b + dt.timedelta(days=1)

    # WINDFOR forecasts from 2025-12-24 to 2026-02-01
    p = dt.date(2025, 12, 24)
    end_p = dt.date(2026, 2, 1)
    while p < end_p:
        p_next = min(p + dt.timedelta(days=7), end_p)
        fc += _stream("WINDFOR", {"publishDateTimeFrom": f"{p}T00:00Z",
                                  "publishDateTimeTo": f"{p_next}T00:00Z"})
        p = p_next

    a_df = _frame(act).drop_duplicates("startTime")
    f_df = _frame(fc)
    f_df = f_df[(f_df.startTime >= "2026-01-01") & (f_df.startTime < "2026-02-01")]
    res = (f_df.drop_duplicates(["startTime", "publishTime"]), a_df)
    try:
        import pickle
        with open(CACHE_FILE, "wb") as f:
            pickle.dump(res, f)
    except Exception:
        pass
    return res


import threading

_fetch_lock = threading.Lock()


def _data():
    if "d" not in _cache:
        with _fetch_lock:
            if "d" not in _cache:
                if CACHE_FILE.exists():
                    try:
                        import pickle
                        with open(CACHE_FILE, "rb") as f:
                            _cache["d"] = pickle.load(f)
                            return _cache["d"]
                    except Exception:
                        pass
                try:
                    _cache["d"] = _fetch_all()
                except Exception as e:
                    raise HTTPException(502, f"Elexon fetch failed: {e}")
    return _cache["d"]





@app.get("/api/health")
def health():
    return {"ok": True, "cutoff_utc": CUTOFF}


@app.get("/api/day")
def day(date: dt.date):
    if date < dt.date(2026, 1, 1) or date > dt.date(2026, 1, 31):
        raise HTTPException(400, "Date must be in January 2026 (2026-01-01 to 2026-01-31)")
    fc, act = _data()
    sel = latest_at_cutoff(fc, CUTOFF)
    d0 = pd.Timestamp(date, tz="UTC")
    in_day = lambda s: s[(s.startTime >= d0) & (s.startTime < d0 + pd.Timedelta(days=1))]
    j = join(in_day(sel), in_day(act))
    h, m = map(int, CUTOFF.split(":"))
    return {"cutoff": (d0 - pd.Timedelta(days=1) + pd.Timedelta(hours=h, minutes=m)).isoformat(),
            "points": json.loads(j.to_json(orient="records", date_format="iso")),
            "summary": summarize(j)}


@app.get("/api/metrics")
def metrics():
    fc, act = _data()
    return summarize(join(latest_at_cutoff(fc, CUTOFF), act))


static_dir = Path(__file__).resolve().parent / "static"
if static_dir.exists():  # built React app, mounted last so /api wins
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="web")


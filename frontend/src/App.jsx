import { useEffect, useState } from "react";
import { ResponsiveContainer, LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend } from "recharts";

const get = async (p) => {
  const r = await fetch(p);
  if (r.ok) return r.json();
  let msg = `${p}: ${r.status}`;
  try {
    const data = await r.json();
    if (data?.detail) {
      msg = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
    }
  } catch (_) {}
  throw new Error(msg);
};

const hhmm = (t) => new Date(t).toISOString().slice(11, 16);
const fmtNum = (v) => (typeof v === "number" ? v.toLocaleString() : v);

function Kpis({ s }) {
  if (!s || !s.n) return <p className="note">No overlapping forecast and actual data yet.</p>;
  const items = [
    ["MAE (MW)", fmtNum(s.mae), "Mean absolute error"],
    ["RMSE (MW)", fmtNum(s.rmse), "Root mean squared error"],
    [
      "Bias (MW)",
      fmtNum(s.bias),
      null,
      "Bias = average of (forecast - actual)"
    ],
    ["95th pct error (MW)", fmtNum(s.p95_abs_err), "95% of absolute errors are below this"],
    ["Error vs output (%)", `${s.wape_pct}%`, "WAPE (sum of errors / sum of actuals)"],
    ["Median lead time (h)", `${s.median_horizon_h}h`, "Decision cutoff to delivery interval"],
  ];
  return (
    <div className="kpis">
      {items.map(([k, v, desc, sub]) => (
        <div className="kpi" key={k} title={desc || undefined}>
          <b>{v}</b>
          <span>{k}</span>
          {sub && (
            <span style={{ display: "block", fontSize: "0.72rem", color: "var(--mute)", marginTop: 2 }}>
              {sub}
            </span>
          )}
        </div>
      ))}
    </div>
  );
}

export default function App() {
  const [date, setDate] = useState("2026-01-15");
  const [day, setDay] = useState(null);
  const [all, setAll] = useState(null);
  const [err, setErr] = useState("");
  const [theme, setTheme] = useState("auto");

  useEffect(() => {
    if (theme === "dark") document.documentElement.setAttribute("data-theme", "dark");
    else if (theme === "light") document.documentElement.setAttribute("data-theme", "light");
    else document.documentElement.removeAttribute("data-theme");
  }, [theme]);

  const loadDay = (d) => {
    if (!d) return;
    if (d < "2026-01-01" || d > "2026-01-31") {
      setErr("Date must be in January 2026 (2026-01-01 to 2026-01-31)");
      setDay(null);
      return;
    }
    setDay(null);
    setErr("");
    get(`/api/day?date=${d}`).then(setDay).catch((e) => setErr(e.message));
  };

  const loadMetrics = () => {
    get("/api/metrics").then(setAll).catch((e) => setErr(e.message));
  };

  useEffect(() => { loadMetrics(); }, []);
  useEffect(() => { loadDay(date); }, [date]);

  const hours = all?.by_hour
    ? Object.entries(all.by_hour).map(([h, mae]) => ({ h: `${String(h).padStart(2, "0")}:00`, mae }))
    : [];

  return (
    <main>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <h1>Wind forecast desk</h1>
        <button
          style={{
            background: "var(--card)",
            color: "var(--ink)",
            border: "1px solid var(--line)",
            borderRadius: 4,
            padding: "4px 10px",
            cursor: "pointer",
            font: "inherit",
            fontSize: "0.85rem",
          }}
          onClick={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}
          title="Toggle light / dark mode"
        >
          {theme === "dark" ? "☀️ Light mode" : "🌙 Dark mode"}
        </button>
      </div>
      <p className="sub">
        GB national wind generation, January 2026. Shows the latest available forecast at day-ahead decision cutoff (D-1 at 09:00 UTC) versus actual settlement generation.
      </p>
      {err && (
        <p className="err">
          Could not load data: {err}{" "}
          <button style={{ marginLeft: 8, cursor: "pointer", padding: "2px 8px" }} onClick={() => { loadDay(date); loadMetrics(); }}>Retry</button>
        </p>
      )}

      <h2>Delivery day</h2>
      <label>
        Day to buy for:{" "}
        <input
          type="date"
          min="2026-01-01"
          max="2026-01-31"
          value={date}
          onChange={(e) => setDate(e.target.value)}
        />
      </label>
      {day && (
        <p className="note">
          Forecast shown is the latest published at or before decision cutoff: <b>{new Date(day.cutoff).toUTCString()}</b>.
        </p>
      )}
      <div className="panel" style={{ height: 320, marginTop: 8 }}>
        {day ? (
          <ResponsiveContainer>
            <LineChart data={day.points.map((p) => ({ ...p, t: hhmm(p.startTime) }))}>
              <CartesianGrid stroke="var(--line)" />
              <XAxis dataKey="t" minTickGap={20} />
              <YAxis unit=" MW" width={80} />
              <Tooltip formatter={(value, name) => [value != null ? `${Number(value).toLocaleString()} MW` : "N/A", name]} />
              <Legend />
              <Line
                dataKey="forecast"
                name="Forecast at cutoff"
                stroke="var(--fc)"
                connectNulls
                dot={{ r: 2 }}
                strokeWidth={2}
              />
              <Line
                dataKey="actual"
                name="Actual"
                stroke="var(--act)"
                dot={false}
                strokeWidth={2}
              />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <p className="note">Loading day-ahead data from Elexon...</p>
        )}
      </div>

      <h2>Accuracy on {date}</h2>
      <Kpis s={day?.summary} />

      <h2>Accuracy across January 2026</h2>
      <Kpis s={all} />
      <p className="note" style={{ marginTop: 10, fontSize: "0.85rem" }}>
        <b>Bias interpretation:</b> Positive = forecast was higher than actual wind, so you would have under-bought. Negative = forecast was lower than actual wind, so you would have over-bought.
      </p>

      <h2>Average error by hour of day (January 2026)</h2>
      <div className="panel" style={{ height: 260 }}>
        <ResponsiveContainer>
          <BarChart data={hours}>
            <CartesianGrid stroke="var(--line)" />
            <XAxis dataKey="h" minTickGap={20} />
            <YAxis unit=" MW" width={80} />
            <Tooltip formatter={(value) => [`${Number(value).toLocaleString()} MW`, "MAE"]} />
            <Bar dataKey="mae" name="MAE" fill="var(--fc)" />
          </BarChart>

        </ResponsiveContainer>
      </div>
    </main>
  );
}


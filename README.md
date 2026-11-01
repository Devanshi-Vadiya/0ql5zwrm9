# Wind Forecast Desk

A web application designed for a UK energy utility's day-ahead trading desk:
1. **Decision-Time Forecast**: Displays the latest national wind generation forecast available before the day-ahead decision cutoff (D-1 at 09:00 UTC).
2. **Quantitative Accuracy**: Evaluates forecast accuracy against actual generation across January 2026 delivery days so traders can price and factor in forecast error.

**Data Source**: National-level wind generation from Elexon BMRS:
- **Actuals**: `FUELHH` stream (`fuelType=WIND`, half-hourly settlement periods).
- **Forecasts**: `WINDFOR` stream (`publishDateTime` and `startTime`, hourly resolution).
- **Period**: Delivery days in January 2026 (`2026-01-01` to `2026-01-31`).

**AI Disclosure**: This project was developed with assistance from AI coding tools (Claude / Anthropic).

---

## File and Directory Structure

- `backend/`
  - `logic.py`: Core pure-function calculation module: cutoff selection (`latest_at_cutoff`), time-series alignment (`join`), and quantitative accuracy metrics (`summarize`). Note on Bias: `Bias = average of (forecast - actual)`. Positive bias means forecast was higher than actual wind, so the desk under-bought day-ahead; negative bias means forecast was lower than actual wind, so the desk over-bought.
  - `main.py`: FastAPI application: handles Elexon BMRS streaming ingestion, thread-safe in-memory caching, API endpoints (`/api/health`, `/api/day`, `/api/metrics`), and static web asset serving.
  - `.cache_data.pkl`: Bundled local snapshot of January 2026 Elexon data (FUELHH and WINDFOR) to eliminate cold-start timeouts.
  - `requirements.txt`: Python package dependencies (`fastapi`, `uvicorn`, `httpx`, `pandas`, `pytest`).
  - `tests/`
    - `test_logic.py`: 11 tests covering data-leakage prevention on synthetic data, manual metric verification (MAE, RMSE, Bias, p95, WAPE), edge cases (empty inputs, zero actuals, missing intervals, duplicate rows), and custom cutoffs.
    - `test_api.py`: 6 integration tests covering `/api/health`, `/api/metrics`, and date validation/error handling on `/api/day`.
  - `static/`: Production build output of the React frontend, mounted by FastAPI.
- `frontend/`
  - `src/App.jsx`: Main React dashboard with day picker, synchronized Recharts line chart (connecting hourly forecasts across settlement intervals), KPI cards, and hourly error breakdown.
  - `src/main.jsx`: React application entry point.
  - `index.html`: Shell HTML with theme CSS tokens supporting both light and dark modes (`prefers-color-scheme`).
  - `vite.config.js`: Vite build configuration with local API proxy (`/api` -> `http://localhost:8000`).
  - `package.json` & `package-lock.json`: Frontend dependencies (`react`, `react-dom`, `recharts`, `vite`).
- `Dockerfile`: Multi-stage Docker build (compiles React via Node 20, then serves via lightweight Python 3.12 slim container).
- `.dockerignore`: Excludes build artifacts, caches, and test files from the container image.

---

## How to Run

### Option 1: Docker (Recommended)

Build and run the containerized application:

```bash
docker build -t wind-desk .
docker run -p 8000:8000 -e PORT=8000 wind-desk
```

Open [http://localhost:8000](http://localhost:8000) in your browser.

### Option 2: Local Development

**1. Start the Backend:**

```bash
cd backend
pip install -r requirements.txt
python -m uvicorn main:app --reload --port 8000
```

The API will be available at [http://127.0.0.1:8000](http://127.0.0.1:8000) (interactive OpenAPI docs at `/docs`).

**2. Start the Frontend (in a separate terminal):**

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173) (Vite dev server proxies `/api` requests to port 8000).

### Option 3: Run the Test Suite

Run all unit and integration tests:

```bash
pytest backend/tests -v
```

---

## Configuration

- **Decision Cutoff**: Defaults to `09:00` UTC on D-1. Override by setting the environment variable:
  ```bash
  DECISION_CUTOFF_UTC=12:00
  ```

---

## Deployment Guide

### Heroku (Container Deployment)

1. Authenticate and create a Heroku app:
   ```bash
   heroku login
   heroku container:login
   heroku create your-wind-desk-app
   ```
2. Build and release the container image:
   ```bash
   heroku container:push web -a your-wind-desk-app
   heroku container:release web -a your-wind-desk-app
   ```
3. Open the live app:
   ```bash
   heroku open -a your-wind-desk-app
   ```

*Note on Cold Starts & Timeouts*: Heroku enforces a strict 30-second router timeout (Error H12). Because fetching a full month of historical stream data from Elexon requires ~11 sequential HTTP requests taking 40–60 seconds, bundling `.cache_data.pkl` in the container ensures instant boot times (< 1 second) and eliminates H12 timeouts.

### Vercel Deployment

Deploying Python backends to Vercel requires configuring Vercel Serverless Functions:
1. Add a `vercel.json` routing `/api/(.*)` to `backend/main.py` using `@vercel/python`.
2. Build frontend static files to `frontend/dist`.
3. *Important*: Vercel Hobby serverless functions have a 10-second execution timeout. Pre-caching or bundling data is mandatory to prevent 504 Gateway Timeout errors on initial load.

---

## Live Application

Live app: <add link>


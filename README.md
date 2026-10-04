# MarketScope

Site-suitability analysis for MSMEs in Panabo City. A user picks a spot on the map and a business type. The backend scores the spot on zoning, flood hazard, and market saturation (competition, road access, nearby anchors, building density). The scores are combined with AHP weights into a viability score and a report.

- **Frontend:** React + Vite + Leaflet, in `marketscope-frontend/`. Deployed on Vercel.
- **Backend:** FastAPI + PostgreSQL + geopandas, in `marketscope-backend/`. Deployed on Render.

## Running locally

**Backend** (needs PostgreSQL running locally, or `DATABASE_URL` pointing at a database):

```bash
cd marketscope-backend
python -m venv .venv
.venv/Scripts/activate            # Windows. On macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python main.py                    # http://localhost:8000. Tables are created on first start.
```

Settings come from environment variables. `marketscope-backend/.env.example` lists all of them with their defaults.

**Frontend:**

```bash
cd marketscope-frontend
npm install
npm run dev                       # http://localhost:5173. Talks to localhost:8000 automatically.
```

**Tests:** `cd marketscope-backend && python -m unittest discover tests`

## Project map

### Backend: `marketscope-backend/`

```
main.py            App entry point: startup work (tables, DB pool, cache preloads) and router registration
core/              config.py (every env var), database.py (DB config + pool), paths.py, security.py (admin token)
db/                schema.py (table creation, migrations, AHP seed data), queries.py (shared read queries),
                   trend_queries.py (SQL for the background trend scan tables)
models/            requests.py: request bodies for every route
constants/         geo.py (Panabo bounds, anchors, zoning boxes), msme.py (business categories + scoring profiles)
utils/             dates.py, values.py, geo.py (distance/bounds), geo_libs.py (optional geopandas/shapely import)
services/          The logic behind the routes (see the table below)
routers/           API routes, one file per feature
data/              panabo.pbf (OpenStreetMap extract), flood/ (hazard GeoJSON), fallback/ (older hazard data)
scripts/           One-off debug scripts (DB checks, PDF test). Not used by the app.
tests/             Unit tests
```

| Router file | Routes |
|---|---|
| `routers/health.py` | `GET/HEAD /` |
| `routers/auth.py` | `/register`, `/login`, `/forgot-password`, `/reset-password`, `/reset-password-direct` |
| `routers/users.py` | `/users/{id}` profile, history, onboarding |
| `routers/trends.py` | `GET /users/{id}/trends`, `POST /users/{id}/trends/rescan`, `GET /trends/results/{id}`, `GET /trends/scan-status` |
| `routers/analysis.py` | `POST /analyze`, `POST /competitors/preview` |
| `routers/reports.py` | `POST /reports/generate` |
| `routers/spaces.py` | `/spaces/*` (user submissions, map markers) and `/admin/spaces/*` |
| `routers/admin_auth.py` | `POST /admin/login` |
| `routers/admin_users.py` | `/admin/users` |
| `routers/msmes.py` | `/admin/custom-msmes` |
| `routers/verified_features.py` | `/admin/verified-local-features` |
| `routers/ahp_admin.py` | `/admin/ahp/matrix`, `/admin/ahp/matrices` |

### Frontend: `marketscope-frontend/src/`

```
main.jsx, App.jsx  Entry point; App holds the session, the active tab, and which page is shown
pages/             One file per screen: AuthPages (landing/login), Home (map + analysis), Report, History,
                   Trends, Profile, AdminPanel
components/
  layout/          Header, BottomNav, AdminNavbar
  common/          Modal, AnalysisLoader, TourSpotlight (shared UI pieces)
  map/             MapPicker
  admin/           Admin panel tabs: AhpWeightsManager, FloodZoneManager, ZoningManager, ZoningEditor
  onboarding/      OnboardingModal, TrendPreferencesGate
  trends/          TrendSpotCard (one scanned spot on the Trends page)
  spaces/          SpaceSubmissionModal
lib/api.js         Backend URL: VITE_API_BASE_URL, else localhost:8000 locally, else the Render URL
constants/         layoutIds.js, motion.js (shared animation easing)
utils/             businessTypes, coordinates, mapTheme, hazardStyle, scoreTone, trendPreferences, useIsDesktop
styles/            index.css (Tailwind), auth.css (landing/login), app/ (main app styles, see below)
public/            panabo_hazard_5yr.geojson (map overlay), sw.js (map tile cache)
```

`styles/app/index.css` imports `01-…` through `22-…` in order. The order matters: later files override earlier ones. They are the original `App.css` cut at its section headings, so each file is named after what it styles: `07-map-overlays.css`, `11-report-dossier.css`, `17-profile-page.css`, and so on.

## Where to look when something breaks

| Symptom | Backend | Frontend |
|---|---|---|
| Viability score looks wrong | `services/analysis.py` (`perform_analysis` combines the factors) | `pages/Report.jsx` |
| Competition / road / anchor / building sub-score | `services/scoring.py` (`_score_*` functions) | |
| Competitors missing or wrong | `services/osm_data.py` (OSM data), `db/queries.py` (`fetch_custom_msmes`) | |
| Flood hazard score | `services/hazard.py`, `data/flood/panabo_hazard_5yr.geojson` | `utils/hazardStyle.js`, `public/panabo_hazard_5yr.geojson` |
| AHP weights | `services/ahp.py` (math), `services/ahp_weights.py` (cache), `routers/ahp_admin.py` | `components/admin/AhpWeightsManager.jsx` |
| Business categories / profiles | `constants/msme.py` | `utils/businessTypes.js` |
| Trend analysis | `routers/trends.py`, `services/trend_*.py`, `db/trend_queries.py` (see below) | `pages/Trends.jsx`, `components/trends/TrendSpotCard.jsx` |
| Login, register, password reset | `routers/auth.py`, `services/auth_service.py`, `services/email.py` | `pages/AuthPages.jsx` |
| Admin panel data | `routers/admin_*.py`, `routers/msmes.py`, `routers/verified_features.py` | `pages/AdminPanel.jsx` |
| Commercial spaces on the map | `routers/spaces.py`, `services/spaces.py` | `components/spaces/SpaceSubmissionModal.jsx`, `pages/Home.jsx` |
| Reports / PDF | `routers/reports.py`, `services/reporting.py` | `pages/Report.jsx` |
| Database tables / columns | `db/schema.py` | |
| Slow first request after deploy | `main.py` lifespan: geo caches load in a background thread | |
| Frontend can't reach the backend | `core/config.py` (`MARKETSCOPE_ALLOWED_ORIGINS`) | `lib/api.js` |

## How trend analysis works

The Trends page shows high-chance spots for the user's business, found by scans that run in the background with the same engine as a manual scan (`perform_analysis`).

1. **Which businesses.** `services/trend_scoring.py` picks the user's primary business, plus up to 2 other business types that pass at least 2 of 3 profile checks (capital, setup, payback).
2. **Which spots.** `services/trend_candidates.py` lists every For Rent/For Sale listing, the Panabo landmarks, and a grid of points about 330 m apart over the commercial zone. Business types allowed in the agri-industrial zone get that zone's grid too.
3. **Scanning.** `services/trend_scan.py` keeps a queue with one worker thread. For each business type it runs `perform_analysis` on every spot (radius 340 m, no history row saved). Each result goes into `trend_scan_results`, and status and progress go into `trend_scan_runs`.
4. **Cache.** A business type whose last finished run is younger than `MARKETSCOPE_TREND_SCAN_FRESH_HOURS` (24) is not scanned again. Its saved results are reused, and they are shared by every user. Scans are queued on login, when trend preferences are saved, when Trends is opened, and from "Rescan now".
5. **What the page shows.** `services/trend_recommendations.py` returns the saved spots scoring at least `MARKETSCOPE_TREND_HIGH_CHANCE_MIN_SCORE` (70), ranked by viability score. "View full report" opens the saved report, so no rescan is needed.

**Debugging:** `GET /trends/scan-status` lists the newest run of each business type. Backend logs start with `[trend-scan]`. In SQL: `SELECT * FROM trend_scan_runs;`

## Flood hazard data

The backend loads the first file that exists from this list (`services/hazard.py`):

1. `marketscope-backend/data/flood/panabo_hazard_5yr.geojson`
2. `marketscope-backend/panabo_hazard_5yr.geojson`
3. `marketscope-frontend/public/panabo_hazard_5yr.geojson`
4. `marketscope-backend/data/fallback/DavaoDelNorte/DavaoDelNorte_Flood_5year.shp`
5. `marketscope-backend/data/fallback/Davao_del_Norte.geojson`

Each feature needs a `Var` property: **1 = Very High, 2 = High, 3 = Moderate** flood hazard. The frontend draws its overlay from its own copy in `marketscope-frontend/public/`. When you replace the hazard data, update both copies.

## Known issues

These were found during the reorganization and left as they are, so behavior stays unchanged:

- **Zoning/flood layer uploads have no backend.** `FloodZoneManager.jsx` and `ZoningManager.jsx` call `/admin/zoning-layers` (list, `/upload`, `/{id}`), but those routes don't exist in the backend, so saving an uploaded layer fails.
- **The CLUP admin tab can't be reached.** `AdminPanel.jsx` renders `ZoningManager` for the `clup` tab, but `AdminNavbar.jsx` has no button for it.
- **Default admin credentials.** If the `MARKETSCOPE_ADMIN_*` variables aren't set, the admin login is `admin@marketscope.local` / `admin123` with a fixed token. Set them on Render.
- **`MARKETSCOPE_RESET_CODE_DEV_MODE` does nothing.** `routers/auth.py` reads it but only runs `pass`.
- **Windows console encoding.** The DB startup logs print ✓/✗. If stdout isn't UTF-8 (for example when output is piped to a file), that print fails and the DB connection is reported as failed. Set `PYTHONIOENCODING=utf-8` when redirecting output.
- **Unused code.** `HAZARD_ZONES` (`services/hazard.py`) and `get_generic_nearby_pbf_competitors` (`services/osm_data.py`) aren't used anywhere.
- **Unused root `package.json` / `node_modules`.** The frontend has its own. The ones at the repo root aren't used by anything.
- **37 ESLint problems** (`npm run lint` in the frontend), mostly unused variables.

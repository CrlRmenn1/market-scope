# MarketScope

Site-suitability analysis for MSMEs in Panabo City. A user picks a spot on the map and a business type. Zoning decides whether the business is allowed there at all. The backend then scores flood hazard and market potential (competition, road access, nearby anchors, building density) and combines them with AHP weights into a viability score, a verdict and a report that explains the score. [docs/ENGINE_METHODOLOGY.md](docs/ENGINE_METHODOLOGY.md) has every formula and where it comes from.

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
| `routers/auth.py` | `/register`, `/login`, `/forgot-password`, `/reset-password` |
| `routers/users.py` | `/users/{id}` profile, history, onboarding |
| `routers/trends.py` | `GET /users/{id}/trends`, `POST /users/{id}/trends/rescan`, `GET /trends/results/{id}`, `GET /trends/scan-status` |
| `routers/analysis.py` | `POST /analyze`, `POST /competitors/preview` |
| `routers/reports.py` | `POST /reports/generate` |
| `routers/spaces.py` | `/spaces/*` (user submissions, map markers) and `/admin/spaces/*` |
| `routers/admin_auth.py` | `POST /admin/login` |
| `routers/admin_users.py` | `/admin/users` |
| `routers/msmes.py` | `/admin/custom-msmes` |
| `routers/verified_features.py` | `/admin/verified-local-features` |
| `routers/map_layers.py` | `/admin/map-layers/*` (hazard/zoning layer CRUD, import, activate) and the public `GET /map-layers/active` |

### Frontend: `marketscope-frontend/src/`

```
main.jsx, App.jsx  Entry point; App holds the session, the active tab, and which page is shown
pages/             One file per screen: AuthPages (landing/login), Home (map + analysis), Report, History,
                   Trends, Profile, AdminPanel (admin console shell)
  admin/           Admin console pages: MsmesPage, UsersPage, SpacesPage, MapLayersPage
components/
  layout/          Header, BottomNav, AdminNavbar
  common/          Modal, AnalysisLoader, TourSpotlight (shared UI pieces)
  map/             MapPicker
  admin/           AdminLayout (desktop sidebar / mobile tab bar), adminNav, ui/ (shared admin pieces,
                   useAdminApi), MapLayerStudio + imageTraceOverlay (Map Layers)
  onboarding/      OnboardingModal, TrendPreferencesGate
  trends/          AreaMap, SuggestionCard (the Trends page's map and business cards)
  spaces/          SpaceSubmissionModal
lib/api.js         Backend URL: VITE_API_BASE_URL, else localhost:8000 locally, else the Render URL
constants/         layoutIds.js, motion.js (shared animation easing)
utils/             businessTypes, coordinates, mapTheme, hazardStyle, zoneStyle, mapLayers, scoreTone,
                   trendPreferences, useIsDesktop
styles/            index.css (Tailwind), auth.css (landing/login), app/ (main app styles, see below)
public/            sw.js (map tile cache)
```

`styles/app/index.css` imports `01-…` through `22-…` in order. The order matters: later files override earlier ones. They are the original `App.css` cut at its section headings, so each file is named after what it styles: `07-map-overlays.css`, `11-report-dossier.css`, `17-profile-page.css`, and so on.

## Where to look when something breaks

| Symptom | Backend | Frontend |
|---|---|---|
| Viability score looks wrong | `services/analysis.py` (`perform_analysis` combines the factors). Measure the engine across the city with `scripts/calibrate_engine.py`. | `pages/Report.jsx` |
| Competition / road / anchor / building sub-score | `services/scoring.py` (`_score_*` functions), `services/value_functions.py`, every number in `constants/engine.py` | |
| Verdict wording or cut-offs | `services/verdict.py`, `constants/engine.py` | `utils/verdict.js` |
| Anchors missing or wrong | `services/anchors.py` (merges admin, original and OSM anchors), `routers/anchors.py` | `pages/admin/AnchorsPage.jsx`, `components/admin/AnchorsMap.jsx` |
| Competitors missing or wrong | `services/osm_data.py` (OSM data, including tags in `other_tags`), `db/queries.py` (`fetch_custom_msmes`) | |
| Flood hazard score | `services/hazard.py`, the active hazard layer in `map_layers` | `utils/hazardStyle.js` |
| Zoning check | `services/zoning.py`, the active zoning layer in `map_layers`, allowed uses in `zoning_allowed_uses` (zones in `constants/map_layers.py`) | `utils/zoneStyle.js`, `components/admin/ZoningAllowedUses.jsx` |
| Map layers (admin) | `routers/map_layers.py`, `services/map_layers.py`, `db/map_layer_queries.py` | `components/admin/MapLayerStudio.jsx` |
| AHP weights | `services/ahp.py` (math), `services/ahp_weights.py` (cache), provisional matrices in `db/schema.py`. Import real answers with `scripts/import_ahp_judgments.py`, then restart the backend. | |
| Business categories / profiles | `constants/msme.py` | `utils/businessTypes.js` |
| Trend analysis | `routers/trends.py`, `services/trend_*.py`, `db/trend_queries.py` (see below) | `pages/Trends.jsx`, `components/trends/AreaMap.jsx`, `components/trends/SuggestionCard.jsx` |
| Login, register, password reset | `routers/auth.py`, `services/auth_service.py`, `services/email.py` | `pages/AuthPages.jsx` |
| Admin panel | `routers/admin_*.py`, `routers/msmes.py`, `routers/spaces.py` | `pages/AdminPanel.jsx`, `pages/admin/`, `components/admin/` |
| Commercial spaces on the map | `routers/spaces.py`, `services/spaces.py` | `components/spaces/SpaceSubmissionModal.jsx`, `pages/Home.jsx` |
| Reports / PDF | `routers/reports.py`, `services/reporting.py` | `pages/Report.jsx` |
| Database tables / columns | `db/schema.py` | |
| Slow first request after deploy | `main.py` lifespan: geo caches load in a background thread | |
| Frontend can't reach the backend | `core/config.py` (`MARKETSCOPE_ALLOWED_ORIGINS`) | `lib/api.js` |

## How trend analysis works

The Trends page ("Business Trend Suggestions") answers "which businesses fit this area?", from scans that run in the background with the same engine as a manual scan (`perform_analysis`). It describes current conditions. Nothing measures change over time, because the project has no historical data, and older runs are deleted.

1. **Which businesses.** Every business type, because suggestions compare them within an area. `services/trend_preferences.py` queues the user's primary business first, then the ones usually run in their preferred setup (`TYPICAL_SETUP` in `constants/msme.py`), then the rest. Preferences never change a score.
2. **Which spots.** `services/trend_candidates.py` lists every For Rent/For Sale listing, the curated anchors and major OSM anchors, and a grid of points about 330 m apart inside every zone of the active zoning layer where the business type is allowed (the admin's allowed-uses table).
3. **Scanning.** `services/trend_scan.py` keeps a queue with one worker thread. For each business type it runs `perform_analysis` on every spot (no history row saved). Each result goes into `trend_scan_results`, and status and progress go into `trend_scan_runs`.
4. **Cache.** A business type whose last finished run is younger than `MARKETSCOPE_TREND_SCAN_FRESH_HOURS` (24), and started after the last change to anything that affects scores (an active map layer, anchors, competitors, or the engine version), is not scanned again. Its saved results are reused, and they are shared by every user. Scans are queued on login, when trend preferences are saved, when Trends is opened, and from "Rescan now". A run where more than 20% of the spots fail counts as failed and doesn't replace the previous good run, and a failed run isn't retried automatically for 30 minutes.
5. **What the page shows.** `services/trend_suggestions.py` groups each permitted spot under its nearest named place from `panabo.pbf`, so an area is "around Gredu", not a barangay boundary. A business's area score is the average of its best 3 spots there, and it is a suggestion when that lands in the Highly Suitable class. Businesses with enough competitor data rank first, then by score. `services/trend_recommendations.py` also returns the best areas for the primary business. "View best spot report" opens the saved report, so no rescan is needed. [ENGINE_METHODOLOGY.md](docs/ENGINE_METHODOLOGY.md) explains the rules and thresholds.

**Debugging:** `GET /trends/scan-status` lists the newest run of each business type. Backend logs start with `[trend-scan]`. In SQL: `SELECT * FROM trend_scan_runs;`

## Map layers (flood hazard and zoning)

Flood hazard and zoning areas are stored in the database, in the `map_layers` table (`db/schema.py`). Each layer is a GeoJSON FeatureCollection of polygons, and every polygon has a `zone_class`:

- **Stacking:** where shapes overlap, the shape on top of the layer wins (`services/layer_stack.py`); new shapes go on top.
- **Hazard:** `very_high`, `high`, `moderate` (scores 5 / 12 / 18; outside every polygon is Low Risk, 25).
- **Zoning:** the 23 zones of the Panabo City Integrated Zoning Map C.Y. 2020-2029 (`ZONING_CLASSES` in `constants/map_layers.py`, e.g. `general_commercial`, `commercial_2`, `tourism`, `general_residential`, `industrial_1`, `agri_industrial`, `quarry`). Zoning is a hard constraint: where a business type isn't allowed, its score is 0 and the verdict is Not Permitted. Outside every polygon the zoning is unverified, which isn't a ban, but the site can't be Highly Suitable. Which business types are allowed where is the `zoning_allowed_uses` table, edited in Admin → Map layers → Zoning → Allowed businesses (seeded once from `DEFAULT_ZONING_ALLOWED_USES`). The six older classes (`commercial`, `mixed_use`, …) are converted once on startup (`LEGACY_ZONE_CLASSES`).

One layer per type is active, and scans use only the active ones. With no active zoning layer every spot's zoning is unverified. With no active hazard layer, flood hazard is left out of the score and the report says so; the site isn't called safe.

**Admin workflow (Admin → Map layers):** draw shapes on the map, trace them over a PDF/PNG/JPG of a printed map (the image stays in the browser and is not saved), or import a GeoJSON, KML or zipped shapefile (the original file is saved in `map_layer_files` and can be downloaded again). On every save the backend keeps only polygons, repairs broken shapes and trims them to the Panabo main area (`PANABO_BOUNDS`). Activating or changing the active layer reloads the scoring caches and marks saved trend scans stale.

**Built-in layers:** on first startup `seed_builtin_map_layers()` (`services/map_layers.py`) copies the old flood file (`data/flood/panabo_hazard_5yr.geojson`, original file kept) and the two `ZONING_LAYERS` boxes into the database as active "Built-in" layers, then sets `map_layers_seeded` in `app_flags` so it never runs again. After that the flood file is only a seed source.

**Debugging:** backend logs start with `[map-layers]`. In SQL: `SELECT id, category, name, origin, is_active FROM map_layers;`

## Known issues

These were found during the reorganization and left as they are, so behavior stays unchanged:

- **Pending user spaces count as available.** `fetch_active_space_markers_for_analysis` (`services/spaces.py`) includes `pending` user submissions, so they appear on the map and in trend scans before an admin approves them.
- **Admin secrets are required in production.** On Render, admin access stays locked until `MARKETSCOPE_ADMIN_PASSWORD` and `MARKETSCOPE_ADMIN_TOKEN` are set to strong values (see `marketscope-backend/.env.example`).
- **`MARKETSCOPE_RESET_CODE_DEV_MODE` does nothing.** `routers/auth.py` reads it but only runs `pass`.
- **Windows console encoding.** The DB startup logs print ✓/✗. If stdout isn't UTF-8 (for example when output is piped to a file), that print fails and the DB connection is reported as failed. Set `PYTHONIOENCODING=utf-8` when redirecting output.
- **Unused user columns.** `users.startup_capital` and `users.target_payback_months` are no longer read or written (those preferences were removed). Existing databases still have them; drop them with `ALTER TABLE users DROP COLUMN startup_capital, DROP COLUMN target_payback_months;` if wanted.
- **Unused code.** `get_generic_nearby_pbf_competitors` (`services/osm_data.py`) isn't used anywhere.
- **Unused root `package.json` / `node_modules`.** The frontend has its own. The ones at the repo root aren't used by anything.
- **30 ESLint problems** (`npm run lint` in the frontend), mostly unused variables.

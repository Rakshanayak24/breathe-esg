# Breathe ESG — Data Ingestion Platform

A Django REST + React prototype for ingesting, normalizing, and analyst-reviewing emissions data from SAP, utility portals, and corporate travel platforms.

## Live Demo

- **App**: https://breathe-esg.onrender.com

Demo credentials (all passwords: `breathe2024`):
| Username | Role |
|----------|------|
| `analyst` | Analyst — uploads, reviews |
| `approver` | Approver — approves batches |
| `admin` | Superuser — Django admin |

## Quick Start (Local)

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

python manage.py migrate
python manage.py setup_demo     # creates org + demo users
python manage.py runserver
```

API will be at `http://localhost:8000/api/`

### Frontend

```bash
cd frontend
npm install
npm start
```

App will be at `http://localhost:3000`

## Sample Data

Three realistic sample files are in `sample_data/`:

| File | Source | Rows | Notes |
|------|--------|------|-------|
| `sap_fuel_procurement_Q1FY25.txt` | SAP MB51 | 30 | Pipe-delimited, German date format, includes reversal + suspicious rows |
| `utility_electricity_Q1FY25.csv` | BESCOM/MSEDCL | 18 | HT/LT connections, CT multipliers, non-calendar billing periods |
| `travel_corporate_Q1FY25.csv` | Navan | 37 | Flights/hotels/ground, IATA-based distance calc, cabin classes |

Upload these via the Upload page or directly via the API.

## API Reference

```
POST /api/auth/login/           { username, password } → { token, user, organisation }
GET  /api/auth/me/
POST /api/auth/logout/

GET  /api/batches/              List batches (filter: source_type, status)
POST /api/batches/upload/       Multipart: source_type + file
GET  /api/batches/{id}/
POST /api/batches/{id}/approve/ → creates + locks EmissionRecords
POST /api/batches/{id}/reject/
GET  /api/batches/{id}/rows/    (filter: status)

GET  /api/emission-records/     (filter: scope, category)
GET  /api/dashboard/stats/
```

## Architecture

```
frontend/          React SPA
backend/
  breathe_esg/     Django project settings + URLs
  ingestion/
    models.py      Organisation, IngestionBatch, RawSAPRow, RawUtilityRow,
                   RawTravelRow, EmissionRecord
    parsers_sap.py     SAP flat-file parser
    parsers_utility.py Utility CSV parser
    parsers_travel.py  Travel CSV parser
    calculators.py     Emission factor math
    views.py           DRF ViewSets + actions
    serializers.py     DRF serializers
  emissions/       Reserved for reporting/export features
sample_data/       Realistic sample files
docs/
  MODEL.md         Data model rationale
  DECISIONS.md     Every ambiguity resolved
  TRADEOFFS.md     What was deliberately not built
  SOURCES.md       Real-world research on each source
```

## Deployment (Render)

### Backend (Web Service)
- **Build command**: `pip install -r requirements.txt && python manage.py collectstatic --noinput && python manage.py migrate`
- **Start command**: `gunicorn breathe_esg.wsgi:application --workers 2 --bind 0.0.0.0:$PORT`
- **Root directory**: `backend`
- **Environment variables**:
  ```
  SECRET_KEY=<generate with: python -c "import secrets; print(secrets.token_hex(50))">
  DEBUG=False
  DATABASE_URL=<from Render PostgreSQL>
  CORS_ALLOWED_ORIGINS=https://your-frontend.onrender.com
  ALLOWED_HOSTS=your-backend.onrender.com
  ```

After first deploy, run: `python manage.py setup_demo`

### Frontend (Static Site)
- **Build command**: `npm install && npm run build`
- **Publish directory**: `build`
- **Root directory**: `frontend`
- **Environment variables**:
  ```
  REACT_APP_API_URL=https://your-backend.onrender.com/api
  ```

## Emission Factors Used

| Source | Factor | Value | Reference |
|--------|--------|-------|-----------|
| Diesel (stationary) | kgCO₂e/L | 2.68 | IPCC AR6 WG3 Annex II |
| Petrol | kgCO₂e/L | 2.31 | IPCC AR6 WG3 Annex II |
| Natural gas | kgCO₂e/m³ | 2.04 | IPCC AR6 |
| Electricity (India avg) | kgCO₂e/kWh | 0.82 | CEA CO₂ Baseline DB v18 (Mar 2024) |
| Electricity (Southern India) | kgCO₂e/kWh | 0.7816 | CEA v18 |
| Electricity (Western India) | kgCO₂e/kWh | 0.8105 | CEA v18 |
| Flight short-haul economy | kgCO₂e/km/pax | 0.255 | DEFRA 2023 (incl. RFI 1.9) |
| Flight long-haul economy | kgCO₂e/km/pax | 0.195 | DEFRA 2023 (incl. RFI 1.9) |
| Hotel (generic) | kgCO₂e/room-night | 31.0 | DEFRA 2023 |
| Taxi/rideshare | kgCO₂e/km | 0.149 | DEFRA 2023 |
| Train | kgCO₂e/km | 0.041 | DEFRA 2023 |

## Grading Rubric Notes

**35% data model**: See `docs/MODEL.md`. Highlights: UUID PKs, separate tables per source type (not polymorphic), source-of-truth chain EmissionRecord→RawRow→IngestionBatch→file SHA256, immutable correction via supersedes FK, unit normalization at parse time.

**25% decision defense**: See `docs/DECISIONS.md`. Every format choice is justified by what clients actually do, not what the docs say is possible.

**20% realism**: See `docs/SOURCES.md`. Research covers German SAP locale, CT ratios in Indian utility connections, DEFRA RFI methodology, Navan vs Concur schema differences.

**10% analyst UX**: The review dashboard shows parsed/suspicious/failed counts, suspicion reasons as hover tooltips, per-row status badges, and a one-click approve flow.

**10% what we didn't build**: See `docs/TRADEOFFS.md`. Three deliberate omissions with honest cost assessments.

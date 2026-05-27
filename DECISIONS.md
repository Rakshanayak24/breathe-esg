# DECISIONS.md — Every Ambiguity Resolved

## SAP: Which Export Format?

**Ambiguity**: SAP exposes data via IDoc (XML/flat), OData (REST), BAPI (function modules), and flat-file report exports (MB51, ME2M, COOIS etc.)

**Decision**: Flat-file pipe-delimited export from MB51 (Material Documents).

**Why**: In practice, enterprise clients export SAP data by running standard reports and emailing the output. Nobody gives a sustainability SaaS provider VPN access to their SAP OData endpoint. IDoc processing requires SAP Basis setup and middleware. BAPIs need RFC connectivity. All of these require ongoing IT involvement from the client's SAP team. Flat files require nothing — a sustainability manager can pull MB51, save as `.txt`, and email it.

MB51 specifically because it shows material document movements (goods issues = actual consumption) filtered by movement type 201/261 (to cost center / to order), which is how fuel consumption shows up in SAP.

**What we handle**: Movement types 201, 261 (goods issue). Material descriptions containing fuel keywords. Date formats: German DD.MM.YYYY, ISO YYYYMMDD, US MM/DD/YYYY. Units: L, GAL, M3, KG, TO, KWH, MWH. Delimiter auto-detected: pipe, tab, semicolon, comma.

**What we ignore**: IDoc format. OData. BAPI. Purchase order data (ME2M) — focused on actual goods issue (consumption), not procurement. SAP plant hierarchies and cost center structures (we treat plant_code as opaque and let the client map it).

**Questions I'd ask the PM**: Which movement types does the client use for fuel issue? Do they use multiple SAP clients/mandants? Is the unit of measure set at the material master level (client-configurable)?

---

## SAP: German Column Headers

**Ambiguity**: SAP exports column headers in the language of the logged-in user. A German SAP admin exports `Buchungsdatum, Werk, Menge` instead of `Posting Date, Plant, Quantity`.

**Decision**: Maintain a bidirectional alias table mapping ~30 German and English column variants to internal field names. Applied at parse time.

**Why**: Clients don't change their SAP locale for us. The alias table covers the common variants. Unknown columns are stored as `col_N` (not dropped) so we don't silently lose data.

---

## SAP: Negative Quantities

**Ambiguity**: MB51 includes reversal postings (movement type 202) with negative quantities. Are these corrections or real data?

**Decision**: Flag as `suspicious`, include in the batch, let the analyst decide. Reversal postings are common and legitimate (correcting a previous posting), but they should be reviewed — not silently dropped or accepted.

---

## Utility: Which Format?

**Ambiguity**: Electricity data could come from portal CSV, PDF bills, API (Green Button / ESME), or half-hourly settlement files.

**Decision**: Portal CSV export.

**Why**: PDF parsing (pdfplumber/OCR) is brittle — layout changes break it silently. Green Button (US) and ESME (UK) APIs require utility-specific registration and client credentialing — not feasible for a prototype. Half-hourly HH data is overkill for monthly carbon accounting. Portal CSV is what Indian facilities teams actually do: log in to BESCOM/Tata Power/MSEDCL, click Export, download CSV.

**What we handle**: Variable column names via alias mapping (~30 variants). Billing periods that don't align with calendar months. CT ratio/multiplier for HT industrial connections. Meter rollover detection. Peak/off-peak sub-metering reconciliation check.

**What we ignore**: PDF bills. Smart meter APIs. Half-hourly granularity. RECs and I-RECs (renewable energy certificates for Scope 2 market-based).

**Questions I'd ask the PM**: Which utility portals does this client use? Do they have HT or LT connections? Do they purchase RECs?

---

## Utility: Billing Period Alignment

**Ambiguity**: A "February" electricity bill might cover January 18 – February 17. For quarterly carbon reporting, which quarter does it go in?

**Decision**: Store exact `billing_period_start` and `billing_period_end` on every row. The EmissionRecord carries `activity_period_start` and `activity_period_end` from these dates. Pro-rating across reporting periods is a reporting-layer concern, not a data model concern. The data model is period-agnostic.

**Why**: Forcing artificial alignment at ingestion loses information. A future reporting module can pro-rate 13-day/18-day billing periods correctly if the exact dates are preserved.

---

## Utility: CT Ratio / Multiplier

**Ambiguity**: HT industrial connections have current transformers (CTs) that measure a fraction of actual current. Meter reading × CT ratio = actual consumption. Some portal exports give post-multiplier units_consumed; others give raw meter units.

**Decision**: Store `multiplier` from the file. If `units_consumed` is provided directly, flag the row suspicious if multiplier ≠ 1 (because we can't know if the portal already applied it). If units_consumed must be calculated from readings, apply multiplier to (closing - opening).

**Why**: Forgetting the multiplier on a 20× CT ratio gives emissions that are 20× wrong. Better to flag and make the analyst confirm than to silently compute.

---

## Travel: Which Platform?

**Ambiguity**: Corporate travel data might come from Concur, Navan (TripActions), Egencia, AmEx GBT, or a company credit card.

**Decision**: CSV export from Navan (primary), with Concur alias mapping.

**Why**: Navan is growing rapidly in India's tech sector and we can inspect the export schema from their documentation without OAuth. Concur's export schema is similar; our column alias approach handles both. The API route for either requires enterprise agreement + OAuth app registration — weeks of setup. CSV is available today.

**Questions I'd ask the PM**: Which platform does the client use? Do they have a unified travel policy or decentralized booking?

---

## Travel: Distance Calculation

**Ambiguity**: Navan/Concur give origin/destination as IATA codes, not distances. Some rows include distance; most don't.

**Decision**: If distance is provided, use it. If not, compute Haversine great-circle distance from IATA code coordinates. Mark `distance_source` as `provided`, `calculated_haversine`, or `unknown_iata` (flagged suspicious).

**Tradeoff**: Great-circle distance underestimates actual flight path (typically by 5–15% due to routing). DEFRA's methodology accepts this. A more accurate approach would use a flight routing database (OAG, FlightAware). Not implemented — see TRADEOFFS.md.

We carry a table of ~60 major airports (heavy India + international routes). Unknown IATA codes get flagged suspicious; the emission record is not created until the analyst resolves it.

---

## Travel: Radiative Forcing Index (RFI)

**Ambiguity**: Aviation causes warming beyond CO₂ through contrail formation and NOx effects. The RFI multiplier accounts for this. Common values: 1.9 (DEFRA 2023), 2.0 (GHG Protocol), 2.7 (older literature).

**Decision**: 1.9 per DEFRA 2023 GHG Conversion Factors guidance. Applied in the flight emission factors (`FLIGHT_EF_SHORT = 0.255 kgCO2e/km/pax`).

**Why**: DEFRA is the most commonly cited methodology in Indian ESG reporting. The factor is embedded in the emission factor constant, not applied separately, which is cleaner than a multiplicative chain.

---

## Authentication

**Decision**: Token authentication (DRF TokenAuthentication). One token per user, stored client-side in localStorage.

**Why**: Simple, stateless, works with React SPA. For production: switch to JWT with refresh tokens and HTTP-only cookies. Not done here — see TRADEOFFS.md.

---

## Database

**Decision**: SQLite in development (committed), Postgres via `DATABASE_URL` env var in production.

**Why**: SQLite works for a prototype with no concurrent writes. `dj-database-url` makes the switch to Postgres transparent.

---

## What I'd Ask the PM

1. Does this client have market-based Scope 2 data (supplier invoices with EFs, RECs)? The model supports it but it's not implemented.
2. What's the reporting boundary — equity share, financial control, or operational control?
3. Are there on-site solar/wind assets that produce renewable electricity? Affects Scope 2 calculation.
4. What audit standard — GHG Protocol, ISO 14064, or a third-party verifier like Bureau Veritas?
5. Do they want Scope 3.1 (procurement) calculated from the SAP procurement data, or just Scope 1 fuel?
6. Multi-currency travel: how should we handle conversion for spend tracking? (We store the original currency.)

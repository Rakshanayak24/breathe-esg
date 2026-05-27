# MODEL.md — Data Model

## Core Entities

### Organisation
Top-level tenant. UUID primary key (not integer) so org IDs aren't guessable from the URL. Every data row carries a FK back to Organisation — this is enforced at the ORM level, not just in the API layer.

```
Organisation
  id (UUID PK)
  name, slug, country_code
  reporting_year_start  → 4 = April (Indian financial year)
```

### IngestionBatch
The unit of work. One upload = one batch. Analysts review at the batch level.

Why batch-level review rather than row-level? Because a batch comes from one source at one time. If the source is wrong (e.g., wrong plant exported), you want to reject the whole batch, not 800 individual rows. Row-level approve/reject is available as a power feature but not the default UX.

```
IngestionBatch
  id (UUID)
  organisation (FK)
  source_type: sap_fuel_procurement | utility_electricity | travel_corporate
  status: pending → in_review → approved | rejected | partial
  uploaded_file, original_filename, file_hash_sha256
  period_start, period_end          ← derived from data, not user input
  rows_parsed, rows_failed, rows_suspicious
  uploaded_by, uploaded_at
  reviewed_by, reviewed_at
  approved_by, approved_at
  parse_log (JSON array of {row, message})
  notes
```

`file_hash_sha256` prevents duplicate uploads. If someone re-exports the same SAP file and uploads it again, we reject it with a 409.

### Raw Row Tables (3 separate tables)

We use **separate tables per source type**, not a single polymorphic `RawRow` table. Why:

1. Column sets are completely different. SAP has plant codes and movement types; utility has meter IDs and CT ratios; travel has cabin classes and IATA codes. A single table would be ~80% NULLs.
2. Queries are always source-scoped. You never join across source types.
3. Django's ORM handles the FK relationships cleanly.

Each table has:
- `status`: ok | suspicious | failed | approved | rejected
- `suspicious_reason`: plain-text description of what triggered the flag
- `parse_error`: what went wrong if status=failed
- `edited_by`, `edited_at`, `edit_note`: for manual corrections (source-of-truth tracking)
- All original raw values preserved alongside normalized values

**RawSAPRow** — Material Document data
Key fields: `plant_code`, `cost_center`, `material_number`, `material_description`, `posting_date` (parsed from raw), `quantity`, `unit_of_measure_raw`, `unit_of_measure_normalized`, `quantity_normalized`, `is_fuel`, `fuel_type`

**RawUtilityRow** — Electricity billing
Key fields: `meter_id`, `account_number`, `site_name`, `billing_period_start`, `billing_period_end`, `billing_period_days`, `multiplier` (CT ratio), `units_consumed_kwh`, `opening_reading`, `closing_reading`, `peak_units_kwh`, `off_peak_units_kwh`, `emission_factor_used`, `grid_region`

**RawTravelRow** — Flights, hotels, ground transport
Key fields: `travel_type` (flight|hotel|ground_*), `origin_iata`, `destination_iata`, `distance_km`, `distance_source` (provided|calculated_haversine|unknown_iata), `cabin_class`, `is_return`, `nights`, `hotel_country`, `distance_km_ground`

### EmissionRecord
The canonical output. Created at approval time, never modified.

```
EmissionRecord
  id (UUID)
  organisation (FK)
  batch (FK)
  source_sap_row | source_utility_row | source_travel_row   ← exactly one set
  scope: scope1 | scope2_location | scope2_market | scope3
  category: s1_stationary | s1_mobile | s2_electricity | s3_business_travel | s3_purchased_goods
  activity_period_start, activity_period_end
  activity_value, activity_unit                ← normalized (L, kWh, km, room-nights)
  emission_factor, emission_factor_source, emission_factor_unit
  co2e_tonnes
  is_locked, locked_at, locked_by
  supersedes (FK self)                         ← immutable correction chain
```

## Multi-tenancy

Enforced by:
1. Every model has `organisation = ForeignKey(Organisation)` — database-level constraint
2. Every ViewSet filters `queryset = Model.objects.filter(organisation=get_user_org(request.user))`
3. No cross-org queries are possible without bypassing the ORM entirely

Missing from this prototype: row-level security at the DB level (would add for production using PostgreSQL RLS policies).

## Scope 1 / 2 / 3 Classification

| Source | Scope | Category |
|--------|-------|----------|
| SAP — fuel materials (diesel, petrol, gas) | Scope 1 | S1: Stationary Combustion |
| SAP — procurement (non-fuel) | Scope 3 | S3.1: Purchased Goods |
| Utility — electricity | Scope 2 (location-based) | S2: Purchased Electricity |
| Travel — flights | Scope 3 | S3.6: Business Travel |
| Travel — hotels | Scope 3 | S3.6: Business Travel |
| Travel — ground | Scope 3 | S3.6: Business Travel |

Scope 2 market-based (using supplier-specific emission factors or RECs) is modelled but not implemented — see TRADEOFFS.md.

## Source-of-Truth Tracking

Every EmissionRecord knows exactly which raw row produced it (via `source_sap_row`, `source_utility_row`, or `source_travel_row` FK). The raw row knows which batch produced it, which file, which line number, and the original raw values. Full chain: `EmissionRecord → RawRow → IngestionBatch → uploaded_file (SHA256 hash)`.

If an analyst manually corrects a value (e.g., wrong quantity in SAP row), the raw row gets `edited_by`, `edited_at`, `edit_note`. The EmissionRecord is re-calculated and the old one gets `supersedes` set to the new one. Neither is deleted.

## Audit Trail

Once a batch is approved, `EmissionRecord.is_locked = True`. Locked records cannot be modified through the API — the serializer enforces `read_only_fields` on lock fields, and the view checks `is_locked` before allowing any update. In production: an additional DB trigger would enforce this at the Postgres level.

## Unit Normalization

Normalization happens at parse time, not at emission calculation time:
- Volumes: all → litres (L). Gallons multiplied by 3.78541 (US) or 4.54609 (Imperial)
- Masses: all → kg. Tonnes × 1000.
- Gas: m³ natural gas preserved as m³ (EF is per m³)
- Electricity: all → kWh. MWh × 1000, GJ × 277.778, MMBtu × 293.071
- Distance: km. Miles × 1.60934

Original raw values always preserved alongside normalized values.

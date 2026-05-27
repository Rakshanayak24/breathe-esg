# SOURCES.md — Research Notes on Each Data Source

## Source 1: SAP Fuel & Procurement

### What Real-World Format Looks Like
SAP MB51 (Material Document List) exports as a report output. When you run MB51 in SAP GUI and click "Export to spreadsheet" or "Local file", you get a pipe-delimited or tab-delimited text file with a header block (report title, selection criteria, timestamp) followed by column headers and data rows.

Real column names (German SAP): `Belegnummer | Buchungsdatum | Werk | Kostenstelle | Materialnummer | Materialbezeichnung | Menge | Basismengeneinheit | Bewegungsart`

Key behaviors observed from SAP documentation and export samples:
- Dates use the SAP system locale (German = DD.MM.YYYY, but can be YYYYMMDD in IDoc output)
- Quantities use German decimal notation in German-locale SAP (1.234,56 = one thousand two hundred thirty four point fifty-six)
- Units are SAP-internal codes: `L` (litre), `KG` (kilogram), `M3` (cubic metre), `TO` (metric tonne), `GAL` (US gallon), `PC` (piece)
- Plant codes (Werk) are 4-character alphanumeric internal codes (e.g., `1000`, `IN01`) — meaningless without the plant master data
- Movement types (Bewegungsart) tell you the direction: 101=goods receipt, 201=goods issue to cost center, 261=goods issue to production order, 202/202=reversal

### What We Learned
The biggest real-world problem is that fuel materials are not tagged as "fuel" in SAP — they're just materials with a description. A client might have material number 10000045 described as "HSD Diesel" in one plant and "Diesel (High Speed)" in another. Classification requires either (a) the client provides a material master export mapping material numbers to fuel types, or (b) keyword matching on descriptions (our approach).

German decimal notation is a real problem that trips up simple CSV parsers. We handle it by detecting the pattern (contains both `.` and `,` with `,` as last separator).

### Our Sample Data Rationale
30 rows covering April–June 2024 across two plants (IN01 = Bangalore, IN02 = Thane). Materials: HSD diesel (stationary generators, production), natural gas (boiler), petrol (fleet). We included:
- Row 29: negative quantity (-150L) to test reversal posting detection → flagged suspicious
- Row 30: missing cost center → flagged with suspicious note
- Row 31: quantity 999,999L → extremely large, flagged suspicious

Date format: German DD.MM.YYYY throughout.

### What Would Break in Real Deployment
1. **Plant code lookup**: We store plant codes as-is. A real deployment needs a plant master CSV from the client mapping `IN01` → "ACME Bangalore Factory, Whitefield".
2. **Material master**: Our keyword-to-fuel-type mapping is fragile. A client with custom material descriptions ("PROD-CONSUMABLE-07") would fail classification. Need a material master extract.
3. **Currency of fuel rows**: SAP material documents don't carry cost at the movement type level in all configurations — cost may require a separate purchase order extract.
4. **Large files**: A plant running 24/7 might have 50,000+ MB51 rows per quarter. Our synchronous parse-on-upload would timeout. Need Celery + Redis for async processing.

---

## Source 2: Utility Electricity

### What Real-World Format Looks Like
Indian utility portal CSV exports (researched: BESCOM, Tata Power Delhi, MSEDCL, TNEB):

**BESCOM (Bangalore) portal export columns**: Account Number, Consumer Name, Meter Number, Division, Sub Division, From Date, To Date, Opening Reading, Closing Reading, Units Consumed, Amount, Bill Date

**MSEDCL (Maharashtra) portal export**: CA No, Meter No, Consumer Name, Billing From, Billing To, Units, Peak Units, Off Peak Units, Amount, Demand (kVA)

**Tata Power Delhi**: Account No, Site, Period, Consumption (kWh), Peak, Off-Peak, Bill Amount

HT (High Tension) industrial connections have CT (Current Transformer) ratios, typically 10× to 100×. The meter measures a fraction; the actual consumption is `meter_reading × CT_ratio`. Some portals apply this automatically in the export; others give raw meter units. This is the most dangerous edge case — a 40× CT ratio means 40× wrong emissions if missed.

CEA (Central Electricity Authority) emission factors used:
- Southern region (BESCOM, TNEB, KSEB): 0.7816 kgCO2e/kWh
- Western region (MSEDCL, Tata Power): 0.8105 kgCO2e/kWh  
- Northern region (BSES, DHBVN): 0.7065 kgCO2e/kWh
- Eastern region (WBSEDCL): 0.9185 kgCO2e/kWh
- National average: 0.82 kgCO2e/kWh
Source: CEA CO2 Baseline Database Version 18 (March 2024)

### What We Learned
Billing periods are structurally misaligned with calendar months, but not in a predictable way. BESCOM reads meters every 30-35 days; the bill might cover March 18 – April 19. For quarterly carbon reporting, attributing this to Q4 or Q1 matters. Our data model stores exact period dates to allow correct pro-rating later.

### Our Sample Data Rationale
18 rows, 5 sites across 3 regions (southern=Bangalore, western=Mumbai, northern=Delhi). Mix of HT industrial (multiplier=10 for factory, multiplier=20 for Thane plant) and LT commercial (multiplier=1 for offices). Billing periods are non-calendar (18th to 17th or 1st to 31st). Includes peak/off-peak split for HT connections.

### What Would Break in Real Deployment
1. **CT ratio ambiguity**: Without confirmation from the client whether the portal export applies the multiplier or not, we can't safely calculate consumption. We flag it but can't auto-resolve.
2. **Portal format changes**: Utility portal CSV layouts change with software updates. BESCOM changed their export format in 2022 — any hardcoded parser would break. Our alias approach is more resilient but not immune.
3. **Green Power Procurement**: A client with solar rooftop or PPAs needs market-based Scope 2. Not implemented.
4. **Multi-site deduplication**: If the same meter appears in two uploads (partial periods), we don't detect or merge overlapping billing periods.

---

## Source 3: Corporate Travel

### What Real-World Format Looks Like
Researched Navan (TripActions) and Concur Travel export documentation:

**Navan CSV export columns** (from their admin reporting portal): TravelerName, TravelerEmail, TripStart, TripEnd, BookingType, Vendor, Origin, Destination, CabinClass, TripAmount, Currency, CostCenter, Department, BookingRef, TransactionDate, MileageDistance

**Concur Travel "Standard Report" CSV**: Employee ID, Department, Cost Center, Expense Date, Transaction Amount, Currency Code, Expense Type, Vendor Name, City of Purchase, Report Name, Travel Start, Travel End

Key gap: **Concur does not give IATA codes or distances in their standard CSV export**. You get city names, not airport codes. To get IATA codes, you need to cross-reference with trip data from the travel module (separate from expense). Navan does give IATA codes. This is a real pain point — addressed by: (a) IATA code extraction from city name if exactly one major airport serves that city, or (b) flag as suspicious and require manual distance entry.

DEFRA 2023 emission factors used:
- Short-haul economy: 0.255 kgCO2e/km/pax (includes RFI 1.9)
- Long-haul economy: 0.195 kgCO2e/km/pax (includes RFI 1.9)
- Cabin multipliers: premium economy 1.6×, business 2.9×, first 4.0×
- Hotels: 31.0 kgCO2e/room-night (generic)
- Taxi/rideshare: 0.149 kgCO2e/km
- Train: 0.041 kgCO2e/km
- Rental car: 0.171 kgCO2e/km

### What We Learned
The Radiative Forcing Index (RFI) for aviation is genuinely contested. DEFRA uses 1.9, but recent science suggests 2.5–3.0. We use 1.9 because it's the current DEFRA standard and changing this requires a stated methodology change (auditors care about consistency between years more than the absolute value).

Hotel emissions are extremely imprecise — star rating, location, and age of building all matter but aren't captured in travel booking data. The DEFRA generic factor is the best available. Some companies use supplier-disclosed factors (Scope 3.1 for hotel chains), but this requires bilateral data sharing.

### Our Sample Data Rationale
37 rows, April–June 2024. Mix of:
- Domestic Indian flights (BLR↔DEL, BLR↔HYD, BOM↔MAA) with IATA codes we have coordinates for
- International flights (BOM↔LHR, BLR↔SFO, BOM↔NRT) — distances calculated via Haversine
- Business class flights (marked with `cabin_class: business`) to test cabin multiplier
- Hotel stays matching flight trips
- Ground transport: taxi (missing distance on one row — flagged suspicious), train (with km), rental car

Row 36 (Uber, no distance) — flagged suspicious, cannot calculate emissions without distance.

### What Would Break in Real Deployment
1. **Concur city names**: Concur gives "San Francisco" not "SFO". A city→IATA lookup table would be needed.
2. **IATA database coverage**: We have 60 airports. The full OurAirports database (8,000 airports) is needed. Tier-3 Indian cities (Hubli = HBX, Tirupati = TIR) would fail.
3. **Multi-leg itineraries**: A BLR→DXB→LHR trip might appear as two rows (BLR→DXB, DXB→LHR) or one (BLR→LHR with DXB connection). Concur typically shows each segment; Navan may collapse. Our parser treats each row independently.
4. **Personal trips on corporate cards**: No way to identify. Requires policy enforcement in the travel platform.
5. **Currency conversion for spend**: Travel rows have amounts in the local currency of booking (INR, USD, EUR, AED). We store the original currency. Normalizing to a single currency for spend analysis requires FX rates.

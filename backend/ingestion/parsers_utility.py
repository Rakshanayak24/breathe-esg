"""
Utility electricity data parser.

Source format chosen: CSV export from utility portal.

Real-world context:
- BESCOM (Bangalore) portal exports CSV with fixed column layout
- Tata Power, MSEDCL, TPDDL portals have similar but not identical schemas
- UK: Half-hourly metered data in ESME/ECOES format (HH settlements)
- US: Green Button Data (GBD) XML or utility CSV

We handle a normalized CSV schema that covers the common fields across
these portals. Column names vary; we use alias matching like the SAP parser.

Key complexity: billing periods ≠ calendar months.
A "January bill" might cover Dec 18 – Jan 17. We store exact period dates
and pro-rate emissions when period spans two reporting months.

Also: multiplier (CT ratio). For HT industrial connections, the meter
measures a fraction of actual consumption. Actual kWh = reading × multiplier.
Forgetting this gives wildly wrong emissions.
"""

import csv
import io
import re
from decimal import Decimal, InvalidOperation
from datetime import datetime, date
from typing import Optional

COLUMN_ALIASES = {
    # Account / meter
    'account number': 'account_number',
    'account no': 'account_number',
    'account_number': 'account_number',
    'consumer no': 'account_number',
    'ca no': 'account_number',
    'meter id': 'meter_id',
    'meter no': 'meter_id',
    'meter number': 'meter_id',
    'meter_id': 'meter_id',
    # Site
    'site': 'site_name',
    'site name': 'site_name',
    'location': 'site_name',
    'premises': 'site_name',
    'address': 'site_address',
    'tariff': 'tariff_category',
    'tariff category': 'tariff_category',
    'tariff type': 'tariff_category',
    'supply type': 'tariff_category',
    # Billing period
    'bill from': 'billing_period_start',
    'from date': 'billing_period_start',
    'billing start': 'billing_period_start',
    'period start': 'billing_period_start',
    'bill to': 'billing_period_end',
    'to date': 'billing_period_end',
    'billing end': 'billing_period_end',
    'period end': 'billing_period_end',
    'days': 'billing_period_days',
    'no of days': 'billing_period_days',
    # Readings
    'opening reading': 'opening_reading',
    'previous reading': 'opening_reading',
    'closing reading': 'closing_reading',
    'current reading': 'closing_reading',
    'multiplier': 'multiplier',
    'ct ratio': 'multiplier',
    'meter multiplier': 'multiplier',
    # Consumption
    'units consumed': 'units_consumed_kwh',
    'units': 'units_consumed_kwh',
    'consumption': 'units_consumed_kwh',
    'kwh': 'units_consumed_kwh',
    'energy': 'units_consumed_kwh',
    'peak units': 'peak_units_kwh',
    'off peak units': 'off_peak_units_kwh',
    'off-peak units': 'off_peak_units_kwh',
    'reactive units': 'reactive_units_kvarh',
    'kvarh': 'reactive_units_kvarh',
    # Financials
    'amount': 'bill_amount',
    'bill amount': 'bill_amount',
    'total amount': 'bill_amount',
    'net amount': 'bill_amount',
    'currency': 'currency',
    # Grid
    'grid region': 'grid_region',
    'region': 'grid_region',
    'state': 'grid_region',
}

# Date formats common in Indian utility bills
DATE_FORMATS = [
    '%d/%m/%Y',
    '%d-%m-%Y',
    '%Y-%m-%d',
    '%d.%m.%Y',
    '%b %d, %Y',   # Jan 01, 2024
    '%d %b %Y',    # 01 Jan 2024
    '%d %B %Y',    # 01 January 2024
    '%m/%d/%Y',
    '%Y%m%d',
]

# Grid emission factors (kgCO2e/kWh) — CEA (Central Electricity Authority) 2023-24
# Source: CEA CO2 Baseline Database Version 18 (March 2024)
INDIA_GRID_FACTORS = {
    'northern': Decimal('0.7065'),
    'western': Decimal('0.8105'),
    'southern': Decimal('0.7816'),
    'eastern': Decimal('0.9185'),
    'northeastern': Decimal('0.5535'),
    'default_india': Decimal('0.82'),   # national average
    'default_uk': Decimal('0.233'),
    'default_us': Decimal('0.386'),
}

STATE_TO_GRID = {
    'karnataka': 'southern', 'tn': 'southern', 'tamil nadu': 'southern',
    'kerala': 'southern', 'andhra': 'southern', 'telangana': 'southern',
    'maharashtra': 'western', 'gujarat': 'western', 'rajasthan': 'western',
    'mp': 'western', 'madhya pradesh': 'western', 'goa': 'western',
    'delhi': 'northern', 'haryana': 'northern', 'punjab': 'northern',
    'up': 'northern', 'uttar pradesh': 'northern', 'hp': 'northern',
    'wb': 'eastern', 'west bengal': 'eastern', 'odisha': 'eastern',
    'jharkhand': 'eastern', 'bihar': 'eastern',
    'assam': 'northeastern', 'meghalaya': 'northeastern',
}


def parse_utility_date(raw: str) -> Optional[date]:
    raw = raw.strip()
    if not raw:
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def parse_decimal(raw: str) -> Optional[Decimal]:
    raw = raw.strip().replace(',', '').replace('\xa0', '')
    if not raw:
        return None
    try:
        return Decimal(raw)
    except InvalidOperation:
        return None


def get_grid_factor(grid_region: str) -> Decimal:
    region_lower = grid_region.lower().strip()
    # Try direct match
    if region_lower in INDIA_GRID_FACTORS:
        return INDIA_GRID_FACTORS[region_lower]
    # Try state mapping
    for state, region in STATE_TO_GRID.items():
        if state in region_lower:
            return INDIA_GRID_FACTORS[region]
    return INDIA_GRID_FACTORS['default_india']


def map_headers(raw_headers: list) -> dict:
    mapping = {}
    for i, header in enumerate(raw_headers):
        norm = header.strip().lower().replace('_', ' ').replace('-', ' ')
        internal = COLUMN_ALIASES.get(norm, norm.replace(' ', '_'))
        mapping[i] = internal
    return mapping


def parse_utility_file(file_content: bytes, original_filename: str) -> dict:
    """
    Parse a utility portal CSV export.

    Handles:
    - Variable column names via alias mapping
    - Billing periods that don't align with calendar months
    - CT ratio/multiplier for HT connections
    - Missing readings (only total consumption given)
    - Multiple meters in one file
    """
    rows = []
    errors = []
    warnings = []

    try:
        text = file_content.decode('utf-8', errors='replace')
    except Exception as e:
        return {'rows': [], 'errors': [{'row': 0, 'message': f'Decode error: {e}'}],
                'warnings': [], 'period_start': None, 'period_end': None}

    # Skip preamble lines (utility reports often have title rows before data)
    lines = text.splitlines()
    data_start = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        lower = stripped.lower()
        if any(kw in lower for kw in ['account', 'meter', 'date', 'consumption', 'units', 'billing']):
            data_start = i
            break

    reader = csv.reader(lines[data_start:])
    headers_raw = next(reader, None)
    if not headers_raw:
        return {'rows': [], 'errors': [{'row': 0, 'message': 'No header row found'}],
                'warnings': [], 'period_start': None, 'period_end': None}

    col_map = map_headers(headers_raw)
    all_period_starts = []
    all_period_ends = []

    for row_num, raw_row in enumerate(reader, start=data_start + 2):
        if not any(cell.strip() for cell in raw_row):
            continue

        row_data = {}
        for col_idx, value in enumerate(raw_row):
            field = col_map.get(col_idx, f'col_{col_idx}')
            row_data[field] = value.strip() if col_idx < len(raw_row) else ''

        parsed = {
            'row_number': row_num,
            'account_number': row_data.get('account_number', ''),
            'meter_id': row_data.get('meter_id', ''),
            'site_name': row_data.get('site_name', ''),
            'site_address': row_data.get('site_address', ''),
            'tariff_category': row_data.get('tariff_category', ''),
            'grid_region': row_data.get('grid_region', ''),
            'currency': row_data.get('currency', 'INR'),
            'parse_error': '',
            'suspicious_reason': '',
            'status': 'ok',
        }

        # Billing period
        period_start = parse_utility_date(row_data.get('billing_period_start', ''))
        period_end = parse_utility_date(row_data.get('billing_period_end', ''))
        parsed['billing_period_start'] = period_start
        parsed['billing_period_end'] = period_end

        if period_start:
            all_period_starts.append(period_start)
        if period_end:
            all_period_ends.append(period_end)

        if period_start and period_end:
            parsed['billing_period_days'] = (period_end - period_start).days + 1
        else:
            days_raw = row_data.get('billing_period_days', '')
            parsed['billing_period_days'] = int(days_raw) if days_raw.isdigit() else None

        # Multiplier (CT ratio) — default 1 for LT connections
        mult_raw = row_data.get('multiplier', '1')
        multiplier = parse_decimal(mult_raw) or Decimal('1')
        parsed['multiplier'] = multiplier

        # Meter readings
        parsed['opening_reading'] = parse_decimal(row_data.get('opening_reading', ''))
        parsed['closing_reading'] = parse_decimal(row_data.get('closing_reading', ''))

        # Consumption — prefer direct units_consumed, else calculate from readings
        units_raw = row_data.get('units_consumed_kwh', '') or row_data.get('consumption', '')
        units_consumed = parse_decimal(units_raw)

        if units_consumed is None and parsed['opening_reading'] is not None and parsed['closing_reading'] is not None:
            reading_diff = parsed['closing_reading'] - parsed['opening_reading']
            if reading_diff < 0:
                # Meter rollover
                units_consumed = (Decimal('99999.99') - parsed['opening_reading'] + parsed['closing_reading']) * multiplier
                parsed['suspicious_reason'] += 'Meter rollover detected. '
                parsed['status'] = 'suspicious'
            else:
                units_consumed = reading_diff * multiplier

        elif units_consumed is not None and multiplier != Decimal('1'):
            # If units_consumed is given raw (pre-multiplier) — depends on utility
            # We assume portal exports give post-multiplier values; flag if not
            parsed['suspicious_reason'] += f'Multiplier {multiplier} present — verify if units_consumed is pre or post-multiplier. '
            if parsed['status'] == 'ok':
                parsed['status'] = 'suspicious'

        parsed['units_consumed_kwh'] = units_consumed
        parsed['units_consumed_raw'] = units_raw

        # Sub-metering (peak/off-peak)
        parsed['peak_units_kwh'] = parse_decimal(row_data.get('peak_units_kwh', ''))
        parsed['off_peak_units_kwh'] = parse_decimal(row_data.get('off_peak_units_kwh', ''))
        parsed['reactive_units_kvarh'] = parse_decimal(row_data.get('reactive_units_kvarh', ''))

        # Sanity: peak + off_peak should ≈ total
        if parsed['peak_units_kwh'] and parsed['off_peak_units_kwh'] and units_consumed:
            sub_total = parsed['peak_units_kwh'] + parsed['off_peak_units_kwh']
            if abs(sub_total - units_consumed) > units_consumed * Decimal('0.05'):
                parsed['suspicious_reason'] += 'Peak + off-peak does not reconcile with total. '
                if parsed['status'] == 'ok':
                    parsed['status'] = 'suspicious'

        # Financial
        parsed['bill_amount'] = parse_decimal(row_data.get('bill_amount', ''))

        # Emission factor
        ef = get_grid_factor(parsed['grid_region'])
        parsed['emission_factor_used'] = ef

        # Validation
        if units_consumed is None:
            parsed['parse_error'] += 'Could not determine units consumed. '
            parsed['status'] = 'failed'

        if units_consumed and units_consumed < Decimal('0'):
            parsed['suspicious_reason'] += 'Negative consumption. '
            parsed['status'] = 'suspicious'

        if parsed['billing_period_days'] and parsed['billing_period_days'] > 95:
            parsed['suspicious_reason'] += f'Billing period {parsed["billing_period_days"]} days — unusually long. '
            if parsed['status'] == 'ok':
                parsed['status'] = 'suspicious'

        if not parsed['meter_id'] and not parsed['account_number']:
            parsed['suspicious_reason'] += 'No meter ID or account number. '

        rows.append(parsed)

    return {
        'rows': rows,
        'errors': errors,
        'warnings': warnings,
        'period_start': min(all_period_starts) if all_period_starts else None,
        'period_end': max(all_period_ends) if all_period_ends else None,
    }

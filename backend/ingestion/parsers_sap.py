"""
SAP flat-file parser for fuel and procurement data.

SAP export format chosen: pipe-delimited flat file from MB51 (Material Document List)
and ME2M (Purchase Orders by Material).

Real SAP exports from MB51 look like:
- Header line with column names (sometimes in German)
- Data rows pipe-delimited or fixed-width
- Dates in DD.MM.YYYY (German locale) or YYYYMMDD
- Units: L (litres), KG, M3, GAL, TON, PC
- Movement types (Bewegungsart): 101=GR, 201=GI to cost center, 261=GI to order

German→English column mappings we handle:
  Buchungsdatum → posting_date
  Werk → plant_code
  Menge → quantity
  Basismengeneinheit → unit_of_measure
  Materialnummer → material_number
  Materialbezeichnung → material_description
  Kostenstelle → cost_center
  Belegnummer → document_number
  Bewegungsart → movement_type
"""

import csv
import io
import re
from decimal import Decimal, InvalidOperation
from datetime import datetime
from typing import Optional

from django.conf import settings

# Material-to-fuel-type mapping (subset of what we handle)
# In production this would be a lookup table loaded from client's material master
MATERIAL_FUEL_MAP = {
    # Diesel variants
    'diesel': 'diesel',
    'hsd': 'diesel',        # High Speed Diesel
    'hfo': 'fuel_oil',      # Heavy Fuel Oil
    'furnace oil': 'fuel_oil',
    'petrol': 'petrol',
    'gasoline': 'petrol',
    'lpg': 'lpg',
    'cng': 'cng',
    'natural gas': 'natural_gas',
    'erdgas': 'natural_gas',  # German
}

# SAP unit → normalized SI unit and conversion factor
UNIT_NORMALIZATION = {
    'L': ('L', Decimal('1')),
    'LT': ('L', Decimal('1')),
    'GAL': ('L', Decimal('3.78541')),      # US gallon → litre
    'GALUK': ('L', Decimal('4.54609')),    # Imperial gallon → litre
    'M3': ('m3', Decimal('1')),
    'KG': ('kg', Decimal('1')),
    'TO': ('kg', Decimal('1000')),          # tonne
    'TON': ('kg', Decimal('1000')),
    'G': ('kg', Decimal('0.001')),
    'KWH': ('kWh', Decimal('1')),
    'MWH': ('kWh', Decimal('1000')),
    'GJ': ('kWh', Decimal('277.778')),
    'MMBTU': ('kWh', Decimal('293.071')),
    'PC': ('unit', Decimal('1')),           # piece/count — not a fuel unit
}

# German column name aliases → internal names
COLUMN_ALIASES = {
    'buchungsdatum': 'posting_date',
    'posting date': 'posting_date',
    'postg date': 'posting_date',
    'posting_date': 'posting_date',
    'werk': 'plant_code',
    'plant': 'plant_code',
    'plant_code': 'plant_code',
    'menge': 'quantity',
    'quantity': 'quantity',
    'amount': 'quantity',
    'basismengeneinheit': 'unit_of_measure',
    'base unit': 'unit_of_measure',
    'unit': 'unit_of_measure',
    'uom': 'unit_of_measure',
    'materialnummer': 'material_number',
    'material': 'material_number',
    'material number': 'material_number',
    'matnr': 'material_number',
    'materialbezeichnung': 'material_description',
    'material description': 'material_description',
    'material_description': 'material_description',
    'kostenstelle': 'cost_center',
    'cost center': 'cost_center',
    'cost_center': 'cost_center',
    'belegnummer': 'document_number',
    'document': 'document_number',
    'doc. no.': 'document_number',
    'bewegungsart': 'movement_type',
    'movement type': 'movement_type',
    'mvt': 'movement_type',
    'bwart': 'movement_type',
}


def parse_sap_date(raw: str) -> Optional[datetime.date]:
    """
    SAP dates come in multiple formats depending on locale and export type:
    - DD.MM.YYYY (German locale, most common in flat files)
    - MM/DD/YYYY (US locale)
    - YYYYMMDD (IDoc format)
    - DD-MM-YYYY
    """
    raw = raw.strip()
    if not raw:
        return None
    formats = [
        '%d.%m.%Y',   # German: 31.01.2024
        '%d/%m/%Y',   # European: 31/01/2024
        '%m/%d/%Y',   # US: 01/31/2024
        '%Y%m%d',     # IDoc: 20240131
        '%Y-%m-%d',   # ISO: 2024-01-31
        '%d-%m-%Y',   # 31-01-2024
    ]
    for fmt in formats:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def parse_sap_quantity(raw: str) -> Optional[Decimal]:
    """
    SAP quantities use German decimal notation (comma as decimal separator
    in some locales): 1.234,56 means 1234.56.
    Also strips SAP-style thousands separators.
    """
    raw = raw.strip().replace('\xa0', '')  # remove non-breaking space
    if not raw:
        return None
    # Detect German format: contains both . and , where , is last
    if ',' in raw and '.' in raw:
        if raw.rfind(',') > raw.rfind('.'):
            # German format: 1.234,56
            raw = raw.replace('.', '').replace(',', '.')
        else:
            # English format: 1,234.56
            raw = raw.replace(',', '')
    elif ',' in raw:
        raw = raw.replace(',', '.')
    # Remove any remaining non-numeric except . and -
    raw = re.sub(r'[^\d.\-]', '', raw)
    try:
        return Decimal(raw)
    except InvalidOperation:
        return None


def normalize_unit(unit_raw: str):
    """Returns (normalized_unit, conversion_factor) or (None, None)."""
    unit_upper = unit_raw.strip().upper()
    return UNIT_NORMALIZATION.get(unit_upper, (unit_upper, Decimal('1')))


def classify_material(material_num: str, description: str) -> dict:
    """
    Determine if a SAP material row is fuel or procurement, and which fuel type.
    In production: query material master / G/L account mapping.
    """
    desc_lower = description.lower()
    result = {
        'is_fuel': False,
        'is_procurement': False,
        'fuel_type': '',
    }
    for keyword, fuel_type in MATERIAL_FUEL_MAP.items():
        if keyword in desc_lower:
            result['is_fuel'] = True
            result['fuel_type'] = fuel_type
            return result
    # SAP material number heuristics: fuel materials often start with specific ranges
    # In real deployment: client provides material master / classification
    if material_num.startswith(('1', '2')) and len(material_num) == 8:
        result['is_procurement'] = True
    return result


def detect_delimiter(sample_lines: list) -> str:
    """Auto-detect delimiter from sample lines."""
    candidates = ['|', '\t', ';', ',']
    for delim in candidates:
        counts = [line.count(delim) for line in sample_lines if line.strip()]
        if counts and min(counts) > 0 and max(counts) - min(counts) <= 2:
            return delim
    return ','  # fallback


def map_headers(raw_headers: list) -> dict:
    """Map raw column names to internal field names."""
    mapping = {}
    for i, header in enumerate(raw_headers):
        normalized = header.strip().lower().replace('_', ' ').replace('-', ' ')
        internal = COLUMN_ALIASES.get(normalized, normalized.replace(' ', '_'))
        mapping[i] = internal
    return mapping


def parse_sap_file(file_content: bytes, original_filename: str) -> dict:
    """
    Main entry point. Parse a SAP flat file export.

    Returns:
        {
            'rows': [list of dicts with parsed fields],
            'errors': [list of {'row': N, 'message': str}],
            'warnings': [list of {'row': N, 'message': str}],
            'period_start': date or None,
            'period_end': date or None,
        }
    """
    rows = []
    errors = []
    warnings = []

    try:
        text = file_content.decode('utf-8', errors='replace')
    except Exception as e:
        return {'rows': [], 'errors': [{'row': 0, 'message': f'File decode error: {e}'}],
                'warnings': [], 'period_start': None, 'period_end': None}

    lines = text.splitlines()

    # Skip SAP report header lines (common patterns: lines starting with |, blank, report title)
    data_start = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped and not stripped.startswith('*') and not stripped.startswith('/'):
            # Check if this looks like a header row
            lower = stripped.lower()
            if any(kw in lower for kw in ['buchungsdatum', 'posting', 'material', 'werk', 'plant', 'menge', 'quantity', 'date']):
                data_start = i
                break

    if data_start >= len(lines):
        return {'rows': [], 'errors': [{'row': 0, 'message': 'Could not find header row'}],
                'warnings': [], 'period_start': None, 'period_end': None}

    # Detect delimiter from first few data lines
    sample = lines[data_start:data_start + 5]
    delimiter = detect_delimiter(sample)

    reader = csv.reader(lines[data_start:], delimiter=delimiter)
    headers_raw = next(reader, None)
    if not headers_raw:
        return {'rows': [], 'errors': [{'row': 0, 'message': 'Empty file or no headers'}],
                'warnings': [], 'period_start': None, 'period_end': None}

    col_map = map_headers(headers_raw)
    all_dates = []

    for row_num, raw_row in enumerate(reader, start=data_start + 2):
        if not any(cell.strip() for cell in raw_row):
            continue  # skip blank rows
        if len(raw_row) < 3:
            continue

        # Map cells to field names
        row_data = {}
        for col_idx, value in enumerate(raw_row):
            field = col_map.get(col_idx, f'col_{col_idx}')
            row_data[field] = value.strip()

        parsed = {
            'row_number': row_num,
            'plant_code': row_data.get('plant_code', ''),
            'cost_center': row_data.get('cost_center', ''),
            'material_number': row_data.get('material_number', ''),
            'material_description': row_data.get('material_description', ''),
            'document_number': row_data.get('document_number', ''),
            'document_type': row_data.get('document_type', row_data.get('movement_type', '')),
            'posting_date_raw': row_data.get('posting_date', ''),
            'quantity_raw': row_data.get('quantity', ''),
            'unit_of_measure_raw': row_data.get('unit_of_measure', ''),
            'parse_error': '',
            'suspicious_reason': '',
            'status': 'ok',
        }

        # Parse date
        posting_date = parse_sap_date(parsed['posting_date_raw'])
        if posting_date:
            parsed['posting_date'] = posting_date
            all_dates.append(posting_date)
        else:
            if parsed['posting_date_raw']:
                parsed['parse_error'] += f"Unparseable date: {parsed['posting_date_raw']}. "
                parsed['status'] = 'failed'

        # Parse quantity
        qty = parse_sap_quantity(parsed['quantity_raw'])
        if qty is not None:
            parsed['quantity'] = qty
            if qty < 0:
                parsed['suspicious_reason'] += 'Negative quantity (reversal posting?). '
                parsed['status'] = 'suspicious'
            if qty == 0:
                parsed['suspicious_reason'] += 'Zero quantity. '
                parsed['status'] = 'suspicious'
        else:
            if parsed['quantity_raw']:
                parsed['parse_error'] += f"Unparseable quantity: {parsed['quantity_raw']}. "
                parsed['status'] = 'failed'

        # Normalize unit
        unit_norm, factor = normalize_unit(parsed['unit_of_measure_raw'])
        parsed['unit_of_measure_normalized'] = unit_norm
        if qty and factor and unit_norm != 'unit':
            parsed['quantity_normalized'] = qty * factor
            parsed['quantity_normalized_unit'] = unit_norm

        # Classify material
        classification = classify_material(
            parsed['material_number'],
            parsed['material_description']
        )
        parsed.update(classification)

        # Suspicious checks
        if parsed.get('quantity') and parsed.get('quantity') > Decimal('100000'):
            parsed['suspicious_reason'] += 'Very large quantity — confirm units. '
            if parsed['status'] == 'ok':
                parsed['status'] = 'suspicious'

        if not parsed['plant_code']:
            parsed['suspicious_reason'] += 'Missing plant code. '

        rows.append(parsed)

    period_start = min(all_dates) if all_dates else None
    period_end = max(all_dates) if all_dates else None

    return {
        'rows': rows,
        'errors': errors,
        'warnings': warnings,
        'period_start': period_start,
        'period_end': period_end,
    }

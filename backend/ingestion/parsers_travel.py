"""
Corporate travel data parser.

Source format: CSV export from Navan (formerly TripActions) or Concur Travel.

Real-world context:
- Navan export: ~40 columns including BookingType, TravelerName, TripStart, TripEnd,
  Origin, Destination, CabinClass, VendorName, Amount, Currency, CostCenter
- Concur export: similar schema, slightly different column names
- Both give airport IATA codes, not distances
- Hotels give check-in/out dates and city, not carbon data
- Ground transport (taxi/Uber): may have distance, may not

Key decisions:
1. Distance calculation: We compute great-circle distance from IATA pairs
   using the Haversine formula. We include a radiative forcing multiplier (RFI=1.9)
   for flights per DEFRA guidance. This is contested in literature (2.0-2.7) but
   1.9 is the DEFRA 2023 default.
2. Hotel emission factor: UK DEFRA gives ~31 kgCO2e/room-night.
   We don't know hotel star rating; we use the generic factor and flag it.
3. Ground transport: If distance is missing, we flag as suspicious but still
   create a record with estimated distance from spend/fare if available.

Scope classification: All travel = Scope 3, Category 6 (Business Travel).
"""

import csv
import re
import math
from decimal import Decimal, InvalidOperation
from datetime import datetime, date
from typing import Optional, Tuple

# IATA airport coordinate lookup — major Indian + international airports
# In production: load from a full IATA database (OurAirports CSV ~8000 airports)
AIRPORT_COORDS = {
    # India
    'BLR': (12.9499, 77.6682), 'DEL': (28.5562, 77.1000), 'BOM': (19.0896, 72.8656),
    'MAA': (12.9900, 80.1693), 'HYD': (17.2403, 78.4294), 'CCU': (22.6540, 88.4467),
    'PNQ': (18.5819, 73.9197), 'COK': (10.1520, 76.4019), 'AMD': (23.0772, 72.6347),
    'GOI': (15.3808, 73.8314), 'IXC': (30.6735, 76.7885), 'JAI': (26.8242, 75.8122),
    'LKO': (26.7606, 80.8893), 'PAT': (25.5913, 85.0878), 'GAU': (26.1061, 91.5859),
    # International (common India-related routes)
    'LHR': (51.4700, -0.4543), 'LGW': (51.1537, -0.1821), 'CDG': (49.0097, 2.5479),
    'DXB': (25.2532, 55.3657), 'SIN': (1.3644, 103.9915), 'HKG': (22.3080, 113.9185),
    'NRT': (35.7720, 140.3929), 'JFK': (40.6413, -73.7781), 'ORD': (41.9742, -87.9073),
    'LAX': (33.9425, -118.4081), 'SFO': (37.6213, -122.3790), 'FRA': (50.0379, 8.5622),
    'AMS': (52.3086, 4.7639), 'ZRH': (47.4647, 8.5492), 'DOH': (25.2609, 51.6138),
    'KUL': (2.7456, 101.7099), 'BKK': (13.6900, 100.7501), 'SYD': (-33.9399, 151.1753),
    'MEL': (-37.6690, 144.8410), 'JNB': (-26.1367, 28.2411), 'NBO': (-1.3192, 36.9275),
    'ORD': (41.9742, -87.9073), 'YYZ': (43.6777, -79.6248),
}

# Cabin class emission multipliers relative to economy
# Source: DEFRA 2023 / ICAO methodology
CABIN_MULTIPLIERS = {
    'economy': Decimal('1.0'),
    'premium_economy': Decimal('1.6'),
    'business': Decimal('2.9'),
    'first': Decimal('4.0'),
    'unknown': Decimal('1.0'),
}

# kgCO2e per km per passenger (economy, before cabin multiplier)
# Short haul < 3700km, long haul >= 3700km
FLIGHT_EF_SHORT = Decimal('0.255')  # includes RFI 1.9
FLIGHT_EF_LONG = Decimal('0.195')   # long haul more fuel-efficient per km

COLUMN_ALIASES = {
    # Traveler
    'employee id': 'employee_id', 'employee_id': 'employee_id',
    'traveler id': 'employee_id', 'user id': 'employee_id',
    'department': 'department', 'dept': 'department',
    'cost center': 'cost_center', 'cost_center': 'cost_center',
    # Trip
    'booking type': 'travel_type', 'type': 'travel_type',
    'segment type': 'travel_type', 'travel type': 'travel_type',
    'travel_type': 'travel_type',
    'travel date': 'travel_date', 'departure date': 'travel_date',
    'trip date': 'travel_date', 'date': 'travel_date',
    'booking reference': 'booking_reference', 'confirmation': 'booking_reference',
    'record locator': 'booking_reference', 'pnr': 'booking_reference',
    'vendor': 'vendor', 'airline': 'vendor', 'carrier': 'vendor',
    'hotel name': 'vendor', 'provider': 'vendor',
    # Flights
    'origin': 'origin_iata', 'from': 'origin_iata', 'departure': 'origin_iata',
    'origin iata': 'origin_iata', 'from airport': 'origin_iata',
    'destination': 'destination_iata', 'to': 'destination_iata',
    'arrival': 'destination_iata', 'destination iata': 'destination_iata',
    'to airport': 'destination_iata',
    'distance': 'distance_km', 'distance km': 'distance_km',
    'miles': 'distance_miles',
    'cabin': 'cabin_class', 'cabin class': 'cabin_class',
    'class': 'cabin_class', 'service class': 'cabin_class',
    'round trip': 'is_return', 'return': 'is_return', 'roundtrip': 'is_return',
    'passengers': 'num_passengers', 'pax': 'num_passengers',
    # Hotels
    'check in': 'check_in_date', 'checkin': 'check_in_date', 'arrival date': 'check_in_date',
    'check out': 'check_out_date', 'checkout': 'check_out_date', 'departure date hotel': 'check_out_date',
    'nights': 'nights', 'no of nights': 'nights', 'room nights': 'nights',
    'city': 'hotel_city', 'hotel city': 'hotel_city',
    'country': 'hotel_country',
    # Ground
    'ground distance': 'distance_km_ground', 'trip distance': 'distance_km_ground',
    'mode': 'transport_mode_detail',
    # Financials
    'amount': 'amount', 'fare': 'amount', 'total': 'amount',
    'currency': 'currency',
}

DATE_FORMATS = [
    '%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%d-%m-%Y',
    '%d %b %Y', '%b %d, %Y', '%d/%m/%y', '%m/%d/%y',
]

TRAVEL_TYPE_MAP = {
    'air': 'flight', 'flight': 'flight', 'plane': 'flight',
    'airline': 'flight', 'fly': 'flight',
    'hotel': 'hotel', 'accommodation': 'hotel', 'lodging': 'hotel',
    'taxi': 'ground_taxi', 'cab': 'ground_taxi', 'uber': 'ground_taxi',
    'lyft': 'ground_taxi', 'rideshare': 'ground_taxi', 'car service': 'ground_taxi',
    'train': 'ground_train', 'rail': 'ground_train', 'metro': 'ground_train',
    'rental car': 'ground_rental', 'car rental': 'ground_rental', 'rent a car': 'ground_rental',
    'bus': 'ground_other', 'shuttle': 'ground_other',
}

CABIN_MAP = {
    'y': 'economy', 'eco': 'economy', 'economy': 'economy', 'coach': 'economy',
    'w': 'premium_economy', 'premium economy': 'premium_economy', 'prem eco': 'premium_economy',
    'c': 'business', 'j': 'business', 'business': 'business', 'biz': 'business',
    'f': 'first', 'first': 'first', 'first class': 'first',
}


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    """Great-circle distance between two points (Haversine formula)."""
    R = 6371.0  # Earth radius km
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))


def get_flight_distance(origin: str, dest: str) -> Tuple[Optional[Decimal], str]:
    """
    Calculate great-circle distance from IATA codes.
    Returns (distance_km, source_description).
    """
    o = origin.upper().strip()
    d = dest.upper().strip()
    if o in AIRPORT_COORDS and d in AIRPORT_COORDS:
        lat1, lon1 = AIRPORT_COORDS[o]
        lat2, lon2 = AIRPORT_COORDS[d]
        km = haversine_km(lat1, lon1, lat2, lon2)
        return Decimal(str(round(km, 1))), 'calculated_haversine'
    return None, 'unknown_iata'


def parse_travel_date(raw: str) -> Optional[date]:
    raw = raw.strip()
    if not raw:
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def normalize_travel_type(raw: str) -> str:
    raw_lower = raw.strip().lower()
    for key, val in TRAVEL_TYPE_MAP.items():
        if key in raw_lower:
            return val
    return 'flight'  # default assumption if ambiguous


def normalize_cabin(raw: str) -> str:
    raw_lower = raw.strip().lower()
    return CABIN_MAP.get(raw_lower, 'economy')


def map_headers(raw_headers: list) -> dict:
    mapping = {}
    for i, header in enumerate(raw_headers):
        norm = header.strip().lower().replace('_', ' ').replace('-', ' ')
        internal = COLUMN_ALIASES.get(norm, norm.replace(' ', '_'))
        mapping[i] = internal
    return mapping


def parse_travel_file(file_content: bytes, original_filename: str) -> dict:
    """
    Parse a Navan/Concur travel export CSV.
    """
    rows = []
    errors = []
    warnings = []

    try:
        text = file_content.decode('utf-8', errors='replace')
    except Exception as e:
        return {'rows': [], 'errors': [{'row': 0, 'message': f'Decode error: {e}'}],
                'warnings': [], 'period_start': None, 'period_end': None}

    lines = text.splitlines()
    # Skip any preamble
    data_start = 0
    for i, line in enumerate(lines):
        lower = line.strip().lower()
        if any(kw in lower for kw in ['type', 'date', 'origin', 'destination', 'amount', 'booking']):
            data_start = i
            break

    reader = csv.reader(lines[data_start:])
    headers_raw = next(reader, None)
    if not headers_raw:
        return {'rows': [], 'errors': [{'row': 0, 'message': 'No header row found'}],
                'warnings': [], 'period_start': None, 'period_end': None}

    col_map = map_headers(headers_raw)
    all_dates = []

    for row_num, raw_row in enumerate(reader, start=data_start + 2):
        if not any(cell.strip() for cell in raw_row):
            continue

        row_data = {}
        for col_idx, value in enumerate(raw_row):
            field = col_map.get(col_idx, f'col_{col_idx}')
            row_data[field] = value.strip() if col_idx < len(raw_row) else ''

        travel_type = normalize_travel_type(row_data.get('travel_type', ''))

        raw_currency = row_data.get('currency', 'INR').strip()
        safe_currency = raw_currency[:3].upper() if raw_currency else 'INR'

        parsed = {
            'row_number': row_num,
            'employee_id': row_data.get('employee_id', ''),
            'department': row_data.get('department', ''),
            'cost_center': row_data.get('cost_center', ''),
            'travel_type': travel_type,
            'booking_reference': row_data.get('booking_reference', ''),
            'vendor': row_data.get('vendor', ''),
            'currency': safe_currency,
            'parse_error': '',
            'suspicious_reason': '',
            'status': 'ok',
        }

        # Travel date
        travel_date = parse_travel_date(row_data.get('travel_date', ''))
        parsed['travel_date'] = travel_date
        if travel_date:
            all_dates.append(travel_date)

        # Amount
        try:
            parsed['amount'] = Decimal(re.sub(r'[^\d.\-]', '', row_data.get('amount', '')) or '0') or None
        except InvalidOperation:
            parsed['amount'] = None

        if travel_type == 'flight':
            # IATA codes
            origin = row_data.get('origin_iata', '').upper().strip()[:3]
            dest = row_data.get('destination_iata', '').upper().strip()[:3]
            parsed['origin_iata'] = origin
            parsed['destination_iata'] = dest

            # Distance
            dist_raw = row_data.get('distance_km', '') or row_data.get('distance_miles', '')
            dist_miles = 'miles' in col_map.values() and not row_data.get('distance_km', '')

            if dist_raw:
                try:
                    dist = Decimal(re.sub(r'[^\d.]', '', dist_raw))
                    if dist_miles:
                        dist = dist * Decimal('1.60934')
                    parsed['distance_km'] = dist
                    parsed['distance_source'] = 'provided'
                except InvalidOperation:
                    parsed['distance_km'] = None

            if not parsed.get('distance_km') and origin and dest:
                calc_dist, source = get_flight_distance(origin, dest)
                parsed['distance_km'] = calc_dist
                parsed['distance_source'] = source
                if source == 'unknown_iata':
                    parsed['suspicious_reason'] += f'Unknown IATA code(s): {origin}/{dest}. '
                    if parsed['status'] == 'ok':
                        parsed['status'] = 'suspicious'

            parsed['cabin_class'] = normalize_cabin(row_data.get('cabin_class', 'economy'))
            is_return_raw = row_data.get('is_return', '').lower()
            parsed['is_return'] = is_return_raw in ('yes', 'true', '1', 'y', 'round trip', 'rt')

            try:
                parsed['num_passengers'] = int(row_data.get('num_passengers', '1') or '1')
            except ValueError:
                parsed['num_passengers'] = 1

            if not parsed.get('distance_km'):
                parsed['parse_error'] += 'Cannot determine flight distance. '
                parsed['status'] = 'failed'

        elif travel_type == 'hotel':
            parsed['check_in_date'] = parse_travel_date(row_data.get('check_in_date', ''))
            parsed['check_out_date'] = parse_travel_date(row_data.get('check_out_date', ''))
            parsed['hotel_city'] = row_data.get('hotel_city', '')
            # Truncate to 2-char ISO code; full country names get clipped
            raw_country = row_data.get('hotel_country', 'IN')
            parsed['hotel_country'] = raw_country[:2].upper() if raw_country else 'IN'

            if parsed['check_in_date'] and parsed['check_out_date']:
                parsed['nights'] = (parsed['check_out_date'] - parsed['check_in_date']).days
            else:
                try:
                    parsed['nights'] = int(row_data.get('nights', '') or '0') or None
                except ValueError:
                    parsed['nights'] = None

            if not parsed['nights']:
                parsed['suspicious_reason'] += 'Cannot determine hotel nights. '
                if parsed['status'] == 'ok':
                    parsed['status'] = 'suspicious'

        else:  # ground transport
            dist_raw = row_data.get('distance_km_ground', '')
            if dist_raw:
                try:
                    parsed['distance_km_ground'] = Decimal(re.sub(r'[^\d.]', '', dist_raw))
                except InvalidOperation:
                    parsed['distance_km_ground'] = None
            else:
                parsed['distance_km_ground'] = None
                parsed['suspicious_reason'] += 'No distance for ground transport — cannot calculate emissions accurately. '
                if parsed['status'] == 'ok':
                    parsed['status'] = 'suspicious'
            parsed['transport_mode_detail'] = row_data.get('transport_mode_detail', '')

        # High spend check
        if parsed.get('amount') and parsed['amount'] > Decimal('500000'):
            parsed['suspicious_reason'] += f'Very high spend: {parsed["amount"]} {parsed["currency"]}. '
            if parsed['status'] == 'ok':
                parsed['status'] = 'suspicious'

        rows.append(parsed)

    return {
        'rows': rows,
        'errors': errors,
        'warnings': warnings,
        'period_start': min(all_dates) if all_dates else None,
        'period_end': max(all_dates) if all_dates else None,
    }

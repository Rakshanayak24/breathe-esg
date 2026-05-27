"""
Emission calculator — converts normalized raw rows into EmissionRecords.

Runs after an analyst approves a batch (or individual rows).
All factors are documented with source citations.

Design: Calculator is pure (no DB writes). The view/serializer handles
saving so we can unit-test the math independently.
"""

from decimal import Decimal
from django.conf import settings

EF = settings.EMISSION_FACTORS

# Fuel → kgCO2e per litre (IPCC AR6 / DEFRA 2023)
FUEL_EF = {
    'diesel': Decimal('2.68'),
    'petrol': Decimal('2.31'),
    'lpg': Decimal('1.51'),
    'cng': Decimal('2.16'),   # per litre LNG equivalent
    'natural_gas': Decimal('2.04'),   # per m3
    'fuel_oil': Decimal('3.18'),
    'hfo': Decimal('3.18'),
}

# kgCO2e per kWh — grid emission factors by region
GRID_EF = {
    'default_india': Decimal('0.82'),   # CEA 2023-24 national avg
    'northern': Decimal('0.7065'),
    'western': Decimal('0.8105'),
    'southern': Decimal('0.7816'),
    'eastern': Decimal('0.9185'),
    'default_uk': Decimal('0.233'),
    'default_us': Decimal('0.386'),
}

# Flight EF kgCO2e/km/pax (includes RFI 1.9 per DEFRA 2023)
FLIGHT_EF_SHORT = Decimal('0.255')
FLIGHT_EF_LONG = Decimal('0.195')
FLIGHT_CABIN_MULTIPLIERS = {
    'economy': Decimal('1.0'),
    'premium_economy': Decimal('1.6'),
    'business': Decimal('2.9'),
    'first': Decimal('4.0'),
    'unknown': Decimal('1.0'),
}

HOTEL_EF = Decimal('31.0')  # kgCO2e per room-night (DEFRA 2023)

GROUND_EF = {
    'ground_taxi': Decimal('0.149'),     # kgCO2e/km
    'ground_train': Decimal('0.041'),
    'ground_rental': Decimal('0.171'),
    'ground_other': Decimal('0.149'),    # assume taxi-like
}


def calc_sap_emission(row) -> dict:
    """
    Calculate emission for a SAP fuel row.
    Returns dict with emission data or None if not calculable.

    Scope 1 for direct combustion (stationary boilers, generators),
    Scope 3.1 for procurement that's not direct combustion.
    """
    if not row.is_fuel or not row.quantity_normalized:
        return None

    fuel_type = row.fuel_type or 'diesel'
    ef = FUEL_EF.get(fuel_type, FUEL_EF['diesel'])

    # Unit: normalized to L or kg or m3
    unit = row.quantity_normalized_unit
    qty = row.quantity_normalized

    # Convert m3 natural gas to kWh-equivalent for EF
    if unit == 'm3' and fuel_type == 'natural_gas':
        ef = Decimal('2.04')  # kgCO2e per m3 natural gas
    elif unit == 'kg':
        # Convert to litre equivalent for liquid fuels
        density = {'diesel': Decimal('0.832'), 'petrol': Decimal('0.745'), 'fuel_oil': Decimal('0.950')}
        d = density.get(fuel_type, Decimal('0.832'))
        qty = qty / d  # kg → L

    co2e_kg = qty * ef
    co2e_tonnes = co2e_kg / Decimal('1000')

    return {
        'scope': 'scope1',
        'category': 's1_stationary',
        'activity_value': qty,
        'activity_unit': 'L',
        'emission_factor': ef,
        'emission_factor_source': 'IPCC AR6 WG3 Annex II / DEFRA 2023',
        'emission_factor_unit': 'kgCO2e/L',
        'co2e_tonnes': co2e_tonnes,
        'activity_period_start': row.posting_date,
        'activity_period_end': row.posting_date,
    }


def calc_utility_emission(row) -> dict:
    """
    Scope 2 location-based emission from electricity consumption.
    Uses CEA grid emission factor for India.
    """
    if not row.units_consumed_kwh:
        return None

    ef = row.emission_factor_used or GRID_EF['default_india']
    co2e_kg = row.units_consumed_kwh * ef
    co2e_tonnes = co2e_kg / Decimal('1000')

    return {
        'scope': 'scope2_location',
        'category': 's2_electricity',
        'activity_value': row.units_consumed_kwh,
        'activity_unit': 'kWh',
        'emission_factor': ef,
        'emission_factor_source': 'CEA CO2 Baseline Database Version 18 (March 2024)',
        'emission_factor_unit': 'kgCO2e/kWh',
        'co2e_tonnes': co2e_tonnes,
        'activity_period_start': row.billing_period_start,
        'activity_period_end': row.billing_period_end,
    }


def calc_travel_emission(row) -> dict:
    """
    Scope 3 Category 6 (Business Travel) emissions.
    """
    if row.travel_type == 'flight':
        if not row.distance_km:
            return None

        dist = row.distance_km
        if row.is_return:
            dist = dist * Decimal('2')

        ef_base = FLIGHT_EF_SHORT if dist < Decimal('3700') else FLIGHT_EF_LONG
        cabin_mult = FLIGHT_CABIN_MULTIPLIERS.get(row.cabin_class or 'economy', Decimal('1.0'))
        ef = ef_base * cabin_mult
        co2e_kg = dist * ef * Decimal(str(row.num_passengers or 1))
        co2e_tonnes = co2e_kg / Decimal('1000')

        from datetime import date as _date
        period_date = row.travel_date or _date.today()

        return {
            'scope': 'scope3',
            'category': 's3_business_travel',
            'activity_value': dist,
            'activity_unit': 'km',
            'emission_factor': ef,
            'emission_factor_source': 'DEFRA 2023 (GHG Conversion Factors, incl. RFI 1.9)',
            'emission_factor_unit': 'kgCO2e/km/pax',
            'co2e_tonnes': co2e_tonnes,
            'activity_period_start': period_date,
            'activity_period_end': period_date,
        }

    elif row.travel_type == 'hotel':
        if not row.nights:
            return None

        co2e_kg = Decimal(str(row.nights)) * HOTEL_EF
        co2e_tonnes = co2e_kg / Decimal('1000')

        # Fallback: if check_in/out missing, use travel_date or today
        from datetime import date as _date
        period_start = row.check_in_date or row.travel_date or _date.today()
        period_end = row.check_out_date or row.travel_date or _date.today()

        return {
            'scope': 'scope3',
            'category': 's3_business_travel',
            'activity_value': Decimal(str(row.nights)),
            'activity_unit': 'room-nights',
            'emission_factor': HOTEL_EF,
            'emission_factor_source': 'DEFRA 2023 (GHG Conversion Factors)',
            'emission_factor_unit': 'kgCO2e/room-night',
            'co2e_tonnes': co2e_tonnes,
            'activity_period_start': period_start,
            'activity_period_end': period_end,
        }

    else:  # ground transport
        dist = row.distance_km_ground
        if not dist:
            return None

        from datetime import date as _date
        period_date = row.travel_date or _date.today()

        ef = GROUND_EF.get(row.travel_type, GROUND_EF['ground_taxi'])
        co2e_kg = dist * ef
        co2e_tonnes = co2e_kg / Decimal('1000')

        return {
            'scope': 'scope3',
            'category': 's3_business_travel',
            'activity_value': dist,
            'activity_unit': 'km',
            'emission_factor': ef,
            'emission_factor_source': 'DEFRA 2023 (GHG Conversion Factors)',
            'emission_factor_unit': 'kgCO2e/km',
            'co2e_tonnes': co2e_tonnes,
            'activity_period_start': period_date,
            'activity_period_end': period_date,
        }

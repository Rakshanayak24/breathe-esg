"""
Ingestion models for Breathe ESG data pipeline.

Design philosophy:
- Every row is traceable to its source file/API call, with full audit trail
- Units are normalized to SI at write time; originals preserved for audit
- Multi-tenancy via Organisation FK on all data rows
- Scope 1/2/3 classification on EmissionRecord, not on raw rows
- IngestionBatch is the unit of review — analysts approve batches, not rows
"""

from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import uuid


class Organisation(models.Model):
    """
    Top-level tenant. All data is scoped to an org.
    Using UUID PK so org IDs can't be enumerated.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    country_code = models.CharField(max_length=2, default='IN')  # ISO 3166-1 alpha-2
    reporting_year_start = models.PositiveSmallIntegerField(default=4)  # April = Indian FY
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class OrganisationMembership(models.Model):
    """Links users to orgs with roles."""
    ROLE_CHOICES = [
        ('analyst', 'Analyst'),
        ('approver', 'Approver'),
        ('admin', 'Admin'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='memberships')
    organisation = models.ForeignKey(Organisation, on_delete=models.CASCADE, related_name='memberships')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='analyst')
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'organisation')


class IngestionBatch(models.Model):
    """
    One batch = one file upload or one API pull.
    Analysts review at the batch level before approving rows.

    SOURCE_TYPE drives which parser runs. INGESTION_MODE captures
    how data arrived — file upload is the primary mode for all three
    sources (see DECISIONS.md for justification).
    """
    SOURCE_TYPE_CHOICES = [
        ('sap_fuel_procurement', 'SAP Fuel & Procurement'),
        ('utility_electricity', 'Utility Electricity'),
        ('travel_corporate', 'Corporate Travel'),
    ]
    STATUS_CHOICES = [
        ('pending', 'Pending Review'),
        ('in_review', 'In Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('partial', 'Partially Approved'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organisation = models.ForeignKey(Organisation, on_delete=models.CASCADE, related_name='batches')
    source_type = models.CharField(max_length=40, choices=SOURCE_TYPE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    # Source-of-truth tracking
    uploaded_file = models.FileField(upload_to='uploads/%Y/%m/', blank=True, null=True)
    original_filename = models.CharField(max_length=500, blank=True)
    file_hash_sha256 = models.CharField(max_length=64, blank=True)  # detect re-uploads

    # Reporting period this batch covers
    period_start = models.DateField(null=True, blank=True)
    period_end = models.DateField(null=True, blank=True)

    # Parse statistics
    rows_parsed = models.PositiveIntegerField(default=0)
    rows_failed = models.PositiveIntegerField(default=0)
    rows_suspicious = models.PositiveIntegerField(default=0)

    # Audit trail
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='uploaded_batches')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_batches')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_batches')
    approved_at = models.DateTimeField(null=True, blank=True)

    parse_log = models.JSONField(default=list)  # list of parse warnings/errors
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"{self.organisation.slug} / {self.source_type} / {self.uploaded_at:%Y-%m-%d}"

    @property
    def success_rate(self):
        total = self.rows_parsed + self.rows_failed
        return (self.rows_parsed / total * 100) if total > 0 else 0


class RawSAPRow(models.Model):
    """
    Raw SAP flat-file row after parsing, before normalization.

    We chose SAP flat-file (pipe-delimited text, COOIS/MB51 style) over IDoc
    because: flat files are what clients actually email. IDocs require
    middleware access we don't have. OData needs VPN + auth setup.
    See DECISIONS.md.

    Column mapping preserves original SAP field names where known.
    German variants normalized at parse time (Menge→quantity, Werk→plant).
    """
    ROW_STATUS_CHOICES = [
        ('ok', 'OK'),
        ('suspicious', 'Suspicious'),
        ('failed', 'Parse Failed'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    batch = models.ForeignKey(IngestionBatch, on_delete=models.CASCADE, related_name='sap_rows')
    organisation = models.ForeignKey(Organisation, on_delete=models.CASCADE, related_name='sap_rows')
    status = models.CharField(max_length=20, choices=ROW_STATUS_CHOICES, default='ok')
    row_number = models.PositiveIntegerField()  # line number in source file

    # SAP identifiers
    plant_code = models.CharField(max_length=20, blank=True)       # Werk
    plant_name = models.CharField(max_length=200, blank=True)      # resolved from lookup
    cost_center = models.CharField(max_length=20, blank=True)
    material_number = models.CharField(max_length=40, blank=True)  # Materialnummer
    material_description = models.CharField(max_length=300, blank=True)
    document_number = models.CharField(max_length=40, blank=True)  # Belegnummer
    document_type = models.CharField(max_length=10, blank=True)    # e.g. WA (goods issue)

    # Dates — SAP uses DD.MM.YYYY in German locale, YYYYMMDD in IDocs
    posting_date_raw = models.CharField(max_length=20, blank=True)  # as-found
    posting_date = models.DateField(null=True, blank=True)           # parsed

    # Quantity — original unit preserved; normalized_quantity in kg or kWh
    quantity_raw = models.CharField(max_length=30, blank=True)
    quantity = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    unit_of_measure_raw = models.CharField(max_length=20, blank=True)  # L, KG, M3, GAL...
    unit_of_measure_normalized = models.CharField(max_length=10, blank=True)  # always SI

    # Fuel/material classification
    fuel_type = models.CharField(max_length=50, blank=True)  # resolved from material
    is_fuel = models.BooleanField(default=False)
    is_procurement = models.BooleanField(default=False)

    # Normalized
    quantity_normalized = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    quantity_normalized_unit = models.CharField(max_length=10, blank=True)  # L or kg

    # Flags
    suspicious_reason = models.TextField(blank=True)
    parse_error = models.TextField(blank=True)

    # Audit
    created_at = models.DateTimeField(auto_now_add=True)
    edited_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    edited_at = models.DateTimeField(null=True, blank=True)
    edit_note = models.TextField(blank=True)

    class Meta:
        ordering = ['batch', 'row_number']


class RawUtilityRow(models.Model):
    """
    Utility electricity bill data.

    Source: portal CSV export (BESCOM/Tata Power format in India,
    or generic utility CSV). We chose CSV over PDF because:
    - Portal exports are machine-readable CSV; PDFs are for humans
    - PDF parsing requires OCR and table extraction which is fragile
    - See DECISIONS.md

    Billing periods don't align with calendar months — we store
    period_start/end explicitly and handle overlap in emission calc.
    """
    ROW_STATUS_CHOICES = [
        ('ok', 'OK'),
        ('suspicious', 'Suspicious'),
        ('failed', 'Parse Failed'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    batch = models.ForeignKey(IngestionBatch, on_delete=models.CASCADE, related_name='utility_rows')
    organisation = models.ForeignKey(Organisation, on_delete=models.CASCADE, related_name='utility_rows')
    status = models.CharField(max_length=20, choices=ROW_STATUS_CHOICES, default='ok')
    row_number = models.PositiveIntegerField()

    # Meter / site identification
    account_number = models.CharField(max_length=50, blank=True)
    meter_id = models.CharField(max_length=50, blank=True)
    site_name = models.CharField(max_length=200, blank=True)
    site_address = models.TextField(blank=True)
    tariff_category = models.CharField(max_length=50, blank=True)  # HT, LT, Industrial...

    # Billing period — NOT calendar month
    billing_period_start = models.DateField(null=True, blank=True)
    billing_period_end = models.DateField(null=True, blank=True)
    billing_period_days = models.PositiveIntegerField(null=True, blank=True)

    # Consumption
    units_consumed_raw = models.CharField(max_length=30, blank=True)
    units_consumed_kwh = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    # Meter readings if available
    opening_reading = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    closing_reading = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    multiplier = models.DecimalField(max_digits=10, decimal_places=4, default=1)  # CT ratio

    # Tariff structure
    peak_units_kwh = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    off_peak_units_kwh = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    reactive_units_kvarh = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)

    # Financials (informational, not used in emission calc)
    bill_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, default='INR')

    # Grid emission factor used
    grid_region = models.CharField(max_length=50, blank=True)  # e.g. 'southern_india'
    emission_factor_used = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)

    # Flags
    suspicious_reason = models.TextField(blank=True)
    parse_error = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    edited_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    edited_at = models.DateTimeField(null=True, blank=True)
    edit_note = models.TextField(blank=True)

    class Meta:
        ordering = ['batch', 'row_number']


class RawTravelRow(models.Model):
    """
    Corporate travel data. Source: Navan/Concur CSV export.

    We chose file export over API because:
    - Concur/Navan API requires OAuth2 app registration + enterprise agreement
    - CSV exports are available to any admin immediately
    - Real deployment would add API pull; see TRADEOFFS.md

    Distances are NOT always provided (Concur gives airport codes, not km).
    We calculate great-circle distance from IATA codes when distance absent.
    """
    TRAVEL_TYPE_CHOICES = [
        ('flight', 'Flight'),
        ('hotel', 'Hotel'),
        ('ground_taxi', 'Taxi/Rideshare'),
        ('ground_train', 'Train/Rail'),
        ('ground_rental', 'Rental Car'),
        ('ground_other', 'Ground Other'),
    ]
    CABIN_CHOICES = [
        ('economy', 'Economy'),
        ('premium_economy', 'Premium Economy'),
        ('business', 'Business'),
        ('first', 'First'),
        ('unknown', 'Unknown'),
    ]
    ROW_STATUS_CHOICES = [
        ('ok', 'OK'),
        ('suspicious', 'Suspicious'),
        ('failed', 'Parse Failed'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    batch = models.ForeignKey(IngestionBatch, on_delete=models.CASCADE, related_name='travel_rows')
    organisation = models.ForeignKey(Organisation, on_delete=models.CASCADE, related_name='travel_rows')
    status = models.CharField(max_length=20, choices=ROW_STATUS_CHOICES, default='ok')
    row_number = models.PositiveIntegerField()

    # Employee (anonymized in prod — hash instead of name)
    employee_id = models.CharField(max_length=50, blank=True)
    department = models.CharField(max_length=100, blank=True)
    cost_center = models.CharField(max_length=50, blank=True)

    travel_type = models.CharField(max_length=20, choices=TRAVEL_TYPE_CHOICES)
    travel_date = models.DateField(null=True, blank=True)
    booking_reference = models.CharField(max_length=50, blank=True)
    vendor = models.CharField(max_length=100, blank=True)

    # Flights
    origin_iata = models.CharField(max_length=3, blank=True)
    destination_iata = models.CharField(max_length=3, blank=True)
    distance_km = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    distance_source = models.CharField(max_length=20, blank=True)  # 'provided', 'calculated', 'estimated'
    cabin_class = models.CharField(max_length=20, choices=CABIN_CHOICES, default='economy')
    is_return = models.BooleanField(default=False)
    num_passengers = models.PositiveSmallIntegerField(default=1)

    # Hotels
    check_in_date = models.DateField(null=True, blank=True)
    check_out_date = models.DateField(null=True, blank=True)
    nights = models.PositiveSmallIntegerField(null=True, blank=True)
    hotel_country = models.CharField(max_length=2, blank=True)  # ISO
    hotel_city = models.CharField(max_length=100, blank=True)

    # Ground transport
    distance_km_ground = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    transport_mode_detail = models.CharField(max_length=100, blank=True)

    # Financials
    amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, default='INR')

    # Flags
    suspicious_reason = models.TextField(blank=True)
    parse_error = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    edited_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    edited_at = models.DateTimeField(null=True, blank=True)
    edit_note = models.TextField(blank=True)

    class Meta:
        ordering = ['batch', 'row_number']


class EmissionRecord(models.Model):
    """
    The canonical emission record — one per raw row, created after approval.
    This is what goes to auditors.

    Scope classification:
    - Scope 1: Direct combustion (SAP fuel rows, company-owned vehicles)
    - Scope 2: Purchased electricity (utility rows) — market-based or location-based
    - Scope 3: Business travel (all travel rows), procurement supply chain

    Once locked (after approval), records are immutable. Corrections create
    new records with a supersedes FK, never overwrite.
    """
    SCOPE_CHOICES = [
        ('scope1', 'Scope 1 — Direct'),
        ('scope2_location', 'Scope 2 — Location-Based'),
        ('scope2_market', 'Scope 2 — Market-Based'),
        ('scope3', 'Scope 3 — Value Chain'),
    ]
    CATEGORY_CHOICES = [
        # Scope 1
        ('s1_stationary', 'S1: Stationary Combustion'),
        ('s1_mobile', 'S1: Mobile Combustion'),
        # Scope 2
        ('s2_electricity', 'S2: Purchased Electricity'),
        # Scope 3
        ('s3_business_travel', 'S3.6: Business Travel'),
        ('s3_purchased_goods', 'S3.1: Purchased Goods & Services'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organisation = models.ForeignKey(Organisation, on_delete=models.CASCADE, related_name='emission_records')
    batch = models.ForeignKey(IngestionBatch, on_delete=models.CASCADE, related_name='emission_records')

    # Traceability — exactly one of these is set
    source_sap_row = models.OneToOneField(RawSAPRow, on_delete=models.SET_NULL, null=True, blank=True)
    source_utility_row = models.OneToOneField(RawUtilityRow, on_delete=models.SET_NULL, null=True, blank=True)
    source_travel_row = models.OneToOneField(RawTravelRow, on_delete=models.SET_NULL, null=True, blank=True)

    scope = models.CharField(max_length=20, choices=SCOPE_CHOICES)
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES)

    activity_period_start = models.DateField()
    activity_period_end = models.DateField()

    # Activity data (normalized)
    activity_value = models.DecimalField(max_digits=18, decimal_places=4)
    activity_unit = models.CharField(max_length=20)  # L, kWh, km, room-nights

    # Emission calculation
    emission_factor = models.DecimalField(max_digits=10, decimal_places=6)
    emission_factor_source = models.CharField(max_length=100)  # e.g. 'IPCC AR6', 'CEA 2023-24'
    emission_factor_unit = models.CharField(max_length=30)  # kgCO2e/L, kgCO2e/kWh
    co2e_tonnes = models.DecimalField(max_digits=14, decimal_places=6)

    # Audit lock
    is_locked = models.BooleanField(default=False)
    locked_at = models.DateTimeField(null=True, blank=True)
    locked_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='locked_records')

    # Corrections (immutable history)
    supersedes = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='superseded_by')

    created_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-activity_period_start']

    def __str__(self):
        return f"{self.scope} / {self.co2e_tonnes:.4f} tCO2e / {self.activity_period_start}"

    def lock(self, user):
        self.is_locked = True
        self.locked_at = timezone.now()
        self.locked_by = user
        self.save()

from django.contrib import admin
from .models import (
    Organisation, OrganisationMembership, IngestionBatch,
    RawSAPRow, RawUtilityRow, RawTravelRow, EmissionRecord
)

@admin.register(Organisation)
class OrganisationAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'country_code', 'created_at']
    prepopulated_fields = {'slug': ('name',)}

@admin.register(OrganisationMembership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ['user', 'organisation', 'role', 'joined_at']

@admin.register(IngestionBatch)
class BatchAdmin(admin.ModelAdmin):
    list_display = ['id', 'organisation', 'source_type', 'status', 'rows_parsed', 'rows_failed', 'uploaded_at']
    list_filter = ['source_type', 'status', 'organisation']
    readonly_fields = ['file_hash_sha256', 'parse_log']

@admin.register(RawSAPRow)
class SAPRowAdmin(admin.ModelAdmin):
    list_display = ['batch', 'row_number', 'plant_code', 'material_description', 'quantity', 'unit_of_measure_raw', 'posting_date', 'status']
    list_filter = ['status', 'is_fuel']

@admin.register(RawUtilityRow)
class UtilityRowAdmin(admin.ModelAdmin):
    list_display = ['batch', 'meter_id', 'site_name', 'units_consumed_kwh', 'billing_period_start', 'billing_period_end', 'status']
    list_filter = ['status']

@admin.register(RawTravelRow)
class TravelRowAdmin(admin.ModelAdmin):
    list_display = ['batch', 'travel_type', 'origin_iata', 'destination_iata', 'travel_date', 'cabin_class', 'status']
    list_filter = ['status', 'travel_type']

@admin.register(EmissionRecord)
class EmissionRecordAdmin(admin.ModelAdmin):
    list_display = ['scope', 'category', 'co2e_tonnes', 'activity_period_start', 'is_locked', 'created_at']
    list_filter = ['scope', 'category', 'is_locked']
    readonly_fields = ['is_locked', 'locked_at', 'locked_by']

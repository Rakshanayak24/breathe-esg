from rest_framework import serializers
from django.contrib.auth.models import User
from .models import (
    Organisation, OrganisationMembership, IngestionBatch,
    RawSAPRow, RawUtilityRow, RawTravelRow, EmissionRecord
)


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name']


class OrganisationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organisation
        fields = ['id', 'name', 'slug', 'country_code', 'reporting_year_start', 'created_at']


class IngestionBatchSerializer(serializers.ModelSerializer):
    uploaded_by_name = serializers.SerializerMethodField()
    reviewed_by_name = serializers.SerializerMethodField()
    approved_by_name = serializers.SerializerMethodField()
    source_type_display = serializers.CharField(source='get_source_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    success_rate = serializers.FloatField(read_only=True)

    class Meta:
        model = IngestionBatch
        fields = [
            'id', 'organisation', 'source_type', 'source_type_display',
            'status', 'status_display',
            'original_filename', 'file_hash_sha256',
            'period_start', 'period_end',
            'rows_parsed', 'rows_failed', 'rows_suspicious',
            'uploaded_by', 'uploaded_by_name', 'uploaded_at',
            'reviewed_by', 'reviewed_by_name', 'reviewed_at',
            'approved_by', 'approved_by_name', 'approved_at',
            'parse_log', 'notes', 'success_rate',
        ]
        read_only_fields = [
            'id', 'file_hash_sha256', 'rows_parsed', 'rows_failed',
            'rows_suspicious', 'uploaded_by', 'uploaded_at', 'success_rate',
        ]

    def get_uploaded_by_name(self, obj):
        return obj.uploaded_by.get_full_name() or obj.uploaded_by.username if obj.uploaded_by else None

    def get_reviewed_by_name(self, obj):
        return obj.reviewed_by.get_full_name() or obj.reviewed_by.username if obj.reviewed_by else None

    def get_approved_by_name(self, obj):
        return obj.approved_by.get_full_name() or obj.approved_by.username if obj.approved_by else None


class RawSAPRowSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    edited_by_name = serializers.SerializerMethodField()

    class Meta:
        model = RawSAPRow
        fields = '__all__'
        read_only_fields = ['id', 'batch', 'organisation', 'row_number', 'created_at']

    def get_edited_by_name(self, obj):
        return obj.edited_by.get_full_name() or obj.edited_by.username if obj.edited_by else None


class RawUtilityRowSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    edited_by_name = serializers.SerializerMethodField()

    class Meta:
        model = RawUtilityRow
        fields = '__all__'
        read_only_fields = ['id', 'batch', 'organisation', 'row_number', 'created_at']

    def get_edited_by_name(self, obj):
        return obj.edited_by.get_full_name() or obj.edited_by.username if obj.edited_by else None


class RawTravelRowSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    edited_by_name = serializers.SerializerMethodField()
    travel_type_display = serializers.CharField(source='get_travel_type_display', read_only=True)

    class Meta:
        model = RawTravelRow
        fields = '__all__'
        read_only_fields = ['id', 'batch', 'organisation', 'row_number', 'created_at']

    def get_edited_by_name(self, obj):
        return obj.edited_by.get_full_name() or obj.edited_by.username if obj.edited_by else None


class EmissionRecordSerializer(serializers.ModelSerializer):
    scope_display = serializers.CharField(source='get_scope_display', read_only=True)
    category_display = serializers.CharField(source='get_category_display', read_only=True)
    locked_by_name = serializers.SerializerMethodField()

    class Meta:
        model = EmissionRecord
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'is_locked', 'locked_at', 'locked_by']

    def get_locked_by_name(self, obj):
        return obj.locked_by.get_full_name() or obj.locked_by.username if obj.locked_by else None


class BatchUploadSerializer(serializers.Serializer):
    """Used for file upload endpoint."""
    source_type = serializers.ChoiceField(choices=IngestionBatch.SOURCE_TYPE_CHOICES)
    file = serializers.FileField()
    notes = serializers.CharField(required=False, allow_blank=True)


class BatchApproveSerializer(serializers.Serializer):
    """Used for batch approval endpoint."""
    notes = serializers.CharField(required=False, allow_blank=True)
    row_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        help_text='If provided, approve only these rows. Otherwise approve all ok/suspicious rows.'
    )


class DashboardStatsSerializer(serializers.Serializer):
    """Summary stats for dashboard."""
    total_batches = serializers.IntegerField()
    pending_batches = serializers.IntegerField()
    approved_batches = serializers.IntegerField()
    total_co2e_tonnes = serializers.DecimalField(max_digits=18, decimal_places=4)
    scope1_tonnes = serializers.DecimalField(max_digits=18, decimal_places=4)
    scope2_tonnes = serializers.DecimalField(max_digits=18, decimal_places=4)
    scope3_tonnes = serializers.DecimalField(max_digits=18, decimal_places=4)
    by_source = serializers.DictField()
    by_month = serializers.ListField()

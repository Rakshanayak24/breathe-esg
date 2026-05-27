"""
API views for Breathe ESG ingestion pipeline.
"""

import hashlib
from decimal import Decimal
from django.utils import timezone
from django.db import transaction
from django.db.models import Sum, Count, Q
from django.contrib.auth import authenticate
from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

from .models import (
    Organisation, IngestionBatch, RawSAPRow, RawUtilityRow,
    RawTravelRow, EmissionRecord
)
from .serializers import (
    OrganisationSerializer, IngestionBatchSerializer,
    RawSAPRowSerializer, RawUtilityRowSerializer, RawTravelRowSerializer,
    EmissionRecordSerializer, BatchUploadSerializer, BatchApproveSerializer
)
from .parsers_sap import parse_sap_file
from .parsers_utility import parse_utility_file
from .parsers_travel import parse_travel_file
from .calculators import calc_sap_emission, calc_utility_emission, calc_travel_emission


@api_view(['POST'])
@permission_classes([AllowAny])
def login_view(request):
    username = request.data.get('username')
    password = request.data.get('password')
    user = authenticate(username=username, password=password)
    if user:
        token, _ = Token.objects.get_or_create(user=user)
        # Get user's org
        membership = user.memberships.select_related('organisation').first()
        org_data = None
        if membership:
            org_data = {
                'id': str(membership.organisation.id),
                'name': membership.organisation.name,
                'slug': membership.organisation.slug,
                'role': membership.role,
            }
        return Response({
            'token': token.key,
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'name': user.get_full_name() or user.username,
            },
            'organisation': org_data,
        })
    return Response({'error': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def logout_view(request):
    request.user.auth_token.delete()
    return Response({'message': 'Logged out'})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def me_view(request):
    user = request.user
    membership = user.memberships.select_related('organisation').first()
    org_data = None
    if membership:
        org_data = {
            'id': str(membership.organisation.id),
            'name': membership.organisation.name,
            'slug': membership.organisation.slug,
            'role': membership.role,
        }
    return Response({
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'name': user.get_full_name() or user.username,
        'organisation': org_data,
    })


def get_user_org(user):
    """Get the organisation for the current user."""
    membership = user.memberships.select_related('organisation').first()
    if membership:
        return membership.organisation
    return None


class IngestionBatchViewSet(viewsets.ModelViewSet):
    serializer_class = IngestionBatchSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def get_queryset(self):
        org = get_user_org(self.request.user)
        if not org:
            return IngestionBatch.objects.none()
        qs = IngestionBatch.objects.filter(organisation=org).select_related(
            'uploaded_by', 'reviewed_by', 'approved_by'
        )
        source_type = self.request.query_params.get('source_type')
        if source_type:
            qs = qs.filter(source_type=source_type)
        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs

    @action(detail=False, methods=['post'], url_path='upload')
    def upload(self, request):
        """
        Upload a data file and trigger parsing.
        Multipart form: source_type + file.
        """
        serializer = BatchUploadSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        org = get_user_org(request.user)
        if not org:
            return Response({'error': 'User has no organisation'}, status=status.HTTP_403_FORBIDDEN)

        uploaded_file = serializer.validated_data['file']
        source_type = serializer.validated_data['source_type']
        notes = serializer.validated_data.get('notes', '')

        # Read file content and compute hash
        content = uploaded_file.read()
        file_hash = hashlib.sha256(content).hexdigest()

        # Check for duplicate upload
        if IngestionBatch.objects.filter(
            organisation=org,
            file_hash_sha256=file_hash
        ).exists():
            return Response(
                {'error': 'This file has already been uploaded (duplicate SHA256 hash).'},
                status=status.HTTP_409_CONFLICT
            )

        with transaction.atomic():
            # Create batch record
            batch = IngestionBatch.objects.create(
                organisation=org,
                source_type=source_type,
                original_filename=uploaded_file.name,
                file_hash_sha256=file_hash,
                uploaded_by=request.user,
                notes=notes,
                status='pending',
            )

            # Parse file
            parse_result = _parse_file(source_type, content, uploaded_file.name)
            rows_ok = 0
            rows_failed = 0
            rows_suspicious = 0

            if source_type == 'sap_fuel_procurement':
                for row_data in parse_result['rows']:
                    s = row_data.get('status', 'ok')
                    if s == 'failed':
                        rows_failed += 1
                    elif s == 'suspicious':
                        rows_suspicious += 1
                    else:
                        rows_ok += 1
                    try:
                        RawSAPRow.objects.create(
                            batch=batch,
                            organisation=org,
                            **_sap_row_fields(row_data)
                        )
                    except Exception as e:
                        rows_failed += 1
                        batch.parse_log.append({'row': row_data.get('row_number', '?'), 'message': f'DB save error: {str(e)}'})

            elif source_type == 'utility_electricity':
                for row_data in parse_result['rows']:
                    s = row_data.get('status', 'ok')
                    if s == 'failed':
                        rows_failed += 1
                    elif s == 'suspicious':
                        rows_suspicious += 1
                    else:
                        rows_ok += 1
                    try:
                        RawUtilityRow.objects.create(
                            batch=batch,
                            organisation=org,
                            **_utility_row_fields(row_data)
                        )
                    except Exception as e:
                        rows_failed += 1
                        batch.parse_log.append({'row': row_data.get('row_number', '?'), 'message': f'DB save error: {str(e)}'})

            elif source_type == 'travel_corporate':
                for row_data in parse_result['rows']:
                    s = row_data.get('status', 'ok')
                    if s == 'failed':
                        rows_failed += 1
                    elif s == 'suspicious':
                        rows_suspicious += 1
                    else:
                        rows_ok += 1
                    try:
                        RawTravelRow.objects.create(
                            batch=batch,
                            organisation=org,
                            **_travel_row_fields(row_data)
                        )
                    except Exception as e:
                        rows_failed += 1
                        batch.parse_log.append({'row': row_data.get('row_number', '?'), 'message': f'DB save error: {str(e)}'})

            batch.rows_parsed = rows_ok + rows_suspicious
            batch.rows_failed = rows_failed
            batch.rows_suspicious = rows_suspicious
            batch.period_start = parse_result.get('period_start')
            batch.period_end = parse_result.get('period_end')
            batch.parse_log = parse_result.get('errors', []) + parse_result.get('warnings', [])
            batch.save()

        return Response(
            IngestionBatchSerializer(batch).data,
            status=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=['post'], url_path='approve',
            parser_classes=[JSONParser, FormParser])
    def approve(self, request, pk=None):
        """Approve a batch (or specific rows), create EmissionRecords, lock."""
        batch = self.get_object()
        if batch.status == 'approved':
            return Response({'error': 'Batch already approved'}, status=status.HTTP_400_BAD_REQUEST)

        serializer = BatchApproveSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        row_ids = serializer.validated_data.get('row_ids', [])

        with transaction.atomic():
            emission_records_created = 0

            if batch.source_type == 'sap_fuel_procurement':
                qs = batch.sap_rows.filter(status__in=['ok', 'suspicious'])
                if row_ids:
                    qs = qs.filter(id__in=row_ids)
                for row in qs:
                    em_data = calc_sap_emission(row)
                    if em_data:
                        EmissionRecord.objects.create(
                            organisation=batch.organisation,
                            batch=batch,
                            source_sap_row=row,
                            **em_data,
                        )
                        emission_records_created += 1
                    row.status = 'approved'
                    row.save(update_fields=['status'])

            elif batch.source_type == 'utility_electricity':
                qs = batch.utility_rows.filter(status__in=['ok', 'suspicious'])
                if row_ids:
                    qs = qs.filter(id__in=row_ids)
                for row in qs:
                    em_data = calc_utility_emission(row)
                    if em_data:
                        EmissionRecord.objects.create(
                            organisation=batch.organisation,
                            batch=batch,
                            source_utility_row=row,
                            **em_data,
                        )
                        emission_records_created += 1
                    row.status = 'approved'
                    row.save(update_fields=['status'])

            elif batch.source_type == 'travel_corporate':
                qs = batch.travel_rows.filter(status__in=['ok', 'suspicious'])
                if row_ids:
                    qs = qs.filter(id__in=row_ids)
                for row in qs:
                    em_data = calc_travel_emission(row)
                    if em_data:
                        EmissionRecord.objects.create(
                            organisation=batch.organisation,
                            batch=batch,
                            source_travel_row=row,
                            **em_data,
                        )
                        emission_records_created += 1
                    row.status = 'approved'
                    row.save(update_fields=['status'])

            batch.status = 'approved'
            batch.approved_by = request.user
            batch.approved_at = timezone.now()
            batch.save()

            # Lock all emission records
            batch.emission_records.all().update(
                is_locked=True,
                locked_at=timezone.now(),
                locked_by=request.user,
            )

        return Response({
            'message': f'Batch approved. {emission_records_created} emission records created and locked.',
            'batch': IngestionBatchSerializer(batch).data,
        })

    @action(detail=True, methods=['post'], url_path='reject',
            parser_classes=[JSONParser, FormParser])
    def reject(self, request, pk=None):
        batch = self.get_object()
        batch.status = 'rejected'
        batch.reviewed_by = request.user
        batch.reviewed_at = timezone.now()
        batch.notes = request.data.get('notes', batch.notes)
        batch.save()
        return Response(IngestionBatchSerializer(batch).data)

    @action(detail=True, methods=['get'], url_path='rows')
    def rows(self, request, pk=None):
        """Get all rows for a batch across all source types."""
        batch = self.get_object()
        status_filter = request.query_params.get('status')

        result = {'sap_rows': [], 'utility_rows': [], 'travel_rows': []}

        if batch.source_type == 'sap_fuel_procurement':
            qs = batch.sap_rows.all()
            if status_filter:
                qs = qs.filter(status=status_filter)
            result['sap_rows'] = RawSAPRowSerializer(qs, many=True).data

        elif batch.source_type == 'utility_electricity':
            qs = batch.utility_rows.all()
            if status_filter:
                qs = qs.filter(status=status_filter)
            result['utility_rows'] = RawUtilityRowSerializer(qs, many=True).data

        elif batch.source_type == 'travel_corporate':
            qs = batch.travel_rows.all()
            if status_filter:
                qs = qs.filter(status=status_filter)
            result['travel_rows'] = RawTravelRowSerializer(qs, many=True).data

        return Response(result)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def dashboard_stats(request):
    """Summary statistics for the analyst dashboard."""
    org = get_user_org(request.user)
    if not org:
        return Response({'error': 'No organisation'}, status=404)

    batches = IngestionBatch.objects.filter(organisation=org)
    records = EmissionRecord.objects.filter(organisation=org, is_locked=True)

    scope_totals = records.values('scope').annotate(total=Sum('co2e_tonnes'))
    scope_map = {s['scope']: float(s['total'] or 0) for s in scope_totals}

    total_co2e = sum(scope_map.values())

    by_source = {
        'sap_fuel_procurement': float(
            records.filter(source_sap_row__isnull=False).aggregate(t=Sum('co2e_tonnes'))['t'] or 0
        ),
        'utility_electricity': float(
            records.filter(source_utility_row__isnull=False).aggregate(t=Sum('co2e_tonnes'))['t'] or 0
        ),
        'travel_corporate': float(
            records.filter(source_travel_row__isnull=False).aggregate(t=Sum('co2e_tonnes'))['t'] or 0
        ),
    }

    # Monthly breakdown for chart
    from django.db.models.functions import TruncMonth
    monthly = records.annotate(month=TruncMonth('activity_period_start')).values(
        'month', 'scope'
    ).annotate(total=Sum('co2e_tonnes')).order_by('month')

    month_dict = {}
    for m in monthly:
        if m['month']:
            key = m['month'].strftime('%Y-%m')
            if key not in month_dict:
                month_dict[key] = {'month': key, 'scope1': 0, 'scope2': 0, 'scope3': 0}
            scope_key = m['scope'].split('_')[0]  # scope1, scope2, scope3
            month_dict[key][scope_key] = float(m['total'] or 0)

    return Response({
        'total_batches': batches.count(),
        'pending_batches': batches.filter(status='pending').count(),
        'approved_batches': batches.filter(status='approved').count(),
        'rejected_batches': batches.filter(status='rejected').count(),
        'total_co2e_tonnes': total_co2e,
        'scope1_tonnes': scope_map.get('scope1', 0),
        'scope2_tonnes': scope_map.get('scope2_location', 0) + scope_map.get('scope2_market', 0),
        'scope3_tonnes': scope_map.get('scope3', 0),
        'by_source': by_source,
        'by_month': sorted(month_dict.values(), key=lambda x: x['month']),
        'suspicious_rows': {
            'sap': org.sap_rows.filter(status='suspicious').count(),
            'utility': org.utility_rows.filter(status='suspicious').count(),
            'travel': org.travel_rows.filter(status='suspicious').count(),
        }
    })


class EmissionRecordViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = EmissionRecordSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ['scope', 'category', 'is_locked']
    search_fields = ['notes']
    ordering_fields = ['activity_period_start', 'co2e_tonnes', 'created_at']

    def get_queryset(self):
        org = get_user_org(self.request.user)
        if not org:
            return EmissionRecord.objects.none()
        return EmissionRecord.objects.filter(organisation=org).select_related(
            'batch', 'locked_by', 'source_sap_row', 'source_utility_row', 'source_travel_row'
        )


# ─── Parser dispatch helpers ───────────────────────────────────────────────────

def _parse_file(source_type: str, content: bytes, filename: str) -> dict:
    if source_type == 'sap_fuel_procurement':
        return parse_sap_file(content, filename)
    elif source_type == 'utility_electricity':
        return parse_utility_file(content, filename)
    elif source_type == 'travel_corporate':
        return parse_travel_file(content, filename)
    return {'rows': [], 'errors': [], 'warnings': [], 'period_start': None, 'period_end': None}


def _sap_row_fields(d: dict) -> dict:
    fields = [
        'row_number', 'plant_code', 'plant_name', 'cost_center',
        'material_number', 'material_description', 'document_number', 'document_type',
        'posting_date_raw', 'posting_date', 'quantity_raw', 'quantity',
        'unit_of_measure_raw', 'unit_of_measure_normalized',
        'fuel_type', 'is_fuel', 'is_procurement',
        'quantity_normalized', 'quantity_normalized_unit',
        'suspicious_reason', 'parse_error', 'status',
    ]
    SENTINEL = object()
    return {k: d.get(k, SENTINEL) for k in fields if d.get(k, SENTINEL) is not SENTINEL}


def _utility_row_fields(d: dict) -> dict:
    fields = [
        'row_number', 'account_number', 'meter_id', 'site_name', 'site_address',
        'tariff_category', 'billing_period_start', 'billing_period_end',
        'billing_period_days', 'units_consumed_raw', 'units_consumed_kwh',
        'opening_reading', 'closing_reading', 'multiplier',
        'peak_units_kwh', 'off_peak_units_kwh', 'reactive_units_kvarh',
        'bill_amount', 'currency', 'grid_region', 'emission_factor_used',
        'suspicious_reason', 'parse_error', 'status',
    ]
    SENTINEL = object()
    return {k: d.get(k, SENTINEL) for k in fields if d.get(k, SENTINEL) is not SENTINEL}


def _travel_row_fields(d: dict) -> dict:
    fields = [
        'row_number', 'employee_id', 'department', 'cost_center',
        'travel_type', 'travel_date', 'booking_reference', 'vendor',
        'origin_iata', 'destination_iata', 'distance_km', 'distance_source',
        'cabin_class', 'is_return', 'num_passengers',
        'check_in_date', 'check_out_date', 'nights', 'hotel_country', 'hotel_city',
        'distance_km_ground', 'transport_mode_detail',
        'amount', 'currency',
        'suspicious_reason', 'parse_error', 'status',
    ]
    # Use SENTINEL to distinguish "key missing from dict" vs "key present but None/False/0"
    SENTINEL = object()
    result = {}
    for k in fields:
        val = d.get(k, SENTINEL)
        if val is not SENTINEL:
            result[k] = val
    return result

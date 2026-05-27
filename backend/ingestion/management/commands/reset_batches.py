"""
Management command: python manage.py reset_batches

Clears all ingestion batches and raw rows so you can re-upload
sample files cleanly. Does NOT delete organisations or users.
Use this when you have corrupt/broken batches from before bug fixes.
"""
from django.core.management.base import BaseCommand
from ingestion.models import IngestionBatch, RawSAPRow, RawUtilityRow, RawTravelRow, EmissionRecord


class Command(BaseCommand):
    help = 'Delete all batches and raw rows (keeps org + users). Use after bug fixes.'

    def add_arguments(self, parser):
        parser.add_argument('--yes', action='store_true', help='Skip confirmation')

    def handle(self, *args, **options):
        if not options['yes']:
            confirm = input('This deletes ALL batches and emission records. Type "yes" to continue: ')
            if confirm.strip().lower() != 'yes':
                self.stdout.write('Aborted.')
                return

        em = EmissionRecord.objects.all().delete()
        sap = RawSAPRow.objects.all().delete()
        util = RawUtilityRow.objects.all().delete()
        travel = RawTravelRow.objects.all().delete()
        batches = IngestionBatch.objects.all().delete()

        self.stdout.write(self.style.SUCCESS(
            f'✓ Cleared: {batches[0]} batches, {em[0]} emission records, '
            f'{sap[0]} SAP rows, {util[0]} utility rows, {travel[0]} travel rows.\n'
            f'  You can now re-upload all three sample files cleanly.'
        ))

"""
Management command: python manage.py setup_demo

Creates demo org, users, and loads sample data files.
"""
import os
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from ingestion.models import Organisation, OrganisationMembership


class Command(BaseCommand):
    help = 'Set up demo organisation and users'

    def handle(self, *args, **options):
        # Create org
        org, created = Organisation.objects.get_or_create(
            slug='acme-corp',
            defaults={
                'name': 'ACME Manufacturing Ltd',
                'country_code': 'IN',
                'reporting_year_start': 4,
            }
        )
        if created:
            self.stdout.write(f'Created organisation: {org.name}')
        else:
            self.stdout.write(f'Organisation exists: {org.name}')

        # Create analyst user
        analyst, created = User.objects.get_or_create(
            username='analyst',
            defaults={
                'email': 'analyst@acme.com',
                'first_name': 'Priya',
                'last_name': 'Sharma',
            }
        )
        analyst.set_password('breathe2024')
        analyst.save()
        OrganisationMembership.objects.get_or_create(
            user=analyst, organisation=org,
            defaults={'role': 'analyst'}
        )

        # Create approver user
        approver, created = User.objects.get_or_create(
            username='approver',
            defaults={
                'email': 'approver@acme.com',
                'first_name': 'Arjun',
                'last_name': 'Patel',
            }
        )
        approver.set_password('breathe2024')
        approver.save()
        OrganisationMembership.objects.get_or_create(
            user=approver, organisation=org,
            defaults={'role': 'approver'}
        )

        # Create admin user
        admin_user, _ = User.objects.get_or_create(
            username='admin',
            defaults={'email': 'admin@acme.com', 'is_staff': True, 'is_superuser': True}
        )
        admin_user.set_password('breathe2024')
        admin_user.save()
        OrganisationMembership.objects.get_or_create(
            user=admin_user, organisation=org,
            defaults={'role': 'admin'}
        )

        self.stdout.write(self.style.SUCCESS(
            '\n✓ Demo setup complete!\n'
            '  Credentials (all passwords: breathe2024):\n'
            '  - analyst / breathe2024  (Analyst role)\n'
            '  - approver / breathe2024 (Approver role)\n'
            '  - admin / breathe2024    (Admin/Superuser)\n'
        ))

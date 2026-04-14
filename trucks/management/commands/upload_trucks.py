# management/commands/upload_trucks.py

import csv
from django.core.management.base import BaseCommand
from django.db import transaction
from trucks.models import Truck, Driver
from decimal import Decimal


class Command(BaseCommand):
    help = 'Upload trucks from CSV file'

    def add_arguments(self, parser):
        parser.add_argument('csv_file', type=str, help='Path to CSV file')

    def handle(self, *args, **options):
        csv_file = options['csv_file']

        created = 0
        updated = 0
        errors = []

        with open(csv_file, 'r') as file:
            reader = csv.DictReader(file)

            with transaction.atomic():
                for row in reader:
                    try:
                        truck_number = row['truck_number'].strip()
                        capacity_tons = Decimal(row['capacity_tons'])
                        driver_phone = row['driver_phone'].strip()

                        # Find driver by phone
                        driver = Driver.objects.filter(phone=driver_phone).first()

                        # Create or update truck
                        truck, is_created = Truck.objects.update_or_create(
                            truck_number=truck_number,
                            defaults={
                                'capacity_tons': capacity_tons,
                                'current_driver': driver,
                                'truck_type': 'flatbed',
                                'is_active': True,
                            }
                        )

                        if is_created:
                            created += 1
                            self.stdout.write(f'✓ Created: {truck_number}')
                        else:
                            updated += 1
                            self.stdout.write(f'↻ Updated: {truck_number}')

                    except Exception as e:
                        error = f'{truck_number}: {str(e)}'
                        errors.append(error)
                        self.stdout.write(self.style.ERROR(f'✗ {error}'))

        # Summary
        self.stdout.write(self.style.SUCCESS(f'\n✅ Done: {created} created, {updated} updated'))
        if errors:
            self.stdout.write(self.style.ERROR(f'❌ Errors: {len(errors)}'))
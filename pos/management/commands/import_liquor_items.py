# yourapp/management/commands/import_liquor_items.py

import csv
from decimal import Decimal
from django.core.management.base import BaseCommand
from pos.models import MenuItem, Category

class Command(BaseCommand):
    help = 'Import liquor items into MenuItem model from CSV'

    def add_arguments(self, parser):
        parser.add_argument('csv_file', type=str, help='Path to CSV file')

    def handle(self, *args, **kwargs):
        path = kwargs['csv_file']

        with open(path, newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                try:
                    category, _ = Category.objects.get_or_create(name=row['category'])

                    item, created = MenuItem.objects.get_or_create(
                        name=row['name'],
                        defaults={
                            'unit_of_measure': row['unit_of_measure'],
                            'category': category,
                            'selling_price': Decimal(row['selling_price']),
                            'supplier_cost_price': Decimal(row['supplier_cost_price']),
                            'stock_quantity': Decimal(row['stock_quantity']),
                            'low_stock_threshold': Decimal(row['low_stock_threshold']),
                            'is_recipe': row['is_recipe'].lower() == 'true',
                            'is_sold_by_weight': row['is_sold_by_weight'].lower() == 'true',
                            'is_active': row['is_active'].lower() == 'true',
                        }
                    )
                    action = "Created" if created else "Skipped (exists)"
                    self.stdout.write(f"{action}: {item.name}")
                except Exception as e:
                    self.stderr.write(f"Error importing {row['name']}: {str(e)}")

        self.stdout.write(self.style.SUCCESS('✅ Import complete!'))

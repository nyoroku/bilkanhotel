from django.core.management.base import BaseCommand
from pos.models import MenuItem

class Command(BaseCommand):
    help = 'Detect and log menu item duplicates'

    def handle(self, *args, **options):
        stats = MenuItem.get_duplicate_stats()
        groups = stats['groups']
        total_dupes = stats['total_duplicates']

        if total_dupes == 0:
            self.stdout.write(
                self.style.SUCCESS("✅ No duplicate menu items found.")
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    f"⚠️ Found {total_dupes} duplicate items in {len(groups)} groups:"
                )
            )
            for i, group in enumerate(groups, 1):
                names = " | ".join(group['names'])
                self.stdout.write(f"  Group {i}: {names}")
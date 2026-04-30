import csv
from io import TextIOWrapper

from django.http import HttpResponse
from django.shortcuts import redirect
from django.contrib import admin, messages
from django.urls import path

from unfold.admin import ModelAdmin

from .models import TruckLogisticsRecord


@admin.register(TruckLogisticsRecord)
class TruckLogisticsRecordAdmin(ModelAdmin):
    list_display = (
        'date', 'truck_number', 'transporter', 'destination',
        'tonnage', 'fuel_amount', 'rate_per_ton', 'total_transport_amount',
        'status', 'delivery_status', 'remarks'
    )
    list_filter = ('date', 'transporter', 'destination', 'status', 'delivery_status')
    search_fields = ('truck_number', 'destination', 'remarks')
    actions = ['export_as_csv']

    change_list_template = "admin/trucks/trucklogisticsrecord/change_list.html"

    # Add custom URL for import
    def get_urls(self):
        default_urls = super().get_urls()
        custom_urls = [
            path("import-csv/", self.admin_site.admin_view(self.import_csv), name="import_logistics_csv"),
        ]
        return custom_urls + default_urls

    # CSV import logic
    def import_csv(self, request):
        if request.method == "POST" and request.FILES.get("csv_file"):
            csv_file = TextIOWrapper(request.FILES["csv_file"].file, encoding="utf-8")
            reader = csv.DictReader(csv_file)
            success_count = 0
            error_count = 0

            for row in reader:
                try:
                    TruckLogisticsRecord.objects.create(
                        date=row.get('Date') or row.get('date'),
                        truck_number=row.get('Truck') or row.get('truck_number', ''),
                        transporter=row.get('Transporter') or row.get('transporter', ''),
                        destination=row.get('Destination') or row.get('destination', ''),
                        tonnage=row.get('Tonnage') or row.get('tonnage'),
                        status=row.get('Status') or row.get('status', ''),
                        delivery_status=row.get('Delivery') or row.get('delivery_status', ''),
                        rate_per_ton=row.get('Rate/Ton') or row.get('rate_per_ton'),
                        total_transport_amount=row.get('Total Transport') or row.get('total_transport_amount'),
                        litres_of_fuel=row.get('Litres') or row.get('litres_of_fuel'),
                        fuel_amount=row.get('Fuel Amount') or row.get('fuel_amount'),
                        is_loaded=True,
                        remarks=row.get('Remarks') or row.get('remarks', ''),
                        source_document="CSV Import"
                    )
                    success_count += 1
                except Exception as e:
                    messages.error(request, f"Row error: {row} — {str(e)}")
                    error_count += 1

            if success_count:
                messages.success(request, f"✅ Successfully imported {success_count} records.")
            if error_count:
                messages.warning(request, f"⚠️ {error_count} records failed to import. Check error messages.")

        return redirect("..")

    # CSV export logic
    def export_as_csv(self, request, queryset):
        meta = self.model._meta
        field_names = [field.name for field in meta.fields]

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="{meta.model_name}_export.csv"'
        writer = csv.writer(response)

        writer.writerow(field_names)
        for obj in queryset:
            writer.writerow([getattr(obj, field) for field in field_names])

        return response

    export_as_csv.short_description = "📤 Export selected records to CSV"



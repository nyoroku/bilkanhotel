# urls.py — Final, Cleaned, No trip_record paths
from django.urls import path
from . import views

app_name = 'trucks'

urlpatterns = [
    # ----------------------------------------------------------
    # 1.  CORE  REPORTING  &  DASHBOARD
    # ----------------------------------------------------------
    path('logistics/report/', views.logistics_report_view, name='logistics_report'),
    path('logistics/print/', views.print_logistics_report_view, name='print_logistics_report'),
    path('dashboard/', views.dashboard_view, name='dashboard_view'),

    # ----------------------------------------------------------
    # 2.  INVOICE  CRUD
    # ----------------------------------------------------------
    path('invoices/', views.invoice_list_view, name='invoice_list'),
    path('invoices/create/', views.invoice_create_view, name='invoice_create'),
    path('invoices/<int:pk>/', views.invoice_detail_view, name='invoice_detail'),
    path('invoices/<int:invoice_id>/payments/create/', views.payment_create_view, name='payment_create'),
    path('invoices/<int:invoice_id>/credits/create/', views.invoice_credit_create_view, name='invoice_credit_create'),
    path('invoices/create/from-trips/', views.invoice_create_from_trips_view, name='invoice_create_from_trips'),
    # ----------------------------------------------------------
    # 3.  TRIP  CRUD  (operational)
    # ----------------------------------------------------------
    path('trips/', views.trip_list_view, name='trip_list'),
    path('trips/create/', views.trip_create_view, name='trip_create'),
    path('trips/<int:pk>/edit/', views.trip_edit_view, name='trip_edit'),
    path('trips/<int:pk>/', views.trip_detail_view, name='trip_detail'),


    # ----------------------------------------------------------
    # 4.  EXPENSE  CRUD
    # ----------------------------------------------------------
    path('trucks/expenses/', views.expense_list_view, name='expense_list'),
    path('trucks/expenses/create/', views.expense_create_view, name='expense_create'),

    # ----------------------------------------------------------
    # 5.  MASTER  TABLES  –  SINGLE  CRUD  PATTERN
    # ----------------------------------------------------------
    # drivers
    path('drivers/', views.driver_list_view, name='driver_list'),
    path('drivers/create/', views.driver_create_view, name='driver_create'),
    path('drivers/<int:pk>/', views.driver_detail_view, name='driver_detail'),
    path('drivers/<int:pk>/edit/', views.driver_edit_view, name='driver_edit'),
    path('drivers/<int:pk>/delete/', views.driver_delete_view, name='driver_delete'),

    # trucks
    path('trucks/', views.truck_list_view, name='truck_list'),
    path('trucks/create/', views.truck_create_view, name='truck_create'),
    path('trucks/<int:pk>/', views.truck_detail_view, name='truck_detail'),
    path('trucks/<int:pk>/edit/', views.truck_edit_view, name='truck_edit'),
    path('trucks/<int:pk>/delete/', views.truck_delete_view, name='truck_delete'),

    # destinations
    path('destinations/', views.destination_list_view, name='destination_list'),
    path('destinations/create/', views.destination_create_view, name='destination_create'),
    path('destinations/<int:pk>/edit/', views.destination_edit_view, name='destination_edit'),
    path('destinations/<int:pk>/delete/', views.destination_delete_view, name='destination_delete'),

    # transporters
    path('transporters/', views.transporter_list_view, name='transporter_list'),
    path('transporters/create/', views.transporter_create_view, name='transporter_create'),
    path('transporters/<int:pk>/edit/', views.transporter_edit_view, name='transporter_edit'),
    path('transporters/<int:pk>/delete/', views.transporter_delete_view, name='transporter_delete'),

    # expense categories
    path('expense-categories/', views.expense_category_list_view, name='expense_category_list'),
    path('expense-categories/create/', views.expense_category_create_view, name='expense_category_create'),
    path('expense-categories/<int:pk>/edit/', views.expense_category_edit_view, name='expense_category_edit'),
    path('expense-categories/<int:pk>/delete/', views.expense_category_delete_view, name='expense_category_delete'),

    # cargo types
    path('cargo-types/', views.cargo_type_list_view, name='cargo_type_list'),
    path('cargo-types/create/', views.cargo_type_create_view, name='cargo_type_create'),
    path('cargo-types/<int:pk>/edit/', views.cargo_type_edit_view, name='cargo_type_edit'),
    path('cargo-types/<int:pk>/delete/', views.cargo_type_delete_view, name='cargo_type_delete'),

    # ----------------------------------------------------------
    # 6.  HTMX  API  END-POINTS
    # ----------------------------------------------------------
    path('api/truck-info/<int:truck_id>/', views.api_truck_info, name='api_truck_info'),
    path('api/destination-info/<int:destination_id>/', views.api_destination_info, name='api_destination_info'),
    path('api/transporter-invoices/<int:transporter_id>/', views.api_transporter_invoices, name='api_transporter_invoices'),
    path('api/calculate-transport-amount/', views.api_calculate_transport_amount, name='api_calculate_transport_amount'),
    path('api/calculate-fuel-amount/', views.api_calculate_fuel_amount, name='api_calculate_fuel_amount'),
    path('api/invoice-summary/<int:invoice_id>/', views.api_invoice_summary, name='api_invoice_summary'),

    path('analytics/', views.analytics_dashboard_view, name='analytics_dashboard'),
    path('analytics/trucks/comparison/', views.truck_comparison_view, name='truck_comparison'),
    path('analytics/trips/profitability/', views.trip_profitability_view, name='trip_profitability'),
    path('analytics/api/chart-data/', views.analytics_api_chart_data, name='analytics_api_chart_data'),
]
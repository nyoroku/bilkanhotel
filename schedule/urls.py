# schedule/urls.py
from django.urls import path
from . import views
from .views_shift_stock import shift_stock_open, shift_stock_close, shift_stock_report

app_name = 'schedule'

urlpatterns = [
    # --- Schedule CRUD
    path('schedules/', views.ScheduleListView.as_view(), name='schedule_list'),
    path('schedules/new/', views.ScheduleCreateView.as_view(), name='schedule_create'),
    path('schedules/<int:pk>/', views.ScheduleDetailView.as_view(), name='schedule_detail'),
    path('schedules/<int:pk>/edit/', views.ScheduleUpdateView.as_view(), name='schedule_edit'),
    path('schedules/<int:pk>/delete/', views.ScheduleDeleteView.as_view(), name='schedule_delete'),

    # --- Shift CRUD
    path('schedules/<int:schedule_pk>/add-shift/', views.ShiftCreateView.as_view(), name='shift_create'),
    path('shifts/<int:pk>/edit/', views.ShiftUpdateView.as_view(), name='shift_edit'),
    path('shifts/<int:pk>/delete/', views.ShiftDeleteView.as_view(), name='shift_delete'),
    path('shift/<str:section>/stock/open/', shift_stock_open, name='shift_stock_open'),
    path('shift/<str:section>/stock/close/', shift_stock_close, name='shift_stock_close'),
    path('shift/<int:shift_id>/<str:section>/report/', shift_stock_report, name='shift_stock_report'),
    # --- Shift-assignment CRUD
    path('shifts/<int:pk>/assignments/<uuid:user_id>/delete/',
         views.ShiftAssignmentDeleteView.as_view(), name='shift_assignment_delete'),

    # --- Swap two staff between two shifts
    path('swap/', views.swap_shift_assignments, name='shift_swap'),
    path('my-shift/sales/', views.shift_sales_summary_view, name='shift_sales_summary'),
    # --- Ajax helpers
    path('shift/<int:shift_id>/available-users/',
         views.get_available_users_for_shift,
         name='get_available_users'),

    path('my-schedule/', views.MyScheduleView.as_view(), name='my_schedule'),
    path('swap-request/<int:pk>/', views.create_swap_request, name='create_swap_request'),
    path('swap-requests/', views.SwapRequestListView.as_view(), name='swap_request_list'),
    path('swap-requests/<int:pk>/approve/', views.approve_swap, name='approve_swap'),
    path('swap-requests/<int:pk>/reject/', views.reject_swap, name='reject_swap'),
    path('shifts/assign-user/', views.ShiftAssignmentCreateView.as_view(), name='shift_assignment_create'),
    path('shift-summary/<str:section>/', views.section_shift_summary_view, name='section_shift_summary'),
    path('shift/<int:shift_id>/handover/', views.shift_handover_summary, name='shift_handover_summary'),
]
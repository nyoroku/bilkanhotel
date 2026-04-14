# accounts/urls.py

from django.urls import path
from . import views

# This app_name is crucial for namespacing your URLs,
# allowing you to use names like 'accounts:pin_login' in your templates.
app_name = 'accounts'

urlpatterns = [
    # --- PIN Login System URLs ---
    path('login/', views.pin_login_view, name='pin_login'),
    path('logout/', views.user_logout_view, name='user_logout'),
    path('process-pin-login/', views.process_pin_login, name='process_pin_login'),

    # --- Staff Management URLs ---
    path('staff/', views.staff_list_view, name='staff_list'),
    path('staff/add/', views.staff_add_view, name='staff_add'),
    path('staff/<uuid:pk>/edit/', views.staff_edit_view, name='staff_edit'),
    path('staff/<uuid:pk>/delete/', views.staff_delete_view, name='staff_delete'),
]

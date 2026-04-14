from django.urls import path
from . import views

app_name = 'rooms'
urlpatterns = [
    path('', views.rooms_dashboard, name='rooms_dashboard'),
    path('list/', views.room_list, name='room_list'),
    path('add/', views.room_add, name='room_add'),
    path('edit/<int:pk>/', views.room_edit, name='room_edit'),
    path('check-in/', views.booking_create, name='booking_create'),
    path('pay/<int:pk>/', views.booking_pay, name='booking_pay'),
    path('checkout/<int:pk>/', views.booking_checkout, name='booking_checkout'),
]

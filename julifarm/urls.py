from django.urls import path
from . import views

app_name = 'julifarm'
urlpatterns = [
    path('food/', views.food_menu, name='food_menu'),
    path('drinks/', views.drinks_menu, name='drinks_menu'),
    path('events/', views.events, name='events'),
    path('events/<slug:slug>/', views.event_detail, name='event_detail'),
]


